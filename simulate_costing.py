#!/usr/bin/env python3
"""v16.2.0 — recipe costing and menu engineering checks (no Frappe needed)."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
	"engine", Path(__file__).resolve().parent / "alphax_pos_suite" / "alphax_pos_suite" / "costing" / "engine.py")
E = importlib.util.module_from_spec(spec)
sys.modules["engine"] = E
spec.loader.exec_module(E)
FAILS = []


def check(c, m):
	print(("  OK   " if c else "  FAIL ") + m)
	if not c:
		FAILS.append(m)


rates = {"BUN": (1.5, "outlet stock"), "BEEF": (40.0, "outlet stock"), "MAYO": (10.0, "last purchase"),
         "GARLIC": (12.0, "company stock"), "OIL": (8.0, "item master")}
uom = lambda m, u: 0.001 if u == "g" else 1.0  # noqa: E731
rate = lambda m: rates.get(m, (0.0, "none"))  # noqa: E731
recipes = {
	"BURGER": {"yield": 1, "lines": [
		{"material": "BUN", "qty": 1, "uom": None, "waste": 0},
		{"material": "BEEF", "qty": 150, "uom": "g", "waste": 20},     # 0.15 kg net → 0.1875 gross
		{"material": "TOUM", "qty": 0.05, "uom": None, "waste": 0},    # sub-recipe
	]},
	"TOUM": {"yield": 2, "lines": [                                   # batch makes 2 units
		{"material": "GARLIC", "qty": 0.2, "uom": None, "waste": 10},
		{"material": "OIL", "qty": 0.8, "uom": None, "waste": 0},
	]},
	"LOOP-A": {"lines": [{"material": "LOOP-B", "qty": 1}]},
	"LOOP-B": {"lines": [{"material": "LOOP-A", "qty": 1}]},
	"SALAD": {"lines": [{"material": "LETTUCE", "qty": 1}]},
}
toum = (0.2 / 0.9 * 12 + 0.8 * 8) / 2
expected = 1.5 + 0.1875 * 40 + 0.05 * toum
c = E.cost_item("BURGER", recipes, rate, uom)
check(abs(c.unit_cost - expected) < 1e-9, f"burger plate cost {c.unit_cost:.4f} = {expected:.4f} (waste, UOM, sub-recipe, batch yield)")
check([l["source"] for l in c.lines] == ["outlet stock", "outlet stock", "sub-recipe"], "cost source recorded per line")
check(E.cost_item("LOOP-A", recipes, rate, uom).warnings[0].startswith("recipe cycle"), "recipe cycle detected, not infinite")
check("no cost for LETTUCE" in E.cost_item("SALAD", recipes, rate, uom).warnings, "missing cost surfaced as a gap")

print("== VAT and channel margin ==")
net = E.net_of_vat(28.75, 15)
check(abs(net - 25.0) < 1e-9, "28.75 VAT-inclusive → 25.00 net")
m_store = net - c.unit_cost
m_hs = E.channel_margin(28.75, net, c.unit_cost, 25)
check(abs(m_hs - (m_store - 28.75 * 0.25)) < 1e-9, f"25% commission on gross: in-store {m_store:.2f} → platform {m_hs:.2f}")

print("== menu engineering (Kasavana–Smith) ==")
cls = E.classify([
	{"item": "BURGER", "qty": 400, "cm": 14}, {"item": "SHAWARMA", "qty": 380, "cm": 6},
	{"item": "TRUFFLE", "qty": 30, "cm": 30}, {"item": "SOUP", "qty": 25, "cm": 3}, {"item": "UNSOLD", "qty": 0, "cm": 50},
])
check(cls == {"BURGER": "Star", "SHAWARMA": "Plowhorse", "TRUFFLE": "Puzzle", "SOUP": "Dog"}, f"classes {cls}")
check("UNSOLD" not in cls, "unsold items are not classified")

print()
print("RESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
sys.exit(1 if FAILS else 0)
