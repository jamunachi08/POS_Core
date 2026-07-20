# AlphaX POS Suite v15.6.5 — Cache-Busted Assets

## The problem

After deploying v15.6.4, the browser still executed v15.6.3's
`main.js` and crashed with the already-fixed load-order error.
Verified: GitHub main was byte-correct at v15.6.4; the browser's own
network log showed assets served "from disk cache".

Root cause: Frappe stamps its own bundles with `?v=<hash>`, but the
cashier's loader URLs carried no version parameter. Browsers and
Frappe Cloud's edge cache therefore pinned old copies of `main.js`,
`sfc-loader.js`, the vendor bundles, and every `.vue` file across
releases. Any future SPA update would hit the same wall.

## The fix

Every `/assets/alphax_pos_suite/...` URL the register loads is now
stamped `?v=<installed app version>` (from `frappe.boot.versions`,
falling back to a timestamp). Stable caching within a release, instant
bust on upgrade. Applied in all three loaders:

- `page/alphax_cashier/alphax_cashier.js` — vendor bundles, bootstrap
  scripts, and the `ALPHAX_SPA_FETCH` assets attempt; exports the
  stamp as `window.ALPHAX_ASSET_VER`.
- `sfc-loader.js` — standalone `.vue` fetch fallback honors the stamp.
- `main.js` — ESM module fetch fallback honors the stamp.

The API fallback endpoints need no stamping (`/api/method` is never
edge-cached).

## Verification

Full jsdom boot simulation re-run with stamped URLs: 28/28 components
compiled, CashierView mounted, add-to-cart correct, settings policy
delivered, return mode functional.

## Deploy note

Because the OLD page loader (without stamps) may itself be cached in
open desk sessions, do ONE hard refresh (Ctrl+Shift+R) after this
deploy. Desk page JS is served through the API on route load, so
normal navigation to /app/alphax-cashier also picks it up fresh.
