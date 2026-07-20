# AlphaX POS Suite v15.6.1 — One Cashier Screen

> **v15.6.1 hotfix over v15.6.0:** the cashier page slug is
> **`alphax-cashier`** (route `/app/alphax-cashier`), not `alphax-pos` —
> that slug is reserved by the "AlphaX POS" workspace title, and Frappe's
> `validate_route_conflict` aborts the workspace fixture import if a Page
> squats on it (the exact failure seen installing v15.6.0 on
> neotectest.frappe.cloud). A new `before_install` hook also deletes any
> leftover conflicting Page rows from failed/partial installs, since
> patches don't execute on fresh installs.

## The headline

Five parallel POS surfaces are now **one**: the Vue 3 cashier SPA, promoted
to the route **`/app/alphax-cashier`**, absorbing everything the retired
screens had that it lacked.

## Removed (screens)

| Retired surface | What it was | Why it went |
|---|---|---|
| `alphax-pos-classic` | 53KB jQuery desk-page monolith | Features ported to the SPA (manager PIN, returns) |
| `alphax-pos-v3` | Tailwind rewrite, ~100KB assets | Never finished; App.vue was 110 lines with a mock API |
| `alphax_apos` | "Phase-1" placeholder stub | Dead weight |
| `/alphax-pos` (www) | Static demo mockup, hard-coded data | Demo, not a register |

A migration patch (`consolidate_to_single_pos_screen`) deletes the stale
`Page` rows on upgraded sites. The workspace fixture, workspace generator,
setup wizard, and setup page all now point at the single `alphax-cashier` route.
The wizard also writes the terminal binding to the SPA's localStorage key
(`alphax_pos_terminal`) so setup flows straight into a booted register.

## Added (ported / new in the one screen)

- **Manager PIN gates** — void line and above-threshold discounts now route
  through the server-side `verify_manager_pin` (lockout, rate limit, audit
  log), driven by `AlphaX POS Settings`: `require_manager_for_void`,
  `require_manager_for_discount`, `discount_threshold_percent`.
- **Returns mode** — sidebar toggle, gated by `allow_returns` and the void
  policy. Reason picker backed by `AlphaX POS Return Reason`; posts a
  `Sales Invoice` with `is_return=1`, negative quantities and payments,
  reason stamped in remarks. Red banner across the cart while active;
  auto-clears after posting.
- **Config panel (⚙)** — in-screen, one place to see terminal, outlet,
  company, profile, warehouse, price list, active domains and feature
  flags. Manager roles can flip the safe policy toggles live (server-side
  role check, explicit field allow-list); saving invalidates the boot cache
  and re-boots the terminal. Accounting-critical settings stay desk-only,
  one click away.
- **Boot payload** now carries a `settings` block (explicit allow-list of
  cashier-relevant fields) so policy is enforced offline too.
- New endpoints: `get_cashier_settings`, `update_cashier_settings`,
  `list_return_reasons` (all in `boot/api.py`).

## Fixed

- `patches.txt` contained every patch **twice**; deduplicated.
- Classic-only CSS removed from `app_include_css` (dead ~10KB per desk load).
- SPA error card no longer offers a fallback to a screen that no longer
  exists; it links to the POS Hub instead.
- Cart lines now record `base_rate` at add time, giving approvals a stable
  list price to compare against.

## Upgrade notes

- Bookmarks to `/app/alphax-pos-v2` should be updated to `/app/alphax-cashier`.
- `bench migrate` handles everything else: patch removes retired pages,
  sync installs the renamed page, fixture refresh rewrites the workspace.
