# AlphaX POS v3 Cashier — Architecture & Build Plan

**Status:** Phase 1 — Planning (no production code yet)
**Date:** May 2026
**Author:** AlphaX team
**Target version:** v15.6.0 (when complete)

---

## 1. Goals

Build a modern Vue 3 cashier at `/app/alphax-pos-v3` that:

- Looks and feels like a contemporary commercial POS (Square, Toast, Lightspeed-quality)
- Uses the same Frappe backend AlphaX already has (no backend rewrites)
- Coexists with Classic during transition; new customers default to v3
- Reaches feature parity with Classic, then surpasses it on UX

Out of scope for v3 (deferred to later versions):
- Offline-first cache and sync conflict resolution (→ v15.7)
- Customer-facing display screen (→ v15.8)
- Native mobile app (→ v16+)
- Inventory, HR, accounting screens (live in Frappe Desk; not part of v3)

---

## 2. What we learned from examining v2

The existing Vue cashier at `/app/alphax-pos-v2` is more substantial than its Beta status suggests. ~6,600 lines across 40 files. It already has:

- **Three-column responsive layout** (Sidebar | Menu | Cart)
- **4 Pinia stores** — pos (572 lines), hardware (205), sync (147), kiosk (95)
- **25 Vue SFC components** covering payments, modifiers, prescriptions, table picker, hold orders, hardware settings, kiosk mode, locale switching
- **vue-i18n integration** with English + Arabic locales
- **Runtime SFC loader** (560 lines) — compiles `.vue` files in the browser at load time, no Vite build step
- **Mock API mode** for offline development
- **Queue-based offline sync** via IndexedDB (`api/queueDB.js`, 137 lines)
- **Bridge daemon integration** for hardware (`api/bridge.js`)
- **Composables** for haptics, modifiers, long-press, money formatting

### Why we're starting v3 fresh anyway

You chose this. My honest read on the trade-offs:

**What v3-fresh gives us:**
- Clean architecture with hindsight from v2's experiences
- Tailwind + Headless UI from day one (v2 uses custom CSS)
- No need to untangle v2's specific design choices that may not match the new vision
- Freedom to skip features that turned out to be over-engineering

**What we lose by going fresh:**
- ~6,600 lines of working code (some of it polished)
- The 25 components, many of which are decent
- vue-i18n setup that already does Arabic
- Mock mode for testing without a backend

### What we'll port from v2 — not as code, as patterns

Even though we start fresh, v2 contains **proven patterns**. We will:

| Pattern from v2 | How v3 uses it |
|---|---|
| Three-column layout (Sidebar / Menu / Cart) | Same — works for desktop and tablet |
| Pinia store split (pos/hardware/sync/kiosk) | Same | 
| Runtime SFC loader to avoid Vite | Same — Frappe Cloud asset constraints unchanged |
| Mock API mode for offline dev | Same — extremely useful for design iteration |
| BootScreen for initial load state | Same |
| Modifiers, prescription capture, table picker components | Re-imagine with Headless UI primitives |
| vue-i18n with EN+AR | Same setup, fresh translations |
| Domain-pack-driven feature flags | Same — `pos.activeFeatures` style |
| Queue-based offline sync | Stub for v3 (online-only); full implementation in v15.7 |

### What we'll explicitly NOT bring from v2

- Custom CSS approach → replaced with Tailwind utility classes
- 560-line sfc-loader → reuse v2's loader as-is (it works; no reason to rewrite)
- Some specific component implementations (cart line actions, hardware settings panel) → rewrite for cleaner Headless UI patterns

---

## 3. Folder structure

