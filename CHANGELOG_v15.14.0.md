# AlphaX POS Suite — v15.14.0

**Role-based process flow page.** Additive. No doctypes, no schema change,
no migration step of its own.

## New

### `/pos_role_flow` — role-filtered process flow

A login-required page that shows the viewer what their role does, in order,
and where it must escalate. Two lanes never reach the same screen: a cashier
gets one lane, a manager gets seven.

Filtering happens in `get_context_payload()` on the server, so a lane the
viewer may not read is **absent from the response**, not hidden in it.
Measured on the rendered HTML from the same URL:

| Role | Lanes | Matrix | Page |
|---|---|---|---|
| `AlphaX POS Cashier` | 1 | own column, 16 rows | 26.8 KB |
| `AlphaX POS Kitchen` | 1 | own column, 3 rows | 15.9 KB |
| `AlphaX POS Supervisor` | 3 (cashier, supervisor, kitchen) | full grid | 55.7 KB |
| `AlphaX POS Manager` | 7 | full grid, 33 rows | 84.0 KB |
| `Accounts Manager` | 1 | full grid | — |
| `System Manager` | 7 | full grid | 84.0 KB |
| no AlphaX role | 0 | — | 9.9 KB "no role assigned" card |

Rows where a non-supervisor has no access at all are dropped rather than
rendered as a column of dashes, which is why the cashier sees 16 of 33.

Bilingual EN/AR with RTL flip, dark/light, and a print stylesheet that
expands every lane the viewer is entitled to.

Two constants at the top of `pos/role_flow.py` control the whole model:

```python
SUPERVISORY_ROLES = {R_ADMIN, R_MANAGER}                 # read every lane
EXTRA_LANES       = {R_SUPERVISOR: ("cashier", "kitchen")}
FULL_MATRIX_ROLES = {R_ADMIN, R_MANAGER, R_SUPERVISOR, R_ACCOUNTS}
```

`SUPERVISORY_ROLES` deliberately mirrors `security.manager_pin.MANAGER_ROLES`
rather than `pos.shift_api._MANAGER_ROLES`. Those two are not the same set,
and the difference is the point of the Supervisor lane (below).

### `role_flow.get_flow()`

Whitelisted, returns the same filtered payload for the cashier SPA or
onboarding help, so on-screen help can never describe a capability the
logged-in user does not hold. Guest callers are rejected.

## Fixed

### `AlphaX POS Kitchen` role was never created

`alphax_pos_kds_ticket.json` grants read/write/create to `AlphaX POS Kitchen`,
but `install.create_roles()` never created that Role. On a fresh site the
permission row pointed at a non-existent role, so no kitchen user could be
given KDS access without hand-creating it first. Now seeded alongside the
other three. Idempotent, so existing sites pick it up on the next migrate.

## Changed

- `verify_tree.py` gains an eighth structural guard (section 6): every
  `MATRIX` row must carry exactly one value per lane. Adding a role without
  extending all 33 rows now fails the build rather than rendering a ragged
  grid.
- `hooks.py` — `/pos-role-flow` aliased to the canonical `/pos_role_flow`.
- Version 15.13.0 → 15.14.0.

## The Supervisor boundary

The matrix values are read out of the code, not out of intent. The
interesting one is where `AlphaX POS Supervisor` stops:

| Source | Supervisor included? |
|---|---|
| `pos/posting.py` `_ensure_role_allowed` | yes — may ring up sales |
| `pos/shift_api.py` `_MANAGER_ROLES` | yes — sees unblinded totals, X report, variance |
| `pos/posting.py` approval branch | **no** — only Manager / System Manager may set Approved |
| `security/manager_pin.py` `MANAGER_ROLES` | **no** — holds no PIN, authorises nothing |
| `alphax_pos_kds_ticket.json` | **no** — cannot advance a KDS ticket |
| Authorization Log doctype | **no** — read is Manager and System Manager only |

So a supervisor sees everything the cashier is blinded from and still fetches
a manager for every PIN gate. That distinction is now visible on the page
instead of living only in five separate source files.

## Files

```
alphax_pos_suite/alphax_pos_suite/pos/role_flow.py    NEW
alphax_pos_suite/www/pos_role_flow.py                 NEW
alphax_pos_suite/www/pos_role_flow.html               NEW
simulate_role_flow.py                                 NEW (repo root)
alphax_pos_suite/alphax_pos_suite/install.py          kitchen role
alphax_pos_suite/hooks.py                             route alias
alphax_pos_suite/__init__.py                          15.14.0
verify_tree.py                                        guard 6
```

## Verify

```bash
python3 simulate_role_flow.py   # 7 guards, exit 1 on failure
python3 verify_tree.py          # full tree, now 6 sections
```

Both pass on this tree.

## Optional

Add a Workspace link so managers reach it without typing the URL —
Workspace **AlphaX POS Hub**, link type **URL**, label `Role Flow`,
url `/pos_role_flow`. Not shipped as a fixture, since the workspace
fixture is filtered by name and a link edit would need a re-export.
