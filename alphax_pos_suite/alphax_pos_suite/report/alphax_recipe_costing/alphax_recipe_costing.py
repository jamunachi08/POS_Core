"""AlphaX Recipe Costing & Menu Engineering.

For one outlet and period, per menu item: plate cost through its recipe (sub-
recipes, yields and waste included), menu price net of inclusive VAT, food
cost %, contribution in the dining room and on each delivery platform after
its commission, quantity sold, total contribution, and the menu class.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from alphax_pos_suite.alphax_pos_suite.costing import engine
from alphax_pos_suite.alphax_pos_suite.costing import service as svc


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not f.outlet:
		frappe.throw(_("Choose an outlet."))
	to_date = getdate(f.to_date or nowdate())
	from_date = getdate(f.from_date or add_days(to_date, -29))
	outlet = frappe.get_cached_doc("AlphaX POS Outlet", f.outlet)

	recipes = svc.load_recipes()
	rates = svc.Rates(outlet.warehouse)
	mix = svc.sales_mix(outlet.name, from_date, to_date)
	plats = svc.platforms()
	vat = svc.inclusive_vat_pct(outlet.sales_taxes_and_charges_template)

	items = set(mix)
	if f.include_unsold:
		used_as_ingredient = {ln["material"] for r in recipes.values() for ln in r["lines"]}
		items |= set(recipes) - used_as_ingredient  # menu recipes, not sauces and doughs
	meta = {
		r.name: r
		for r in frappe.get_all("Item", filters={"name": ["in", list(items) or [""]]},
		                        fields=["name", "item_name", "item_group", "is_sales_item"])
	}
	if f.item_group:
		items = {i for i in items if meta.get(i) and meta[i].item_group == f.item_group}
	prices = svc.menu_prices(outlet.default_price_list, list(items))

	rows, class_input = [], []
	for item in sorted(items):
		if not meta.get(item) or not meta[item].is_sales_item:
			continue
		c = engine.cost_item(item, recipes, rates, svc.uom_factor)
		m = mix.get(item) or {"qty": 0.0, "revenue": 0.0, "by_platform": {}}
		gross = flt(prices.get(item))
		if not gross and m["qty"]:
			gross = flt(m["revenue"]) / flt(m["qty"]) * (1 + vat / 100.0)  # sold price when no list price
		net = engine.net_of_vat(gross, vat)
		cm = net - c.unit_cost
		row = {
			"item_code": item,
			"item_name": meta[item].item_name,
			"item_group": meta[item].item_group,
			"has_recipe": 1 if item in recipes else 0,
			"plate_cost": round(c.unit_cost, 4),
			"menu_price": round(gross, 2),
			"net_price": round(net, 2),
			"food_cost_pct": round(100 * c.unit_cost / net, 1) if net else None,
			"margin": round(cm, 2),
			"qty_sold": round(m["qty"], 2),
			"total_margin": round(cm * m["qty"], 2),
			"warnings": "; ".join(dict.fromkeys(c.warnings))[:300],
		}
		for p in plats:
			row[_pf(p.name)] = round(engine.channel_margin(gross, net, c.unit_cost, flt(p.commission_percent)), 2)
		rows.append(row)
		class_input.append({"item": item, "qty": m["qty"], "cm": cm})

	classes = engine.classify(class_input)
	for r in rows:
		r["menu_class"] = classes.get(r["item_code"], "Not sold")
	rows.sort(key=lambda r: -flt(r["total_margin"]))

	return _columns(plats), rows, None, _chart(rows), _summary(rows, vat)


def _pf(name: str) -> str:
	return "margin_" + frappe.scrub(name)


def _columns(plats):
	cols = [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_group", "label": _("Group"), "fieldtype": "Link", "options": "Item Group", "width": 110},
		{"fieldname": "menu_class", "label": _("Menu Class"), "fieldtype": "Data", "width": 95},
		{"fieldname": "has_recipe", "label": _("Recipe"), "fieldtype": "Check", "width": 65},
		{"fieldname": "plate_cost", "label": _("Plate Cost"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "menu_price", "label": _("Menu Price"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "net_price", "label": _("Price ex VAT"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "food_cost_pct", "label": _("Food Cost %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "margin", "label": _("Margin (in store)"), "fieldtype": "Currency", "width": 110},
	]
	for p in plats:
		cols.append({"fieldname": _pf(p.name), "label": _("Margin on {0} ({1}%)").format(p.name, flt(p.commission_percent)),
		             "fieldtype": "Currency", "width": 130})
	cols += [
		{"fieldname": "qty_sold", "label": _("Qty Sold"), "fieldtype": "Float", "width": 85},
		{"fieldname": "total_margin", "label": _("Total Margin"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "warnings", "label": _("Costing Gaps"), "fieldtype": "Data", "width": 220},
	]
	return cols


def _chart(rows):
	counts = {k: 0 for k in ("Star", "Plowhorse", "Puzzle", "Dog")}
	for r in rows:
		if r["menu_class"] in counts:
			counts[r["menu_class"]] += 1
	return {"data": {"labels": list(counts), "datasets": [{"name": _("Items"), "values": list(counts.values())}]},
	        "type": "bar", "colors": ["#1B7F79"]}


def _summary(rows, vat):
	sold = [r for r in rows if r["qty_sold"] > 0]
	rev = sum(r["net_price"] * r["qty_sold"] for r in sold)
	cost = sum(r["plate_cost"] * r["qty_sold"] for r in sold)
	gaps = sum(1 for r in rows if r["warnings"] or not r["has_recipe"])
	losing = [r for r in rows if any(k.startswith("margin_") and flt(v) < 0 for k, v in r.items())]
	return [
		{"label": _("Theoretical food cost"), "value": round(100 * cost / rev, 1) if rev else 0, "datatype": "Percent",
		 "indicator": "Green" if rev and cost / rev < 0.32 else "Orange"},
		{"label": _("Items with costing gaps"), "value": gaps, "datatype": "Int", "indicator": "Red" if gaps else "Green"},
		{"label": _("Items losing money on a platform"), "value": len(losing), "datatype": "Int",
		 "indicator": "Red" if losing else "Green"},
		{"label": _("Prices treated as VAT-inclusive at"), "value": vat, "datatype": "Percent", "indicator": "Blue"},
	]
