# AlphaX POS Suite — v15.15.1

Puts the process flow on the hub page at `/app/alphax-pos`, and repairs
what was already broken there.

## Added

- **`Process Flow` shortcut tile** on the AlphaX POS hub, after
  `② Open Cashier`.
- **`Process Flow` link** in the **Operations** card, under Modules.
- Both added to `build_workspace.py` LAYOUT as well as the generated
  fixture, so regenerating the workspace keeps them.

## Fixed — three pre-existing workspace faults

### 1. Three shortcuts were defined but never drawn

A workspace `content` block references a shortcut by its **label**. The
fixture defined six shortcuts but the content row named only four, and one
of those four (`Open Cashier`) no longer matched its shortcut, which had
been relabelled `② Open Cashier`.

Net effect on the live page: **`① Start Setup` and `② Open Cashier` were
not rendering at all**, and the content row was asking for a shortcut that
did not exist. The shortcut row is now rebuilt from the real shortcut list,
so all six draw.

### 2. Four Page links pointed at folder names, not page names

A workspace Page link must carry the Page document's `name`, which is
hyphenated. Four carried the underscored module-folder name instead and
were dead menu entries:

| Link | Was | Now |
|---|---|---|
| Floor Plan | `alphax_floor_designer` | `alphax-floor-designer` |
| Kitchen Display | `alphax_kds` | `alphax-kds` |
| Setup Wizard | `alphax_pos_setup` | `alphax-pos-setup` |
| Profitability Dashboard | `alphax_pos_profitability` | `alphax-pos-profitability` |

Fixed in both the fixture and `build_workspace.py`.

### 3. `verify_tree.py` gains an eighth guard section

Catches all three faults above before a push:

- every shortcut has a content block (defined but not drawn)
- every content block has a shortcut (drawn as nothing)
- content cards match Card Break rows
- every workspace Page link resolves to a real Page `name`

## Known divergence — read before running `build_workspace.py`

`fixtures/workspace.json` and `build_workspace.py` were **already out of
sync before this release**, and this change does not reconcile them. The
committed fixture carries `① Start Setup` and `Activity Log`; the
generator's `SHORTCUTS` list carries neither, and carries a `ZATCA Status`
tile the fixture does not have.

Running `python build_workspace.py` right now would therefore drop
`① Start Setup` and `Activity Log` and reintroduce `ZATCA Status`. The
Process Flow additions and the Page-link repairs are in both files, so
they survive either way — but reconcile the shortcut list first if you
intend to regenerate.

## Files

```
alphax_pos_suite/fixtures/workspace.json    shortcut row rebuilt, link added, 4 links repaired
build_workspace.py                          LAYOUT: flow shortcut + Operations link, links repaired
verify_tree.py                              guard section 8
alphax_pos_suite/__init__.py                15.15.1
```

## Deploy

Push and let Frappe Cloud migrate. Workspace fixtures reload on every
migrate, so the hub picks the changes up with no manual step.
