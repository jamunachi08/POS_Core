"""v16.1.0 — give the demand planner working defaults on existing sites.

Only fills values that are empty, so an operator's choices survive re-runs.
"""

import frappe

DEFAULTS = {
	"enabled": 1,
	"horizon_days": 7,
	"history_days": 400,
	"min_history_days": 28,
	"plan_to": "P80",
	"min_item_qty": 0.5,
	"material_request_type": "Material Transfer",
	"ai_model": "qwen2.5:7b-instruct",
	"ai_timeout": 30,
}


def execute():
	if not frappe.db.exists("DocType", "AlphaX POS Forecast Settings"):
		return
	for field, value in DEFAULTS.items():
		current = frappe.db.get_single_value("AlphaX POS Forecast Settings", field)
		if current in (None, "", 0) and not (field == "enabled" and current == 0 and _was_saved()):
			frappe.db.set_single_value("AlphaX POS Forecast Settings", field, value)


def _was_saved() -> bool:
	return bool(
		frappe.db.sql(
			"select 1 from `tabSingles` where doctype = 'AlphaX POS Forecast Settings' and field = 'modified' limit 1"
		)
	)
