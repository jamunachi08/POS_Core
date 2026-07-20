# AlphaX POS Suite v15.6.3 — Root Cause: App Layout

## The real bug, finally

The v15.6.2 self-diagnosing error card reported from neotectest:

    app files present: NO
    sites/assets link: missing

which exposed the true, original defect: **the app's directory layout
was non-standard**. Frappe serves `/assets/<app>/...` from
`<package>/public`, but this repo kept `public/` (and `www/`, `config/`)
one level deeper, inside the module folder:

    had:      alphax_pos_suite/alphax_pos_suite/public   ← invisible to Frappe
    expected: alphax_pos_suite/public                     ← what bench build links

DocTypes and desk pages always worked because they live in the MODULE
folder, which happens to share the app's name — masking the problem.
`/assets` never resolved on a clean bench; every past asset workaround
(committing pre-built bundles, rebuild hooks) treated symptoms.
Confirmation: `cashier/vendor.py` already wrote its runtime-fetched
bundles to `get_app_path()/public` — the CORRECT path — so fetched and
committed files were living in two different trees.

## Changes

- **Moved `public/`, `www/`, `config/` to the package root** (Frappe's
  expected layout). `/assets/alphax_pos_suite/...` now works the way it
  does for every other Frappe app — no rebuild hooks needed.
- Makefile and `frontend/vite.config.js` output paths updated.
- `setup.py` package_data extended for the new locations; wheel autopsy
  confirms all 59 public files + www ship at the package root.
- `cashier/assets.py` fallback now probes multiple roots best-first
  (get_app_path, package location old AND new layout, bench apps clone)
  and serves from whichever verifiably contains the SPA — tested
  against both the healthy and the observed split-brain scenario.
- `asset_health` v2 prints every probed root with its result on the
  error card.
- `force_rebuild_assets` gained strategy 0: if the assets link is
  missing/incomplete but a verified-complete public root exists,
  symlink directly to it.

## Upgrade

Push and deploy; no data migration involved. The assets link created by
FC's `bench build` will now point at a `public/` directory that
actually exists.