```
alphax_pos_suite/alphax_pos_suite/
├── page/alphax_pos_v3/                    <-- new
│   ├── __init__.py
│   ├── alphax_pos_v3.json                 (Frappe Page registration)
│   └── alphax_pos_v3.js                   (~150 lines — loads SPA into Frappe page)
│
└── public/dist/vendor/cashier_v3/         <-- new (parallel to cashier/)
    ├── sfc-loader.js                      (copy v2's; unchanged)
    ├── tailwind.css                       (pre-compiled, ~30-50 KB)
    ├── sfc/
    │   ├── main.js                        (mount + plugin wiring)
    │   ├── App.vue                        (root: boot vs cashier)
    │   ├── views/
    │   │   ├── CashierView.vue           (main 3-column layout)
    │   │   ├── ShiftOpenView.vue         (shift open flow)
    │   │   ├── ShiftCloseView.vue        (shift close flow)
    │   │   └── SettingsView.vue          (cashier-side preferences)
    │   ├── components/
    │   │   ├── layout/
    │   │   │   ├── TopBar.vue            (station banner, sync pill, gear)
    │   │   │   ├── Sidebar.vue           (mode switcher: Sale/Return/Hold)
    │   │   │   └── BottomBar.vue         (keyboard shortcuts hint)
    │   │   ├── product/
    │   │   │   ├── ProductGrid.vue       (tile picker)
    │   │   │   ├── ProductTile.vue       (single product card)
    │   │   │   ├── ProductSearch.vue     (search + barcode field)
    │   │   │   └── CategoryTabs.vue      (Item Group nav)
    │   │   ├── cart/
    │   │   │   ├── CartPanel.vue         (right column)
    │   │   │   ├── CartLine.vue          (single line)
    │   │   │   ├── CartSummary.vue       (subtotal/tax/total)
    │   │   │   └── ModeBanner.vue        (Sale / Return / etc.)
    │   │   ├── payment/
    │   │   │   ├── PaymentSheet.vue      (bottom sheet: pick method)
    │   │   │   ├── QuickCashButtons.vue  (5/10/20/50/100/500 SAR)
    │   │   │   ├── CardPaymentModal.vue  (calls v15.5.16 card adapter)
    │   │   │   └── PaymentRow.vue        (one applied payment)
    │   │   ├── dialogs/
    │   │   │   ├── CustomerPicker.vue
    │   │   │   ├── HeldOrders.vue
    │   │   │   ├── ManagerPINDialog.vue  (when an action needs approval)
    │   │   │   └── ConfirmDialog.vue
    │   │   ├── shift/
    │   │   │   ├── OpenShiftForm.vue
    │   │   │   ├── CloseShiftForm.vue
    │   │   │   └── CashCountInput.vue
    │   │   └── ui/                       (Headless UI wrappers)
    │   │       ├── Button.vue
    │   │       ├── Input.vue
    │   │       ├── Modal.vue
    │   │       ├── Toast.vue
    │   │       └── Spinner.vue
    │   ├── stores/
    │   │   ├── pos.js                    (cart, customer, mode, profile)
    │   │   ├── catalog.js                (items, item groups, prices)
    │   │   ├── shift.js                  (active shift state)
    │   │   └── ui.js                     (theme, locale, modals)
    │   ├── api/
    │   │   ├── client.js                 (Frappe call wrapper)
    │   │   └── mock.js                   (fixture-based dev mode)
    │   ├── composables/
    │   │   ├── useMoney.js               (formatting, SAR symbol)
    │   │   ├── useShortcuts.js           (F-key bindings)
    │   │   └── useToast.js               (toast manager)
    │   ├── locales/
    │   │   ├── en.js
    │   │   ├── ar.js
    │   │   └── index.js
    │   └── styles/
    │       └── theme.css                 (CSS custom properties for mauve)
```

**Why parallel folders, not extending v2's:**
You picked "start fresh." Parallel folders make it impossible to accidentally inherit v2 quirks. v2 stays exactly as it is. When v3 is stable in production, we can choose to delete v2 in a later release.

---

## 4. Component count vs. v2

