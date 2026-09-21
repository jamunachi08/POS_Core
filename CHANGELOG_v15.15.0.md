# AlphaX POS Suite — v15.15.0

**Interactive process flow board**, built to the same pattern as the boards
in AlphaX Lab, NeoAqua, PieceWork and CIT: the whole cycle in system
sequence, every card a real document, every card filtered by what the
viewer can actually reach.

Desk route: **`/app/alphax-pos-flow`**, plus a `Process Flow` shortcut on
the AlphaX POS Hub workspace.

## The board

23 stages across 8 lanes, 75 document nodes.

| Lane | Stages | Driven by |
|---|---|---|
| Setup | Company & Outlet, Terminals & Hardware, Catalogue & Pricing, Menus/Combos/Offers, People & Access | Administrator |
| Open | Shift Open, Floor & Order Type | Cashier / Supervisor |
| Sell | Build the Order, Kitchen Routing, Payment, Post & Fiscalise | Cashier |
| Serve | Kitchen Preparation, Guest Ordering | Kitchen / Customer |
| Control | Authorisation, Returns & Store Credit, Cash Movement | Manager |
| Close | Shift Close, Day Close, Reporting & Notification | Supervisor / Manager |
| Finance | Revenue Posting, Liability & Reconciliation | Accounts |
| Governance | Audit & Logs, Flow Definition | Administrator |

Nodes deliberately mix AlphaX POS documents with the stock ERPNext ones the
process depends on — Company, Item, Item Price, Item Tax Template,
Warehouse, Customer, Mode of Payment, Sales Invoice, Payment Entry, Journal
Entry, Period Closing Voucher, User, Role, Activity Log. `node_summary()`
returns the split. That mix is the plainest answer to "what does the POS
actually post into?", and it is the thing Stocky and UltimatePOS cannot
show.

## Access, and why role rows are not the gate

`pos/flow_api.get_flow()` runs two filters in order:

1. **Role rows** on the node — a node may name the roles allowed to see it.
2. **`frappe.has_permission(doctype, "read")`** — the same check the desk
   itself uses. `"create"` separately decides whether the card offers a
   **New** button.

Step 2 is the one that cannot be got wrong by editing data. Even if an
administrator lists every role on every node, a cashier still cannot reach
a Journal Entry card. **Role rows narrow the board; they never widen it.**

Stages with no surviving nodes are dropped rather than rendered empty, so a
cashier gets a short board, not a mostly-blank one.

Measured by `simulate_process_flow.py` against the real seeder tables:

| Role | Stages | Nodes |
|---|---|---|
| `AlphaX POS Cashier` | 6 | 9 |
| `AlphaX POS Kitchen` | 2 | 4 |
| `AlphaX POS Supervisor` | 16 | 35 |
| `AlphaX POS Manager` | 20 | 45 |
| `Accounts Manager` | 2 | 4 |
| `System Manager` | 23 | 75 |
| no AlphaX role | 0 | 0 |

A node whose target DocType is not installed on the site is dropped at read
time rather than rendered as a dead card, so a partial install still gives
a working board.

## New

```
doctype/alphax_pos_process_flow/     flow header + ordered stages
doctype/alphax_pos_process_stage/    child: stage, lane, actor, sequence, colour
doctype/alphax_pos_process_node/     one card; target, view, filters, roles
doctype/alphax_pos_node_role/        child: role restriction
pos/flow_api.py                      get_flow(), node_summary()
seed/process_flow.py                 23 stages, 75 nodes, idempotent
page/alphax_pos_flow/                desk board (swimlanes, counts, actions)
simulate_process_flow.py             7 access guards
```

Each card shows a live document count, an **Open** action that carries the
node's filters into the list view, and a **New** action only where the user
holds create. Bilingual EN/AR toggle, counts toggle, refresh.

## Changed

- `hooks.py` — seeder wired into `after_migrate`, so new stages and nodes
  reach existing sites with no manual step.
- `install.py` — seeder runs last in `after_install`, wrapped so a failure
  logs rather than aborting the install.
- `fixtures/workspace.json` — `Process Flow` shortcut after `② Open Cashier`.
- `verify_tree.py` — seventh guard section: every node targets a known
  DocType, every node's stage exists, no DocType sits in both the app and
  STD sets, and no page route collides with a DocType slug. That last one
  is why the route is `alphax-pos-flow` and not `alphax-pos-process-flow`,
  which would have resolved to the DocType list view instead of the board.
- Version 15.14.0 → 15.15.0.

## Editing the flow

`seed/process_flow.py` is the source of truth. `STAGES` and `NODES` are two
plain tables; re-running the seeder updates labels, sequences and roles in
place and never duplicates a node. A node an administrator disabled by hand
stays disabled — the seeder does not re-enable it.

Administrators can also edit `AlphaX POS Process Flow` and
`AlphaX POS Process Node` directly in the desk. Those edits survive until
the next migrate re-asserts the seeded values for seeded nodes; nodes added
by hand are never touched.

## Verify

```bash
python3 simulate_process_flow.py   # 7 access guards
python3 simulate_role_flow.py      # 7 role-flow guards
python3 verify_tree.py             # full tree, 7 sections
```

All pass on this tree.

## Relationship to `/pos_role_flow`

Two different jobs, both kept:

- **`/pos_role_flow`** (v15.14.0) — training view. Prose, what each role
  does and where it escalates, printable, bilingual. Answers "how do I do
  my job?"
- **`/app/alphax-pos-flow`** (this release) — operational navigation.
  Live counts, real documents, Open and New. Answers "where do I go next?"

The board carries a node linking to the role flow in stage H2, so one
reaches the other.
