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
import json
import os
import re
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

print("== 4. packaging metadata (uv / Frappe Cloud build) ==")
setup_src = open("setup.py", encoding="utf-8").read()
pyproject_src = open("pyproject.toml", encoding="utf-8").read()

# A runtime requirement on frappe makes uv resolve frappe's own dependency
# tree during `bench get-app`. frappe pins pypika as a git URL, and uv
# refuses URL dependencies that arrive transitively:
#
#   x Failed to resolve dependencies for `frappe` (v15.116.1)
#   `-> Package `pypika` was included as a URL dependency.
#
# The frappe/erpnext floor belongs in [tool.bench.frappe-dependencies],
# which bench reads itself and never hands to the Python resolver.
declared_frappe = re.search(
    r"^\s*(install_requires|dependencies)\s*=.*?frappe", setup_src, re.M | re.S
)
check(
    not declared_frappe,
    "setup.py declares no frappe runtime dependency"
    + ("" if not declared_frappe else f" — found: {declared_frappe.group(0)[:80]}"),
)

pep621_deps = re.search(r"^\s*dependencies\s*=\s*\[[^\]]*frappe", pyproject_src, re.M | re.S)
check(not pep621_deps, "pyproject.toml declares no frappe runtime dependency")

check(
    "[tool.bench.frappe-dependencies]" in pyproject_src,
    "pyproject.toml carries [tool.bench.frappe-dependencies]",
)

stray_eggs = [p for p in glob.glob("**/*.egg-info", recursive=True)]
check(not stray_eggs, f"no committed egg-info ({stray_eggs[:2] if stray_eggs else 'clean'})")

setup_ver = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)', open(
    "alphax_pos_suite/__init__.py", encoding="utf-8").read()).group(1)
check(
    "get_version()" in setup_src,
    f"setup.py reads version from __init__.py (currently {setup_ver})",
)

print("== 4.5 doctype json integrity ==")
bad_dt = []
for f in glob.glob("alphax_pos_suite/**/doctype/*/*.json", recursive=True):
    if os.path.basename(f).startswith("test_"):
        continue
    try:
        j = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        bad_dt.append(f"{f}: {e}")
        continue
    if j.get("doctype") != "DocType":
        continue
    folder = os.path.basename(os.path.dirname(f))
    expected = j.get("name", "").lower().replace(" ", "_").replace("-", "_")
    if folder != expected:
        bad_dt.append(f"{f}: folder {folder} != name {expected}")
    if not os.path.exists(os.path.join(os.path.dirname(f), "__init__.py")):
        bad_dt.append(f"{f}: missing __init__.py")
    for fld in j.get("fields", []):
        if fld.get("fieldtype") in ("Link", "Table") and not fld.get("options"):
            bad_dt.append(f"{f}: {fld.get('fieldname')} is {fld['fieldtype']} with no options")
check(not bad_dt, f"doctype json sane ({bad_dt[:3] if bad_dt else 'clean'})")

print("== 4.6 select values written by server code ==")
# A Select field rejects any value outside its options, and the failure
# only ever surfaces at runtime in front of a user (v15.10.9 shipped
# shape="Square" against options Rectangle/Circle/Rounded Rectangle).
# Cross-check every dict literal that names one of our doctypes against
# that doctype's Select options.
_select_options = {}
for f in glob.glob("alphax_pos_suite/**/doctype/*/*.json", recursive=True):
    try:
        j = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if j.get("doctype") != "DocType" or not j.get("name"):
        continue
    opts = {}
    for fld in j.get("fields", []):
        if fld.get("fieldtype") == "Select" and fld.get("options"):
            opts[fld["fieldname"]] = {
                o.strip() for o in str(fld["options"]).split("\n") if o.strip()
            }
    if opts:
        _select_options[j["name"]] = opts

bad_select = []
for f in glob.glob("alphax_pos_suite/**/*.py", recursive=True):
    try:
        tree = ast.parse(open(f, encoding="utf-8").read())
    except Exception:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                pairs[k.value] = v
        dt = pairs.get("doctype")
        if not (isinstance(dt, ast.Constant) and isinstance(dt.value, str)):
            continue
        opts = _select_options.get(dt.value)
        if not opts:
            continue
        for field, valnode in pairs.items():
            if field not in opts:
                continue
            if not (isinstance(valnode, ast.Constant) and isinstance(valnode.value, str)):
                continue  # computed at runtime — not checkable here
            if valnode.value and valnode.value not in opts[field]:
                bad_select.append(
                    f"{f}:{valnode.lineno} {dt.value}.{field} = "
                    f"{valnode.value!r} not in {sorted(opts[field])}"
                )
check(not bad_select, f"select values valid ({bad_select[:2] if bad_select else 'clean'})")

print("== 4.7 custom docperm never locks out System Manager ==")
# One Custom DocPerm row replaces a doctype's entire standard permission
# set. A role left off the list loses access silently, and the symptom is
# a desk route that stops resolving ("Page alphax-pos-settings not found"),
# not a permission error. Administrator bypasses permissions, so whoever
# builds the site never sees it.
lockouts = []
for f in glob.glob("alphax_pos_suite/**/*.py", recursive=True):
    try:
        tree = ast.parse(open(f, encoding="utf-8").read())
    except Exception:
        continue
    for node in ast.walk(tree):
        # perm_map = { "Doctype": { "Role": {...}, ... }, ... }
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if not k.value.startswith("AlphaX"):
                continue
            if not isinstance(v, ast.Dict):
                continue
            roles = [rk.value for rk in v.keys
                     if isinstance(rk, ast.Constant) and isinstance(rk.value, str)]
            # Only role maps: every value must itself be a permission dict.
            if not roles or not all(isinstance(rv, ast.Dict) for rv in v.values):
                continue
            if not any("Manager" in r or "Cashier" in r or "Supervisor" in r for r in roles):
                continue
            if "System Manager" not in roles:
                lockouts.append(f"{f}:{k.lineno} {k.value} grants {roles} "
                                f"but not System Manager")
check(not lockouts, f"System Manager never locked out ({lockouts[:2] if lockouts else 'clean'})")

print("== 5. python parse + conflict markers ==")
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
