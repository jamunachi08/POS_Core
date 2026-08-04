"""
Cashier-facing shift & cash management API.

Flow at the till:
    open_shift(float)            → drawer starts with a declared float
    record_cash_movement(...)    → Paid In / Paid Out / Petty Cash
                                   Expense / Cash Drop To Safe, mid-shift
    x_report()                   → read-only snapshot, any time, no reset
    close_shift(counted_cash)    → BLIND count: cashier declares first,
                                   server then reveals expected cash and
                                   the over/short (variance) — the
                                   industry-standard honesty control
    day_close()                  → rolls all of a terminal's closed
                                   shifts for the date into an AlphaX
                                   POS Day Close document

Data-source note: this module is source-aware. Terminals configured
for the classic pipeline aggregate AlphaX POS Order; the Vue register
posts Sales Invoices directly, which as of v15.7.1 carry an
`alphax_pos_terminal` stamp — so multi-terminal sites reconcile each
drawer independently. Sales Invoices posted before the stamp existed
fall back to owner+time-window matching.

Credit sales (is_pos=0, order type "Credit") are reported in their own
bucket: they are revenue for the shift but never cash in the drawer.
"""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

MOVEMENT_TYPES = ("Paid In", "Paid Out", "Petty Cash Expense", "Cash Drop To Safe")

# Movement directions relative to the drawer.
_IN = {"Paid In"}
_OUT = {"Paid Out", "Petty Cash Expense", "Cash Drop To Safe"}


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _bust_boot_cache(terminal: str):
    """Boot payload caches the terminal's business date — shift open and
    day close change it, so both must invalidate the cache or registers
    reload into a stale trading day."""
    try:
        frappe.cache().delete_value(f"alphax_pos_boot::{terminal}")
    except Exception:
        pass


def _cash_mop() -> str:
    try:
        s = frappe.get_cached_doc("AlphaX POS Settings")
        return s.get("cash_mode_of_payment") or "Cash"
    except Exception:
        return "Cash"


def _get_open_shift(terminal: str):
    rows = frappe.get_all(
        "AlphaX POS Shift",
        filters={"pos_terminal": terminal, "status": "Open"},
        fields=["name"],
        order_by="opened_on desc",
        limit=1,
    )
    return frappe.get_doc("AlphaX POS Shift", rows[0].name) if rows else None


def _source_for(terminal: str) -> str:
    from alphax_pos_suite.alphax_pos_suite.reporting.close_reports import _get_close_source
    return _get_close_source(terminal, default="Sales Invoice")


def _shift_invoices(shift) -> list[dict]:
    """Submitted sale documents belonging to this shift, source-aware."""
    frm = shift.opened_on
    to = shift.closed_on or now_datetime()

    if _source_for(shift.pos_terminal) == "AlphaX POS Order":
        rows = frappe.get_all(
            "AlphaX POS Order",
            filters={
                "docstatus": 1,
                "pos_terminal": shift.pos_terminal,
                "creation": ["between", [frm, to]],
            },
            fields=["name", "is_return"],
        )
        if rows:
            for r in rows:
                r["doctype"] = "AlphaX POS Order"
            return rows
        # Config-tolerant fallback: a terminal set to POS Order source
        # while the register posts Sales Invoices directly would report
        # zero sales all shift (field report: 4 invoices, X report 0.00,
        # terminal had close_report_source = "AlphaX POS Order"). If the
        # configured source has NOTHING in the window, fall through to
        # the Sales Invoice scan — the report tells the truth either way.

    # Sales Invoice source. Preferred scope: the terminal stamp. Legacy
    # rows (pre-stamp) are matched by cashier + time window instead.
    stamped = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "alphax_pos_terminal": shift.pos_terminal,
            "creation": ["between", [frm, to]],
        },
        fields=["name", "is_return", "is_pos", "alphax_order_type",
                "grand_total", "discount_amount", "total_taxes_and_charges"],
    )
    if stamped:
        return stamped
    return frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "owner": shift.user,
            "alphax_pos_terminal": ["is", "not set"],
            "creation": ["between", [frm, to]],
        },
        fields=["name", "is_return", "is_pos", "alphax_order_type",
                "grand_total", "discount_amount", "total_taxes_and_charges"],
    )


