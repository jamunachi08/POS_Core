# AlphaX POS Suite v15.7.5 — Deploy Integrity + Adaptive Layout + Sidebar Rail

## Why hard-refresh could never fix your register (root cause)

The v15.7.4 zip carried the FIXED source files but a STALE embedded
payload (`spa_payload.py`, sha 0884… vs tree 4e12…). When git transport
drops the deep vendor tree (the twice-observed Windows long-path
failure), the server self-heals the tree **from that payload** on
migrate — faithfully restoring the OLD code. The site then genuinely
serves the previous build; no amount of Ctrl+Shift+R can help because
the bug is on the server, not in the browser cache.

Fixed permanently with **versioned self-heal**:

- `build_spa_payload.py` now writes a `.payload_sha` stamp into the
  vendor tree recording the digest of the payload built from it.
- `install.py` on every migrate re-extracts the payload whenever the
  on-disk stamp is missing or differs from `spa_payload.SHA256` — the
  tree and payload can no longer diverge on a deployed site. A release
  is shipped only when payload = tree = stamp (verified three-way this
  release: 8680c979…).

## Layout: measure, verify, and a scroll safety net

v15.7.4 sized the register with `top: var(--navbar-height, 60px)` — but
nothing ever set that variable, so every install ran on the 60px guess.
Branded navbars (client logo), browser zoom, and OS font scaling make
the real navbar taller; `position: fixed` additionally re-anchors to any
desk ancestor carrying a CSS transform. Both failure modes clipped the
Pay footer below the fold with the page unscrollable (reported from
production, WhiteHelmet site).

- The shell now **measures** the real navbar bottom at runtime, sizes
  itself to the true viewport remainder, then **verifies** its own
  on-screen rect next frame and subtracts any residual offset from a
  transformed ancestor. Re-runs on window resize, navbar resize
  (ResizeObserver), and late font load.
- The cart panel is a strict flex column: lines scroll internally,
  the totals + Pay footer is pinned and always visible.
- **Safety net:** the shell root carries `overflow-y: auto` — if
  geometry is ever wrong again, content scrolls; it can never be
  unreachable.

## Collapsible sidebar rail

- Collapsed 64px icon rail by default (labels stop being read after
  day two; grid space never stops mattering) — returns ~200px to the
  item grid, a full extra card column.
- Tap the rail toggle to pin it open; state persists per terminal.
- Mouse users additionally get hover-expand (300ms intent delay) as an
  overlay that never reflows the grid. Hover is intentionally NOT the
  primary mechanism: touch terminals have no hover, and hover panels
  flap when a hand crosses the screen.
- Shift In/Close stays visible as a colored icon in rail mode — it is
  the register's most safety-critical state indicator.

## Verification & diagnostics

- New canonical click-through sim on happy-dom (`simulate_happy.js`):
  boot → item tap → modifier picker (size/milk/extras) → Add to order →
  cart line lands → Pay → PaymentDialog with Cash tender. All real DOM
  clicks, all green.
- The jsdom sim (`simulate.js`) keeps the geometry/rail/safety-net
  assertions. A jsdom-specific artifact was diagnosed and documented:
  under jsdom, mounting the modifier picker triggers a phantom
  click→close chain that unmounts it, leaving zombie DOM whose emits
  are silently dropped. Confirmed NOT present on happy-dom — app code
  is correct; the annotation prevents future sessions from chasing it.
- `main.js` now registers `app.config.errorHandler` (production Vue
  otherwise rethrows and errors vanish) and exposes
  `window.__ALPHAX_PINIA__` / `window.__ALPHAX_APP__` so on-site
  diagnostics can inspect store state without a dev build.

## Upgrade

Push to GitHub → Deploy on Frappe Cloud → `bench migrate` runs the
stamped self-heal automatically. One hard refresh after deploy and the
register is guaranteed to run this build.
