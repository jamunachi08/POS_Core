"""
AlphaX POS — self-hosted bridge distribution.

The bridge installer ships INSIDE this app, under
``alphax_pos_suite/public/bridge/``, which Frappe serves statically at
``/assets/alphax_pos_suite/bridge/``. Consequences:

  - A shop with no route to GitHub still installs the bridge. Many retail
    LANs allow the ERP host and nothing else.
  - The bridge version is pinned to the POS version that shipped it. No
    ``bridge_target_version`` to drift out of sync, no 404 when a release
    asset is renamed.
  - Deploying the POS deploys the bridge installer. One artefact.

The kit is a ~72 KB zip because it installs from a Python wheel and
fetches Python itself if absent — not a 40 MB frozen binary. That is what
makes vendoring it practical.

One-click means ONE file. The cashier should not download a zip, find it,
extract it, hunt for a .bat and read a readme. So ``bootstrap()`` returns
a tiny personalised script with the site URL, port and pairing token
already baked in. Double-click, done — it fetches the kit from this site,
unpacks to temp, and runs the installer with the right arguments.
"""

from __future__ import annotations

import hashlib
import json
import os

import frappe
from frappe import _
from frappe.utils import cint, get_url

MANIFEST_PATH = "alphax_pos_suite/public/bridge/manifest.json"
ASSET_BASE = "/assets/alphax_pos_suite/bridge"


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

def _manifest_file() -> str:
    return os.path.join(frappe.get_app_path("alphax_pos_suite"),
                        "public", "bridge", "manifest.json")


def read_manifest() -> dict:
    """What bridge version this POS build ships, and under what filename.

    Written by ``scripts/sync_bridge_kit.ps1`` at vendoring time so the
    two repos can never silently disagree about the version.
    """
    path = _manifest_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "bridge manifest unreadable")
        return {}


def kit_available() -> bool:
    m = read_manifest()
    if not m.get("kit_file"):
        return False
    return os.path.exists(os.path.join(
        frappe.get_app_path("alphax_pos_suite"), "public", "bridge", m["kit_file"]))


@frappe.whitelist()
def bundled_bridge_info() -> dict:
    m = read_manifest()
    available = kit_available()
    return {
        "available": available,
        "version": m.get("version") or "",
        "kit_file": m.get("kit_file") or "",
        "kit_url": f"{ASSET_BASE}/{m['kit_file']}" if available else "",
        "sha256": m.get("sha256") or "",
        "built_at": m.get("built_at") or "",
        "source_tag": m.get("source_tag") or "",
    }


# ---------------------------------------------------------------------------
# bootstrap script generation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def bootstrap(os_name: str = "windows", port: int = 8420,
              lan_access: int = 0, terminal: str | None = None):
    """Return a one-file installer personalised for this site and session.

    The response is a downloadable script, not JSON. The wizard triggers
    it with a plain link so the browser's own download handling applies.
    """
    from .bridge_registry import issue_pairing_token, normalise_os

    info = bundled_bridge_info()
    if not info["available"]:
        frappe.throw(_("No bridge installer is bundled with this POS build. "
                       "Run scripts/sync_bridge_kit.ps1 and redeploy."))

    plat = normalise_os(os_name)
    token = issue_pairing_token()
    site = get_url().rstrip("/")
    kit_url = f"{site}{info['kit_url']}"
    port = cint(port) or 8420

    if plat == "windows":
        body = _windows_bootstrap(kit_url, info, port, cint(lan_access), site, token)
        filename = f"Install-AlphaX-Bridge-{info['version']}.bat"
        mimetype = "application/bat"
    else:
        body = _posix_bootstrap(kit_url, info, port, cint(lan_access), site, token)
        filename = f"install-alphax-bridge-{info['version']}.sh"
        mimetype = "application/x-sh"

    frappe.local.response.filename = filename
    frappe.local.response.filecontent = body.encode("utf-8")
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"

    if terminal:
        _note_attempt(terminal, plat, info["version"])

    return


def _note_attempt(terminal, plat, version):
    try:
        from .api import mark_bridge_install_attempt
        mark_bridge_install_attempt(terminal, "bundled_bootstrap", plat,
                                    f"bridge {version} from site bundle")
    except Exception:
        pass


