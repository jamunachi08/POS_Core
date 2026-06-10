"""
AlphaX POS — Unified Boot

The cashier SPA calls `pos_boot(terminal)` exactly once on login. The response
contains everything needed to run the terminal offline-capable for a shift:

    - terminal       : Terminal record (basic identity)
    - outlet         : Outlet record (company, branch, warehouse, price list, ...)
    - domains        : Active domain packs with their capability flags
    - profile        : POS Profile (modes of payment, item groups, tax template)
    - theme          : Theme record if linked
    - loyalty        : Active programs scoped to this outlet's domains
    - payment_methods: Modes of payment + terminal-capture flags
    - scale_rules    : Weighing-scale barcode rules (prefix-based)
    - taxes          : Sales taxes & charges template (rows)
    - currency       : Default currency + symbol + precision
    - server_time    : Server clock (for offline-skew detection)
    - features       : Union of feature flags from active domains

Performance: this is one query-heavy call, but it's ONLY called on login
and on shift open. Caching at frappe.cache layer (per-terminal, 5 min TTL)
makes it cheap on subsequent logins.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime


_FEATURE_FIELDS = [
    "uses_floor_plan",
    "uses_kds",
    "uses_modifiers",
    "uses_recipes",
    "uses_scale",
    "uses_batch_expiry",
    "uses_serial",
    "uses_appointments",
    "uses_tips",
    "uses_service_charge",
    "uses_courses",
    "uses_table_qr",
    "uses_split_bill",
    "uses_loyalty",
    "uses_prescription",
]


def _resolve_outlet_for_terminal(terminal_doc):
    """A Terminal can be linked to an Outlet directly, or via its POS Profile.

    The Terminal doctype field is ``pos_outlet`` (older builds used
    ``outlet``); we try both so existing data keeps resolving.
    """
    outlet_name = getattr(terminal_doc, "pos_outlet", None) or getattr(
        terminal_doc, "outlet", None
    )
    if outlet_name and frappe.db.exists("AlphaX POS Outlet", outlet_name):
        return outlet_name

    profile_name = getattr(terminal_doc, "pos_profile", None)
    if profile_name:
        # The custom field `alphax_outlet` is added to the standard
        # ERPNext POS Profile by our install.py; that's where it lives,
        # not on a separate doctype.
        outlet = frappe.db.get_value(
            "POS Profile", profile_name, "alphax_outlet"
        )
        if outlet and frappe.db.exists("AlphaX POS Outlet", outlet):
            return outlet
    return None


def _domain_pack_summary(domain_code):
    """Return the pack's capability dict, or None if pack missing."""
    if not domain_code:
        return None
    if not frappe.db.exists("AlphaX POS Domain Pack", domain_code):
        return None
    pack = frappe.db.get_value(
        "AlphaX POS Domain Pack",
        domain_code,
        ["domain_code", "label", "icon", "enabled", "default_item_group"]
        + _FEATURE_FIELDS,
        as_dict=True,
    )
    return pack


def _collect_active_domains(outlet_doc):
    """Return list of domain pack summaries for this outlet (in order)."""
    out = []
    seen = set()
    for row in (outlet_doc.domains or []):
        code = row.domain
        if not code or code in seen:
            continue
        seen.add(code)
        summary = _domain_pack_summary(code)
        if summary and summary.get("enabled"):
            out.append(summary)

    if not out:
        legacy = (outlet_doc.pos_type or "").strip()
        if legacy and legacy not in ("Use Global", ""):
            summary = _domain_pack_summary(legacy)
            if summary:
                out.append(summary)

    if not out:
        fallback = _domain_pack_summary("Generic")
        if fallback:
            out.append(fallback)

    return out


def _union_features(domains):
    """Take the OR of every feature flag across active domains."""
    feats = {f: 0 for f in _FEATURE_FIELDS}
    for d in domains:
        for f in _FEATURE_FIELDS:
            if d.get(f):
                feats[f] = 1
    return feats


