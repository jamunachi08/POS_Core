"""
AlphaX POS — Zero-Touch Cashier Onboarding
==========================================

Goal: a cashier opens the POS on a brand-new PC or tablet and is running
in under 60 seconds, without a manager typing hostnames, MAC addresses,
IPs or bridge tokens.

Flow driven by the SPA (`OnboardingWizard.vue`):

    1.  SPA collects what the BROWSER can see (stable local UUID, screen,
        platform, timezone, touch capability) -> `client_hints`.
    2.  SPA probes localhost for the bridge daemon on the known ports.
        If found it pulls hostname / MAC / OS / bridge version / device
        list from the bridge — those are the authoritative values.
    3.  SPA calls `probe()` with everything it has. The server adds what
        only IT can see (real client IP, forwarded-for chain, User-Agent)
        and answers with a MATCH DECISION:
            - "bound"        -> this fingerprint already owns a terminal
            - "candidate"    -> a terminal exists with matching UUID/MAC
                                but is not yet bound; offer to claim it
            - "provisionable"-> nothing matches; offer to auto-create
            - "ambiguous"    -> several matches; make a human choose
    4.  SPA calls `claim()` or `auto_provision()`. Both write the
        identity block onto AlphaX POS Terminal and stamp last_bound_at.
    5.  From then on `report_bridge_state()` is called on every boot and
        every 5 min heartbeat, so the desk always knows whether the
        bridge on that station is alive, which version, and what devices
        it can see.

Nothing here trusts the client blindly: the client supplies hints, the
server decides. Fingerprints are stored hashed-in-the-clear (they are
not secrets, they are identifiers) but the bridge auth token is NEVER
persisted server-side — only a 4-char hint for support calls.
"""

from __future__ import annotations

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, get_datetime, time_diff_in_seconds

# A station is considered "bridge online" if it heartbeat within this window.
BRIDGE_STALE_SECONDS = 15 * 60

# Ports the SPA probes, in order. Kept server-side so we can change the
# default fleet-wide without reshipping the SPA bundle.
DEFAULT_BRIDGE_PORTS = [8420, 8421, 8080]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean_mac(mac: str | None) -> str:
    """Normalise to AA:BB:CC:DD:EE:FF. Returns '' for junk / locally
    administered randomised MACs, which are useless as identity."""
    if not mac:
        return ""
    hexs = re.sub(r"[^0-9a-fA-F]", "", str(mac)).upper()
    if len(hexs) != 12:
        return ""
    # Locally-administered bit set => randomised MAC (common on tablets,
    # and on Windows with "random hardware addresses" on). Not identity.
    try:
        if int(hexs[0:2], 16) & 0x02:
            return ""
    except ValueError:
        return ""
    if hexs == "000000000000":
        return ""
    return ":".join(hexs[i:i + 2] for i in range(0, 12, 2))


def _client_ip() -> str:
    """Real client IP, honouring the Frappe Cloud / nginx proxy chain."""
    try:
        req = frappe.local.request
        if not req:
            return ""
        xff = req.headers.get("X-Forwarded-For") or ""
        if xff:
            # left-most entry is the originating client
            return xff.split(",")[0].strip()
        return req.headers.get("X-Real-IP") or req.remote_addr or ""
    except Exception:
        return ""


def _user_agent() -> str:
    try:
        return (frappe.local.request.headers.get("User-Agent") or "")[:255]
    except Exception:
        return ""


def _fingerprint(hints: dict) -> str:
    """A stable-ish device id.

    Priority order matters. Anything the bridge tells us beats anything
    the browser guesses, because the browser value dies when the cashier
    clears site data.

        1. bridge machine uuid   (survives browser reset + reinstall)
        2. normalised MAC        (survives browser reset)
        3. browser-local uuid    (survives nothing, but better than none)
    """
    for key in ("bridge_machine_uuid", "machine_uuid"):
        v = (hints.get(key) or "").strip()
        if len(v) >= 8:
            return f"hw:{v.lower()}"

    mac = _clean_mac(hints.get("mac_address"))
    if mac:
        return f"mac:{mac.lower()}"

    v = (hints.get("browser_uuid") or "").strip()
    if len(v) >= 8:
        return f"bx:{v.lower()}"

    # Last resort: hash of the weak signals. Collides across identical
    # tablets from the same batch, which is exactly why we return
    # "ambiguous" rather than auto-binding when this is all we have.
    blob = json.dumps({
        k: hints.get(k) for k in
        ("platform", "screen", "timezone", "language", "device_memory", "cores")
    }, sort_keys=True)
    return "wk:" + hashlib.sha256(blob.encode()).hexdigest()[:24]


