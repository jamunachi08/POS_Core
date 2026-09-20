"""Offline check of the process flow board's access filtering.

Stubs frappe so the two filters in ``pos/flow_api.get_flow`` can be
exercised without a bench: the per-node role list, and the real
``frappe.has_permission`` gate behind it.

The guards below are the ones worth failing a build over. In particular
guard 3: a cashier must not reach a Journal Entry card no matter what the
seeder's role rows say, because the permission check is the same one the
desk uses and role rows can only narrow the board, never widen it.
"""

import ast
import importlib.util
import os
import sys
import types

APP = "alphax_pos_suite/alphax_pos_suite"

# ---------------------------------------------------------------- stub frappe

_ROLES = []
_PERMS = {}          # doctype -> set of roles with read
_CREATE = {}         # doctype -> set of roles with create
_EXISTING_DT = set()


class _Doc(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def get(self, k, default=None):
        return dict.get(self, k, default)


frappe = types.ModuleType("frappe")
frappe.session = types.SimpleNamespace(user="sim@example.com")
frappe.get_roles = lambda u=None: list(_ROLES)
frappe.whitelist = lambda *a, **k: (lambda f: f)
frappe._ = lambda s: s
frappe.PermissionError = Exception


def _has_permission(dt, ptype="read"):
    table = _CREATE if ptype == "create" else _PERMS
    return bool(set(_ROLES) & table.get(dt, set()))


frappe.has_permission = _has_permission

_FLOW = {"stages": [], "nodes": []}


class _DB:
    def exists(self, dt, name=None):
        if dt == "DocType":
            return name in _EXISTING_DT
        return True

    def get_value(self, *a, **k):
        return "AlphaX POS End-to-End Process"

    def count(self, dt, filters=None):
        return 7


frappe.db = _DB()


def _get_all(dt, filters=None, fields=None, order_by=None, ignore_permissions=False, **k):
    if dt == "AlphaX POS Process Node":
        return [_Doc(n) for n in _FLOW["nodes"]]
    if dt == "AlphaX POS Node Role":
        parent = (filters or {}).get("parent")
        for n in _FLOW["nodes"]:
            if n["name"] == parent:
                return [_Doc({"role": r}) for r in n["_roles"]]
        return []
    return []


frappe.get_all = _get_all
frappe.get_doc = lambda dt, name=None: _Doc({
    "name": name, "flow_name": name, "flow_name_ar": "", "description": "",
    "stages": [_Doc(s) for s in _FLOW["stages"]],
})
sys.modules["frappe"] = frappe

# ------------------------------------------------- load seeder + api as data

spec = importlib.util.spec_from_file_location("seed_flow", os.path.join(APP, "seed", "process_flow.py"))
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

spec = importlib.util.spec_from_file_location("flow_api", os.path.join(APP, "pos", "flow_api.py"))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

# Build the in-memory flow from the real seeder tables.
_FLOW["stages"] = [
    {"stage_key": k, "stage_label": lbl, "stage_label_ar": ar, "lane": lane,
     "actor": actor, "sequence": seq, "colour": col}
    for k, lbl, ar, lane, actor, seq, col in seed.STAGES
]
for i, n in enumerate(seed.NODES):
    label, label_ar, stage, seq, ntype, target, view, filters, roles, desc = n
    _FLOW["nodes"].append({
        "name": f"node{i}", "node_label": label, "node_label_ar": label_ar,
        "stage_key": stage, "sequence": seq, "node_type": ntype,
        "document_type": target if ntype == "DocType" else None,
        "report_name": target if ntype == "Report" else None,
        "route_override": desc if ntype not in ("DocType", "Report") else "",
        "default_view": view, "filters_json": "", "is_erpnext_standard": 0,
        "show_count": 1 if ntype == "DocType" else 0, "icon": None,
        "description": desc if ntype in ("DocType", "Report") else "",
        "_roles": roles,
    })

_EXISTING_DT = {n["document_type"] for n in _FLOW["nodes"] if n["document_type"]}

# --------------------------------------------------------------- permissions
# Deliberately realistic: a cashier holds no Journal Entry read.
ALL_POS = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}
for dt in _EXISTING_DT:
    _PERMS[dt] = set(ALL_POS)
    _CREATE[dt] = {"AlphaX POS Manager", "System Manager"}

