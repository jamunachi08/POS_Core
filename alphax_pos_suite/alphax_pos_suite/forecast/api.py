"""Whitelisted endpoints for the Demand & Prep Planner page."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from alphax_pos_suite.alphax_pos_suite.forecast import calendar_ksa as cal
from alphax_pos_suite.alphax_pos_suite.forecast import service

PLANNERS = {"AlphaX POS Manager", "System Manager"}
VIEWERS = PLANNERS | {"AlphaX POS Kitchen", "AlphaX POS Supervisor"}


def _require(roles):
	if not roles & set(frappe.get_roles()):
		frappe.throw(_("You do not have access to the demand planner."), frappe.PermissionError)


@frappe.whitelist()
def get_planner(outlet: str | None = None, date: str | None = None):
	_require(VIEWERS)
	outlets = frappe.get_all("AlphaX POS Outlet", pluck="name", order_by="name")
	outlet = outlet if outlet in outlets else (outlets[0] if outlets else None)
	d = getdate(date or nowdate())
	out = {
		"outlets": outlets,
		"outlet": outlet,
		"date": str(d),
		"can_plan": bool(PLANNERS & set(frappe.get_roles())),
		"enabled": service.settings().enabled,
		"forecast": None,
		"prep": None,
		"accuracy": {},
		"week": [],
	}
	if not outlet:
		return out
	hy, hm, hd = cal.to_hijri(d)
	out["hijri"] = f"{hd}/{hm}/{hy}"
	fc = frappe.db.get_value("AlphaX POS Demand Forecast", {"outlet": outlet, "forecast_date": d})
	if fc:
		out["forecast"] = frappe.get_doc("AlphaX POS Demand Forecast", fc).as_dict()
	prep = frappe.db.get_value("AlphaX POS Prep Plan", {"outlet": outlet, "business_date": d})
	if prep:
		out["prep"] = frappe.get_doc("AlphaX POS Prep Plan", prep).as_dict()
	out["accuracy"] = service.accuracy_summary(outlet)
	out["week"] = frappe.get_all(
		"AlphaX POS Demand Forecast",
		filters={"outlet": outlet, "forecast_date": ["between", [d, add_days(d, 6)]]},
		fields=["forecast_date", "total_forecast", "events"],
		order_by="forecast_date asc",
	)
	return out


@frappe.whitelist(methods=["POST"])
def run_now(outlet: str):
	_require(PLANNERS)
	if not frappe.db.exists("AlphaX POS Outlet", outlet):
		frappe.throw(_("Unknown outlet {0}.").format(outlet))
	frappe.enqueue(
		"alphax_pos_suite.alphax_pos_suite.forecast.service.generate_for_outlet",
		queue="long",
		timeout=1800,
		job_id=f"alphax_forecast::{outlet}",
		deduplicate=True,
		outlet=outlet,
	)
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
def build_prep(outlet: str, date: str, force: int = 0):
	_require(PLANNERS)
	return service.build_prep_plan(outlet, date, force=bool(int(force or 0)))


@frappe.whitelist(methods=["POST"])
def create_material_request(prep_plan: str):
	_require(PLANNERS)
	return service.create_material_request(prep_plan)


@frappe.whitelist(methods=["POST"])
def mark_prep_line(prep_plan: str, line: str, done: int = 1):
	_require(VIEWERS)
	frappe.db.set_value(
		"AlphaX POS Prep Plan Line", {"name": line, "parent": prep_plan}, "done", 1 if int(done) else 0
	)
	return True


@frappe.whitelist(methods=["POST"])
def test_ai_connection():
	_require({"System Manager", "AlphaX POS Manager"})
	from alphax_pos_suite.alphax_pos_suite.forecast import ai

	return ai.check_connection()
