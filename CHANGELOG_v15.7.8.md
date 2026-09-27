# AlphaX POS Suite v15.7.8 — Custom-field drift: fresh installs were missing 11 fields

## Queue flush failing: 1054 Unknown column 'tabSales Invoice.alphax_client_uuid'

Field report (testneo.frappe.cloud): the offline queue (fixed in
v15.7.7) captured the sale correctly, but every flush attempt failed —
the dedupe hook queries Sales Invoice by `alphax_client_uuid`, and the
column didn't exist on the site.

Root cause is a whole *class* of drift, not one field: **eleven custom
fields were defined only in the v15.0 upgrade patch**, which fresh
installs never execute. Any site installed from scratch was missing:

- `Sales Invoice.alphax_client_uuid` — offline-queue dedupe key
  (unique, read-only, no-copy); without it, retries after a dropped
  network could double-post sales
- `Sales Invoice` loyalty set: `alphax_loyalty_program`,
  `alphax_loyalty_redeem_points`, `alphax_loyalty_redeem_value`,
  `alphax_loyalty_earned_points`
- `Sales Invoice.alphax_outlet`, `AlphaX POS Profile.alphax_outlet` —
  outlet stamping
- `Customer.alphax_default_loyalty_program`
- `AlphaX POS Loyalty Ledger.custom_expired`
- `AlphaX POS Outlet.zatca_enabled`, `AlphaX POS Outlet.zatca_section`

Loyalty and per-outlet ZATCA configuration were therefore silently
inoperative on fresh sites, not just the queue.

## Fixes

- All eleven definitions extracted from the patch (verbatim, via AST)
  and merged into `data/custom_fields_seed.json`, stamped with the
  `"doctype": "Custom Field"` marker the create loop requires, ordered
  so `insert_after` chains resolve (loyalty fields precede
  `alphax_client_uuid`). Seed validated: 37 rows, zero would-skip,
  zero insert_after order violations.
- **`ensure_custom_fields_silently` added to after_migrate**: until
  now `create_custom_fields()` ran only in after_install, so a site
  installed while the seed was deficient stayed deficient forever.
  The function is idempotent (per-field exists check), so it now runs
  on every migrate — any field added to the seed reaches every site on
  its next deploy. This closes the drift class permanently, matching
  the existing self-healing conventions (SPA payload stamp, asset
  rebuild).

## After deploying

`bench migrate` creates the missing fields automatically. The queued
sale on the register will flush on the worker's next retry (or reload
the register to trigger it) — the two failed attempts will succeed
once the column exists.
