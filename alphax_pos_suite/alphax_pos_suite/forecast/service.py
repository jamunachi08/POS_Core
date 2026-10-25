"""Demand planner service — reads posted sales, writes forecasts and prep plans.

All computation happens inside this site's own workers. Nothing here sends
sales data anywhere; the optional briefing writer (``ai.py``) receives only
item names, quantities and calendar tags, and only on an allowed network.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from alphax_pos_suite.alphax_pos_suite.forecast import calendar_ksa as cal
from alphax_pos_suite.alphax_pos_suite.forecast import engine

SETTINGS = "AlphaX POS Forecast Settings"
SLOTS = ("Morning", "Lunch", "Evening")


# ------------------------------------------------------------------ settings


def settings():
	s = frappe.get_cached_doc(SETTINGS)
	return frappe._dict(
		enabled=cint(s.get("enabled")),
		horizon=max(cint(s.get("horizon_days")) or 7, 1),
		history=max(cint(s.get("history_days")) or 400, 56),
		min_history=max(cint(s.get("min_history_days")) or 28, 14),
		plan_to=s.get("plan_to") or "P80",
		min_item_qty=flt(s.get("min_item_qty")) if s.get("min_item_qty") is not None else 0.5,
		mr_type=s.get("material_request_type") or "Material Transfer",
		source_warehouse=s.get("source_warehouse"),
		doc=s,
	)


# ------------------------------------------------------------------ data


def _hour_expr():
	return "extract(hour from si.posting_time)" if frappe.db.db_type == "postgres" else "hour(si.posting_time)"


def load_daily_sales(outlet: str, start, end) -> dict[str, dict]:
	"""{item_code: {date: qty}} from submitted POS invoices; returns net off."""
	rows = frappe.db.sql(
		"""
		select sii.item_code, si.posting_date as d, sum(sii.stock_qty) as qty
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.is_pos = 1
			and si.alphax_outlet = %(outlet)s
			and si.posting_date between %(start)s and %(end)s
		group by sii.item_code, si.posting_date
		""",
		{"outlet": outlet, "start": start, "end": end},
		as_dict=True,
	)
	out: dict[str, dict] = defaultdict(dict)
	for r in rows:
		out[r.item_code][getdate(r.d)] = max(flt(r.qty), 0.0)
	return out


def load_slot_shares(outlet: str, end, days: int = 56) -> tuple[dict[str, dict], dict]:
	"""Per-item and outlet-wide share of daily demand by prep slot."""
	rows = frappe.db.sql(
		f"""
		select sii.item_code, {_hour_expr()} as h, sum(sii.stock_qty) as qty
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.is_pos = 1 and si.is_return = 0
			and si.alphax_outlet = %(outlet)s
			and si.posting_date between %(start)s and %(end)s
		group by sii.item_code, h
		""",
		{"outlet": outlet, "start": add_days(end, -days), "end": end},
		as_dict=True,
	)
	per_item: dict[str, dict[int, float]] = defaultdict(dict)
	overall: dict[int, float] = defaultdict(float)
	for r in rows:
		h = cint(r.h)
		per_item[r.item_code][h] = per_item[r.item_code].get(h, 0.0) + flt(r.qty)
		overall[h] += flt(r.qty)
	outlet_slots = engine.prep_slots(engine.hourly_profile(overall))
	item_slots = {}
	for item, hours in per_item.items():
		item_slots[item] = (
			engine.prep_slots(engine.hourly_profile(hours)) if sum(hours.values()) >= 30 else outlet_slots
		)
	return item_slots, outlet_slots


def events_between(outlet: str, start, end):
	"""{date: set(tags)} plus priors {tag: multiplier} and closure dates."""
	by_day = {d: cal.builtin_events(d) for d in cal.daterange(getdate(start), getdate(end))}
	priors: dict[str, float] = {}
	closures = set()
	rows = frappe.get_all(
		"AlphaX POS Calendar Event",
		filters={"to_date": [">=", start], "from_date": ["<=", end]},
		or_filters=[["outlet", "=", outlet], ["outlet", "is", "not set"]],
		fields=["event_type", "from_date", "to_date", "expected_uplift_pct"],
	)
	confirmed = {"Ramadan", "Last 10 Nights", "Eid al-Fitr", "Eid al-Adha"}
	for r in rows:
		days = list(cal.daterange(getdate(r.from_date), getdate(r.to_date)))
		if r.event_type in confirmed:
			# Confirmed dates replace the computed ones for that event.
			for d in by_day:
				if abs((d - days[0]).days) <= 3 or abs((d - days[-1]).days) <= 3:
					by_day[d].discard(r.event_type)
		for d in days:
			if d in by_day:
				if r.event_type == "Closure":
					closures.add(d)
				else:
					by_day[d].add(r.event_type)
		if r.expected_uplift_pct not in (None, 0) and r.event_type != "Closure":
			priors[r.event_type] = max(0.0, 1 + flt(r.expected_uplift_pct) / 100)
	return by_day, priors, closures


def active_outlets(days: int = 60) -> list[str]:
	return frappe.db.sql_list(
		"""
		select distinct alphax_outlet from `tabSales Invoice`
		where docstatus = 1 and is_pos = 1 and coalesce(alphax_outlet, '') != ''
			and posting_date >= %s
		""",
		add_days(nowdate(), -days),
	)


# ------------------------------------------------------------------ forecast


def generate_for_outlet(outlet: str, with_briefing: bool = True) -> dict:
	s = settings()
	today = getdate(nowdate())
	history_end = add_days(today, -1)
	history_start = add_days(history_end, -s.history)
	targets = [add_days(today, i) for i in range(s.horizon)]

	sales = load_daily_sales(outlet, history_start, history_end)
	events, priors, closures = events_between(outlet, history_start, targets[-1])
	item_slots, outlet_slots = load_slot_shares(outlet, history_end)

	per_target: dict = defaultdict(list)
	recent_from = add_days(history_end, -55)
	for item, raw in sales.items():
		if not raw:
			continue
		first = min(raw)
		if (history_end - first).days + 1 < s.min_history:
			continue
		if not any(d >= recent_from and q > 0 for d, q in raw.items()):
			continue  # not sold in eight weeks: discontinued or seasonal-off
		series = {d: raw.get(d, 0.0) for d in cal.daterange(first, history_end)}
		for fc in engine.forecast_item(item, series, events, history_end, targets, priors):
			if fc.target in closures:
				fc.qty = fc.low = fc.high = 0.0
				fc.drivers = ["Outlet closed (calendar)"]
			if fc.qty < s.min_item_qty:
				continue
			per_target[fc.target].append(fc)

	names = []
	item_names = dict(
		frappe.get_all(
			"Item", filters={"name": ["in", list(sales) or [""]]}, fields=["name", "item_name"], as_list=True
		)
	)
	for t in targets:
		fcs = sorted(per_target.get(t, []), key=lambda x: -x.qty)
		doc = _upsert_forecast(outlet, t, history_end, s, fcs, item_names, item_slots, outlet_slots, events)
		names.append(doc.name)

	if with_briefing and names:
		from alphax_pos_suite.alphax_pos_suite.forecast import ai

		first = frappe.get_doc("AlphaX POS Demand Forecast", names[0])
		text, source = ai.write_briefing(first)
		first.db_set({"briefing": text, "briefing_source": source}, update_modified=False)

	frappe.db.commit()
	return {"outlet": outlet, "forecasts": names}


def _upsert_forecast(outlet, target, history_end, s, fcs, item_names, item_slots, outlet_slots, events):
	name = frappe.db.get_value("AlphaX POS Demand Forecast", {"outlet": outlet, "forecast_date": target})
	doc = frappe.get_doc("AlphaX POS Demand Forecast", name) if name else frappe.new_doc("AlphaX POS Demand Forecast")
	doc.outlet = outlet
	doc.forecast_date = target
	hy, hm, hd = cal.to_hijri(target)
	doc.hijri_date = f"{hd}/{hm}/{hy} AH"
	doc.events = ", ".join(sorted(events.get(target, set())))
	doc.generated_on = now_datetime()
	doc.history_to = history_end
	doc.plan_to = s.plan_to
	doc.set("lines", [])
	total = 0.0
	for fc in fcs:
		slots = item_slots.get(fc.item_code) or outlet_slots
		peak = max(slots, key=slots.get) if slots else ""
		planned = round(fc.planned(s.plan_to), 2)
		total += fc.qty
		doc.append(
			"lines",
			{
				"item_code": fc.item_code,
				"item_name": item_names.get(fc.item_code, fc.item_code),
				"forecast_qty": fc.qty,
				"low_qty": fc.low,
				"high_qty": fc.high,
				"planned_qty": planned,
				"method": fc.method,
				"backtest_wape": round((fc.backtest_wape or 0) * 100, 1) if fc.backtest_wape is not None else None,
				"drivers": "; ".join(fc.drivers),
				"peak_slot": peak,
			},
		)
	doc.total_forecast = round(total, 2)
	doc.flags.ignore_permissions = True
	doc.save() if name else doc.insert()
	return doc


def generate_all():
	"""Nightly: score yesterday, then forecast every trading outlet."""
	s = settings()
	if not s.enabled:
		return
	record_actuals()
	for outlet in active_outlets():
		frappe.enqueue(
			"alphax_pos_suite.alphax_pos_suite.forecast.service.generate_for_outlet",
			queue="long",
			timeout=1800,
			job_id=f"alphax_forecast::{outlet}",
			deduplicate=True,
			outlet=outlet,
		)


# ------------------------------------------------------------------ accuracy


def record_actuals(days_back: int = 3):
	"""Fill actuals for recent past forecasts (re-runs absorb late postings)."""
	today = getdate(nowdate())
	rows = frappe.get_all(
		"AlphaX POS Demand Forecast",
		filters={"forecast_date": ["between", [add_days(today, -days_back), add_days(today, -1)]]},
		fields=["name", "outlet", "forecast_date"],
	)
	for r in rows:
		sales = load_daily_sales(r.outlet, r.forecast_date, r.forecast_date)
		doc = frappe.get_doc("AlphaX POS Demand Forecast", r.name)
		pairs = []
		for line in doc.lines:
			actual = flt(sales.get(line.item_code, {}).get(getdate(r.forecast_date), 0.0))
			line.actual_qty = actual
			pairs.append((actual, flt(line.forecast_qty)))
		doc.total_actual = round(sum(a for a, _ in pairs), 2)
		w, b = engine.wape(pairs), engine.bias(pairs)
		doc.wape = round(w * 100, 1) if w is not None else None
		doc.bias = round(b * 100, 1) if b is not None else None
		doc.flags.ignore_permissions = True
		doc.save()
	frappe.db.commit()


def accuracy_summary(outlet: str, days: int = 14) -> dict:
	rows = frappe.get_all(
		"AlphaX POS Demand Forecast",
		filters={
			"outlet": outlet,
			"forecast_date": ["between", [add_days(nowdate(), -days), add_days(nowdate(), -1)]],
			"total_actual": [">", 0],
		},
		fields=["forecast_date", "total_forecast", "total_actual", "wape", "bias"],
		order_by="forecast_date asc",
	)
	if not rows:
		return {"days": 0, "series": []}
	return {
		"days": len(rows),
		"wape": round(sum(flt(r.wape) for r in rows) / len(rows), 1),
		"bias": round(sum(flt(r.bias) for r in rows) / len(rows), 1),
		"series": [
			{"date": str(r.forecast_date), "forecast": flt(r.total_forecast), "actual": flt(r.total_actual)}
			for r in rows
		],
	}


# ------------------------------------------------------------------ prep plan


def _uom_factor(item_code: str, uom: str | None, stock_uom: str) -> float:
	if not uom or uom == stock_uom:
		return 1.0
	f = frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor")
	return flt(f) or 1.0


def build_prep_plan(outlet: str, business_date, force: bool = False) -> str:
	s = settings()
	business_date = getdate(business_date)
	fc_name = frappe.db.get_value("AlphaX POS Demand Forecast", {"outlet": outlet, "forecast_date": business_date})
	if not fc_name:
		frappe.throw(_("No forecast for {0} on {1}. Run the forecast first.").format(outlet, business_date))
	fc = frappe.get_doc("AlphaX POS Demand Forecast", fc_name)

	existing = frappe.db.get_value(
		"AlphaX POS Prep Plan", {"outlet": outlet, "business_date": business_date}, ["name", "status"], as_dict=True
	)
	if existing and existing.status != "Draft" and not force:
		frappe.throw(_("Prep plan {0} is already {1}.").format(existing.name, existing.status))

	warehouse = frappe.db.get_value("AlphaX POS Outlet", outlet, "warehouse")
	item_slots, outlet_slots = load_slot_shares(outlet, add_days(business_date, -1))

	sold = [l.item_code for l in fc.lines]
	recipes = {
		r.name: r
		for r in frappe.get_all("AlphaX POS Recipe", filters={"item_code": ["in", sold or [""]], "disabled": 0}, fields=["name", "item_code"])
	}
	recipe_rows = defaultdict(list)
	if recipes:
		for row in frappe.get_all(
			"AlphaX POS Recipe Item",
			filters={"parent": ["in", list(recipes)], "parenttype": "AlphaX POS Recipe"},
			fields=["parent", "material_item", "qty", "uom"],
		):
			recipe_rows[recipes[row.parent].item_code].append(row)
	stations = dict(
		frappe.get_all("AlphaX POS Item Station", filters={"item_code": ["in", sold or [""]]}, fields=["item_code", "station"], as_list=True)
	)

	need = defaultdict(float)  # (slot, station, material) -> qty in material stock uom
	for_items = defaultdict(set)
	no_recipe = []
	stock_uoms = {}
	for line in fc.lines:
		qty = flt(line.planned_qty)
		rows = recipe_rows.get(line.item_code)
		if not rows:
			no_recipe.append(f"{line.item_name or line.item_code} ({qty:g})")
			continue
		shares = item_slots.get(line.item_code) or outlet_slots
		for r in rows:
			if r.material_item not in stock_uoms:
				stock_uoms[r.material_item] = frappe.get_cached_value("Item", r.material_item, "stock_uom")
			per_unit = flt(r.qty) * _uom_factor(r.material_item, r.uom, stock_uoms[r.material_item])
			for slot in SLOTS:
				share = flt(shares.get(slot))
				if share <= 0:
					continue
				key = (slot, stations.get(line.item_code) or "", r.material_item)
				need[key] += qty * share * per_unit
				for_items[key].add(line.item_name or line.item_code)

	materials = {k[2] for k in need}
	on_hand = {}
	if warehouse and materials:
		on_hand = dict(
			frappe.get_all(
				"Bin", filters={"warehouse": warehouse, "item_code": ["in", list(materials)]},
				fields=["item_code", "actual_qty"], as_list=True,
			)
		)
	remaining = {m: max(flt(on_hand.get(m)), 0.0) for m in materials}

	doc = frappe.get_doc("AlphaX POS Prep Plan", existing.name) if existing else frappe.new_doc("AlphaX POS Prep Plan")
	doc.outlet = outlet
	doc.business_date = business_date
	doc.demand_forecast = fc.name
	doc.plan_to = fc.plan_to
	doc.warehouse = warehouse
	doc.status = "Draft"
	doc.set("lines", [])
	order = {slot: i for i, slot in enumerate(SLOTS)}
	for key in sorted(need, key=lambda k: (order[k[0]], k[1], k[2])):
		slot, station, material = key
		req = round(need[key], 3)
		if req <= 0:
			continue
		have = remaining[material]
		short = max(req - have, 0.0)
		remaining[material] = max(have - req, 0.0)
		doc.append(
			"lines",
			{
				"prep_slot": slot,
				"station": station or None,
				"material_item": material,
				"uom": stock_uoms.get(material),
				"required_qty": req,
				"on_hand_qty": round(have, 3),
				"shortfall_qty": round(short, 3),
				"for_items": ", ".join(sorted(for_items[key]))[:500],
			},
		)
	doc.unrecipe_items = ", ".join(no_recipe)[:2000]
	doc.flags.ignore_permissions = True
	doc.save() if existing else doc.insert()
	return doc.name


def create_material_request(prep_plan: str) -> str:
	s = settings()
	plan = frappe.get_doc("AlphaX POS Prep Plan", prep_plan)
	if plan.material_request and frappe.db.exists("Material Request", plan.material_request):
		return plan.material_request
	short = defaultdict(float)
	for l in plan.lines:
		if flt(l.shortfall_qty) > 0:
			short[l.material_item] += flt(l.shortfall_qty)
	if not short:
		frappe.throw(_("Nothing is short for this plan."))
	if not plan.warehouse:
		frappe.throw(_("Set a warehouse on outlet {0}.").format(plan.outlet))
	if s.mr_type == "Material Transfer" and not s.source_warehouse:
		frappe.throw(_("Set the central kitchen / store warehouse in AlphaX POS Forecast Settings."))

	company = frappe.db.get_value("AlphaX POS Outlet", plan.outlet, "company") or frappe.defaults.get_user_default("company")
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = s.mr_type
	mr.company = company
	mr.transaction_date = nowdate()
	mr.schedule_date = max(getdate(plan.business_date), getdate(nowdate()))
	mr.set_warehouse = plan.warehouse
	if s.mr_type == "Material Transfer":
		mr.set_from_warehouse = s.source_warehouse
	for item, qty in sorted(short.items()):
		row = {
			"item_code": item,
			"qty": round(qty, 3),
			"schedule_date": mr.schedule_date,
			"warehouse": plan.warehouse,
			"uom": frappe.get_cached_value("Item", item, "stock_uom"),
			"conversion_factor": 1,
		}
		if s.mr_type == "Material Transfer":
			row["from_warehouse"] = s.source_warehouse
		mr.append("items", row)
	mr.insert()
	plan.db_set({"material_request": mr.name, "status": "Issued"})
	return mr.name
