import json
import os

import frappe


def before_install():
    """Runs before Frappe syncs this app's doctypes, pages, and fixtures.

    Removes Page rows left behind by retired cashier screens. This
    matters on FRESH installs specifically: Frappe marks all patches as
    completed without executing them when an app is first installed, so
    the consolidate_to_single_pos_screen patch never runs there — but a
    previous failed/partial install (or an older version of the app) may
    have left rows that collide with what we're about to sync.

    The critical one is `alphax-pos`: that route is reserved by the
    "AlphaX POS" workspace title, and validate_route_conflict aborts the
    entire workspace fixture import if a Page row squats on it.

    Idempotent and silent — a fresh site simply finds nothing to delete.
    """
    cleanup_retired_pages()


def seed_delivery_platforms():
    """Seed the KSA delivery platform masters (idempotent; Mode of
    Payment intentionally left for the operator to map — accounts are
    site-specific). Runs at install; safe to re-run."""
    defaults = [
        ("HungerStation", 25, 14),
        ("Keeta", 20, 7),
        ("Jahez", 25, 14),
        ("Jeeny", 20, 7),
        ("Noon Food", 22, 14),
        ("Amazon", 15, 14),
        ("ToYou", 22, 7),
        ("Mrsool", 20, 7),
    ]
    if not frappe.db.table_exists("AlphaX Delivery Platform"):
        return
    for name, commission, days in defaults:
        try:
            if frappe.db.exists("AlphaX Delivery Platform", name):
                continue
            frappe.get_doc({
                "doctype": "AlphaX Delivery Platform",
                "platform_name": name,
                "commission_percent": commission,
                "settlement_days": days,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title=f"AlphaX POS: could not seed delivery platform {name}",
                message=frappe.get_traceback(),
            )


def restore_spa_files_if_missing():
    """Self-heal the vendor asset tree from the embedded payload.

    The vendor tree has twice been deleted from the repo by Windows
    long-path failures on the developer's machine, bricking every
    register on deploy. alphax_pos_suite/spa_payload.py (a short-path
    file that survives those failures) carries a complete compressed
    copy; this unpacks it whenever the on-disk tree is missing the SPA.
    Runs first in after_migrate so force_rebuild_assets links a
    complete tree. Idempotent; never crashes migrate.
    """
    import io
    import zipfile

    try:
        from alphax_pos_suite.spa_payload import payload_bytes, FILE_COUNT
    except Exception:
        return  # payload module itself missing — nothing we can do here

    try:
        from alphax_pos_suite.spa_payload import SHA256 as PAYLOAD_SHA
    except Exception:
        PAYLOAD_SHA = None

    try:
        vendor = os.path.join(frappe.get_app_path("alphax_pos_suite"), "public", "dist", "vendor")
        probe = os.path.join(vendor, "cashier", "sfc-loader.js")
        stamp_path = os.path.join(vendor, ".payload_sha")

        # The tree is "intact" only if it exists AND carries the stamp of
        # the exact payload shipped in this deploy. A missing or mismatched
        # stamp means tree and payload diverged in transport (observed
        # v15.7.4→.5: stale payload + lost tree self-healed registers back
        # to OLD code, unfixable by any browser refresh). The payload is
        # rebuilt from the tree at packaging time, so it is always the
        # authoritative copy for its own release — re-extract on mismatch.
        if os.path.isfile(probe) and PAYLOAD_SHA:
            try:
                with open(stamp_path) as f:
                    if f.read().strip() == PAYLOAD_SHA:
                        return  # tree intact and current
            except OSError:
                pass  # no stamp (pre-15.7.5 tree) → re-extract once
        elif os.path.isfile(probe) and not PAYLOAD_SHA:
            return  # payload has no SHA (very old build) — keep legacy behavior

        os.makedirs(vendor, exist_ok=True)
        z = zipfile.ZipFile(io.BytesIO(payload_bytes()))
        z.extractall(vendor)
        if PAYLOAD_SHA:
            with open(stamp_path, "w") as f:
                f.write(PAYLOAD_SHA + "\n")
        frappe.logger().info(
            f"AlphaX POS: restored {FILE_COUNT} vendor asset files from embedded payload"
        )
    except Exception:
        frappe.log_error(
            title="AlphaX POS: embedded-payload restore failed (register will use API serving)",
            message=frappe.get_traceback(),
        )


def cleanup_retired_pages():
    from alphax_pos_suite.alphax_pos_suite.patches.v15_0.consolidate_to_single_pos_screen import (
        RETIRED_PAGES,
    )
    for name in RETIRED_PAGES:
        try:
            if frappe.db.exists("Page", name):
                frappe.delete_doc("Page", name, ignore_permissions=True, force=True)
                frappe.logger().info(f"AlphaX POS: removed retired page '{name}'")
        except Exception:
            frappe.log_error(
                title=f"AlphaX POS: retired page cleanup failed for {name}",
                message=frappe.get_traceback(),
            )


def after_install():
    """Create required setup objects for AlphaX POS Suite."""
    repair_orphaned_modules_silently()
    seed_delivery_platforms()
    create_roles()
    create_custom_fields()
    create_role_profiles()
    apply_permissions()
    seed_domain_packs()
    seed_default_barcode_definition()
    fetch_vendor_bundles_silently()
    force_rebuild_assets()


def force_rebuild_assets():
    """Rebuild the public asset symlinks so /assets/alphax_pos_suite/...
    URLs serve our JS/CSS/vendor files.

    Frappe Cloud's deploy pipeline runs `bench build` automatically as
    part of its build phase. This function is a belt-and-suspenders
    fallback that runs after migrate, in case the build phase missed our
    app for any reason.

    We try three strategies in order, falling back to the next on failure:

    1. Call frappe.build.bundle() if it exists in this Frappe version
       (the public-ish Python API on some v15 builds).
    2. Shell out to `bench build --app alphax_pos_suite` (the documented
       CLI; works in any Frappe version).
    3. Walk the public/ folder ourselves and create the symlinks under
       sites/assets/<app>/ manually (last-ditch fallback that doesn't
       require any Frappe internals).

    Failures are logged but never crash the install. If all three fail,
    the bench operator can run `bench build --app alphax_pos_suite`
    manually and the assets will appear.
    """
    # Strategy 0: direct repair. If sites/assets/alphax_pos_suite is
    # missing or points at an INCOMPLETE public dir (the Frappe Cloud
    # split-brain: python package resolves but public/dist is stripped),
    # link it straight at a root that verifiably contains the cashier
    # SPA. Cheap, no subprocess, fixes the observed failure exactly.
    try:
        from alphax_pos_suite.alphax_pos_suite.cashier.assets import _vendor_root, _PROBE

        vendor = _vendor_root()
        if os.path.isfile(os.path.join(vendor, _PROBE)):
            # vendor = <complete root>/public/dist/vendor → public dir is 2 up
            public_dir = os.path.dirname(os.path.dirname(vendor))
            link = os.path.join(
                frappe.utils.get_bench_path(), "sites", "assets", "alphax_pos_suite"
            )
            probe_via_link = os.path.join(link, "dist", "vendor", *_PROBE.split("/"))
            if not os.path.isfile(probe_via_link):
                if os.path.islink(link):
                    os.unlink(link)
                if not os.path.exists(link):
                    os.symlink(public_dir, link)
                    frappe.logger().info(
                        f"AlphaX POS: relinked sites/assets/alphax_pos_suite -> {public_dir}"
                    )
    except Exception:
        frappe.log_error(
            title="AlphaX POS: direct asset relink failed (trying bundle)",
            message=frappe.get_traceback(),
        )

    # Strategy 1: try frappe.build.bundle if it exists with the expected signature
    try:
        from frappe.build import bundle
        bundle(mode="production", apps="alphax_pos_suite", hard_link=True)
        frappe.logger().info(
            "AlphaX POS: rebuilt assets via frappe.build.bundle"
        )
        return
    except (ImportError, TypeError, AttributeError):
        # Module/function doesn't exist or signature differs — fall through
        pass
    except Exception:
        # Any other error — log and try next strategy
        frappe.log_error(
            title="AlphaX POS: frappe.build.bundle failed (trying fallback)",
            message=frappe.get_traceback(),
        )

    # Strategy 2: shell out to `bench build`
    try:
        import subprocess
        result = subprocess.run(
            ["bench", "build", "--app", "alphax_pos_suite"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            frappe.logger().info(
                "AlphaX POS: rebuilt assets via 'bench build --app'"
            )
            return
    except Exception:
        pass

    # Strategy 3: walk public/ ourselves and create symlinks under sites/assets/
    try:
        _manual_asset_symlink()
        frappe.logger().info(
            "AlphaX POS: created asset symlinks manually"
        )
    except Exception:
        frappe.log_error(
            title="AlphaX POS install: asset rebuild failed (non-fatal)",
            message=frappe.get_traceback(),
        )


def _manual_asset_symlink():
    """Last-ditch asset symlink creation.

    Creates symlinks from sites/assets/alphax_pos_suite/* to the actual
    public/ folder inside this app. This is what `bench build` does
    behind the scenes for static (non-bundled) assets.

    Used only when both frappe.build.bundle and `bench build` CLI failed.
    """
    import os
    import frappe.utils

    bench_path = os.path.dirname(os.path.dirname(frappe.utils.get_bench_path()))
    public_src = os.path.join(
        bench_path, "apps", "alphax_pos_suite",
        "alphax_pos_suite", "public"
    )
    if not os.path.isdir(public_src):
        # Try the other common layout (repo named after app)
        public_src_alt = os.path.join(
            frappe.utils.get_bench_path(), "apps", "alphax_pos_suite",
            "alphax_pos_suite", "public"
        )
        if os.path.isdir(public_src_alt):
            public_src = public_src_alt
        else:
            return

    assets_dest = os.path.join(
        frappe.utils.get_bench_path(),
        "sites", "assets", "alphax_pos_suite"
    )
    os.makedirs(os.path.dirname(assets_dest), exist_ok=True)

    # If a stale link/dir is in the way, remove it
    if os.path.islink(assets_dest) or os.path.exists(assets_dest):
        try:
            if os.path.islink(assets_dest):
                os.unlink(assets_dest)
            elif os.path.isdir(assets_dest):
                import shutil
                shutil.rmtree(assets_dest)
        except Exception:
            pass

    # Symlink the public folder contents into assets/alphax_pos_suite/
    try:
        os.symlink(public_src, assets_dest)
    except OSError:
        # Filesystem doesn't support symlinks — copy instead
        import shutil
        shutil.copytree(public_src, assets_dest)


def repair_orphaned_modules_silently():
    """Clear orphaned foreign-module references (e.g. a removed ZATCA app)
    that would otherwise make Frappe throw 'Module ... not found' during
    setup. Conservative + idempotent; no-op on clean sites."""
    try:
        from alphax_pos_suite.alphax_pos_suite.setup_repair import (
            repair_orphaned_module_blockers,
        )
        repair_orphaned_module_blockers()
    except Exception:
        frappe.log_error(
            title="AlphaX POS: orphan-module repair failed (non-fatal)",
            message=frappe.get_traceback(),
        )


def fetch_vendor_bundles_silently():
    """Fetch the cashier UI's Vue/Pinia/vue-i18n bundles into
    public/dist/vendor/ so the cashier page works on first open
    without any manual command.

    Failures are logged but don't abort the install — the cashier
    falls back to CDN at runtime if the bundles are missing, so a
    failed fetch here just means the first cashier load will pull
    from a CDN. The cashier still works either way.

    Runs in the bench's outbound network context (which has CDN
    access on Frappe Cloud), not the runtime browser context.
    """
    try:
        from alphax_pos_suite.alphax_pos_suite.cashier.vendor import fetch_all
        result = fetch_all(force=False)
        frappe.logger().info(
            f"AlphaX POS: vendor bundles installed — {result}"
        )
    except Exception:
        frappe.log_error(
            title="AlphaX POS install: vendor bundle fetch failed (non-fatal)",
            message=frappe.get_traceback(),
        )


def seed_domain_packs():
    """Seed the eight domain packs on fresh install."""
    try:
        from alphax_pos_suite.alphax_pos_suite.patches.v15_0.upgrade_to_vertical_platform import (
            _seed_domain_packs,
        )
        _seed_domain_packs()
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="AlphaX POS install: domain pack seeding failed",
            message=frappe.get_traceback(),
        )


def seed_default_barcode_definition():
    """Seed a sensible default weight/price-embedded barcode scheme.

    This makes deli/produce/butcher 'scale' barcodes work the moment the
    app is installed, with zero configuration. It encodes the common
    EAN-13 in-store scheme:

        2 PPPPP QQQQQ C
        | |     |     |
        | |     |     check digit (ignored)
        | |     embedded value (weight in grams /1000, or price in cents)
        | 5-digit item / PLU code
        prefix '2'  (the GS1 in-store / variable-measure prefix)

    Owners can edit, disable, or add definitions from
    'AlphaX POS Scale Barcode Definition' in the desk — this is just a
    friendly starting point, not a hardcoded rule.
    """
    try:
        if not frappe.db.exists("DocType", "AlphaX POS Scale Barcode Definition"):
            return

        defn_name = "Default Weight/Price Barcode (EAN-13, prefix 2)"
        if not frappe.db.exists("AlphaX POS Scale Barcode Definition", {"definition_name": defn_name}):
            frappe.get_doc({
                "doctype": "AlphaX POS Scale Barcode Definition",
                "definition_name": defn_name,
                "enabled": 1,
                "prefix": "2",
                "total_length": 13,
                "mapping_type": "Fixed Segments",
                "item_start": 2,
                "item_length": 5,
                "qty_start": 7,
                "qty_length": 5,
                "qty_divider": 1000,       # 5 digits = grams -> kg
                "use_qty_from_barcode": 1,
                "rate_start": 7,
                "rate_length": 5,
                "rate_divider": 100,       # 5 digits = cents -> currency
                "use_rate_from_barcode": 0,  # default: weight scheme, not price
            }).insert(ignore_permissions=True)

        # A catch-all rule so the definition is active without per-item setup.
        if frappe.db.exists("DocType", "AlphaX POS Scale Barcode Rule"):
            defn = frappe.db.get_value(
                "AlphaX POS Scale Barcode Definition",
                {"definition_name": defn_name}, "name",
            )
            if defn and not frappe.db.exists(
                "AlphaX POS Scale Barcode Rule",
                {"applies_to": "Barcode Prefix", "barcode_prefix": "2"},
            ):
                frappe.get_doc({
                    "doctype": "AlphaX POS Scale Barcode Rule",
                    "priority": 50,
                    "applies_to": "Barcode Prefix",
                    "barcode_prefix": "2",
                    "definition": defn,
                }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="AlphaX POS install: barcode definition seeding failed",
            message=frappe.get_traceback(),
        )


def _safe_insert(doc_dict):
    """Insert a doc if it doesn't already exist."""
    if not doc_dict.get("doctype"):
        return
    name = doc_dict.get("name")
    if name and frappe.db.exists(doc_dict["doctype"], name):
        return
    try:
        frappe.get_doc(doc_dict).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
    title=f"AlphaX POS install: failed inserting {doc_dict.get('doctype')}",
    message=frappe.get_traceback()
)



def create_roles():
    """Create POS roles used for UI permission gating."""
    roles = [
        "AlphaX POS Cashier",
        "AlphaX POS Supervisor",
        "AlphaX POS Manager",
        "AlphaX POS User",   # the catch-all read-only role used in pharmacy doctypes
        "Pharmacist",         # used by pharmacy doctypes
    ]

    for role in roles:
        if not frappe.db.exists("Role", role):
            doc = frappe.get_doc({"doctype": "Role", "role_name": role})
            doc.insert(ignore_permissions=True)


def create_role_profiles():
    """Optional role profiles to speed user setup."""
    if not frappe.db.exists("DocType", "Role Profile"):
        return

    profiles = [
        {
            "doctype": "Role Profile",
            "role_profile": "AlphaX POS - Cashier",
            "roles": [{"role": "AlphaX POS Cashier"}],
        },
        {
            "doctype": "Role Profile",
            "role_profile": "AlphaX POS - Supervisor",
            "roles": [{"role": "AlphaX POS Supervisor"}, {"role": "AlphaX POS Cashier"}],
        },
        {
            "doctype": "Role Profile",
            "role_profile": "AlphaX POS - Manager",
            "roles": [
                {"role": "AlphaX POS Manager"},
                {"role": "AlphaX POS Supervisor"},
                {"role": "AlphaX POS Cashier"},
            ],
        },
    ]
    for p in profiles:
        if not frappe.db.exists("Role Profile", p["role_profile"]):
            _safe_insert(p)


def create_workspace():
    """Create a workspace with shortcuts for Bonanza POS."""
    if not frappe.db.exists("DocType", "Workspace"):
        return
    ws_name = "AlphaX Bonanza POS"
    if frappe.db.exists("Workspace", ws_name):
        return

    shortcuts = [
        {"type": "doctype", "label": "POS Settings", "link_to": "AlphaX POS Settings"},
        {"type": "page", "label": "Setup Wizard", "link_to": "alphax-pos-setup"},
        {"type": "doctype", "label": "POS Terminal", "link_to": "AlphaX POS Terminal"},
        {"type": "doctype", "label": "POS Floor", "link_to": "AlphaX POS Floor"},
        {"type": "doctype", "label": "POS Table", "link_to": "AlphaX POS Table"},
        {"type": "doctype", "label": "POS Recipe", "link_to": "AlphaX POS Recipe"},
        {"type": "doctype", "label": "Processing Log", "link_to": "AlphaX POS Processing Log"},
        {"type": "doctype", "label": "Card Transactions", "link_to": "AlphaX POS Card Transaction"},
    ]

    ws = {
        "doctype": "Workspace",
        "name": ws_name,
        "title": ws_name,
        "module": "AlphaX POS Suite",
        "icon": "pos",
        "is_standard": 0,
        "content": [],
        "sequence_id": 99,
        "shortcuts": shortcuts,
    }
    _safe_insert(ws)


def ensure_workspace_visible():
    """Make sure the AlphaX POS workspace is public and visible.

    Background: in v15.5.17 several users reported the workspace
    disappearing from the left sidebar after a deploy. The fixture file
    is correct (public=1, hide_custom=0), but in some cases the existing
    database row has `for_user` set or `is_hidden=1` from a prior version
    or a manual customization. The fixture importer respects those user
    customizations by default, so the workspace stays invisible.

    This function runs on every after_migrate and forces:
      - public = 1
      - is_hidden = 0
      - for_user = NULL (so it's not pinned to a single user)
      - module = 'AlphaX POS Suite' (in case it got reset)

    Safe to run multiple times; idempotent.
    """
    if not frappe.db.exists("DocType", "Workspace"):
        return

    if not frappe.db.exists("Workspace", "AlphaX POS"):
        frappe.logger().warning(
            "AlphaX POS: workspace 'AlphaX POS' not found in DB after migrate. "
            "The fixture should have created it. Check fixtures/workspace.json."
        )
        return

    try:
        frappe.db.set_value(
            "Workspace",
            "AlphaX POS",
            {
                "public": 1,
                "is_hidden": 0,
                "for_user": "",  # empty string == not user-scoped
                "module": "AlphaX POS Suite",
            },
            update_modified=False,
        )
        frappe.db.commit()
        frappe.logger().info(
            "AlphaX POS: ensured 'AlphaX POS' workspace is public + visible"
        )
    except Exception:
        # Non-fatal: log and continue. The workspace may still be reachable
        # via direct URL even if this update failed.
        frappe.log_error(
            title="AlphaX POS: failed to ensure workspace visibility",
            message=frappe.get_traceback(),
        )


def apply_permissions():
    """Apply basic permissions to core suite doctypes using Custom DocPerm."""
    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return

    # Minimal set: settings + key operational doctypes
    perm_map = {
        "AlphaX POS Settings": {
            "AlphaX POS Manager": {"read": 1, "write": 1, "create": 1, "delete": 0, "submit": 0, "cancel": 0},
            "AlphaX POS Supervisor": {"read": 1, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0},
            "AlphaX POS Cashier": {"read": 1, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0},
        },
        "AlphaX POS Processing Log": {
            "AlphaX POS Manager": {"read": 1, "write": 1, "create": 1, "delete": 0},
            "AlphaX POS Supervisor": {"read": 1, "write": 0, "create": 0, "delete": 0},
            "AlphaX POS Cashier": {"read": 0, "write": 0, "create": 0, "delete": 0},
        },
    }

    for doctype, roles in perm_map.items():
        for role, perms in roles.items():
            if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
                continue
            d = {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
            }
            d.update(perms)
            try:
                frappe.get_doc(d).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), title=f"AlphaX POS install: failed custom perm {doctype} / {role}")


