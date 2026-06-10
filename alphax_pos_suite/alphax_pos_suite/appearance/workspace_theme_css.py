"""
Workspace theme toggle — desk integration.

`boot_workspace_theme` is wired into Frappe's `boot_session` hook in
hooks.py. Frappe calls it once per desk page load, passing the bootinfo
dict; we add an `alphax_workspace_theme_enabled` boolean to it. A tiny
companion JS file (alphax_workspace_theme_apply.js) reads that boolean
and adds a body class accordingly.

The CSS file (alphax_pos_hub.css) is shipped on every desk page via
app_include_css in hooks.py. Every selector inside is gated on:

    body.alphax-pos-themed[data-page-route^="Workspaces/AlphaX POS Hub"] ...

So when the toggle is off, the body class is absent and not a single
selector matches. The CSS is harmless dead weight in that case.

We never raise from this hook — if AlphaX POS Settings doesn't exist
yet (e.g. mid-install) or any other error occurs, we silently default
to "off" and the workspace renders stock-Frappe.
"""
from __future__ import annotations

import frappe


def boot_workspace_theme(bootinfo) -> None:
    """Annotate bootinfo with the workspace theme toggle state."""
    enabled = False
    try:
        value = frappe.db.get_single_value(
            "AlphaX POS Settings",
            "enable_polished_workspace_theme",
        )
        # Frappe Check fields default to None when the row doesn't exist
        # and to 1 (int) when set to True. Anything truthy counts as on.
        enabled = bool(value)
    except Exception:
        # Mid-install, missing doctype, DB hiccup — fall back to off.
        enabled = False

    try:
        bootinfo["alphax_workspace_theme_enabled"] = enabled
    except Exception:
        # bootinfo is normally a dict-like; if it isn't, don't crash boot.
        pass
