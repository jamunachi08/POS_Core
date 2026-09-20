# v15.5.28

## Deployment / packaging fix (resolves /assets 404 on Frappe Cloud)
- Unified the build backend to setuptools (removed conflicting flit config in
  pyproject.toml). setuptools + MANIFEST.in (`graft`) + `include_package_data`
  + explicit `package_data` now guarantee that **all static assets** under
  `public/` (incl. `public/dist/vendor/...`) and `www/` ship in both the sdist
  and the wheel — so `/assets/alphax_pos_suite/...` is always served and the
  cashier/v2/v3/Classic screens stop returning nginx 404.
- Removed the `.gitignore` rule that was ignoring `public/dist/` (latent trap).

## Screens added in this line (already present, now publishable)
- New cashier screen at `/alphax-pos` (Vue 3, vendored, wired to pos_boot,
  catalog via Item/Item Price, card reader, loyalty, Sales Invoice checkout).
- Customer/kiosk web ordering at `/bonanza_order?token=...` + guest
  `get_qr_menu` endpoint.
- Printable table-QR generator: `ensure_table_token` /
  `generate_outlet_table_tokens` endpoints, **Order QR** buttons on AlphaX POS
  Table and Outlet, and the `/table_qr` print page (offline QR lib vendored).
