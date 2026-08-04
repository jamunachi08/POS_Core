"""
SPA asset fallback + asset-pipeline diagnostics.

The problem this solves
=======================

The cashier SPA ships as plain files under
`public/dist/vendor/cashier/` and is normally served by nginx from
`/assets/alphax_pos_suite/dist/vendor/cashier/...`.

On Frappe Cloud we have repeatedly seen deploys where the app code is
live (desk pages work — they're served through Frappe itself) but the
`/assets` path 404s for these files, bricking the register with
"Failed to load .../sfc-loader.js" even though the files are committed
to the repo and present in the deployed image. We don't control FC's
asset pipeline, so instead of guessing, the register now has a second
supply line:

    /api/method/...cashier.assets.spa_asset?path=cashier/sfc-loader.js
    /api/method/...cashier.assets.spa_manifest

These read the files straight from the installed app package via
Python — completely bypassing bench build, symlinks, and nginx asset
serving. If Frappe can execute this module, it can serve these files.

The page loader tries `/assets` first (fast, cacheable) and falls back
to these endpoints only when that fails, so a healthy site never pays
the API cost.

Security
========

Read-only serving of files that are ALREADY public web assets — there
is nothing sensitive here. We still enforce:

- login required (no `allow_guest`; the cashier is a desk page anyway),
- the resolved path must stay inside `public/dist/vendor/`,
- extension allow-list,
- no symlink escapes (realpath containment check).
"""
from __future__ import annotations

import json
import os

import frappe

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------
# On a healthy bench, frappe.get_app_path() points at the git clone in
# apps/ and everything under public/ is there. On Frappe Cloud we have
# OBSERVED (asset_health, v15.6.2, neotectest) a split-brain state:
# Python modules import fine but public/dist is absent at get_app_path —
# consistent with the app module resolving to a data-stripped
# site-packages copy while the full git clone sits in bench/apps/.
#
# So we don't trust any single root. We enumerate every plausible one
# and serve from the first that actually contains the SPA.

_PROBE = os.path.join("cashier", "sfc-loader.js")
_VENDOR_ROOT = None
_PAYLOAD_ZIP = None  # lazily-opened zipfile.ZipFile over the embedded payload


def _payload_zip():
    """The embedded SPA payload (alphax_pos_suite/spa_payload.py) as an
    open in-memory zip, or None if unavailable.

    This is the root of last resort: a complete copy of the vendor tree
    baked into a single short-path .py file, immune to the Windows
    long-path failures that twice deleted the real tree from the repo.
    If Python imports, this serves."""
    global _PAYLOAD_ZIP
    if _PAYLOAD_ZIP is None:
        try:
            import io
            import zipfile
            from alphax_pos_suite.spa_payload import payload_bytes
            _PAYLOAD_ZIP = zipfile.ZipFile(io.BytesIO(payload_bytes()))
        except Exception:
            _PAYLOAD_ZIP = False
    return _PAYLOAD_ZIP or None


def _candidate_roots():
    """Yield possible .../public/dist/vendor directories, best-first."""
    seen = set()

    def _push(base):
        if not base:
            return None
        root = os.path.realpath(os.path.join(base, "public", "dist", "vendor"))
        if root in seen:
            return None
        seen.add(root)
        return root

    # 1. Frappe's own idea of the app path.
    try:
        r = _push(frappe.get_app_path("alphax_pos_suite"))
        if r:
            yield r
    except Exception:
        pass

    # 2. Where the Python package actually lives. As of v15.6.3 public/
    #    sits at the PACKAGE ROOT (Frappe's expected layout); the inner
    #    module dir is probed too for any stale pre-restructure deploy.
    try:
        import alphax_pos_suite as _pkg
        pkg_dir = os.path.dirname(os.path.abspath(_pkg.__file__))
        for base in (pkg_dir, os.path.join(pkg_dir, "alphax_pos_suite")):
            r = _push(base)
            if r:
                yield r
    except Exception:
        pass

    # 3. The bench's git clone — present on every bench-managed install,
    #    and on Frappe Cloud this is the copy that is guaranteed complete.
    try:
        bench_apps = os.path.join(
            frappe.utils.get_bench_path(), "apps", "alphax_pos_suite", "alphax_pos_suite"
        )
        r = _push(bench_apps)
        if r:
            yield r
    except Exception:
        pass


def _vendor_root() -> str:
    """First candidate root that actually contains the SPA probe file.
    Falls back to the first candidate (so error messages carry a real
    path) if none qualify."""
    global _VENDOR_ROOT
    if _VENDOR_ROOT is None:
        first = None
        for root in _candidate_roots():
            if first is None:
                first = root
            if os.path.isfile(os.path.join(root, _PROBE)):
                _VENDOR_ROOT = root
                break
        else:
            _VENDOR_ROOT = first or "/nonexistent"
    return _VENDOR_ROOT

_ALLOWED_EXTENSIONS = {".js", ".css", ".vue", ".json", ".map", ".svg", ".woff2", ".png"}

# The manifest bundles every file the SPA needs after the two
# bootstrap scripts. Keep this list tight — it's read on every
# fallback boot.
_MANIFEST_DIRS = ("cashier/sfc",)
_BOOTSTRAP_FILES = ("cashier/sfc-loader.js", "cashier/main.js")