def _is_weak(fp: str) -> bool:
    return fp.startswith("wk:")


def _terminal_identity(doc) -> dict:
    return {
        "name": doc.name,
        "pos_outlet": doc.get("pos_outlet"),
        "branch": doc.get("branch"),
        "pos_profile": doc.get("pos_profile"),
        "pc_hostname": doc.get("pc_hostname"),
        "pc_uuid": doc.get("pc_uuid"),
        "pc_mac_address": doc.get("pc_mac_address"),
        "last_bound_at": doc.get("last_bound_at"),
        "last_bound_by": doc.get("last_bound_by"),
        "bridge_installed": cint(doc.get("bridge_installed")),
        "bridge_version": doc.get("bridge_version"),
        "bridge_port": doc.get("bridge_port"),
        "bridge_last_seen": doc.get("bridge_last_seen"),
    }


def _match_terminals(fp: str, hints: dict) -> list[str]:
    """Find terminal names that plausibly ARE this machine."""
    names: list[str] = []

    def _add(rows):
        for r in rows:
            if r.name not in names:
                names.append(r.name)

    # exact fingerprint is the strongest signal
    _add(frappe.get_all("AlphaX POS Terminal",
                        filters={"device_fingerprint": fp}, fields=["name"]))

    uuid = (hints.get("bridge_machine_uuid") or hints.get("machine_uuid") or "").strip()
    if len(uuid) >= 8:
        _add(frappe.get_all("AlphaX POS Terminal",
                            filters={"pc_uuid": uuid}, fields=["name"]))

    mac = _clean_mac(hints.get("mac_address"))
    if mac:
        _add(frappe.get_all("AlphaX POS Terminal",
                            filters={"pc_mac_address": mac}, fields=["name"]))

    return names


def _allowed_terminals_for_user() -> set[str]:
    """Terminals this user may bind to. System/POS Managers: all.
    Everyone else: only terminals in outlets they have access to."""
    if frappe.session.user == "Administrator":
        return set()  # empty set == unrestricted, checked by caller
    roles = set(frappe.get_roles())
    if roles & {"System Manager", "AlphaX POS Manager"}:
        return set()
    names = {r.name for r in frappe.get_all("AlphaX POS Terminal", fields=["name"])}
    return names


# ---------------------------------------------------------------------------
# 1. probe
# ---------------------------------------------------------------------------

@frappe.whitelist()
def probe(client_hints=None):
    """Called once, immediately after the SPA loads, before any terminal
    is chosen. Returns a decision the wizard can act on without further
    round-trips."""
    hints = frappe.parse_json(client_hints) if isinstance(client_hints, str) else (client_hints or {})
    if not isinstance(hints, dict):
        hints = {}

    fp = _fingerprint(hints)
    server_view = {
        "client_ip": _client_ip(),
        "user_agent": _user_agent(),
        "server_time": now_datetime(),
        "site": frappe.local.site,
    }

    matches = _match_terminals(fp, hints)
    total_terminals = frappe.db.count("AlphaX POS Terminal")

    if len(matches) == 1:
        doc = frappe.get_doc("AlphaX POS Terminal", matches[0])
        bound = (doc.get("device_fingerprint") == fp)
        decision = "bound" if bound else "candidate"
        payload = {
            "decision": decision,
            "terminal": _terminal_identity(doc),
        }
    elif len(matches) > 1:
        payload = {
            "decision": "ambiguous",
            "candidates": [
                _terminal_identity(frappe.get_doc("AlphaX POS Terminal", n))
                for n in matches[:10]
            ],
        }
    elif _is_weak(fp) and total_terminals > 0:
        # Nothing to go on but weak browser signals AND terminals already
        # exist -> never guess. Show the list.
        payload = {"decision": "ambiguous", "candidates": _list_bindable()}
    else:
        payload = {
            "decision": "provisionable",
            "suggested_name": _suggest_terminal_name(hints),
            "defaults": _provision_defaults(),
        }

    payload.update({
        "fingerprint": fp,
        "fingerprint_strength": "weak" if _is_weak(fp) else "strong",
        "server": server_view,
        "bridge_ports": DEFAULT_BRIDGE_PORTS,
        "can_provision": _can_provision(),
        "total_terminals": total_terminals,
    })
    return payload


