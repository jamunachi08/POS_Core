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
    d = os.path.dirname(f)
    if not os.path.exists(os.path.join(d, "__init__.py")):
        bad_dt.append(f"{f}: missing __init__.py")

    # Frappe imports a controller module for EVERY DocType, child tables
    # included, and aborts the whole install when one is absent:
    #   "Module import failed for X, the DocType you're trying to open
    #    might be deleted."
    # v15.12.0 shipped three child tables with a JSON and no .py, which
    # made the app uninstallable. The class must exist too — an empty
    # file passes the import and then fails at run_module_method.
    ctrl = os.path.join(d, folder + ".py")
    if not os.path.exists(ctrl):
        bad_dt.append(f"{f}: missing controller {folder}.py")
    else:
        src = open(ctrl, encoding="utf-8").read()
        expected = "".join(w[0].upper() + w[1:] for w in j["name"].split())
        expected = expected.replace("Pos", "POS").replace("Alphax", "AlphaX")
        if not re.search(r"class\s+\w+\s*\(\s*Document\s*\)", src):
            bad_dt.append(f"{ctrl}: no Document subclass (expected {expected})")
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

print("== 4.8 vue composition api imports ==")
# `watch(...)` used without importing `watch` is a ReferenceError at
# component setup, which Vue turns into a blank page — no stack in the UI,
# nothing in the network tab. v15.11.4 shipped exactly that because a
# find-and-replace on the import line silently matched nothing.
VUE_API = [
    "ref", "computed", "watch", "watchEffect", "reactive", "readonly",
    "toRef", "toRefs", "nextTick", "provide", "inject", "shallowRef",
    "onMounted", "onUnmounted", "onBeforeMount", "onBeforeUnmount",
    "onUpdated", "onActivated", "onDeactivated", "defineAsyncComponent",
]
missing_imports = []
for f in glob.glob("alphax_pos_suite/**/*.vue", recursive=True):
    src = open(f, encoding="utf-8").read()
    m = re.search(r"<script[^>]*>(.*?)</script>", src, re.S)
    if not m:
        continue
    script = m.group(1)
    imported = set()
    for imp in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"]vue['\"]", script):
        for part in imp.group(1).split(","):
            name = part.strip().split(" as ")[-1].strip()
            if name:
                imported.add(name)
    # Strip strings and comments so a mention inside text is not a use.
    body = re.sub(r"//[^\n]*", "", script)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", "''", body)
    for name in VUE_API:
        if name in imported:
            continue
        # A call, not a property access or a local declaration.
        if re.search(r"(?<![\w.$])" + name + r"\s*\(", body) and \
           not re.search(r"(?:const|let|var|function)\s+" + name + r"\b", body):
            missing_imports.append(f"{f}: uses {name}() but does not import it from 'vue'")
check(not missing_imports,
      f"vue composition api imported where used ({missing_imports[:2] if missing_imports else 'clean'})")

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

print("== 6. role flow: lane/matrix width ==")
# Adding a lane without extending every MATRIX row renders a ragged grid
# and silently drops a column. Fail the build instead of the page.
try:
    import re as _re
    _src = open("alphax_pos_suite/alphax_pos_suite/pos/role_flow.py", encoding="utf-8").read()
    _tree = ast.parse(_src)
    _lane_ids, _widths, _roles_used = [], set(), set()
    for node in _tree.body:
        if not isinstance(node, ast.Assign):
            continue
        name = getattr(node.targets[0], "id", None)
        if name == "LANES":
            for el in node.value.elts:
                for k, v in zip(el.keys, el.values):
                    if getattr(k, "value", None) == "id":
                        _lane_ids.append(v.value)
                    if getattr(k, "value", None) == "role" and isinstance(v, ast.Name):
                        _roles_used.add(v.id)
        if name == "MATRIX":
            for el in node.value.elts:
                _widths.add(len(el.elts[2].elts))
    check(bool(_lane_ids), f"role_flow LANES parsed ({len(_lane_ids)} lanes)")
    check(_widths == {len(_lane_ids)},
          f"every MATRIX row has one value per lane (lanes={len(_lane_ids)}, widths={sorted(_widths)})")
except FileNotFoundError:
    check(True, "role_flow.py absent — skipped")
except Exception as e:
    check(False, f"role flow guard could not run: {e}")

