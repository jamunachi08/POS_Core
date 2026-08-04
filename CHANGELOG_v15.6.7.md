# AlphaX POS Suite v15.6.7 — Clean Release

## Why this release exists

The v15.6.6 push resolved a git merge incorrectly: four files were
committed WITH their conflict markers still inside
(`alphax_pos_suite/__init__.py`, `setup.py`, `boot/api.py`,
`reporting/close_reports.py`). Those files were not valid Python, so
Frappe Cloud rejected the release ("invalid release with commit hash
…"). Every other file on main was verified byte-identical to the
intended v15.6.6 tree.

## Changes

- The four mangled files restored to their correct v15.6.6 content
  (no code changes beyond the version bump — v15.6.7 exists so the
  platform sees an unambiguous new release).
- Removed `.jetro/daemon/credentials.json`, a local dev-tool scaffold
  accidentally committed by `git add -A`. It was an empty `{}` — no
  secrets were exposed — but the class of mistake is dangerous.
- Added a `.gitignore` (the repo never had one): blocks tool
  scaffolds, caches, build junk, and anything matching
  `*credentials*.json` / `*.key` / `.env` from ever being committed.

## Push procedure (avoids another merge)

    git fetch origin
    git reset --hard origin/main
    # extract this zip over the repo folder, Replace All
    git rm -r --ignore-unmatch .jetro
    git add -A
    git commit -m "v15.6.7 - clean release"
    git push origin main

Note: extracting a zip never DELETES files, so the `git rm` line is
required to drop the stray .jetro folder.
