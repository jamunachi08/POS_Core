"""The 86 list — what the kitchen has run out of.

Mid-service the kitchen runs out of something. On a till without this, the
cashier keeps selling it, the ticket reaches the pass, somebody walks back
to the table, and the guest is told no after they have already decided.
The fix is one record and one rule: an item marked **Off** at an outlet is
not offered at that outlet's tills.

Three states rather than two, because kitchens do not think in two:

  Off   gone. Hidden at the till, drawn on the kitchen board.
  Low   nearly gone. Still sells, but the cashier is warned before adding
        it, so a party of eight does not order the last two portions.
  On    back. Kept as a record rather than deleted, so "how often did we
        86 the salmon last month" is a question with an answer.

Availability is per outlet, never per company. One branch running out of
lamb is not a reason to stop selling it across the city.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

WRITE_ROLES = {"AlphaX POS Kitchen", "AlphaX POS Supervisor",
               "AlphaX POS Manager", "System Manager"}
READ_ROLES = WRITE_ROLES | {"AlphaX POS Cashier"}


def _require(roles: set):
    if not (set(frappe.get_roles()) & roles):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def current_map(outlet: str | None) -> dict:
    """{item_code: {"status", "reason"}} for everything not On right now.

    Returned as a plain dict so the menu builder can filter in memory
    rather than issuing a query per item.
    """
    if not outlet or not frappe.db.exists("DocType", "AlphaX POS Item Availability"):
        return {}
    rows = frappe.get_all(
        "AlphaX POS Item Availability",
        filters={"outlet": outlet, "status": ["in", ["Off", "Low"]]},
        fields=["item", "status", "reason", "until"],
        ignore_permissions=True, limit_page_length=0)

    now = now_datetime()
    out = {}
    for r in rows:
        # An expired hold is already back on, whether or not the scheduler
        # has run. The till must never be the last to know.
        if r.until and frappe.utils.get_datetime(r.until) <= now:
            continue
        out[r.item] = {"status": r.status, "reason": r.reason or ""}
    return out


@frappe.whitelist()
def board(outlet: str | None = None) -> dict:
    """What is off and what is low, for the kitchen board and the till."""
    _require(READ_ROLES)
    outlet = outlet or frappe.db.get_value("AlphaX POS Outlet", {}, "name")
    rows = current_map(outlet)
    if not rows:
        return {"outlet": outlet, "off": [], "low": [], "count": 0}

    names = {r.name: r.item_name for r in frappe.get_all(
        "Item", filters={"name": ["in", list(rows)]}, fields=["name", "item_name"],
        ignore_permissions=True)}

    def pack(status):
        return sorted(
            [{"item": k, "item_name": names.get(k, k), "reason": v["reason"]}
             for k, v in rows.items() if v["status"] == status],
            key=lambda x: x["item_name"])

    off, low = pack("Off"), pack("Low")
    return {"outlet": outlet, "off": off, "low": low, "count": len(off) + len(low)}


@frappe.whitelist()
def set_availability(item: str, outlet: str, status: str = "Off",
                     reason: str | None = None, until: str | None = None) -> dict:
    """Take an item off, flag it low, or put it back.

    One row per item per outlet, updated in place: a second Off on an item
    already off should correct the reason, not create a second record that
    someone later has to reconcile.
    """
    _require(WRITE_ROLES)
    if status not in ("Off", "Low", "On"):
        frappe.throw(_("Status must be Off, Low or On."))
    if not frappe.db.exists("Item", item):
        frappe.throw(_("Unknown item {0}").format(item))
    if not frappe.db.exists("AlphaX POS Outlet", outlet):
        frappe.throw(_("Unknown outlet {0}").format(outlet))

    name = frappe.db.get_value("AlphaX POS Item Availability",
                               {"item": item, "outlet": outlet}, "name")
    if name:
        doc = frappe.get_doc("AlphaX POS Item Availability", name)
    else:
        doc = frappe.new_doc("AlphaX POS Item Availability")
        doc.item = item
        doc.outlet = outlet

    was = doc.get("status")
    doc.status = status
    doc.reason = (reason or "").strip()[:140]
    doc.until = until or None

    if status == "On":
        doc.restored_by = frappe.session.user
        doc.restored_on = now_datetime()
    else:
        doc.marked_by = frappe.session.user
        doc.marked_on = now_datetime()
        doc.restored_by = None
        doc.restored_on = None

    doc.flags.ignore_permissions = True
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
    frappe.db.commit()

    # The till caches its menu; tell every screen at once rather than
    # waiting for the next reload.
    frappe.publish_realtime("alphax_availability_update",
                            {"outlet": outlet, "item": item, "status": status})

    return {"ok": True, "item": item, "outlet": outlet,
            "status": status, "was": was}


def restore_expired():
    """Scheduler: put back anything whose hold has run out.

    Runs hourly. The till already ignores an expired hold, so this only
    tidies the records and keeps the board honest for whoever reads it.
    """
    if not frappe.db.exists("DocType", "AlphaX POS Item Availability"):
        return
    rows = frappe.get_all(
        "AlphaX POS Item Availability",
        filters={"status": ["in", ["Off", "Low"]], "until": ["<=", now_datetime()]},
        fields=["name", "outlet", "item"], ignore_permissions=True)
    for r in rows:
        frappe.db.set_value("AlphaX POS Item Availability", r.name, {
            "status": "On", "restored_on": now_datetime(), "restored_by": "Administrator",
        }, update_modified=False)
        frappe.publish_realtime("alphax_availability_update",
                                {"outlet": r.outlet, "item": r.item, "status": "On"})
    if rows:
        frappe.db.commit()