def _loyalty_programs_for_outlet(outlet_doc, active_domain_codes):
    """All enabled loyalty programs that apply to this outlet."""
    rows = frappe.get_all(
        "AlphaX POS Loyalty Program",
        filters={"enabled": 1, "company": outlet_doc.company},
        fields=[
            "name",
            "program_code",
            "program_name",
            "domain_scope",
            "earn_basis",
            "default_earn_points",
            "default_earn_per_amount",
            "redemption_value",
            "min_points_to_redeem",
            "max_redeem_percent",
            "expiry_days",
        ],
    )
    out = []
    for r in rows:
        scope = r.get("domain_scope") or "All Domains"
        if scope == "All Domains" or scope in active_domain_codes:
            out.append(r)
    return out


def _payment_methods_for_profile(profile_name):
    if not profile_name:
        return []
    rows = frappe.get_all(
        "AlphaX POS Profile Payment Method",
        filters={"parent": profile_name},
        fields=[
            "mode_of_payment",
            "default",
            "amount",
            "allow_in_returns",
        ],
        order_by="idx asc",
    )
    enriched = []
    for r in rows:
        if not r.get("mode_of_payment"):
            continue
        mop = frappe.db.get_value(
            "Mode of Payment",
            r["mode_of_payment"],
            [
                "type",
                "alphax_capture_terminal_data",
                "alphax_terminal_settings",
                "alphax_require_terminal_approval",
                "alphax_allow_manual_ref",
            ],
            as_dict=True,
        ) or {}
        enriched.append({**r, **mop})
    return enriched


def _scale_rules():
    rules = frappe.get_all(
        "AlphaX POS Scale Barcode Rule",
        filters={},
        fields=[
            "name",
            "prefix",
            "total_length",
            "code_start",
            "code_length",
            "value_start",
            "value_length",
            "value_kind",
            "value_divisor",
            "check_digit_present",
        ],
        order_by="prefix",
    )
    return rules


def _taxes_rows(template):
    if not template:
        return []
    return frappe.get_all(
        "Sales Taxes and Charges",
        filters={"parent": template},
        fields=[
            "charge_type",
            "account_head",
            "rate",
            "tax_amount",
            "description",
            "included_in_print_rate",
            "cost_center",
        ],
        order_by="idx asc",
    )


def _company_currency(company):
    if not company:
        return {"currency": "USD", "symbol": "$", "precision": 2}
    cur = frappe.db.get_value("Company", company, "default_currency")
    cur_doc = frappe.db.get_value(
        "Currency", cur, ["symbol", "smallest_currency_fraction_value"], as_dict=True
    ) or {}
    return {
        "currency": cur,
        "symbol": cur_doc.get("symbol") or cur,
        "precision": 2,
    }


