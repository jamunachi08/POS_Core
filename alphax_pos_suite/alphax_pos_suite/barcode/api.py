"""
Barcode scan endpoint for the cashier.

One whitelisted call, `scan_barcode`, resolves any of the three things a
retail/grocery cashier scans:

  1. A standard product barcode (EAN-13 / UPC-A / EAN-8 / Code-128) that is
     stored against the Item in ERPNext's native 'Item Barcode' table.
  2. A variable-measure / scale barcode that embeds a PLU + weight or price
     (deli, butcher, produce). Parsed via the configurable
     'AlphaX POS Scale Barcode Definition' records.
  3. A bare item code / PLU typed or scanned directly.

It returns a normalised, cashier-ready payload so the front end never has
to know which of the three it scanned.
"""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from alphax_pos_suite.alphax_pos_suite.barcode import parser


_ITEM_FIELDS = [
    "name", "item_code", "item_name", "item_group", "stock_uom",
    "standard_rate", "image", "is_stock_item", "disabled",
]


def _active_definitions() -> list[dict]:
    """Return enabled scale-barcode definitions as plain dicts."""
    try:
        rows = frappe.get_all(
            "AlphaX POS Scale Barcode Definition",
            filters={"enabled": 1},
            fields=[
                "name", "definition_name", "enabled", "prefix", "total_length",
                "mapping_type", "item_start", "item_length",
                "qty_start", "qty_length", "qty_divider", "use_qty_from_barcode",
                "rate_start", "rate_length", "rate_divider", "use_rate_from_barcode",
            ],
            order_by="total_length desc",
        )
        return rows
    except Exception:
        return []


def _find_item_by_barcode(code: str) -> str | None:
    """Native ERPNext product-barcode lookup."""
    if not frappe.db.has_column("Item Barcode", "barcode"):
        return None
    return frappe.db.get_value("Item Barcode", {"barcode": code}, "parent")


def _find_item_by_plu(plu: str) -> str | None:
    """Resolve an embedded PLU/item code to a real Item.

    Tries, in order: exact item_code, the optional `alphax_scale_item_code`
    custom field, a product barcode equal to the PLU, then zero-padded
    item_code variants (scales often left-pad codes).
    """
    if not plu:
        return None

    if frappe.db.exists("Item", plu):
        return plu

    # Custom scale-item-code field (added by this app for weighing items)
    if frappe.db.has_column("Item", "alphax_scale_item_code"):
        hit = frappe.db.get_value("Item", {"alphax_scale_item_code": plu}, "name")
        if hit:
            return hit

    # A product barcode that equals the PLU
    hit = _find_item_by_barcode(plu)
    if hit:
        return hit

    # Zero-padded / unpadded variants
    for variant in {plu.lstrip("0"), plu.zfill(6), plu.zfill(5)}:
        if variant and variant != plu and frappe.db.exists("Item", variant):
            return variant

    return None


def _resolve_price_list(pos_profile: str | None, outlet: str | None) -> str | None:
    if pos_profile and frappe.db.exists("POS Profile", pos_profile):
        pl = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
        if pl:
            return pl
    if outlet and frappe.db.exists("AlphaX POS Outlet", outlet):
        pl = frappe.db.get_value("AlphaX POS Outlet", outlet, "default_price_list")
        if pl:
            return pl
    return frappe.db.get_single_value("Selling Settings", "selling_price_list")


def _item_price(item_code: str, price_list: str | None, standard_rate: float) -> float:
    """Best-effort selling rate: price list first, then the item's standard rate."""
    if price_list:
        rate = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": price_list, "selling": 1},
            "price_list_rate",
        )
        if rate:
            return flt(rate)
    return flt(standard_rate)


def _item_payload(item_name: str, price_list: str | None) -> dict | None:
    if not frappe.db.exists("Item", item_name):
        return None
    item = frappe.db.get_value("Item", item_name, _ITEM_FIELDS, as_dict=True)
    if not item or item.get("disabled"):
        return None
    rate = _item_price(item["item_code"], price_list, item.get("standard_rate") or 0)
    return {
        "item_code": item["item_code"],
        "item_name": item.get("item_name") or item["item_code"],
        "item_group": item.get("item_group"),
        "uom": item.get("stock_uom"),
        "image": item.get("image"),
        "rate": flt(rate),
        "is_stock_item": int(item.get("is_stock_item") or 0),
    }


@frappe.whitelist()
def scan_barcode(code: str, pos_profile: str | None = None, outlet: str | None = None) -> dict:
    """Resolve a scanned/typed code to a cashier-ready cart line.

    Returns
    -------
    dict
        Found:
          {found: True, source: 'product'|'scale'|'plu', item_code, item_name,
           item_group, uom, image, qty, rate, rate_overridden: bool,
           definition: str|None}
        Not found:
          {found: False, code: <normalised>, message: <human text>}
    """
    code = (code or "").strip()
    if not code:
        return {"found": False, "code": code, "message": _("Empty barcode.")}

    price_list = _resolve_price_list(pos_profile, outlet)

    # 1) Native product barcode (most common path)
    item_name = _find_item_by_barcode(code)
    if item_name:
        payload = _item_payload(item_name, price_list)
        if payload:
            payload.update({
                "found": True, "source": "product", "qty": 1,
                "rate_overridden": False, "definition": None,
            })
            return payload

    # 2) Variable-measure / scale barcode (PLU + weight or price)
    if code.isdigit():
        parsed = parser.parse_first(code, _active_definitions())
        if parsed:
            item_name = _find_item_by_plu(parsed.item_code)
            if item_name:
                payload = _item_payload(item_name, price_list)
                if payload:
                    qty = parsed.qty if parsed.qty is not None else 1
                    rate_overridden = parsed.rate is not None
                    payload.update({
                        "found": True,
                        "source": "scale",
                        "qty": flt(qty) or 1,
                        "rate": flt(parsed.rate) if rate_overridden else payload["rate"],
                        "rate_overridden": rate_overridden,
                        "definition": parsed.definition_name,
                    })
                    return payload

    # 3) Bare item code / PLU
    item_name = _find_item_by_plu(code)
    if item_name:
        payload = _item_payload(item_name, price_list)
        if payload:
            payload.update({
                "found": True, "source": "plu", "qty": 1,
                "rate_overridden": False, "definition": None,
            })
            return payload

    return {
        "found": False,
        "code": code,
        "message": _("No item found for barcode {0}.").format(code),
    }
