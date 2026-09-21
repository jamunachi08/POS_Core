"""pre_model_sync: import the KOT doctypes before the general model sync.

Frappe syncs an app's doctypes in alphabetical folder order, so
alphax_pos_kds_ticket syncs before alphax_pos_print_station — and the
KDS Ticket's new `station` Link field then references a doctype that
does not exist yet, aborting migrate with "Field station is referring
to non-existing doctype AlphaX POS Print Station" (field report,
v15.8.0 deploy). Importing Print Station (and Routing Rule, which
links to it) here — in the [pre_model_sync] phase — guarantees the
link targets exist before any dependent doctype is validated.

Idempotent: import_file_by_path with force updates in place; re-running
on every future migrate is harmless and also self-heals a site where
the doctype was deleted by hand.
"""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
    base = frappe.get_app_path("alphax_pos_suite", "alphax_pos_suite", "doctype")
    for folder in ("alphax_pos_print_station", "alphax_pos_kot_routing_rule"):
        path = os.path.join(base, folder, f"{folder}.json")
        if os.path.exists(path):
            import_file_by_path(path, force=True)
    frappe.db.commit()
