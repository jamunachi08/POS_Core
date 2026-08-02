"""
AlphaX POS — Manager PIN security.

This module is the single source of truth for manager-PIN handling.
It exposes whitelisted endpoints called by the cashier UI and the
admin tooling.

Security model
==============

PIN storage
-----------
PINs are bcrypt-hashed (12 rounds) and stored in the `pin_hash` field
of `AlphaX POS Manager PIN`. The plaintext PIN is never stored or
logged. The verify path takes the plain PIN over HTTPS, hashes it
on the server, and compares to the stored hash.

Lockout policy (exponential backoff)
------------------------------------
Five wrong PIN attempts in a row trigger a lockout. The lockout
duration escalates each time the same manager hits this limit
within a single calendar day:

    Lockout #1:    5 minutes
    Lockout #2:   30 minutes
    Lockout #3:    4 hours
    Lockout #4:   24 hours  + admin alert email
    Lockout #5+:  admin reset required (lockout never auto-clears)

The "in a row" counter (`failed_attempts_in_window`) resets to 0
on a successful PIN entry. The "today" counter
(`lockout_count_today`) resets at midnight local time via a daily
scheduled task.

Audit
-----
Every authorization attempt — success or failure — appends a row to
`AlphaX POS Manager Authorization Log`. The log is append-only
(write/create/delete denied to all users in the doctype JSON), so a
compromised manager account cannot scrub its own audit trail through
the Frappe UI.

Rate limiting
-------------
The verify endpoint is rate-limited to 10 calls per 5 minutes per IP
via an in-house cache-based rate limiter. This bounds brute-force attempts even
before the per-account lockout kicks in.
"""
from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import (
    add_to_date,
    cint,
    get_datetime,
    get_request_session,
    now_datetime,
)


# ---------------------------------------------------------------------- *
# Constants
# ---------------------------------------------------------------------- *

#: Min/max allowed PIN length. 4 digits = 10,000 combinations; 6 = 1,000,000.
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 6

#: How many wrong attempts before triggering a lockout.
LOCKOUT_AFTER_ATTEMPTS = 5

#: Lockout duration schedule (in minutes). Index 0 = lockout #1.
#: Past the end of this list, admin reset is required.
LOCKOUT_SCHEDULE_MINUTES = [
    5,           # Lockout #1: 5 minutes
    30,          # Lockout #2: 30 minutes
    4 * 60,      # Lockout #3: 4 hours
    24 * 60,     # Lockout #4: 24 hours + admin alert
]

#: Roles that count as "manager" for the purpose of cashier station
#: authorization. System Manager always wins.
MANAGER_ROLES = ("AlphaX POS Manager", "System Manager")


# ---------------------------------------------------------------------- *
# Internal helpers
# ---------------------------------------------------------------------- *

def _hash_pin(pin: str) -> str:
    """Hash a PIN with bcrypt. Returns the hash string."""
    from passlib.hash import bcrypt
    return bcrypt.using(rounds=12).hash(pin)


def _verify_pin_hash(pin: str, stored_hash: str) -> bool:
    """Compare a plain PIN to a stored bcrypt hash."""
    if not pin or not stored_hash:
        return False
    from passlib.hash import bcrypt
    try:
        return bcrypt.verify(pin, stored_hash)
    except Exception:
        return False


def _validate_pin_format(pin: str) -> None:
    """Raise if the PIN doesn't meet our length/digit requirements."""
    if not isinstance(pin, str):
        frappe.throw(_("PIN must be a string of digits."))
    if not re.fullmatch(r"\d{%d,%d}" % (PIN_MIN_LENGTH, PIN_MAX_LENGTH), pin):
        frappe.throw(
            _("PIN must be {0} to {1} digits (no letters or symbols).").format(
                PIN_MIN_LENGTH, PIN_MAX_LENGTH
            )
        )


