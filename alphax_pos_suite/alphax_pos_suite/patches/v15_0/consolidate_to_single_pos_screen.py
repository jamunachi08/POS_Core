"""
Consolidate to a single POS screen.

Why this patch exists
=====================

Through v15.5.x the app accumulated FIVE parallel cashier surfaces:

    alphax-pos-classic   jQuery desk page (53KB monolith)
    alphax-pos-v2        Vue 3 SPA — the most complete implementation
    alphax-pos-v3        Tailwind rewrite, never finished
    alphax_apos          Phase-1 placeholder stub
    /alphax-pos (www)    static demo mockup with hard-coded data

As of v15.6.0 there is exactly ONE cashier: the Vue SPA, promoted from
`alphax-pos-v2` to the clean slug `alphax-pos`, with the classic
screen's manager-PIN gates, returns flow, and an in-screen Config
panel ported into it.

The page folders are gone from the codebase; this patch removes the
stale `Page` doctype rows from upgraded databases so they stop
appearing in desk search and the sidebar. The new `alphax-cashier`
page is synced from file by the same migrate run (sync happens after
patches). Fresh installs are covered by the `before_install` cleanup
in install.py, because Frappe marks patches as completed without
running them when an app is first installed.

Note: the older `remove_obsolete_alphax_pos_page` patch deleted a
pre-v15.4 row named `alphax-pos` for exactly the same route-conflict
reason. History rhymed; now the reserved slug is documented above.

Idempotent — safe to re-run.
"""
import frappe

RETIRED_PAGES = (
    "alphax-pos-v2",
    "alphax-pos-v3",
    "alphax-pos-classic",
    "alphax_apos",
    # The route `alphax-pos` is RESERVED by the "AlphaX POS" workspace —
    # Frappe's validate_route_conflict rejects any Page with the same
    # slug as a Workspace title. A v15.6.0 pre-release briefly shipped
    # the cashier under this name; any row it left behind must go.
    "alphax-pos",
)


def execute():
    for name in RETIRED_PAGES:
        if not frappe.db.exists("Page", name):
            continue
        try:
            frappe.delete_doc("Page", name, ignore_permissions=True, force=True)
            frappe.logger().info(f"AlphaX POS: removed retired page '{name}'")
        except Exception:
            # Never crash migrate over a cosmetic leftover.
            frappe.log_error(
                title=f"AlphaX POS: failed to remove retired page {name}",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()
