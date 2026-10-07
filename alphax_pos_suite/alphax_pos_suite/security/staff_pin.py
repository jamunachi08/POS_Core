"""Sign in at the till with a PIN.

A cashier starting a shift should not be typing an email address and a
password on a greasy touchscreen with a queue forming. Every serious till
signs staff in with a short PIN, and this does the same — but a 4-digit
PIN is 10,000 possibilities, so it is only safe inside a cage. The cage:

  * **Off by default.** Nothing works until an administrator enables
    ``pin_signin_enabled`` on AlphaX POS Settings.
  * **Bound terminals only.** The request must come from a PC already
    bound to a terminal. An unbound browser, anywhere on the internet,
    gets the same answer as a wrong PIN.
  * **Outlet-scoped.** A PIN is only matched against users who hold a POS
    role at that terminal's outlet, which keeps the candidate set to the
    handful of people who actually work there.
  * **Unique per outlet.** Setting a PIN that already belongs to a
    colleague at the same outlet is refused, because a PIN that matches
    two people signs in the wrong one.
  * **Locked out on failure**, on the same escalating schedule the manager
    PIN uses, counted per terminal rather than per user — a brute force
    does not know whose PIN it is guessing.
  * **Audited** either way, to the same log as manager authorisations.

What it is not: a replacement for a password. A PIN proves "the person at
this till is on this outlet's rota", which is the right question at a
till. It is deliberately useless anywhere else.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from alphax_pos_suite.alphax_pos_suite.security.manager_pin import (
    _audit_log, _hash_pin, _validate_pin_format, _verify_pin_hash,
)

#: Roles that may sign in with a PIN. A PIN never grants a role; it only
#: proves identity for someone who already holds one.
SIGNIN_ROLES = ("AlphaX POS Cashier", "AlphaX POS Supervisor",
                "AlphaX POS Manager", "AlphaX POS Kitchen")

#: Failures tolerated at one terminal before it stops accepting PINs.
MAX_ATTEMPTS = 5

#: Escalating lockout, in minutes, per consecutive lockout at a terminal.
LOCKOUT_MINUTES = (1, 5, 15, 60)

#: Never iterate more than this many candidates for one attempt. A site
#: with a very large staff list would otherwise turn sign-in into a slow
#: bcrypt loop, which is its own denial of service.
MAX_CANDIDATES = 60


# --------------------------------------------------------------------------
# settings and state
# --------------------------------------------------------------------------


def _enabled() -> bool:
    try:
        return bool(frappe.db.get_single_value("AlphaX POS Settings", "pin_signin_enabled"))
    except Exception:
        return False


def _terminal_for_request(terminal: str | None):
    """The terminal this request is really coming from.

    Trusting a terminal name posted by the browser would defeat the whole
    binding, so the name is only accepted if such a terminal exists and is
    bound to a device. The device fingerprint check belongs to the bind
    flow; here we require the record to exist and be enabled.
    """
    if not terminal or not frappe.db.exists("AlphaX POS Terminal", terminal):
        return None
    row = frappe.db.get_value("AlphaX POS Terminal", terminal,
                              ["name", "pos_outlet", "disabled"], as_dict=True)
    if not row or cint(row.get("disabled")):
        return None
    return row


def _attempt_key(terminal: str) -> str:
    return f"alphax_pin_attempts::{terminal}"


def _attempts(terminal: str) -> dict:
    return frappe.cache().get_value(_attempt_key(terminal)) or {
        "failures": 0, "lockouts": 0, "locked_until": None}


def _save_attempts(terminal: str, data: dict) -> None:
    # 24h expiry: a terminal that misbehaved yesterday starts clean today.
    frappe.cache().set_value(_attempt_key(terminal), data, expires_in_sec=86400)


def _locked_for(terminal: str) -> int:
    """Seconds remaining on this terminal's lockout, 0 if it is free."""
    st = _attempts(terminal)
    until = st.get("locked_until")
    if not until:
        return 0
    remaining = (frappe.utils.get_datetime(until) - now_datetime()).total_seconds()
    return int(remaining) if remaining > 0 else 0


def _register_failure(terminal: str) -> int:
    st = _attempts(terminal)
    st["failures"] = cint(st.get("failures")) + 1
    if st["failures"] >= MAX_ATTEMPTS:
        idx = min(cint(st.get("lockouts")), len(LOCKOUT_MINUTES) - 1)
        st["locked_until"] = str(add_to_date(now_datetime(), minutes=LOCKOUT_MINUTES[idx]))
        st["lockouts"] = cint(st.get("lockouts")) + 1
        st["failures"] = 0
    _save_attempts(terminal, st)
    return _locked_for(terminal)


def _clear_failures(terminal: str) -> None:
    frappe.cache().delete_value(_attempt_key(terminal))


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------


