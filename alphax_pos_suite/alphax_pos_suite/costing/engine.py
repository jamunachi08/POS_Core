"""Recipe costing and menu engineering — pure functions, testable without Frappe.

* Costs a menu item through its recipe, including sub-recipes (a sauce or a
  dough that has its own recipe), batch yields and trim/cooking waste.
* Detects recipe cycles instead of recursing forever.
* Classifies the menu with the Kasavana–Smith matrix: popularity against 70%
  of an even share of the mix, contribution margin against the mix-weighted
  average — Star, Plowhorse, Puzzle, Dog.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_DEPTH = 6


@dataclass
class Costed:
	item: str
	unit_cost: float
	lines: list[dict] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)


def cost_item(item, recipes, rate_of, uom_factor, _path=()) -> Costed:
	"""recipes: {item: {"yield": float, "lines": [{"material","qty","uom","waste"}]}}
	rate_of(material) -> (rate per stock uom, source label)
	uom_factor(material, uom) -> stock-uom quantity in one `uom`
	"""
	if item in _path:
		return Costed(item, 0.0, warnings=[f"recipe cycle: {' → '.join(_path + (item,))}"])
	if len(_path) > MAX_DEPTH:
		return Costed(item, 0.0, warnings=[f"recipe nesting deeper than {MAX_DEPTH} at {item}"])
	rec = recipes.get(item)
	if not rec:
		rate, src = rate_of(item)
		return Costed(item, rate, warnings=[] if rate else [f"no cost for {item}"], lines=[{"source": src}])
	yld = rec.get("yield") or 1.0
	total, lines, warns = 0.0, [], []
	for ln in rec.get("lines") or []:
		mat = ln["material"]
		qty_stock = (ln.get("qty") or 0.0) * uom_factor(mat, ln.get("uom"))
		waste = min(max(ln.get("waste") or 0.0, 0.0), 95.0)
		gross_qty = qty_stock / (1 - waste / 100.0)
		if mat in recipes:
			sub = cost_item(mat, recipes, rate_of, uom_factor, _path + (item,))
			rate, src = sub.unit_cost, "sub-recipe"
			warns += sub.warnings
		else:
			rate, src = rate_of(mat)
			if not rate:
				warns.append(f"no cost for {mat}")
		amount = gross_qty * rate
		total += amount
		lines.append({"material": mat, "net_qty": round(qty_stock, 6), "gross_qty": round(gross_qty, 6),
		              "waste_percent": waste, "rate": round(rate, 6), "source": src, "amount": round(amount, 6)})
	return Costed(item, total / yld, lines, warns)


def classify(rows: list[dict]) -> dict[str, str]:
	"""rows: [{"item", "qty", "cm"}] for one outlet and period → {item: class}."""
	sold = [r for r in rows if (r.get("qty") or 0) > 0]
	n = len(sold)
	total_qty = sum(r["qty"] for r in sold)
	if not n or not total_qty:
		return {}
	pop_threshold = 0.7 * (1.0 / n)
	avg_cm = sum(r["qty"] * r["cm"] for r in sold) / total_qty
	out = {}
	for r in sold:
		popular = r["qty"] / total_qty >= pop_threshold
		profitable = r["cm"] >= avg_cm
		out[r["item"]] = ("Star" if profitable else "Plowhorse") if popular else ("Puzzle" if profitable else "Dog")
	return out


def net_of_vat(price: float, inclusive_rate_pct: float) -> float:
	return price / (1 + inclusive_rate_pct / 100.0) if inclusive_rate_pct else price


def channel_margin(gross_price: float, net_price: float, cost: float, commission_pct: float) -> float:
	"""Contribution after an aggregator's commission (charged on the gross price)."""
	return net_price - gross_price * commission_pct / 100.0 - cost