| Area | v2 | v3 plan |
|---|---|---|
| Layout components | 6 (Sidebar, MenuPanel, etc.) | 5 (TopBar, Sidebar, BottomBar + 2 layout wrappers) |
| Product/menu | mostly in MenuPanel.vue (1 large file) | 4 components (Grid, Tile, Search, Tabs) |
| Cart | 3 (CartPanel, CartLineActions, Summary) | 4 (Panel, Line, Summary, ModeBanner) |
| Payment | 4 (PaymentDialog, SplitBill, QuickCash, etc.) | 4 (Sheet, QuickCash, Card, Row) |
| Dialogs | 9 (Customer, Held, Modifier, Loyalty, etc.) | 4 in v3 + we'll defer prescription/modifier/table to v15.6.1 |
| Shift | none | 3 (Open, Close, CashCount) |
| Settings | 1 (HardwareSettings) | 1 (SettingsView) |
| UI primitives | none — used Frappe's | 5 (Button, Input, Modal, Toast, Spinner via Headless UI) |
| **Total** | **~25** | **~30** |

v3 has slightly more files because we explicitly extract small reusable UI primitives. Tradeoff: more files but less duplication.

---

## 5. Tailwind strategy (the build pipeline question)

**The problem:** Tailwind normally requires `tailwindcss` CLI to compile `.css` from utility classes. We can't run that on Frappe Cloud at deploy time (the same constraint that drove our vendor bundles strategy).

**Our solution:** Pre-compile Tailwind on Claude's side (or a developer's laptop) into a single CSS file, commit it to the repo at:

```
public/dist/vendor/cashier_v3/tailwind.css
```

Workflow:
1. Component author writes `<button class="px-4 py-2 bg-mauve-500 hover:bg-mauve-600">`
2. We maintain a `tailwind.config.js` and a small build script
3. On significant Tailwind-class changes, we run the compile script
4. Output is committed; Frappe Cloud serves the static CSS

**Implications:**
- Adding a new utility class requires a recompile (manual or via a Claude turn)
- We commit ~30-50 KB of pre-compiled CSS (acceptable)
- No npm install during deploy (matches our existing constraint)

This is the same trade-off we made for vue.global.prod.js, pinia, vue-i18n. The pattern works.

---

## 6. State model (Pinia stores)

### `pos.js` — the active sale
- `mode`: 'sale' | 'return' | 'hold-resume'
- `cart`: array of line items (item_code, qty, rate, modifiers, line_uuid)
- `customer`: linked customer or null
- `payments`: array of applied payments
- `terminal`: current bound terminal
- `profile`: resolved POS Profile (from v15.5.15 logic)
- `outlet`, `branch`, `domainPack`: from `pos_boot` response
- Actions: `addItem`, `removeItem`, `setQty`, `addPayment`, `holdSale`, `resumeSale`, `submitSale`, `startReturn`, `cancelSale`

### `catalog.js` — items, groups, prices
- `items`: cached array (loaded on boot)
- `itemGroups`: nav tabs
- `activeCategory`: filter
- `searchQuery`: text or scanned code
- Computed: `filteredItems` (by category + search)
- Actions: `loadCatalog`, `refresh`, `lookupBarcode`

### `shift.js` — current shift state
- `shift`: active shift doc or null
- `cashFloat`: opening cash
- Actions: `openShift`, `closeShift`, `cashDrop`, `cashLift`

### `ui.js` — theme, locale, modal stack
- `theme`: 'light' | 'dark'  (dark mode is v15.6.1; light only for v15.6.0)
- `locale`: 'en' | 'ar'
- `modalStack`: which modals are open (for Esc-to-close)
- `toasts`: queue of pending toast messages

---

## 7. The visual design

### Layout (desktop, 1280×800 minimum)

