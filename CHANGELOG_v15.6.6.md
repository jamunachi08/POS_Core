# AlphaX POS Suite v15.6.6 — Boot SQL Fixes + Schema Audit

## Context

v15.6.5's cache-busted loaders delivered the register's own BootScreen
for the first time — which called `pos_boot` for the first time on a
real database, exposing server-side SQL against columns that don't
exist. An app-wide static schema audit (every `frappe.get_all` field
list checked against the shipped DocType JSONs) found three instances
of the same day-one bug class:

1. **`_scale_rules`** (the 500 on screen): queried the RULE doctype
   with the DEFINITION doctype's field list ("Unknown column
   'prefix'"). Now reuses the barcode module's canonical
   `_active_definitions()` query, wrapped non-fatally.
2. **`_payment_methods_for_profile`**: selected `default`, `amount`,
   `allow_in_returns` — none exist on AlphaX POS Profile Payment
   Method (real schema: `is_default`, `button_color`, `sort_order`).
   Would have 500'd boot the moment a POS profile was attached.
3. **Shift-close & day-close reports**: selected `grand_total` from
   AlphaX POS Order, which has no such column — first shift close
   would have crashed. Totals now derive from the linked Sales Invoice
   or the order's payment rows (`reporting/order_totals.py`).

## Boot resilience

`pos_boot` now wraps every OPTIONAL payload section (domains, features,
loyalty, taxes, currency, payment methods, theme, scale rules,
settings) individually: a failing section logs to Error Log and
degrades to a safe default instead of 500ing the terminal. Terminal
and outlet resolution remain fatal by design — there is no register
without them.

## Verification

- App-wide schema audit: zero remaining mismatches.
- Full jsdom boot simulation: register mounts, cart, settings, and
  return mode all functional.