@frappe.whitelist()
def pos_boot(terminal):
    """One call returns the entire bootstrap payload."""
    if not terminal or not frappe.db.exists("AlphaX POS Terminal", terminal):
        frappe.throw(_("Terminal not found: {0}").format(terminal))

    cache_key = f"alphax_pos_boot::{terminal}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        cached["server_time"] = now_datetime().isoformat()
        cached["from_cache"] = True
        return cached

    t = frappe.get_doc("AlphaX POS Terminal", terminal)
    outlet_name = _resolve_outlet_for_terminal(t)

    payload = {
        "terminal": {
            "name": t.name,
            "terminal_name": getattr(t, "terminal_name", t.name),
            "pos_profile": getattr(t, "pos_profile", None),
            "outlet": outlet_name,
        },
        "outlet": None,
        "domains": [],
        "features": {f: 0 for f in _FEATURE_FIELDS},
        "profile": None,
        "theme": None,
        "loyalty_programs": [],
        "payment_methods": [],
        "scale_rules": [],
        "taxes": [],
        "currency": {"currency": "USD", "symbol": "$", "precision": 2},
        "server_time": now_datetime().isoformat(),
        "from_cache": False,
    }

    if outlet_name:
        outlet = frappe.get_doc("AlphaX POS Outlet", outlet_name)
        domains = _collect_active_domains(outlet)
        active_codes = [d["domain_code"] for d in domains]
        payload["outlet"] = {
            "name": outlet.name,
            "outlet_name": outlet.outlet_name,
            "company": outlet.company,
            "branch": outlet.branch,
            "warehouse": outlet.warehouse,
            "cost_center": outlet.cost_center,
            "primary_domain": outlet.primary_domain,
            "update_stock": int(outlet.update_stock or 0),
            "default_price_list": outlet.default_price_list,
            "default_loyalty_program": outlet.default_loyalty_program,
            "service_charge_item": outlet.service_charge_item,
            "tips_item": outlet.tips_item,
            "sales_taxes_and_charges_template": outlet.sales_taxes_and_charges_template,
        }
        payload["domains"] = domains
        payload["features"] = _union_features(domains)
        payload["loyalty_programs"] = _loyalty_programs_for_outlet(outlet, active_codes)
        payload["taxes"] = _taxes_rows(outlet.sales_taxes_and_charges_template)
        payload["currency"] = _company_currency(outlet.company)

    profile_name = getattr(t, "pos_profile", None)
    if profile_name and frappe.db.exists("POS Profile", profile_name):
        prof = frappe.get_doc("POS Profile", profile_name)
        payload["profile"] = {
            "name": prof.name,
            "currency": getattr(prof, "currency", None),
            "language": getattr(prof, "language", None),
            "theme": getattr(prof, "theme", None),
        }
        payload["payment_methods"] = _payment_methods_for_profile(profile_name)
        theme_name = getattr(prof, "theme", None)
        if theme_name and frappe.db.exists("AlphaX POS Theme", theme_name):
            theme = frappe.get_doc("AlphaX POS Theme", theme_name)
            payload["theme"] = theme.as_dict()

    payload["scale_rules"] = _scale_rules()

    frappe.cache().set_value(cache_key, payload, expires_in_sec=300)
    return payload


@frappe.whitelist()
def invalidate_boot_cache(terminal=None):
    """Manager flips an outlet flag, calls this to refresh terminals."""
    if terminal:
        frappe.cache().delete_value(f"alphax_pos_boot::{terminal}")
    else:
        for key in frappe.cache().get_keys("alphax_pos_boot::*"):
            frappe.cache().delete_value(key)
    return {"ok": True}


