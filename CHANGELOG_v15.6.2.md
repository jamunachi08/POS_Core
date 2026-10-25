# AlphaX POS Suite v15.6.2 — Asset-Pipeline Immunity

## The problem

On neotectest.frappe.cloud the cashier failed with
`Failed to load /assets/.../cashier/sfc-loader.js` even though:

- the file is committed to the repo (verified byte-identical against
  GitHub main),
- the deployed code is live (the custom error card itself is new code),
- Frappe's build cleanup provably does not delete these files (verified
  against frappe v15's esbuild/build-cleanup.js source).

Conclusion: Frappe Cloud's asset pipeline intermittently fails to serve
committed files under `public/` — a recurrence of the platform issue
this product has hit before. We do not control that pipeline, so the
register now no longer depends on it.

## The fix: a second supply line

New module `cashier/assets.py`:

- **`spa_asset(path)`** — serves any single SPA file, read directly from
  the installed app package via Python. Bypasses bench build, symlinks,
  and nginx asset serving entirely.
- **`spa_manifest()`** — all 47 SPA source files in one JSON payload
  (~273KB), so a fallback boot costs one round-trip, not 47.
- **`asset_health()`** — server-side diagnosis: do the files exist in
  the app package? does sites/assets resolve? is the file visible
  through the assets path?

Hardening: login required, realpath containment (no traversal), strict
extension allow-list. Serves only files that are already public web
assets.

## Loader changes

- The desk page defines `window.ALPHAX_SPA_FETCH` — tries `/assets`
  first (fast, cacheable), and on the FIRST failure pulls the full
  manifest through the API and serves everything from memory.
- `sfc-loader.js` and `main.js` route their fetches through the same
  hook. Bootstrap scripts inject inline when `/assets` is broken.
- `globals.css` loads through the same supply lines (inline `<style>`).
- The error card now **self-diagnoses**: it calls `asset_health` and
  prints the server's view (app files present / assets link kind / file
  visible via assets / API reachable), so a screenshot of the card is
  an actionable bug report. Stale "open Classic register" Arabic text
  removed.

## Net effect

A healthy site behaves exactly as before (assets path, zero API cost).
A site with a broken asset pipeline boots the full register anyway,
about one second slower on first load, and says why in the console.
