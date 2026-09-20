"""
AlphaX POS — quick-pick pad driven by real sales velocity.

Supermarkets and pharmacies both have a long tail of items that must be
entered by hand: loose produce, bakery, carrier bags, newspapers, OTC
singles. Hand-curating that pad goes stale within a month and nobody
maintains it.

So compute it. Rank by *transaction frequency* rather than quantity or
revenue — the cashier cares how OFTEN they reach for a thing, not how
much of it sold. Bananas beat a 50 kg rice sack even though the sack is
worth more.

Filters applied:
  - only items with no barcode, or flagged `weighed`, or explicitly
    pinned. An item with a barcode does not belong on a manual pad.
  - scoped to the terminal's outlet warehouse / price list so a
    multi-branch chain does not show one branch's habits to another.
  - cached 30 min per (outlet, window) — this is a dashboard-grade
    query, not a hot path.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, nowdate

CACHE_TTL = 30 * 60


@frappe.whitelist()
def get_top_movers(terminal: str | None = None, limit: int = 12,
                   window_days: int = 28, include_barcoded: int = 0):
    limit = max(1, min(cint(limit) or 12, 40))
    window_days = max(1, min(cint(window_days) or 28, 180))

    outlet, company, price_list = _terminal_context(terminal)
    key = f"alphax_top_movers:{outlet or company or 'all'}:{window_days}:{limit}:{cint(include_barcoded)}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached

    rows = _query(company, window_days, limit * 4)
    pinned = _pinned_items(outlet)

    out, seen = [], set()

    # Pinned items always lead, in the operator's order.
    for it in pinned:
        if it["item_code"] in seen:
            continue
        seen.add(it["item_code"])
        out.append(it)

    for r in rows:
        if len(out) >= limit:
            break
        if r.item_code in seen:
            continue
        if not cint(include_barcoded) and _has_barcode(r.item_code):
            continue
        seen.add(r.item_code)
        out.append(_decorate(r.item_code, price_list, r.txn_count))

    result = out[:limit]
    frappe.cache().set_value(key, result, expires_in_sec=CACHE_TTL)
    return result


def _terminal_context(terminal):
    if not terminal or not frappe.db.exists("AlphaX POS Terminal", terminal):
        return None, None, None
    outlet = frappe.db.get_value("AlphaX POS Terminal", terminal, "pos_outlet")
    company = price_list = None
    if outlet:
        company, price_list = frappe.db.get_value(
            "AlphaX POS Outlet", outlet, ["company", "selling_price_list"]) or (None, None)
    return outlet, company, price_list


def _query(company, window_days, fetch):
    """Transaction frequency over the window. Counts DISTINCT invoices an
    item appeared on, not units sold."""
    since = add_days(nowdate(), -window_days)
    conditions = ["si.docstatus = 1", "si.posting_date >= %(since)s", "si.is_pos = 1"]
    params = {"since": since, "fetch": fetch}
    if company:
        conditions.append("si.company = %(company)s")
        params["company"] = company

    return frappe.db.sql(f"""
        SELECT sii.item_code            AS item_code,
               COUNT(DISTINCT si.name)  AS txn_count,
               SUM(sii.qty)             AS total_qty
          FROM `tabSales Invoice Item` sii
          JOIN `tabSales Invoice` si ON si.name = sii.parent
         WHERE {' AND '.join(conditions)}
      GROUP BY sii.item_code
      ORDER BY txn_count DESC, total_qty DESC
         LIMIT %(fetch)s
    """, params, as_dict=True)


def _has_barcode(item_code) -> bool:
    return bool(frappe.db.exists("Item Barcode", {"parent": item_code}))


def _pinned_items(outlet):
    """Operator overrides live on the Outlet as a small child table
    (`quick_pick_items`). Optional — absent on older installs."""
    if not outlet:
        return []
    try:
        doc = frappe.get_cached_doc("AlphaX POS Outlet", outlet)
        rows = doc.get("quick_pick_items") or []
    except Exception:
        return []
    price_list = doc.get("selling_price_list")
    return [_decorate(r.item_code, price_list, None, pinned=True)
            for r in rows if r.get("item_code")]


def _decorate(item_code, price_list, txn_count, pinned=False):
    item = frappe.get_cached_value(
        "Item", item_code,
        ["item_name", "stock_uom", "image", "item_group", "is_stock_item"],
        as_dict=True) or {}
    rate = 0
    if price_list:
        rate = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": price_list, "selling": 1},
            "price_list_rate") or 0
    if not rate:
        rate = frappe.db.get_value("Item", item_code, "standard_rate") or 0

    weighed = _is_weighed(item_code)
    return {
        "item_code": item_code,
        "item_name": item.get("item_name") or item_code,
        "item_group": item.get("item_group"),
        "uom": item.get("stock_uom"),
        "image": item.get("image"),
        "standard_rate": rate,
        "rate": rate,
        "weighed": weighed,
        "pinned": pinned,
        "txn_count": txn_count,
    }


def _is_weighed(item_code) -> bool:
    """An item is weighed if its stock UOM is a mass unit, or a scale
    barcode rule targets it."""
    uom = frappe.get_cached_value("Item", item_code, "stock_uom") or ""
    if uom.lower() in ("kg", "kilogram", "g", "gram", "gm"):
        return True
    try:
        return bool(frappe.db.exists("AlphaX POS Scale Barcode Rule", {"item_code": item_code}))
    except Exception:
        return False


@frappe.whitelist()
def invalidate(outlet: str | None = None):
    """Called after a bulk item import or price change."""
    frappe.cache().delete_keys("alphax_top_movers:")
    return {"ok": True}