```
┌───────────────────────────────────────────────────────────────────────┐
│ [AlphaX]  Riyadh Mall › Coffee Shop › Terminal A07         [⚙] [👤]   │  Top bar (56px)
├──────────────────────────────────────────────────────────────────────┤
│      │                                              │                │
│  📋  │  [Search items or scan barcode...]           │  CURRENT SALE  │
│      │                                              │                │
│  💰  │  Hot Drinks  Cold Drinks  Pastry  ...        │  (1) Latte     │
│      │                                              │      x1  12.00 │
│  ↩   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │                │
│      │  │Latte │ │Mocha │ │Cap.  │ │ Tea  │         │  (2) Croissant │
│  ⏸   │  │12.00 │ │14.00 │ │11.00 │ │ 8.00 │         │      x1  10.00 │
│      │  └──────┘ └──────┘ └──────┘ └──────┘         │                │
│      │                                              │  ─────────────  │
│  ⋮   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │  Subtotal      │
│      │  │Crois.│ │Donut │ │Muffin│ │Cookie│         │       22.00    │
│      │  │10.00 │ │ 7.00 │ │ 8.00 │ │ 5.00 │         │  VAT 15%       │
│      │  └──────┘ └──────┘ └──────┘ └──────┘         │        3.30    │
│      │                                              │  TOTAL ﷼25.30  │
│      │                                              │                │
│      │                                              │  [Pay & Submit]│
│      │                                              │                │
├──────┴──────────────────────────────────────────────┴────────────────┤
│ F2 Scan   F3 Customer   F4 Hold   F8 Pay   F9 Return    Esc Cancel   │  Bottom bar
└──────────────────────────────────────────────────────────────────────┘
```

### Sidebar icons (left, 56px wide)
- 📋 Sale mode (default)
- 💰 Pay
- ↩ Return mode
- ⏸ Holds
- ⋮ More (settings, shift, etc.)

### Mode banner
When in **Return mode**, the top bar turns **orange** with the text "RETURN MODE — Original invoice: ABC-2026-00123". When **Sale mode**, normal mauve. Clear visual indicator.

### Quick-cash buttons (in payment sheet)
Below the cash amount field: `[5] [10] [20] [50] [100] [200] [500]` — one tap to populate the amount.

### Saudi Riyal symbol
The total line shows `﷼25.30` using the font we shipped in v15.5.16.

### Color palette
- Primary: mauve `#714B67` (matches AlphaX brand)
- Surface: white `#FFFFFF`
- Background: warm grey `#FAF7F9`
- Border: `#EAE5E9`
- Sale mode header: mauve
- Return mode header: amber-700 `#B45309`
- Approve: green-600 `#16A34A`
- Decline: red-600 `#DC2626`

---

## 8. Backend dependencies — what v3 needs from the backend

All backend pieces are already shipped or shipping in v15.5.x:

- `pos_boot(terminal)` → v15.5.7+ (existing)
- `resolve_session_pos_profile(terminal)` → v15.5.15 (existing)
- `run_setup_wizard(payload)` → v15.5.15 (existing)
- `request_card_payment(...)` → v15.5.16 (existing)
- `get_card_payment_status(...)` → v15.5.16 (existing)
- Manager PIN endpoints → v15.5.13 (existing)
- Shift open/close endpoints → **need to verify these exist**
- Print profile lookup → v15.5.16 (existing)

**Action item:** in Phase 2, verify shift endpoints exist and are sufficient. If not, add them to the backend in parallel with the frontend build.

---

## 9. Migration plan

### When v3 ships (v15.6.0):

1. New customers go through the existing v15.5.15 setup wizard.
2. The wizard's final step gets a flag: "Try the new cashier (v3)" — checked by default for fresh installs.
3. Existing v15.5.15 customers see Classic by default.
4. The workspace gets a "Try v3 Cashier (Beta)" shortcut next to "Open Cashier" for opt-in.
5. Both `/app/alphax-pos-classic` and `/app/alphax-pos-v3` remain functional.

### v15.6.x patch cycle:

Bug fixes for v3 + selective backports to Classic for critical issues only. We do NOT keep adding features to Classic — it's frozen.

### v15.7 or later (decision point):

When v3 has 3+ months of production use and feedback shows it's stable, we make v3 the default for all customers. Classic stays accessible but unadvertised. v2 may be deleted at this point.

---

## 10. Phase plan & calendar

