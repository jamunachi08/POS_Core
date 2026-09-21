"""Setup readiness for the process flow board.

The flow board shows *what* the cycle is. This module answers *what is
missing to run it* on this site, and fixes whatever can be fixed from the
server with one click.

Three honest categories, never blurred together:

``auto``
    The server can do it. Roles, custom fields, permissions, seeded
    masters, default printer profiles and stations. Every one of these
    delegates to an installer the app already ships (``install.py``,
    ``onboarding/setup.py``) — nothing is re-implemented here, so the
    button and ``bench migrate`` can never disagree about what "installed"
    means.

``device``
    Only the physical PC can do it. PC hostname, hardware UUID, MAC and
    bridge state are reported by the AlphaX Bridge daemon running *on that
    machine*. A browser cannot read any of them. The button here downloads
    the personalised installer; the fields fill themselves in on the
    bridge's first heartbeat after it runs.

``manual``
    Needs a human decision the server must not guess. Card readers carry
    a vendor, merchant ID and credentials; creating a placeholder would
    give a till a payment device that silently fails at the first sale.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

AX_ROLES = [
    "AlphaX POS Cashier",
    "AlphaX POS Supervisor",
    "AlphaX POS Manager",
    "AlphaX POS Kitchen",
]

#: Who may read readiness. Supervisors see it so they know what to chase.
READ_ROLES = {"AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}

#: Who may change site configuration from the board.
RUN_ROLES = {"AlphaX POS Manager", "System Manager"}

#: The setup wizard used to copy the first user-agent token into the
#: hostname field, which is the OS ("Windows NT 10.0"), not a hostname.
#: Matches exactly those tokens so a real hostname is never touched.
_UA_OS_TOKEN = re.compile(
    r"^(Windows NT [\d.]+|Macintosh|X11|Linux( x86_64| aarch64)?|iPhone|iPad|Android[\s\d.]*|CrOS.*)$",
    re.I,
)

DEFAULT_PRINTER_PROFILES = [
    {
        "profile_name": "AlphaX Thermal 80mm",
        "print_type": "Receipt",
        "transport": "qz-tray",
        "paper_width_mm": 80,
        "characters_per_line": 42,
        "auto_cut": 1,
        "open_cash_drawer": 1,
    },
    {
        "profile_name": "AlphaX Kitchen Ticket 80mm",
        "print_type": "Kitchen Ticket",
        "transport": "qz-tray",
        "paper_width_mm": 80,
        "characters_per_line": 42,
        "auto_cut": 1,
        "open_cash_drawer": 0,
    },
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _require(roles: set):
    if not (set(frappe.get_roles()) & roles):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _count(doctype: str, filters=None) -> int:
    if not frappe.db.exists("DocType", doctype):
        return 0
    try:
        return frappe.db.count(doctype, filters or {})
    except Exception:
        return 0


def _has(doctype: str, fieldname: str) -> bool:
    try:
        return frappe.get_meta(doctype).has_field(fieldname)
    except Exception:
        return False


def _terminals() -> list:
    if not frappe.db.exists("DocType", "AlphaX POS Terminal"):
        return []
    want = ["name", "pos_outlet", "pc_hostname", "pc_uuid", "pc_mac_address"]
    for f in ("hardware_plan_json", "hardware_profile", "hardware_configured_on",
              "bridge_installed", "bridge_last_seen", "bridge_version", "bridge_device_count"):
        if _has("AlphaX POS Terminal", f):
            want.append(f)
    return frappe.get_all("AlphaX POS Terminal", fields=want, order_by="creation asc",
                          ignore_permissions=True)


def _plan_of(row) -> dict:
    raw = row.get("hardware_plan_json")
    if not raw:
        return {}
    try:
        val = json.loads(raw) if isinstance(raw, str) else raw
        return val if isinstance(val, dict) else {}
    except ValueError:
        return {}


def _needs(plans: list, *roles) -> bool:
    """True if any terminal's hardware plan ticks any of ``roles``."""
    return any(p.get(r) for p in plans for r in roles)


def _bridge_kit_available() -> bool:
    try:
        from alphax_pos_suite.alphax_pos_suite.onboarding.bridge_dist import bundled_bridge_info
        return bool(bundled_bridge_info().get("available"))
    except Exception:
        return False


def _item(key, label, label_ar, status, kind, count=None, detail="", route=None,
          required=True):
    return {
        "key": key, "label": label, "label_ar": label_ar, "status": status,
        "kind": kind, "count": count, "detail": detail, "route": route,
        "required": required,
    }


# --------------------------------------------------------------------------
# readiness
# --------------------------------------------------------------------------


