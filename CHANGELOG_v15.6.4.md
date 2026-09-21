# AlphaX POS Suite v15.6.4 — The Register Actually Boots

## Context

v15.6.3's layout fix got `/assets` serving for the first time — which
meant the Vue cashier's own code finally executed in production, and
immediately hit `Cannot destructure 'usePOSStore' of
'window.AlphaXStores'`. Rather than fix one error per deploy, this
release was validated with a full offline boot simulation (jsdom +
the exact pinned Vue/Pinia/vue-i18n bundles + the real sfc-loader and
main.js + a stubbed pos_boot), which reproduced the production error
and then caught every subsequent one in a single session. Verdict:
the Vue register had never successfully booted anywhere — four latent
bugs stood between it and first paint.

## Fixed (all found and verified by the simulation)

1. **Boot phase order** (`main.js`): composables loaded before stores,
   but `useMoney.js` destructures `window.AlphaXStores` at module
   scope. Stores now load first (they only depend on the api phase).
   — this was the error on screen.
2. **`useBarcodeScanner` never registered** (`main.js`): CashierView
   imports it, but it was missing from the composables load list —
   the identical destructure crash, one phase later.
3. **api phase order** (`main.js`): `client.js` loaded before
   `mock.js`, which it imports — every API call died with
   `Cannot read properties of undefined (reading 'isMockMode')`.
   Order is now mock → bridge → queueDB → client.
4. **SFC loader ASI hazard** (`sfc-loader.js`): the transform rewrote
   `defineEmits([...])` into a line starting with `(`, which ASI glued
   onto the preceding semicolon-free `computed(...)` as a call —
   "computed(...) is not a function" in SidebarPanel. The rewrite is
   now position-aware: semicolon-guarded in statement position, plain
   in expression position.
5. **SFC loader props harvesting** (`sfc-loader.js`): the
   `defineProps` extractor used a lazy regex that truncated at the
   first `)` — any props literal with a function default
   (`default: () => []`, as in ModifierPicker) failed to compile.
   Replaced with a string-aware balanced-delimiter scanner.
6. **Menu robustness** (`stores/pos.js`): `listItems()` result is now
   Array-checked; a truthy non-array (Frappe error dict) previously
   crashed MenuPanel's render loop.

## Verification

Simulated boot result: 28/28 SFCs compiled, pos_boot consumed,
CashierView mounted, add-to-cart produced a correct line, the
settings policy block reached the store, and return mode toggled with
a reason. The simulation lives at the packaging level and can be
rerun before any future release.