FINANCE = {"Journal Entry", "Payment Entry", "Period Closing Voucher", "Sales Invoice"}
for dt in FINANCE:
    _PERMS[dt] = {"Accounts Manager", "System Manager"}
    _CREATE[dt] = {"Accounts Manager", "System Manager"}
_PERMS["Sales Invoice"] |= {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager"}

ADMIN_ONLY = {"User", "Role", "Role Profile", "Activity Log", "Access Log", "Company",
              "AlphaX POS Process Flow", "AlphaX POS Process Node"}
for dt in ADMIN_ONLY:
    if dt in _PERMS:
        _PERMS[dt] = {"System Manager"}
        _CREATE[dt] = {"System Manager"}

KITCHEN = {"AlphaX POS KDS Ticket", "AlphaX POS Kitchen Station",
           "AlphaX POS Central Kitchen Request"}
for dt in KITCHEN:
    if dt in _PERMS:
        _PERMS[dt] |= {"AlphaX POS Kitchen"}

# --------------------------------------------------------------------- checks

CASES = [
    ("Cashier", ["AlphaX POS Cashier"]),
    ("Kitchen", ["AlphaX POS Kitchen"]),
    ("Supervisor", ["AlphaX POS Supervisor"]),
    ("Manager", ["AlphaX POS Manager"]),
    ("Accounts", ["Accounts Manager"]),
    ("System Manager", ["System Manager"]),
    ("No role", ["Employee"]),
]

fail = 0
seen = {}
for name, roles in CASES:
    _ROLES[:] = roles
    d = api.get_flow()
    labels = {n["node_label"] for st in d.get("stages", []) for n in st["nodes"]}
    seen[name] = labels
    print(f"{name:16s} stages={len(d.get('stages', [])):2d} nodes={len(labels):3d}"
          f" of {d.get('total_nodes', 0)}")

    # Guard 1: a role list that excludes the user must hide the node.
    for st in d.get("stages", []):
        for n in st["nodes"]:
            idx = int(n["name"].replace("node", ""))
            allowed = seed.NODES[idx][8]
            if allowed and not (set(roles) & set(allowed)):
                print(f"   !! role filter leaked: {n['node_label']}")
                fail += 1

    # Guard 2: no empty stage should survive.
    for st in d.get("stages", []):
        if not st["nodes"]:
            print(f"   !! empty stage rendered: {st['stage_key']}")
            fail += 1

    # Guard 3: permission gate, not just role rows.
    for st in d.get("stages", []):
        for n in st["nodes"]:
            dt = n.get("document_type")
            if dt and not _has_permission(dt, "read"):
                print(f"   !! permission gate leaked: {dt}")
                fail += 1

    # Guard 4: New only where create is actually held.
    for st in d.get("stages", []):
        for n in st["nodes"]:
            dt = n.get("document_type")
            if n.get("can_create") and dt and not _has_permission(dt, "create"):
                print(f"   !! New offered without create: {dt}")
                fail += 1

# Guard 5: the finance lane must not reach the floor.
for role in ("Cashier", "Kitchen"):
    for label in ("Journal Entries", "Payment Entries", "Period Closing"):
        if label in seen[role]:
            print(f"   !! {role} can see {label}")
            fail += 1

# Guard 6: a user with no AlphaX role gets nothing.
if seen["No role"]:
    print("   !! unroled user sees nodes")
    fail += 1

# Guard 7: System Manager must see strictly more than a cashier.
if not seen["Cashier"] < seen["System Manager"]:
    print("   !! cashier board is not a subset of the admin board")
    fail += 1

print()
print(f"STAGES: {len(seed.STAGES)}   NODES: {len(seed.NODES)}")
print("RESULT:", "PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(1 if fail else 0)