@frappe.whitelist()
def get_readiness() -> dict:
    """Checklist of what this site still needs, and what can be fixed here."""
    _require(READ_ROLES)

    terms = _terminals()
    plans = [_plan_of(t) for t in terms]
    site = []

    # ---- core install: roles, custom fields, permissions --------------------
    missing_roles = [r for r in AX_ROLES if not frappe.db.exists("Role", r)]
    onboarding_ok = _has("AlphaX POS Terminal", "bridge_installed")
    core_ok = not missing_roles and onboarding_ok
    site.append(_item(
        "core", "Roles, fields and permissions", "الأدوار والحقول والصلاحيات",
        "ok" if core_ok else "missing", "auto",
        detail=("" if core_ok else
                "Missing: " + ", ".join(missing_roles + ([] if onboarding_ok
                                                          else ["terminal bridge fields"]))),
    ))

    # ---- masters seeded by install.py ---------------------------------------
    masters = {
        "Order types": _count("AlphaX POS Order Type"),
        "Domain packs": _count("AlphaX POS Domain Pack"),
        "Delivery platforms": _count("AlphaX Delivery Platform"),
        "Scale barcode": _count("AlphaX POS Scale Barcode Definition"),
    }
    empty = [k for k, v in masters.items() if not v]
    site.append(_item(
        "masters", "Seeded master data", "البيانات الأساسية",
        "ok" if not empty else "missing", "auto",
        count=sum(masters.values()),
        detail=("" if not empty else "Empty: " + ", ".join(empty)),
    ))

    # ---- structure: needs the wizard, which asks the operator questions -----
    structure = {
        "Company": _count("Company"),
        "Outlet": _count("AlphaX POS Outlet"),
        "Terminal": len(terms),
        "POS Profile": _count("AlphaX POS Profile"),
    }
    gaps = [k for k, v in structure.items() if not v]
    site.append(_item(
        "structure", "Company, outlet and terminal", "الشركة والمنفذ ونقطة البيع",
        "ok" if not gaps else "missing", "wizard",
        detail=("" if not gaps else "Run the setup wizard to create: " + ", ".join(gaps)),
        route="/app/alphax-pos-setup-wizard",
    ))

    # ---- printing, driven by what terminals actually said they have ---------
    wants_print = _needs(plans, "receipt_printer", "kot_printer") or not plans
    n_prof = _count("AlphaX POS Printer Profile")
    site.append(_item(
        "printer_profiles", "Printer profiles", "ملفات الطابعات",
        "ok" if n_prof else ("missing" if wants_print else "skipped"), "auto",
        count=n_prof, required=wants_print,
        detail=("" if n_prof else
                "Creates AlphaX Thermal 80mm and AlphaX Kitchen Ticket 80mm."),
    ))

    n_out = _count("AlphaX POS Outlet")
    n_ps = _count("AlphaX POS Print Station")
    site.append(_item(
        "print_stations", "Print stations", "محطات الطباعة",
        "ok" if n_ps else ("missing" if (wants_print and n_out) else
                           ("blocked" if wants_print else "skipped")), "auto",
        count=n_ps, required=wants_print,
        detail=("" if n_ps else
                ("One receipt station per outlet. Printer names are filled in "
                 "once the bridge reports the devices it can see."
                 if n_out else "Needs an outlet first.")),
    ))

    wants_kitchen = _needs(plans, "kot_printer", "kds_screen")
    n_ks = _count("AlphaX POS Kitchen Station")
    site.append(_item(
        "kitchen_stations", "Kitchen stations", "محطات المطبخ",
        "ok" if n_ks else ("missing" if (wants_kitchen and n_out) else
                           ("blocked" if wants_kitchen else "skipped")), "auto",
        count=n_ks, required=wants_kitchen,
        detail=("" if n_ks else
                ("One main kitchen per outlet." if wants_kitchen
                 else "No terminal has a kitchen printer or display ticked.")),
    ))

    # ---- payment: never auto ------------------------------------------------
    wants_card = _needs(plans, "card_terminal")
    n_cr = _count("AlphaX POS Card Reader")
    site.append(_item(
        "card_readers", "Card readers", "قارئات البطاقات",
        "ok" if n_cr else ("missing" if wants_card else "skipped"), "manual",
        count=n_cr, required=wants_card,
        detail=("" if n_cr else
                ("Needs vendor, merchant ID and credentials. Not created "
                 "automatically — a placeholder would fail at the first card sale."
                 if wants_card else "No terminal has a card terminal ticked.")),
        route="/app/alphax-pos-card-reader/new",
    ))

    n_pts = _count("AlphaX POS Payment Terminal Settings")
    site.append(_item(
        "payment_settings", "Payment terminal settings", "إعدادات أجهزة الدفع",
        "ok" if n_pts else ("missing" if wants_card else "skipped"), "manual",
        count=n_pts, required=wants_card,
        detail=("" if n_pts else
                ("Gateway credentials for card payments. Entered by hand."
                 if wants_card else "Only needed once a terminal takes card payments.")),
        route="/app/alphax-pos-payment-terminal-settings",
    ))

    # ---- flow board itself --------------------------------------------------
    n_nodes = _count("AlphaX POS Process Node")
    site.append(_item(
        "process_flow", "Process flow board", "لوحة مسار العمل",
        "ok" if n_nodes else "missing", "auto", count=n_nodes,
    ))

    # ---- per terminal: only the bridge can finish these ---------------------
    kit = _bridge_kit_available()
    terminals = []
    for t, plan in zip(terms, plans):
        configured = bool(t.get("hardware_configured_on"))
        needs_bridge = _needs([plan], "receipt_printer", "kot_printer", "cash_drawer",
                              "card_terminal", "weighing_scale", "customer_display")
        installed = bool(t.get("bridge_installed"))
        host = (t.get("pc_hostname") or "").strip()
        bad_host = bool(host) and bool(_UA_OS_TOKEN.match(host))
        identity = bool(t.get("pc_uuid") or t.get("pc_mac_address"))

        if not configured:
            status, detail = "missing", "Hardware plan not chosen yet. Open the cashier on this PC."
        elif not needs_bridge:
            status, detail = "ok", "No ticked device needs the bridge."
        elif not installed:
            status, detail = "device", "Bridge not installed on this PC."
        elif not identity:
            status, detail = "device", "Bridge online but has not reported hardware identity yet."
        else:
            status, detail = "ok", ""

        terminals.append({
            "terminal": t.name,
            "outlet": t.get("pos_outlet"),
            "status": status,
            "detail": detail,
            "configured": configured,
            "needs_bridge": needs_bridge,
            "bridge_installed": installed,
            "bridge_last_seen": t.get("bridge_last_seen"),
            "bridge_version": t.get("bridge_version"),
            "devices": t.get("bridge_device_count") or 0,
            "pc_hostname": host,
            "hostname_is_os_string": bad_host,
            "identity_captured": identity,
        })

    bad_hosts = [t["terminal"] for t in terminals if t["hostname_is_os_string"]]
    if bad_hosts:
        site.append(_item(
            "hostnames", "Terminal hostnames", "أسماء أجهزة الطرفيات",
            "missing", "auto", count=len(bad_hosts),
            detail=("Holds the browser's OS string, not the PC name: "
                    + ", ".join(bad_hosts[:5])
                    + ". Clearing is safe; the bridge writes the real name."),
        ))

    auto_pending = [i["key"] for i in site if i["kind"] == "auto" and i["status"] == "missing"]

    return {
        "site": site,
        "terminals": terminals,
        "auto_pending": auto_pending,
        "bad_hostnames": bad_hosts,
        "bridge_kit_available": kit,
        "can_run": bool(set(frappe.get_roles()) & RUN_ROLES),
        "ready": not auto_pending and all(
            i["status"] in ("ok", "skipped", "info") for i in site
        ) and all(t["status"] == "ok" for t in terminals),
    }