def _get_request_metadata():
    """Best-effort capture of IP and user-agent from the request."""
    ip = ""
    ua = ""
    try:
        if frappe.local.request:
            ip = (
                frappe.local.request.headers.get("X-Forwarded-For", "")
                or frappe.local.request.remote_addr
                or ""
            )
            # X-Forwarded-For can be a comma-separated list; take the first
            if "," in ip:
                ip = ip.split(",")[0].strip()
            ua = frappe.local.request.headers.get("User-Agent", "")[:500]
    except Exception:
        pass
    return ip, ua


def _audit_log(
    *,
    manager: str | None,
    action_type: str,
    result: str,
    terminal: str | None = None,
    outlet: str | None = None,
    notes: str = "",
) -> None:
    """Append a row to the authorization audit log. Best-effort —
    we never raise out of audit logging because that would break
    the actual operation."""
    try:
        ip, ua = _get_request_metadata()
        frappe.get_doc({
            "doctype": "AlphaX POS Manager Authorization Log",
            "manager": manager,
            "cashier_user": frappe.session.user
                if frappe.session.user != "Guest" else None,
            "action_type": action_type,
            "result": result,
            "terminal": terminal or "",
            "outlet": outlet or "",
            "ip_address": ip,
            "user_agent": ua,
            "notes": notes or "",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="AlphaX POS: failed to write authorization audit log",
            message=frappe.get_traceback(),
        )


def _resolve_lockout_minutes(lockout_count_today: int) -> int | None:
    """Given how many lockouts the manager has triggered today,
    return the next lockout duration in minutes, or None if we've
    exceeded the schedule (= admin reset required).
    """
    idx = lockout_count_today  # next lockout is the (count+1)th, 0-indexed
    if idx >= len(LOCKOUT_SCHEDULE_MINUTES):
        return None
    return LOCKOUT_SCHEDULE_MINUTES[idx]


def _user_is_manager(user: str) -> bool:
    if not user or user == "Guest":
        return False
    roles = set(frappe.get_roles(user))
    return any(r in roles for r in MANAGER_ROLES)


# ---------------------------------------------------------------------- *
# Public API: set / reset
# ---------------------------------------------------------------------- *

@frappe.whitelist()
def set_manager_pin(user: str, pin: str) -> dict:
    """Set or reset the PIN for a manager.

    Restricted to System Manager. Validates PIN format, hashes the PIN,
    upserts the AlphaX POS Manager PIN record, and writes an audit log
    entry. Resets any existing lockout state.

    Parameters
    ----------
    user : str
        The User name (typically the user's email).
    pin : str
        4-6 digit PIN (digits only).

    Returns
    -------
    dict
        {ok: True, pin_record: <name>}
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager can set or reset manager PINs."))

    _validate_pin_format(pin)

    if not frappe.db.exists("User", user):
        frappe.throw(_("User {0} does not exist.").format(user))

    if not _user_is_manager(user):
        frappe.throw(
            _("User {0} does not have a manager role. Assign 'AlphaX POS Manager' "
              "or 'System Manager' first, then set their PIN.").format(user)
        )

    pin_hash = _hash_pin(pin)
    now = now_datetime()

    if frappe.db.exists("AlphaX POS Manager PIN", user):
        doc = frappe.get_doc("AlphaX POS Manager PIN", user)
        doc.pin_hash = pin_hash
        doc.pin_set_on = now
        doc.pin_set_by = frappe.session.user
        doc.is_active = 1
        # Reset lockout state on PIN change
        doc.failed_attempts_in_window = 0
        doc.lockout_count_today = 0
        doc.locked_until = None
        doc.last_failed_at = None
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "AlphaX POS Manager PIN",
            "user": user,
            "pin_hash": pin_hash,
            "pin_set_on": now,
            "pin_set_by": frappe.session.user,
            "is_active": 1,
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()

    _audit_log(
        manager=user,
        action_type="PIN Set",
        result="Success",
        notes=f"PIN set/reset by {frappe.session.user}",
    )

    return {"ok": True, "pin_record": doc.name}


@frappe.whitelist()
def reset_manager_lockout(user: str) -> dict:
    """Manually clear all lockout state for a manager.

    Restricted to System Manager. Used when a manager hit a 24-hour
    or admin-only lockout and you want to let them back in early.
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager can reset manager lockouts."))

    if not frappe.db.exists("AlphaX POS Manager PIN", user):
        frappe.throw(_("No PIN record exists for {0}.").format(user))

    doc = frappe.get_doc("AlphaX POS Manager PIN", user)
    doc.failed_attempts_in_window = 0
    doc.lockout_count_today = 0
    doc.locked_until = None
    doc.last_failed_at = None
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _audit_log(
        manager=user,
        action_type="Other",
        result="Success",
        notes=f"Lockout manually cleared by {frappe.session.user}",
    )

    return {"ok": True}


# ---------------------------------------------------------------------- *
# Public API: verify (the hot path)
# ---------------------------------------------------------------------- *

@frappe.whitelist(allow_guest=False)
def verify_manager_pin(
    user: str,
    pin: str,
    action_type: str = "Verify Only",
    terminal: str | None = None,
    outlet: str | None = None,
) -> dict:
    """Verify a manager's PIN.

    Two-step authentication: the manager identifies themselves with their
    User name (typically email), then types their PIN. This lets us:

    - Track failed attempts per-manager (enabling exponential lockout)
    - Show better audit logs ("Khalid tried 5 times and failed" rather
      than "someone tried PIN 1234")
    - Reject quickly when the user doesn't have a manager role, without
      revealing whether the PIN is correct

    Security note: we use the SAME generic "Incorrect credentials"
    error message regardless of whether the user doesn't exist, isn't
    a manager, has no PIN set, or simply mistyped. This prevents an
    attacker from enumerating valid manager users.

    Parameters
    ----------
    user : str
        The manager's User name (email).
    pin : str
        The PIN entered.
    action_type : str
        What the manager intends to do (logged for audit).
    terminal, outlet : str, optional
        Context for the audit log.

    Returns
    -------
    dict
        On success:  {authorized: True, manager: <user>, manager_name: <full name>}
        On failure:  {authorized: False, message: <generic>, locked_until: <iso>?}
    """
    # All failure paths return this exact response. Don't leak which
    # of the many possible reasons we're rejecting.
    GENERIC_FAILURE = {
        "authorized": False,
        "message": _("Incorrect credentials."),
    }

    # In-house IP-based rate limit (replaces @frappe.rate_limit which is
    # not available in all Frappe versions). 10 attempts per 5 minutes
    # per IP. Same effect as the decorator, but uses the cache directly.
    try:
        ip = frappe.local.request_ip if hasattr(frappe.local, "request_ip") else "unknown"
        rl_key = f"alphax_pin_rate:{ip}"
        cache = frappe.cache()
        count = cache.get_value(rl_key) or 0
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        if count >= 10:
            _audit_log(
                manager=user if isinstance(user, str) else None,
                action_type=action_type, result="Rate Limited",
                terminal=terminal, outlet=outlet,
                notes=f"IP {ip} exceeded 10 attempts in 5 min",
            )
            return GENERIC_FAILURE
        # Increment with 5-minute expiry
        cache.set_value(rl_key, count + 1, expires_in_sec=5 * 60)
    except Exception:
        # If the cache is unavailable, allow the call through. The
        # per-manager exponential lockout still protects against
        # brute-force on a specific account.
        pass

    # Defensive: PIN format check
    if not isinstance(pin, str) or not pin.isdigit() or len(pin) > PIN_MAX_LENGTH * 2:
        _audit_log(
            manager=user if isinstance(user, str) else None,
            action_type=action_type, result="Wrong PIN",
            terminal=terminal, outlet=outlet,
            notes="Malformed PIN input",
        )
        return GENERIC_FAILURE

    if not isinstance(user, str) or not user:
        _audit_log(
            manager=None, action_type=action_type, result="Manager Not Found",
            terminal=terminal, outlet=outlet,
            notes="No user supplied",
        )
        return GENERIC_FAILURE

    user = user.strip().lower()

    # Does the user exist and have manager role? Don't tell the
    # attacker either way — but we have to short-circuit here so we
    # don't leak via timing.
    if not frappe.db.exists("User", user) or not _user_is_manager(user):
        _audit_log(
            manager=user, action_type=action_type, result="No Manager Role",
            terminal=terminal, outlet=outlet,
        )
        # Burn a constant-ish amount of time to mask timing differences
        # between "no such user" vs "user but no PIN" vs "wrong PIN"
        try:
            from passlib.hash import bcrypt
            bcrypt.using(rounds=12).hash("dummy-timing-mask")
        except Exception:
            pass
        return GENERIC_FAILURE

    # Does the user have a PIN record?
    if not frappe.db.exists("AlphaX POS Manager PIN", user):
        _audit_log(
            manager=user, action_type=action_type, result="Manager Not Found",
            terminal=terminal, outlet=outlet,
            notes="Manager exists but no PIN record",
        )
        try:
            from passlib.hash import bcrypt
            bcrypt.using(rounds=12).hash("dummy-timing-mask")
        except Exception:
            pass
        return GENERIC_FAILURE

    doc = frappe.get_doc("AlphaX POS Manager PIN", user)

    if not doc.is_active:
        _audit_log(
            manager=user, action_type=action_type, result="PIN Inactive",
            terminal=terminal, outlet=outlet,
        )
        return GENERIC_FAILURE

    # Currently locked?
    now = now_datetime()
    if doc.locked_until and get_datetime(doc.locked_until) > now:
        _audit_log(
            manager=user, action_type=action_type, result="Locked Out",
            terminal=terminal, outlet=outlet,
            notes=f"Locked until {doc.locked_until}",
        )
        return {
            "authorized": False,
            "message": _("This account is locked. Try again later."),
            "locked_until": str(doc.locked_until),
        }

    # Verify the PIN.
    if not _verify_pin_hash(pin, doc.pin_hash):
        # Wrong PIN. Increment the counter, possibly trigger a lockout.
        doc.failed_attempts_in_window = (doc.failed_attempts_in_window or 0) + 1
        doc.last_failed_at = now

        triggered_lockout = False
        if doc.failed_attempts_in_window >= LOCKOUT_AFTER_ATTEMPTS:
            # Trigger a lockout. Reset the in-window counter (so the
            # next round of 5 attempts can count fresh after expiry)
            # and increment the today-counter for backoff.
            today_count = (doc.lockout_count_today or 0)
            minutes = _resolve_lockout_minutes(today_count)
            if minutes is None:
                # Past the end of the schedule — admin reset only.
                # We set locked_until very far in the future as a
                # sentinel; admin tooling will clear it.
                doc.locked_until = add_to_date(now, years=10)
                lock_label = "admin reset required"
            else:
                doc.locked_until = add_to_date(now, minutes=minutes)
                lock_label = f"{minutes} minutes"

            doc.lockout_count_today = today_count + 1
            doc.failed_attempts_in_window = 0
            triggered_lockout = True

            # Email alert to System Manager on the 4th lockout (24-hour)
            if doc.lockout_count_today >= 4:
                _alert_system_manager_about_lockout(user, doc.lockout_count_today)

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        if triggered_lockout:
            _audit_log(
                manager=user, action_type="Lockout Triggered", result="Locked Out",
                terminal=terminal, outlet=outlet,
                notes=f"5 wrong PINs in a row; locked for {lock_label} "
                      f"(daily lockout #{doc.lockout_count_today})",
            )
            return {
                "authorized": False,
                "message": _("Too many wrong attempts. Account is now locked."),
                "locked_until": str(doc.locked_until),
            }

        _audit_log(
            manager=user, action_type=action_type, result="Wrong PIN",
            terminal=terminal, outlet=outlet,
            notes=f"Failed attempt {doc.failed_attempts_in_window}/"
                  f"{LOCKOUT_AFTER_ATTEMPTS} in current window",
        )
        return GENERIC_FAILURE

    # Success! Update usage stats, clear failure counter, audit.
    ip, _ua = _get_request_metadata()
    doc.last_used_on = now
    doc.last_used_terminal = terminal or ""
    doc.last_used_outlet = outlet or ""
    doc.last_used_ip = ip
    doc.failed_attempts_in_window = 0
    doc.locked_until = None
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _audit_log(
        manager=user, action_type=action_type, result="Success",
        terminal=terminal, outlet=outlet,
    )

    return {
        "authorized": True,
        "manager": user,
        "manager_name": frappe.db.get_value("User", user, "full_name") or user,
    }


def _alert_system_manager_about_lockout(user: str, lockout_count: int) -> None:
    """Send an email alert when a manager hits a 24-hour or admin-reset lockout.

    Best-effort — we don't raise if email delivery fails.
    """
    try:
        recipients = frappe.get_all(
            "Has Role",
            filters={"role": "System Manager", "parenttype": "User"},
            fields=["parent"],
        )
        emails = [r["parent"] for r in recipients if r.get("parent")]
        # Drop System / Administrator
        emails = [e for e in emails if e not in ("Administrator", "Guest")]
        if not emails:
            return

        frappe.sendmail(
            recipients=emails,
            subject=f"[AlphaX POS] Manager PIN locked: {user}",
            message=(
                f"<p>Manager <b>{user}</b> has been locked out after "
                f"5 wrong PIN attempts in a row.</p>"
                f"<p>This is daily lockout #{lockout_count} for this manager. "
                f"If this is unexpected, it may indicate an attack on the PIN system.</p>"
                f"<p>Review the recent attempts in <b>AlphaX POS Manager Authorization Log</b>.</p>"
                f"<p>To unlock the manager early, go to their <b>AlphaX POS Manager PIN</b> "
                f"record and use the 'Reset Lockout' admin action.</p>"
            ),
            now=False,
            delayed=True,
        )
    except Exception:
        frappe.log_error(
            title="AlphaX POS: failed to send lockout alert email",
            message=frappe.get_traceback(),
        )


@frappe.whitelist()
def log_action(action_type: str, terminal: str | None = None,
               outlet: str | None = None, notes: str = "") -> dict:
    """Append an audit log entry for an action the cashier UI just did.

    The cashier UI calls this AFTER the manager-PIN dialog already
    succeeded, to record what was done with that authorization (bind,
    change, reset). The `verify_manager_pin` endpoint already logged
    the verification itself; this is the follow-up.

    We only allow a small set of action types here, and we don't
    accept arbitrary `result` strings — the result is always Success
    because if the action had failed the cashier would have shown an
    error to the user and not called this.
    """
    allowed = {"Bind Terminal", "Change Terminal", "Reset Station"}
    if action_type not in allowed:
        return {"ok": False}

    _audit_log(
        manager=None,  # we don't have the manager at this point —
                       # the verify call right before us recorded it
        action_type=action_type,
        result="Success",
        terminal=terminal,
        outlet=outlet,
        notes=notes,
    )
    return {"ok": True}


# ---------------------------------------------------------------------- *
# Scheduled task — daily counter reset
# ---------------------------------------------------------------------- *

def reset_daily_counters() -> None:
    """Reset `lockout_count_today` for every PIN at midnight.

    Called by Frappe's scheduler (registered in hooks.py under
    `scheduler_events.daily`).
    """
    try:
        frappe.db.sql("""
            UPDATE `tabAlphaX POS Manager PIN`
            SET `lockout_count_today` = 0,
                `failed_attempts_in_window` = 0
            WHERE `lockout_count_today` > 0
               OR `failed_attempts_in_window` > 0
        """)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="AlphaX POS: failed to reset daily PIN lockout counters",
            message=frappe.get_traceback(),
        )