def _seed_custom_fields():
    seed_path = os.path.join(os.path.dirname(__file__), "data", "custom_fields_seed.json")
    if not os.path.exists(seed_path):
        return []
    with open(seed_path, encoding="utf-8") as f:
        return json.load(f)


def create_custom_fields():
    """Create Custom Fields required by the suite."""
    try:
        from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    except Exception:
        return

    for row in _seed_custom_fields():
        if row.get("doctype") != "Custom Field":
            continue

        dt = row.get("dt")
        fieldname = row.get("fieldname")
        if not dt or not fieldname:
            continue

        if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
            continue

        df = dict(row)
        df.pop("doctype", None)
        df.pop("dt", None)

        # create_custom_field signature differs slightly across versions
        try:
            create_custom_field(dt, df, ignore_validate=True)
        except TypeError:
            create_custom_field(dt, df)


def ensure_custom_fields_silently():
    """after_migrate: make the custom-field seed self-healing.

    Until v15.7.8, create_custom_fields() ran only in after_install —
    so a site installed while the seed was missing entries stayed
    missing them forever, and eleven fields (offline-queue dedupe UUID
    alphax_client_uuid, the loyalty set, outlet stamping, ZATCA outlet
    toggles) lived only in the v15.0 upgrade patch, which fresh
    installs never execute. Field report (testneo.frappe.cloud): queue
    flush failing with 1054 Unknown column
    'tabSales Invoice.alphax_client_uuid'.

    create_custom_fields() is idempotent (per-field exists check), so
    running it on every migrate is cheap and closes the drift class:
    any field added to the seed reaches every site on its next deploy.
    """
    try:
        create_custom_fields()
    except Exception:
        frappe.log_error(
            title="AlphaX POS: ensure_custom_fields_silently failed",
            message=frappe.get_traceback(),
        )

    # Split-brain guard: a Custom Field *record* can exist while the DB
    # *column* doesn't (aborted migrate mid-run). The exists-check above
    # would then skip creation and the column stays missing forever —
    # the 1054 error persists even though Customize Form looks correct.
    # Verify every seeded field has a real column; updatedb() re-syncs
    # the table from meta for any doctype that's short.
    try:
        needs_sync = set()
        for row in _seed_custom_fields():
            dt, fieldname = row.get("dt"), row.get("fieldname")
            if not dt or not fieldname:
                continue
            try:
                if not frappe.db.has_column(dt, fieldname):
                    needs_sync.add(dt)
            except Exception:
                continue  # doctype's table may not exist yet on this site
        for dt in needs_sync:
            try:
                frappe.db.updatedb(dt)
                frappe.logger().info(f"AlphaX POS: re-synced missing columns on {dt}")
            except Exception:
                frappe.log_error(
                    title=f"AlphaX POS: column re-sync failed for {dt}",
                    message=frappe.get_traceback(),
                )
    except Exception:
        frappe.log_error(
            title="AlphaX POS: custom-field column verification failed",
            message=frappe.get_traceback(),
        )