def _windows_bootstrap(kit_url, info, port, lan, site, token) -> str:
    lan_flag = " -LanAccess" if lan else ""
    # A .bat wrapper rather than a bare .ps1: double-clicking a .ps1 opens
    # Notepad on a default Windows install, which reads as "the download
    # is broken" to a cashier. The .bat shells to PowerShell itself.
    return f"""@echo off
title AlphaX POS Bridge Setup
echo.
echo   AlphaX POS Bridge {info['version']}
echo   from {site}
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$tmp = Join-Path $env:TEMP ('alphax-bridge-' + [guid]::NewGuid().ToString('N').Substring(0,8));" ^
  "New-Item -ItemType Directory -Force -Path $tmp | Out-Null;" ^
  "$zip = Join-Path $tmp 'kit.zip';" ^
  "Write-Host 'Downloading the bridge...';" ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "Invoke-WebRequest -Uri '{kit_url}' -OutFile $zip -UseBasicParsing;" ^
  "$want = '{info['sha256']}';" ^
  "if ($want) {{ $got = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower();" ^
  "  if ($got -ne $want) {{ throw ('Download is corrupt. Expected ' + $want + ' got ' + $got) }} }};" ^
  "Write-Host 'Unpacking...';" ^
  "Expand-Archive -Path $zip -DestinationPath $tmp -Force;" ^
  "$ps1 = Get-ChildItem -Path $tmp -Filter 'install.ps1' -Recurse | Select-Object -First 1;" ^
  "if (-not $ps1) {{ throw 'installer not found inside the kit' }};" ^
  "& $ps1.FullName -Port {port}{lan_flag} -PairUrl '{site}' -PairToken '{token}';" ^
  "Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue"
echo.
if errorlevel 1 (
  echo   Setup did not complete. Send the messages above to support.
) else (
  echo   Done. Return to the POS screen - it detects the bridge automatically.
)
echo.
pause
"""


def _posix_bootstrap(kit_url, info, port, lan, site, token) -> str:
    lan_flag = " --lan-access" if lan else ""
    return f"""#!/usr/bin/env bash
# AlphaX POS Bridge {info['version']} — from {site}
set -euo pipefail

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading the bridge..."
curl -fsSL "{kit_url}" -o "$TMP/kit.zip"

WANT="{info['sha256']}"
if [ -n "$WANT" ]; then
  if command -v sha256sum >/dev/null; then
    GOT="$(sha256sum "$TMP/kit.zip" | cut -d' ' -f1)"
  else
    GOT="$(shasum -a 256 "$TMP/kit.zip" | cut -d' ' -f1)"
  fi
  [ "$GOT" = "$WANT" ] || {{ echo "Download is corrupt."; exit 1; }}
fi

echo "Unpacking..."
unzip -q "$TMP/kit.zip" -d "$TMP"

SH="$(find "$TMP" -name 'install-linux.sh' -o -name 'Install AlphaX Bridge.command' | head -1)"
[ -n "$SH" ] || {{ echo "installer not found inside the kit"; exit 1; }}
chmod +x "$SH"

"$SH" --port {port}{lan_flag} --pair-url "{site}" --pair-token "{token}"

echo "Done. Return to the POS screen - it detects the bridge automatically."
"""


# ---------------------------------------------------------------------------
# integrity check, surfaced in the desk
# ---------------------------------------------------------------------------

@frappe.whitelist()
def verify_bundle() -> dict:
    """Confirm the vendored kit matches its manifest hash. Cheap enough to
    run from a health-check page; catches a truncated git-lfs fetch or a
    partial deploy."""
    m = read_manifest()
    if not m.get("kit_file"):
        return {"ok": False, "reason": "no manifest"}

    path = os.path.join(frappe.get_app_path("alphax_pos_suite"),
                        "public", "bridge", m["kit_file"])
    if not os.path.exists(path):
        return {"ok": False, "reason": "kit file missing", "expected": m["kit_file"]}

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()

    expected = (m.get("sha256") or "").lower()
    return {
        "ok": (not expected) or digest == expected,
        "version": m.get("version"),
        "sha256": digest,
        "expected": expected,
        "size": os.path.getsize(path),
    }
