"""
Setup self-heal.

A previous (partial) install of a third-party app — most commonly the
ERPGulf ZATCA app — can leave behind customization records (Custom Fields,
Property Setters, Scripts, Print Formats, Reports…) and/or a Module Def
that point at a module whose app code is no longer on the bench. When
Frappe later has to resolve that module to an owning app (for example
while the Setup Wizard creates a Company), it raises:

    Module Zatca Erpgulf not found

…which aborts whatever operation was running.

This module removes those *orphaned* references so setup can proceed. It is
deliberately conservative:

  * It only touches modules whose name looks like ZATCA / ERPGulf AND that
    are genuinely orphaned (no Module Def, or an owning app that is not in
    the site's installed-apps list). A properly installed ZATCA app is
    left completely alone.
  * It removes only *customization* records (never your data). Orphaned
    DocTypes are reported, not dropped, because dropping a DocType deletes
    its table.

Run automatically at the start of the Setup Wizard and on every migrate,
or manually:  AlphaX POS → run `repair_setup_blockers`.
"""
from __future__ import annotations

import frappe
from frappe import _

# Customization doctypes that carry a `module` field and are safe to remove
# when orphaned (none of these hold business data).
CUSTOMIZATION_DOCTYPES = [
    "Custom Field", "Property Setter", "Client Script", "Server Script",
    "Print Format", "Print Style", "Report", "Notification",
    "Dashboard Chart", "Number Card", "Workspace", "Web Form",
]


def _looks_foreign(module_name: str) -> bool:
    """Scope the repair tightly to the known ZATCA / ERPGulf leftovers."""
    if not module_name:
        return False
    s = frappe.scrub(module_name)
    return ("zatca" in s) or ("erpgulf" in s)


def _owner_map() -> dict:
    """scrub(module) -> app_name, built from Module Def records."""
    out = {}
    try:
        for md in frappe.get_all("Module Def", fields=["name", "app_name"]):
            out[frappe.scrub(md.name)] = md.app_name
    except Exception:
        pass
    return out


def repair_orphaned_module_blockers(dry_run: bool = False) -> dict:
    """Remove orphaned ZATCA/ERPGulf customization records + Module Defs.

    Returns a summary dict:
        {ok, removed: [..], doctypes_found: [..], module_defs: [..]}
    """
    summary = {"ok": True, "removed": [], "doctypes_found": [], "module_defs": []}

    try:
        installed = set(frappe.get_installed_apps())
    except Exception:
        installed = set()
    owners = _owner_map()

    def is_orphan(module_name: str) -> bool:
        if not module_name:
            return False
        app = owners.get(frappe.scrub(module_name))
        if not app:          # no Module Def at all -> this is what throws
            return True
        return app not in installed  # Module Def points at a missing app

    # 0) Identify orphaned foreign DocTypes FIRST. This lets us also clear
    #    any field that *points at* one of them — e.g. a child-table Custom
    #    Field the removed ZATCA app added to Company. That field is exactly
    #    what makes Company creation throw "Module ... not found" inside the
    #    Setup Wizard (Frappe instantiates the child table on insert).
    orphan_doctypes = set()
    try:
        for d in frappe.get_all("DocType", fields=["name", "module"]):
            if _looks_foreign(d.get("module")) and is_orphan(d.get("module")):
                orphan_doctypes.add(d.name)
    except Exception:
        pass
    summary["doctypes_found"] = sorted(orphan_doctypes)

    # 1) Remove orphaned customization records: those whose OWN module is the
    #    foreign orphan, PLUS any Custom Field whose TARGET (options) is an
    #    orphaned DocType — regardless of the field's own module.
    for dt in CUSTOMIZATION_DOCTYPES:
        try:
            if not frappe.db.exists("DocType", dt):
                continue
            if not frappe.db.has_column(dt, "module"):
                continue
            fields = ["name", "module"]
            if dt == "Custom Field":
                fields += ["options", "fieldtype", "dt"]
            rows = frappe.get_all(dt, fields=fields)
        except Exception:
            continue
        for r in rows:
            mod = r.get("module")
            remove = _looks_foreign(mod) and is_orphan(mod)
            if dt == "Custom Field" and r.get("options") in orphan_doctypes:
                remove = True  # field points at a broken doctype
            if not remove:
                continue
            label = f"{dt}: {r.name}"
            if dt == "Custom Field" and r.get("dt"):
                label = f"Custom Field on {r.get('dt')}: {r.name}"
            summary["removed"].append(label)
            if not dry_run:
                try:
                    frappe.delete_doc(
                        dt, r.name, force=1,
                        ignore_permissions=True, ignore_on_trash=True,
                    )
                except Exception:
                    # Last resort: blank the module so it stops throwing.
                    try:
                        frappe.db.set_value(
                            dt, r.name, "module", None, update_modified=False
                        )
                    except Exception:
                        pass

    # 2) Orphaned Module Def(s) — only safe to drop when no orphan DocType
    #    still depends on them (we never drop a DocType / its data).
    try:
        for md in frappe.get_all("Module Def", fields=["name", "app_name"]):
            if _looks_foreign(md.name) and (md.app_name not in installed):
                summary["module_defs"].append(md.name)
                if not dry_run and not orphan_doctypes:
                    try:
                        frappe.delete_doc(
                            "Module Def", md.name, force=1, ignore_permissions=True
                        )
                    except Exception:
                        pass
    except Exception:
        pass

    # Refresh caches so freshly-cleaned doctype metas (e.g. Company) are
    # rebuilt without the removed child-table field.
    if not dry_run:
        try:
            frappe.db.commit()
            frappe.clear_cache()
        except Exception:
            pass

    if summary["removed"] or summary["module_defs"]:
        frappe.logger().info(
            f"AlphaX POS setup-repair: cleared orphaned refs {summary}"
        )
    return summary


