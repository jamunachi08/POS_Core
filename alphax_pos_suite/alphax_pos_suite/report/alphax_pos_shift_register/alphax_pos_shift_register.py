"""Shift Register: the audit trail of who held the desk, when, and
with what cash.

One row per shift in the trading-day range: cashier, open/close
timestamps, opening float, counted cash, over/short, whether the close
was a HANDOVER (and to whom / continuing which shift — the unbroken
chain of custody), the day close it rolled into, and whether the
system auto-closed it at store closing time (RECOUNT REQUIRED note).
This is the "what happened at that date, at that time, who was at the
desk" answer for disputes and evidence requests.
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    conditions = {"docstatus": ["<", 2]}
    if filters.get("from_date"):
        conditions["business_date"] = [">=", filters["from_date"]]
    if filters.get("to_date"):
        bd = conditions.get("business_date")
        conditions["business_date"] = (
            ["between", [filters["from_date"], filters["to_date"]]]
            if bd else ["<=", filters["to_date"]]
        )
    if filters.get("terminal"):
        conditions["pos_terminal"] = filters["terminal"]
    if filters.get("user"):
        conditions["user"] = filters["user"]

    rows = frappe.get_all(
        "AlphaX POS Shift",
        filters=conditions,
        fields=[
            "name", "business_date", "pos_terminal", "user", "status",
            "opened_on", "closed_on", "opening_cash", "closing_cash",
            "expected_cash", "variance",
            "is_handover", "handover_to", "handover_from_shift",
            "day_close_id", "notes",
        ],
        order_by="business_date desc, pos_terminal, opened_on asc",
    )
    for r in rows:
        r["auto_closed"] = 1 if "AUTO-CLOSED" in (r.get("notes") or "") else 0
        r["kind"] = (
            _("Handover →") if r.is_handover
            else _("Relief (continued)") if r.handover_from_shift
            else _("Regular")
        )

    columns = [
        {"label": _("Trading Day"), "fieldname": "business_date", "fieldtype": "Date", "width": 105},
        {"label": _("Terminal"), "fieldname": "pos_terminal", "fieldtype": "Link", "options": "AlphaX POS Terminal", "width": 120},
        {"label": _("Shift"), "fieldname": "name", "fieldtype": "Link", "options": "AlphaX POS Shift", "width": 130},
        {"label": _("Cashier"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 170},
        {"label": _("Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 120},
        {"label": _("Opened"), "fieldname": "opened_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Closed"), "fieldname": "closed_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Opening Float"), "fieldname": "opening_cash", "fieldtype": "Currency", "width": 110},
        {"label": _("Counted"), "fieldname": "closing_cash", "fieldtype": "Currency", "width": 110},
        {"label": _("Over/Short"), "fieldname": "variance", "fieldtype": "Currency", "width": 100},
        {"label": _("Handed To"), "fieldname": "handover_to", "fieldtype": "Link", "options": "User", "width": 150},
        {"label": _("Continues"), "fieldname": "handover_from_shift", "fieldtype": "Link", "options": "AlphaX POS Shift", "width": 130},
        {"label": _("Auto-Closed"), "fieldname": "auto_closed", "fieldtype": "Check", "width": 90},
        {"label": _("Day Close"), "fieldname": "day_close_id", "fieldtype": "Link", "options": "AlphaX POS Day Close", "width": 130},
    ]
    return columns, rows
