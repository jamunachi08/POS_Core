"""Recipe costing data access: valuation, prices, VAT, sales mix, commissions."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import flt

from alphax_pos_suite.alphax_pos_suite.costing import engine


def load_recipes() -> dict:
	recipes = {}
	heads = frappe.get_all("AlphaX POS Recipe", filters={"disabled": 0}, fields=["name", "item_code", "yield_qty"])
	by_name = {h.name: h for h in heads}
	for h in heads:
		recipes[h.item_code] = {"yield": flt(h.yield_qty) or 1.0, "lines": []}
	if heads:
		for r in frappe.get_all(
			"AlphaX POS Recipe Item",
			filters={"parent": ["in", list(by_name)], "parenttype": "AlphaX POS Recipe"},
			fields=["parent", "material_item", "qty", "uom", "waste_percent"],
			order_by="idx asc",
		):
			recipes[by_name[r.parent].item_code]["lines"].append(
				{"material": r.material_item, "qty": flt(r.qty), "uom": r.uom, "waste": flt(r.waste_percent)}
			)
	return recipes


class Rates:
	"""Valuation per stock UOM: outlet warehouse → company-wide → last purchase → item master."""

	def __init__(self, warehouse: str | None):
		self.warehouse = warehouse
		self.cache = {}

	def __call__(self, item: str):
		if item in self.cache:
			return self.cache[item]
		rate, src = 0.0, "none"
		if self.warehouse:
			v = frappe.db.get_value("Bin", {"item_code": item, "warehouse": self.warehouse},
			                        ["valuation_rate", "actual_qty"], as_dict=True)
			if v and flt(v.valuation_rate) > 0:
				rate, src = flt(v.valuation_rate), "outlet stock"
		if not rate:
			agg = frappe.db.sql(
				"select sum(stock_value), sum(actual_qty) from `tabBin` where item_code=%s and actual_qty > 0", item
			)
			if agg and flt(agg[0][1]) > 0 and flt(agg[0][0]) > 0:
				rate, src = flt(agg[0][0]) / flt(agg[0][1]), "company stock"
		if not rate:
			lp, vr = frappe.db.get_value("Item", item, ["last_purchase_rate", "valuation_rate"]) or (0, 0)
			if flt(lp) > 0:
				rate, src = flt(lp), "last purchase"
			elif flt(vr) > 0:
				rate, src = flt(vr), "item master"
		self.cache[item] = (rate, src)
		return self.cache[item]


_uom_cache: dict = {}


def uom_factor(item: str, uom: str | None) -> float:
	if not uom:
		return 1.0
	key = (item, uom)
	if key not in _uom_cache:
		stock_uom = frappe.get_cached_value("Item", item, "stock_uom")
		if uom == stock_uom:
			_uom_cache[key] = 1.0
		else:
			f = frappe.db.get_value("UOM Conversion Detail", {"parent": item, "parenttype": "Item", "uom": uom}, "conversion_factor")
			_uom_cache[key] = flt(f) or 1.0
	return _uom_cache[key]


def inclusive_vat_pct(template: str | None) -> float:
	if not template:
		return 0.0
	rows = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": template, "parenttype": "Sales Taxes and Charges Template", "included_in_print_rate": 1,
		         "charge_type": "On Net Total"},
		fields=["rate"],
	)
	return sum(flt(r.rate) for r in rows)


def menu_prices(price_list: str | None, items: list[str]) -> dict:
	if not price_list or not items:
		return {}
	out = {}
	for r in frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "item_code": ["in", items], "selling": 1},
		fields=["item_code", "price_list_rate", "customer", "valid_from"],
		order_by="valid_from desc",
	):
		if r.customer:
			continue
		out.setdefault(r.item_code, flt(r.price_list_rate))
	return out


def sales_mix(outlet: str, from_date, to_date) -> dict:
	"""{item: {"qty", "revenue", "by_platform": {platform: qty}}} from POS invoices, net of returns."""
	rows = frappe.db.sql(
		"""
		select sii.item_code, coalesce(si.alphax_delivery_platform, '') as platform,
			sum(sii.stock_qty) as qty, sum(sii.base_net_amount) as revenue
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.is_pos = 1 and si.alphax_outlet = %s
			and si.posting_date between %s and %s
		group by sii.item_code, platform
		""",
		(outlet, from_date, to_date),
		as_dict=True,
	)
	mix = defaultdict(lambda: {"qty": 0.0, "revenue": 0.0, "by_platform": defaultdict(float)})
	for r in rows:
		m = mix[r.item_code]
		m["qty"] += flt(r.qty)
		m["revenue"] += flt(r.revenue)
		if r.platform:
			m["by_platform"][r.platform] += flt(r.qty)
	return mix


def platforms() -> list[dict]:
	return frappe.get_all("AlphaX Delivery Platform", filters={"disabled": 0},
	                      fields=["name", "commission_percent"], order_by="name")


def cost_one(item_code: str, warehouse: str | None = None) -> engine.Costed:
	return engine.cost_item(item_code, load_recipes(), Rates(warehouse), uom_factor)
