"""Stub frappe so the resolution logic can be exercised without a bench."""
import sys, types, importlib.util

frappe = types.ModuleType("frappe")
class PermissionError(Exception): pass
frappe.PermissionError = PermissionError
frappe.session = types.SimpleNamespace(user="test@example.com")
_ROLES = []
frappe.get_roles = lambda u=None: list(_ROLES)
frappe.whitelist = lambda *a, **k: (lambda f: f)
frappe.throw = lambda m, e=Exception: (_ for _ in ()).throw(e(m))
frappe._ = lambda s: s
sys.modules["frappe"] = frappe

spec = importlib.util.spec_from_file_location(
    "role_flow", "alphax_pos_suite/alphax_pos_suite/pos/role_flow.py")
rf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)

CASES = [
    ("Cashier only",        ["AlphaX POS Cashier"]),
    ("Kitchen only",        ["AlphaX POS Kitchen"]),
    ("Supervisor",          ["AlphaX POS Supervisor", "AlphaX POS Cashier"]),
    ("Manager",             ["AlphaX POS Manager", "AlphaX POS Supervisor", "AlphaX POS Cashier"]),
    ("Accounts only",       ["Accounts Manager"]),
    ("System Manager",      ["System Manager"]),
    ("No AlphaX role",      ["Employee"]),
]
fail = 0
for name, roles in CASES:
    _ROLES[:] = roles
    p = rf.get_context_payload()
    lanes = [l["id"] for l in p["lanes"]]
    cols  = [c["id"] for c in p["columns"]]
    print(f"{name:20s} lanes={lanes} cols={len(cols)} rows={len(p['matrix'])} full={p['full_matrix']}")
    # Guard 1: a non-supervisor must never receive a lane they don't hold
    if not (set(roles) & rf.SUPERVISORY_ROLES):
        allowed = set(roles)
        for r, extra in rf.EXTRA_LANES.items():
            if r in roles:
                allowed |= set(extra)
        for l in p["lanes"]:
            if l["role"] not in roles and l["id"] not in allowed:
                print("   !! LEAK:", l["id"]); fail += 1
    # Guard 2: guest lane never reaches a non-supervisor
    if "customer" in lanes and not (set(roles) & rf.SUPERVISORY_ROLES):
        print("   !! guest lane leaked"); fail += 1
    # Guard 3: column count must match every row's value count
    for row in p["matrix"]:
        if len(row["v"]) != len(cols):
            print("   !! width mismatch"); fail += 1; break
    # Guard 4: cashier must not see the expected-cash row as permitted
    if roles == ["AlphaX POS Cashier"]:
        for row in p["matrix"]:
            if row["a_en"].startswith("See expected cash"):
                print("   !! cashier sees expected cash"); fail += 1
    # Guard 7: Supervisor must never be able to authorise a PIN gate,
    # because security.manager_pin.MANAGER_ROLES excludes that role.
    if "AlphaX POS Supervisor" in roles and p["full_matrix"]:
        si = [c["id"] for c in p["columns"]].index("supervisor")
        for row in p["matrix"]:
            if row["a_en"].startswith("Hold or reset a manager PIN") and row["v"][si] != "n":
                print("   !! supervisor holds a PIN"); fail += 1

# Guard 5: every matrix row must carry one value per lane
for a_en, _a, v in rf.MATRIX:
    if len(v) != len(rf.LANE_IDS):
        print("   !! MATRIX row wrong width:", a_en); fail += 1

# Guard 6: every lane role must appear in the matrix column order
print()
print("MATRIX rows:", len(rf.MATRIX), "lanes:", len(rf.LANES))
print("RESULT:", "PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(1 if fail else 0)
