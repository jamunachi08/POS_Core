"""Offline proof of the 86 list and the PIN sign-in cage.

Two rules with real consequences:

  * an item the kitchen has taken off must LEAVE the till payload, not be
    greyed out. A disabled tile still gets tapped;
  * a PIN sign-in must fail closed. Disabled setting, unknown terminal,
    wrong PIN and short PIN must all return the same shape, and five
    failures must lock the terminal.
"""
import importlib.util
import sys
import types
from datetime import datetime, timedelta

AVAIL = []          # rows of AlphaX POS Item Availability
CACHE = {}
SETTINGS = {"pin_signin_enabled": 1}
TERMINALS = {"T-1": {"name": "T-1", "pos_outlet": "OUT", "disabled": 0}}
PINS = []           # {name, user, pin_hash, is_active}
ROLES = {"cashier@x.com": ["AlphaX POS Cashier"], "nobody@x.com": ["Employee"]}
LOGGED_IN = []


class _R(dict):
    __getattr__ = dict.get


fr = types.ModuleType("frappe")
fr._ = lambda s: s
fr.whitelist = lambda *a, **k: (lambda f: f)
fr.PermissionError = Exception


class Thrown(Exception):
    pass


fr.throw = lambda m, e=None: (_ for _ in ()).throw(Thrown(m))
fr.get_roles = lambda u=None: ROLES.get(u, ["System Manager"]) if u else ["System Manager"]
fr.session = types.SimpleNamespace(user="mgr@x.com")
fr.publish_realtime = lambda *a, **k: None
fr.log_error = lambda **k: None
fr.get_traceback = lambda: ""


class Cache:
    def get_value(self, k): return CACHE.get(k)
    def set_value(self, k, v, expires_in_sec=None): CACHE[k] = v
    def delete_value(self, k): CACHE.pop(k, None)


fr.cache = lambda: Cache()


class DB:
    def exists(self, dt, name=None):
        if dt == "DocType":
            return True
        if dt == "AlphaX POS Terminal":
            return name in TERMINALS
        if dt == "User":
            return name in ROLES
        return True

    def get_value(self, dt, name, field=None, as_dict=False, order_by=None):
        if dt == "AlphaX POS Terminal":
            row = TERMINALS.get(name if isinstance(name, str) else "")
            return _R(row) if (row and as_dict) else (row or {}).get(field) if row else None
        if dt == "User":
            return 1 if field == "enabled" else "Test User"
        if dt == "AlphaX POS Outlet":
            return "OUT"
        return None

    def get_single_value(self, dt, f): return SETTINGS.get(f)
    def set_value(self, *a, **k): return None
    def commit(self): return None


fr.db = DB()
fr.get_all = lambda dt, filters=None, fields=None, **k: (
    [_R(r) for r in PINS if r.get("is_active")] if dt == "AlphaX POS Manager PIN"
    else [_R(r) for r in AVAIL
          if r["outlet"] == (filters or {}).get("outlet")
          and r["status"] in (filters or {}).get("status", ["in", []])[1]]
    if dt == "AlphaX POS Item Availability"
    else [_R(name=i, item_name=i.title()) for i in
          (filters or {}).get("name", ["in", []])[1]] if dt == "Item" else [])
fr.get_doc = lambda *a, **k: _R()
fr.new_doc = lambda dt: _R()
fr.local = types.SimpleNamespace(
    request=None,
    login_manager=types.SimpleNamespace(
        login_as=lambda u: LOGGED_IN.append(u),
        run_trigger=lambda *a: None, resume=True))

u = types.ModuleType("frappe.utils")
u.cint = lambda v: int(v or 0)
u.now_datetime = lambda: datetime(2026, 10, 5, 19, 0, 0)
u.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.strptime(
    str(v)[:19], "%Y-%m-%d %H:%M:%S")
u.add_to_date = lambda d, minutes=0, **k: u.get_datetime(d) + timedelta(minutes=minutes)
fr.utils = u
sys.modules.update({"frappe": fr, "frappe.utils": u})

APP = "alphax_pos_suite/alphax_pos_suite"


def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod] = m
    spec.loader.exec_module(m)
    return m


