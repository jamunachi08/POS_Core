# CHANGELOG — v15.5.19

This release focuses on **install reliability**, **first-run usability**,
and a **proper barcode-scanning subsystem**.

## Fixed (install / usability blockers)

- **Terminal now resolves its outlet.** `boot.api._resolve_outlet_for_terminal`
  read a non-existent `outlet` field; the actual Terminal field is
  `pos_outlet`. The cashier was booting with no outlet, no domains, no taxes,
  and no loyalty. Now reads `pos_outlet` (with `outlet` kept as a fallback).
- **Setup Wizard now produces a *usable* POS Profile.** The auto-created
  profile previously had no payment method and no applicable users, so the
  register could ring items but never complete a sale. The wizard now:
  - attaches a default **Cash** Mode of Payment (creating + wiring its
    company account if needed),
  - adds the admin + current user as applicable users,
  - stamps the outlet onto the profile's `alphax_outlet` field so
    terminal→outlet resolution always works.
- **Single workspace.** Removed the duplicate `AlphaX Bonanza POS` workspace
  created at install time; `AlphaX POS Hub` (the themed one) is now the only
  POS workspace.
- **Vendor bundles are actually embedded now.** `vue.global.prod.js`,
  `pinia.iife.prod.js`, and `vue-i18n.global.prod.js` are committed under
  `public/dist/vendor/`, so the cashier loads instantly and offline as the
  docs promised. Relaxed the Pinia size validator (Pinia 3.x is ~5 KB).
- **Removed dead code:** the orphaned triple-nested `install.py`.
- **Version consistency:** everything now reports `15.5.19`.

## Added — Barcode scanning subsystem

A real, configurable barcode pipeline — the core retail/grocery capability.

- **`barcode/parser.py`** — pure-Python, unit-tested parser for
  variable-measure (weight/price-embedded) barcodes. Driven entirely by the
  existing `AlphaX POS Scale Barcode Definition` records, so it's editable
  from the desk with zero code.
- **`barcode/api.py::scan_barcode(code, pos_profile, outlet)`** — one
  whitelisted endpoint that resolves, in order:
  1. a standard product barcode via ERPNext's native **Item Barcode** table
     (EAN-13 / UPC / Code-128),
  2. a **scale/weight/price** barcode (PLU + embedded value),
  3. a bare **item code / PLU**.
  Returns a normalised, cashier-ready line with the correct **price-list**
  rate (falls back to the item's standard rate).
- **`composables/useBarcodeScanner.js`** — keyboard-wedge listener. Any USB
  or Bluetooth scanner works with no driver; it never interferes with typing
  into the search box or dialogs.
- **Cashier wiring:** `api.scanBarcode`, a `pos.scan(code)` store action that
  adds straight to the cart, and toast feedback on hit/miss.
- **Seeded on install:** a sensible default EAN-13 weight scheme
  (`2 PPPPP VVVVV C`) + a catch-all rule, so deli/produce/butcher barcodes
  work out of the box.
- **Shipped test:** `tests/test_barcode_parser.py` (7 cases).

## Notes / decisions left to you

- **License mismatch:** `hooks.py`/`pyproject.toml` say MIT, the README says
  Proprietary © Neotec. Pick one — it's a business call, so I left it.
- The dev source in `frontend/src/` was **not** mirrored; the running app
  uses the no-build files in `public/dist/vendor/cashier/sfc/`, which is what
  I edited. Sync `frontend/src` later if you maintain that path.
