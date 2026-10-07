# CHANGELOG — v15.5.21

Follow-up to v15.5.20. The traceback showed the orphaned ZATCA leftover was
not a stray custom field by module, but a **child table the removed app had
added to Company**. On `Company.insert()`, Frappe instantiates that child
table and throws "Module Zatca Erpgulf not found", aborting the wizard.

## Fixed
- **Setup repair now also removes fields that *point at* an orphaned
  doctype.** Previously it matched a record's own `module`; now it first
  finds the orphaned foreign DocTypes, then deletes any Custom Field whose
  `options` targets one of them — regardless of that field's own module.
  This clears the child-table field on Company that was blocking setup.
- **Self-healing retry around Company creation.** If `comp.insert()` still
  raises a "Module … not found" error, the wizard runs the repair, refreshes
  caches, and retries once with a fresh document whose meta no longer
  includes the broken field.
- The repair now calls `frappe.clear_cache()` after cleaning so doctype
  metas (e.g. Company) are rebuilt without the removed field.

## Unchanged safety guarantees
- Still only touches modules that look like ZATCA / ERPGulf **and** are
  genuinely orphaned. A properly installed ZATCA app is untouched.
- Still **never drops a DocType** (your data). Orphaned doctypes are
  reported in `doctypes_found`; only their dangling *field references* and
  customization records are removed.

## Apply
Deploy and migrate (the repair runs on migrate), then open
`/app/alphax-pos-setup-wizard`. Or run `preview_setup_blockers` first to see
what will be cleaned.
