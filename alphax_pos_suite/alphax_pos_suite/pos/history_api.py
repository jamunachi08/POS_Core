"""Read-only sales history for the cashier register.

Cashiers need to verify and reprint recent documents ("did table 4 pay
by card?", "customer wants a copy") without desk access and without any
ability to modify. This module exposes exactly two read-only endpoints,
scoped to one terminal's invoices; there is deliberately NO mutation
here — reprint-for-verification, not back-office editing.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

_TABS = {
    "history": {"docstatus": 1, "is_return": 0},
    "unpaid": {"docstatus": 1, "is_return": 0, "outstanding_amount": [">", 0.005]},
    "drafts": {"docstatus": 0},
    "returns": {"docstatus": 1, "is_return": 1},
}


def _require_read():
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw(
            _(
                "Your user has no read access to Sales Invoice. "
                "Ask an administrator to grant read permission, then reload."
            ),
            frappe.PermissionError,
        )


@frappe.whitelist()
def list_invoices(
    terminal: str,
    tab: str = "history",
    search: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 60,
):
    """This terminal's invoices for one tab, plus KPI totals.

    Scope is the TERMINAL, not the user: shift handovers mean the next
    cashier must be able to verify the previous cashier's sales on the
    same till. Permission model stays read-only by construction.
    """
    _require_read()
    if not frappe.db.exists("AlphaX POS Terminal", terminal):
        frappe.throw(_("Unknown terminal"))
    if tab not in _TABS:
        frappe.throw(_("Unknown tab: {0}").format(tab))

    filters = {"alphax_pos_terminal": terminal, **_TABS[tab]}
    if from_date:
        filters["posting_date"] = [">=", from_date]
    if to_date:
        filters.setdefault("posting_date", None)
        filters["posting_date"] = (
            ["between", [from_date, to_date]] if from_date else ["<=", to_date]
        )

    or_filters = None
    if search:
        like = f"%{search}%"
        or_filters = [
            ["Sales Invoice", "name", "like", like],
            ["Sales Invoice", "customer", "like", like],
            ["Sales Invoice", "customer_name", "like", like],
        ]

    rows = frappe.get_list(
        "Sales Invoice",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name", "docstatus", "status", "is_return",
            "posting_date", "posting_time",
            "customer", "customer_name",
            "grand_total", "paid_amount", "outstanding_amount",
            "change_amount", "currency",
        ],
        order_by="posting_date desc, posting_time desc",
        limit_page_length=min(int(limit or 60), 200),
    )

    # Tab badge counts + KPI strip for the same terminal/date range.
    counts = {}
    for key, tab_filters in _TABS.items():
        f = {"alphax_pos_terminal": terminal, **tab_filters}
        if filters.get("posting_date"):
            f["posting_date"] = filters["posting_date"]
        counts[key] = frappe.db.count("Sales Invoice", f)

    kpi_filters = {"alphax_pos_terminal": terminal, "docstatus": 1}
    if filters.get("posting_date"):
        kpi_filters["posting_date"] = filters["posting_date"]
    agg = frappe.get_all(
        "Sales Invoice",
        filters=kpi_filters,
        fields=[
            "sum(grand_total) as gross",
            "sum(paid_amount) as tendered",
            "sum(change_amount) as change_returned",
            "sum(outstanding_amount) as outstanding",
        ],
    )
    a = agg[0] if agg else {}

    return {
        "rows": rows,
        "counts": counts,
        "kpi": {
            "invoices": counts.get("history", 0) + counts.get("returns", 0),
            "gross": flt(a.get("gross")),
            "tendered": flt(a.get("tendered")),
            "change_returned": flt(a.get("change_returned")),
            "outstanding": flt(a.get("outstanding")),
        },
    }


@frappe.whitelist()
def get_invoice_receipt(name: str):
    """One invoice in the SPA's receipt shape, for reprint.

    Built server-side so the reprint matches the original layout even
    for invoices created before the register was last reloaded (items,
    tax breakdown, and payments come from the document, not from any
    client state). Marked as a REPRINT in the footer — a duplicate
    receipt must be distinguishable from the original for audit.
    """
    _require_read()
    si = frappe.get_doc("Sales Invoice", name)  # raises if not found
    si.check_permission("read")

    terminal = getattr(si, "alphax_pos_terminal", None)
    outlet = {}
    if getattr(si, "alphax_outlet", None):
        o = frappe.db.get_value(
            "AlphaX POS Outlet",
            si.alphax_outlet,
            ["outlet_name", "branch", "address", "vat_no", "phone"],
            as_dict=True,
        ) or {}
        outlet = o

    return {
        "header": {
            "store_name": outlet.get("outlet_name") or si.company,
            "branch": outlet.get("branch") or "",
            "address": outlet.get("address") or "",
            "vat_no": outlet.get("vat_no") or si.get("company_tax_id") or "",
            "phone": outlet.get("phone") or "",
        },
        # ZATCA simplified-invoice QR (TLV base64), attached to the
        # Sales Invoice by the alphax_zatca app after submit. Field name
        # differs by stack: ERPNext KSA regional uses ksa_einv_qr; the
        # zatca app may use its own. First non-empty wins; None when the
        # invoice predates ZATCA enablement or the app isn't installed.
        # The bridge renders it as a QR block; receipts without it are
        # not valid simplified tax invoices for B2C in KSA.
        "zatca_qr": next(
            (
                si.get(f)
                for f in ("ksa_einv_qr", "zatca_qr_code", "qr_code", "alphax_zatca_qr")
                if si.get(f)
            ),
            None,
        ),
        "meta": {
            "invoice_no": si.name,
            "datetime": f"{si.posting_date} {si.posting_time or ''}".strip(),
            "cashier": si.owner,
            "terminal": terminal or "",
            "table": "",
            "customer": si.customer_name or si.customer,
        },
        "items": [
            {
                "name": it.item_name or it.item_code,
                "qty": it.qty,
                "rate": it.rate,
                "amount": flt(it.amount),
                "modifiers": [],
            }
            for it in si.items
        ],
        "totals": {
            "subtotal": flt(si.net_total),
            "tax": flt(si.total_taxes_and_charges),
            "total": flt(si.grand_total),
            "tendered": flt(si.paid_amount),
            "change": flt(si.change_amount),
            "tax_breakdown": [
                {"label": tx.description or tx.charge_type, "amount": flt(tx.tax_amount)}
                for tx in (si.taxes or [])
            ],
        },
        "payments": [
            {"mode": p.mode_of_payment, "amount": flt(p.amount)}
            for p in (si.payments or [])
            if flt(p.amount)
        ],
        "footer": {
            "line1": _("REPRINT — duplicate copy"),
            "line2": si.name,
        },
        "is_return": bool(si.is_return),
        "docstatus": si.docstatus,
    }
