"""
Remove the obsolete `alphax-pos` Page from the database.

Why this patch exists
=====================

In versions prior to v15.4, the cashier UI was a single jQuery-based
Frappe Page registered as `alphax-pos`. Starting in v15.4, the cashier
was rewritten as a Vue 3 SPA at a new page slug `alphax-pos-v2`, and
the old page was supposed to be removed.

The old page folder in the codebase did get removed in v15.5.8, but
existing benches that were upgraded from older versions still have a
`Page` doctype row with `name = "alphax-pos"` in their database. That
row causes two problems:

1. It shows up as "AlphaX POS" in the desk sidebar alongside our
   workspace (which has the same title). When a user clicks it, they
   get the broken old page instead of the workspace at /app/alphax-pos-hub.

2. The old page's JS file references a function that no longer exists
   (`inject_css()`), so opening it throws "ReferenceError" and renders
   a broken UI.

This patch deletes that database row. The new Vue cashier at
`alphax-pos-v2` is unaffected.

Idempotent — safe to re-run.
"""
import frappe


OBSOLETE_PAGE_NAME = "alphax-pos"


def execute():
    if not frappe.db.exists("Page", OBSOLETE_PAGE_NAME):
        # Already removed (or never existed on a fresh install) — nothing to do
        return

    try:
        frappe.delete_doc(
            "Page", OBSOLETE_PAGE_NAME,
            ignore_permissions=True,
            force=True,
        )
        frappe.db.commit()
        frappe.logger().info(
            f"AlphaX POS: removed obsolete page '{OBSOLETE_PAGE_NAME}'"
        )
    except Exception:
        # Don't crash migrate if something exotic prevents deletion —
        # the worst case is the user still sees the duplicate sidebar
        # entry, which is cosmetic.
        frappe.log_error(
            title="AlphaX POS: failed to remove obsolete alphax-pos page",
            message=frappe.get_traceback(),
        )
