# CHANGELOG — v15.5.20

Fixes the Setup Wizard failure: **"Module Zatca Erpgulf not found."**

## Root cause
A previous, partially-removed third-party app (ERPGulf's ZATCA) left
orphaned customization records and/or a Module Def pointing at a module
whose app code is no longer on the bench. When the wizard created the
Company, Frappe tried to resolve that module to an owning app, failed,
and aborted setup. This was a site-data problem, not a bug in the POS app.

## Added — self-healing setup repair
- New `setup_repair.py` with `repair_orphaned_module_blockers()`:
  - Detects modules that look like ZATCA/ERPGulf **and** are genuinely
    orphaned (no Module Def, or an owning app not in the installed list).
    A properly installed ZATCA app is left untouched.
  - Removes only **customization** records (Custom Field, Property Setter,
    Client/Server Script, Print Format/Style, Report, Notification,
    Dashboard Chart, Number Card, Workspace, Web Form) and the orphan
    Module Def.
  - **Never drops a DocType** (that would delete data) — orphaned DocTypes
    are reported instead, and the Module Def is preserved while one exists.
  - Idempotent; no-op on clean sites.
- Whitelisted entry points: `repair_setup_blockers` (apply) and
  `preview_setup_blockers` (dry run).
- Wired to run automatically: at the **start of the Setup Wizard**, in
  **after_install**, and in **after_migrate**. So simply redeploying this
  version heals the site — you don't even need to open the wizard first.
- Clearer wizard error: if a "Module … not found" ever surfaces again, the
  message now points you to `repair_setup_blockers`.

## Cleaned — workspace fixture
- Removed the dead "ZATCA App" link (pointed at a non-existent
  `Zatca Settings` doctype).
- Relabelled the mislabelled "ZATCA Status" shortcut to "Activity Log"
  (it already pointed at the POS Processing Log).
- The Hub now has no dead ZATCA links on a deferred-ZATCA install.

## How to apply
Redeploy this version and run a migrate (Frappe Cloud: deploy the update).
The repair runs on migrate; then re-open `/app/alphax-pos-setup-wizard`.
If you prefer, run `repair_setup_blockers` once, then the wizard.
