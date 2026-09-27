# AlphaX POS Suite v15.7.0 — Feature Release: The Complete Register

First feature release after the register reached production. Everything
below was verified in the full jsdom boot simulation before packaging.

## Fixed

- **Items not adding to cart** (and dialog Cancel/close buttons dead):
  ONE loader bug — the SFC transform assigned the raw emits ARRAY to
  `const emit = defineEmits(...)`, so every script-level `emit()` threw
  "emit is not a function" across 18 components. The transform now
  yields the live ctx emit/props via the comma operator; verified by a
  DOM-level click producing a cart line.
- **Sidebar "AlphaX POS" → 404**: workspace name ("AlphaX POS Hub")
  and title ("AlphaX POS") slugged to different routes; the sidebar
  links by title, the router resolves by name. Workspace renamed to
  match its title (patch + fixture); /app/alphax-pos now works, and
  every hub reference in code/styling follows.
- **Every dialog now closes**: AppModal renders the × header always,
  closes on Esc and backdrop click — app-wide.

## New

- **Order types** — Dine In / Takeaway / Delivery / Staff / Credit as
  a touch-friendly segmented bar on the cart:
  - *Credit*: requires a named customer; posts a regular outstanding
    Sales Invoice (is_pos=0, no payments) on the customer's account.
  - *Delivery*: pick from the new **AlphaX Delivery Platform** master
    (HungerStation, Keeta, Jahez, Jeeny, Noon Food, Amazon, ToYou,
    Mrsool seeded); posts the full amount against the platform's Mode
    of Payment and stamps the invoice with platform + type.
  - Custom fields `alphax_order_type` / `alphax_delivery_platform`
    added to Sales Invoice (idempotent seed).
- **AlphaX Delivery Reconciliation** (Script Report): per-invoice
  gross, platform commission %, commission amount, expected net
  payout, and outstanding — filter by period/platform/company; match a
  platform's settlement statement line-by-line and clear it with a
  Payment Entry.
- **Item browsing**: category tabs, card/list view toggle, item
  images (with initials placeholder), preferences persisted per
  terminal.
- **Themes**: Emerald / Ocean / Sand / Dark, one tap in the Config
  panel's new Appearance section, applied live via CSS variables.
- **Touch-first pass**: 44px+ minimum targets on buttons/inputs,
  larger item cards, grouped sidebar (Sale / Order / System).

## Removed

- The raw domain-switcher chips (Restaurant / domains.Bakery) from the
  sidebar — cashier-facing confusion; the active domain remains
  visible in the Config panel.

## Verification

jsdom simulation: register mounts, DOM click adds to cart, credit
guard enforced, credit invoice shape correct (is_pos=0, 0 payments),
delivery invoice posts full amount to the platform MOP, theme applies
to the DOM. Payload regenerated (59 files); schema audit clean.