print("== 7. process flow seeder integrity ==")
# Three ways this seeder silently rots: a node pointing at a DocType that
# no longer exists, a node filed under a stage that was renamed, and a
# desk Page route colliding with a DocType slug (which makes the route
# resolve to the list view instead of the board).
try:
    import json as _json

    _seed = "alphax_pos_suite/alphax_pos_suite/seed/process_flow.py"
    _src = open(_seed, encoding="utf-8").read()
    _tree = ast.parse(_src)

    _stage_keys, _nodes = set(), []
    for _n in _tree.body:
        if not isinstance(_n, ast.Assign) or not isinstance(_n.targets[0], ast.Name):
            continue
        if _n.targets[0].id == "STAGES":
            for _el in _n.value.elts:
                _stage_keys.add(_el.elts[0].value)
        if _n.targets[0].id == "NODES":
            for _el in _n.value.elts:
                _nodes.append(_el)

    # DocTypes this app ships
    _known = set()
    _dtdir = "alphax_pos_suite/alphax_pos_suite/doctype"
    for _d in os.listdir(_dtdir):
        _f = os.path.join(_dtdir, _d, _d + ".json")
        if os.path.isfile(_f):
            _known.add(_json.load(open(_f, encoding="utf-8")).get("name"))

    # Stock Frappe/ERPNext doctypes the seeder is allowed to reference.
    # Kept in step with the STD set inside the seeder itself.
    _std = set()
    for _n in _tree.body:
        if isinstance(_n, ast.Assign) and isinstance(_n.targets[0], ast.Name) \
                and _n.targets[0].id == "STD":
            _std = {_e.value for _e in _n.value.elts}

    _bad_dt, _bad_stage, _untagged = [], [], []
    for _el in _nodes:
        _v = [e.value if isinstance(e, ast.Constant) else None for e in _el.elts]
        _label, _stage, _ntype, _target = _v[0], _v[2], _v[4], _v[5]
        if _stage not in _stage_keys:
            _bad_stage.append(f"{_label} -> stage '{_stage}'")
        if _ntype == "DocType":
            if _target not in _known and _target not in _std:
                _bad_dt.append(f"{_label} -> '{_target}'")
            if _target in _known and _target in _std:
                _untagged.append(_label)

    check(bool(_nodes), f"process flow seeder parsed ({len(_stage_keys)} stages, {len(_nodes)} nodes)")
    check(not _bad_stage, f"every node has a known stage ({_bad_stage[:3] if _bad_stage else 'clean'})")
    check(not _bad_dt, f"every node targets a known DocType ({_bad_dt[:3] if _bad_dt else 'clean'})")
    check(not _untagged, f"no doctype in both app and STD sets ({_untagged[:3] if _untagged else 'clean'})")

    # A Single has no table: a List node on one raises TableMissingError.
    _singles = set()
    for _d in os.listdir(_dtdir):
        _f = os.path.join(_dtdir, _d, _d + ".json")
        if os.path.isfile(_f):
            _j = _json.load(open(_f, encoding="utf-8"))
            if _j.get("issingle"):
                _singles.add(_j.get("name"))
    _bad_single = []
    for _el in _nodes:
        _v = [e.value if isinstance(e, ast.Constant) else None for e in _el.elts]
        if _v[4] == "DocType" and _v[5] in _singles and _v[6] != "Form":
            _bad_single.append(f"{_v[0]} -> {_v[5]} view={_v[6]}")
    check(not _bad_single,
          f"single doctypes use Form view ({_bad_single[:3] if _bad_single else 'clean'})")

    # Page route must not collide with a DocType slug.
    _collisions = []
    _pagedir = "alphax_pos_suite/alphax_pos_suite/page"
    _slugs = {d.lower().replace(" ", "-") for d in _known}
    if os.path.isdir(_pagedir):
        for _d in os.listdir(_pagedir):
            _f = os.path.join(_pagedir, _d, _d + ".json")
            if not os.path.isfile(_f):
                continue
            _pn = _json.load(open(_f, encoding="utf-8")).get("page_name")
            if _pn in _slugs:
                _collisions.append(_pn)
    check(not _collisions,
          f"no page route collides with a doctype slug ({_collisions[:3] if _collisions else 'clean'})")
except FileNotFoundError:
    check(True, "process flow seeder absent — skipped")
except Exception as e:
    check(False, f"process flow guard could not run: {e}")

print("== 8. workspace fixture integrity ==")
# Three silent killers on the hub page: a shortcut with no matching content
# block (defined but never drawn), a content block naming a shortcut that no
# longer exists (drawn as nothing), and a Page link pointing at a folder name
# instead of the Page's actual name (a dead menu entry).
try:
    import json as _json

    _wf = "alphax_pos_suite/fixtures/workspace.json"
    _w = _json.load(open(_wf, encoding="utf-8"))[0]
    _content = _w["content"]
    _content = _json.loads(_content) if isinstance(_content, str) else _content

    _sc = {x["label"] for x in _w.get("shortcuts", [])}
    _cb = {b["data"]["shortcut_name"] for b in _content if b.get("type") == "shortcut"}
    check(not (_sc - _cb),
          f"every shortcut is drawn ({sorted(_sc - _cb)[:3] if (_sc - _cb) else 'clean'})")
    check(not (_cb - _sc),
          f"every tile has a shortcut ({sorted(_cb - _sc)[:3] if (_cb - _sc) else 'clean'})")

    _cards = {b["data"]["card_name"] for b in _content if b.get("type") == "card"}
    _breaks = {l["label"] for l in _w.get("links", []) if l.get("type") == "Card Break"}
    check(not (_cards ^ _breaks),
          f"cards match card breaks ({sorted(_cards ^ _breaks)[:3] if (_cards ^ _breaks) else 'clean'})")

    _pagedir = "alphax_pos_suite/alphax_pos_suite/page"
    _pages = set()
    if os.path.isdir(_pagedir):
        for _d in os.listdir(_pagedir):
            _f = os.path.join(_pagedir, _d, _d + ".json")
            if os.path.isfile(_f):
                _j = _json.load(open(_f, encoding="utf-8"))
                _pages.add(_j.get("name"))

    _dead = [(l.get("label"), l.get("link_to")) for l in _w.get("links", [])
             if l.get("link_type") == "Page" and l.get("link_to") and l["link_to"] not in _pages]
    _dead += [(x.get("label"), x.get("link_to")) for x in _w.get("shortcuts", [])
              if x.get("type") == "Page" and x.get("link_to") not in _pages]
    check(not _dead, f"every workspace Page link resolves ({_dead[:3] if _dead else 'clean'})")
