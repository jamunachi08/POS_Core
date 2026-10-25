"""Order Queue endpoints for staff (desk page alphax-order-queue)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, nowdate

from alphax_pos_suite.alphax_pos_suite.ordering import queue as Q

FLOOR = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "AlphaX POS Kitchen", "System Manager"}
TILL = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}


def _require(roles):
	if not roles & set(frappe.get_roles()):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


@frappe.whitelist()
def board(outlet: str | None = None):
	_require(FLOOR)
	filters = {"order_source": ["in", ["QR", "Online"]], "posting_date": [">=", add_days(nowdate(), -1)]}
	if outlet:
		filters["pos_outlet"] = outlet
	rows = frappe.get_all(
		Q.ORDER, filters=filters,
		fields=["name", "queue_number", "queue_status", "order_source", "fulfilment", "table", "customer_name",
		        "customer_phone", "promised_at", "queue_note", "reject_reason", "sales_invoice", "pos_outlet", "creation"],
		order_by="creation desc", limit=300,
	)
	names = [r.name for r in rows]
	items = {}
	for it in frappe.get_all("AlphaX POS Order Item", filters={"parent": ["in", names or [""]], "parenttype": Q.ORDER},
	                         fields=["parent", "item_code", "qty", "rate", "notes"], order_by="idx asc"):
		items.setdefault(it.parent, []).append(it)
	item_names = dict(frappe.get_all("Item", filters={"name": ["in", list({i.item_code for v in items.values() for i in v}) or [""]]},
	                                 fields=["name", "item_name"], as_list=True))
	for r in rows:
		r["items"] = [{"name": item_names.get(i.item_code, i.item_code), "qty": i.qty, "note": i.notes} for i in items.get(r.name, [])]
		r["total"] = round(sum((i.qty or 0) * (i.rate or 0) for i in items.get(r.name, [])), 2)
	mops = []
	if outlet:
		term = frappe.db.get_value("AlphaX POS Terminal", {"pos_outlet": outlet}, "pos_profile")
		if term:
			mops = frappe.get_all("POS Payment Method", filters={"parent": term, "parenttype": "POS Profile"}, pluck="mode_of_payment")
	if not mops:
		mops = frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name", limit=20)
	return {"orders": rows, "outlets": frappe.get_all("AlphaX POS Outlet", pluck="name", order_by="name"),
	        "modes_of_payment": mops, "now": str(frappe.utils.now_datetime())}


@frappe.whitelist(methods=["POST"])
def confirm(order: str, prep_minutes: int | None = None):
	_require(TILL)
	return Q.confirm(order, cint(prep_minutes) or None)


@frappe.whitelist(methods=["POST"])
def reject(order: str, reason: str):
	_require(TILL)
	return Q.reject(order, reason)


@frappe.whitelist(methods=["POST"])
def cancel(order: str, reason: str):
	_require({"AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"})
	return Q.cancel(order, reason)


@frappe.whitelist(methods=["POST"])
def ready(order: str):
	_require(FLOOR)
	return Q.mark_ready(order)


@frappe.whitelist(methods=["POST"])
def complete(order: str):
	_require(TILL)
	return Q.complete(order)


@frappe.whitelist(methods=["POST"])
def settle(order: str, mode_of_payment: str):
	_require(TILL)
	return Q.settle(order, mode_of_payment)