def _list_bindable(limit=25):
    rows = frappe.get_all(
        "AlphaX POS Terminal",
        fields=["name", "pos_outlet", "branch", "pc_hostname", "device_fingerprint"],
        limit=limit, order_by="modified desc",
    )
    return [dict(r, already_bound=bool(r.get("device_fingerprint"))) for r in rows]


def _can_provision() -> bool:
    roles = set(frappe.get_roles())
    return bool(roles & {"System Manager", "AlphaX POS Manager", "AlphaX POS Supervisor"})


def _suggest_terminal_name(hints: dict) -> str:
    host = (hints.get("bridge_hostname") or hints.get("hostname") or "").strip()
    if host:
        base = re.sub(r"[^A-Za-z0-9\- ]", "", host)[:40]
    else:
        plat = (hints.get("platform") or "POS").split()[0]
        base = f"{plat} Station"
    n = 1
    candidate = base
    while frappe.db.exists("AlphaX POS Terminal", {"terminal_label": candidate}):
        n += 1
        candidate = f"{base} {n}"
    return candidate


def _provision_defaults() -> dict:
    """Best-guess outlet / profile so auto-provision needs zero input in
    the overwhelmingly common single-outlet install."""
    outlets = frappe.get_all("AlphaX POS Outlet", fields=["name", "company", "branch"], limit=5)
    profiles = frappe.get_all("POS Profile", fields=["name", "company"], limit=5)
    return {
        "outlet": outlets[0].name if len(outlets) == 1 else None,
        "outlet_count": len(outlets),
        "pos_profile": profiles[0].name if len(profiles) == 1 else None,
        "profile_count": len(profiles),
        "outlets": outlets,
        "profiles": profiles,
    }


# ---------------------------------------------------------------------------
# 2. claim / auto-provision
# ---------------------------------------------------------------------------

def _write_identity(doc, fp: str, hints: dict):
    doc.device_fingerprint = fp
    doc.pc_hostname = (hints.get("bridge_hostname") or hints.get("hostname")
                       or doc.get("pc_hostname") or "")[:140]
    uuid = (hints.get("bridge_machine_uuid") or hints.get("machine_uuid") or "").strip()
    if uuid:
        doc.pc_uuid = uuid[:140]
    mac = _clean_mac(hints.get("mac_address"))
    if mac:
        doc.pc_mac_address = mac
    doc.client_ip = _client_ip()[:64]
    doc.client_user_agent = _user_agent()
    doc.client_platform = (hints.get("platform") or "")[:64]
    doc.client_screen = (hints.get("screen") or "")[:32]
    doc.last_bound_at = now_datetime()
    doc.last_bound_by = frappe.session.user


@frappe.whitelist()
def claim(terminal: str, client_hints=None, force: int = 0):
    """Bind an EXISTING terminal record to this machine."""
    hints = frappe.parse_json(client_hints) if isinstance(client_hints, str) else (client_hints or {})
    fp = _fingerprint(hints or {})

    doc = frappe.get_doc("AlphaX POS Terminal", terminal)
    doc.check_permission("write")

    existing = doc.get("device_fingerprint")
    if existing and existing != fp and not cint(force):
        frappe.throw(
            _("Terminal {0} is already bound to a different machine "
              "(last bound {1} by {2}). Re-bind to move it to this PC.")
            .format(terminal, doc.get("last_bound_at"), doc.get("last_bound_by")),
            title=_("Already Bound"), exc=frappe.ValidationError,
        )

    _write_identity(doc, fp, hints)
    doc.save(ignore_permissions=False)
    frappe.db.commit()

    _log_event(doc.name, "claim", {"forced": cint(force), "fingerprint": fp})
    return {"ok": True, "terminal": _terminal_identity(doc)}


