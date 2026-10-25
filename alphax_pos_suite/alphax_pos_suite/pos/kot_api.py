"""KOT routing: one order fans out into one ticket per kitchen station.

The shop model (Foodics/Aloha convention, done ERPNext-native):

  AlphaX POS Print Station   — Juice Bar, Sandwich, Shawarma… Printer
                               stations print through the local bridge;
                               Kitchen Display stations appear on the
                               KDS board.
  AlphaX POS KOT Routing Rule — Item Group → Station. Nearest-ancestor
                               wins (a rule on "Hot Beverages" beats a
                               rule on "Beverages" for a cappuccino);
                               outlet-specific rules beat global ones;
                               anything unmatched falls back to the
                               outlet's default station so nothing ever
                               silently drops.

Two consumers, deliberately different transports:

  PAPER  — routed and printed CLIENT-SIDE at sale time from rules the
           register got at boot. The kitchen must get its ticket even
           with no internet; a cloud round-trip can never gate the
           shawarma station.
  SCREEN — KDS tickets are created SERVER-SIDE on invoice submit (this
           module) and pushed over frappe.realtime. For offline-queued
           sales they appear when the sale syncs; paper already went
           out at sale time.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _item_group_ancestors(item_group: str) -> list[str]:
    """[group, parent, grandparent, …] via nested-set lft/rgt."""
    if not item_group:
        return []
    bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
    if not bounds:
        return [item_group]
    rows = frappe.get_all(
        "Item Group",
        filters={"lft": ["<=", bounds.lft], "rgt": [">=", bounds.rgt]},
        fields=["name", "lft"],
        order_by="lft desc",  # deepest (self) first → nearest-ancestor wins
    )
    return [r.name for r in rows]


def _routing_table(outlet: str | None):
    """{item_group: station} with outlet rules overriding global ones."""
    rules = frappe.get_all(
        "AlphaX POS KOT Routing Rule",
        filters={"enabled": 1},
        fields=["item_group", "station", "outlet"],
    )
    table: dict[str, str] = {}
    for r in rules:  # global first
        if not r.outlet:
            table[r.item_group] = r.station
    for r in rules:  # outlet-specific override
        if outlet and r.outlet == outlet:
            table[r.item_group] = r.station
    return table


def _item_overrides() -> dict[str, str]:
    """Exact item → station map from AlphaX POS Item Station (v1)."""
    try:
        return {
            r.item_code: r.station
            for r in frappe.get_all(
                "AlphaX POS Item Station", fields=["item_code", "station"]
            )
            if r.station
        }
    except Exception:
        return {}


def _default_station(outlet: str | None) -> str | None:
    for filters in (
        {"enabled": 1, "is_default": 1, "outlet": outlet},
        {"enabled": 1, "is_default": 1, "outlet": ["in", ["", None]]},
    ):
        if outlet is None and "outlet" in filters and filters["outlet"] == outlet:
            continue
        name = frappe.db.get_value("AlphaX POS Print Station", filters, "name")
        if name:
            return name
    return None


def _item_overrides() -> dict[str, str]:
    """AlphaX POS Item Station rows: exact item beats every group rule
    (v1 compatibility surface, kept as the per-item override)."""
    if not frappe.db.table_exists("AlphaX POS Item Station"):
        return {}
    return {
        r.item_code: r.station
        for r in frappe.get_all("AlphaX POS Item Station", fields=["item_code", "station"])
        if r.station
    }


def resolve_station(item_group: str, outlet: str | None, table=None,
                    item_code: str | None = None, overrides=None) -> str | None:
    if item_code:
        overrides = overrides if overrides is not None else _item_overrides()
        if item_code in overrides:
            return overrides[item_code]
    table = table if table is not None else _routing_table(outlet)
    for group in _item_group_ancestors(item_group):
        if group in table:
            return table[group]
    return _default_station(outlet)


# ---------------------------------------------------------------------------
# Server-side ticket creation (KDS + audit) — Sales Invoice on_submit hook
# ---------------------------------------------------------------------------

def create_kots_for_invoice(doc, method=None):
    """Fan the submitted register invoice out into per-station tickets.

    Register invoices only (alphax_client_uuid marks them); returns are
    skipped — a return is a till operation, not a kitchen instruction.
    Failures never block the sale: the invoice is money, the ticket is
    workflow.
    """
    try:
        if not getattr(doc, "alphax_client_uuid", None) or getattr(doc, "is_return", 0):
            return
        outlet = getattr(doc, "alphax_outlet", None)
        stations = frappe.get_all(
            "AlphaX POS Print Station", filters={"enabled": 1}, fields=["name"], limit_page_length=1
        )
        if not stations:
            return  # shop hasn't adopted KOT routing — zero overhead

        table = _routing_table(outlet)
        overrides = _item_overrides()
        groups: dict[str, list] = {}
        lines_all: list = []
        meta_cache: dict[str, str] = {}
        for it in doc.items:
            ig = meta_cache.get(it.item_code)
            if ig is None:
                ig = frappe.db.get_value("Item", it.item_code, "item_group") or ""
                meta_cache[it.item_code] = ig
            station = resolve_station(ig, outlet, table, item_code=it.item_code, overrides=overrides)
            if not station:
                continue
            groups.setdefault(station, []).append(it)
            lines_all.append(it)

        # Allergens are snapshotted onto the ticket rather than looked up by
        # the pass. An item edited at 21:00 must not rewrite a ticket that
        # has been on the rail since 20:00.
        diet = _dietary_snapshot([it.item_code for it in lines_all])
        guest_note = _guest_allergy_note(doc)

        for station, lines in groups.items():
            ticket_allergens = sorted({
                a for it in lines for a in diet.get(it.item_code, {}).get("allergens", [])})
            ticket = frappe.get_doc({
                "doctype": "AlphaX POS KDS Ticket",
                "outlet": outlet,
                "station": station,
                "sales_invoice": doc.name,
                "customer": doc.customer,
                "business_date": str(getattr(doc, "posting_date", "") or nowdate()),
                "status": "New",
                "guest_allergy_note": guest_note,
                "ticket_allergens": ", ".join(ticket_allergens),
                "items": [
                    {
                        "item_code": it.item_code,
                        "qty": it.qty,
                        "notes": "",
                        "status": "New",
                        "station": station,
                        "food_type": diet.get(it.item_code, {}).get("food_type") or "",
                        "allergens": ", ".join(
                            diet.get(it.item_code, {}).get("allergens", [])),
                    }
                    for it in lines
                ],
            })
            ticket.insert(ignore_permissions=True)
            frappe.publish_realtime(
                "alphax_kds_update",
                {"station": station, "ticket": ticket.name, "action": "new"},
            )
    except Exception:
        frappe.log_error(
            title="AlphaX POS: KOT fan-out failed",
            message=frappe.get_traceback(),
        )


def _dietary_snapshot(item_codes: list) -> dict:
    """Food type and allergen short codes per item, read once per ticket run.

    Short codes ("NUT", "MLK") rather than full names: a kitchen ticket is
    42 characters wide and the pass reads it at arm's length.
    """
    out = {c: {"food_type": "", "allergens": []} for c in item_codes}
    if not item_codes:
        return out
    try:
        meta = frappe.get_meta("Item")
    except Exception:
        return out

    if meta.has_field("alphax_food_type"):
        for row in frappe.get_all("Item", filters={"name": ["in", item_codes]},
                                  fields=["name", "alphax_food_type"]):
            out.setdefault(row.name, {"food_type": "", "allergens": []})
            out[row.name]["food_type"] = row.alphax_food_type or ""

    if not (meta.has_field("alphax_dietary_tags")
            and frappe.db.exists("DocType", "AlphaX POS Dietary Tag")):
        return out

    links = frappe.get_all(
        "AlphaX POS Item Dietary Tag",
        filters={"parenttype": "Item", "parent": ["in", item_codes]},
        fields=["parent", "dietary_tag"], ignore_permissions=True)
    if not links:
        return out
    tags = {t.name: t for t in frappe.get_all(
        "AlphaX POS Dietary Tag",
        filters={"name": ["in", list({l.dietary_tag for l in links})],
                 "tag_kind": "Allergen", "disabled": 0},
        fields=["name", "short_code"], ignore_permissions=True)}
    for l in links:
        t = tags.get(l.dietary_tag)
        if not t:
            continue
        out.setdefault(l.parent, {"food_type": "", "allergens": []})
        code = t.short_code or t.name
        if code not in out[l.parent]["allergens"]:
            out[l.parent]["allergens"].append(code)
    return out


def _guest_allergy_note(doc) -> str:
    """What the guest actually told us, if anything.

    An order-level note wins over the reservation: it is the later
    statement, and the one the cashier heard at the table.
    """
    note = (getattr(doc, "allergy_notes", "") or "").strip()
    if note:
        return note[:500]

    table = getattr(doc, "alphax_table", None) or getattr(doc, "table", None)
    if not table or not frappe.db.exists("DocType", "AlphaX POS Table Reservation"):
        return ""
    res = frappe.get_all(
        "AlphaX POS Table Reservation",
        filters={"table": table, "status": "Seated"},
        fields=["allergy_notes"], order_by="seated_on desc", limit=1,
        ignore_permissions=True)
    return ((res[0].allergy_notes or "").strip()[:500]) if res else ""


# ---------------------------------------------------------------------------
# Whitelisted API — boot config, KDS board, bump
# ---------------------------------------------------------------------------

@frappe.whitelist()
def kot_config(outlet: str | None = None):
    """Stations + routing rules for the register's boot payload.

    The register routes and PRINTS client-side at sale time from this —
    the whole point is that paper KOTs survive an internet outage.
    """
    stations = frappe.get_all(
        "AlphaX POS Print Station",
        filters={"enabled": 1},
        fields=["name", "station_name", "station_type", "outlet", "bridge_target", "is_default"],
    )
    stations = [s for s in stations if not s.outlet or s.outlet == outlet]
    rules = frappe.get_all(
        "AlphaX POS KOT Routing Rule",
        filters={"enabled": 1},
        fields=["item_group", "station", "outlet"],
    )
    rules = [r for r in rules if not r.outlet or r.outlet == outlet]

    # Pre-expand ancestor chains server-side so the client's routing is
    # a plain dict walk — no Item Group tree on the register.
    chains = {}
    groups = {r["item_group"] for r in rules} | set(
        frappe.get_all("Item Group", pluck="name", limit_page_length=0)
    )
    for g in groups:
        chains[g] = _item_group_ancestors(g)

    # v15.10.8 — how many printers the kitchen actually has.
    #
    #   Station Routing     each item to its own printer (the default)
    #   Single Printer      one machine prints everything, with the section
    #                       each block belongs to printed above it so the
    #                       line can still tear the ticket apart
    #   No Kitchen Tickets  suppressed entirely (bar-only, retail)
    mode = "Station Routing"
    single_target = None
    group_by_section = 1
    copies = 1
    if outlet:
        row = frappe.db.get_value(
            "AlphaX POS Outlet", outlet,
            ["kot_mode", "kot_single_target", "kot_group_by_section", "kot_copies"],
            as_dict=True,
        ) or {}
        mode = row.get("kot_mode") or "Station Routing"
        single_target = row.get("kot_single_target") or None
        group_by_section = 1 if row.get("kot_group_by_section") is None else int(
            row.get("kot_group_by_section") or 0)
        copies = int(row.get("kot_copies") or 1) or 1

    if mode == "Single Printer" and not single_target:
        # Fall back to whatever the default station points at, so a site
        # that flips the switch without filling the field still prints.
        default_station = next((s for s in stations if s.get("is_default")), None) \
            or (stations[0] if stations else None)
        if default_station:
            single_target = default_station.get("bridge_target") or default_station.get("name")

    return {
        "stations": stations,
        "rules": rules,
        "group_chains": chains,
        "item_overrides": _item_overrides(),
        "mode": mode,
        "single_target": single_target,
        "group_by_section": group_by_section,
        "copies": copies,
    }


@frappe.whitelist()
def kds_board(station: str | None = None, business_date: str | None = None):
    """Tickets for the KDS board, grouped by status lane."""
    filters = {"status": ["in", ["New", "Preparing", "In Progress", "Packing", "Ready"]]}
    if station:
        filters["station"] = station
    if business_date:
        filters["business_date"] = business_date
    tickets = frappe.get_all(
        "AlphaX POS KDS Ticket",
        filters=filters,
        fields=["name", "station", "sales_invoice", "customer", "table",
                "token_no", "status", "creation", "started_on",
                "guest_allergy_note", "ticket_allergens"],
        order_by="creation asc",
        limit_page_length=200,
    )
    for t in tickets:
        t["lines"] = frappe.get_all(
            "AlphaX POS KDS Ticket Item",
            filters={"parent": t["name"]},
            fields=["item_code", "qty", "notes", "status", "food_type", "allergens"],
            order_by="idx asc",
        )
    return tickets


@frappe.whitelist()
def bump_ticket(ticket: str, status: str):
    """Advance a ticket: New → Preparing → Ready → Served."""
    # Packing sits between the pass and the counter: food is made but
    # not yet bagged. Takeaway and delivery live there; dine-in skips it.
    if status not in ("Preparing", "Packing", "Ready", "Served"):
        frappe.throw(_("Invalid status"))
    doc = frappe.get_doc("AlphaX POS KDS Ticket", ticket)
    doc.status = status
    if status == "Preparing" and not doc.started_on:
        doc.started_on = frappe.utils.now_datetime()
    if status == "Ready":
        doc.ready_on = frappe.utils.now_datetime()
    if status == "Served":
        doc.served_on = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    frappe.publish_realtime(
        "alphax_kds_update",
        {"station": doc.station, "ticket": doc.name, "action": status.lower()},
    )
    return {"ok": True}


@frappe.whitelist()
def mark_printed(tickets):
    """Register confirms the bridge printed these tickets."""
    if isinstance(tickets, str):
        tickets = json.loads(tickets)
    for name in tickets or []:
        frappe.db.set_value("AlphaX POS KDS Ticket", name, "printed", 1, update_modified=False)
    return {"ok": True, "count": len(tickets or [])}
