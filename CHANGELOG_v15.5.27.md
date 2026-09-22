# CHANGELOG — v15.5.27

## Improved — v2 cashier error screen now tells you WHY (and gives a way out)
The "Something went wrong loading the register" card was generic. It now:
- **Shows the actual failing file** (e.g. "Failed to load
  /assets/alphax_pos_suite/dist/vendor/cashier/main.js") so an admin can see
  the real cause without a stack trace.
- **Offers an "Open Classic register" button** so a cashier is never stuck —
  Classic works even when v2's display files aren't published yet.
- **Auto-retries at most once per session** (via sessionStorage) instead of
  looping a reload forever when files are genuinely missing.

## Why v2 was failing (diagnosis, not a code bug)
All v2 SPA files (main.js, sfc-loader.js, globals.css, vendor bundles) are
present in the app. The failure means they aren't being **served** at
`/assets/alphax_pos_suite/...` on the site — i.e. assets weren't built /
symlinked on the bench. The Vue/Pinia libraries fall back to CDN and load,
which hides this, then the SPA's own files 404 → the generic error.

Fix on the site: rebuild & publish assets, then hard-refresh:
    bench build --app alphax_pos_suite
    bench --site <site> clear-cache
(Frappe Cloud: redeploy so the build step republishes assets.)