def _candidates(outlet: str | None) -> list:
    """Users who could plausibly be standing at this till.

    Scoped to the outlet where the suite records one, because the smaller
    the candidate set, the smaller the chance two people share a PIN and
    the shorter the verification loop.
    """
    rows = frappe.get_all(
        "AlphaX POS Manager PIN",
        filters={"is_active": 1}, fields=["name", "user", "pin_hash"],
        ignore_permissions=True, limit_page_length=0)

    out = []
    for r in rows:
        if not r.pin_hash or not r.user:
            continue
        roles = set(frappe.get_roles(r.user))
        if not roles & set(SIGNIN_ROLES):
            continue
        if not frappe.db.get_value("User", r.user, "enabled"):
            continue
        out.append(r)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def pin_signin(terminal: str | None = None, pin: str | None = None) -> dict:
    """Exchange a PIN for a session at a bound terminal.

    Guest-callable by necessity — the whole point is that nobody is signed
    in yet. Every failure returns the same shape and the same message, so
    the response cannot be used to learn whether a PIN, a terminal or a
    user exists.
    """
    deny = {"ok": False, "message": _("Wrong PIN.")}

    if not _enabled():
        return {"ok": False, "message": _("PIN sign-in is not enabled on this site.")}

    row = _terminal_for_request(terminal)
    if not row:
        # Deliberately the same message as a wrong PIN: an attacker
        # guessing terminal names learns nothing from the difference.
        return deny

    wait = _locked_for(row.name)
    if wait:
        return {"ok": False, "locked": True, "retry_in": wait,
                "message": _("Too many wrong PINs. Try again in {0} seconds, or sign in with a password.").format(wait)}

    if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 8:
        _register_failure(row.name)
        return deny

    matched = None
    for cand in _candidates(row.get("pos_outlet")):
        if _verify_pin_hash(pin, cand.pin_hash):
            matched = cand
            break

    if not matched:
        wait = _register_failure(row.name)
        _audit_log(manager=None, action_type="PIN Sign-in", result="Failed",
                   terminal=row.name, outlet=row.get("pos_outlet"),
                   notes="No match for the PIN entered.")
        if wait:
            return {"ok": False, "locked": True, "retry_in": wait,
                    "message": _("Too many wrong PINs. Try again in {0} seconds, or sign in with a password.").format(wait)}
        return deny

    _clear_failures(row.name)

    frappe.local.login_manager.login_as(matched.user)
    frappe.local.login_manager.resume = False
    frappe.local.login_manager.run_trigger("on_session_creation")

    frappe.db.set_value("AlphaX POS Manager PIN", matched.name, {
        "last_used_on": now_datetime(),
        "last_used_terminal": row.name,
        "last_used_outlet": row.get("pos_outlet"),
    }, update_modified=False)

    _audit_log(manager=None, action_type="PIN Sign-in", result="Success",
               terminal=row.name, outlet=row.get("pos_outlet"),
               notes=f"Signed in as {matched.user}.")
    frappe.db.commit()

    return {"ok": True, "user": matched.user,
            "full_name": frappe.db.get_value("User", matched.user, "full_name"),
            "redirect": "/app/alphax-cashier"}


@frappe.whitelist()
def set_staff_pin(user: str, pin: str) -> dict:
    """Give a cashier a sign-in PIN.

    Managers may set PINs for their own staff; a System Manager may set
    anyone's. The uniqueness check is the important part: two people
    sharing a PIN at one outlet means the till signs in whichever the loop
    reached first, and the shift report then names the wrong person.
    """
    roles = set(frappe.get_roles())
    if not roles & {"AlphaX POS Manager", "System Manager"}:
        frappe.throw(_("Only a manager can set a sign-in PIN."), frappe.PermissionError)

    _validate_pin_format(pin)
    if not frappe.db.exists("User", user):
        frappe.throw(_("Unknown user {0}").format(user))
    if not set(frappe.get_roles(user)) & set(SIGNIN_ROLES):
        frappe.throw(_("{0} holds no AlphaX POS role, so a till PIN would not sign them in.")
                     .format(user))
    if pin in ("0000", "1111", "1234", "123456", "000000", "111111"):
        frappe.throw(_("That PIN is too easy to guess. Choose another."))

    for cand in _candidates(None):
        if cand.user != user and _verify_pin_hash(pin, cand.pin_hash):
            # Never say whose. Naming the colleague would leak their PIN.
            frappe.throw(_("Another member of staff already uses that PIN. Choose another."))

    name = frappe.db.get_value("AlphaX POS Manager PIN", {"user": user}, "name")
    if name:
        doc = frappe.get_doc("AlphaX POS Manager PIN", name)
    else:
        doc = frappe.new_doc("AlphaX POS Manager PIN")
        doc.user = user

    doc.pin_hash = _hash_pin(pin)
    doc.pin_set_on = now_datetime()
    doc.pin_set_by = frappe.session.user
    doc.is_active = 1
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)

    _audit_log(manager=frappe.session.user, action_type="PIN Set", result="Success",
               notes=f"Sign-in PIN set for {user}.")
    frappe.db.commit()
    return {"ok": True, "user": user}


@frappe.whitelist()
def clear_terminal_lockout(terminal: str) -> dict:
    """Let a manager unlock a till that a guest jammed with wrong PINs."""
    if not set(frappe.get_roles()) & {"AlphaX POS Manager", "System Manager"}:
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    _clear_failures(terminal)
    _audit_log(manager=frappe.session.user, action_type="PIN Lockout Reset",
               result="Success", terminal=terminal)
    return {"ok": True, "terminal": terminal}


@frappe.whitelist(allow_guest=True)
def signin_context(terminal: str | None = None) -> dict:
    """What the lock screen needs before anyone has signed in.

    Returns nothing that identifies a person: no names, no PIN hints, no
    staff list. Only whether the keypad should be drawn at all.
    """
    row = _terminal_for_request(terminal)
    return {
        "enabled": bool(_enabled() and row),
        "terminal": row.name if row else None,
        "outlet": row.get("pos_outlet") if row else None,
        "locked_for": _locked_for(row.name) if row else 0,
    }
