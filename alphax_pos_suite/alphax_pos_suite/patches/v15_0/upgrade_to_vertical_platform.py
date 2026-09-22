"""
Patch v15_1.upgrade_to_vertical_platform

Migrates existing installs to the new multi-domain + loyalty + visual-floor
architecture. Idempotent — safe to re-run.

Steps:
 1. Seed the eight Domain Packs (Restaurant, Cafe, Retail, Grocery, Pharmacy,
    Salon, Service, Generic) with sensible default capability flags.
 2. For every existing Outlet, populate the new `domains` table:
       - If the legacy `pos_type` was set to a known value, add that domain.
       - Else default to "Generic".
       Set `primary_domain` to the same value.
       Auto-fill `outlet_name` from the docname if missing.
 3. Fill `outlet` field on every Floor by inferring from the Tables on it
    (best-effort; leaves blank if ambiguous).
 4. Default new visual-layout fields on every Table (pos_x/pos_y/width/height)
    using a simple grid layout, so existing tables show up somewhere on the
    designer canvas.
 5. Add custom field `alphax_default_loyalty_program` on Customer.
 6. Add custom fields on Sales Invoice for loyalty: `alphax_loyalty_program`,
    `alphax_loyalty_redeem_points`, `alphax_loyalty_redeem_value`,
    `alphax_loyalty_earned_points`, plus `alphax_outlet`.
 7. Invalidate any cached pos_boot payloads.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


_DOMAIN_DEFAULTS = [
    {
        "domain_code": "Restaurant", "label": "Restaurant", "icon": "utensils",
        "uses_floor_plan": 1, "uses_kds": 1, "uses_modifiers": 1, "uses_recipes": 1,
        "uses_tips": 1, "uses_service_charge": 1, "uses_courses": 1,
        "uses_table_qr": 1, "uses_split_bill": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Cafe", "label": "Cafe", "icon": "coffee",
        "uses_kds": 1, "uses_modifiers": 1, "uses_recipes": 1, "uses_tips": 1,
        "uses_loyalty": 1,
    },
    {
        "domain_code": "Retail", "label": "Retail", "icon": "shopping-bag",
        "uses_serial": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Grocery", "label": "Grocery", "icon": "shopping-cart",
        "uses_scale": 1, "uses_batch_expiry": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Pharmacy", "label": "Pharmacy", "icon": "pill",
        "uses_batch_expiry": 1, "uses_prescription": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Salon", "label": "Salon", "icon": "scissors",
        "uses_appointments": 1, "uses_tips": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Service", "label": "Service", "icon": "briefcase",
        "uses_appointments": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Generic", "label": "Generic", "icon": "package",
        "uses_loyalty": 1,
    },
    {
        "domain_code": "Supermarket", "label": "Supermarket", "icon": "shopping-cart-large",
        "uses_scale": 1, "uses_batch_expiry": 1, "uses_loyalty": 1, "uses_modifiers": 0,
    },
    {
        "domain_code": "Bakery", "label": "Bakery", "icon": "bread",
        "uses_scale": 1, "uses_batch_expiry": 1, "uses_modifiers": 1,
        "uses_recipes": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Clothing", "label": "Clothing & Apparel", "icon": "shirt",
        "uses_loyalty": 1,
    },
    {
        "domain_code": "Electronics", "label": "Electronics", "icon": "phone",
        "uses_serial": 1, "uses_loyalty": 1,
    },
    {
        "domain_code": "Garage", "label": "Garage / Auto Service", "icon": "wrench",
        "uses_appointments": 1, "uses_recipes": 1, "uses_loyalty": 1,
    },
]


def _seed_domain_packs():
    for spec in _DOMAIN_DEFAULTS:
        if frappe.db.exists("AlphaX POS Domain Pack", spec["domain_code"]):
            continue
        doc = frappe.new_doc("AlphaX POS Domain Pack")
        for k, v in spec.items():
            setattr(doc, k, v)
        doc.enabled = 1
        try:
            doc.insert(ignore_permissions=True)
            print(f"  seeded domain pack: {spec['domain_code']}")
        except Exception as e:
            frappe.log_error(
                f"Failed to seed domain pack {spec['domain_code']}: {e}",
                "Vertical Platform Patch",
            )


def _migrate_outlets():
    legacy_map = {
        "Restaurant": "Restaurant",
        "Retail": "Retail",
        "Pharmacy": "Pharmacy",
        "Electronics": "Retail",
        "Generic": "Generic",
    }
    outlets = frappe.get_all(
        "AlphaX POS Outlet",
        fields=["name", "pos_type"],
    )
    for o in outlets:
        try:
            doc = frappe.get_doc("AlphaX POS Outlet", o["name"])
            if not getattr(doc, "outlet_name", None):
                doc.outlet_name = doc.name

            target_domain = legacy_map.get(
                (o.get("pos_type") or "").strip(), "Generic"
            )

            existing = {row.domain for row in (doc.domains or [])}
            if target_domain not in existing:
                doc.append("domains", {"domain": target_domain})

            if not getattr(doc, "primary_domain", None):
                doc.primary_domain = target_domain

            doc.save(ignore_permissions=True)
            print(f"  migrated outlet: {o['name']} -> {target_domain}")
        except Exception as e:
            frappe.log_error(
                f"Failed to migrate outlet {o['name']}: {e}",
                "Vertical Platform Patch",
            )


def _backfill_floor_outlets():
    floors = frappe.get_all(
        "AlphaX POS Floor", filters={"outlet": ["is", "not set"]}, fields=["name"]
    )
    for f in floors:
        outlets = frappe.db.sql(
            """
            select distinct outlet
            from `tabAlphaX POS Table`
            where floor = %s and outlet is not null and outlet != ''
            """,
            (f["name"],),
        )
        if len(outlets) == 1 and outlets[0][0]:
            frappe.db.set_value(
                "AlphaX POS Floor", f["name"], "outlet", outlets[0][0]
            )
            print(f"  backfilled floor outlet: {f['name']} -> {outlets[0][0]}")


def _grid_layout_existing_tables():
    floors = frappe.get_all("AlphaX POS Floor", fields=["name"])
    for f in floors:
        tables = frappe.get_all(
            "AlphaX POS Table",
            filters={"floor": f["name"]},
            fields=["name", "pos_x", "pos_y", "width", "height"],
            order_by="table_code asc",
        )
        col, row = 0, 0
        for t in tables:
            if t.get("pos_x") and t.get("pos_y"):
                continue
            x = 30 + col * 100
            y = 30 + row * 90
            frappe.db.set_value(
                "AlphaX POS Table",
                t["name"],
                {"pos_x": x, "pos_y": y, "width": 80, "height": 60},
            )
            col += 1
            if col >= 7:
                col = 0
                row += 1


def _add_custom_fields():
    fields = [
        {
            "dt": "Customer",
            "fieldname": "alphax_default_loyalty_program",
            "label": "Default Loyalty Program",
            "fieldtype": "Link",
            "options": "AlphaX POS Loyalty Program",
            "insert_after": "customer_group",
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_outlet",
            "label": "AlphaX Outlet",
            "fieldtype": "Link",
            "options": "AlphaX POS Outlet",
            "insert_after": "pos_profile",
            "read_only": 0,
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_loyalty_program",
            "label": "Loyalty Program",
            "fieldtype": "Link",
            "options": "AlphaX POS Loyalty Program",
            "insert_after": "alphax_outlet",
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_loyalty_redeem_points",
            "label": "Loyalty Points Redeemed",
            "fieldtype": "Float",
            "insert_after": "alphax_loyalty_program",
            "default": 0,
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_loyalty_redeem_value",
            "label": "Loyalty Redeemed Value",
            "fieldtype": "Currency",
            "insert_after": "alphax_loyalty_redeem_points",
            "default": 0,
            "read_only": 1,
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_loyalty_earned_points",
            "label": "Loyalty Points Earned",
            "fieldtype": "Float",
            "insert_after": "alphax_loyalty_redeem_value",
            "read_only": 1,
        },
        {
            "dt": "Sales Invoice",
            "fieldname": "alphax_client_uuid",
            "label": "AlphaX Client UUID",
            "fieldtype": "Data",
            "insert_after": "alphax_loyalty_earned_points",
            "read_only": 1,
            "unique": 1,
            "no_copy": 1,
            "description": "Set by the offline-aware cashier SPA. Used to dedupe retries when the network drops mid-submit.",
        },
        {
            "dt": "AlphaX POS Profile",
            "fieldname": "alphax_outlet",
            "label": "AlphaX Outlet",
            "fieldtype": "Link",
            "options": "AlphaX POS Outlet",
            "insert_after": "company",
        },
        {
            "dt": "AlphaX POS Loyalty Ledger",
            "fieldname": "custom_expired",
            "label": "Already Expired",
            "fieldtype": "Check",
            "default": 0,
            "insert_after": "expires_on",
            "read_only": 1,
        },
        # ZATCA integration toggle. Wired by alphax_pos_suite.alphax_pos_suite.integrations.zatca_adapter.
        # Has no effect unless the standalone `alphax_zatca` Frappe app is also installed.
        {
            "dt": "AlphaX POS Outlet",
            "fieldname": "zatca_section",
            "label": "ZATCA E-Invoicing",
            "fieldtype": "Section Break",
            "insert_after": "tips_item",
            "collapsible": 1,
        },
        {
            "dt": "AlphaX POS Outlet",
            "fieldname": "zatca_enabled",
            "label": "Enable ZATCA Phase 2 submission",
            "fieldtype": "Check",
            "default": 0,
            "insert_after": "zatca_section",
            "description": "Requires the standalone alphax_zatca app. When on, every Sales Invoice from this outlet is automatically signed and submitted to ZATCA.",
        },
    ]
    for spec in fields:
        try:
            create_custom_field(spec["dt"], spec, ignore_validate=True)
        except Exception as e:
            frappe.log_error(
                f"Failed to create custom field {spec['dt']}.{spec['fieldname']}: {e}",
                "Vertical Platform Patch",
            )


def _invalidate_caches():
    try:
        for key in frappe.cache().get_keys("alphax_pos_boot::*"):
            frappe.cache().delete_value(key)
    except Exception:
        pass


def execute():
    print("AlphaXPOS: upgrading to vertical platform...")
    _seed_domain_packs()
    _add_custom_fields()
    frappe.db.commit()

    _migrate_outlets()
    _backfill_floor_outlets()
    _grid_layout_existing_tables()
    _invalidate_caches()

    frappe.db.commit()
    print("AlphaXPOS: vertical platform upgrade complete.")
