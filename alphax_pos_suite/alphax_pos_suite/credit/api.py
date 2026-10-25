"""
AlphaX POS — store credit.

The concept comes from POSNext's customer wallet; the implementation is
ours, and differs on the three points that decide whether it survives a
ZATCA audit.

**1. It is a liability, not income.**
Money taken now for goods later is owed, not earned. Booking it to income
at issue overstates revenue in the period it is sold and understates it in
the period it is used. This is a standard audit finding, and it is the
default outcome of every store-credit feature that treats the balance as a
number on a customer record rather than a posting.

**2. VAT attaches on redemption, not on issue.**
Issuing credit is not a supply — nothing has been delivered, so there is
nothing to tax yet. The tax point is when the credit is spent against
goods, at whatever rate those goods carry. Charging VAT at issue and again
at redemption is double taxation; charging it only at issue is wrong when
the customer later buys zero-rated items. Both are recoverable only by
amending returns.

**3. The balance is the ledger.**
A stored balance that drifts from its entries cannot be reconciled after
the fact, because nobody can say which of the two was right. The field on
the parent is a cache; every read that matters recomputes.

Deliberately separate from loyalty points. Points are a marketing accrual
a business may devalue or expire at will. Store credit is the customer's
money. Merging them is convenient until someone asks which part of the
balance is a liability.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, nowdate


def _default_liability_account(company: str) -> str | None:
    """Where unspent credit sits.

    Falls back through the settings, then a conventionally named account,
    and returns None rather than guessing at something plausible — an
    entry posted to the wrong liability account is harder to find than one
    that refused to post.
    """
    try:
        acct = frappe.db.get_single_value("AlphaX POS Settings", "store_credit_account")
        if acct and frappe.db.get_value("Account", acct, "company") == company:
            return acct
    except Exception:
        pass
    abbr = frappe.db.get_value("Company", company, "abbr")
    for candidate in (f"Store Credit Payable - {abbr}", f"Customer Deposits - {abbr}"):
        if frappe.db.exists("Account", candidate):
            return candidate
    return None


@frappe.whitelist()
def get_balance(customer: str | None = None, card_code: str | None = None,
                company: str | None = None):
    """What this customer or card can spend.

    Recomputed from the ledger on every call. The till asks this
    immediately before tendering, so a stale answer here is a real
    overdraw rather than a cosmetic one.
    """
    credit = _find(customer=customer, card_code=card_code, company=company)
    if not credit:
        return {"found": False, "balance": 0, "currency": None}

    doc = frappe.get_doc("AlphaX POS Store Credit", credit)
    balance = doc.recompute()
    expired = bool(doc.expires_on and doc.expires_on < nowdate())

    return {
        "found": True,
        "name": doc.name,
        "customer": doc.customer,
        "balance": balance,
        "spendable": 0 if (expired or doc.status != "Active") else balance,
        "currency": doc.currency,
        "status": doc.status,
        "expires_on": doc.expires_on,
        "expired": expired,
        "card_code": doc.card_code,
    }


def _find(customer=None, card_code=None, company=None):
    if card_code:
        return frappe.db.get_value(
            "AlphaX POS Store Credit", {"card_code": str(card_code).strip().upper()}, "name")
    if customer:
        f = {"customer": customer, "status": "Active"}
        if company:
            f["company"] = company
        return frappe.db.get_value("AlphaX POS Store Credit", f, "name")
    return None


def _ensure(customer: str, company: str, currency: str | None = None) -> str:
    existing = _find(customer=customer, company=company)
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "AlphaX POS Store Credit",
        "customer": customer,
        "company": company,
        "currency": currency or frappe.db.get_value("Company", company, "default_currency"),
        "status": "Active",
        "liability_account": _default_liability_account(company),
    }).insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def issue(customer: str, amount: float, company: str, reason: str = "",
          reference_doctype: str = None, reference_name: str = None,
          terminal: str = None, client_uuid: str = None, expires_on: str = None,
          post_gl: int = 1):
    """Give a customer credit.

    Typically a refund the customer chose to take as credit rather than
    cash, or a prepayment. Posts the liability unless the movement is
    already carried by another document — a return invoice that pays out
    to a credit account has posted it once already, and posting again
    doubles the liability.

    No VAT here. Issuing credit is not a supply.
    """
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Amount must be positive."))

    if client_uuid:
        seen = frappe.db.get_value("AlphaX POS Store Credit Entry",
                                   {"client_uuid": client_uuid}, "name")
        if seen:
            # An offline till retrying is expected, not exceptional.
            return {"ok": True, "entry": seen, "duplicate": True,
                    "balance": get_balance(customer=customer, company=company)["balance"]}

    credit = _ensure(customer, company)
    doc = frappe.get_doc("AlphaX POS Store Credit", credit)
    if expires_on and not doc.expires_on:
        doc.db_set("expires_on", expires_on, update_modified=False)

    entry = frappe.get_doc({
        "doctype": "AlphaX POS Store Credit Entry",
        "store_credit": credit,
        "entry_type": "Issue",
        "amount": amount,
        "posting_date": nowdate(),
        "terminal": terminal,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "client_uuid": client_uuid,
        "remarks": reason,
    }).insert(ignore_permissions=True)
    entry.submit()

    if int(post_gl or 0):
        _post_journal(entry, doc, direction="issue")

    return {"ok": True, "entry": entry.name, "duplicate": False,
            "balance": frappe.db.get_value("AlphaX POS Store Credit", credit, "balance")}


@frappe.whitelist()
def redeem(amount: float, customer: str = None, card_code: str = None,
           company: str = None, reference_doctype: str = None,
           reference_name: str = None, terminal: str = None,
           client_uuid: str = None, post_gl: int = 0):
    """Spend credit against a sale.

    `post_gl` defaults OFF, which is the opposite of `issue`, and the
    reason is worth stating: the normal path is a Sales Invoice carrying a
    payment line against the store-credit account. That invoice already
    debits the liability. Posting a journal here as well would relieve it
    twice and leave the account permanently short.

    Turn it on only for a redemption with no invoice behind it.
    """
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Amount must be positive."))

    if client_uuid:
        seen = frappe.db.get_value("AlphaX POS Store Credit Entry",
                                   {"client_uuid": client_uuid}, "name")
        if seen:
            return {"ok": True, "entry": seen, "duplicate": True}

    name = _find(customer=customer, card_code=card_code, company=company)
    if not name:
        frappe.throw(_("No store credit found for this customer or card."))

    doc = frappe.get_doc("AlphaX POS Store Credit", name)
    if doc.expires_on and doc.expires_on < nowdate():
        frappe.throw(_("This credit expired on {0}.").format(doc.expires_on))

    entry = frappe.get_doc({
        "doctype": "AlphaX POS Store Credit Entry",
        "store_credit": name,
        "entry_type": "Redeem",
        "amount": amount,
        "posting_date": nowdate(),
        "terminal": terminal,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "client_uuid": client_uuid,
    }).insert(ignore_permissions=True)
    entry.submit()

    if int(post_gl or 0):
        _post_journal(entry, doc, direction="redeem")

    return {"ok": True, "entry": entry.name, "duplicate": False,
            "balance": frappe.db.get_value("AlphaX POS Store Credit", name, "balance")}


def _post_journal(entry, credit, direction: str):
    """Move the liability.

    Issue:  debit the funding account (cash paid in, or the return's
            clearing account), credit the store-credit liability.
    Redeem: the reverse.

    Silent on failure is not an option here — an entry whose GL half
    vanished is a balance the books do not know about.
    """
    liability = credit.liability_account or _default_liability_account(credit.company)
    if not liability:
        frappe.throw(_(
            "No store credit liability account for {0}. Set one on the credit, "
            "or as Store Credit Account in AlphaX POS Settings. Unspent credit is "
            "money owed and has to sit somewhere real."
        ).format(credit.company))

    funding = frappe.db.get_value("Company", credit.company, "default_cash_account")
    if not funding:
        frappe.throw(_("Company {0} has no Default Cash Account.").format(credit.company))

    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Journal Entry",
        "company": credit.company,
        "posting_date": entry.posting_date,
        "user_remark": f"AlphaX store credit {direction} — {entry.name}",
        "accounts": [
            {"account": funding if direction == "issue" else liability,
             "debit_in_account_currency": flt(entry.amount),
             "party_type": "Customer" if direction != "issue" else None,
             "party": credit.customer if direction != "issue" else None},
            {"account": liability if direction == "issue" else funding,
             "credit_in_account_currency": flt(entry.amount),
             "party_type": "Customer" if direction == "issue" else None,
             "party": credit.customer if direction == "issue" else None},
        ],
    })
    je.insert(ignore_permissions=True)
    je.submit()
    entry.db_set("journal_entry", je.name, update_modified=False)


@frappe.whitelist()
def statement(customer: str = None, card_code: str = None, limit: int = 50):
    """Movements, newest first. What a customer asks for at the counter."""
    name = _find(customer=customer, card_code=card_code)
    if not name:
        return {"found": False, "entries": []}
    doc = frappe.get_doc("AlphaX POS Store Credit", name)
    return {
        "found": True,
        "name": name,
        "customer": doc.customer,
        "balance": doc.recompute(),
        "currency": doc.currency,
        "entries": frappe.get_all(
            "AlphaX POS Store Credit Entry",
            filters={"store_credit": name, "docstatus": 1},
            fields=["name", "posting_date", "entry_type", "amount", "balance_after",
                    "reference_doctype", "reference_name", "remarks", "terminal"],
            order_by="posting_date desc, creation desc",
            limit_page_length=min(int(limit or 50), 200),
        ),
    }


def expire_stale_credit():
    """Scheduled: retire balances past their expiry date.

    Writes an Expiry entry rather than zeroing the balance, so the
    statement still explains where the money went. Runs daily; safe to run
    twice because an already-zero balance produces no entry.
    """
    today = nowdate()
    due = frappe.get_all(
        "AlphaX POS Store Credit",
        filters={"status": "Active", "expires_on": ["<", today], "balance": [">", 0]},
        fields=["name", "balance"],
    )
    for row in due:
        try:
            doc = frappe.get_doc("AlphaX POS Store Credit", row.name)
            live = doc.recompute()
            if live <= 0:
                continue
            e = frappe.get_doc({
                "doctype": "AlphaX POS Store Credit Entry",
                "store_credit": doc.name,
                "entry_type": "Expiry",
                "amount": live,
                "posting_date": today,
                "remarks": _("Expired on {0}").format(doc.expires_on),
            }).insert(ignore_permissions=True)
            e.submit()
            doc.db_set("status", "Closed", update_modified=False)
        except Exception:
            frappe.log_error(title=f"AlphaX POS: could not expire credit {row.name}",
                             message=frappe.get_traceback())