def ensure_dependency_doctypes():
    """before_migrate: unconditionally create our dependency doctypes.

    The pre_model_sync patches that normally handle this run ONCE — and
    if a migrate ever failed and "Skip failing patches" was used on
    Frappe Cloud, the patch is marked executed without having run, the
    child doctypes never exist, and every later migrate aborts when the
    alphabetical model sync validates a parent's Link/Table against a
    missing child (field report: "DocType AlphaX POS Notify Recipient
    not found" persisting on v15.9.1). A before_migrate hook has no
    execution history: it runs at the START of EVERY migrate, checks
    existence, imports what's missing in dependency order, and no-ops
    in a healthy site. This permanently retires this failure class.
    """
    import os

    from frappe.modules.import_file import import_file_by_path

    ordered = (
        "alphax_pos_print_station",      # v15.8 stations before rules/tickets
        "alphax_pos_kot_routing_rule",
        "alphax_pos_combo_component",    # children before parents
        "alphax_pos_notify_recipient",
        "alphax_pos_combo",
    )
    name_of = {
        "alphax_pos_print_station": "AlphaX POS Print Station",
        "alphax_pos_kot_routing_rule": "AlphaX POS KOT Routing Rule",
        "alphax_pos_combo_component": "AlphaX POS Combo Component",
        "alphax_pos_notify_recipient": "AlphaX POS Notify Recipient",
        "alphax_pos_combo": "AlphaX POS Combo",
    }
    base = frappe.get_app_path("alphax_pos_suite", "alphax_pos_suite", "doctype")
    created = []
    for folder in ordered:
        try:
            if frappe.db.exists("DocType", name_of[folder]):
                continue
            path = os.path.join(base, folder, f"{folder}.json")
            if os.path.exists(path):
                import_file_by_path(path, force=True)
                created.append(name_of[folder])
        except Exception:
            frappe.log_error(
                title=f"AlphaX POS: ensure doctype {folder} failed",
                message=frappe.get_traceback(),
            )
    if created:
        frappe.db.commit()
        frappe.logger().info(f"AlphaX POS before_migrate created: {created}")
