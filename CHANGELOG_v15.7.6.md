# AlphaX POS Suite v15.7.6 — Terminal Picker: real errors, real labels

## "No terminals configured" with a terminal that clearly exists

Field report (WhiteHelmet site): an AlphaX POS Terminal existed and was
readable in the desk, yet the boot screen said "No terminals
configured".

Root cause: the picker listed terminals via raw
`frappe.client.get_list`, which applies role permissions and **silently
returns an empty list** when the logged-in user's roles have no read
grant on the AlphaX POS Terminal DocType (or a User Permission on a
linked master filters everything out). The BootScreen then swallowed
every error into the same empty state — access-denied and
genuinely-empty were indistinguishable, on screen and in support.

## Fixes

- **New endpoint** `boot.api.list_terminals`: if the user lacks read
  access it *throws* with a fix-it message naming the user and the
  exact permission to grant; otherwise it returns terminals (name,
  outlet, branch, hostname) via `get_all` after the explicit
  doctype-level check — per-document User Permissions on linked
  masters no longer make hardware vanish from the picker.
- **BootScreen** now has a distinct error state that shows the server's
  message verbatim instead of collapsing everything into "No terminals
  configured"; the empty state itself now tells you what to create.
  Both states localized EN/AR.
- **Auto-select single terminal**: one configured terminal and nothing
  stored means that IS the terminal — the cashier no longer taps a
  one-item list on every fresh device.
- Terminal cards show `outlet · branch` under the ID so multi-outlet
  sites can tell terminals apart.
- **client.js error unpacking**: Frappe packs human messages into
  `_server_messages` JSON; the API client now unpacks them so every
  boot card and toast shows "Your user has no read access to…" instead
  of a wall of escaped JSON. Benefits all endpoints, not just this one.
- Fixed a latent template bug: the terminal loop variable `t` shadowed
  the i18n `t()` inside the picker markup.

## After deploying

If the picker now shows a permission error instead of the list: open
Role Permission Manager → AlphaX POS Terminal → grant Read to the role
your cashier users hold (e.g. a dedicated "AlphaX Cashier" role), then
reload the register.

Payload integrity: payload = tree = stamp (a76e272e…), versioned
self-heal from v15.7.5 carries this build to the site even if git
transport drops the vendor tree.
