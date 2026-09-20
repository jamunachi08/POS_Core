"""
AlphaX POS — catalogue resolution.

What a till may sell is decided here, on the server, once.

Before this module the register asked `frappe.client.get_list` for Items
directly, filtered by the domain pack's single `default_item_group`. Three
things were wrong with that, and all three get worse with time rather
than better:

  1. Every Restaurant outlet on the site necessarily shared one menu.
     The moment a second branch carries a different range, the only lever
     available was to reorganise the Item Group tree — which is also what
     every historical report groups by. Opening a branch would have
     rewritten last year's figures.

  2. A generic `get_list` from the browser is the client deciding what it
     is allowed to see. Whatever the UI filters, the endpoint still
     answers the unfiltered question to anyone who asks it directly.

  3. It capped at 200 rows with no pagination and no signal. A grocery
     outlet would have silently sold from an arbitrary fifth of its range.

The model this replaces it with, and the reason for each part:

  Item Group   — what a product IS. A taxonomy. Never touched to open a
                 branch, never given channel meaning. Reports depend on
                 its stability.
  Menu         — where a product is SOLD. Set algebra over groups, items,
                 brands. This is the only thing that decides what appears
                 on a till.
  Price List   — what it COSTS there. Already ERPNext's job; a menu may
                 name one so a delivery or airport range can be priced up
                 without a duplicate item master.
  Domain Pack  — what the SOFTWARE DOES (floor plan, KDS, modifiers).
                 Deliberately no longer decides items. A Restaurant and a
                 Cafe differ in features; two Restaurants differ in menu.
  Outlet       — a place. Carries the menus.
  Terminal     — a device in a place. May narrow the outlet's menus
                 (drive-thru, kiosk) but never widen them.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate

CACHE_TTL = 300


# ---------------------------------------------------------------------------
# Which menus apply
# ---------------------------------------------------------------------------

def _time_ok(menu: dict, at=None) -> bool:
    """Is this menu live right now?

    Breakfast, Ramadan and weekend ranges are time windows on one menu,
    not separate outlets. Modelling them as outlets is the other classic
    mistake: it fragments the sales history of a single shop.
    """
    at = at or now_datetime()

    if menu.get("valid_from") and getdate(at) < getdate(menu["valid_from"]):
        return False
    if menu.get("valid_upto") and getdate(at) > getdate(menu["valid_upto"]):
        return False

    days = (menu.get("days_of_week") or "").strip()
    if days:
        today = at.strftime("%a").lower()[:3]
        allowed = {d.strip().lower()[:3] for d in days.split(",") if d.strip()}
        if today not in allowed:
            return False

    start, end = menu.get("available_from"), menu.get("available_to")
    if start and end:
        clock = at.time()
        s, e = _as_time(start), _as_time(end)
        if s and e:
            if s <= e:
                if not (s <= clock <= e):
                    return False
            else:
                # Window crosses midnight — 22:00 to 02:00 is one shift.
                if not (clock >= s or clock <= e):
                    return False
    return True


def _as_time(v):
    try:
        if hasattr(v, "total_seconds"):        # timedelta from the DB
            secs = int(v.total_seconds())
            import datetime
            return datetime.time(secs // 3600 % 24, secs // 60 % 60, secs % 60)
        if hasattr(v, "hour"):
            return v
        import datetime
        return datetime.datetime.strptime(str(v), "%H:%M:%S").time()
    except Exception:
        return None


def menus_for(terminal: str | None = None, outlet: str | None = None,
              at=None, ignore_window: bool = False) -> list[dict]:
    """Menus in force, most specific first.

    A terminal's own menus REPLACE the outlet's rather than adding to
    them. That is the whole point of a terminal override: a drive-thru
    till exists to sell less than the dining room, and an override that
    only ever widened the range could not express it.
    """
    if not frappe.db.table_exists("AlphaX POS Menu"):
        return []

    if terminal and not outlet:
        outlet = frappe.db.get_value("AlphaX POS Terminal", terminal, "pos_outlet")

    names = []
    if terminal:
        names = _linked_menus("AlphaX POS Terminal", terminal)
    if not names and outlet:
        names = _linked_menus("AlphaX POS Outlet", outlet)
    if not names:
        return []

    rows = frappe.get_all(
        "AlphaX POS Menu",
        filters={"name": ["in", names], "enabled": 1},
        fields=["name", "menu_name", "price_list", "priority", "company",
                "available_from", "available_to", "days_of_week",
                "valid_from", "valid_upto"],
        order_by="priority desc, menu_name asc",
    )
    if ignore_window:
        return rows
    return [m for m in rows if _time_ok(m, at)]


def _linked_menus(parenttype: str, parent: str) -> list[str]:
    try:
        return frappe.get_all(
            "AlphaX POS Menu Link",
            filters={"parenttype": parenttype, "parent": parent,
                     "parentfield": "menus"},
            pluck="menu", order_by="idx asc",
        ) or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Which items those menus contain
# ---------------------------------------------------------------------------

def _group_descendants(group: str) -> list[str]:
    bounds = frappe.db.get_value("Item Group", group, ["lft", "rgt"], as_dict=True)
    if not bounds:
        return [group]
    return frappe.get_all(
        "Item Group",
        filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
        pluck="name",
    ) or [group]


def resolve_menu_items(menu_names: list[str]) -> set:
    """Item codes the given menus resolve to.

    Includes union, excludes subtract, excludes always win. Evaluated over
    sellable items only, so a menu can name a broad group without dragging
    in raw materials or disabled lines.
    """
    if not menu_names:
        return set()

    base = {"disabled": 0, "has_variants": 0, "is_sales_item": 1}
    included, excluded = set(), set()

    rules = frappe.get_all(
        "AlphaX POS Menu Rule",
        filters={"parent": ["in", menu_names], "parenttype": "AlphaX POS Menu"},
        fields=["rule_type", "match_on", "item_group", "include_descendants",
                "item", "brand", "attribute", "attribute_value"],
    )

    for r in rules:
        hits = set()
        if r.match_on == "Item Group" and r.item_group:
            groups = (_group_descendants(r.item_group)
                      if cint(r.include_descendants) else [r.item_group])
            hits = set(frappe.get_all(
                "Item", filters=dict(base, item_group=["in", groups]), pluck="name") or [])
        elif r.match_on == "Item" and r.item:
            if frappe.db.exists("Item", r.item):
                hits = {r.item}
        elif r.match_on == "Brand" and r.brand:
            hits = set(frappe.get_all(
                "Item", filters=dict(base, brand=r.brand), pluck="name") or [])
        elif r.match_on == "Item Attribute" and r.attribute:
            f = {"attribute": r.attribute}
            if r.attribute_value:
                f["attribute_value"] = r.attribute_value
            owners = frappe.get_all("Item Variant Attribute", filters=f, pluck="parent") or []
            if owners:
                hits = set(frappe.get_all(
                    "Item", filters=dict(base, name=["in", owners]), pluck="name") or [])

        (excluded if r.rule_type == "Exclude" else included).update(hits)

    return included - excluded


# ---------------------------------------------------------------------------
# What the register asks for
# ---------------------------------------------------------------------------

@frappe.whitelist()
def list_menu_items(terminal: str | None = None, outlet: str | None = None,
                    search: str | None = None, limit: int = 500, start: int = 0):
    """The sellable range for a till, priced.

    Server-side and authoritative: the browser cannot widen it. Falls back
    to the legacy domain-group behaviour when no menu is assigned, so an
    unmigrated site keeps selling exactly what it sold yesterday.
    """
    if terminal and not outlet:
        outlet = frappe.db.get_value("AlphaX POS Terminal", terminal, "pos_outlet")
    if not outlet:
        frappe.throw(_("No outlet resolved for this terminal."))

    o = frappe.db.get_value(
        "AlphaX POS Outlet", outlet,
        ["default_price_list", "primary_domain", "company"], as_dict=True) or {}

    menus = menus_for(terminal=terminal, outlet=outlet)
    codes = resolve_menu_items([m["name"] for m in menus]) if menus else None

    source = "menu"
    if codes is None:
        codes, source = _legacy_scope(o), "domain_group"
    if not codes:
        # A menu that resolves to nothing is a configuration error, not an
        # empty shop. Say which, rather than showing a blank grid.
        return {"items": [], "total": 0, "source": source, "menus": [m["menu_name"] for m in menus],
                "warning": _("No items resolved. Check the menus assigned to this outlet.")
                if menus else _("No menu is assigned to this outlet.")}

    filters = {"name": ["in", list(codes)], "disabled": 0,
               "has_variants": 0, "is_sales_item": 1}
    or_filters = None
    if search:
        s = f"%{search}%"
        or_filters = {"item_code": ["like", s], "item_name": ["like", s],
                      "description": ["like", s]}

    total = frappe.db.count("Item", filters)
    rows = frappe.get_all(
        "Item", filters=filters, or_filters=or_filters,
        fields=["name", "item_code", "item_name", "item_group", "standard_rate",
                "image", "description", "stock_uom", "brand"],
        order_by="item_name asc",
        limit_start=cint(start), limit_page_length=min(cint(limit) or 500, 2000),
    )

    _apply_prices(rows, menus, o.get("default_price_list"))
    _apply_optional_fields(rows)

    return {
        "items": rows,
        "total": total,
        "start": cint(start),
        "source": source,
        "menus": [m["menu_name"] for m in menus],
        "price_list": o.get("default_price_list"),
    }


def _legacy_scope(outlet_row: dict) -> set:
    """Pre-menu behaviour: everything under the domain's default group.

    Kept deliberately. An upgrade that empties a till's menu is worse than
    an upgrade that changes nothing.
    """
    base = {"disabled": 0, "has_variants": 0, "is_sales_item": 1}
    group = None
    if outlet_row.get("primary_domain"):
        group = frappe.db.get_value(
            "AlphaX POS Domain Pack", outlet_row["primary_domain"], "default_item_group")
    if group:
        base["item_group"] = ["in", _group_descendants(group)]
    return set(frappe.get_all("Item", filters=base, pluck="name") or [])


def _apply_prices(rows: list, menus: list, outlet_price_list: str | None):
    """Resolve each row's rate.

    Menu price list beats outlet price list beats standard rate. Highest
    menu priority wins where two menus both carry the item — which is how
    a promotional range overrides a core one without editing either.
    """
    if not rows:
        return
    codes = [r["item_code"] for r in rows]
    priced = {}

    # Lowest priority first so higher priority overwrites.
    for m in sorted(menus, key=lambda x: cint(x.get("priority"))):
        pl = m.get("price_list")
        if not pl:
            continue
        for p in frappe.get_all(
            "Item Price",
            filters={"price_list": pl, "selling": 1, "item_code": ["in", codes]},
            fields=["item_code", "price_list_rate"],
        ):
            priced[p.item_code] = (p.price_list_rate, pl)

    if outlet_price_list:
        for p in frappe.get_all(
            "Item Price",
            filters={"price_list": outlet_price_list, "selling": 1,
                     "item_code": ["in", codes]},
            fields=["item_code", "price_list_rate"],
        ):
            priced.setdefault(p.item_code, (p.price_list_rate, outlet_price_list))

    for r in rows:
        rate, source = priced.get(r["item_code"], (None, None))
        r["rate"] = rate if rate is not None else (r.get("standard_rate") or 0)
        r["price_source"] = source or ("standard_rate" if r.get("standard_rate") else "unpriced")


def _apply_optional_fields(rows: list):
    """Scale fields exist only where the scale app/fields were installed."""
    if not rows:
        return
    meta = frappe.get_meta("Item")
    wanted = [f for f in ("alphax_is_weighing_item", "alphax_scale_item_code")
              if meta.has_field(f)]
    if not wanted:
        return
    extra = {r.name: r for r in frappe.get_all(
        "Item", filters={"name": ["in", [r["item_code"] for r in rows]]},
        fields=["name"] + wanted)}
    for r in rows:
        src = extra.get(r["item_code"])
        for f in wanted:
            r[f] = src.get(f) if src else None


@frappe.whitelist()
def preview_menu(menu: str):
    """Manager-facing: what does this menu actually contain?

    A menu is set algebra, and set algebra is easy to get subtly wrong.
    Showing the result at design time is cheaper than discovering it at
    the till on a Friday night.
    """
    if not frappe.has_permission("AlphaX POS Menu", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    codes = resolve_menu_items([menu])
    rows = frappe.get_all(
        "Item", filters={"name": ["in", list(codes)]} if codes else {"name": ["in", []]},
        fields=["item_code", "item_name", "item_group"],
        order_by="item_group asc, item_name asc", limit_page_length=500)

    by_group = {}
    for r in rows:
        by_group.setdefault(r.item_group, 0)
        by_group[r.item_group] += 1

    return {
        "count": len(codes),
        "shown": len(rows),
        "by_group": sorted(({"item_group": k, "count": v} for k, v in by_group.items()),
                           key=lambda x: -x["count"]),
        "sample": rows[:50],
    }


@frappe.whitelist()
def catalog_diagnose(terminal: str):
    """Why is this till showing the wrong items?

    Walks the same chain the register does and reports where the answer
    came from, so the question is settled by reading rather than guessing.
    """
    if not frappe.has_permission("AlphaX POS Terminal", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    out = {"terminal": terminal, "checks": []}

    def note(label, ok, detail=""):
        out["checks"].append({"check": label, "ok": bool(ok), "detail": detail})
        return ok

    if not note("terminal exists", frappe.db.exists("AlphaX POS Terminal", terminal)):
        return out

    t = frappe.db.get_value("AlphaX POS Terminal", terminal,
                            ["pos_outlet", "branch", "pos_profile"], as_dict=True) or {}
    out["outlet"], out["branch"] = t.get("pos_outlet"), t.get("branch")
    if not note("outlet linked", bool(t.get("pos_outlet")),
                "Set Outlet on the terminal."):
        return out

    own = _linked_menus("AlphaX POS Terminal", terminal)
    note("terminal-level menu override", bool(own),
         f"{own} — these REPLACE the outlet's menus." if own
         else "None, so the outlet's menus apply (normal).")

    outlet_menus = _linked_menus("AlphaX POS Outlet", t["pos_outlet"])
    note("outlet has menus", bool(outlet_menus),
         f"{outlet_menus}" if outlet_menus
         else "None — the till falls back to the domain's default item group.")

    live = menus_for(terminal=terminal, outlet=t["pos_outlet"])
    allm = menus_for(terminal=terminal, outlet=t["pos_outlet"], ignore_window=True)
    dormant = [m["menu_name"] for m in allm if m["name"] not in {x["name"] for x in live}]
    note("menus live right now", bool(live),
         f"live: {[m['menu_name'] for m in live]}"
         + (f" · outside their window: {dormant}" if dormant else ""))

    codes = resolve_menu_items([m["name"] for m in live]) if live else None
    if codes is None:
        legacy = _legacy_scope(frappe.db.get_value(
            "AlphaX POS Outlet", t["pos_outlet"],
            ["default_price_list", "primary_domain", "company"], as_dict=True) or {})
        note("items resolved (legacy domain group)", bool(legacy),
             f"{len(legacy)} items")
        out["item_count"], out["source"] = len(legacy), "domain_group"
    else:
        note("items resolved from menus", bool(codes), f"{len(codes)} items")
        out["item_count"], out["source"] = len(codes), "menu"

    pl = frappe.db.get_value("AlphaX POS Outlet", t["pos_outlet"], "default_price_list")
    note("outlet has a price list", bool(pl),
         "Without one every item falls back to its standard rate.")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out
