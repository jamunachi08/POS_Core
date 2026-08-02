"""
Sales Invoice dedupe.

When the cashier SPA is offline, sales are queued in IndexedDB with a
client_uuid. When connectivity returns, the queue worker submits each
queued sale. If the original online submit had already gone through
(e.g. the network dropped *after* the server accepted but *before* the
client got the response), we'd otherwise create a duplicate invoice.

This hook looks up Sales Invoice by `alphax_client_uuid` and:

  * if a submitted match exists, throws a clean `DuplicateEntryError`
    that the SPA detects and treats as "already synced"
  * if a draft match exists, raises so the SPA can decide what to do

The custom field `alphax_client_uuid` is created by the v15.0 patch.
"""
from __future__ import annotations

import frappe
from frappe import _


class DuplicateEntryError(frappe.ValidationError):
    """Raised when a Sales Invoice with the same alphax_client_uuid exists."""


def sales_invoice_before_insert(doc, method=None):
    uuid = getattr(doc, "alphax_client_uuid", None)
    if not uuid:
        return  # not from the cashier SPA

    _enforce_business_date(doc)

    existing = frappe.db.get_all(
        "Sales Invoice",
        filters={"alphax_client_uuid": uuid},
        fields=["name", "docstatus"],
        limit=1,
    )
    if not existing:
        return

    row = existing[0]
    # Submitted (1) or draft (0) — either way, the SPA already pushed this once.
    # We surface the existing name so the SPA can update its queue row.
    if row.docstatus == 1:
        frappe.throw(
            _("This sale has already been recorded as {0}.").format(row.name),
            DuplicateEntryError,
            title=_("Duplicate sale"),
        )
    elif row.docstatus == 0:
        # Draft already exists. Throw so the SPA submits the existing draft
        # rather than creating a second one.
        frappe.throw(
            _("A draft already exists for this sale: {0}.").format(row.name),
            DuplicateEntryError,
            title=_("Duplicate draft"),
        )
    # docstatus == 2 (cancelled) — let the new insert proceed.


def _enforce_business_date(doc):
    """Every register sale posts on its shift's trading day.

    The SPA stamps posting_date with the business date AT SALE TIME (so
    a sale queued offline at 12:30 AM keeps yesterday's trading day even
    if it only syncs after day close). Server side we (a) make ERPNext
    honor the stamped date by forcing set_posting_time, and (b) fill the
    date from the terminal's current business date when an older SPA
    didn't stamp it. Runs only for register-originated invoices
    (identified by alphax_client_uuid).
    """
    doc.set_posting_time = 1
    if getattr(doc, "posting_date", None):
        return
    terminal = getattr(doc, "alphax_pos_terminal", None)
    if terminal:
        bd = frappe.db.get_value(
            "AlphaX POS Terminal", terminal, "current_business_date"
        )
        if bd:
            doc.posting_date = bd
