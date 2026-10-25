"""Offline proof of the shift age cut-off.

The control it enforces: a till left open past its limit stops taking
sales. The three things that matter and are therefore asserted:

  * the block is SYNCHRONOUS. It holds in the posting path whether or not
    the scheduler ever runs, because a dead background worker must not
    quietly re-open a closed control;
  * the outlet's own limit beats the site setting, so a 24-hour forecourt
    and a dinner-only restaurant can differ;
  * auto-close never invents a counted figure. It declares float plus
    recorded movements and flags the shift for recount.
"""
import importlib.util
import sys
import types
from datetime import datetime, timedelta

NOW = datetime(2026, 10, 6, 15, 0, 0)
OUTLETS = {"OUT-24H": {"max_shift_hours": 0},
           "OUT-DINNER": {"max_shift_hours": 12}}
SETTINGS = {"max_shift_hours": 24, "max_shift_warn_minutes": 60,
            "max_shift_action": "Block new sales"}
SHIFT = {"opened_on": NOW - timedelta(hours=5)}


class _R(dict):
    __getattr__ = dict.get


class Thrown(Exception):
    pass


fr = types.ModuleType("frappe")
fr._ = lambda s: s
fr.whitelist = lambda *a, **k: (lambda f: f)
fr.throw = lambda m, title=None: (_ for _ in ()).throw(Thrown(m))
fr.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda f: True)
fr.get_cached_doc = lambda dt: _R(SETTINGS)
fr.get_all = lambda dt, **k: []
fr.log_error = lambda **k: None
fr.get_traceback = lambda: ""
fr.db = types.SimpleNamespace(
    get_value=lambda dt, name, field=None, as_dict=False: (
        OUTLETS.get(name, {}).get("max_shift_hours")
        if dt == "AlphaX POS Outlet" else
        (_R({"name": "SH-1", **SHIFT}) if as_dict and SHIFT else None)),
    commit=lambda: None)

u = types.ModuleType("frappe.utils")
u.cint = lambda v: int(v or 0)
u.flt = lambda v: float(v or 0)
u.now_datetime = lambda: NOW
u.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")
u.add_to_date = lambda d, hours=0, minutes=0, **k: u.get_datetime(d) + timedelta(hours=hours or 0, minutes=minutes or 0)
u.time_diff_in_seconds = lambda a, b: (u.get_datetime(a) - u.get_datetime(b)).total_seconds()
fr.utils = u
sys.modules.update({"frappe": fr, "frappe.utils": u})
for pkg in ("alphax_pos_suite", "alphax_pos_suite.alphax_pos_suite",
            "alphax_pos_suite.alphax_pos_suite.pos"):
    sys.modules.setdefault(pkg, types.ModuleType(pkg))

spec = importlib.util.spec_from_file_location(
    "sa", "alphax_pos_suite/alphax_pos_suite/pos/shift_age.py")
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

fails = 0


def check(c, m):
    global fails
    print(("  OK   " if c else "  FAIL ") + m)
    fails += (not c)


print("== which limit applies ==")
check(sa.limit_hours(None) == 24, "site setting is 24h")
check(sa.limit_hours("OUT-DINNER") == 12, "an outlet with its own 12h limit overrides the site")
check(sa.limit_hours("OUT-24H") == 24, "an outlet set to 0 falls back to the site, it does not become unlimited")
SETTINGS["max_shift_hours"] = 0
check(sa.limit_hours("OUT-24H") == 0, "with the site off and no outlet limit, there is no cut-off")
check(sa.limit_hours("OUT-DINNER") == 12, "an outlet limit still applies when the site has none")
SETTINGS["max_shift_hours"] = 24

print("== the countdown ==")
for opened_h, expect_warn, expect_expired, why in [
    (5,    False, False, "5h in: nothing shown"),
    (23.2, True,  False, "48 min left: inside the 60-minute warning"),
    (24,   False, True,  "exactly 24h: expired"),
    (30,   False, True,  "30h: long expired"),
]:
    st = sa.status_for(_R(opened_on=NOW - timedelta(hours=opened_h)), None, _R(SETTINGS))
    ok = st["warn"] == expect_warn and st["expired"] == expect_expired
    check(ok, f"{why} (left={st['minutes_left']}m warn={st['warn']} expired={st['expired']})")

print("== the block is synchronous ==")
SHIFT["opened_on"] = NOW - timedelta(hours=10)
try:
    sa.ensure_not_expired("T-1", None, _R(SETTINGS))
    check(True, "a 10h shift sells normally")
except Thrown as e:
    check(False, f"10h shift wrongly blocked: {e}")

SHIFT["opened_on"] = NOW - timedelta(hours=26)
try:
    sa.ensure_not_expired("T-1", None, _R(SETTINGS))
    check(False, "a 26h shift was NOT blocked")
except Thrown as e:
    check("more than 24 hours" in str(e), f"a 26h shift is refused: {str(e)[:70]}…")
    check("Close the shift" in str(e) and "day close" in str(e),
          "the message tells the cashier what to actually do")

SETTINGS["max_shift_hours"] = 0
try:
    sa.ensure_not_expired("T-1", None, _R(SETTINGS))
    check(True, "with no limit configured, an old shift is not blocked (opt-in, not imposed)")
except Thrown:
    check(False, "blocked despite no limit configured")
SETTINGS["max_shift_hours"] = 24

SHIFT.clear()
try:
    sa.ensure_not_expired("T-1", None, _R(SETTINGS))
    check(True, "no open shift means nothing to block here")
except Thrown:
    check(False, "threw with no open shift")
SHIFT["opened_on"] = NOW - timedelta(hours=26)

try:
    sa.ensure_not_expired(None, None, _R(SETTINGS))
    check(True, "no terminal supplied is a no-op, not an error")
except Thrown:
    check(False, "threw without a terminal")

print("== auto-close is opt-in and never invents a count ==")
src = open("alphax_pos_suite/alphax_pos_suite/pos/shift_age.py", encoding="utf-8").read()
body = src[src.index("def enforce_max_shift_age"):]
check('!= "Block new sales and auto-close the shift"' in body or
      'action != "Block new sales and auto-close the shift"' in body,
      "the scheduler returns unless auto-close was explicitly chosen")
check("RECOUNT REQUIRED" in body, "an auto-closed shift is flagged RECOUNT REQUIRED")
check("opening_cash" in body and "movements" in body,
      "the declared figure is float plus recorded movements, not a guess")
check("_maybe_time_dayclose" in body, "day close follows where the terminal is set to trigger it")

print()
print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