def _movement_totals(shift_name: str) -> dict:
    rows = frappe.get_all(
        "AlphaX POS Cash Movement",
        filters={"shift": shift_name},
        fields=["movement_type", "sum(amount) as amt"],
        group_by="movement_type",
    )
    out = {t: 0.0 for t in MOVEMENT_TYPES}
    for r in rows:
        out[r.movement_type] = flt(r.amt)
    return out


def _shift_summary(shift) -> dict:
    """Everything both X and Z reports need, computed fresh."""
    invoices = _shift_invoices(shift)
    cash_mop = _cash_mop()

    by_mop: dict[str, float] = {}
    gross = returns = discount = vat = 0.0
    credit_total = 0.0
    sale_count = return_count = credit_count = 0

    si_names = [i["name"] for i in invoices
                if i.get("doctype", "Sales Invoice") == "Sales Invoice"]
    payments = []
    if si_names:
        payments = frappe.get_all(
            "Sales Invoice Payment",
            filters={"parent": ["in", si_names], "parenttype": "Sales Invoice"},
            fields=["parent", "mode_of_payment", "amount"],
        )
    else:
        order_names = [i["name"] for i in invoices]
        if order_names:
            payments = frappe.get_all(
                "AlphaX POS Payment",
                filters={"parent": ["in", order_names]},
                fields=["parent", "mode_of_payment", "amount"],
            )

    for p in payments:
        by_mop[p.mode_of_payment] = by_mop.get(p.mode_of_payment, 0.0) + flt(p.amount)

    for inv in invoices:
        gt = flt(inv.get("grand_total") or 0)
        if inv.get("alphax_order_type") == "Credit":
            credit_total += gt
            credit_count += 1
        elif inv.get("is_return"):
            returns += abs(gt)
            return_count += 1
        else:
            gross += gt
            sale_count += 1
        discount += flt(inv.get("discount_amount") or 0)
        vat += flt(inv.get("total_taxes_and_charges") or 0)

    moves = _movement_totals(shift.name)
    cash_sales = by_mop.get(cash_mop, 0.0)
    expected_cash = (
        flt(shift.opening_cash)
        + cash_sales
        + sum(v for t, v in moves.items() if t in _IN)
        - sum(v for t, v in moves.items() if t in _OUT)
    )

    return {
        "shift": shift.name,
        "terminal": shift.pos_terminal,
        "user": shift.user,
        "business_date": str(shift.get("business_date") or ""),
        "opened_on": shift.opened_on,
        "closed_on": shift.closed_on,
        "status": shift.status,
        "opening_cash": flt(shift.opening_cash),
        "cash_mop": cash_mop,
        "by_mop": [{"mode_of_payment": k, "amount": v} for k, v in sorted(by_mop.items())],
        "gross_sales": gross,
        "returns": returns,
        "net_sales": gross - returns,
        "credit_sales": credit_total,
        "discount": discount,
        "vat": vat,
        "sale_count": sale_count,
        "return_count": return_count,
        "credit_count": credit_count,
        "movements": moves,
        "cash_sales": cash_sales,
        "expected_cash": expected_cash,
    }


# ---------------------------------------------------------------------------
# whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_shift_state(terminal: str):
    """Current shift (if any) for the terminal, with live totals."""
    shift = _get_open_shift(terminal)
    if not shift:
        return {"open": False}
    summary = _shift_summary(shift)
    if not _is_manager():
        summary = _blind(summary)
    return {"open": True, "summary": summary, "is_manager": _is_manager()}


_MANAGER_ROLES = ("System Manager", "AlphaX POS Manager", "AlphaX POS Supervisor")


def _is_manager() -> bool:
    return bool(set(frappe.get_roles()) & set(_MANAGER_ROLES))


