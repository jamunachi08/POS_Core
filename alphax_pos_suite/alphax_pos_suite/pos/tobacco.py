"""KSA tobacco fee — the ERPGulf-compatible design.

Constraint (field-confirmed): with VAT-inclusive pricing, the ERPGulf
ZATCA app does not accept item-wise tax templates, and ZATCA's XML has
no category for a non-VAT levy anyway — per ZATCA guidance the 100%
tobacco fee is part of the CONSIDERATION (taxable base), not a tax
subtotal.

So the invoice stays a textbook inclusive S-15% document: sheesha at
SAR 115 → taxable 100, VAT 15 — nothing tobacco-shaped in the XML.
The separate-account-head requirement is met at POSTING time instead:
on submit, this hook computes the fee portion inside each tobacco
line's net (fee = net × r ÷ (100 + r); at 100%: net 100 → 50 sales +
50 fee) and moves it from the line's income account to the configured
liability account with one Journal Entry. Cancel reverses it. The rate,
account, and item group live on AlphaX POS Settings — regulation
changes are a form edit, never development.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def _cfg():
    try:
        s = frappe.get_cached_doc("AlphaX POS Settings")
    except Exception:
        return None
    if not s.get("tobacco_fee_enabled"):
        return None
    if not (s.get("tobacco_fee_account") and s.get("tobacco_item_group")):
        return None
    return {
        "account": s.tobacco_fee_account,
        "rate": flt(s.get("tobacco_fee_rate")) or 100.0,
        "group": s.tobacco_item_group,
    }


def _tobacco_groups(root: str) -> set[str]:
    bounds = frappe.db.get_value("Item Group", root, ["lft", "rgt"], as_dict=True)
    if not bounds:
        return {root}
    return set(
        frappe.get_all(
            "Item Group",
            filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
            pluck="name",
        )
    )


def repost_tobacco_fee(doc, method=None):
    """Sales Invoice on_submit: move the fee portion to the fee account."""
    try:
        cfg = _cfg()
        if not cfg or getattr(doc, "is_return", 0):
            return
        if frappe.db.exists(
            "Journal Entry",
            {"cheque_no": f"TOBACCO::{doc.name}", "docstatus": 1},
        ):
            return  # idempotent

        groups = _tobacco_groups(cfg["group"])
        r = cfg["rate"]
        # fee sits INSIDE the net base: fee = net × r / (100 + r)
        per_income: dict[str, float] = {}
        for it in doc.items:
            ig = frappe.db.get_value("Item", it.item_code, "item_group")
            if ig not in groups:
                continue
            fee = flt(it.base_net_amount) * r / (100.0 + r)
            if fee > 0.005:
                per_income[it.income_account] = per_income.get(it.income_account, 0.0) + fee

        total = sum(per_income.values())
        if total < 0.01:
            return

        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": doc.company,
            "posting_date": doc.posting_date,
            "cheque_no": f"TOBACCO::{doc.name}",
            "cheque_date": doc.posting_date,
            "user_remark": _(
                "KSA tobacco fee split for {0}: {1}% of tobacco base moved "
                "from sales income to the fee account (ZATCA-neutral; the "
                "e-invoice remains plain inclusive VAT)."
            ).format(doc.name, r),
            "accounts": [
                *[
                    {"account": acct, "debit_in_account_currency": flt(amt, 2),
                     "cost_center": doc.get("cost_center")}
                    for acct, amt in per_income.items()
                ],
                {"account": cfg["account"],
                 "credit_in_account_currency": flt(total, 2),
                 "cost_center": doc.get("cost_center")},
            ],
        })
        je.insert(ignore_permissions=True)
        je.submit()
    except Exception:
        # The sale is money; the split is bookkeeping — never block the
        # invoice. Failures land in the Error Log for the accountant.
        frappe.log_error(
            title="AlphaX POS: tobacco fee repost failed",
            message=frappe.get_traceback(),
        )


def cancel_tobacco_fee(doc, method=None):
    """Sales Invoice on_cancel: cancel the companion JE."""
    try:
        for name in frappe.get_all(
            "Journal Entry",
            filters={"cheque_no": f"TOBACCO::{doc.name}", "docstatus": 1},
            pluck="name",
        ):
            frappe.get_doc("Journal Entry", name).cancel()
    except Exception:
        frappe.log_error(
            title="AlphaX POS: tobacco fee cancel failed",
            message=frappe.get_traceback(),
        )
