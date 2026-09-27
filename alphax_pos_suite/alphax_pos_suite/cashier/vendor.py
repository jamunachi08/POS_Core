"""
Vendor bundle fetcher for the cashier SPA.

The cashier UI is a Vue 3 SPA. To work on Frappe Cloud (which doesn't
let users SSH in to run `npm install`) and to work *offline forever*
once installed (which is what a real cashier needs), we ship the SPA
source as `.vue` files and load Vue/Pinia/vue-i18n as pre-minified
browser bundles from the app's own `public/dist/vendor/` folder.

This module fetches those bundles. It runs once after install via:

    bench --site <site> execute alphax_pos_suite.alphax_pos_suite.cashier.vendor.fetch_all

It uses Python's stdlib `urllib.request` so it adds no dependency.
It tries a list of mirrors (unpkg, jsdelivr, cdnjs) in order so a single
CDN being slow or unreachable doesn't break the install.

Once the bundles are in `public/dist/vendor/`, the cashier loader
serves them from `/assets/alphax_pos_suite/dist/vendor/...` — local
file, instant load, no internet needed at runtime.

If for any reason the bundles aren't there at runtime (e.g., owner forgot
to run this command), the cashier loader falls back to fetching from CDN
on first page load and caches them in IndexedDB. Either way the cashier
sees a working register; this module just makes the experience faster
and offline-resilient.
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

import frappe

log = logging.getLogger("alphax.cashier.vendor")


# Library versions are pinned. Bumping any of these is a deliberate
# release decision. Don't auto-update.
VUE_VERSION       = "3.5.13"
PINIA_VERSION     = "3.0.3"
VUE_I18N_VERSION  = "9.14.0"


@dataclass(frozen=True)
class Bundle:
    """A single vendor JS bundle to fetch and stash in public/dist/vendor/."""
    name: str               # filename to write
    description: str        # for log messages
    urls: tuple[str, ...]   # CDN mirrors, tried in order
    min_size: int           # sanity-check; reject if smaller than this
    max_size: int           # sanity-check; reject if larger than this
    expected_marker: str    # a string that MUST appear in the bundle
                            # (defends against fetching an HTML error page)


BUNDLES: tuple[Bundle, ...] = (
    Bundle(
        name="vue.global.prod.js",
        description=f"Vue {VUE_VERSION} (with runtime template compiler)",
        urls=(
            f"https://unpkg.com/vue@{VUE_VERSION}/dist/vue.global.prod.js",
            f"https://cdn.jsdelivr.net/npm/vue@{VUE_VERSION}/dist/vue.global.prod.js",
            f"https://cdnjs.cloudflare.com/ajax/libs/vue/{VUE_VERSION}/vue.global.prod.min.js",
        ),
        min_size=80_000,    # real Vue bundle is ~110KB, never under 80KB
        max_size=300_000,
        expected_marker="Vue",
    ),
    Bundle(
        name="pinia.iife.prod.js",
        description=f"Pinia {PINIA_VERSION} (state management)",
        urls=(
            f"https://unpkg.com/pinia@{PINIA_VERSION}/dist/pinia.iife.prod.js",
            f"https://cdn.jsdelivr.net/npm/pinia@{PINIA_VERSION}/dist/pinia.iife.prod.js",
        ),
        min_size=4_000,     # Pinia 3.x iife.prod is ~5KB
        max_size=60_000,
        expected_marker="Pinia",
    ),
    Bundle(
        name="vue-i18n.global.prod.js",
        description=f"vue-i18n {VUE_I18N_VERSION} (bilingual EN/AR)",
        urls=(
            f"https://unpkg.com/vue-i18n@{VUE_I18N_VERSION}/dist/vue-i18n.global.prod.js",
            f"https://cdn.jsdelivr.net/npm/vue-i18n@{VUE_I18N_VERSION}/dist/vue-i18n.global.prod.js",
        ),
        min_size=30_000,
        max_size=200_000,
        expected_marker="VueI18n",
    ),
)


def _vendor_dir() -> str:
    """Absolute path to public/dist/vendor inside the installed app."""
    app_path = frappe.get_app_path("alphax_pos_suite")
    target = os.path.join(app_path, "public", "dist", "vendor")
    os.makedirs(target, exist_ok=True)
    return target


def _fetch_one_url(url: str, timeout: float = 30.0) -> Optional[bytes]:
    """Try a single URL. Returns the bytes on 200, None on any error."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AlphaX-POS-Vendor-Fetcher/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                log.warning("Vendor fetch %s -> HTTP %s", url, resp.status)
                return None
            return resp.read()
    except urllib.error.URLError as e:
        log.warning("Vendor fetch %s failed: %s", url, e)
        return None
    except Exception as e:
        log.warning("Vendor fetch %s unexpected error: %s", url, e)
        return None