@frappe.whitelist()
def get_default_terminal_for_session():
    """Resolve which terminal should be auto-selected on this login.

    Resolution order (first match wins):

      1. The ``default_alphax_terminal`` field on the logged-in user.
         (Set by an admin in the User profile under "AlphaX POS" section.)

      2. None — caller falls back to localStorage on the PC, and if
         that's also empty, prompts the cashier to pick a terminal.

    The cashier UI persists the chosen terminal to localStorage on the
    PC, so the second visit on the same browser bypasses this call.
    This server-side default is the FALLBACK when the PC has no memory
    yet (first time setup, browser cache cleared, new device).

    Returns
    -------
    dict with keys:
        terminal      : str | None — terminal ID
        outlet        : str | None — outlet linked to that terminal
        outlet_name   : str | None — display name of outlet
        branch        : str | None — branch linked to that outlet
        can_change    : bool        — true if the user has 'AlphaX POS Manager'
                                       role (used by the UI to show/hide the
                                       'Change Terminal' button)
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"terminal": None, "outlet": None, "outlet_name": None,
                "branch": None, "can_change": False}

    # Step 1: read the user's default terminal (custom field added by us)
    terminal = None
    try:
        terminal = frappe.db.get_value("User", user, "default_alphax_terminal")
    except Exception:
        # Custom field not installed yet (mid-migrate, fresh install) —
        # don't crash the cashier; just return no default.
        terminal = None

    # Resolve outlet + branch chain if we got a terminal
    outlet = outlet_name = branch = None
    if terminal:
        # Verify the terminal still exists (the user record could be stale)
        if frappe.db.exists("AlphaX POS Terminal", terminal):
            terminal_doc = frappe.get_cached_doc("AlphaX POS Terminal", terminal)
            try:
                outlet = _resolve_outlet_for_terminal(terminal_doc)
            except Exception:
                outlet = None
            if outlet and frappe.db.exists("AlphaX POS Outlet", outlet):
                outlet_doc = frappe.get_cached_doc("AlphaX POS Outlet", outlet)
                outlet_name = outlet_doc.get("outlet_name") or outlet
                branch = outlet_doc.get("branch") or None
        else:
            terminal = None  # stale link — fall through to "no default"

    # Manager check — used by the UI to show/hide the "Change" button
    can_change = (
        "AlphaX POS Manager" in frappe.get_roles(user)
        or "System Manager" in frappe.get_roles(user)
    )

    return {
        "terminal": terminal,
        "outlet": outlet,
        "outlet_name": outlet_name,
        "branch": branch,
        "can_change": can_change,
    }


@frappe.whitelist()
def resolve_session_pos_profile(terminal: str | None = None) -> dict:
    """Resolve which POS Profile the cashier should use right now.

    The active profile is the intersection of:
      - profiles allowed at this terminal (Terminal.allowed_pos_profiles)
      - profiles allowed for this user (User.allowed_pos_profiles)

    Resolution rules:
      1. If terminal has no allowed list → fall back to any profile the
         user is allowed (legacy behavior).
      2. If user has no allowed list → fall back to any profile allowed
         at the terminal (legacy behavior — useful for one-vertical shops
         where every cashier can use the only profile).
      3. If both lists are non-empty → take the intersection.
      4. Within the eligible set, prefer the user's "default" row,
         then the terminal's "default" profile field, then the first
         profile alphabetically.

    Returns
    -------
    dict
        {
            "profile": str | None,  # the resolved profile name
            "candidates": list[str],  # all eligible profiles, for picker
            "needs_picker": bool,  # true if multiple candidates exist
            "message": str | None,  # error message if profile is None
        }
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"profile": None, "candidates": [], "needs_picker": False,
                "message": "Not logged in."}

    # 1) Get terminal's allowed list
    terminal_allowed = []
    terminal_default = None
    if terminal and frappe.db.exists("AlphaX POS Terminal", terminal):
        try:
            t_doc = frappe.get_cached_doc("AlphaX POS Terminal", terminal)
            terminal_allowed = [
                row.pos_profile for row in (t_doc.get("allowed_pos_profiles") or [])
                if row.get("pos_profile")
            ]
            terminal_default = t_doc.get("pos_profile")
        except Exception:
            terminal_allowed = []

    # 2) Get user's allowed list
    user_allowed = []
    user_default = None
    try:
        user_rows = frappe.get_all(
            "AlphaX POS Profile Allowed",
            filters={"parent": user, "parenttype": "User"},
            fields=["pos_profile", "is_default"],
        )
        user_allowed = [r["pos_profile"] for r in user_rows if r.get("pos_profile")]
        for r in user_rows:
            if r.get("is_default") and r.get("pos_profile"):
                user_default = r["pos_profile"]
                break
    except Exception:
        user_allowed = []

    # 3) Compute eligible set
    if terminal_allowed and user_allowed:
        # Intersection
        eligible = [p for p in terminal_allowed if p in user_allowed]
    elif terminal_allowed:
        # User has no allowed list — accept any terminal-allowed profile
        eligible = terminal_allowed
    elif user_allowed:
        # Terminal has no allowed list — accept any user-allowed profile
        eligible = user_allowed
    else:
        # Both empty — try ERPNext's standard POS Profile.applicable_for_users
        # for backward compatibility
        try:
            std_rows = frappe.get_all(
                "POS Profile User",
                filters={"user": user},
                fields=["parent"],
            )
            eligible = [r["parent"] for r in std_rows if r.get("parent")]
        except Exception:
            eligible = []

    if not eligible:
        return {
            "profile": None,
            "candidates": [],
            "needs_picker": False,
            "message": "No POS Profile is assigned to you for this terminal. "
                       "Ask your administrator to assign one.",
        }

    # 4) Pick best candidate
    eligible_sorted = sorted(set(eligible))
    if user_default and user_default in eligible_sorted:
        chosen = user_default
    elif terminal_default and terminal_default in eligible_sorted:
        chosen = terminal_default
    else:
        chosen = eligible_sorted[0]

    return {
        "profile": chosen,
        "candidates": eligible_sorted,
        "needs_picker": len(eligible_sorted) > 1,
        "message": None,
    }



    """Return all active terminals with their outlet/branch context.

    Used by the cashier UI's first-time terminal picker dialog (when
    no default exists for the user and the PC has no localStorage).

    The list is intentionally NOT filtered by user permissions — the
    point is "let the cashier or manager pick the right station". POS
    Profile permissions are still enforced at order creation time, so
    this is safe.
    """
    rows = frappe.get_all(
        "AlphaX POS Terminal",
        fields=["name", "pos_outlet"],
        order_by="name asc",
        limit_page_length=200,
    )

    # Enrich with outlet/branch names so the picker can show
    # "Riyadh Mall — Branch 02 — Terminal 3" in the dropdown.
    out = []
    outlet_cache = {}
    for r in rows:
        outlet = r.get("pos_outlet")
        outlet_name = branch = None
        if outlet:
            if outlet not in outlet_cache:
                if frappe.db.exists("AlphaX POS Outlet", outlet):
                    od = frappe.get_cached_doc("AlphaX POS Outlet", outlet)
                    outlet_cache[outlet] = (
                        od.get("outlet_name") or outlet,
                        od.get("branch") or None,
                    )
                else:
                    outlet_cache[outlet] = (outlet, None)
            outlet_name, branch = outlet_cache[outlet]

        out.append({
            "terminal": r["name"],
            "outlet": outlet,
            "outlet_name": outlet_name,
            "branch": branch,
        })
    return out