@frappe.whitelist()
def repair_setup_blockers():
    """Whitelisted entry point. Safe to run anytime; idempotent."""
    return repair_orphaned_module_blockers(dry_run=False)


@frappe.whitelist()
def preview_setup_blockers():
    """Dry run — report what would be cleaned without changing anything."""
    return repair_orphaned_module_blockers(dry_run=True)


@frappe.whitelist()
def repair_doctypes_now():
    """Browser-callable heal for a site whose migrates have not been
    completing: creates missing dependency doctypes (children first),
    reloads the app's full schema, and physically ALTERs missing
    parent/parentfield/parenttype/idx columns into child tables created
    while istable=0 (Frappe never retrofits standard columns). Column
    inspection uses information_schema directly — ground truth, no
    caches. Idempotent; returns full diagnostics.
    """
    frappe.only_for("System Manager")

    import json as _json
    import os as _os

    from alphax_pos_suite.alphax_pos_suite.install import ensure_dependency_doctypes

    critical = (
        "AlphaX POS Print Station", "AlphaX POS KOT Routing Rule",
        "AlphaX POS Combo Component", "AlphaX POS Notify Recipient",
        "AlphaX POS Combo",
    )
    before = {name: bool(frappe.db.exists("DocType", name)) for name in critical}
    ensure_dependency_doctypes()

    base_dir = frappe.get_app_path("alphax_pos_suite", "alphax_pos_suite", "doctype")
    children, parents = [], []
    for folder in sorted(_os.listdir(base_dir)):
        jpath = _os.path.join(base_dir, folder, f"{folder}.json")
        if not _os.path.exists(jpath):
            continue
        try:
            meta = _json.load(open(jpath))
        except Exception:
            continue
        (children if meta.get("istable") else parents).append(folder)

    reloaded, failed = [], []
    for folder in children + parents:
        try:
            frappe.reload_doc("alphax_pos_suite", "doctype", folder, force=True)
            reloaded.append(folder)
        except Exception:
            failed.append(folder)
            frappe.log_error(
                title=f"AlphaX POS repair: reload {folder} failed",
                message=frappe.get_traceback(),
            )

    healed_columns = []
    column_diagnostics = {}
    for folder in children:
        jpath = _os.path.join(base_dir, folder, f"{folder}.json")
        try:
            dt = _json.load(open(jpath))["name"]
        except Exception:
            continue
        table = f"tab{dt}"
        cols = {
            r[0]
            for r in frappe.db.sql(
                """SELECT COLUMN_NAME FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s""",
                (table,),
            )
        }
        if not cols:
            column_diagnostics[dt] = "NO TABLE"
            continue
        missing = [c for c in ("parent", "parentfield", "parenttype") if c not in cols]
        if "idx" not in cols:
            missing.append("idx")
        column_diagnostics[dt] = {"missing_before": missing or "none"}
        for col in missing:
            ddl = (
                f"ALTER TABLE `{table}` ADD COLUMN `idx` int(8) NOT NULL DEFAULT 0"
                if col == "idx"
                else f"ALTER TABLE `{table}` ADD COLUMN `{col}` varchar(140)"
            )
            try:
                # DDL inside a request transaction trips Frappe's
                # implicit-commit guard (field diagnostics: every ALTER
                # failed with "This statement can cause implicit
                # commit"). sql_ddl commits first, then runs the DDL —
                # the same path Frappe's own schema sync uses.
                frappe.db.sql_ddl(ddl)
                healed_columns.append(f"{dt}.{col}")
            except Exception as e:
                column_diagnostics[dt][col] = f"ALTER FAILED: {e}"
        try:
            frappe.db.sql_ddl(f"ALTER TABLE `{table}` ADD INDEX parent (parent)")
        except Exception:
            pass  # already indexed — non-fatal

    frappe.clear_cache()
    frappe.db.commit()
    after = {name: bool(frappe.db.exists("DocType", name)) for name in before}
    return {
        "existed_before": before,
        "exists_now": after,
        "created": [k for k in after if after[k] and not before[k]],
        "reloaded": reloaded,
        "reload_failed": failed,
        "healed_columns": healed_columns,
        "column_diagnostics": column_diagnostics,
        "note": "Hard-refresh the desk (Ctrl+Shift+R), then run day close.",
    }


