"""A hard cut-off for a till left open.

Closing-time enforcement already handles an outlet that configured a
closing time. It cannot help the ones that did not, and it cannot help a
24-hour site where there is no closing time to enforce. On those, a shift
opened on Monday afternoon will still be taking sales on Thursday, every
one of them posting against Monday's business date.

That is not a cosmetic problem. A stale shift means:

  * takings for three days land in one cash declaration, so the variance
    is meaningless and nobody can be held to it;
  * sales post to a business date that closed days ago, which moves
    revenue into the wrong period;
  * the day close that should have run never runs, so the shift-wise
    report and the deposit never line up.

So this adds an age limit that applies to every terminal, configured or
not. Two separate things happen at the limit, and the distinction matters:

  **Blocking** is synchronous and server-side. It runs in the posting
  path, so it is true the moment the limit passes, whether or not the
  scheduler has woken up. A till cannot sell past its limit even if the
  background worker is dead.

  **Auto-closing** is the scheduler's job, and optional. It declares the
  opening float plus recorded cash movements and flags the shift for
  recount — exactly as closing-time enforcement does. The system never
  invents a counted figure, because a counted figure nobody counted is
  worse than an obvious gap.

The sale in progress is never interrupted. The block applies to the next
one, which is the only humane place to put it: a half-rung sale abandoned
at the payment screen costs a customer.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime, time_diff_in_seconds


def limit_hours(outlet: str | None = None, settings=None) -> int:
    """Hours a shift may stay open here. 0 means no limit.

    The outlet wins where it sets one: a 24-hour forecourt and a
    dinner-only restaurant do not share a sensible number.
    """
    if outlet:
        try:
            if frappe.get_meta("AlphaX POS Outlet").has_field("max_shift_hours"):
                v = cint(frappe.db.get_value("AlphaX POS Outlet", outlet, "max_shift_hours"))
                if v > 0:
                    return v
        except Exception:
            pass
    try:
        if settings is None:
            settings = frappe.get_cached_doc("AlphaX POS Settings")
        return cint(getattr(settings, "max_shift_hours", 0))
    except Exception:
        return 0


def expiry_for(shift_doc, outlet: str | None = None, settings=None):
    """When this shift stops taking sales, or None if it never does."""
    hours = limit_hours(outlet, settings)
    if hours <= 0:
        return None
    opened = shift_doc.get("opened_on") or shift_doc.get("creation")
    if not opened:
        return None
    return add_to_date(get_datetime(opened), hours=hours)


def status_for(shift_doc, outlet: str | None = None, settings=None) -> dict:
    """Countdown state for the till, so the block is never a surprise."""
    expires = expiry_for(shift_doc, outlet, settings)
    if not expires:
        return {"limited": False}

    try:
        warn = cint(getattr(settings or frappe.get_cached_doc("AlphaX POS Settings"),
                            "max_shift_warn_minutes", 60))
    except Exception:
        warn = 60

    remaining = int(time_diff_in_seconds(expires, now_datetime()) // 60)
    return {
        "limited": True,
        "expires_on": str(expires),
        "minutes_left": remaining,
        "expired": remaining <= 0,
        "warn": 0 < remaining <= max(0, warn),
        "limit_hours": limit_hours(outlet, settings),
    }


def ensure_not_expired(terminal: str | None, outlet: str | None = None, settings=None) -> None:
    """Refuse the sale if this terminal's open shift is past its limit.

    Called from the posting path. Raises rather than returning a flag,
    because a caller that forgets to check a flag is a caller that sells
    past the limit.
    """
    if not terminal:
        return
    hours = limit_hours(outlet, settings)
    if hours <= 0:
        return

    row = frappe.db.get_value(
        "AlphaX POS Shift",
        {"pos_terminal": terminal, "status": "Open"},
        ["name", "opened_on", "user"], as_dict=True)
    if not row or not row.opened_on:
        return

    expires = add_to_date(get_datetime(row.opened_on), hours=hours)
    if now_datetime() < expires:
        return

    over = int(time_diff_in_seconds(now_datetime(), expires) // 3600)
    frappe.throw(
        _("This shift has been open for more than {0} hours and stopped taking sales "
          "{1} hour(s) ago. Close the shift, count the drawer and run day close, then "
          "open a new shift.").format(hours, max(over, 1)),
        title=_("Shift past its limit"))


# --------------------------------------------------------------------------
# scheduler
# --------------------------------------------------------------------------


def enforce_max_shift_age():
    """Every 5 minutes: close shifts past their limit, where configured.

    Deliberately separate from closing-time enforcement rather than folded
    into it. The two answer different questions — "is the shop shut?" and
    "has this till been open too long?" — and an outlet can need the second
    without having the first.
    """
    try:
        settings = frappe.get_cached_doc("AlphaX POS Settings")
    except Exception:
        return

    action = getattr(settings, "max_shift_action", "") or "Block new sales"
    site_limit = cint(getattr(settings, "max_shift_hours", 0))

    # Outlets with their own limit, plus every outlet if the site sets one.
    outlet_limits = {}
    try:
        if frappe.get_meta("AlphaX POS Outlet").has_field("max_shift_hours"):
            for o in frappe.get_all("AlphaX POS Outlet",
                                    fields=["name", "max_shift_hours"]):
                if cint(o.max_shift_hours) > 0:
                    outlet_limits[o.name] = cint(o.max_shift_hours)
    except Exception:
        pass

    if site_limit <= 0 and not outlet_limits:
        return
    if action != "Block new sales and auto-close the shift":
        return      # blocking alone is handled in the posting path

    from alphax_pos_suite.alphax_pos_suite.pos.shift_api import (
        _maybe_time_dayclose, _movement_totals, _outlet_for_terminal, _shift_summary,
    )
    from frappe.utils import flt

    now = now_datetime()
    for s in frappe.get_all("AlphaX POS Shift", filters={"status": "Open"},
                            fields=["name", "pos_terminal", "opened_on"]):
        if not s.opened_on:
            continue
        outlet = _outlet_for_terminal(s.pos_terminal)
        hours = outlet_limits.get(outlet) or site_limit
        if hours <= 0:
            continue
        if now < add_to_date(get_datetime(s.opened_on), hours=hours):
            continue

        try:
            doc = frappe.get_doc("AlphaX POS Shift", s.name)
            movements = _movement_totals(doc.name)
            declared = (flt(doc.opening_cash) + flt(movements.get("in"))
                        - flt(movements.get("out")))
            doc.status = "Closed"
            doc.closing_cash = declared
            doc.closed_on = now_datetime()
            doc.notes = ((doc.notes or "") +
                         f"\n[AUTO-CLOSED after {hours}h open — counted cash NOT declared "
                         "by cashier; figure is float+movements. RECOUNT REQUIRED.]").strip()
            doc.save(ignore_permissions=True)

            from alphax_pos_suite.alphax_pos_suite.pos.notify import notify_shift_close
            notify_shift_close({**_shift_summary(doc), "terminal": s.pos_terminal,
                                "counted_cash": declared, "auto_closed": True}, outlet)
        except Exception:
            frappe.log_error(title="AlphaX POS: max shift age auto-close failed",
                             message=frappe.get_traceback())
            continue

        _maybe_time_dayclose(s.pos_terminal)
    frappe.db.commit()


@frappe.whitelist()
def shift_age_status(terminal: str) -> dict:
    """What the till shows in its countdown."""
    row = frappe.db.get_value(
        "AlphaX POS Shift", {"pos_terminal": terminal, "status": "Open"},
        ["name", "opened_on"], as_dict=True)
    if not row:
        return {"limited": False, "open": False}

    outlet = frappe.db.get_value("AlphaX POS Terminal", terminal, "pos_outlet")
    try:
        settings = frappe.get_cached_doc("AlphaX POS Settings")
    except Exception:
        settings = None
    out = status_for(row, outlet, settings)
    out["open"] = True
    out["shift"] = row.name
    return out