# --------------------------------------------------------------------------
# install
# --------------------------------------------------------------------------


@frappe.whitelist()
def run_setup(keys=None) -> dict:
    """Run the server-side installers for the requested keys.

    Every step is idempotent and delegates to the installer the app already
    uses on ``bench install-app`` / ``bench migrate``. A failure in one step
    is reported and the rest still run.
    """
    _require(RUN_ROLES)

    if isinstance(keys, str):
        keys = frappe.parse_json(keys) if keys.strip().startswith("[") else [keys]
    keys = list(keys or get_readiness()["auto_pending"])

    steps = {
        "core": _run_core,
        "masters": _run_masters,
        "printer_profiles": _run_printer_profiles,
        "print_stations": _run_print_stations,
        "kitchen_stations": _run_kitchen_stations,
        "process_flow": _run_process_flow,
        "hostnames": _run_clean_hostnames,
    }

    results = []
    for key in keys:
        fn = steps.get(key)
        if not fn:
            results.append({"key": key, "ok": False, "message": "Not an automatic step."})
            continue
        try:
            msg = fn()
            frappe.db.commit()
            results.append({"key": key, "ok": True, "message": msg})
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"AlphaX POS setup: {key} failed",
                             message=frappe.get_traceback())
            results.append({"key": key, "ok": False,
                            "message": "Failed — see Error Log for the traceback."})

    frappe.clear_cache()
    return {"results": results, "readiness": get_readiness()}


def _run_core() -> str:
    from alphax_pos_suite.alphax_pos_suite import install
    from alphax_pos_suite.alphax_pos_suite.onboarding.setup import (
        ensure_onboarding_fields, seed_layout_presets,
    )
    install.create_roles()
    install.create_custom_fields()
    install.create_role_profiles()
    install.apply_permissions()
    install.heal_lost_manager_access()
    ensure_onboarding_fields()
    seed_layout_presets()
    return "Roles, role profiles, custom fields and permissions ensured."


