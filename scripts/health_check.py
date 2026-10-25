#!/usr/bin/env python3
"""
AlphaX POS Suite — static health check (v16 readiness + internal integrity).

Usage:
    python scripts/health_check.py [--ref /path/to/apps]   # dir holding frappe/ and erpnext/ source

Without --ref, only internal checks run. With --ref pointing at Frappe/ERPNext
version-16 source, every import, dotted method path, DocType and core-field
reference in the app is resolved against v16.

Exit code 1 on any FAIL. WARN lines do not fail the run.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "alphax_pos_suite"
FAILS: list[str] = []
WARNS: list[str] = []
SECTION = [""]

REMOVED_STDLIB = {  # removed by Python 3.12–3.14 (Frappe v16 runs 3.14)
	"distutils", "imp", "asynchat", "asyncore", "smtpd", "cgi", "cgitb", "crypt", "telnetlib",
	"nntplib", "pipes", "audioop", "chunk", "imghdr", "mailcap", "msilib", "nis", "ossaudiodev",
	"sndhdr", "spwd", "sunau", "uu", "xdrlib", "lib2to3", "pkg_resources",
}


def section(name):
	SECTION[0] = name
	print(f"\n== {name} ==")


def fail(msg):
	FAILS.append(f"[{SECTION[0]}] {msg}")
	print("  FAIL", msg)


def warn(msg):
	WARNS.append(f"[{SECTION[0]}] {msg}")
	print("  WARN", msg)


def ok(msg):
	print("  OK  ", msg)


# ---------------------------------------------------------------- module index


class ModuleIndex:
	"""Resolve dotted names against one or more source roots without importing."""

	def __init__(self, roots: list[Path]):
		self.roots = roots
		self._names: dict[Path, set[str]] = {}

	def _file(self, dotted: str) -> Path | None:
		parts = dotted.split(".")
		for root in self.roots:
			base = root.joinpath(*parts)
			if base.with_suffix(".py").is_file():
				return base.with_suffix(".py")
			if (base / "__init__.py").is_file():
				return base / "__init__.py"
		return None

	def names(self, path: Path) -> set[str]:
		if path not in self._names:
			out = set()
			try:
				tree = ast.parse(path.read_text(encoding="utf-8"))
			except Exception:
				self._names[path] = {"*"}
				return self._names[path]
			for node in tree.body:
				if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
					out.add(node.name)
				elif isinstance(node, ast.Assign):
					for t in node.targets:
						for n in ast.walk(t):
							if isinstance(n, ast.Name):
								out.add(n.id)
				elif isinstance(node, (ast.AnnAssign,)) and isinstance(node.target, ast.Name):
					out.add(node.target.id)
				elif isinstance(node, (ast.Import, ast.ImportFrom)):
					for a in node.names:
						out.add("*" if a.name == "*" else (a.asname or a.name).split(".")[0])
				elif isinstance(node, (ast.If, ast.Try)):
					for sub in ast.walk(node):
						if isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
							out.add(sub.name)
						elif isinstance(sub, ast.Assign):
							for t in sub.targets:
								if isinstance(t, ast.Name):
									out.add(t.id)
						elif isinstance(sub, (ast.Import, ast.ImportFrom)):
							for a in sub.names:
								out.add((a.asname or a.name).split(".")[0])
			self._names[path] = out
		return self._names[path]

	def module_exists(self, dotted: str) -> bool:
		return self._file(dotted) is not None

	def resolve_attr(self, module: str, name: str) -> bool:
		f = self._file(module)
		if f is None:
			return False
		if self._file(f"{module}.{name}"):
			return True
		names = self.names(f)
		return name in names or "*" in names

	def resolve_path(self, dotted: str) -> bool:
		"""a.b.c.func — module a.b.c with attribute func (or a module itself)."""
		if self.module_exists(dotted):
			return True
		mod, _, attr = dotted.rpartition(".")
		return bool(mod) and self.resolve_attr(mod, attr)


# ---------------------------------------------------------------- doctype index


def load_doctypes(root: Path, app_label: str) -> dict[str, dict]:
	out = {}
	for p in root.rglob("doctype/*/*.json"):
		if p.parent.name != p.stem:
			continue
		try:
			d = json.loads(p.read_text(encoding="utf-8"))
		except Exception:
			continue
		if isinstance(d, dict) and d.get("doctype") == "DocType" and d.get("name"):
			d["_path"] = p
			d["_app"] = app_label
			out[d["name"]] = d
	return out


def py_files(base: Path):
	for p in base.rglob("*.py"):
		if "node_modules" in p.parts or "__pycache__" in p.parts:
			continue
		yield p


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--ref", help="directory containing frappe/ and erpnext/ source checkouts")
	args = ap.parse_args()

	ref_roots = []
	if args.ref:
		ref = Path(args.ref)
		for name in ("frappe", "erpnext"):
			cand = [ref / name, *ref.glob(f"{name}-*")]
			for c in cand:
				if (c / name / "__init__.py").is_file():
					ref_roots.append(c)
					break
			else:
				print(f"--ref: could not find {name} source under {ref}")
				sys.exit(2)

	index = ModuleIndex([ROOT, *ref_roots])
	app_doctypes = load_doctypes(APP, "alphax_pos_suite")
	ref_doctypes = {}
	for r in ref_roots:
		ref_doctypes.update(load_doctypes(r, r.name))
	all_doctypes = {**ref_doctypes, **app_doctypes}

	# -------------------------------------------------------------- 1 versions
	section("1. version and dependency pins")
	init_ver = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (APP / "__init__.py").read_text()).group(1)
	ok(f"app version {init_ver}")
	pyproject = (ROOT / "pyproject.toml").read_text()
	for dep in ("frappe", "erpnext"):
		m = re.search(rf'^{dep}\s*=\s*"([^"]+)"', pyproject, re.M)
		if not m:
			warn(f"no {dep} pin in [tool.bench.frappe-dependencies]")
			continue
		spec = m.group(1)
		if "<16" in spec.replace(" ", ""):
			fail(f"{dep} pinned '{spec}' — Frappe Cloud will refuse a v16 bench")
		else:
			ok(f"{dep} pin '{spec}' admits v16")
	if 'requires-python' in pyproject:
		ok("requires-python declared")
	# frappe / erpnext must never be pip dependencies: pip/uv then tries to
	# resolve frappe from PyPI, whose pypika URL pin uv refuses ("URL
	# dependencies must be expressed as direct requirements"), and bench
	# get-app fails. Bench resolves them from [tool.bench.frappe-dependencies].
	setup_py = (ROOT / "setup.py").read_text() if (ROOT / "setup.py").exists() else ""
	proj = re.search(r"^\[project\](.*?)(^\[|\Z)", pyproject, re.S | re.M)
	pip_deps = (proj.group(1) if proj else "") + (setup_py.split("install_requires", 1)[1][:800] if "install_requires" in setup_py else "")
	bad = re.findall(r"['\"](frappe|erpnext)\s*[<>=~!\]]", pip_deps)
	if bad:
		fail(f"{', '.join(sorted(set(bad)))} listed as a pip dependency — bench get-app fails under uv; keep them only in [tool.bench.frappe-dependencies]")
	else:
		ok("frappe/erpnext are bench dependencies only, not pip dependencies")

	# -------------------------------------------------------------- 2 python
	section("2. Python 3.14 readiness")
	removed_hits = defaultdict(list)
	utcnow = []
	for p in py_files(APP):
		try:
			tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
		except SyntaxError as e:
			fail(f"syntax error {p.relative_to(ROOT)}:{e.lineno} {e.msg}")
			continue
		for node in ast.walk(tree):
			mods = []
			if isinstance(node, ast.Import):
				mods = [a.name for a in node.names]
			elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
				mods = [node.module]
			for m in mods:
				if m.split(".")[0] in REMOVED_STDLIB:
					removed_hits[m.split(".")[0]].append(f"{p.relative_to(ROOT)}:{node.lineno}")
			if isinstance(node, ast.Attribute) and node.attr in ("utcnow", "utcfromtimestamp"):
				utcnow.append(f"{p.relative_to(ROOT)}:{node.lineno}")
	for m, where in removed_hits.items():
		fail(f"imports '{m}' (removed in Python 3.12–3.14): {', '.join(where[:5])}")
	if not removed_hits:
		ok("no removed stdlib modules imported")
	if utcnow:
		warn(f"datetime.utcnow/utcfromtimestamp deprecated ({len(utcnow)}): {', '.join(utcnow[:5])}")

	# -------------------------------------------------------------- 3 imports
	if ref_roots:
		section("3. frappe / erpnext imports resolve on v16")
		bad = []
		checked = 0
		for p in py_files(APP):
			tree = ast.parse(p.read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
					top = node.module.split(".")[0]
					if top not in ("frappe", "erpnext"):
						continue
					if not index.module_exists(node.module):
						bad.append(f"{p.relative_to(ROOT)}:{node.lineno} module {node.module}")
						continue
					for a in node.names:
						checked += 1
						if a.name != "*" and not index.resolve_attr(node.module, a.name):
							bad.append(f"{p.relative_to(ROOT)}:{node.lineno} {node.module}.{a.name}")
				elif isinstance(node, ast.Import):
					for a in node.names:
						if a.name.split(".")[0] in ("frappe", "erpnext") and "." in a.name:
							checked += 1
							if not index.module_exists(a.name):
								bad.append(f"{p.relative_to(ROOT)}:{node.lineno} import {a.name}")
		for b in bad:
			fail(f"unresolved on v16: {b}")
		if not bad:
			ok(f"{checked} imported names resolve on v16")

	# -------------------------------------------------------------- 4 hooks
	section("4. hooks.py dotted paths")
	hooks_src = (APP / "hooks.py").read_text()
	paths = set(re.findall(r'["\']((?:alphax_pos_suite|frappe|erpnext)(?:\.[A-Za-z_][A-Za-z0-9_]*){2,})["\']', hooks_src))
	unresolved = [d for d in sorted(paths) if (d.startswith("alphax") or ref_roots) and not index.resolve_path(d)]
	for d in unresolved:
		fail(f"hooks.py → {d} does not resolve")
	if not unresolved:
		ok(f"{len(paths)} dotted paths resolve")

	section("4b. duplicate keys in dict literals")
	dup_hits = []
	for p in py_files(APP):
		try:
			tree = ast.parse(p.read_text(encoding="utf-8"))
		except SyntaxError:
			continue
		for node in ast.walk(tree):
			if isinstance(node, ast.Dict):
				seen = set()
				for k in node.keys:
					if isinstance(k, ast.Constant) and isinstance(k.value, (str, int)):
						if k.value in seen:
							dup_hits.append(f"{p.relative_to(ROOT)}:{k.lineno} key {k.value!r}")
						seen.add(k.value)
	for d in dup_hits:
		fail(f"duplicate dict key (the earlier value is silently lost): {d}")
	if not dup_hits:
		ok("no duplicate keys in dict literals")

	# -------------------------------------------------------------- 5 patches
	section("5. patches.txt")
	pt = APP / "patches.txt"
	n = 0
	for line in pt.read_text().splitlines():
		line = line.split("#")[0].strip()
		if not line or line.startswith("["):
			continue
		if line.startswith("execute:"):
			continue
		n += 1
		mod = line.split()[0]
		f = index._file(mod)
		if not f:
			fail(f"patch module missing: {mod}")
		elif "execute" not in index.names(f):
			fail(f"patch has no execute(): {mod}")
	ok(f"{n} patch entries checked")

	# -------------------------------------------------------------- 6 doctypes
	section("6. app DocTypes")
	modules = {m.strip() for m in (APP / "modules.txt").read_text().splitlines() if m.strip()}
	dup_names = defaultdict(list)
	for name, d in app_doctypes.items():
		rel = d["_path"].relative_to(ROOT)
		if d.get("module") not in modules:
			fail(f"{name}: module '{d.get('module')}' not in modules.txt")
		seen = set()
		for f in d.get("fields", []):
			fn = f.get("fieldname")
			if not fn:
				continue
			if fn in seen:
				fail(f"{name}: duplicate fieldname '{fn}'")
			seen.add(fn)
			ft, opt = f.get("fieldtype"), (f.get("options") or "").strip()
			if ft in ("Link", "Table", "Table MultiSelect") and opt:
				if opt not in all_doctypes and (ref_roots or opt.startswith("AlphaX")):
					fail(f"{name}.{fn} → {ft} '{opt}' does not exist{' on v16' if ref_roots else ''}")
				elif ft != "Link" and opt in all_doctypes and not all_doctypes[opt].get("istable"):
					fail(f"{name}.{fn} → '{opt}' is not a child table")
		dup_names[name.lower()].append(str(rel))
		if d.get("istable") and d.get("is_submittable"):
			fail(f"{name}: child table marked submittable")
		for perm in d.get("permissions", []):
			if perm.get("role") and ref_roots and not any(True for _ in [0]):
				pass
	ok(f"{len(app_doctypes)} DocTypes parsed")

	# -------------------------------------------------------------- 7 core refs
	if ref_roots:
		section("7. DocType names and core fields used in Python (v16)")
		call_re = re.compile(
			r'frappe\.(?:get_doc|get_cached_doc|new_doc|get_all|get_list|get_meta|db\.get_value|db\.set_value|'
			r'db\.exists|db\.count|db\.get_single_value|get_cached_value|db\.get_all|qb\.DocType|db\.delete|'
			r'has_permission|get_single)\(\s*["\']([A-Z][A-Za-z0-9 ]+)["\']'
		)
		value_re = re.compile(
			r'frappe\.(?:db\.get_value|get_cached_value|db\.set_value)\(\s*["\']([A-Z][A-Za-z0-9 ]+)["\']\s*,[^,()]+,\s*["\']([a-z_][a-z0-9_]*)["\']'
		)
		custom_fields = defaultdict(set)
		for jf in list((APP / "fixtures").glob("*.json")) + list(APP.rglob("custom/*.json")) + list(APP.rglob("data/*custom_field*.json")):
			try:
				data = json.loads(jf.read_text())
			except Exception:
				continue
			rows = data if isinstance(data, list) else data.get("custom_fields", [])
			for r in rows if isinstance(rows, list) else []:
				if isinstance(r, dict) and r.get("dt") and r.get("fieldname"):
					custom_fields[r["dt"]].add(r["fieldname"])
		# custom fields created in Python
		cf_src_re = re.compile(r'["\']fieldname["\']\s*:\s*["\']([a-z_][a-z0-9_]*)["\']')
		for p in py_files(APP):
			src = p.read_text(encoding="utf-8")
			if "create_custom_field" in src or "Custom Field" in src:
				for fn in cf_src_re.findall(src):
					custom_fields["*"].add(fn)
		missing_dt, missing_field = set(), set()
		for p in py_files(APP):
			src = p.read_text(encoding="utf-8")
			for dt in call_re.findall(src):
				if dt not in all_doctypes and dt not in ("DocType", "File"):
					missing_dt.add(f"'{dt}' in {p.relative_to(ROOT)}")
			for dt, fn in value_re.findall(src):
				d = all_doctypes.get(dt)
				if not d or d.get("_app") == "alphax_pos_suite":
					continue
				std = {f.get("fieldname") for f in d.get("fields", [])} | {
					"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parenttype", "parentfield"
				}
				if fn not in std and fn not in custom_fields.get(dt, set()) and fn not in custom_fields["*"]:
					missing_field.add(f"{dt}.{fn} in {p.relative_to(ROOT)}")
		for m in sorted(missing_dt):
			fail(f"DocType not on v16 or in app: {m}")
		for m in sorted(missing_field):
			fail(f"field not on v16 DocType or app custom fields: {m}")
		if not missing_dt and not missing_field:
			ok("DocType and core-field references resolve on v16")

		section("8. custom fields target v16 DocTypes")
		bad = []
		for jf in list((APP / "fixtures").glob("*.json")) + list(APP.rglob("data/*custom_field*.json")):
			try:
				data = json.loads(jf.read_text())
			except Exception:
				fail(f"fixture not valid JSON: {jf.name}")
				continue
			for r in data if isinstance(data, list) else []:
				if isinstance(r, dict) and r.get("doctype") in ("Custom Field", "Property Setter"):
					dt = r.get("dt") or r.get("doc_type")
					if dt and dt not in all_doctypes:
						bad.append(f"{jf.name}: {r.get('doctype')} on missing DocType '{dt}'")
					ia = r.get("insert_after")
					if dt in all_doctypes and ia:
						fields = {f.get("fieldname") for f in all_doctypes[dt].get("fields", [])} | custom_fields.get(dt, set())
						if ia not in fields:
							warn(f"{jf.name}: {dt}.{r.get('fieldname')} insert_after '{ia}' not on v16 (field lands at end)")
		for b in bad:
			fail(b)
		if not bad:
			ok("fixture custom fields target existing DocTypes")

	# -------------------------------------------------------------- 8b selects
	section("8b. Select values in literal documents")
	bad_sel = []

	def _sel_options(dt, fn):
		d = all_doctypes.get(dt)
		if not d:
			return None
		for fld in d.get("fields", []):
			if fld.get("fieldname") == fn:
				if fld.get("fieldtype") == "Select" and fld.get("options"):
					return [o for o in fld["options"].split("\n")]
				if fld.get("fieldtype") in ("Table", "Table MultiSelect"):
					return ("table", fld.get("options"))
		return None

	def _check_dict(node, dt, where):
		for k, v in zip(node.keys, node.values):
			if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
				continue
			opt = _sel_options(dt, k.value)
			if isinstance(opt, list) and isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value:
				if v.value not in opt:
					bad_sel.append(f"{where}:{v.lineno} {dt}.{k.value} = {v.value!r} (options: {', '.join(o for o in opt if o)})")
			elif isinstance(opt, tuple):
				child = opt[1]
				elts = v.elts if isinstance(v, ast.List) else ([v.elt] if isinstance(v, ast.ListComp) else [])
				for e in elts:
					if isinstance(e, ast.Dict):
						_check_dict(e, child, where)

	for p in py_files(APP):
		try:
			tree = ast.parse(p.read_text(encoding="utf-8"))
		except SyntaxError:
			continue
		for node in ast.walk(tree):
			if isinstance(node, ast.Dict):
				for k, v in zip(node.keys, node.values):
					if isinstance(k, ast.Constant) and k.value == "doctype" and isinstance(v, ast.Constant) and v.value in all_doctypes:
						_check_dict(node, v.value, p.relative_to(ROOT))
	for b in bad_sel:
		fail(f"invalid Select value: {b}")
	if not bad_sel:
		ok("Select values in literal documents are valid options")

	# -------------------------------------------------------------- 9 js calls
	section("9. browser → server method calls")
	whitelisted = set()
	for p in py_files(APP):
		src = p.read_text(encoding="utf-8")
		if "whitelist" not in src:
			continue
		tree = ast.parse(src)
		mod = ".".join(p.relative_to(ROOT).with_suffix("").parts)
		for node in tree.body:
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				for dec in node.decorator_list:
					target = dec.func if isinstance(dec, ast.Call) else dec
					if isinstance(target, ast.Attribute) and target.attr == "whitelist":
						whitelisted.add(f"{mod}.{node.name}")
	js_re = re.compile(r'["\'`](alphax_pos_suite\.[A-Za-z0-9_.]+)["\'`]')
	missing = set()
	count = 0
	for p in list(APP.rglob("*.js")) + list(APP.rglob("*.vue")) + list(APP.rglob("*.html")):
		if "node_modules" in p.parts or "vendor" in p.parts and p.suffix == ".js" and "_js" not in p.parts:
			continue
		try:
			src = p.read_text(encoding="utf-8", errors="ignore")
		except Exception:
			continue
		# constants holding a module path, used as BASE + '.fn' / `${BASE}.fn` / M + 'fn'
		bases = dict(re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*["\'`](alphax_pos_suite\.[A-Za-z0-9_.]+)["\'`]', src))
		refs = list(js_re.findall(src))
		for var, base in bases.items():
			for fn in re.findall(r'(?:\$\{' + var + r'\}|\b' + var + r'\s*\+\s*["\'`])\.?([a-z_][A-Za-z0-9_]*)', src):
				refs.append(base.rstrip(".") + "." + fn)
		for m in refs:
			if m.endswith(".") or index.module_exists(m):
				continue
			if m.count(".") < 3 or m.endswith((".js", ".css", ".html", ".json")):
				continue
			if m.split(".")[-1][:1].isupper():
				continue
			count += 1
			if m not in whitelisted:
				if index.resolve_path(m):
					missing.add(f"{m} (exists but not whitelisted) ← {p.relative_to(ROOT)}")
				else:
					missing.add(f"{m} (missing) ← {p.relative_to(ROOT)}")
	for m in sorted(missing):
		fail(f"client calls {m}")
	if not missing:
		ok(f"{count} client method references resolve to whitelisted functions")

	# -------------------------------------------------------------- 10 security
	section("10. whitelist hygiene")
	guest = []
	ignore_perm = 0
	for p in py_files(APP):
		src = p.read_text(encoding="utf-8")
		for m in re.finditer(r"@frappe\.whitelist\(([^)]*allow_guest\s*=\s*True[^)]*)\)\s*\ndef\s+(\w+)", src):
			guest.append(f"{p.relative_to(ROOT)}::{m.group(2)}")
		ignore_perm += len(re.findall(r"ignore_permissions\s*=\s*True", src))
	ok(f"{len(whitelisted)} whitelisted methods; {len(guest)} allow guests")
	reviewed = {  # guest endpoints reviewed in v16.0.0 and the control each relies on
		"submit_qr_order": "active table token + per-token rate limit",
		"get_qr_menu": "active table token",
		"board": "outlet display key (_check)",
		"confirm_pairing": "short-lived pairing token in cache",
		"pin_signin": "bound terminal + escalating lockout",
		"signin_context": "bound terminal; returns no secrets",
		"card_payment_callback": "rate limit + HMAC secret + Pending-only",
		"qr_menu": "active table token",
		"qr_place": "active table token + 30/hour per table",
		"store": "outlet must have online ordering on",
		"place": "store open + capacity cap + 5/hour per phone, 20/hour per IP",
		"track": "random 16-char reference, no personal data, 600/hour per IP",
		"balance": "card number (Luhn) + PIN for high-value cards, PIN lockout, 10/hour per IP",
	}
	for g in guest:
		fn = g.split("::")[-1]
		if fn in reviewed:
			ok(f"guest-callable {fn}: {reviewed[fn]}")
		else:
			warn(f"guest-callable: {g} — not yet reviewed; confirm it validates a token")
	ok(f"{ignore_perm} ignore_permissions=True call sites (review list in report)")

	# -------------------------------------------------------------- result
	print()
	print(f"RESULT: {len(FAILS)} FAIL, {len(WARNS)} WARN")
	sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
	main()
