"""
AlphaX POS — session scope.

Who is this person, where do they work, and which till are they about to
open? Answered once at login, on the server.

The chain, and why it is in this order:

    login → branch → terminal → POS profile → shift → sell

**Branch before terminal.** A person is employed at a branch; they are not
employed at a till. Assigning users to terminals looks simpler until the
first time somebody covers a shift on the next register along and cannot
sign in. Branch-level assignment survives staff moving around, which they
do constantly.

**Terminal decides the POS Profile, not the person.** The profile carries
the income account, the write-off account, the tender list and the naming
series — it describes the till's accounting, not the operator's identity.
If a person's profile followed them between registers, two cashiers on the
same machine would post the same sale to different accounts, and the
difference would only surface at reconciliation. The user's assignment may
express a *preference*, honoured only when the terminal permits it.

**No picker when there is no choice.** One assignment means no prompt at
all. A picker that always has one button is a daily insult to the person
using it.
"""

from __future__ import annotations

import frappe
from frappe import _

MANAGER_ROLES = ("System Manager", "AlphaX POS Manager")


def _is_manager() -> bool:
    roles = set(frappe.get_roles())
    return any(r in roles for r in MANAGER_ROLES)


def _assignments(user: str) -> list[dict]:
    if not frappe.db.table_exists("AlphaX POS User Assignment"):
        return []
    try:
        return frappe.get_all(
            "AlphaX POS User Assignment",
            filters={"parent": user, "parenttype": "User",
                     "parentfield": "alphax_pos_assignments"},
            fields=["branch", "pos_outlet", "terminal", "pos_profile", "is_default"],
            order_by="is_default desc, idx asc",
        ) or []
    except Exception:
        return []