@frappe.whitelist()
def open_shift(terminal: str, opening_cash, notes: str | None = None, for_user: str | None = None):
    if not frappe.db.exists("AlphaX POS Terminal", terminal):
        frappe.throw(_("Unknown terminal"))
    if _get_open_shift(terminal):
        frappe.throw(_("A shift is already open on this terminal. Close it first."))
    opening_cash = flt(opening_cash)
    if opening_cash < 0:
        frappe.throw(_("Opening float cannot be negative"))

    # Supervisor override: a manager may open the shift ON BEHALF of a
    # cashier (e.g. cashier's account has no desk access, or shift
    # handover). The shift OWNER becomes the cashier; the audit trail
    # (owner/creation of the shift doc) still records who performed it.
    shift_user = frappe.session.user
    if for_user and for_user != frappe.session.user:
        if not _is_manager():
            frappe.throw(_("Only managers can open a shift on behalf of another user"))
        if not frappe.db.exists("User", for_user):
            frappe.throw(_("Unknown user: {0}").format(for_user))
        shift_user = for_user

    # Business date: the trading day this shift (and every sale in it)
    # belongs to. Restaurants trade past midnight — a 9 PM–1 AM shift is
    # ONE trading day, and 24h sites run 3 shifts against the same date.
    # Rule: first shift after a Day Close starts a fresh trading day
    # (today); until Day Close runs, every subsequent shift open — even
    # after midnight — inherits the terminal's current business date.
    _enforce_opening_time(terminal)
    business_date = frappe.db.get_value(
        "AlphaX POS Terminal", terminal, "current_business_date"
    ) or nowdate()
    frappe.db.set_value(
        "AlphaX POS Terminal", terminal, "current_business_date", business_date,
        update_modified=False,
    )

    doc = frappe.get_doc({
        "doctype": "AlphaX POS Shift",
        "pos_terminal": terminal,
        "user": shift_user,
        "status": "Open",
        "business_date": business_date,
        "opened_on": now_datetime(),
        "opening_cash": opening_cash,
        "notes": notes,
    }).insert(ignore_permissions=False)
    _bust_boot_cache(terminal)
    return {"open": True, "summary": _shift_summary(doc)}


@frappe.whitelist()
def record_cash_movement(shift: str, movement_type: str, amount, remarks: str | None = None):
    if movement_type not in MOVEMENT_TYPES:
        frappe.throw(_("Invalid movement type"))
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Amount must be positive"))
    sh = frappe.get_doc("AlphaX POS Shift", shift)
    if sh.status != "Open":
        frappe.throw(_("Shift is not open"))
    frappe.get_doc({
        "doctype": "AlphaX POS Cash Movement",
        "shift": shift,
        "pos_terminal": sh.pos_terminal,
        "user": frappe.session.user,
        "movement_type": movement_type,
        "amount": amount,
        "remarks": remarks,
        "posting_datetime": now_datetime(),
    }).insert(ignore_permissions=False)
    return {"summary": _shift_summary(sh)}


@frappe.whitelist()
def x_report(shift: str):
    if not _is_manager():
        frappe.throw(_("X report is available to supervisors only."))
    """Mid-shift read. Never mutates, never resets — print as often as
    you like."""
    sh = frappe.get_doc("AlphaX POS Shift", shift)
    return _shift_summary(sh)


