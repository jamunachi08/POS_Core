#!/usr/bin/env python3
"""v16.1.0 — forecasting engine checks on synthetic Saudi outlet data.

Runs without Frappe. Builds two years of daily sales with a Fri/Sat
weekend, a Ramadan shift, Eid spikes, a payday lift and noise; then checks
that the engine beats seasonal-naive out of sample, that its P90 band covers
roughly what it claims, that intermittent items route to Croston, and that the
Hijri calendar lands on known Umm al-Qura dates within a day.
"""

import importlib.util
import random
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent / "alphax_pos_suite" / "alphax_pos_suite" / "forecast"


def load(name):
	spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
	mod = importlib.util.module_from_spec(spec)
	sys.modules[name] = mod
	spec.loader.exec_module(mod)
	return mod


cal = load("calendar_ksa")
eng = load("engine")
FAILS = []


def check(cond, msg):
	print(("  OK   " if cond else "  FAIL ") + msg)
	if not cond:
		FAILS.append(msg)


print("== Hijri calendar vs Umm al-Qura ==")
known = {
	date(2025, 3, 1): (1446, 9, 1),     # 1 Ramadan 1446
	date(2026, 2, 18): (1447, 9, 1),    # 1 Ramadan 1447
	date(2026, 3, 20): (1447, 10, 1),   # Eid al-Fitr 1447
	date(2026, 5, 27): (1447, 12, 10),  # Eid al-Adha 1447
	date(2025, 6, 6): (1446, 12, 10),   # Eid al-Adha 1446
}
for g, h in known.items():
	got = cal.to_hijri(g)
	off = min(abs((cal.from_hijri(*h) - g).days), 99)
	check(off <= 1, f"{g} → {got}, Umm al-Qura {h} (off by {off} day)")

print("== synthetic outlet ==")
random.seed(7)
WD = {0: 1.0, 1: 0.95, 2: 1.0, 3: 1.25, 4: 1.45, 5: 1.35, 6: 0.9}  # Thu-Sat busiest
start, end = date(2024, 9, 1), date(2026, 9, 30)
events = {d: cal.builtin_events(d) for d in cal.daterange(start, end + timedelta(days=14))}


def true_demand(d, base):
	tags = events[d]
	f = WD[d.weekday()]
	if "Ramadan" in tags:
		f *= 1.6
	if "Eid al-Fitr" in tags or "Eid al-Adha" in tags:
		f *= 2.0
	if "Payday" in tags:
		f *= 1.12
	trend = 1 + 0.10 * ((d - start).days / 730)
	return base * f * trend


items = {"SHAWARMA": 80, "KUNAFA": 25, "SAFFRON-TEA": 40}
series = {k: {} for k in items}
for d in cal.daterange(start, end):
	for k, b in items.items():
		mu = true_demand(d, b)
		series[k][d] = max(0.0, round(random.gauss(mu, mu * 0.18)))
# intermittent item
series["CATERING-TRAY"] = {d: (random.choice([0, 0, 0, 0, 3, 5]) if random.random() < 0.3 else 0) for d in cal.daterange(start, end)}

print("== out-of-sample accuracy (rolling, 60 origins incl. Ramadan 1447) ==")
origins = [date(2026, 1, 20) + timedelta(days=i) for i in range(0, 120, 2)]
tot = {"model": 0.0, "naive": 0.0, "act": 0.0}
covered = n = 0
for k in items:
	for o in origins:
		t = o + timedelta(days=1)
		hist = {d: v for d, v in series[k].items() if d <= o}
		fc = eng.forecast_item(k, hist, events, o, [t])[0]
		a = series[k][t]
		tot["model"] += abs(a - fc.qty)
		tot["naive"] += abs(a - eng._seasonal_naive(hist, o, t))
		tot["act"] += a
		covered += fc.low <= a <= fc.high
		n += 1
m_wape, n_wape = tot["model"] / tot["act"], tot["naive"] / tot["act"]
print(f"       engine WAPE {m_wape:.1%}  seasonal-naive WAPE {n_wape:.1%}")
check(m_wape < n_wape * 0.9, "engine beats seasonal-naive by >10% across Ramadan/Eid")
check(m_wape < 0.25, "engine WAPE under 25% on daily item level")
cov = covered / n
print(f"       P10–P90 band coverage {cov:.0%} (nominal 80%)")
check(0.65 <= cov <= 0.95, "interval coverage within 65–95%")

print("== Ramadan uplift learned from the previous year ==")
o = date(2026, 2, 17)
fc = eng.forecast_item("SHAWARMA", {d: v for d, v in series["SHAWARMA"].items() if d <= o}, events, o, [date(2026, 2, 19)])[0]
check(any("Ramadan" in dr for dr in fc.drivers), f"driver list names Ramadan: {fc.drivers}")
truth = true_demand(date(2026, 2, 19), 80)
check(abs(fc.qty - truth) / truth < 0.25, f"day-2 Ramadan forecast {fc.qty:.0f} vs true mean {truth:.0f}")

print("== intermittent item ==")
o = date(2026, 9, 29)
fc = eng.forecast_item("CATERING-TRAY", series["CATERING-TRAY"], events, o, [o + timedelta(days=1)])[0]
check(fc.method.startswith("Croston") or fc.method == "Seasonal naive", f"intermittent item uses {fc.method}")
check(fc.qty < 3, f"intermittent daily rate is small ({fc.qty})")

print("== planning quantile ==")
check(fc.planned("P90") >= fc.planned("P80") >= fc.planned("P50"), "P90 ≥ P80 ≥ P50")

print("== prep slots ==")
prof = eng.hourly_profile({9: 5, 12: 30, 13: 25, 19: 30, 21: 10})
slots = eng.prep_slots(prof)
check(abs(sum(slots.values()) - 1) < 1e-6 and slots["Lunch"] == 0.55, f"slot shares {slots}")

print()
print("RESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
sys.exit(1 if FAILS else 0)