@frappe.whitelist()
def get_session_scope():
    """Everything the cashier SPA needs to decide what to ask the user.

    Returns `mode`, which is the whole point:

        'auto'    — exactly one place to be. Open it, ask nothing.
        'branch'  — several branches. Show the branch picker.
        'open'    — no assignment at all. Legacy behaviour: every terminal
                    the user can read, as before this release.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"mode": "open", "branches": [], "user": None}

    rows = _assignments(user)
    manager = _is_manager()

    if not rows:
        # Unassigned. Managers and freshly-installed sites must keep
        # working exactly as they did; assignment is an improvement to
        # opt into, never a gate that locks people out on upgrade.
        return {
            "mode": "open",
            "user": user,
            "branches": _all_branches_with_terminals(),
            "can_change": True,
            "note": _("No branch assignment for this user; showing everything."),
        }

    branches = []
    seen = set()
    for r in rows:
        if r["branch"] in seen:
            continue
        seen.add(r["branch"])
        branches.append({
            "branch": r["branch"],
            "label": frappe.db.get_value("Branch", r["branch"], "branch") or r["branch"],
            "outlet": r.get("pos_outlet"),
            "terminal": r.get("terminal"),
            "pos_profile": r.get("pos_profile"),
            "is_default": bool(r.get("is_default")),
            "terminals": _terminals_for(r["branch"], r.get("pos_outlet")),
        })

    default = next((b for b in branches if b["is_default"]), branches[0])
    return {
        "mode": "auto" if len(branches) == 1 else "branch",
        "user": user,
        "branches": branches,
        "default_branch": default["branch"],
        "can_change": manager,
    }


def _terminals_for(branch: str, outlet: str | None = None) -> list[dict]:
    filters = {}
    if outlet:
        filters["pos_outlet"] = outlet
    elif branch:
        outlets = frappe.get_all("AlphaX POS Outlet",
                                 filters={"branch": branch}, pluck="name") or []
        # A terminal may carry the branch directly or inherit it via outlet.
        if outlets:
            filters["pos_outlet"] = ["in", outlets]
        else:
            filters["branch"] = branch

    rows = frappe.get_all(
        "AlphaX POS Terminal", filters=filters,
        fields=["name", "pos_outlet", "pos_profile", "pc_hostname", "last_bound_at"],
        order_by="name asc", limit_page_length=100,
    ) or []
    for r in rows:
        r["label"] = r.get("pc_hostname") or r["name"]
        r["outlet_label"] = frappe.db.get_value(
            "AlphaX POS Outlet", r.get("pos_outlet"), "outlet_name") or r.get("pos_outlet")
    return rows


def _all_branches_with_terminals() -> list[dict]:
    out = []
    for b in frappe.get_all("Branch", fields=["name", "branch"],
                            order_by="name asc", limit_page_length=200):
        terms = _terminals_for(b.name)
        if terms:
            out.append({"branch": b.name, "label": b.branch or b.name,
                        "is_default": False, "terminals": terms})
    return out


@frappe.whitelist()
def resolve_pos_profile(terminal: str):
    """Which POS Profile this session posts under, and why.

    Precedence, deliberately terminal-first:

      1. The user's assigned profile — but only if the terminal lists it
         in Allowed POS Profiles. A preference, not an override.
      2. The terminal's own profile. The normal answer.
      3. The terminal's default allowed profile.

    `reason` is returned so the choice is auditable from the till rather
    than inferred. A cashier asking "why did this post to the wrong
    account" deserves an answer that does not require reading code.
    """
    if not frappe.db.exists("AlphaX POS Terminal", terminal):
        frappe.throw(_("Unknown terminal {0}").format(terminal))

    t = frappe.get_doc("AlphaX POS Terminal", terminal)
    allowed = [r.pos_profile for r in (t.get("allowed_pos_profiles") or [])]

    wanted = None
    for a in _assignments(frappe.session.user):
        if a.get("pos_profile") and (
                not a.get("terminal") or a["terminal"] == terminal):
            wanted = a["pos_profile"]
            break

    if wanted and (not allowed or wanted in allowed):
        return {"pos_profile": wanted, "reason": "user_assignment",
                "detail": _("Your assignment names this profile and the terminal permits it.")}

    if wanted and allowed and wanted not in allowed:
        # Say so rather than silently substituting. Silent substitution of
        # an accounting configuration is how month-end surprises are made.
        return {"pos_profile": t.get("pos_profile"), "reason": "terminal_default",
                "detail": _("Your assigned profile {0} is not allowed on this terminal; "
                            "using the terminal's own profile.").format(wanted)}

    if t.get("pos_profile"):
        return {"pos_profile": t.pos_profile, "reason": "terminal",
                "detail": _("The terminal's configured profile.")}

    default_row = next((r for r in (t.get("allowed_pos_profiles") or []) if r.is_default), None)
    if default_row:
        return {"pos_profile": default_row.pos_profile, "reason": "terminal_allowed_default",
                "detail": _("First allowed profile on this terminal.")}

    return {"pos_profile": None, "reason": "none",
            "detail": _("No POS Profile on this terminal. Set one before selling.")}


@frappe.whitelist()
def choose_branch(branch: str, terminal: str | None = None):
    """Commit a branch for this session and hand back the till to open.

    Picks the terminal when the branch has exactly one, or when the user's
    assignment names one — the branch prompt should not immediately become
    a second prompt for a machine there is no choice about.
    """
    rows = _assignments(frappe.session.user)
    if rows and branch not in {r["branch"] for r in rows} and not _is_manager():
        frappe.throw(_("You are not assigned to {0}.").format(branch),
                     frappe.PermissionError)

    assigned = next((r for r in rows if r["branch"] == branch), None)
    terminals = _terminals_for(branch, assigned.get("pos_outlet") if assigned else None)

    if not terminal:
        if assigned and assigned.get("terminal"):
            terminal = assigned["terminal"]
        elif len(terminals) == 1:
            terminal = terminals[0]["name"]

    if not terminal:
        return {"branch": branch, "terminal": None, "terminals": terminals,
                "needs_terminal": True}

    if terminal not in {t["name"] for t in terminals} and not _is_manager():
        frappe.throw(_("Terminal {0} is not in {1}.").format(terminal, branch),
                     frappe.PermissionError)

    profile = resolve_pos_profile(terminal)

    # Remembered so the next login on any device skips straight through.
    try:
        frappe.db.set_value("User", frappe.session.user,
                            "default_alphax_terminal", terminal,
                            update_modified=False)
    except Exception:
        pass

    return {
        "branch": branch,
        "terminal": terminal,
        "terminals": terminals,
        "needs_terminal": False,
        "pos_profile": profile.get("pos_profile"),
        "profile_reason": profile.get("reason"),
        "profile_detail": profile.get("detail"),
    }
