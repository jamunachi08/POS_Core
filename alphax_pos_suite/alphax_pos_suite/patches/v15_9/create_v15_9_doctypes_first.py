"""pre_model_sync: import v15.9 doctypes in dependency order.

Same class of failure as v15.8.1's create_kot_doctypes_first: Frappe
syncs doctype folders alphabetically, so 'alphax_pos_combo' (whose
Table field points at 'alphax_pos_combo_component') validates before
the child exists, migrate aborts, and everything later in the
alphabet — including AlphaX POS Notify Recipient — never gets created
(field report, v15.9.0 deploy: "DocType AlphaX POS Notify Recipient
not found"). Children first, then parents, before general model sync.
Idempotent (force re-import).
"""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
    base = frappe.get_app_path("alphax_pos_suite", "alphax_pos_suite", "doctype")
    for folder in (
        "alphax_pos_combo_component",   # child before parent
        "alphax_pos_notify_recipient",  # child used by Outlet fields
        "alphax_pos_combo",
    ):
        path = os.path.join(base, folder, f"{folder}.json")
        if os.path.exists(path):
            import_file_by_path(path, force=True)
    frappe.db.commit()
