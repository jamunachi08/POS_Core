"""Offline proof of the table-booking rules.

Two things decide whether a service runs or falls over, and both are
enforced in the controller rather than the UI, because the timeline is not
the only door into a reservation:

  * a table may not hold two live bookings whose windows overlap, INCLUDING
    the turnaround minutes the outlet needs to clear and reset it;
  * a party may not be seated at a table that cannot hold it.

Cancelled and No Show bookings must be invisible to both, so releasing a
table is a status change and the history survives.
"""
import importlib.util
import sys
import types
from datetime import datetime, timedelta

TABLES = {
    "T1": {"name": "T1", "table_code": "T1", "seats": 2,  "outlet": "OUT", "status": "Free",
           "floor": "Ground", "readiness": "Ready", "min_party_size": 0, "max_party_size": 0},
    "T2": {"name": "T2", "table_code": "T2", "seats": 4,  "outlet": "OUT", "status": "Free",
           "floor": "Ground", "readiness": "Ready", "min_party_size": 0, "max_party_size": 4},
    "T3": {"name": "T3", "table_code": "T3", "seats": 8,  "outlet": "OUT", "status": "Free",
           "floor": "Terrace", "readiness": "Ready", "min_party_size": 4, "max_party_size": 8},
    "T4": {"name": "T4", "table_code": "T4", "seats": 6,  "outlet": "OUT", "status": "Disabled",
           "floor": "Terrace", "readiness": "Out of Service", "min_party_size": 0, "max_party_size": 6},
}
RES = []          # live bookings, filled per case
DATE = "2026-10-02"


class _R(dict):
    __getattr__ = dict.get


fr = types.ModuleType("frappe")
fr._ = lambda s: s
fr.whitelist = lambda *a, **k: (lambda f: f)
fr.PermissionError = Exception
fr.get_roles = lambda u=None: ["System Manager"]


class Thrown(Exception):
    pass


def _throw(msg, exc=None):
    raise Thrown(msg)


fr.throw = _throw


class DB:
    def get_value(self, dt, name, field=None, as_dict=False, order_by=None):
        if dt == "AlphaX POS Table":
            row = TABLES.get(name if isinstance(name, str) else "", {})
            if as_dict:
                return _R({k: row.get(k) for k in (field or [])})
            return row.get(field)
        return None


fr.db = DB()
fr.get_all = lambda dt, filters=None, fields=None, order_by=None, ignore_permissions=False, **k: (
    sorted([_R(r) for r in RES
            if r["table"] == (filters or {}).get("table")
            and r["status"] in ("Booked", "Seated")
            and r["name"] != ((filters or {}).get("name") or ["", ""])[1]],
           key=lambda r: r["from_time"])
    if dt == "AlphaX POS Table Reservation" else
    [_R(t) for t in TABLES.values() if t["status"] != "Disabled"]
    if dt == "AlphaX POS Table" else [])
fr.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda f: False)

utils = types.ModuleType("frappe.utils")
utils.cint = lambda v: int(v or 0)
utils.flt = lambda v: float(v or 0)
utils.getdate = lambda d=None: str(d)[:10]
utils.get_time = lambda t: t
utils.now_datetime = lambda: datetime.now()
utils.get_datetime = lambda v: (v if isinstance(v, datetime)
                                else datetime.strptime(str(v)[:19].replace("T", " "),
                                                       "%Y-%m-%d %H:%M:%S"))


def _add(dt, minutes=0, hours=0):
    return utils.get_datetime(dt) + timedelta(minutes=minutes or 0, hours=hours or 0)


utils.add_to_date = _add
utils.time_diff_in_seconds = lambda a, b: (utils.get_datetime(a) - utils.get_datetime(b)).total_seconds()
fr.utils = utils
model = types.ModuleType("frappe.model")
doc_mod = types.ModuleType("frappe.model.document")


class Document:
    pass


doc_mod.Document = Document
sys.modules.update({"frappe": fr, "frappe.utils": utils,
                    "frappe.model": model, "frappe.model.document": doc_mod})

P = ("alphax_pos_suite/alphax_pos_suite/doctype/alphax_pos_table_reservation/"
     "alphax_pos_table_reservation.py")
spec = importlib.util.spec_from_file_location("res", P)
res = importlib.util.module_from_spec(spec)
spec.loader.exec_module(res)

fails = 0


def check(cond, msg):
    global fails
    print(("  OK   " if cond else "  FAIL ") + msg)
    fails += (not cond)


def book(name, table, start, minutes=90, status="Booked", guest="Guest"):
    RES.append({"name": name, "table": table, "guest_name": guest,
                "from_time": start + ":00", "duration_minutes": minutes,
                "to_time": (utils.get_datetime(f"{DATE} {start}:00")
                            + timedelta(minutes=minutes)).strftime("%H:%M:%S"),
                "covers": 2, "status": status, "vip": 0})


print("== overlap, with a 10-minute turnaround ==")
RES.clear()
book("R1", "T2", "19:00", 90)                       # 19:00 – 20:30

cases = [
    ("18:00", 60, True,  "ends 19:00, straight into R1 — too tight"),
    ("17:30", 60, False, "ends 18:30, half an hour clear — fine"),
    ("20:30", 60, True,  "starts the moment R1 ends — no time to reset"),
    ("20:40", 60, False, "starts 10 min after R1 — exactly the turnaround"),
    ("19:45", 60, True,  "starts inside R1 — overlap"),
    ("19:00", 90, True,  "identical window — overlap"),
]
for start, mins, expect_clash, why in cases:
    got = res.first_clash("T2", DATE, start + ":00", mins) is not None
    check(got == expect_clash, f"{start} for {mins}m -> {'refused' if got else 'allowed'} ({why})")

print("== a released table frees up ==")
RES.clear()
book("R2", "T2", "19:00", 90, status="Cancelled")
check(res.first_clash("T2", DATE, "19:00:00", 90) is None, "a Cancelled booking blocks nothing")
RES.clear()
book("R3", "T2", "19:00", 90, status="No Show")
check(res.first_clash("T2", DATE, "19:00:00", 90) is None, "a No Show blocks nothing")
RES.clear()
book("R4", "T2", "19:00", 90, status="Seated")
check(res.first_clash("T2", DATE, "19:30:00", 60) is not None, "a Seated party still blocks the table")

print("== editing a booking does not clash with itself ==")
RES.clear()
book("R5", "T2", "19:00", 90)
check(res.first_clash("T2", DATE, "19:00:00", 120, exclude="R5") is None,
      "extending R5 from 90 to 120 min is allowed")

print("== party size ==")
RES.clear()
doc = res.AlphaXPOSTableReservation()
for table, covers, ok, why in [
    ("T2", 4, True,  "4 at a table for 4"),
    ("T2", 5, False, "5 at a table for 4"),
    ("T1", 3, False, "3 at a 2-top (seats used as the cap)"),
    ("T3", 2, False, "2 at the 8-top held for parties of 4+"),
    ("T3", 6, True,  "6 at the 8-top"),
]:
    doc.__dict__.update({"table": table, "covers": covers, "outlet": "OUT",
                         "name": "NEW", "reservation_date": DATE})
    try:
        doc._check_party_size()
        got = True
    except Thrown:
        got = False
    check(got == ok, f"{why} -> {'allowed' if got else 'refused'}")

print("== window padding is symmetric ==")
s, e = res.window(DATE, "19:00:00", 90, pad=10)
check(s.strftime("%H:%M") == "18:50" and e.strftime("%H:%M") == "20:40",
      f"90 min from 19:00 padded by 10 = {s:%H:%M}–{e:%H:%M}")

print()
print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