@frappe.whitelist()
def close_shift(shift: str, counted_cash, notes: str | None = None,
                handover_to: str | None = None):
    """Blind close: the cashier's count arrives BEFORE the expected
    figure is revealed. Returns the full Z payload including variance."""
    sh = frappe.get_doc("AlphaX POS Shift", shift)
    if sh.status != "Open":
        frappe.throw(_("Shift is not open"))
    if sh.user != frappe.session.user and not _is_manager():
        frappe.throw(_("Only managers can close another cashier's shift"))

    counted = flt(counted_cash)
    sh.closed_on = now_datetime()
    summary = _shift_summary(sh)

    sh.closing_cash = counted
    sh.expected_cash = summary["expected_cash"]
    sh.variance = counted - summary["expected_cash"]
    sh.status = "Closed"
    if notes:
        sh.notes = (sh.notes + "\n" if sh.notes else "") + notes
    sh.save(ignore_permissions=False)

    summary.update({
        "status": "Closed",
        "closed_on": sh.closed_on,
        "counted_cash": counted,
        "variance": sh.variance,
    })

    # Emailed close report — best effort, never blocks the drawer.
    try:
        from alphax_pos_suite.alphax_pos_suite.reporting.close_reports import (
            build_shift_close_context, maybe_send_close_email,
        )
        ctx = build_shift_close_context(sh)
        maybe_send_close_email("Shift", sh.doctype, sh.name, ctx)
    except Exception:
        frappe.log_error(
            title="AlphaX POS: shift close email failed (non-fatal)",
            message=frappe.get_traceback(),
        )

    return summary


@frappe.whitelist()
def day_close(terminal: str, posting_date: str | None = None):
    """Roll every CLOSED, un-rolled shift of the terminal's trading day
    into an AlphaX POS Day Close and return its consolidated summary.

    The trading day is the shifts' business_date, NOT the calendar date
    of the clock: a day close run at 1 AM on the 13th closes the 12th's
    trade, including the post-midnight sales. On success the terminal's
    current_business_date is cleared — the next shift open starts a
    fresh trading day.
    """
    if frappe.session.user != "Administrator" and not _is_manager() and not frappe.flags.in_scheduler_dayclose:
        frappe.throw(_("Day close is a supervisor operation. Ask a manager to run it."))
    posting_date = posting_date or frappe.db.get_value(
        "AlphaX POS Terminal", terminal, "current_business_date"
    ) or nowdate()

    if _get_open_shift(terminal):
        frappe.throw(_("Close the open shift before running day close."))

    shifts = frappe.get_all(
        "AlphaX POS Shift",
        filters={
            "pos_terminal": terminal,
            "status": "Closed",
            "day_close_id": ["in", ["", None]],
            "business_date": posting_date,
        },
        fields=["name"],
        order_by="opened_on asc",
    )
    if not shifts:
        # Legacy shifts (pre-business-date builds) have no business_date;
        # fall back to the old calendar-window match so historic days can
        # still be closed after upgrading.
        shifts = frappe.get_all(
            "AlphaX POS Shift",
            filters={
                "pos_terminal": terminal,
                "status": "Closed",
                "day_close_id": ["in", ["", None]],
                "business_date": ["in", ["", None]],
                "opened_on": ["between", [f"{posting_date} 00:00:00", f"{posting_date} 23:59:59"]],
            },
            fields=["name"],
            order_by="opened_on asc",
        )
    if not shifts:
        frappe.throw(_("No closed shifts found for trading day {0}").format(posting_date))

    # Terminal has no company column (field report: day close failed with
    # 1054 Unknown column 'company'). Resolve through the chain that
    # always exists: POS Profile.company → outlet's company → site default.
    company = None
    profile = frappe.db.get_value("AlphaX POS Terminal", terminal, "pos_profile")
    if profile:
        company = frappe.db.get_value("POS Profile", profile, "company")
    if not company:
        company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
            "Company", {}, "name"
        )
    dc = frappe.get_doc({
        "doctype": "AlphaX POS Day Close",
        "company": company,
        "pos_terminal": terminal,
        "data_source": _source_for(terminal),
        "posting_date": posting_date,
    }).insert(ignore_permissions=False)

    # Aggregate the closed shifts' stored figures.
    totals = {"sales": 0.0, "returns": 0.0, "expected": 0.0,
              "counted": 0.0, "variance": 0.0, "vat": 0.0}
    per_shift = []
    for row in shifts:
        sh = frappe.get_doc("AlphaX POS Shift", row.name)
        s = _shift_summary(sh)
        totals["sales"] += s["gross_sales"]
        totals["returns"] += s["returns"]
        totals["vat"] += flt(s.get("vat"))
        totals["expected"] += flt(sh.expected_cash)
        totals["counted"] += flt(sh.closing_cash)
        totals["variance"] += flt(sh.variance)
        per_shift.append({
            "shift": sh.name, "user": sh.user,
            "opened_on": sh.opened_on, "closed_on": sh.closed_on,
            "net_sales": s["net_sales"], "expected_cash": sh.expected_cash,
            "counted_cash": sh.closing_cash, "variance": sh.variance,
        })
        sh.db_set("day_close_id", dc.name, update_modified=False)

    dc.sales_value = totals["sales"]
    dc.return_value = totals["returns"]
    dc.net_sales = totals["sales"] - totals["returns"]
    dc.vat_amount = totals["vat"]
    dc.cash_total = totals["counted"]
    dc.variance = totals["variance"]
    dc.save(ignore_permissions=False)

    # Trading day is closed: clear the terminal's business date so the
    # next shift open starts a fresh one (naturally handles overnight
    # closes, closed-on-Friday gaps, and multi-day misses alike).
    frappe.db.set_value(
        "AlphaX POS Terminal", terminal, "current_business_date", None,
        update_modified=False,
    )
    _bust_boot_cache(terminal)

    shift_summaries = []
    for sh in shifts:
        try:
            shift_summaries.append(_shift_summary(frappe.get_doc("AlphaX POS Shift", sh.name)))
        except Exception:
            pass
    from alphax_pos_suite.alphax_pos_suite.pos.notify import notify_day_close
    notify_day_close(dc, shift_summaries, _outlet_for_terminal(terminal))

    try:
        from alphax_pos_suite.alphax_pos_suite.reporting.close_reports import (
            build_day_close_context, maybe_send_close_email,
        )
        ctx = build_day_close_context(dc)
        maybe_send_close_email("Day", dc.doctype, dc.name, ctx)
    except Exception:
        frappe.log_error(
            title="AlphaX POS: day close email failed (non-fatal)",
            message=frappe.get_traceback(),
        )

    return {
        "day_close": dc.name,
        "posting_date": str(posting_date),
        "terminal": terminal,
        "shifts": per_shift,
        "net_sales": totals["sales"] - totals["returns"],
        "vat_amount": totals["vat"],
        "counted_cash": totals["counted"],
        "variance": totals["variance"],
        **totals,
    }