def _safe_resolve(rel_path: str) -> str:
    """Resolve a vendor-relative path, rejecting anything that escapes
    the vendor root or has a disallowed extension."""
    if not rel_path or not isinstance(rel_path, str):
        frappe.throw("Invalid path")
    root = _vendor_root()
    full = os.path.realpath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep):
        frappe.throw("Invalid path")
    _, ext = os.path.splitext(full)
    if ext.lower() not in _ALLOWED_EXTENSIONS:
        frappe.throw("Invalid file type")
    if not os.path.isfile(full):
        frappe.throw(f"Not found: {rel_path}", frappe.DoesNotExistError)
    return full


_CONTENT_TYPES = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".vue": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
}


@frappe.whitelist()
def spa_asset(path: str):
    """Return one vendor file's text content, JSON-wrapped.

    JSON wrapping (rather than a raw download response) sidesteps every
    content-type / content-disposition edge case: the page loader takes
    `message.content` and injects it as an inline <script> or <style>,
    which browsers execute without complaint.
    """
    _, ext = os.path.splitext(path)
    ctype = _CONTENT_TYPES.get(ext.lower(), "text/plain")
    try:
        full = _safe_resolve(path)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content, "content_type": ctype}
    except Exception:
        # Filesystem miss → embedded payload (see _payload_zip docstring).
        z = _payload_zip()
        if z is not None and ext.lower() in _ALLOWED_EXTENSIONS:
            norm = path.replace("\\", "/").lstrip("/")
            if norm in z.namelist():
                content = z.read(norm).decode("utf-8", errors="replace")
                return {"path": path, "content": content, "content_type": ctype, "source": "embedded"}
        raise


@frappe.whitelist()
def spa_manifest():
    """Return EVERY SPA source file in one payload.

    One round-trip instead of ~45. The client seeds the SFC loader's
    source cache with this, so the register boots at full speed even
    when /assets is completely dead.
    """
    root = _vendor_root()
    files = {}
    for rel_dir in _MANIFEST_DIRS:
        base = os.path.realpath(os.path.join(root, rel_dir))
        if not base.startswith(root) or not os.path.isdir(base):
            continue
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                _, ext = os.path.splitext(name)
                if ext.lower() not in _ALLOWED_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                try:
                    with open(full, encoding="utf-8") as f:
                        files[rel] = f.read()
                except (UnicodeDecodeError, OSError):
                    continue
    for rel in _BOOTSTRAP_FILES:
        try:
            full = _safe_resolve(rel)
            with open(full, encoding="utf-8") as f:
                files[rel] = f.read()
        except Exception:
            pass

    if not files:
        # No filesystem root has the SPA (the twice-observed Windows
        # long-path repo loss) — serve the complete tree from the
        # embedded payload instead.
        z = _payload_zip()
        if z is not None:
            for norm in z.namelist():
                _, ext = os.path.splitext(norm)
                if ext.lower() not in _ALLOWED_EXTENSIONS:
                    continue
                if not (norm in _BOOTSTRAP_FILES or any(norm.startswith(d + "/") for d in _MANIFEST_DIRS)):
                    continue
                try:
                    files[norm] = z.read(norm).decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if files:
                return {"count": len(files), "files": files, "source": "embedded"}

    return {"count": len(files), "files": files}


@frappe.whitelist()
def asset_health():
    """Diagnostics for the asset supply lines, shown on the error card.

    v2 (after the neotectest split-brain finding): enumerates EVERY
    candidate root with its probe result, plus where the Python package
    actually imports from — enough to distinguish "repo missing files"
    from "site-packages copy stripped of data" from "assets symlink
    broken" at a glance.
    """
    checks = {"roots": []}
    for root in _candidate_roots():
        checks["roots"].append({
            "path": root,
            "exists": os.path.isdir(root),
            "has_spa": os.path.isfile(os.path.join(root, _PROBE)),
        })
    chosen = _vendor_root()
    checks["chosen_root"] = chosen
    checks["chosen_has_spa"] = os.path.isfile(os.path.join(chosen, _PROBE))

    try:
        import alphax_pos_suite as _pkg
        checks["package_file"] = os.path.abspath(_pkg.__file__)
    except Exception as e:
        checks["package_file"] = f"error: {e}"

    try:
        assets_dir = os.path.realpath(os.path.join(frappe.utils.get_bench_path(), "sites", "assets"))
        link = os.path.join(assets_dir, "alphax_pos_suite")
        kind = (
            "symlink" if os.path.islink(link)
            else "dir" if os.path.isdir(link)
            else "missing"
        )
        checks["sites_assets_link"] = {"path": link, "kind": kind}
        assets_sample = os.path.join(link, "dist", "vendor", "cashier", "sfc-loader.js")
        checks["assets_sample_file"] = {"path": assets_sample, "exists": os.path.isfile(assets_sample)}
    except Exception as e:
        checks["sites_assets_link"] = {"error": str(e)}

    checks["fallback_available"] = checks["chosen_has_spa"]
    z = _payload_zip()
    checks["embedded_payload"] = {"available": z is not None, "files": len(z.namelist()) if z else 0}
    if not checks["fallback_available"] and z is not None:
        checks["fallback_available"] = True  # payload can serve everything
    return checks
