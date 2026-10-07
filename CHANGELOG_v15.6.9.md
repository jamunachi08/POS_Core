# AlphaX POS Suite v15.6.9 — Unbrickable Register

## Context

The v15.6.8 push lost the vendor asset tree AGAIN (GitHub main: 368
files, zero cashier files) — the second time Windows long-path
handling has eaten the deep tree in transit. Rather than attempt a
third file-transport fix, the architecture now makes the register
impossible to brick by file loss.

## The embedded payload

- **`alphax_pos_suite/spa_payload.py`** (263 KB, auto-generated):
  a compressed, sha256-verified copy of ALL 57 vendor asset files,
  baked into one Python file at a SHORT path — immune to the long-path
  failures that deleted the real tree twice. If Python deploys, the
  register deploys.
- **Serving** (`cashier/assets.py`): when no filesystem root has the
  SPA, `spa_asset` and `spa_manifest` serve straight from the payload
  (in-memory zip). Verified in a worst-case test: a repo containing
  ONLY python files boots the full register.
- **Self-heal** (`install.py` + hooks): `restore_spa_files_if_missing`
  runs first in `after_migrate` (and at install) — if the on-disk tree
  lacks the SPA, it unpacks the payload to
  `public/dist/vendor/`, then `force_rebuild_assets` links a complete
  tree, so even the fast `/assets` path recovers automatically.
- **Regeneration**: after any SPA file change, run
  `python build_spa_payload.py`. `verify_tree.py` now FAILS if the
  payload is out of sync with the tree, so a stale payload cannot
  ship.
- `asset_health` reports the payload's availability on the error card.

## Deploy expectation

Even if this push loses the deep tree a third time, the deploy
self-heals: migrate unpacks the payload, `/assets` serves, register
boots. If migrate hooks are skipped for any reason, the API fallback
serves from the payload directly. There is no remaining failure mode
short of the Python package itself not deploying.
