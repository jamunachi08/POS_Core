# AlphaX POS Suite v15.7.3 — Shift Controls v2, View Fixes, 8 Themes

## Shift In / Shift Close (two interlocked buttons)

- The single shift chip is now TWO explicit sidebar buttons: **Shift
  In** (disabled while a shift is open) and **Shift Close** (disabled
  until one is) — states verified in the DOM simulation both ways.
- **Supervisor override**: managers/supervisors see an "open on behalf
  of (cashier user)" field — the shift's OWNER becomes that cashier
  while the audit trail records who performed the action. Closing
  another cashier's shift prompts a manager PIN on the client and is
  role-enforced on the server. Guards unit-tested: cashier on-behalf
  denied, supervisor allowed with correct ownership; foreign close
  denied for cashiers, allowed for managers.

## Fixed

- **View toggle buttons clipped/unlabelled** (screenshot report): the
  Cards / List / Images controls moved into the category bar's right
  side as labelled pill buttons that render on every font stack.
- Order-type bar (Dine In / Takeaway / Delivery / Staff / Credit)
  re-verified present in the rendered DOM (5 buttons) — if it was
  absent on the last deploy that was stale-asset residue from the
  failed v15.7.1 migrate; this release re-busts caches.

## Appearance

- **Four new themes**: Graphite (dark blue-steel), Rose, Violet, and
  Gold (dark luxe) — 8 total, one tap in Config → Appearance.
- **Modernization pass**: layered shadows, item-card hover lift,
  gradient Pay button with accent glow, pill categories, rounded-18
  modals — all token-driven so every theme inherits it.

## Verification

DOM interlock both states, on-behalf server guards, full shift math
regression (expected 570 / variance −5), order-type + credit +
delivery invoice shapes, add-to-cart click — all green.
