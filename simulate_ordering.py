#!/usr/bin/env python3
"""v16.3.0 — guest ordering rules and wiring checks (no Frappe needed)."""

import ast
import importlib.util
import json
import sys
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "alphax_pos_suite" / "alphax_pos_suite"
spec = importlib.util.spec_from_file_location("rules", APP / "ordering" / "rules.py")
R = importlib.util.module_from_spec(spec)
sys.modules["rules"] = R
spec.loader.exec_module(R)
FAILS = []


def check(c, m):
	print(("  OK   " if c else "  FAIL ") + m)
	if not c:
		FAILS.append(m)


print("== trading hours ==")
check(R.within_hours(time(10), time(23), time(12)), "inside a same-day window")
check(not R.within_hours(time(10), time(23), time(23, 30)), "after closing")
check(R.within_hours(time(18), time(2), time(1, 30)), "past-midnight window, after midnight")
check(not R.within_hours(time(18), time(2), time(9)), "past-midnight window, morning")
check(R.within_hours(None, None, time(4)), "no hours set: always open")

print("== phone numbers ==")
check(R.valid_phone("05 5123 4567"), "local mobile with spaces")
check(R.valid_phone("00966551234567") and R.normalise_phone("00966551234567") == "+966551234567", "00 prefix normalised to +")
check(not R.valid_phone("12345"), "too short rejected")
check(not R.valid_phone("call me"), "text rejected")

print("== wiring ==")
order = json.loads((APP / "doctype/alphax_pos_order/alphax_pos_order.json").read_text())
fields = {f["fieldname"]: f for f in order["fields"]}
reqd = {f for f, d in fields.items() if d.get("reqd")}
src = (APP / "ordering/queue.py").read_text()
for f in sorted(reqd - {"items"}):
	check(f"order.{f} =" in src, f"create_order sets required field {f}")
qs = fields["queue_status"]["options"].split("\n")
for s in ("New", "In Kitchen", "Ready", "Completed", "Settled", "Rejected", "Cancelled"):
	check(s in qs, f"queue status {s} exists")
kot = (APP / "pos/kot_api.py").read_text()
check('"status": "Queued"' in kot and "routing = _routing_table(outlet)" in kot, "kitchen rows use Queued; routing table no longer shadows the dine-in table")
check("frappe.db.exists(\"AlphaX POS KDS Ticket\", {\"pos_order\": linked})" in kot, "settling a queued order does not cook it twice")
hooks = (ROOT / "alphax_pos_suite/hooks.py").read_text()
check("ordering.queue.on_ticket_update" in hooks and "/shop/<slug>" in hooks and "/track/<ref>" in hooks, "hooks: KDS ready signal and guest routes")
pub = ast.parse((APP / "ordering/public.py").read_text())
guest = [n.name for n in pub.body if isinstance(n, ast.FunctionDef) and any("allow_guest" in ast.unparse(d) for d in n.decorator_list)]
for fn in guest:
	body = ast.unparse(next(n for n in pub.body if isinstance(n, ast.FunctionDef) and n.name == fn))
	check(any(k in body for k in ("_limit(", "_token(", "_store(")), f"guest endpoint {fn} is bounded by a token, store check or rate limit")

print()
print("RESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
sys.exit(1 if FAILS else 0)
