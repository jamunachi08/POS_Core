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

        for station, lines in groups.items():
            ticket = frappe.get_doc({
                "doctype": "AlphaX POS KDS Ticket",
                "outlet": outlet,
                "station": station,
                "sales_invoice": doc.name,
                "customer": doc.customer,
                "business_date": str(getattr(doc, "posting_date", "") or nowdate()),
                "status": "New",
                "items": [
                    {
                        "item_code": it.item_code,
                        "qty": it.qty,
                        "notes": "",
                        "status": "New",
                        "station": station,
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

    return {
        "stations": stations,
        "rules": rules,
        "group_chains": chains,
        "item_overrides": _item_overrides(),
    }


@frappe.whitelist()
def kds_board(station: str | None = None, business_date: str | None = None):
    """Tickets for the KDS board, grouped by status lane."""
    filters = {"status": ["in", ["New", "Preparing", "Ready"]]}
    if station:
        filters["station"] = station
    if business_date:
        filters["business_date"] = business_date
    tickets = frappe.get_all(
        "AlphaX POS KDS Ticket",
        filters=filters,
        fields=["name", "station", "sales_invoice", "customer", "table",
                "token_no", "status", "creation", "started_on"],
        order_by="creation asc",
        limit_page_length=200,
    )
    for t in tickets:
        t["lines"] = frappe.get_all(
            "AlphaX POS KDS Ticket Item",
            filters={"parent": t["name"]},
            fields=["item_code", "qty", "notes", "status"],
            order_by="idx asc",
        )
    return tickets


@frappe.whitelist()
def bump_ticket(ticket: str, status: str):
    """Advance a ticket: New → Preparing → Ready → Served."""
    if status not in ("Preparing", "Ready", "Served"):
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
