# CHANGELOG — v15.5.24

## Fixed — "Page #Form not found" / "Page #List not found" on setup pages
The AlphaX Bonanza setup page (and two others) built their buttons with the
**old pre-v15 hash routes** (`#Form/DocType/name`, `#List/DocType/List`).
Frappe v15 removed hash routing and uses path routes
(`/app/<doctype-slug>[/<name>]`), so every button raised
"Page #Form not found" / "Page #List not found".

Fixed in all three pages so every button opens the right list/form:
- `alphax-pos-setup` — all 13 buttons (Settings, Outlets, Terminals, POS
  Profiles, Floors, Tables, Kitchen Stations, Item→Station, Recipes,
  Processing Log, Offers, POS Orders) now use correct routes. Also added a
  prominent **"Run the guided 5-step setup wizard"** button and an
  **"Open Cashier"** button.
- `alphax-pos-classic` — the held-order **Open** link.
- `alphax-pos-central-kitchen-dashboard` — the request link.

Routes are built with `frappe.router.slug()` (with a safe fallback), so they
stay correct for any doctype name.

## Note — "Page alphax-pos not found"
This came from an obsolete `alphax-pos` Page row left in the database from an
older build (the cashier was renamed to `alphax-pos-classic` / `-v2`). The
existing migration patch `remove_obsolete_alphax_pos_page` deletes it on
migrate, and the workspace shortcuts already point at the correct pages, so
this clears once this version is deployed.