def _fetch_bundle(bundle: Bundle) -> Optional[bytes]:
    """Try every mirror for a bundle. Returns valid bytes or None."""
    for url in bundle.urls:
        data = _fetch_one_url(url)
        if data is None:
            continue

        # Size sanity check — guards against fetching a small error page.
        size = len(data)
        if size < bundle.min_size or size > bundle.max_size:
            log.warning(
                "Vendor fetch %s returned %d bytes, expected %d-%d. Skipping.",
                url, size, bundle.min_size, bundle.max_size,
            )
            continue

        # Marker check — guards against fetching a CDN error HTML page
        # that happens to be the right size.
        try:
            text_head = data[:5000].decode("utf-8", errors="ignore")
        except Exception:
            text_head = ""
        if bundle.expected_marker not in text_head and bundle.expected_marker not in data[:50_000].decode("utf-8", errors="ignore"):
            log.warning(
                "Vendor fetch %s missing expected marker %r. Skipping.",
                url, bundle.expected_marker,
            )
            continue

        # All checks pass.
        return data

    return None


def _write_bundle(bundle: Bundle, data: bytes, target_dir: str) -> dict:
    """Write a bundle to disk. Returns a result dict."""
    target_path = os.path.join(target_dir, bundle.name)
    sha256 = hashlib.sha256(data).hexdigest()

    # Atomic write: write to .tmp, then rename. Avoids leaving a
    # half-written file if something interrupts the process.
    tmp_path = target_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, target_path)

    return {
        "name":   bundle.name,
        "ok":     True,
        "size":   len(data),
        "sha256": sha256,
        "path":   target_path,
    }


def _check_existing(bundle: Bundle, target_dir: str) -> Optional[dict]:
    """If the bundle already exists locally and looks valid, return its
    info dict; otherwise None (signaling 'fetch please')."""
    target_path = os.path.join(target_dir, bundle.name)
    if not os.path.exists(target_path):
        return None
    try:
        size = os.path.getsize(target_path)
        if size < bundle.min_size or size > bundle.max_size:
            return None
        with open(target_path, "rb") as f:
            head = f.read(50_000).decode("utf-8", errors="ignore")
        if bundle.expected_marker not in head:
            return None
        with open(target_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        return {
            "name":     bundle.name,
            "ok":       True,
            "size":     size,
            "sha256":   sha256,
            "path":     target_path,
            "cached":   True,   # was already there; we didn't re-fetch
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def fetch_all(force: bool = False) -> dict:
    """Fetch every vendor bundle into public/dist/vendor/.

    Args:
        force: if True, re-fetch even if the bundle already exists locally.

    Returns:
        {
            "ok": True/False,
            "vendor_dir": "/path/to/public/dist/vendor",
            "results": [ { "name": "...", "ok": True, "size": N, "sha256": ... }, ... ],
            "summary": "3/3 bundles installed",
        }

    This function is safe to run repeatedly — already-present valid
    bundles are skipped unless force=True. It never raises; it always
    returns a structured result so the caller can decide what to do.
    """
    target_dir = _vendor_dir()
    results: list[dict] = []
    successes = 0

    for bundle in BUNDLES:
        # Cached?
        if not force:
            cached = _check_existing(bundle, target_dir)
            if cached:
                successes += 1
                results.append(cached)
                continue

        # Fetch fresh.
        data = _fetch_bundle(bundle)
        if data is None:
            results.append({
                "name":   bundle.name,
                "ok":     False,
                "error":  "all mirrors failed; check internet access on this server",
            })
            continue

        try:
            written = _write_bundle(bundle, data, target_dir)
            successes += 1
            results.append(written)
        except Exception as e:
            results.append({
                "name":   bundle.name,
                "ok":     False,
                "error":  f"could not write: {e}",
            })

    return {
        "ok":         successes == len(BUNDLES),
        "vendor_dir": target_dir,
        "results":    results,
        "summary":    f"{successes}/{len(BUNDLES)} bundles installed at {target_dir}",
    }


@frappe.whitelist()
def fetch_vendor_bundles(force: int = 0) -> dict:
    """Frappe-callable wrapper for fetch_all.

    Usage from bench shell:
        bench --site <site> execute alphax_pos_suite.alphax_pos_suite.cashier.vendor.fetch_vendor_bundles

    Or with force re-fetch:
        bench --site <site> execute alphax_pos_suite.alphax_pos_suite.cashier.vendor.fetch_vendor_bundles --kwargs '{"force": 1}'
    """
    result = fetch_all(force=bool(int(force)))
    if result["ok"]:
        print(f"✓ {result['summary']}")
    else:
        print(f"✗ {result['summary']}")
        for r in result["results"]:
            if not r.get("ok"):
                print(f"  {r['name']}: {r.get('error', 'unknown error')}")
    return result


@frappe.whitelist(allow_guest=False)
def vendor_status() -> dict:
    """Lightweight status check the cashier loader can call to know
    whether bundles are present locally.

    Returns:
        {
            "ok": True/False,                # all bundles present and valid
            "bundles": {
                "vue.global.prod.js":      { "present": True, "size": 110000 },
                "pinia.iife.prod.js":      { "present": True, "size": 12000 },
                "vue-i18n.global.prod.js": { "present": False },
            }
        }
    """
    target_dir = _vendor_dir()
    out: dict = {"ok": True, "bundles": {}}
    for bundle in BUNDLES:
        cached = _check_existing(bundle, target_dir)
        if cached:
            out["bundles"][bundle.name] = {
                "present": True,
                "size":    cached["size"],
            }
        else:
            out["ok"] = False
            out["bundles"][bundle.name] = {"present": False}
    return out
