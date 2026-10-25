"""Delivery Inbox endpoints (desk page alphax-delivery-inbox)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_url, now_datetime

from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import protocol as P
from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import service as S

FLOOR = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}
MANAGERS = {"AlphaX POS Manager", "System Manager"}


def _require(roles):
	if not roles & set(frappe.get_roles()):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


@frappe.whitelist()
def inbox(outlet: str | None = None):
	_require(FLOOR)
	filters = {"creation": [">", add_days(now_datetime(), -1)]}
	if outlet:
		filters["outlet"] = outlet
	rows = frappe.get_all(
		S.ORDER, filters=filters,
		fields=["name", "platform", "outlet", "short_code", "status", "expiry", "pickup_time", "is_test",
		        "expedition", "customer_name", "customer_note", "gross_total", "sales_invoice", "needs_review",
		        "review_note", "last_error", "connection", "creation"],
		order_by="creation desc", limit=200,
	)
	names = [r.name for r in rows]
	items = {}
	for it in frappe.get_all("AlphaX Aggregator Order Item", filters={"parent": ["in", names or [""]], "parenttype": S.ORDER},
	                         fields=["parent", "external_name", "qty", "is_modifier", "item_code", "note"], order_by="idx asc"):
		items.setdefault(it.parent, []).append(it)
	reasons = {}
	for r in rows:
		r["items"] = items.get(r.name, [])
		if r.connection not in reasons:
			reasons[r.connection] = S.proto(S.conn_doc(r.connection)).get("reject_reasons") or ["OTHER"]
	return {"orders": rows, "reasons": reasons, "now": str(now_datetime()),
	        "outlets": frappe.get_all("AlphaX POS Outlet", pluck="name", order_by="name")}


@frappe.whitelist(methods=["POST"])
def accept(order: str, prep_minutes: int | None = None):
	_require(FLOOR)
	return S.accept(order, cint(prep_minutes) or None)


@frappe.whitelist(methods=["POST"])
def reject(order: str, reason: str, message: str = ""):
	_require(FLOOR)
	return S.reject(order, reason, message)


@frappe.whitelist(methods=["POST"])
def ready(order: str):
	_require(FLOOR)
	return S.mark_ready(order)


@frappe.whitelist(methods=["POST"])
def picked_up(order: str, force: int = 0):
	_require(FLOOR)
	if cint(force):
		_require(MANAGERS)
	return S.mark_picked_up(order, cint(force))


@frappe.whitelist(methods=["POST"])
def post_invoice(order: str):
	_require(MANAGERS)
	return S.post_invoice(order)


@frappe.whitelist()
def connection_setup(connection: str):
	"""Webhook URL and protocol template for a connection form."""
	_require(MANAGERS)
	conn = frappe.get_doc(S.CONN, connection)
	base = f"{get_url()}/aggregator/{connection}"
	url = base if conn.adapter == P.DH else f"{base}/webhook"
	return {"webhook_url": url, "template": P.template_for(conn.adapter)}