@frappe.whitelist()
def get_setup_wizard_context() -> dict:
    """Existing data the wizard should let the user pick from instead of
    blindly creating new records — important when installing onto a site
    that already has a Company and Branches.
    """
    companies = []
    try:
        companies = frappe.get_all(
            "Company",
            fields=["name", "default_currency", "country", "abbr"],
            order_by="creation asc",
        )
    except Exception:
        pass

    branches = []
    try:
        if frappe.db.exists("DocType", "Branch"):
            branches = frappe.get_all(
                "Branch", fields=["name"], order_by="creation asc", pluck="name"
            )
    except Exception:
        pass

    return {
        "companies": companies,
        "branches": branches,
        "has_company": bool(companies),
        "has_branch": bool(branches),
        "default_currency": frappe.db.get_default("currency") or "SAR",
    }


@frappe.whitelist()
def run_setup_wizard(payload) -> dict:
    """Execute the Setup Wizard's create-everything action.

    Called by the wizard's final-step submit. The wizard collects
    company, branch, outlet, terminal, and admin user details across
    5 steps; we receive them all here and create the records in one
    coordinated pass.

    Returns
    -------
    dict
        On success: {ok: True, terminal: <name>, profile: <name>,
                     branch: <name>, outlet: <name>, message: str}
        On failure: {ok: False, message: <human-readable reason>}

    Errors are caught and returned as ``{ok: False}`` rather than raised,
    so the wizard can show them inline. Partial creations are NOT rolled
    back automatically — Frappe doesn't have transactional doctype-creation
    in the way SQL does. If something fails midway, the wizard tells the
    user what was created and what failed; they can finish manually from
    the standard list views.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return {"ok": False, "message": "Invalid payload."}

    company_data = payload.get("company") or {}
    branch_data  = payload.get("branch")  or {}
    outlet_data  = payload.get("outlet")  or {}
    terminal_data = payload.get("terminal") or {}
    admin_data   = payload.get("admin")   or {}

    # Self-heal: a leftover ZATCA/ERPGulf module from a previous partial
    # install can make Frappe throw "Module ... not found" the moment we
    # create the Company. Clear those orphaned references first so the
    # wizard can complete. No-op on clean sites.
    try:
        from alphax_pos_suite.alphax_pos_suite.setup_repair import (
            repair_orphaned_module_blockers,
        )
        repair_orphaned_module_blockers()
    except Exception:
        frappe.log_error(
            title="Setup wizard: orphan-module repair failed (non-fatal)",
            message=frappe.get_traceback(),
        )

    created = {"company": None, "branch": None, "outlet": None,
               "terminal": None, "user": None, "profile": None}

    try:
        # 1. Company
        company_name = (company_data.get("name") or "").strip()
        if not company_name:
            return {"ok": False, "message": "Company name is required."}

        if frappe.db.exists("Company", company_name):
            created["company"] = company_name
        else:
            company_doc = {
                "doctype": "Company",
                "company_name": company_name,
                "abbr": _abbr_for(company_name),
                "default_currency": company_data.get("currency") or "SAR",
                "country": company_data.get("country") or "Saudi Arabia",
                "tax_id": company_data.get("vat") or "",
            }
            try:
                comp = frappe.get_doc(dict(company_doc))
                comp.insert(ignore_permissions=True)
            except frappe.DoesNotExistError:
                # A leftover foreign module (e.g. a removed ZATCA app that
                # added a child table to Company) slipped through. Clean it,
                # refresh caches, and retry once with a fresh doc whose meta
                # no longer includes the broken field.
                try:
                    from alphax_pos_suite.alphax_pos_suite.setup_repair import (
                        repair_orphaned_module_blockers,
                    )
                    repair_orphaned_module_blockers()
                    frappe.clear_cache()
                except Exception:
                    frappe.log_error(
                        title="Setup wizard: repair-on-retry failed",
                        message=frappe.get_traceback(),
                    )
                comp = frappe.get_doc(dict(company_doc))
                comp.insert(ignore_permissions=True)
            created["company"] = comp.name

        # 2. Branch (standard ERPNext doctype)
        branch_name = (branch_data.get("name") or "").strip()
        if not branch_name:
            return {"ok": False, "message": "Branch name is required."}

        if not frappe.db.exists("Branch", branch_name):
            br = frappe.get_doc({
                "doctype": "Branch",
                "branch": branch_name,
            })
            br.insert(ignore_permissions=True)
        created["branch"] = branch_name

        # 3. Outlet (AlphaX POS Outlet)
        outlet_name = (outlet_data.get("name") or "").strip()
        if not outlet_name:
            return {"ok": False, "message": "Outlet name is required."}
        domain_code = outlet_data.get("domain") or "Generic"

        if frappe.db.exists("AlphaX POS Outlet", outlet_name):
            created["outlet"] = outlet_name
        else:
            outlet = frappe.get_doc({
                "doctype": "AlphaX POS Outlet",
                "outlet_name": outlet_name,
                "branch": branch_name,
                "primary_domain": domain_code,
                "domains": [{"domain": domain_code}],
            })
            outlet.insert(ignore_permissions=True)
            created["outlet"] = outlet.name

        # 4. POS Profile (standard ERPNext)
        #
        # An ERPNext POS Profile is only *usable* if it has at least one
        # payment method and at least one applicable user. A profile that
        # validates but has no payments lets the cashier ring items yet
        # never complete a sale — the single most common "it loads but
        # doesn't work" failure. So we build a minimally-complete profile
        # here and link it back to the outlet via our custom field.
        profile_name = f"{outlet_name} Profile"
        if not frappe.db.exists("POS Profile", profile_name):
            try:
                profile = frappe.get_doc({
                    "doctype": "POS Profile",
                    "name": profile_name,
                    "company": created["company"],
                    "currency": (
                        frappe.get_cached_value(
                            "Company", created["company"], "default_currency"
                        )
                        or company_data.get("currency")
                        or "SAR"
                    ),
                    "write_off_account": _default_account(created["company"], "Round Off"),
                    "write_off_cost_center": _default_cost_center(created["company"]),
                    "warehouse": _default_warehouse(created["company"]),
                })
                # Link the outlet so terminal->outlet resolution always works
                # even if the terminal's own pos_outlet ever gets cleared.
                if profile.meta.has_field("alphax_outlet"):
                    profile.alphax_outlet = created["outlet"]

                # Attach a default Cash payment method so sales can complete.
                cash_mop = _ensure_cash_mode_of_payment(created["company"])
                if cash_mop:
                    profile.append("payments", {
                        "mode_of_payment": cash_mop,
                        "default": 1,
                    })

                # Make the admin (and the running user) applicable so the
                # profile shows up when opening a POS session.
                applicable = {frappe.session.user}
                admin_email_pre = (admin_data.get("email") or "").strip().lower()
                if admin_email_pre:
                    applicable.add(admin_email_pre)
                for u in applicable:
                    if u and u != "Guest":
                        profile.append("applicable_for_users", {"user": u})

                profile.insert(ignore_permissions=True)
                created["profile"] = profile.name
            except Exception:
                # POS Profile creation can fail on accounts being missing —
                # for first-time setups, that's expected. Log but continue.
                frappe.log_error(
                    title="Setup wizard: POS Profile creation failed",
                    message=frappe.get_traceback(),
                )
                created["profile"] = None
        else:
            created["profile"] = profile_name

        # Belt & suspenders: stamp the outlet onto the profile's custom
        # field if it isn't already, so _resolve_outlet_for_terminal's
        # fallback path also resolves.
        if created["profile"]:
            try:
                if frappe.get_meta("POS Profile").has_field("alphax_outlet"):
                    if not frappe.db.get_value("POS Profile", created["profile"], "alphax_outlet"):
                        frappe.db.set_value(
                            "POS Profile", created["profile"],
                            "alphax_outlet", created["outlet"],
                            update_modified=False,
                        )
            except Exception:
                pass

        # 5. Terminal
        terminal_name = (terminal_data.get("name") or "Terminal 1").strip()
        if frappe.db.exists("AlphaX POS Terminal", terminal_name):
            # Don't overwrite — use the existing one
            created["terminal"] = terminal_name
        else:
            terminal_doc = frappe.get_doc({
                "doctype": "AlphaX POS Terminal",
                "name": terminal_name,
                "pos_outlet": created["outlet"],
                "pc_hostname": (terminal_data.get("pc_hostname") or "").strip(),
                "last_bound_at": now_datetime(),
                "last_bound_by": frappe.session.user,
                "pos_profile": created["profile"],
            })
            if created["profile"]:
                terminal_doc.append("allowed_pos_profiles", {
                    "pos_profile": created["profile"],
                    "is_default": 1,
                })
            try:
                terminal_doc.insert(ignore_permissions=True)
                created["terminal"] = terminal_doc.name
            except frappe.NameError:
                # Terminal name collision — pick the first available variant
                base = terminal_name
                for i in range(2, 100):
                    candidate = f"{base} ({i})"
                    if not frappe.db.exists("AlphaX POS Terminal", candidate):
                        terminal_doc.name = candidate
                        terminal_doc.insert(ignore_permissions=True)
                        created["terminal"] = candidate
                        break

        # 6. Admin user + manager PIN
        admin_email = (admin_data.get("email") or "").strip().lower()
        admin_name  = (admin_data.get("full_name") or "").strip()
        admin_pin   = (admin_data.get("pin") or "").strip()

        if not admin_email or "@" not in admin_email:
            return {
                "ok": False,
                "message": "Admin email is required and must be valid.",
                "partial": created,
            }
        if not re.fullmatch(r"\d{4,6}", admin_pin):
            return {
                "ok": False,
                "message": "Manager PIN must be 4 to 6 digits.",
                "partial": created,
            }

        if frappe.db.exists("User", admin_email):
            user = frappe.get_doc("User", admin_email)
            created["user"] = admin_email
        else:
            first_name, _, last_name = admin_name.partition(" ")
            user = frappe.get_doc({
                "doctype": "User",
                "email": admin_email,
                "first_name": first_name or admin_name,
                "last_name": last_name or "",
                "send_welcome_email": 1,
                "user_type": "System User",
                "enabled": 1,
                "roles": [
                    {"role": "System Manager"},
                    {"role": "AlphaX POS Manager"},
                    {"role": "Sales User"},
                ],
            })
            user.insert(ignore_permissions=True)
            created["user"] = user.name

        # Make sure user has AlphaX POS Manager role even if user existed
        existing_roles = {r.role for r in (user.get("roles") or [])}
        for needed in ("System Manager", "AlphaX POS Manager"):
            if needed not in existing_roles:
                user.append("roles", {"role": needed})
        user.save(ignore_permissions=True)

        # 7. Manager PIN
        try:
            from alphax_pos_suite.alphax_pos_suite.security.manager_pin import set_manager_pin
            set_manager_pin(user=admin_email, pin=admin_pin)
        except Exception:
            frappe.log_error(
                title="Setup wizard: failed to set manager PIN",
                message=frappe.get_traceback(),
            )

        # 8. Mark setup as complete (so wizard doesn't keep prompting)
        try:
            frappe.db.set_value("System Settings", None, "setup_complete", 1)
        except Exception:
            pass

        frappe.db.commit()

        return {
            "ok": True,
            "terminal": created["terminal"],
            "profile": created["profile"],
            "branch": created["branch"],
            "outlet": created["outlet"],
            "user": created["user"],
            "message": "All set! Loading your cashier register...",
        }

    except Exception as e:
        frappe.log_error(
            title="Setup wizard failed",
            message=frappe.get_traceback(),
        )
        msg = str(e)[:200]
        hint = ""
        if "not found" in msg and ("Module" in msg or "module" in msg):
            hint = (" A leftover module from a previously removed app is "
                    "blocking setup. Run 'repair_setup_blockers' (AlphaX POS "
                    "setup-repair) and try again.")
        return {
            "ok": False,
            "message": f"Setup failed: {msg}. Check Error Log for details.{hint}",
            "partial": created,
        }


def _abbr_for(name: str) -> str:
    """Generate a 3-letter abbreviation from a company name."""
    parts = [p for p in name.upper().split() if p]
    if not parts:
        return "CO"
    if len(parts) == 1:
        return parts[0][:3]
    return "".join(p[0] for p in parts[:3])


def _default_account(company: str, account_type: str):
    """Try to find a default account for the company, return None if missing."""
    try:
        return frappe.db.get_value(
            "Account",
            {"company": company, "account_type": account_type, "is_group": 0},
            "name",
        )
    except Exception:
        return None


def _default_cost_center(company: str):
    try:
        return frappe.db.get_value(
            "Cost Center",
            {"company": company, "is_group": 0},
            "name",
        )
    except Exception:
        return None


def _default_warehouse(company: str):
    try:
        return frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 0},
            "name",
        )
    except Exception:
        return None


def _ensure_cash_mode_of_payment(company: str):
    """Return a usable 'Cash' Mode of Payment, creating one if needed.

    A POS Profile needs at least one payment method to complete a sale.
    'Cash' exists on most ERPNext sites out of the box; if not, we create
    it and wire its default account to the company's Cash account so the
    payment posts cleanly.
    """
    try:
        mop = "Cash"
        if not frappe.db.exists("Mode of Payment", mop):
            doc = frappe.get_doc({
                "doctype": "Mode of Payment",
                "mode_of_payment": mop,
                "type": "Cash",
                "enabled": 1,
            })
            doc.insert(ignore_permissions=True)

        # Make sure it has a default account for this company so the
        # Sales Invoice payment entry can post without prompting.
        cash_account = _default_account(company, "Cash") or _default_account(
            company, "Bank"
        )
        if cash_account:
            mop_doc = frappe.get_doc("Mode of Payment", mop)
            has_company = any(
                row.company == company for row in (mop_doc.get("accounts") or [])
            )
            if not has_company:
                mop_doc.append("accounts", {
                    "company": company,
                    "default_account": cash_account,
                })
                mop_doc.save(ignore_permissions=True)
        return mop
    except Exception:
        frappe.log_error(
            title="Setup wizard: failed ensuring Cash mode of payment",
            message=frappe.get_traceback(),
        )
        return None
