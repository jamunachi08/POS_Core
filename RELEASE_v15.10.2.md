# AlphaX POS Suite v15.10.2 — complete verified app

Drop-in replacement for the whole repo. Every check below passed on this
exact tree before packaging.

## Why the release was invalid

`alphax_pos_suite/spa_payload.py` was not valid UTF-8. Byte 0x97 sat at
offset 43 — a cp1252 em-dash where UTF-8 needs e2 80 94.

Python 3 source must be UTF-8. That byte makes the module unparseable:

    SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0x97

`install.py` imports spa_payload for `restore_spa_files_if_missing()`, so
the whole app package became unimportable. Frappe Cloud byte-compiles the
app during build, hit that, and rejected the release.

**Cause:** `build_spa_payload.py` line 47 was `open(OUT, "w")` with no
encoding. On Linux and macOS that is UTF-8. On Windows, Python 3.12 uses
the locale encoding — cp1252 on a typical install — so the em-dash in the
generated docstring became a single byte. The file was regenerated on
Windows several times during this work, which is when it appeared.

**Fixed:** both writes in `build_spa_payload.py` now pin
`encoding="utf-8"`, and the generated header is ASCII-only so there is
nothing left to corrupt on an unusual locale.

## Everything else in this build

| Area | State |
|---|---|
| `pyproject.toml` | `[tool.bench.frappe-dependencies]`, pinned `>=15.0.0,<16.0.0` |
| `setup.py` | version read from `__init__.py`, cannot drift |
| `spa_payload.py` | valid UTF-8, parses, 70 files |
| `public/bridge/manifest.json` | no BOM (PowerShell 5.1 wrote one; Python's json.load raised on it and the bundled bridge silently reported unavailable) |
| kit zip | forward slashes, 33 entries, sha matches manifest |
| SFC files | 7 new, identical in `frontend/src` and `public/dist/vendor/cashier/sfc` |
| `main.js` | api / stores / composables / component tiers registered |
| backend | hooks, install, boot all wired |
| i18n | EN + AR in both trees |
| doctypes | 64 valid, no duplicate fieldnames |

## Install

```powershell
cd "E:\POS CORE"
Rename-Item POS_Core POS_Core_old
Expand-Archive alphax_pos_suite-v15.10.2-complete.zip -DestinationPath .
Rename-Item POS_Core-main POS_Core

cd POS_Core
Copy-Item ..\POS_Core_old\.git . -Recurse
git status --short
```

Review the diff, then:

```powershell
git add -A
git commit -m "v15.10.2 - fix spa_payload utf-8 corruption breaking the release build"
git push origin main
```

Then in Frappe Cloud, fetch the new commit and add the app.

## If it still fails

Frappe Cloud prints the real reason below the "invalid release" line —
yours was cut off, so this fix comes from auditing rather than from the
message. If it recurs, paste the full text.

Also confirm the bench's Frappe major version. This declares v15 only;
pass a v16 bench and it will be rejected as incompatible. Change both
lines under `[tool.bench.frappe-dependencies]` if so.

## Known, not fixed

- Root `package.json` pulls `jsdom` and `happy-dom` for `simulate.js`.
  `bench build` runs npm there. It has always been present and has always
  deployed, so it is not the blocker — but those are test-only deps that
  do not belong in a production build.
- `setup.py` declares `install_requires=["frappe>=15.0.0"]`. Frappe comes
  from git via bench, not PyPI. It resolves today because frappe is
  already in the environment; a clean resolve could reach for an
  unrelated PyPI package of that name.
- Non-admin bridge install untested on a real standard-user account.
- Arabic strings are a first pass, not reviewed by a native speaker.