def _run_masters() -> str:
    from alphax_pos_suite.alphax_pos_suite import install
    install.seed_delivery_platforms()
    install.seed_order_types()
    install.sync_order_type_field_options()
    install.seed_outlet_menus()
    install.seed_domain_packs()
    install.seed_default_barcode_definition()
    return "Order types, domain packs, delivery platforms and barcode rules seeded."


def _run_printer_profiles() -> str:
    made = 0
    for spec in DEFAULT_PRINTER_PROFILES:
        if frappe.db.exists("AlphaX POS Printer Profile", spec["profile_name"]):
            continue
        doc = frappe.get_doc({"doctype": "AlphaX POS Printer Profile", "is_active": 1, **spec})
        doc.insert(ignore_permissions=True)
        made += 1
    return f"{made} printer profile(s) created." if made else "Printer profiles already present."


def _outlets() -> list:
    return frappe.get_all("AlphaX POS Outlet", pluck="name", ignore_permissions=True)


def _run_print_stations() -> str:
    made = 0
    for outlet in _outlets():
        name = f"Receipt - {outlet}"[:140]
        if frappe.db.exists("AlphaX POS Print Station", name):
            continue
        has_default = frappe.db.exists("AlphaX POS Print Station",
                                       {"outlet": outlet, "is_default": 1})
        frappe.get_doc({
            "doctype": "AlphaX POS Print Station",
            "station_name": name,
            "outlet": outlet,
            "station_type": "Printer",
            "is_default": 0 if has_default else 1,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        made += 1
    if not _outlets():
        return "No outlet yet — run the setup wizard first."
    return f"{made} print station(s) created." if made else "Print stations already present."


def _run_kitchen_stations() -> str:
    made = 0
    for outlet in _outlets():
        name = f"Main Kitchen - {outlet}"[:140]
        if frappe.db.exists("AlphaX POS Kitchen Station", name):
            continue
        frappe.get_doc({
            "doctype": "AlphaX POS Kitchen Station",
            "station_name": name,
            "outlet": outlet,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        made += 1
    if not _outlets():
        return "No outlet yet — run the setup wizard first."
    return f"{made} kitchen station(s) created." if made else "Kitchen stations already present."


def _run_process_flow() -> str:
    from alphax_pos_suite.alphax_pos_suite.seed.process_flow import seed_process_flow
    seed_process_flow()
    return "Process flow stages and nodes seeded."


def _run_clean_hostnames() -> str:
    """Blank hostnames that are really the browser's OS string.

    Only touches a terminal whose bridge is not installed — once the bridge
    runs it reports the real hostname and overwrites the field anyway, so
    a bridged terminal is left exactly as it is.
    """
    cleaned = 0
    for t in _terminals():
        host = (t.get("pc_hostname") or "").strip()
        if host and _UA_OS_TOKEN.match(host) and not t.get("bridge_installed"):
            frappe.db.set_value("AlphaX POS Terminal", t.name, "pc_hostname", "",
                                update_modified=False)
            cleaned += 1
    return f"{cleaned} hostname(s) cleared." if cleaned else "No OS-string hostnames found."


# --------------------------------------------------------------------------
# bridge
# --------------------------------------------------------------------------


@frappe.whitelist()
def bridge_download(terminal: str, os_name: str = "windows") -> dict:
    """Where to get the bridge for ``terminal``, without generating it yet.

    Returns the URL of the existing personalised bootstrap endpoint, or the
    external install plan when no kit is bundled with this build. The
    browser follows the URL itself so the normal download handling applies.
    """
    _require(READ_ROLES)
    if not frappe.db.exists("AlphaX POS Terminal", terminal):
        frappe.throw(_("Unknown terminal {0}").format(terminal))

    if _bridge_kit_available():
        from urllib.parse import urlencode
        qs = urlencode({"os_name": os_name, "terminal": terminal})
        return {
            "mode": "bundled",
            "url": "/api/method/alphax_pos_suite.alphax_pos_suite.onboarding."
                   f"bridge_dist.bootstrap?{qs}",
            "note": _("Run the downloaded file on {0} itself, as the Windows user "
                      "who operates the till. PC identity and bridge state fill in "
                      "on its first heartbeat, within 5 minutes.").format(terminal),
        }

    from alphax_pos_suite.alphax_pos_suite.onboarding.api import get_bridge_installers
    return {
        "mode": "external",
        "plan": get_bridge_installers(os_name),
        "note": _("No installer is bundled with this build. Follow the install "
                  "plan, or run scripts/sync_bridge_kit.ps1 and redeploy to bundle one."),
    }
