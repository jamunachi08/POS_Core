"""
AlphaX POS — bridge installer catalogue. (v2, self-hosted first)

Answers "the bridge isn't on this machine, how do I get it here?" with a
plan tailored to the detected OS.

Source precedence:

  1. BUNDLED  — the kit vendored into this app at
                ``public/bridge/``, served from this site. Default when
                present. Works in a shop with no route to GitHub, and the
                bridge version can never drift from the POS version that
                shipped it.
  2. MIRROR   — ``bridge_download_base_url`` in AlphaX POS Settings, for
                operators who host installers on an internal file server.
  3. GITHUB   — public release URL. Fallback for a POS build where nobody
                ran the vendoring script.

Regardless of source, the plan hands the installer a ``--pair-token`` and
``--pair-url`` so the bridge writes its own config and calls home. The
cashier never copies a token between screens.
"""

from __future__ import annotations

import secrets
from urllib.parse import quote

import frappe
from frappe.utils import cint, get_url

DEFAULT_GITHUB_BASE = ("https://github.com/jamunachi08/"
                       "alphax-pos-bridge-v15.5.0/releases/latest/download")
DEFAULT_PORT = 8420

# Filenames for the GitHub fallback path only. The bundled kit is one
# cross-platform zip, named by the manifest.
ARTIFACTS = {
    "windows": "AlphaX-POS-Bridge-Setup-{version}.exe",
    "macos":   "AlphaX-POS-Bridge-{version}.pkg",
    "debian":  "alphax-pos-bridge_{version}_amd64.deb",
    "linux":   "AlphaX-POS-Bridge-{version}-x86_64.AppImage",
}

PLATFORM_LABEL = {
    "windows": "Windows 10 / 11",
    "macos":   "macOS 12+",
    "debian":  "Ubuntu / Debian",
    "linux":   "Linux",
}


def _settings() -> dict:
    try:
        s = frappe.get_cached_doc("AlphaX POS Settings")
    except Exception:
        return {}
    return {
        "base_url": (s.get("bridge_download_base_url") or "").rstrip("/"),
        "version": s.get("bridge_target_version") or "",
        "port": cint(s.get("bridge_default_port")) or DEFAULT_PORT,
        "allow_oneliner": cint(
            s.get("bridge_allow_oneliner")
            if s.get("bridge_allow_oneliner") is not None else 1),
        "lan_access": cint(s.get("bridge_lan_access") or 0),
    }


def normalise_os(os_hint: str | None) -> str:
    h = (os_hint or "").lower()
    if "win" in h:
        return "windows"
    if "mac" in h or "darwin" in h or "iphone" in h or "ipad" in h:
        return "macos"
    if "ubuntu" in h or "debian" in h:
        return "debian"
    if "linux" in h or "android" in h or "cros" in h:
        return "linux"
    return "windows"


def issue_pairing_token(ttl_minutes: int = 30) -> str:
    """One-shot token the bridge presents back to prove it is the daemon
    we just told this cashier to install. Cache, not DB — short-lived by
    design."""
    tok = secrets.token_urlsafe(24)
    frappe.cache().set_value(f"alphax_bridge_pair:{tok}",
                             {"user": frappe.session.user, "site": frappe.local.site},
                             expires_in_sec=ttl_minutes * 60)
    return tok


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def build_install_plan(os_hint: str | None = None) -> dict:
    from .bridge_dist import bundled_bridge_info

    cfg = _settings()
    plat = normalise_os(os_hint)
    port = cfg.get("port") or DEFAULT_PORT
    site = get_url().rstrip("/")

    bundled = bundled_bridge_info()
    source = ("bundled" if bundled["available"]
              else ("mirror" if cfg.get("base_url") else "github"))
    version = (bundled["version"] if bundled["available"]
               else (cfg.get("version") or "15.5.3"))

    pair_token = issue_pairing_token()
    methods = []

    if source == "bundled":
        # ONE file. The endpoint generates a script with the site URL,
        # port and token already inside, so there is nothing to fill in.
        qs = (f"os_name={plat}&port={port}"
              f"&lan_access={cint(cfg.get('lan_access'))}")
        methods.append({
            "id": "installer",
            "rank": 1,
            "label": frappe._("Download and run"),
            "sublabel": frappe._("{0} — installs from this site").format(PLATFORM_LABEL[plat]),
            "download_url": (f"{site}/api/method/alphax_pos_suite.alphax_pos_suite"
                             f".onboarding.bridge_dist.bootstrap?{qs}"),
            "filename": (f"Install-AlphaX-Bridge-{version}.bat" if plat == "windows"
                         else f"install-alphax-bridge-{version}.sh"),
            "silent_args": "",
            "steps": _bundled_steps(plat),
            "self_hosted": True,
        })
    else:
        base = cfg.get("base_url") or DEFAULT_GITHUB_BASE
        artifact = ARTIFACTS[plat].format(version=version)
        methods.append({
            "id": "installer",
            "rank": 1,
            "label": frappe._("Download installer"),
            "sublabel": PLATFORM_LABEL[plat],
            "download_url": f"{base}/{artifact}",
            "filename": artifact,
            "silent_args": _silent_args(plat, port, pair_token, site),
            "steps": _external_steps(plat),
            "self_hosted": False,
        })

        if cfg.get("allow_oneliner", 1):
            methods.append({
                "id": "oneliner",
                "rank": 2,
                "label": frappe._("Run one command"),
                "sublabel": frappe._("If downloads are blocked by IT policy"),
                "shell": "powershell" if plat == "windows" else "bash",
                "command": _oneliner(plat, base, port, pair_token, site),
                "steps": _oneliner_steps(plat),
            })

    methods.append({
        "id": "manual",
        "rank": 3,
        "label": frappe._("Install with pip"),
        "sublabel": frappe._("For IT staff"),
        "shell": "bash",
        "command": (f"pip install alphax-pos-bridge[all] && "
                    f"alphax-bridge-wizard --port {port} "
                    f"--pair-url {site} --pair-token {pair_token}"),
        "steps": [],
    })

    return {
        "detected_os": plat,
        "os_label": PLATFORM_LABEL[plat],
        "version": version,
        "source": source,
        "bundled": bundled,
        "port": port,
        "probe_urls": [f"http://127.0.0.1:{port}/", f"http://localhost:{port}/"],
        "pair_token": pair_token,
        "pair_url": site,
        "pair_expires_minutes": 30,
        "methods": sorted(methods, key=lambda m: m["rank"]),
    }