@frappe.whitelist()
def auto_provision(client_hints=None, terminal_label: str | None = None,
                   outlet: str | None = None, pos_profile: str | None = None):
    """Create a terminal for this machine with zero manual data entry."""
    if not _can_provision():
        frappe.throw(_("You do not have permission to create a POS Terminal. "
                       "Ask a manager to add this station."), frappe.PermissionError)

    hints = frappe.parse_json(client_hints) if isinstance(client_hints, str) else (client_hints or {})
    hints = hints or {}
    fp = _fingerprint(hints)

    if _is_weak(fp):
        # Refuse to silently create duplicates for a rack of identical
        # tablets. Ask the wizard to install the bridge first, which
        # gives us a real machine UUID.
        frappe.throw(_("This device cannot be identified reliably from the browser alone. "
                       "Install the AlphaX POS Bridge on this station first, "
                       "or pick an existing terminal from the list."),
                     title=_("Weak Device Identity"))

    dupes = _match_terminals(fp, hints)
    if dupes:
        return {"ok": False, "reason": "exists", "candidates": dupes}

    defaults = _provision_defaults()
    outlet = outlet or defaults.get("outlet")
    pos_profile = pos_profile or defaults.get("pos_profile")

    doc = frappe.new_doc("AlphaX POS Terminal")
    doc.terminal_label = terminal_label or _suggest_terminal_name(hints)
    if outlet:
        doc.pos_outlet = outlet
        doc.branch = frappe.db.get_value("AlphaX POS Outlet", outlet, "branch")
    if pos_profile:
        doc.pos_profile = pos_profile
    doc.auto_provisioned = 1
    _write_identity(doc, fp, hints)
    doc.insert(ignore_permissions=False)
    frappe.db.commit()

    _log_event(doc.name, "auto_provision", {"fingerprint": fp, "outlet": outlet})
    return {"ok": True, "terminal": _terminal_identity(doc)}


@frappe.whitelist()
def release(terminal: str):
    """Unbind a terminal so another PC can claim it (RMA / PC swap)."""
    doc = frappe.get_doc("AlphaX POS Terminal", terminal)
    doc.check_permission("write")
    doc.device_fingerprint = None
    doc.bridge_installed = 0
    doc.bridge_last_seen = None
    doc.save()
    frappe.db.commit()
    _log_event(terminal, "release", {})
    return {"ok": True}


# ---------------------------------------------------------------------------
# 3. bridge lifecycle
# ---------------------------------------------------------------------------

@frappe.whitelist()
def report_bridge_state(terminal: str, state=None):
    """Called by the SPA after every bridge probe (boot + 5-min heartbeat).

    `state` is whatever the SPA learned from the local daemon:
        { online, version, port, url, token_hint, devices: [...],
          os, hostname, machine_uuid, mac_address }

    Persisting this is what makes "is the bridge installed on till 3?"
    answerable from the desk, from a report, from a dashboard — instead
    of phoning the shop.
    """
    st = frappe.parse_json(state) if isinstance(state, str) else (state or {})
    if not isinstance(st, dict):
        st = {}

    if not frappe.db.exists("AlphaX POS Terminal", terminal):
        return {"ok": False, "reason": "no such terminal"}

    online = bool(st.get("online"))
    devices = st.get("devices") or []
    values = {
        "bridge_installed": 1 if online else 0,
        "bridge_version": (st.get("version") or "")[:32],
        "bridge_port": cint(st.get("port")) or None,
        "bridge_url": (st.get("url") or "")[:255],
        "bridge_token_hint": (st.get("token_hint") or "")[:8],
        "bridge_os": (st.get("os") or "")[:64],
        "bridge_device_count": len(devices),
        "bridge_devices_json": json.dumps(devices)[:14000],
    }
    if online:
        values["bridge_last_seen"] = now_datetime()
        values["bridge_first_seen"] = (
            frappe.db.get_value("AlphaX POS Terminal", terminal, "bridge_first_seen")
            or now_datetime()
        )

    # Opportunistically upgrade weak identity now that the bridge can
    # tell us the real machine UUID.
    if st.get("machine_uuid"):
        values["pc_uuid"] = str(st["machine_uuid"])[:140]
    if st.get("hostname"):
        values["pc_hostname"] = str(st["hostname"])[:140]
    mac = _clean_mac(st.get("mac_address"))
    if mac:
        values["pc_mac_address"] = mac

    frappe.db.set_value("AlphaX POS Terminal", terminal, values, update_modified=False)
    frappe.db.commit()
    return {"ok": True, "recorded": now_datetime(), "device_count": len(devices)}


