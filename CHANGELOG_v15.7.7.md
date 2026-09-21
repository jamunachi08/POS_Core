# AlphaX POS Suite v15.7.7 — Dynamic import 404s (customer display + offline queue)

## "Failed to fetch dynamically imported module: …/cashier/sync"

Field report (testneo.frappe.cloud). Two code paths in `stores/pos.js`
used native dynamic imports — `await import('./hardware')` and
`await import('./sync')`. The SFC loader rewrites *static* imports to
the preloaded registries, but dynamic `import(...)` passes through
untouched; under loader-evaluated modules the browser resolves it as a
raw extensionless URL (`…/dist/vendor/cashier/sync`) → 404.

Impact was worse than the error text suggests:

- The **hardware** import sits in the customer-display watcher, which
  runs on *every cart change* — an unhandled rejection per keystroke.
- The **sync** import is the **offline sale queue fallback**: with it
  broken, a sale that failed to post online would error out instead of
  queueing — the offline-first guarantee was silently void.

## Fix

Both sites now resolve their store factory from
`window.AlphaXStores` **at call time** — main.js preloads every store
factory there before mount, and call-time lookup gives the exact
deferred resolution the dynamic imports existed for (pos.js loads
first, so a module-scope destructure would capture undefined).

- Customer display: registry miss degrades gracefully (skip display
  update).
- Offline queue: registry miss rethrows the original online error —
  the register must never pretend a sale was queued when it wasn't.

Also corrected the rethrow variable in the queue fallback to the
enclosing catch's `onlineErr`.

Verified: happy-dom click-through sim green end-to-end (boot → item →
modifiers → cart → Pay → PaymentDialog); jsdom geometry/rail/safety-net
asserts green. Payload = tree = stamp (52285f01…).