def _blind(summary: dict) -> dict:
    """Blind-close view: cashiers count the drawer without seeing what
    the system expects — showing expected/net invites 'adjusting' the
    count to match. Item history and reprint stay available; totals,
    expectations, and variance are supervisor information."""
    hidden = {
        "net_sales", "gross", "returns", "discount", "vat", "by_mop",
        "expected_cash", "variance", "credit_total", "payments",
        "sales_value",
    }
    return {k: v for k, v in summary.items() if k not in hidden}


def _outlet_for_terminal(terminal: str):
    try:
        from alphax_pos_suite.alphax_pos_suite.boot.api import _resolve_outlet_for_terminal
        t = frappe.get_cached_doc("AlphaX POS Terminal", terminal)
        return _resolve_outlet_for_terminal(t)
    except Exception:
        return None


def _store_hours(terminal: str):
    outlet = _outlet_for_terminal(terminal)
    if not outlet:
        return None
    return frappe.db.get_value(
        "AlphaX POS Outlet", outlet,
        ["opening_time", "enforce_opening_time", "closing_time",
         "enforce_closing_time", "closing_grace_minutes"],
        as_dict=True,
    )


def _enforce_opening_time(terminal: str):
    h = _store_hours(terminal)
    if not h or not h.enforce_opening_time or not h.opening_time:
        return
    now_t = now_datetime().time()
    open_t = (frappe.utils.get_time(h.opening_time)
              if isinstance(h.opening_time, str) else h.opening_time)
    if hasattr(open_t, "total_seconds"):  # timedelta from DB
        open_t = (frappe.utils.get_datetime("2000-01-01") + open_t).time()
    if now_t < open_t:
        frappe.throw(
            _("The store opens at {0}. Shifts cannot be opened earlier "
              "(Store Hours are enforced on the outlet).").format(str(open_t)[:5])
        )