# manager_pin is imported by staff_pin; stub only the four helpers it uses
mp = types.ModuleType("alphax_pos_suite.alphax_pos_suite.security.manager_pin")
mp._audit_log = lambda **k: None
mp._hash_pin = lambda pin: "H:" + pin
mp._verify_pin_hash = lambda pin, h: h == "H:" + pin
mp._validate_pin_format = lambda pin: None
sys.modules[mp.__name__] = mp
for pkg in ("alphax_pos_suite", "alphax_pos_suite.alphax_pos_suite",
            "alphax_pos_suite.alphax_pos_suite.security"):
    sys.modules.setdefault(pkg, types.ModuleType(pkg))

av = load("av", f"{APP}/pos/availability.py")
sp = load("sp", f"{APP}/security/staff_pin.py")

fails = 0


def check(c, m):
    global fails
    print(("  OK   " if c else "  FAIL ") + m)
    fails += (not c)


print("== 86 list ==")
AVAIL[:] = [
    {"outlet": "OUT", "item": "SALMON", "status": "Off", "reason": "Deliveries missed", "until": None},
    {"outlet": "OUT", "item": "LAMB", "status": "Low", "reason": "4 portions left", "until": None},
    {"outlet": "OUT", "item": "SOUP", "status": "Off", "reason": "", "until": "2026-10-05 18:00:00"},
]
m = av.current_map("OUT")
check("SALMON" in m and m["SALMON"]["status"] == "Off", "an item taken off appears as Off")
check("LAMB" in m and m["LAMB"]["status"] == "Low", "a low item appears as Low")
check("SOUP" not in m, "a hold that expired at 18:00 is already back on at 19:00, without the scheduler")
check(av.current_map(None) == {}, "no outlet means no 86 list, not every outlet's")

rows = [{"item_code": c} for c in ("SALMON", "LAMB", "STEAK")]
kept = [r for r in rows if m.get(r["item_code"], {}).get("status") != "Off"]
check([r["item_code"] for r in kept] == ["LAMB", "STEAK"],
      f"menu drops Off items entirely -> {[r['item_code'] for r in kept]}")
check(m.get("LAMB", {}).get("reason") == "4 portions left", "the kitchen's reason reaches the till")

print("== PIN sign-in fails closed ==")
PINS[:] = [{"name": "P1", "user": "cashier@x.com", "pin_hash": "H:4821", "is_active": 1},
           {"name": "P2", "user": "nobody@x.com", "pin_hash": "H:9999", "is_active": 1}]

SETTINGS["pin_signin_enabled"] = 0
r = sp.pin_signin("T-1", "4821")
check(not r["ok"] and not LOGGED_IN, "disabled setting refuses even a correct PIN")
SETTINGS["pin_signin_enabled"] = 1

CACHE.clear()
r = sp.pin_signin("NOT-A-TERMINAL", "4821")
check(not r["ok"] and r["message"] == "Wrong PIN.",
      "an unknown terminal gets the same message as a wrong PIN (no probing)")

CACHE.clear()
r = sp.pin_signin("T-1", "12")
check(not r["ok"] and not LOGGED_IN, "a 2-digit PIN is refused")

CACHE.clear()
r = sp.pin_signin("T-1", "9999")
check(not r["ok"] and not LOGGED_IN,
      "a correct PIN held by someone with no POS role does not sign in")

CACHE.clear()
r = sp.pin_signin("T-1", "4821")
check(r["ok"] and LOGGED_IN == ["cashier@x.com"], f"a valid cashier PIN signs in -> {LOGGED_IN}")

print("== lockout ==")
CACHE.clear()
LOGGED_IN.clear()
res = [sp.pin_signin("T-1", "0000") for _ in range(5)]
check(all(not x["ok"] for x in res), "five wrong PINs all refused")
check(res[-1].get("locked") and res[-1].get("retry_in", 0) > 0,
      f"the fifth locks the terminal for {res[-1].get('retry_in')}s")
blocked = sp.pin_signin("T-1", "4821")
check(not blocked["ok"] and blocked.get("locked"),
      "while locked, even the CORRECT PIN is refused — brute force cannot outrun it")
sp.clear_terminal_lockout("T-1")
after = sp.pin_signin("T-1", "4821")
check(after["ok"], "a manager can clear the lockout and the till works again")

print("== context leaks nothing ==")
CACHE.clear()
ctx = sp.signin_context("T-1")
check(set(ctx) == {"enabled", "terminal", "outlet", "locked_for"},
      f"context keys = {sorted(ctx)}")
check(not any("user" in str(k).lower() or "pin" in str(k).lower() for k in ctx),
      "no user list and no PIN hint reach an unauthenticated screen")

print()
print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
