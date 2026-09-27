"""
Adds the `alphax_outlet` Link field to the standard ERPNext POS Profile
on existing installs.

This field was missing from earlier versions of the seed (v15.5.1 and
prior). Without it, the cashier UI couldn't be linked to an AlphaX POS
Outlet from the POS Profile screen, which broke domain-pack feature
detection (modifiers, loyalty, prescription capture, etc.).

This patch is idempotent — if the field already exists (newly installed
post-fix), it does nothing. Safe to run repeatedly.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    if frappe.db.exists("Custom Field",
                        {"dt": "POS Profile", "fieldname": "alphax_outlet"}):
        return

    df = {
        "fieldname": "alphax_outlet",
        "label": "AlphaX Outlet",
        "fieldtype": "Link",
        "options": "AlphaX POS Outlet",
        "insert_after": "currency",
        "description": (
            "Link this POS Profile to an AlphaX POS Outlet to enable "
            "cashier UI features (domain pack, multi-outlet routing, "
            "modifiers, loyalty)."
        ),
        "reqd": 0,
        "in_list_view": 1,
        "in_standard_filter": 1,
    }

    try:
        create_custom_field("POS Profile", df, ignore_validate=True)
    except TypeError:
        create_custom_field("POS Profile", df)

    frappe.db.commit()
