# Shared helpers for shift-close and day-close reports.
#
# AlphaX POS Order intentionally has NO grand_total column — the order
# header carries adjustments (discount/tips/service charge) while the
# authoritative total lives on the linked, submitted Sales Invoice, or
# failing that, in the sum of the order's payment rows. Both close
# reports previously selected `grand_total` straight off the order and
# would have crashed with SQL 1054 on first shift close (caught by the
# v15.6.6 schema audit; the reports had never run on a real site).

import frappe
from frappe.utils import flt


def order_grand_total(order_doc) -> float:
    """Best-available total for an AlphaX POS Order document."""
    si = getattr(order_doc, "sales_invoice", None)
    if si:
        gt = frappe.db.get_value("Sales Invoice", si, "grand_total")
        if gt is not None:
            return flt(gt)
    return flt(sum(flt(p.amount or 0) for p in (order_doc.payments or [])))
