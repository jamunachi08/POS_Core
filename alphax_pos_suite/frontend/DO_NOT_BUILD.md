# DO NOT BUILD THIS FOLDER

This folder contains the **original Vite-based source** for the AlphaX
POS cashier UI.

As of v15.4.0 (April 2026), the cashier no longer ships a pre-built
bundle. The `.vue` source files in this folder are mirrored into
`alphax_pos_suite/public/dist/cashier/sfc/` and compiled at runtime by
the SFC loader in the browser. This avoids requiring `npm install`
during `bench install-app` (which broke installs on Frappe Cloud).

**Do not** add a `package.json` to the parent (`alphax_pos_suite/`)
folder. Doing so will cause `bench build` to try to invoke `npm` here,
which will fail on most production benches and prevent ANY of the app's
public assets from being symlinked to `sites/assets/`.

This folder is kept around for:
  - Local development with `npm run dev` (your own machine, your own npm)
  - Reference / source-of-truth for the .vue files
  - Future migration if/when we go back to a pre-built bundle

It is **not** read by the Frappe install pipeline.
