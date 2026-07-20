#!/usr/bin/env python3
"""
Pre-push tree verification for AlphaX POS Suite.

Run from the repo root BEFORE every `git push`:

    python verify_tree.py

Exists because of a real incident: Git for Windows silently failed to
check out files under the 260-character path limit during a
`git reset --hard`, and the following `git add -A` committed the
disappearance of the entire public/dist/vendor tree (57 files),
bricking every register on the next deploy.

Checks, in order:
  1. git core.longpaths is enabled (Windows only; the root cause).
  2. Sentinel files that MUST exist for the app to function.
  3. Minimum file counts for the trees that got lost last time.
  4. Every .py parses; no git conflict markers anywhere.

Exit code 0 = safe to push. Anything else: DO NOT PUSH.
"""
import ast
import glob
import os
import subprocess
import sys

FAIL = []

def check(ok, msg):
    print(("  OK   " if ok else "  FAIL ") + msg)
    if not ok:
        FAIL.append(msg)

print("== 1. git long-path support ==")
try:
    lp = subprocess.run(
        ["git", "config", "--get", "core.longpaths"],
        capture_output=True, text=True
    ).stdout.strip().lower()
    if os.name == "nt":
        check(lp == "true", "core.longpaths=true (run: git config core.longpaths true)")
    else:
        print("  --   not Windows, skipping")
except FileNotFoundError:
    print("  --   git not on PATH, skipping")

print("== 2. sentinel files ==")
SENTINELS = [
    "alphax_pos_suite/hooks.py",
    "alphax_pos_suite/patches.txt",
    "alphax_pos_suite/public/dist/vendor/cashier/sfc-loader.js",
    "alphax_pos_suite/public/dist/vendor/cashier/main.js",
    "alphax_pos_suite/public/dist/vendor/cashier/sfc/App.vue",
    "alphax_pos_suite/public/dist/vendor/cashier/sfc/views/CashierView.vue",
    "alphax_pos_suite/public/dist/vendor/_css/alphax_pos_hub.css",
    "alphax_pos_suite/www/bonanza_order.py",
    "alphax_pos_suite/alphax_pos_suite/page/alphax_cashier/alphax_cashier.js",
    "alphax_pos_suite/alphax_pos_suite/boot/api.py",
    "alphax_pos_suite/alphax_pos_suite/cashier/assets.py",
]
for s in SENTINELS:
    check(os.path.isfile(s), s)

print("== 3. tree sizes ==")
MINIMUMS = {
    "alphax_pos_suite/public/dist/vendor": 50,
    "alphax_pos_suite/public/dist/vendor/cashier/sfc": 40,
    "alphax_pos_suite/alphax_pos_suite/doctype": 100,
}
for root, minimum in MINIMUMS.items():
    n = sum(len(files) for _, _, files in os.walk(root))
    check(n >= minimum, f"{root}: {n} files (need >= {minimum})")

print("== 3.5 embedded payload freshness ==")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_p", "alphax_pos_suite/spa_payload.py")
    _p = importlib.util.module_from_spec(spec); spec.loader.exec_module(_p)
    import io, zipfile, hashlib
    raw = _p.payload_bytes()
    check(hashlib.sha256(raw).hexdigest() == _p.SHA256, "payload hash matches")
    z = zipfile.ZipFile(io.BytesIO(raw))
    disk = {}
    for r, _d, fs in os.walk("alphax_pos_suite/public/dist/vendor"):
        for n in fs:
            rel = os.path.relpath(os.path.join(r, n), "alphax_pos_suite/public/dist/vendor").replace(os.sep, "/")
            disk[rel] = open(os.path.join(r, n), "rb").read()
    stale = [n for n in z.namelist() if n in disk and z.read(n) != disk[n]]
    # .payload_sha is the tree's record of the payload's own digest —
    # it is excluded from the payload BY DESIGN (packing it would change
    # the digest it records). Not a sync failure.
    missing = [n for n in disk if n not in z.namelist() and n != ".payload_sha"]
    check(not stale and not missing,
          f"payload in sync with tree (stale={stale[:2]}, missing={missing[:2]}) — run: python build_spa_payload.py")
except Exception as e:
    check(False, f"payload check errored: {e}")

print("== 3.6 vue template div balance ==")
import re as _re
bad_tpl = []
for vf in glob.glob("alphax_pos_suite/public/dist/vendor/cashier/sfc/**/*.vue", recursive=True):
    txt = open(vf, encoding="utf-8").read()
    m = _re.search(r"<template>([\s\S]*)</template>", txt)
    if not m:
        continue
    tpl = m.group(1)
    o, c = len(_re.findall(r"<div\b", tpl)), len(_re.findall(r"</div>", tpl))
    if o != c:
        bad_tpl.append(f"{vf} ({o} open / {c} close)")
check(not bad_tpl, f"vue templates balanced ({bad_tpl[:2] if bad_tpl else 'clean'})")

print("== 4. python parse + conflict markers ==")
bad_py = []
for f in glob.glob("**/*.py", recursive=True):
    try:
        ast.parse(open(f, encoding="utf-8").read())
    except Exception as e:
        bad_py.append(f"{f}: {e}")
check(not bad_py, f"all python parses ({bad_py[:3] if bad_py else 'clean'})")

marked = []
for f in glob.glob("**/*", recursive=True):
    if not os.path.isfile(f) or os.path.getsize(f) > 5_000_000:
        continue
    # Skip this validator itself (its source mentions the markers) and
    # compiled bytecode (embeds those literals too).
    if os.path.basename(f) == "verify_tree.py" or f.endswith((".pyc", ".pyo")):
        continue
    try:
        txt = open(f, encoding="utf-8", errors="ignore").read()
    except OSError:
        continue
    if "\n<<<<<<< " in txt or txt.startswith("<<<<<<< ") or "\n>>>>>>> " in txt:
        marked.append(f)
check(not marked, f"no conflict markers ({marked[:3] if marked else 'clean'})")

print()
if FAIL:
    print(f"RESULT: {len(FAIL)} FAILURE(S) — DO NOT PUSH.")
    sys.exit(1)
print("RESULT: tree verified — safe to push.")
