# AlphaX POS Suite — v15.16.0

**Setup & Install from the process flow board**, plus the fix for the
`TableMissingError` on `AlphaX POS Settings` and the `Windows NT 10.0`
hostname.

## New — Setup & Install on `/app/alphax-pos-flow`

A **Setup & Install** primary button on the board, and a yellow banner at
the top whenever something is outstanding. Opens a checklist of the site and
of every terminal, and installs whatever the server can install.

Every item is one of three kinds, and they are never blurred together:

| Kind | Who can finish it | Examples |
|---|---|---|
| **Automatic** | the server, one click | roles, custom fields, permissions, seeded masters, printer profiles, print stations, kitchen stations, flow board |
| **Needs the PC** | only the AlphaX Bridge on that machine | PC hostname, hardware UUID, MAC, bridge installed, port, devices |
| **By hand** | a human decision | card readers, payment terminal settings |

### Why the PC Identity and Hardware Bridge sections cannot be "fetched"

A browser cannot read a PC's hostname, hardware UUID or MAC address. Those
fields, and the bridge state below them, are written by the AlphaX Bridge
daemon running on the till itself (`onboarding/api.report_bridge_state`, on
every boot and 5-minute heartbeat). So for each terminal the checklist
offers **Download bridge** — the existing personalised installer from
`onboarding/bridge_dist.bootstrap`, carrying a pairing token for this site.
Run it on that PC and the fields fill themselves in within five minutes.
Downloading is not installing, and the dialog says so.

If no installer is bundled with the build, the button falls back to the
external install plan from `onboarding/api.get_bridge_installers` and tells
you to run `scripts/sync_bridge_kit.ps1` and redeploy.

### Nothing is re-implemented

Every automatic step delegates to the installer the app already runs on
`bench install-app` and `bench migrate` — `install.create_roles`,
`create_custom_fields`, `apply_permissions`, `heal_lost_manager_access`,
`seed_order_types`, `seed_domain_packs`, `onboarding.setup.ensure_onboarding_fields`
and the rest. The button and a migrate can never disagree about what
"installed" means. Each step is idempotent, and a failure in one is logged
and reported without stopping the others.

### Hardware follows the hardware plan

Printing, kitchen and card items are only marked required when some
terminal's hardware plan actually ticks the matching device — the same rule
the cashier's hardware panel already uses. A tablet-only site is not told it
is missing a kitchen printer.

New defaults, created only when absent:

- Printer profiles **AlphaX Thermal 80mm** (receipt, drawer kick) and
  **AlphaX Kitchen Ticket 80mm**
- One **Receipt** print station per outlet, the first marked default
- One **Main Kitchen** station per outlet

Card readers are deliberately **never** auto-created. They carry a vendor,
merchant ID and credentials; a placeholder would give a till a payment
device that fails at the first card sale.

### Access

Readiness is visible to Supervisor, Manager and System Manager. Installing
requires Manager or System Manager. A cashier sees no banner and no button
action.

## Fixed

### `TableMissingError: ('DocType', 'AlphaX POS Settings')`

`AlphaX POS Settings` is a Single, which has no table. The board built its
route as `/app/<slug>/view/form` — not a real Frappe route — which fell
through to the List view and queried a table that does not exist.

`flow_api` now reads `issingle` from the doctype meta. Singles open as a
form, never show a **New** button, and are never counted. Separately,
`AlphaX POS Payment Terminal Settings` turned out **not** to be a Single;
it is a normal named doctype and is treated as one.

### `PC Hostname = "Windows NT 10.0"`

The setup wizard's fallback copied the first token of `navigator.userAgent`
into the hostname field. That token is the operating system, not the
machine name, and it then stuck on the terminal because the bind step keeps
an existing hostname. The fallback is removed.

For terminals already carrying such a value, the checklist shows a
**Terminal hostnames** item that clears them. It matches only OS tokens
(`Windows NT x.y`, `Macintosh`, `X11`, `Linux …`, `iPhone`, `Android …`,
`CrOS …`) and only on terminals with no bridge installed — tested against
eight OS strings and nine real hostnames including `MacBook-Pro`,
`Windows-Till` and `POS-ANDROID-1`, none of which are touched.

## verify_tree.py

- Section 7 gains: **a node on a Single doctype must use Form view.**
- New section 9: **every server call on the flow page resolves to a
  whitelisted Python function.** A renamed function otherwise fails silently
  in the browser as a 404.

Both mutation-tested: a `List` view on `AlphaX POS Settings` and a typo in
`bridge_download` each fail the build.

## Files

```
pos/flow_setup.py                                NEW  readiness, run_setup, bridge_download
pos/flow_api.py                                  Single detection, routing, counts
page/alphax_pos_flow/alphax_pos_flow.js          Setup & Install button, banner, checklist dialog
page/alphax_pos_setup_wizard/...setup_wizard.js  user-agent hostname fallback removed
simulate_process_flow.py                         guard 8: Singles
verify_tree.py                                   Single-view rule, section 9
alphax_pos_suite/__init__.py                     15.16.0
```

No doctypes changed; no migration step of its own.
