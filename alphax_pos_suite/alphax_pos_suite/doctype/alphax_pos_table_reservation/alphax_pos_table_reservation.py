"""A table held for a party at a time.

Two rules are enforced here rather than in the UI, because the timeline is
not the only way a reservation gets created — the desk form, an import and
(later) an online booking all land in the same place:

  * a table cannot hold two live bookings that overlap, including the
    turnaround gap the outlet needs to clear and reset it;
  * a party cannot be seated at a table too small for it.

Cancelled and No Show bookings are ignored by both, so releasing a table
is a status change rather than a delete, and the history survives.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, get_datetime, get_time, getdate

#: Minutes a table needs between one party leaving and the next sitting
#: down. Overridable per outlet via ``table_turnaround_minutes`` if that
#: field is added later; the default matches typical casual dining.
DEFAULT_TURNAROUND = 10

LIVE_STATUSES = ("Booked", "Seated")


class AlphaXPOSTableReservation(Document):
    def validate(self):
        self._normalise()
        self._check_party_size()
        self._check_overlap()

    def _normalise(self):
        self.duration_minutes = cint(self.duration_minutes) or 90
        if self.duration_minutes < 15:
            frappe.throw(_("A reservation needs at least 15 minutes."))
        self.covers = cint(self.covers) or 1

        start = get_datetime(f"{self.reservation_date} {self.from_time}")
        self.to_time = add_to_date(start, minutes=self.duration_minutes).strftime("%H:%M:%S")

        if self.table and not self.outlet:
            self.outlet = frappe.db.get_value("AlphaX POS Table", self.table, "outlet")
        if self.table and not self.floor:
            self.floor = frappe.db.get_value("AlphaX POS Table", self.table, "floor")

    def _check_party_size(self):
        if not self.table:
            return
        row = frappe.db.get_value(
            "AlphaX POS Table", self.table,
            ["seats", "min_party_size", "max_party_size", "outlet", "status"], as_dict=True) or {}

        if row.get("outlet") and self.outlet and row["outlet"] != self.outlet:
            frappe.throw(_("Table {0} belongs to outlet {1}.").format(self.table, row["outlet"]))
        if row.get("status") == "Disabled":
            frappe.throw(_("Table {0} is disabled.").format(self.table))

        # max_party_size wins where set; otherwise the seat count is the cap.
        cap = cint(row.get("max_party_size")) or cint(row.get("seats"))
        if cap and self.covers > cap:
            frappe.throw(_("Table {0} seats {1}. This party is {2}.")
                         .format(self.table, cap, self.covers))
        floor_min = cint(row.get("min_party_size"))
        if floor_min and self.covers < floor_min:
            frappe.throw(_("Table {0} is only released for parties of {1} or more.")
                         .format(self.table, floor_min))

    def _check_overlap(self):
        if not self.table or self.status not in LIVE_STATUSES:
            return
        clash = first_clash(self.table, self.reservation_date, self.from_time,
                            self.duration_minutes, exclude=self.name)
        if clash:
            frappe.throw(_("Table {0} is already held by {1} from {2} to {3}.")
                         .format(self.table, clash["guest_name"],
                                 str(clash["from_time"])[:5], str(clash["to_time"])[:5]))


# --------------------------------------------------------------------------
# shared helpers, used by the timeline API too
# --------------------------------------------------------------------------


def turnaround_minutes(outlet: str | None = None) -> int:
    if outlet:
        try:
            if frappe.get_meta("AlphaX POS Outlet").has_field("table_turnaround_minutes"):
                v = cint(frappe.db.get_value("AlphaX POS Outlet", outlet,
                                             "table_turnaround_minutes"))
                if v:
                    return v
        except Exception:
            pass
    return DEFAULT_TURNAROUND


def window(date, from_time, minutes: int, pad: int = 0):
    """(start, end) datetimes for a booking, optionally padded by turnaround."""
    start = get_datetime(f"{getdate(date)} {from_time}")
    end = add_to_date(start, minutes=cint(minutes))
    if pad:
        start = add_to_date(start, minutes=-pad)
        end = add_to_date(end, minutes=pad)
    return start, end


def live_reservations(table: str, date, exclude: str | None = None) -> list:
    filters = {"table": table, "reservation_date": getdate(date),
               "status": ["in", LIVE_STATUSES]}
    if exclude:
        filters["name"] = ["!=", exclude]
    return frappe.get_all(
        "AlphaX POS Table Reservation", filters=filters,
        fields=["name", "guest_name", "from_time", "to_time", "duration_minutes",
                "covers", "status", "vip"],
        order_by="from_time asc", ignore_permissions=True)


def first_clash(table: str, date, from_time, minutes: int, exclude: str | None = None):
    """The first live booking whose padded window overlaps the given one."""
    outlet = frappe.db.get_value("AlphaX POS Table", table, "outlet")
    pad = turnaround_minutes(outlet)
    start, end = window(date, from_time, minutes)

    for r in live_reservations(table, date, exclude):
        # Pad the *existing* booking so a new one cannot start while the
        # table is still being cleared.
        o_start, o_end = window(date, r.from_time, r.duration_minutes, pad=pad)
        if start < o_end and o_start < end:
            return r
    return None