except FileNotFoundError:
    check(True, "workspace fixture absent — skipped")
except Exception as e:
    check(False, f"workspace guard could not run: {e}")

print("== 9. flow page JS -> python resolution ==")
# The board calls two modules. A renamed function fails silently in the
# browser as a 404 on /api/method, so resolve every call here instead.
try:
    import re as _re

    def _whitelisted(path):
        _t = ast.parse(open(path, encoding="utf-8").read())
        out = set()
        for _n in _t.body:
            if isinstance(_n, ast.FunctionDef):
                for _dec in _n.decorator_list:
                    _src = ast.unparse(_dec) if hasattr(ast, "unparse") else ""
                    if "whitelist" in _src:
                        out.add(_n.name)
        return out

    _base = "alphax_pos_suite/alphax_pos_suite"
    _js = open(f"{_base}/page/alphax_pos_flow/alphax_pos_flow.js", encoding="utf-8").read()
    _mods = {
        "alphax_pos_suite.alphax_pos_suite.pos.flow_api": _whitelisted(f"{_base}/pos/flow_api.py"),
        "alphax_pos_suite.alphax_pos_suite.pos.flow_setup": _whitelisted(f"{_base}/pos/flow_setup.py"),
    }
    _missing = []
    for _mod, _m in _re.findall(r'"(alphax_pos_suite\.alphax_pos_suite\.pos\.flow_\w+)\.(\w+)"', _js):
        if _m not in _mods.get(_mod, set()):
            _missing.append(f"{_mod.split('.')[-1]}.{_m}")
    _setup = _re.search(r'const SETUP = "([^"]+)"', _js)
    if _setup:
        for _m in _re.findall(r"\$\{SETUP\}\.(\w+)", _js):
            if _m not in _mods.get(_setup.group(1), set()):
                _missing.append(f"SETUP.{_m}")
    _calls = len(_re.findall(r"\$\{SETUP\}\.\w+", _js)) + len(
        _re.findall(r'"alphax_pos_suite\.alphax_pos_suite\.pos\.flow_\w+\.\w+"', _js))
    check(_calls > 0, f"flow page server calls found ({_calls})")
    check(not _missing, f"every flow page call is whitelisted ({_missing[:3] if _missing else 'clean'})")
except FileNotFoundError:
    check(True, "flow page absent — skipped")
except Exception as e:
    check(False, f"flow JS resolution guard could not run: {e}")

print("== 10. bridge kit integrity ==")
# The personalised installer verifies the kit's SHA-256 against this
# manifest before unpacking. A kit rebuilt without updating the manifest
# makes every bridge install on every till fail with "Download is corrupt".
try:
    import hashlib as _hl, json as _json, zipfile as _zf
    _bd = "alphax_pos_suite/public/bridge"
    _m = _json.load(open(f"{_bd}/manifest.json", encoding="utf-8-sig"))
    _kit = f"{_bd}/{_m.get('kit_file', '')}"
    check(os.path.isfile(_kit), f"kit file present ({_m.get('kit_file')})")
    if os.path.isfile(_kit):
        _data = open(_kit, "rb").read()
        check(_hl.sha256(_data).hexdigest() == (_m.get("sha256") or "").lower(),
              "kit SHA-256 matches manifest")
        check(len(_data) == int(_m.get("size_bytes") or -1), "kit size matches manifest")
        _whl = [n for n in _zf.ZipFile(_kit).namelist() if n.endswith(".whl")]
        check(len(_whl) == 1 and f"-{_m.get('version')}-" in _whl[0],
              f"kit carries exactly one wheel at the manifest version ({_whl})")
    _stale = [f for f in os.listdir(_bd) if f.startswith("AlphaX-POS-Bridge-Setup-")
              and f != _m.get("kit_file")]
    check(not _stale, f"no stale kits left beside the current one ({_stale or 'clean'})")
except FileNotFoundError:
    check(True, "no bridge manifest — skipped")
except Exception as e:
    check(False, f"bridge kit guard could not run: {e}")

print()
if FAIL:
    print(f"RESULT: {len(FAIL)} FAILURE(S) — DO NOT PUSH.")
    sys.exit(1)
print("RESULT: tree verified — safe to push.")
