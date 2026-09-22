# AlphaX POS Suite

Custom Frappe v15 POS for retail, restaurants, and pharmacies in Saudi
Arabia, with ZATCA Phase 2 e-invoicing support.

## For deploying v15.5.7

**Read `DEPLOY_v15.5.7.md`.** It walks through:

1. Run `python3 fetch_vendor_bundles.py` (downloads Vue/Pinia/vue-i18n
   into the repo)
2. Commit those files via git
3. Deploy through Frappe Cloud's UI
4. Verify the cashier loads

The current version is 15.5.7 — cashier vendor bundles are now embedded
in the repo so the cashier loads even when the bench can't reach the
internet.

## Architecture

Three components:

- `alphax-pos-core` (this repo) — Frappe app, Vue cashier UI, no-build
  runtime SFC compilation
- `alphax-zatca` (separate repo) — ZATCA Phase 2 fork from ERPGulf
- `alphax-pos-bridge` (separate repo) — hardware bridge daemon (runs on
  cashier PCs, not on Frappe Cloud)

## License

Proprietary. © 2026 Neotec.

ZATCA fork is GPL-3.0 by ERPGulf, modified under same license.
