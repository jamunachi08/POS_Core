# AlphaX POS Suite — v15.19.0

Dietary and allergen handling, end to end: item master → till filters →
kitchen ticket → the pass. This is the F&B item specified as next in
v15.18.0.

All original AlphaX work. No third-party code, schema, markup or assets.

## New — diets and allergens

Two new masters and four Item fields. The distinction between them is the
whole design, and it is enforced everywhere:

| | Diet | Allergen |
|---|---|---|
| What it is | what a guest **chooses** — vegan, halal, gluten free | what a dish **contains** — peanuts, milk, gluten |
| Cost of missing it | a lost sale | a guest in hospital |
| At the till | a filter chip the cashier switches on | always drawn on the card, never filterable |
| On the ticket | not printed | printed as a short code, always |

Seeded on install and migrate: 9 diets and the **14 declarable allergens**
(the EU/UK set that GCC food-service practice follows), each with an
Arabic label, a 3-character ticket code and a colour.

### Item

Collapsible **Food & Beverage** section: `alphax_food_type`
(Veg / Non-Veg / Egg), `alphax_dietary_tags` (a multi-select of diets and
allergens) and `alphax_spice_level`.

### At the till

Diet chips sit beside the category row. **They combine with AND, not OR** —
a guest who is vegan *and* gluten free must only see dishes that satisfy
both. An OR would hand them a dish that satisfies neither, which is the
kind of bug that reads as fine in testing and fails in front of a guest.

Every card carries a food-type dot (green / red / amber) and, where the
dish has them, allergen codes. The codes are not filterable: "contains
nuts" is the wrong question, because a guest avoiding nuts wants a dish the
kitchen has signed off as **Nut Free**, not one whose warning label nobody
remembered to tick.

### On the pass

- The guest's own words appear as a **red banner above the lines**, not
  beside them. An allergy warning the pass can scroll past is a warning
  that will eventually be missed.
- Each line carries its food-type dot and allergen codes.
- Allergens are **snapshotted onto the ticket when it is raised**, not
  looked up live. An item edited at 21:00 must not silently rewrite a
  ticket that has been on the rail since 20:00.
- The guest note comes from the order if the cashier captured one,
  otherwise from the seated reservation. The later statement wins, because
  it is the one the cashier actually heard at the table.

## Layout ideas adopted

From the UI references reviewed: dietary toggles beside the search row,
per-card dietary markers, and short allergen chips on the item card. Taken
as shapes only and drawn in the existing AlphaX cashier styling — no
imported markup, classes or assets.

## Verification

`simulate_dietary.py` — 18 assertions, including:

- Vegan **AND** Gluten Free returns only the dish satisfying both, where an
  OR would wrongly include two more;
- a combination nothing satisfies returns nothing, not everything;
- no diet ever lands in the allergen list, and no diet is ever printed as a
  ticket allergen — a Halal, gluten-free dish must not print "HAL" where a
  cook looks for allergens;
- a dish with no allergens carries an empty list, not a null;
- ticket codes stay short enough for an 80mm roll.

`verify_tree.py` caught the embedded SPA payload going stale during this
work and refused the push until `build_spa_payload.py` was re-run. That is
the guard doing exactly its job; the payload is rebuilt (70 files).

## Files

```
doctype/alphax_pos_dietary_tag/          NEW  the master
doctype/alphax_pos_item_dietary_tag/     NEW  child link on Item
seed/dietary_tags.py                     NEW  9 diets + 14 allergens, idempotent
data/custom_fields_seed.json             Item: food type, tags, spice level
catalog/api.py                           diets/allergens on the menu payload; dietary_filters()
pos/kot_api.py                           allergen snapshot; guest note; board payload
doctype/alphax_pos_kds_ticket/           guest_allergy_note, ticket_allergens
doctype/alphax_pos_kds_ticket_item/      food_type, allergens
page/alphax_kds/                         allergy banner, food dots, allergen chips
components/MenuPanel.vue (both copies)   diet chips, card markers
stores/pos.js (both copies)              AND filtering, chip state
seed/process_flow.py                     Diets & Allergens node in A4
spa_payload.py                           rebuilt
simulate_dietary.py                      NEW
```

Seeded tags and Item fields arrive on migrate. No data migration.

## Next — v15.20.0

**Course firing** — fire starters, hold mains. Needs a course on the order
line, a fire action per course on the KDS, and fired timestamps so hold
times can be reported rather than argued about. Then **focus mode** and the
**complimentary bill**.
