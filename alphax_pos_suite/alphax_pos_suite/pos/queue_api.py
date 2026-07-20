"""Server side of the offline sale queue.

Until v15.7.10 the SPA flushed queued sales through the generic
frappe.client.insert + frappe.client.submit pair. That had three
problems, all observed in the field (testneo.frappe.cloud):

* two round-trips with a failure window between them (insert ok,
  submit failed → draft strays)
* core-ERPNext exceptions surfaced to the register as bare messages
  ("cannot unpack non-iterable NoneType object") with the traceback
  discarded — undiagnosable from the till
* no place to translate well-known fresh-site setup gaps into
  actionable errors

push_queued_invoice does insert + submit in ONE call, logs the full
traceback to Error Log (desk → Error Log, title "AlphaX POS: queue
push failed") on any failure, and preflights the common gaps first so
the cashier sees "No Fiscal Year covers 2026-07-13 for company X"
instead of a TypeError from deep inside GL posting.
"""

from __future__ import annotations

import json

import frappe
from frappe import _


@frappe.whitelist()
def push_queued_invoice(doc):
    """Insert + submit one queued Sales Invoice. Returns {ok, name}.

    Dedupe: if a Sales Invoice already carries this alphax_client_uuid,
    returns it instead of inserting again — the client marks the queue
    row synced. (The before_insert hook still guards the raw-insert
    path for older SPAs.)
    """
    if isinstance(doc, str):
        doc = json.loads(doc)
    if not isinstance(doc, dict) or doc.get("doctype") != "Sales Invoice":
        frappe.throw(_("push_queued_invoice only accepts a Sales Invoice document"))

    uuid = doc.get("alphax_client_uuid")
    if uuid:
        existing = frappe.db.get_value(
            "Sales Invoice",
            {"alphax_client_uuid": uuid},
            ["name", "docstatus"],
            as_dict=True,
        )
        if existing:
            if existing.docstatus == 0:
                # Stray draft from the old two-call flow: finish the job.
                try:
                    si = frappe.get_doc("Sales Invoice", existing.name)
                    si.submit()
                except Exception:
                    frappe.log_error(
                        title="AlphaX POS: queue push failed (submitting stray draft)",
                        message=frappe.get_traceback(),
                    )
                    raise
            return {"ok": True, "name": existing.name, "duplicate": True}

    _heal_customer(doc)
    _preflight(doc)

    try:
        si = frappe.get_doc(doc)
        si.insert()  # normal permissions; dedupe before_insert hook runs
        si.submit()
        return {"ok": True, "name": si.name}
    except Exception:
        # The register can only show one line; the full story goes to
        # Error Log where support can actually read it.
        frappe.log_error(
            title="AlphaX POS: queue push failed",
            message=frappe.get_traceback(),
        )
        raise


def _preflight(doc):
    """Translate well-known fresh-site setup gaps into fix-it errors.

    Each check mirrors a real opaque failure mode of core ERPNext when
    a site is young. Checks are cheap lookups; anything not covered
    falls through to insert/submit and gets full-traceback logging.
    """
    company = doc.get("company")
    if not company:
        frappe.throw(_("Queued sale has no company. Check the POS Profile's company."))
    if not frappe.db.exists("Company", company):
        frappe.throw(_("Company {0} does not exist on this site.").format(company))

    posting_date = doc.get("posting_date")
    if posting_date:
        fy = frappe.db.sql(
            """
            select fy.name
            from `tabFiscal Year` fy
            where fy.disabled = 0
              and %(d)s between fy.year_start_date and fy.year_end_date
              and (
                    not exists (
                        select 1 from `tabFiscal Year Company` fyc
                        where fyc.parent = fy.name
                    )
                    or exists (
                        select 1 from `tabFiscal Year Company` fyc
                        where fyc.parent = fy.name and fyc.company = %(c)s
                    )
              )
            limit 1
            """,
            {"d": posting_date, "c": company},
        )
        if not fy:
            frappe.throw(
                _(
                    "No Fiscal Year covers {0} for company {1}. "
                    "Create one under Accounting → Fiscal Year (and if you restrict "
                    "fiscal years to companies, include {1}), then retry — the queued "
                    "sale will sync automatically."
                ).format(posting_date, company)
            )

    receivable = frappe.db.get_value("Company", company, "default_receivable_account")
    if not receivable and doc.get("customer"):
        frappe.throw(
            _(
                "Company {0} has no Default Receivable Account. "
                "Set it on the Company record (Accounting section), then retry."
            ).format(company)
        )

    customer = doc.get("customer")
    if customer and not frappe.db.exists("Customer", customer):
        frappe.throw(
            _(
                "Customer {0} does not exist on this site. "
                "The terminal's default customer must exist here."
            ).format(customer)
        )

    for p in doc.get("payments") or []:
        mop = p.get("mode_of_payment")
        if mop and not frappe.db.exists(
            "Mode of Payment Account", {"parent": mop, "company": company}
        ):
            frappe.throw(
                _(
                    "Mode of Payment {0} has no account set for company {1}. "
                    "Open Mode of Payment {0} → Accounts and add a row for {1}."
                ).format(mop, company)
            )


def _heal_customer(doc):
    """Substitute a real customer for placeholder/unknown ones in QUEUED
    payloads.

    Pre-v15.7.12 SPAs stamped '__Walk-in' (a customer that exists on no
    site) when boot delivered no default customer — those payloads are
    frozen in registers' IndexedDB queues and would fail forever. When
    the payload's customer doesn't exist, substitute the terminal's
    default customer (then the global settings one), validated to
    exist, and note the substitution in remarks for the audit trail.
    If nothing valid is available, leave it for _preflight's clear
    error rather than inventing data.
    """
    customer = doc.get("customer")
    if customer and frappe.db.exists("Customer", customer):
        return

    replacement = None
    terminal = doc.get("alphax_pos_terminal")
    if terminal:
        cand = frappe.db.get_value("AlphaX POS Terminal", terminal, "default_customer")
        if cand and frappe.db.exists("Customer", cand):
            replacement = cand
    if not replacement:
        try:
            cand = frappe.db.get_single_value("AlphaX POS Settings", "default_customer")
            if cand and frappe.db.exists("Customer", cand):
                replacement = cand
        except Exception:
            pass

    if replacement:
        note = _("Customer '{0}' from the register queue does not exist; substituted terminal default '{1}'.").format(
            customer or "", replacement
        )
        doc["customer"] = replacement
        doc["remarks"] = ((doc.get("remarks") or "") + "\n" + note).strip()
