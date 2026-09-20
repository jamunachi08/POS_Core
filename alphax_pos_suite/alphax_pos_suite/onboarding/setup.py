"""
Code-driven schema additions for zero-touch onboarding.

Called from after_install and after_migrate. Idempotent — safe to run on
every migrate, which is the whole point given there is no bench shell on
Frappe Cloud.

Two groups of fields:

  A. AlphaX POS Terminal — identity + bridge state. These are what make
     "which PC is till 3, and is its printer reachable?" answerable from
     a list view instead of a phone call.

  B. AlphaX POS Domain Pack — layout preset selection, so the cashier
     screen adapts to the vertical without a code change.

  C. AlphaX POS Settings — fleet-level bridge distribution config.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


TERMINAL_FIELDS = [
    # --- identity -------------------------------------------------------
    dict(fieldname="device_fingerprint", label="Device Fingerprint",
         fieldtype="Data", insert_after="pc_uuid", read_only=1, unique=0,
         description="Stable machine identity computed at bind time. "
                     "hw: = bridge machine UUID, mac: = network card, "
                     "bx: = browser-local UUID (weakest)."),
    dict(fieldname="auto_provisioned", label="Auto Provisioned",
         fieldtype="Check", insert_after="device_fingerprint", read_only=1,
         description="Created by the onboarding wizard rather than by hand."),
    dict(fieldname="terminal_label", label="Station Name",
         fieldtype="Data", insert_after="naming_series",
         description="Human name shown on the cashier boot screen."),
    dict(fieldname="client_ip", label="Last Client IP",
         fieldtype="Data", insert_after="auto_provisioned", read_only=1),
    dict(fieldname="client_platform", label="Platform",
         fieldtype="Data", insert_after="client_ip", read_only=1),
    dict(fieldname="client_screen", label="Screen",
         fieldtype="Data", insert_after="client_platform", read_only=1),
    dict(fieldname="client_user_agent", label="User Agent",
         fieldtype="Small Text", insert_after="client_screen", read_only=1,
         hidden=1),

    # --- bridge ----------------------------------------------------------
    dict(fieldname="section_bridge", label="Hardware Bridge",
         fieldtype="Section Break", insert_after="client_user_agent",
         description="Populated automatically by the cashier SPA on every "
                     "boot and every 5-minute heartbeat. A station showing "
                     "Installed = No cannot print, open its drawer, or "
                     "take a card payment through a local terminal."),
    dict(fieldname="bridge_installed", label="Bridge Installed",
         fieldtype="Check", insert_after="section_bridge", read_only=1,
         in_list_view=1, in_standard_filter=1),
    dict(fieldname="bridge_version", label="Bridge Version",
         fieldtype="Data", insert_after="bridge_installed", read_only=1),
    dict(fieldname="bridge_os", label="Bridge OS",
         fieldtype="Data", insert_after="bridge_version", read_only=1),
    dict(fieldname="bridge_port", label="Port",
         fieldtype="Int", insert_after="bridge_os", read_only=1),
    dict(fieldname="col_bridge", fieldtype="Column Break",
         insert_after="bridge_port"),
    dict(fieldname="bridge_url", label="Bridge URL",
         fieldtype="Data", insert_after="col_bridge", read_only=1),
    dict(fieldname="bridge_token_hint", label="Token Hint",
         fieldtype="Data", insert_after="bridge_url", read_only=1,
         description="Last 4 characters only. The full token is never "
                     "stored server-side."),
    dict(fieldname="bridge_first_seen", label="First Seen",
         fieldtype="Datetime", insert_after="bridge_token_hint", read_only=1),
    dict(fieldname="bridge_last_seen", label="Last Heartbeat",
         fieldtype="Datetime", insert_after="bridge_first_seen", read_only=1,
         in_list_view=1),
    dict(fieldname="bridge_device_count", label="Devices",
         fieldtype="Int", insert_after="bridge_last_seen", read_only=1),
    dict(fieldname="bridge_devices_json", label="Devices (raw)",
         fieldtype="Code", options="JSON", insert_after="bridge_device_count",
         read_only=1, hidden=1),

    # --- hardware plan (v15.10.8) ---------------------------------------
    # Which peripherals this station actually has. A tablet on a counter
    # needs none of them; a full till needs five. Asking once, at setup,
    # is what stops the wizard demanding a bridge from a station that has
    # nothing to bridge to.
    dict(fieldname="section_hardware", label="Hardware Plan",
         fieldtype="Section Break", insert_after="bridge_devices_json",
         description="Chosen in the setup wizard, changeable any time from "
                     "the cashier's hardware panel. Only the ticked roles "
                     "are set up, monitored, or complained about."),
    dict(fieldname="hardware_profile", label="Hardware Profile",
         fieldtype="Select", insert_after="section_hardware",
         options="\nFull Station\nReceipt Only\nTablet Only\nKitchen Only\nCustom",
         in_list_view=0,
         description="A shorthand for the ticked roles. Custom means the "
                     "operator picked their own combination."),
    dict(fieldname="hardware_plan_json", label="Hardware Plan (raw)",
         fieldtype="Code", options="JSON", insert_after="hardware_profile",
         read_only=1, hidden=1),
    dict(fieldname="hardware_configured_on", label="Hardware Chosen On",
         fieldtype="Datetime", insert_after="hardware_plan_json", read_only=1),
]

DOMAIN_PACK_FIELDS = [
    dict(fieldname="section_layout", label="Cashier Screen",
         fieldtype="Section Break", insert_after="default_item_group",
         description="Controls how the cashier screen is arranged for this "
                     "vertical. Leave blank to use the preset mapped from "
                     "the domain code."),
    dict(fieldname="layout_preset", label="Layout Preset",
         fieldtype="Select", insert_after="section_layout",
         options="\nrestaurant\nsupermarket\nretail\npharmacy\nhospitality\nservice",
         description="restaurant = menu-first tiles. supermarket = scan-first "
                     "tape. retail = tiles + variants. pharmacy = search + Rx. "
                     "hospitality = folio/room-first. service = appointment-first."),
    dict(fieldname="show_top_movers", label="Show Quick-Pick Pad",
         fieldtype="Check", insert_after="layout_preset", default="0",
         description="Auto-computed pad of the most frequently hand-entered "
                     "items (produce, bakery, bags). Ranked by how often they "
                     "appear on an invoice, not by revenue."),
    dict(fieldname="top_movers_count", label="Quick-Pick Count",
         fieldtype="Int", insert_after="show_top_movers", default="12",
         depends_on="eval:doc.show_top_movers"),
    dict(fieldname="col_layout", fieldtype="Column Break",
         insert_after="top_movers_count"),
    dict(fieldname="tile_density", label="Tile Density",
         fieldtype="Select", insert_after="col_layout",
         options="Comfortable\nCompact\nDense", default="Comfortable"),
    dict(fieldname="scan_first", label="Scanner Owns Focus",
         fieldtype="Check", insert_after="tile_density", default="0",
         description="Keeps keyboard focus permanently on the scan field. "
                     "Essential for grocery throughput; disruptive in a "
                     "restaurant where the cashier types notes."),
]

SETTINGS_FIELDS = [
    dict(fieldname="section_bridge_dist", label="Bridge Distribution",
         fieldtype="Section Break", insert_after="",
         description="Where cashier stations fetch the bridge installer. "
                     "Point this at an internal file server for sites with "
                     "no outbound internet."),
    dict(fieldname="bridge_download_base_url", label="Installer Base URL",
         fieldtype="Data", insert_after="section_bridge_dist",
         description="Leave blank to use the public GitHub release URL."),
    dict(fieldname="bridge_target_version", label="Target Version",
         fieldtype="Data", insert_after="bridge_download_base_url",
         default="15.5.0"),
    dict(fieldname="col_bridge_dist", fieldtype="Column Break",
         insert_after="bridge_target_version"),
    dict(fieldname="bridge_default_port", label="Default Port",
         fieldtype="Int", insert_after="col_bridge_dist", default="8420"),
    dict(fieldname="bridge_allow_oneliner", label="Offer Command-Line Install",
         fieldtype="Check", insert_after="bridge_default_port", default="1",
         description="Some IT policies block downloaded executables but "
                     "permit a scripted install."),
]


def ensure_onboarding_fields():
    """Idempotent. Missing parent doctypes are skipped silently so a
    partial install never aborts a migrate."""
    spec = {}
    if frappe.db.exists("DocType", "AlphaX POS Terminal"):
        spec["AlphaX POS Terminal"] = TERMINAL_FIELDS
    if frappe.db.exists("DocType", "AlphaX POS Domain Pack"):
        spec["AlphaX POS Domain Pack"] = DOMAIN_PACK_FIELDS
    if frappe.db.exists("DocType", "AlphaX POS Settings"):
        spec["AlphaX POS Settings"] = SETTINGS_FIELDS

    if not spec:
        return

    try:
        create_custom_fields(spec, ignore_validate=True, update=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AlphaX onboarding fields failed")


def seed_layout_presets():
    """Give existing Domain Packs a sensible preset so an upgrade changes
    the screen for grocery/pharmacy without anyone touching a form."""
    mapping = {
        "Restaurant": ("restaurant", 0, 0),
        "Cafe": ("restaurant", 0, 0),
        "Bakery": ("supermarket", 1, 1),
        "Supermarket": ("supermarket", 1, 1),
        "Grocery": ("supermarket", 1, 1),
        "Retail": ("retail", 0, 1),
        "Clothing": ("retail", 0, 0),
        "Electronics": ("retail", 0, 1),
        "Pharmacy": ("pharmacy", 1, 1),
        "Salon": ("service", 0, 0),
        "Service": ("service", 0, 0),
        "Garage": ("service", 0, 0),
        "Generic": ("restaurant", 0, 0),
    }
    if not frappe.db.exists("DocType", "AlphaX POS Domain Pack"):
        return
    for name in frappe.get_all("AlphaX POS Domain Pack", pluck="name"):
        try:
            doc = frappe.get_doc("AlphaX POS Domain Pack", name)
            if doc.get("layout_preset"):
                continue  # never overwrite an operator choice
            preset, movers, scan = mapping.get(doc.get("domain_code"), ("restaurant", 0, 0))
            doc.db_set("layout_preset", preset, update_modified=False)
            doc.db_set("show_top_movers", movers, update_modified=False)
            doc.db_set("scan_first", scan, update_modified=False)
        except Exception:
            continue
    frappe.db.commit()


def after_migrate():
    ensure_onboarding_fields()
    seed_layout_presets()
