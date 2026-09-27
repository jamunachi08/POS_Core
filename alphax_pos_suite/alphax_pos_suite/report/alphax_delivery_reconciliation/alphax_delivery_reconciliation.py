"""
AlphaX Delivery Reconciliation.

Purpose: match what the delivery platforms OWE you against what the
books say. For every submitted delivery Sales Invoice in the period it
computes the platform commission and the net payout you should expect
in the bank, and shows how much of the invoice is still outstanding —
so a platform's settlement statement (HungerStation, Keeta, Jahez, …)
can be reconciled line-by-line, and gaps chased.

Workflow:
  1. Filter by period and (optionally) platform.
  2. Compare each platform's "Net Expected" subtotal against the bank
     settlement received.
  3. Post the settlement as a Payment Entry against the platform's
     Mode of Payment account; the Outstanding column then drops to
     zero for reconciled invoices.
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "platform", "label": _("Platform"), "fieldtype": "Link",
         "options": "AlphaX Delivery Platform", "width": 140},
        {"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link",
         "options": "Sales Invoice", "width": 160},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Data", "width": 150},
        {"fieldname": "grand_total", "label": _("Gross"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "commission_percent", "label": _("Comm %"), "fieldtype": "Percent", "width": 80},
        {"fieldname": "commission_amount", "label": _("Commission"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "net_expected", "label": _("Net Expected"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "mode_of_payment", "label": _("Mode of Payment"), "fieldtype": "Data", "width": 130},
    ]


def get_data(filters):
    conditions = {
        "docstatus": 1,
        "alphax_order_type": "Delivery",
    }
    if filters.get("from_date") and filters.get("to_date"):
        conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
    elif filters.get("from_date"):
        conditions["posting_date"] = [">=", filters.from_date]
    elif filters.get("to_date"):
        conditions["posting_date"] = ["<=", filters.to_date]
    if filters.get("platform"):
        conditions["alphax_delivery_platform"] = filters.platform
    if filters.get("company"):
        conditions["company"] = filters.company

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=conditions,
        fields=[
            "name", "posting_date", "customer", "grand_total",
            "outstanding_amount", "alphax_delivery_platform", "is_return",
        ],
        order_by="posting_date asc, name asc",
    )

    # Platform master lookup (commission + MOP), tolerant of deleted rows
    platforms = {
        p.name: p for p in frappe.get_all(
            "AlphaX Delivery Platform",
            fields=["name", "platform_name", "commission_percent", "mode_of_payment"],
        )
    } if frappe.db.table_exists("AlphaX Delivery Platform") else {}

    rows = []
    for inv in invoices:
        p = platforms.get(inv.alphax_delivery_platform)
        pct = flt(p.commission_percent) if p else 0.0
        gross = flt(inv.grand_total)
        commission = gross * pct / 100.0
        rows.append({
            "posting_date": inv.posting_date,
            "platform": inv.alphax_delivery_platform,
            "invoice": inv.name,
            "customer": inv.customer,
            "grand_total": gross,
            "commission_percent": pct,
            "commission_amount": commission,
            "net_expected": gross - commission,
            "outstanding": flt(inv.outstanding_amount),
            "mode_of_payment": (p.mode_of_payment if p else None) or "",
        })
    return rows
