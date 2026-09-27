"""
AlphaX POS — Customer Display (order status board)

The screen in the lobby. It runs unattended on a TV stick or a spare
tablet, so it must work without a login and without anyone reconnecting
it after a power cut. Access is by outlet + display key rather than a
session: a key is a lobby screen's whole identity, and rotating it is one
field edit.

The board never exposes prices, customer names, or line items — a queue
of strangers can read it. Order number, lane, and elapsed time only.
"""

import urllib.parse

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, get_datetime

# KDS status -> the three lanes the guest actually cares about.
LANES = {
    "preparing": ["New", "Preparing", "In Progress"],
    "packing": ["Packing"],
    "ready": ["Ready"],
}


def _ensure_key(outlet: str) -> str:
    key = frappe.db.get_value("AlphaX POS Outlet", outlet, "display_key")
    if key:
        return key
    key = frappe.generate_hash(length=24)
    frappe.db.set_value("AlphaX POS Outlet", outlet, "display_key", key,
                        update_modified=False)
    return key


@frappe.whitelist()
def get_display_url(outlet: str):
    """Manager-facing: the URL to open on the lobby screen.

    Generates the key on first call, so setting a screen up is 'copy this
    link' rather than 'find the key field'.
    """
    if not frappe.has_permission("AlphaX POS Outlet", "write", doc=outlet):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    key = _ensure_key(outlet)
    return {
        "url": f"{frappe.utils.get_url()}/order_status"
               f"?outlet={urllib.parse.quote(outlet)}&key={key}",
        "key": key,
    }


def _check(outlet: str, key: str):
    if not outlet or not frappe.db.exists("AlphaX POS Outlet", outlet):
        frappe.throw(_("Unknown outlet"), frappe.DoesNotExistError)
    stored = frappe.db.get_value("AlphaX POS Outlet", outlet, "display_key")
    if not stored or not key or key != stored:
        # Deliberately identical message for missing and wrong keys.
        frappe.throw(_("This screen is not authorised."), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def board(outlet: str, key: str, business_date: str | None = None):
    """Everything the lobby screen draws, in one call.

    Poll-friendly: cheap, no joins beyond the ticket table, and the
    payload is small enough that a 4-second poll on a shop TV is nothing.
    """
    _check(outlet, key)

    cfg = frappe.db.get_value(
        "AlphaX POS Outlet", outlet,
        ["outlet_name", "branch", "display_announce", "display_announce_repeat",
         "display_ticker_en", "display_ticker_ar", "display_feedback_url",
         "display_ready_hold_seconds"],
        as_dict=True,
    ) or {}

    hold = cint(cfg.get("display_ready_hold_seconds")) or 180

    statuses = [s for group in LANES.values() for s in group]
    filters = {"outlet": outlet, "status": ["in", statuses]}
    if business_date:
        filters["business_date"] = business_date

    tickets = frappe.get_all(
        "AlphaX POS KDS Ticket",
        filters=filters,
        fields=["name", "pos_order", "token_no", "status", "creation",
                "started_on", "ready_on", "sla_minutes", "table"],
        order_by="creation asc",
        limit_page_length=120,
    )

    now = now_datetime()
    lanes = {"preparing": [], "packing": [], "ready": []}

    for t in tickets:
        lane = next((k for k, v in LANES.items() if t.status in v), None)
        if not lane:
            continue

        # A ready order that nobody collected clears itself, otherwise the
        # board fills up overnight and the real ones scroll out of sight.
        if lane == "ready" and t.ready_on:
            age = (now - get_datetime(t.ready_on)).total_seconds()
            if age > hold:
                continue

        started = get_datetime(t.started_on or t.creation)
        elapsed = max(0, int((now - started).total_seconds()))
        target = (cint(t.sla_minutes) or 0) * 60

        lanes[lane].append({
            "id": t.name,
            # Guests read the order number off their receipt; the token is
            # what a counter shouts. Prefer the token when there is one.
            "label": t.token_no or _short_order(t.pos_order) or t.name[-6:],
            "order": t.pos_order,
            "elapsed": elapsed,
            "progress": min(100, int(elapsed * 100 / target)) if target else None,
            "late": bool(target and elapsed > target),
            "ready_on": str(t.ready_on) if t.ready_on else None,
        })

    return {
        "ok": True,
        "server_time": str(now),
        "outlet": {
            "name": outlet,
            "label": cfg.get("outlet_name") or outlet,
            "branch": cfg.get("branch"),
        },
        "lanes": lanes,
        "counts": {k: len(v) for k, v in lanes.items()},
        "announce": {
            "enabled": bool(cint(cfg.get("display_announce") or 0)),
            "repeat": max(1, cint(cfg.get("display_announce_repeat")) or 2),
        },
        "ticker": {
            "en": cfg.get("display_ticker_en") or "",
            "ar": cfg.get("display_ticker_ar") or "",
        },
        "feedback_url": cfg.get("display_feedback_url") or "",
    }


def _short_order(order_name: str | None) -> str:
    """APOS-ORD-2026-00063 -> 00063.

    The full name is unreadable at four metres and unspeakable by a voice
    engine. The trailing number is what a guest matches against.
    """
    if not order_name:
        return ""
    tail = str(order_name).rsplit("-", 1)[-1]
    return tail if tail.isdigit() else str(order_name)[-6:]
