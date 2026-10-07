"""Table timeline — the F&B answer to a hotel tape chart.

A hotel plots rooms against nights. A restaurant turns the same table five
times in one evening, so the axis that matters is hours, not days, and the
scarce resource is covers rather than keys.

What the board shows, per outlet per service day:

  rows       tables, grouped by floor
  bars       reservations (booked or seated) and live table sessions
  position   per half hour: covers held against covers available, and
             tables in use against tables open. The yield line.
  conflicts  two bars overlapping on one table, or a gap too short to
             clear and reset it between two parties.

Everything is computed server-side. The board draws what it is given, so
the same numbers answer "can I take a party of six at eight" whether the
question comes from the desk, the cashier, or a phone call.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (add_to_date, cint, get_datetime, getdate, now_datetime,
                          time_diff_in_seconds)

from alphax_pos_suite.alphax_pos_suite.doctype.alphax_pos_table_reservation.alphax_pos_table_reservation import (  # noqa: E501
    LIVE_STATUSES, first_clash, turnaround_minutes, window,
)

SLOT_MINUTES = 30
READ_ROLES = {"AlphaX POS Cashier", "AlphaX POS Supervisor",
              "AlphaX POS Manager", "System Manager"}
WRITE_ROLES = {"AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}


def _require(roles: set):
    if not (set(frappe.get_roles()) & roles):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _minutes(dt, day_start) -> int:
    return int(time_diff_in_seconds(dt, day_start) // 60)


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------


@frappe.whitelist()
def get_timeline(outlet: str | None = None, date: str | None = None,
                 floor: str | None = None, start_hour: int = 10,
                 end_hour: int = 24) -> dict:
    _require(READ_ROLES)

    outlet = outlet or frappe.db.get_value("AlphaX POS Outlet", {}, "name")
    if not outlet:
        return {"tables": [], "warning": _("No outlet exists yet.")}
    day = getdate(date or frappe.utils.nowdate())
    start_hour, end_hour = cint(start_hour), cint(end_hour)
    if end_hour <= start_hour:
        end_hour = start_hour + 1

    day_start = get_datetime(f"{day} {start_hour:02d}:00:00")
    day_end = get_datetime(f"{day} 00:00:00")
    day_end = add_to_date(day_end, hours=end_hour)
    span = _minutes(day_end, day_start)

    t_filters = {"outlet": outlet, "status": ["!=", "Disabled"]}
    if floor:
        t_filters["floor"] = floor
    tables = frappe.get_all(
        "AlphaX POS Table", filters=t_filters,
        fields=["name", "table_code", "floor", "seats", "status", "readiness",
                "min_party_size", "max_party_size"],
        order_by="floor asc, table_code asc", ignore_permissions=True)

    by_table = {t.name: t for t in tables}
    pad = turnaround_minutes(outlet)

    res = frappe.get_all(
        "AlphaX POS Table Reservation",
        filters={"outlet": outlet, "reservation_date": day,
                 "status": ["in", LIVE_STATUSES + ("Completed", "No Show")]},
        fields=["name", "table", "guest_name", "phone", "covers", "status", "vip",
                "source", "from_time", "to_time", "duration_minutes",
                "allergy_notes", "notes", "seated_on", "table_session"],
        order_by="from_time asc", ignore_permissions=True)

    bars, unassigned = {}, []
    for r in res:
        s, e = window(day, r.from_time, r.duration_minutes)
        bar = {
            "kind": "reservation", "name": r.name, "label": r.guest_name,
            "covers": r.covers, "status": r.status, "vip": cint(r.vip),
            "source": r.source, "phone": r.phone,
            "from": str(r.from_time)[:5], "to": str(r.to_time or "")[:5],
            "start_min": _minutes(s, day_start), "end_min": _minutes(e, day_start),
            "allergy": (r.allergy_notes or "").strip(),
            "notes": (r.notes or "").strip(),
            "seated_on": r.seated_on, "session": r.table_session,
        }
        if r.table and r.table in by_table:
            bars.setdefault(r.table, []).append(bar)
        elif r.status in LIVE_STATUSES:
            unassigned.append(bar)

    # Live sessions: a walk-in has no reservation, but it still occupies a
    # table and still consumes covers, so it belongs on the same axis.
    sess_fields = ["name", "table", "opened_on", "status"]
    meta = frappe.get_meta("AlphaX POS Table Session")
    for extra in ("closed_on", "covers", "reservation"):
        if meta.has_field(extra):
            sess_fields.append(extra)
    sessions = frappe.get_all(
        "AlphaX POS Table Session",
        filters={"table": ["in", list(by_table)] or [""],
                 "opened_on": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
        fields=sess_fields, order_by="opened_on asc", ignore_permissions=True)

    seen_sessions = {b.get("session") for v in bars.values() for b in v if b.get("session")}
    now = now_datetime()
    for s in sessions:
        if s.name in seen_sessions:
            continue                       # already drawn as its reservation
        opened = get_datetime(s.opened_on)
        closed = get_datetime(s.get("closed_on")) if s.get("closed_on") else None
        end = closed or min(now, day_end) if opened <= day_end else opened
        bars.setdefault(s.table, []).append({
            "kind": "session", "name": s.name, "label": _("Walk-in"),
            "covers": cint(s.get("covers")), "status": s.status,
            "vip": 0, "source": "Walk-in", "phone": None,
            "from": opened.strftime("%H:%M"), "to": (closed or now).strftime("%H:%M"),
            "start_min": _minutes(opened, day_start), "end_min": _minutes(end, day_start),
            "open": s.status == "Open", "allergy": "", "notes": "",
        })

    # ---- conflicts ------------------------------------------------------
    conflicts = []
    for tname, rows in bars.items():
        rows.sort(key=lambda b: b["start_min"])
        for a, b in zip(rows, rows[1:]):
            if b["start_min"] < a["end_min"]:
                kind, detail = "overlap", _("{0} and {1} overlap on this table").format(
                    a["label"], b["label"])
            elif b["start_min"] - a["end_min"] < pad:
                kind, detail = "turnaround", _(
                    "Only {0} min between {1} leaving and {2} arriving; this outlet "
                    "needs {3}.").format(b["start_min"] - a["end_min"], a["label"],
                                         b["label"], pad)
            else:
                continue
            conflicts.append({
                "table": tname, "table_code": by_table[tname].table_code,
                "kind": kind, "detail": detail,
                "first": a["name"], "second": b["name"],
                "at": b["from"],
            })

    # ---- position line ---------------------------------------------------
    seats_total = sum(cint(t.seats) for t in tables) or 0
    slots = []
    for m in range(0, span, SLOT_MINUTES):
        held_cov = held_tables = 0
        for tname, rows in bars.items():
            for b in rows:
                if b["start_min"] < m + SLOT_MINUTES and m < b["end_min"]:
                    held_cov += cint(b["covers"]) or cint(by_table[tname].seats)
                    held_tables += 1
                    break
        at = add_to_date(day_start, minutes=m)
        slots.append({
            "label": at.strftime("%H:%M"), "minute": m,
            "covers": held_cov, "seats": seats_total,
            "tables": held_tables, "table_count": len(tables),
            "occupancy": round(100.0 * held_cov / seats_total, 1) if seats_total else 0,
            "over": held_cov > seats_total,
        })

    return {
        "outlet": outlet, "date": str(day), "floor": floor,
        "start_hour": start_hour, "end_hour": end_hour,
        "span_minutes": span, "slot_minutes": SLOT_MINUTES,
        "turnaround_minutes": pad,
        "tables": [{
            "name": t.name, "table_code": t.table_code, "floor": t.floor,
            "seats": cint(t.seats), "status": t.status, "readiness": t.readiness,
            "min_party_size": cint(t.min_party_size), "max_party_size": cint(t.max_party_size),
            "bars": bars.get(t.name, []),
        } for t in tables],
        "unassigned": unassigned,
        "conflicts": conflicts,
        "slots": slots,
        "totals": {
            "tables": len(tables), "seats": seats_total,
            "reservations": len([r for r in res if r.status in LIVE_STATUSES]),
            "covers": sum(cint(r.covers) for r in res if r.status in LIVE_STATUSES),
            "peak_covers": max([s["covers"] for s in slots], default=0),
            "no_shows": len([r for r in res if r.status == "No Show"]),
        },
    }


@frappe.whitelist()
def suggest_tables(reservation: str, limit: int = 5) -> list:
    """Tables that could take this party, best fit first.

    Best fit means the smallest table that still seats the party, because
    seating four at a table for eight costs covers later in the evening.
    A table with a clash is not offered at all.
    """
    _require(READ_ROLES)
    r = frappe.get_doc("AlphaX POS Table Reservation", reservation)

    rows = frappe.get_all(
        "AlphaX POS Table",
        filters={"outlet": r.outlet, "status": ["!=", "Disabled"]},
        fields=["name", "table_code", "seats", "floor", "readiness",
                "min_party_size", "max_party_size"], ignore_permissions=True)

    out = []
    for t in rows:
        cap = cint(t.max_party_size) or cint(t.seats)
        if cap and cint(r.covers) > cap:
            continue
        if cint(t.min_party_size) and cint(r.covers) < cint(t.min_party_size):
            continue
        if first_clash(t.name, r.reservation_date, r.from_time, r.duration_minutes,
                       exclude=r.name):
            continue
        out.append({
            "table": t.name, "table_code": t.table_code, "floor": t.floor,
            "seats": cint(t.seats), "capacity": cap,
            "spare": max(0, cap - cint(r.covers)),
            "readiness": t.readiness,
        })

    out.sort(key=lambda x: (x["spare"], x["seats"]))
    return out[:cint(limit) or 5]


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------


@frappe.whitelist()
def assign_table(reservation: str, table: str) -> dict:
    """Move a booking onto a table. Validation lives in the controller."""
    _require(WRITE_ROLES)
    doc = frappe.get_doc("AlphaX POS Table Reservation", reservation)
    doc.table = table
    doc.save()                       # overlap + party size enforced here
    frappe.db.commit()
    return {"ok": True, "reservation": doc.name, "table": doc.table}


@frappe.whitelist()
def reschedule(reservation: str, from_time: str | None = None,
               date: str | None = None, duration_minutes: int | None = None) -> dict:
    """Drag a bar. Same validation path as typing the change on the form."""
    _require(WRITE_ROLES)
    doc = frappe.get_doc("AlphaX POS Table Reservation", reservation)
    if date:
        doc.reservation_date = getdate(date)
    if from_time:
        doc.from_time = from_time
    if duration_minutes:
        doc.duration_minutes = cint(duration_minutes)
    doc.save()
    frappe.db.commit()
    return {"ok": True, "reservation": doc.name,
            "from": str(doc.from_time)[:5], "to": str(doc.to_time)[:5]}


@frappe.whitelist()
def set_status(reservation: str, status: str) -> dict:
    _require(WRITE_ROLES)
    if status not in ("Booked", "Seated", "Completed", "No Show", "Cancelled"):
        frappe.throw(_("Unknown status {0}").format(status))
    doc = frappe.get_doc("AlphaX POS Table Reservation", reservation)
    doc.status = status
    if status in ("Completed", "No Show", "Cancelled") and not doc.released_on:
        doc.released_on = now_datetime()
    doc.save()
    frappe.db.commit()
    return {"ok": True, "reservation": doc.name, "status": doc.status}


@frappe.whitelist()
def seat(reservation: str) -> dict:
    """Seat the party: open a table session and mark the table occupied.

    The session is the existing document the cashier screen already works
    with, so a seated reservation becomes an ordinary running table rather
    than a parallel concept the till has to learn.
    """
    _require({"AlphaX POS Cashier"} | WRITE_ROLES)
    doc = frappe.get_doc("AlphaX POS Table Reservation", reservation)
    if not doc.table:
        frappe.throw(_("Assign a table before seating this party."))
    if doc.status == "Seated":
        return {"ok": True, "reservation": doc.name, "session": doc.table_session,
                "already": True}

    session = frappe.db.get_value("AlphaX POS Table Session",
                                  {"table": doc.table, "status": "Open"}, "name")
    if not session:
        s = frappe.new_doc("AlphaX POS Table Session")
        s.table = doc.table
        s.opened_on = now_datetime()
        s.status = "Open"
        if s.meta.has_field("covers"):
            s.covers = cint(doc.covers)
        if s.meta.has_field("reservation"):
            s.reservation = doc.name
        s.insert(ignore_permissions=True)
        session = s.name

    doc.status = "Seated"
    doc.seated_on = now_datetime()
    doc.table_session = session
    doc.save(ignore_permissions=True)

    frappe.db.set_value("AlphaX POS Table", doc.table,
                        {"status": "Occupied", "last_seated_on": now_datetime()},
                        update_modified=False)
    frappe.db.commit()
    return {"ok": True, "reservation": doc.name, "session": session, "table": doc.table}
