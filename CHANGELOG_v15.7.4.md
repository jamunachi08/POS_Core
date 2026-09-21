# AlphaX POS Suite v15.7.4 — Layout Repair + Payment Fix

## Payment now completes (root cause found)

The tender dialog rendered "No payment methods configured on this
profile" whenever the terminal had no POS Profile attached — zero
tender buttons, Complete sale permanently disabled, payment
impossible. Fixed at both ends:

- **Server** (`boot/api.py`): if the profile supplies no methods,
  pos_boot falls back to every enabled Mode of Payment (cash first,
  marked default). A register can now ALWAYS tender.
- **Client** (`PaymentDialog`): if a stale boot payload still carries
  an empty list, the dialog synthesizes a Cash method from settings.

Verified by a full DOM click-through in the simulation: Pay → select
Cash → quick-tender → Add → Complete sale → Sales Invoice posted with
the correct payment row → cart cleared.

## Layout repaired (v15.7.3 regression — my defect)

The v15.7.3 category-bar patch left its wrapper div unclosed, nesting
the entire item grid inside a flex ROW: grid shoved right, categories
floating mid-screen, controls hidden. Structure rewritten and correct;
the release gate now includes a per-template div-balance check
(section 3.6) so an unbalanced Vue template can never pass again.

## Screen real estate (as requested)

- The desk page-title band ("AlphaX POS" heading) is removed on the
  cashier route — pure dead space on a register.
- The register previously rendered from y=0 UNDER the desk navbar,
  hiding the search row and pushing Pay below the fold. It now fills
  exactly the area below the navbar; cart lines scroll internally and
  the totals + Pay block is permanently pinned and visible.

## Verification

Full regression: boot, add-to-cart click, payment click-through,
order types (credit/delivery invoice shapes), shift lifecycle
(expected 570 / variance −5), two-button interlock, 8 themes.
Template balance, schema audit, payload freshness: all green.