@frappe.whitelist()
def diagnose_desk_access(doctype: str = "AlphaX POS Settings"):
    """Why will this doctype's desk page not open?

    Frappe reports a doctype the current user cannot read as
    "Page <slug> not found", which sends everyone hunting for a missing
    page instead of a missing permission. This answers the actual
    question, in order, and says which of the three causes it is.

        /api/method/alphax_pos_suite.alphax_pos_suite.setup_repair.diagnose_desk_access
        /api/method/...diagnose_desk_access?doctype=AlphaX%20POS%20Outlet
    """
    frappe.only_for("System Manager")

    slug = doctype.lower().replace(" ", "-")
    out = {
        "doctype": doctype,
        "expected_url": f"/app/{slug}",
        "user": frappe.session.user,
        "roles": sorted(frappe.get_roles()),
        "checks": [],
    }

    def note(label, ok, detail=""):
        out["checks"].append({"check": label, "ok": bool(ok), "detail": detail})
        return ok

    if not note("DocType row exists", frappe.db.exists("DocType", doctype),
                "Not synced to this site. Run bench migrate, then "
                "setup_repair.repair_doctypes_now if it persists."):
        out["verdict"] = "not_installed"
        return out

    meta = frappe.get_meta(doctype)
    note("is a Single (opens directly at /app/<slug>)", meta.issingle,
         "List doctypes open at /app/<slug>/view/list instead.")

    if not meta.issingle:
        table_ok = frappe.db.table_exists(doctype)
        note("database table exists", table_ok,
             "" if table_ok else "Schema out of step with the doctype.")

    custom = frappe.get_all(
        "Custom DocPerm", filters={"parent": doctype, "permlevel": 0},
        fields=["role", "read", "write"],
    )
    if custom:
        # This is the trap: one custom row and the JSON's own permissions
        # stop applying entirely.
        roles_with_read = sorted(r.role for r in custom if r.read)
        note("custom permissions override the standard set", True,
             f"Standard permissions are IGNORED. Roles with read: "
             f"{roles_with_read or 'none'}")
        note("System Manager retained read", "System Manager" in roles_with_read,
             "Missing — this is what makes the page vanish. "
             "bench migrate now restores it automatically, or call "
             "setup_repair.restore_manager_access.")
    else:
        note("standard permissions in force", True,
             f"Roles with read: "
             f"{sorted({p.role for p in meta.permissions if p.read})}")

    can_read = frappe.has_permission(doctype, "read")
    note("current user can read it", can_read,
         "" if can_read else "The desk route will not resolve for this user.")

    out["verdict"] = "ok" if can_read else "no_permission"
    return out


@frappe.whitelist()
def restore_manager_access(doctype: str | None = None):
    """Give System Manager back read/write on AlphaX doctypes.

    Same repair the migrate hook performs, exposed for a site that cannot
    wait for a deploy. Idempotent.
    """
    frappe.only_for("System Manager")

    from alphax_pos_suite.alphax_pos_suite.install import heal_lost_manager_access

    if doctype:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(_("Unknown doctype {0}").format(doctype))
        if not frappe.db.exists("Custom DocPerm",
                                {"parent": doctype, "role": "System Manager", "permlevel": 0}):
            frappe.get_doc({
                "doctype": "Custom DocPerm", "parent": doctype,
                "parenttype": "DocType", "parentfield": "permissions",
                "role": "System Manager", "permlevel": 0,
                "read": 1, "write": 1, "create": 1, "delete": 1,
                "report": 1, "export": 1, "print": 1, "email": 1, "share": 1,
            }).insert(ignore_permissions=True)
            frappe.clear_cache()
            return {"ok": True, "healed": [doctype]}
        return {"ok": True, "healed": [], "note": "already present"}

    healed = heal_lost_manager_access() or []
    return {"ok": True, "healed": healed,
            "note": "Reload the desk (Ctrl+Shift+R) after this."}