def enforce_closing_time():
    """Scheduler (every 5 minutes): closing-time enforcement.

    For each outlet with enforce_closing_time on, past closing +
    grace: any open shift on the outlet's terminals is auto-closed
    with its OPENING float + recorded cash movements as the declared
    count, flagged for recount — the system never invents a counted
    figure. If the terminal's trigger is "Auto: At Closing Time", day
    close follows. The register additionally blocks NEW sales past
    closing client-side; the sale in progress always finishes.
    """
    now = now_datetime()
    outlets = frappe.get_all(
        "AlphaX POS Outlet",
        filters={"enforce_closing_time": 1},
        fields=["name", "closing_time", "closing_grace_minutes"],
    )
    for o in outlets:
        if not o.closing_time:
            continue
        close_t = o.closing_time
        if hasattr(close_t, "total_seconds"):
            close_t = (frappe.utils.get_datetime("2000-01-01") + close_t).time()
        elif isinstance(close_t, str):
            close_t = frappe.utils.get_time(close_t)
        deadline = frappe.utils.get_datetime(f"{now.date()} {close_t}")
        deadline = frappe.utils.add_to_date(deadline, minutes=o.closing_grace_minutes or 0)
        if now < deadline:
            continue
        terminals = frappe.get_all(
            "AlphaX POS Terminal", filters={"pos_outlet": ["in", [o.name]]}, pluck="name"
        ) or frappe.get_all("AlphaX POS Terminal", pluck="name")
        for terminal in terminals:
            shift = _get_open_shift(terminal)
            if not shift:
                # No open shift: maybe day close is still pending for the trigger
                _maybe_time_dayclose(terminal)
                continue
            # Only close shifts belonging to TODAY's trading window —
            # never touch a shift opened after midnight for a business
            # day whose closing time hasn't come yet.
            try:
                doc = frappe.get_doc("AlphaX POS Shift", shift.name)
                movements = _movement_totals(doc.name)
                declared = flt(doc.opening_cash) + flt(movements.get("in")) - flt(movements.get("out"))
                doc.status = "Closed"
                doc.closing_cash = declared
                doc.closed_on = now_datetime()
                doc.notes = ((doc.notes or "") +
                             "\n[AUTO-CLOSED at store closing time — counted cash NOT declared "
                             "by cashier; figure is float+movements. RECOUNT REQUIRED.]").strip()
                doc.save(ignore_permissions=True)
                outlet = _outlet_for_terminal(terminal)
                from alphax_pos_suite.alphax_pos_suite.pos.notify import notify_shift_close
                notify_shift_close({**_shift_summary(doc), "terminal": terminal,
                                    "counted_cash": declared,
                                    "auto_closed": True}, outlet)
            except Exception:
                frappe.log_error(title="AlphaX POS: closing-time shift auto-close failed",
                                 message=frappe.get_traceback())
                continue
            _maybe_time_dayclose(terminal)


def _maybe_time_dayclose(terminal: str):
    if frappe.db.get_value("AlphaX POS Terminal", terminal, "day_close_trigger") != "Auto: At Closing Time":
        return
    bd = frappe.db.get_value("AlphaX POS Terminal", terminal, "current_business_date")
    if not bd:
        return  # already closed
    if _get_open_shift(terminal):
        return  # a shift is still open (mid-grace); next scheduler pass
    try:
        frappe.flags.in_scheduler_dayclose = True
        day_close(terminal, str(bd))
    except Exception:
        frappe.log_error(title="AlphaX POS: closing-time day close failed",
                         message=frappe.get_traceback())
    finally:
        frappe.flags.in_scheduler_dayclose = False
