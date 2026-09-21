"""
Rename the Workspace so its URL matches what the desk sidebar links to.

The sidebar labels workspaces by TITLE and links to the title's slug,
but the router resolves the NAME's slug. Ours were split — name
"AlphaX POS Hub" (route /app/alphax-pos-hub) vs title "AlphaX POS"
(sidebar link /app/alphax-pos) — so clicking the sidebar entry 404'd
("Page alphax-pos not found") while the manual -hub URL worked.

Fix: name := title. Both slugs become alphax-pos. Idempotent.
"""
import frappe


def execute():
    old, new = "AlphaX POS Hub", "AlphaX POS"
    if not frappe.db.exists("Workspace", old):
        return
    if frappe.db.exists("Workspace", new):
        # Fixture sync may already have created the new one — drop the
        # stale twin so only one sidebar entry remains.
        frappe.delete_doc("Workspace", old, ignore_permissions=True, force=True)
        return
    # NOTE: rename_doc has no ignore_permissions kwarg (learned from a
    # failed migrate on FC); patches run as Administrator, so none is
    # needed.
    frappe.rename_doc("Workspace", old, new, force=True)
    frappe.db.commit()