| Phase | Deliverable | My estimate |
|---|---|---|
| **1. Plan (this doc)** | Architecture document + visual mockup | 1 session (today) |
| **2. Foundation** | Frappe Page, asset paths, Tailwind compile, SFC loader, mock API, dev workflow | 2-3 sessions |
| **3. Layout shell** | TopBar, Sidebar, BottomBar, theme, locale switching | 1-2 sessions |
| **4. Catalog** | ProductGrid, ProductTile, Search, CategoryTabs, catalog store | 2-3 sessions |
| **5. Cart** | CartPanel, CartLine, CartSummary, pos store basics | 2-3 sessions |
| **6. Payments** | PaymentSheet, QuickCashButtons, CardPaymentModal, payment flow | 2-3 sessions |
| **7. Returns** | Return mode banner, return flow, original-invoice lookup | 1-2 sessions |
| **8. Holds** | HeldOrders dialog, hold/resume actions | 1 session |
| **9. Shifts** | OpenShift, CloseShift, CashCount, shift store | 2-3 sessions |
| **10. Settings** | SettingsView, hardware test, locale, printer setup | 1-2 sessions |
| **11. Manager PIN** | ManagerPINDialog, integrate with v15.5.13 endpoints | 1 session |
| **12. Polish** | Toasts, keyboard shortcuts, mobile responsive, edge cases | 2-3 sessions |
| **13. Migration** | Wizard tweaks, workspace shortcut, opt-in flag | 1 session |
| **14. Docs** | Update 4 manuals with v3 sections | 2 sessions |
| **15. Final QA** | Test against neo15, fix what breaks | 2-3 sessions |

**Total: 24-37 sessions over 4-7 weeks.**

A "session" ≈ one of our conversation turns. Some phases are short (Phase 1, Phase 11). Some are heavy (Phase 4-6 — that's the core sale flow).

**Realistic ship date if we start now: late June to mid-July 2026.**

---

## 11. Risks I want you to know about

1. **My biggest risk:** I cannot test the runtime. Vue components compile and render only when actually loaded in a browser. I will write code that looks correct, validates syntactically, and may still fail at runtime in ways I can't predict. **Plan on every phase needing a real test on neo15 before moving to the next.**

2. **Tailwind class set drift.** If I use a class in a component that's not in the precompiled CSS, it silently doesn't apply. I'll need to be careful, or we accept a "recompile after every phase" step.

3. **Frappe Cloud asset path issues** (the same ones that bit us through v15.5.x). Likely first time I touch the cashier_v3 folder, something doesn't symlink correctly. We solved this for vendor; should be solvable here.

4. **Token budget across sessions.** A 25-session build means I'll need a transcript-friendly journal for context handoff between sessions. I'll create one at the end of Phase 1.

5. **Backend gaps.** If shift endpoints don't exist with the right shape, we'll need to add them mid-build, which delays Phase 9.

6. **Visual mismatch.** I can describe what v3 looks like in markdown and ASCII. The actual rendered Vue may look different from what you imagined. **Phase 2 will produce an HTML/CSS visual mockup you can click on** before we commit to the full Vue build. Cheapest moment to course-correct.

---

## 12. What I commit to

- **Honest progress updates.** When a phase hits a problem, I tell you, not paper over it.
- **No surprise features.** I won't decide mid-build that v3 needs dark mode or a customer display.
- **Stop and ask when uncertain.** If a decision needs your input, I'll surface it before coding around it.
- **Frequent test points.** End of each major phase, you should be able to test the new piece on neo15.
- **Keep Classic working.** I won't touch Classic during v3 development unless a real bug needs fixing.

---

## 13. What I need from you

Three things before I start Phase 2:

1. **Sign off on this plan.** Read it, push back on anything that's wrong.

2. **Visual references.** If you have favorite POS UIs you want v3 to feel like (screenshots, links to videos), share them. retail-suite's screenshots are one reference; if you have others (Square, Foodics, anything you've seen at a real shop), they help me make the right small decisions.

3. **Commitment to test cycles.** v3 will involve many "deploy to neo15, click around, tell me what's broken" rounds. If you can't run those quickly, the build will drag. Realistic test cycle: 1-2 days from each phase ship to your testing.

---

*Plan version 1.0 — May 14, 2026. Author: AlphaX team. Refer back to this document throughout the build to confirm we haven't drifted.*