def _bundled_steps(plat) -> list[str]:
    if plat == "windows":
        return [
            frappe._("Click Download. One small file lands in Downloads."),
            frappe._("Double-click it. If Windows warns you, choose More info then Run anyway."),
            frappe._("Wait — it installs everything, including Python if needed."),
            frappe._("This screen detects the bridge on its own."),
        ]
    return [
        frappe._("Click Download."),
        frappe._("Open a terminal in your Downloads folder and run: bash install-alphax-bridge-*.sh"),
        frappe._("This screen detects the bridge on its own."),
    ]


def _external_steps(plat) -> list[str]:
    if plat == "windows":
        return [
            frappe._("Click Download."),
            frappe._("Double-click the installer. Choose More info then Run anyway if warned."),
            frappe._("Accept the defaults — autostart is already ticked."),
            frappe._("Return here; the bridge is detected automatically."),
        ]
    return [
        frappe._("Click Download and run the installer."),
        frappe._("Return here; the bridge is detected automatically."),
    ]


def _silent_args(plat, port, token, url) -> str:
    q = f"--port {port} --pair-url {quote(url, safe=':/')} --pair-token {token}"
    if plat == "windows":
        return f"/VERYSILENT /MERGETASKS=\"autostart\" /BRIDGEARGS=\"{q}\""
    return q


def _oneliner(plat, base, port, token, url) -> str:
    if plat == "windows":
        return ("powershell -ExecutionPolicy Bypass -Command \"iwr "
                f"{base}/bootstrap.ps1 -UseBasicParsing | iex\" "
                f"-Port {port} -PairUrl {url} -PairToken {token}")
    return (f"curl -fsSL {base}/bootstrap.sh | bash -s -- "
            f"--port {port} --pair-url {url} --pair-token {token}")


def _oneliner_steps(plat) -> list[str]:
    term = (frappe._("PowerShell (right-click Start)") if plat == "windows"
            else frappe._("Terminal"))
    return [
        frappe._("Click Copy."),
        frappe._("Open {0}.").format(term),
        frappe._("Paste and press Enter."),
        frappe._("Return here; the bridge is detected automatically."),
    ]


# ---------------------------------------------------------------------------
# pairing loop
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def confirm_pairing(pair_token: str, bridge_info=None):
    """Called by the BRIDGE once installed, with the token baked into its
    config. Lets the wizard's spinner resolve before the cashier even
    switches back to the browser."""
    cached = frappe.cache().get_value(f"alphax_bridge_pair:{pair_token}")
    if not cached:
        return {"ok": False, "reason": "expired"}
    info = (frappe.parse_json(bridge_info) if isinstance(bridge_info, str)
            else (bridge_info or {}))
    frappe.cache().set_value(f"alphax_bridge_paired:{pair_token}",
                             {"info": info, "at": frappe.utils.now()},
                             expires_in_sec=1800)
    return {"ok": True}


@frappe.whitelist()
def poll_pairing(pair_token: str):
    v = frappe.cache().get_value(f"alphax_bridge_paired:{pair_token}")
    return {"paired": bool(v), "info": (v or {}).get("info") or {}}