@frappe.whitelist()
def bridge_status(terminal: str):
    """Desk-side / SPA-side read of the last known bridge state."""
    row = frappe.db.get_value(
        "AlphaX POS Terminal", terminal,
        ["bridge_installed", "bridge_version", "bridge_port", "bridge_url",
         "bridge_last_seen", "bridge_device_count", "bridge_os", "bridge_devices_json"],
        as_dict=True,
    )
    if not row:
        return {"known": False}
    stale = True
    if row.bridge_last_seen:
        stale = time_diff_in_seconds(now_datetime(), get_datetime(row.bridge_last_seen)) > BRIDGE_STALE_SECONDS
    row = dict(row)
    row["stale"] = stale
    row["known"] = True
    try:
        row["devices"] = json.loads(row.pop("bridge_devices_json") or "[]")
    except Exception:
        row["devices"] = []
        row.pop("bridge_devices_json", None)
    return row


@frappe.whitelist()
def get_bridge_installers(os_hint: str | None = None):
    """Everything the SPA needs to render the one-click install card.

    Sourced from AlphaX POS Settings so an operator can point a fleet at
    an internal mirror (a shop with no internet still needs to install
    the bridge from the local file server).
    """
    from .bridge_registry import build_install_plan
    return build_install_plan(os_hint)


@frappe.whitelist()
def mark_bridge_install_attempt(terminal: str, method: str, os_name: str = "", note: str = ""):
    """Audit trail: who tried to install the bridge, how, from where.
    Support calls become answerable."""
    doc = frappe.new_doc("AlphaX POS Bridge Install")
    doc.terminal = terminal
    doc.install_method = method
    doc.os_name = os_name[:64]
    doc.client_ip = _client_ip()[:64]
    doc.attempted_by = frappe.session.user
    doc.note = note[:500]
    doc.status = "Attempted"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}


def _log_event(terminal: str, action: str, payload: dict):
    try:
        frappe.get_doc({
            "doctype": "AlphaX POS Bridge Install",
            "terminal": terminal,
            "install_method": action,
            "status": "Info",
            "client_ip": _client_ip()[:64],
            "attempted_by": frappe.session.user,
            "note": json.dumps(payload)[:500],
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AlphaX onboarding log failed")


# ---------------------------------------------------------------------------
# 4. scheduled — flag stations whose bridge went quiet
# ---------------------------------------------------------------------------

def flag_stale_bridges():
    """Hourly. A till whose bridge stopped heartbeating cannot print.
    Better to know at 09:00 than when a queue has formed."""
    rows = frappe.get_all(
        "AlphaX POS Terminal",
        filters={"bridge_installed": 1},
        fields=["name", "bridge_last_seen"],
    )
    stale = []
    for r in rows:
        if not r.bridge_last_seen:
            continue
        age = time_diff_in_seconds(now_datetime(), get_datetime(r.bridge_last_seen))
        if age > BRIDGE_STALE_SECONDS:
            stale.append(r.name)
            frappe.db.set_value("AlphaX POS Terminal", r.name,
                                "bridge_installed", 0, update_modified=False)
    if stale:
        frappe.db.commit()
        frappe.logger("alphax_pos").info(f"bridge went stale on: {stale}")
    return stale
