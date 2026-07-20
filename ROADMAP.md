# AlphaX POS — Top-5 Execution Roadmap

Strategy summary (full document: `AlphaX_POS_Top5_Strategy.docx`):
reach floor parity with Foodics / Syrve / NCR Aloha while pressing the
five moats they cannot copy — one-system ERP fusion, ZATCA/PDPL
compliance-native, data sovereignty (local AI), white-label channel,
no per-branch SaaS tax.

Every item lists the code it builds on. Definition of done for ANY
item: boot simulation passes, schema audit clean, `verify_tree.py`
green, payload regenerated, EN+AR locales, changelog entry.

---

## Phase 1 — Own the floor (operational parity)

- [ ] **Shift & cash management UI**
      Backend: `pos/shift.py`, `reporting/close_reports.py` (fixed v15.6.6).
      Build: shift bar in sidebar (open/close state), blind cash
      declaration dialog (denomination count), over/short posting,
      X report (mid-shift) and Z report (close) print formats.
- [ ] **KDS v2**
      Base: `page/alphax_kds/` (249-line v1).
      Build: station routing (Item Group → station map in settings),
      bump/recall, prep timers with colour ageing, expo view,
      realtime via `frappe.realtime` from Sales Invoice / POS Order.
- [ ] **Customer-facing display (CFD)**
      Build: `www/alphax-cfd` second-screen page paired to a terminal
      (pairing code), live cart via realtime, ZATCA QR on completion,
      branded idle loop from AlphaX POS Theme.
- [ ] **Combos & promotions engine**
      New: `AlphaX Promotion` doctype (rule types: combo price, BOGO,
      time-window %, threshold amount), evaluated in `stores/pos.js`
      cart recompute, re-validated server-side in `pos/processing.py`.
- [ ] **Receipt designer**
      Base: print formats + `_fonts/saudiriyalsymbol.ttf`.
      Build: per-outlet template selection in AlphaX POS Settings,
      80mm/58mm Arabic thermal layouts, ZATCA QR block.
- [ ] **Gift cards / stored value**
      Base: AlphaX Wallet app (separate repo — integrate, don't rebuild).
      Build: sell/redeem card at the till as a payment mode.

## Phase 2 — Own the order (revenue channels)

- [ ] **QR dine-in self-ordering** — finish `www/table_qr` into
      guest ordering → KDS; cashier tenders. Reuses menu API + boot.
- [ ] **Online ordering storefront** — branded `www` store per outlet,
      pickup/delivery slots, gateway prepay, orders land as held carts.
- [ ] **Aggregator integrations** — menu push + order pull for
      HungerStation / Jahez / Keeta on top of `AlphaX Delivery
      Platform` master + reconciliation report (shipped v15.7.0).
      Pattern: `integrations/<platform>/api.py`, long-queue jobs.
- [ ] **Reservations & waitlist** — bookings on the floor plan
      (`floor/api.py`), deposits to wallet.

## Phase 3 — Own the margin (intelligence)

- [ ] **Recipe costing & menu engineering** — ERPNext BOM per menu
      item; theoretical vs actual cost; stars/dogs matrix as a
      Neotec Insight dataset.
- [ ] **Wastage & outlet stock counts** — guided count UI on the
      register; variance posts Stock Reconciliation automatically.
- [ ] **Forecast & prep planning** — sales forecast → prep lists;
      NISA/Ollama local inference (data never leaves KSA).
- [ ] **Franchise console** — multi-company royalty + menu governance
      over ERPNext multi-company.

## Phase 4 — Own the platform

- [ ] **Payments** — mada-certified acquirer flows on the
      `integrations/card_reader` (Geidea) adapter pattern.
- [ ] **Public API + marketplace** — documented REST surface,
      partner app registry, reseller developer program.
- [ ] **Hardware program** — certified terminal/printer/CDS bundles.

---

## Standing rules

1. Ship every two weeks. No release without the three gates.
2. Each phase exits with one lighthouse customer live in Riyadh.
3. Any feature request that neither closes a matrix gap nor deepens a
   moat waits — this file is the triage authority.
