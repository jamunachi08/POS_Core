"""Order queue — table (QR) and online pickup orders, from guest to kitchen.

One path for both sources:

    guest places order ─► New ─(staff confirm, or auto)─► In Kitchen ─(all
    tickets ready)─► Ready ─(served / collected)─► Completed ─(paid)─► Settled

* Prices are always the server's: the outlet price list, never the client.
* Items switched off on the availability board cannot be ordered.
* Kitchen tickets are created on confirmation through the same station
  routing as register sales, carrying the order's short number so the lobby
  screen can call it. Settling later does not create a second set.
* Each order gets a random guest reference; the tracking page shows status,
  number and ready-by time only, never names or phone numbers.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, getdate, now_datetime, nowdate

ORDER = "AlphaX POS Order"
OPEN_STATES = ("New", "In Kitchen", "Ready")


# ------------------------------------------------------------------ menu


def _allowed_groups(outlet: dict) -> list[str] | None:
	if not outlet.get("primary_domain"):
		return None
	root = frappe.db.get_value("AlphaX POS Domain Pack", outlet["primary_domain"], "default_item_group")
	if not root:
		return None
	g = frappe.db.get_value("Item Group", root, ["lft", "rgt"], as_dict=True)
	if not g:
		return None
	return frappe.get_all("Item Group", filters={"lft": [">=", g.lft], "rgt": ["<=", g.rgt]}, pluck="name")


def menu(outlet_name: str) -> dict:
	"""Sellable items for guests: outlet menu scope, server price, available now."""
	from alphax_pos_suite.alphax_pos_suite.pos.availability import current_map

	outlet = frappe.db.get_value(
		"AlphaX POS Outlet", outlet_name,
		["name", "outlet_name", "company", "default_price_list", "primary_domain"], as_dict=True,
	)
	if not outlet:
		frappe.throw(_("Unknown outlet."))
	filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
	groups = _allowed_groups(outlet)
	if groups:
		filters["item_group"] = ["in", groups]
	rows = frappe.get_all("Item", filters=filters, fields=["name", "item_name", "item_group", "image",
	                      "standard_rate", "description"], order_by="item_group asc, item_name asc", limit_page_length=600)
	prices = {}
	if outlet.default_price_list and rows:
		for p in frappe.get_all("Item Price", filters={"price_list": outlet.default_price_list, "selling": 1,
		                        "item_code": ["in", [r.name for r in rows]]},
		                        fields=["item_code", "price_list_rate", "customer"], order_by="valid_from desc"):
			if not p.customer:
				prices.setdefault(p.item_code, flt(p.price_list_rate))
	off = current_map(outlet.name)
	items = []
	for r in rows:
		rate = prices.get(r.name) or flt(r.standard_rate)
		if rate <= 0:
			continue
		state = (off.get(r.name) or {}).get("status")
		items.append({"item_code": r.name, "item_name": r.item_name, "item_group": r.item_group,
		              "rate": rate, "image": r.image, "available": state != "Off", "low": state == "Low"})
	currency = frappe.db.get_value("Company", outlet.company, "default_currency") if outlet.company else "SAR"
	return {"outlet": outlet.name, "outlet_name": outlet.outlet_name or outlet.name,
	        "currency": currency or "SAR", "items": items}


# ------------------------------------------------------------------ numbers


def _queue_number(outlet: str) -> str:
	"""Short daily number per outlet (Q-017 for tables, W-017 for web)."""
	key = frappe.cache.make_key(f"alphax_queue_no:{outlet}:{nowdate()}")  # site-scoped on a shared Redis
	n = cint(frappe.cache.incr(key))
	if n == 1:
		frappe.cache.expire(key, 36 * 3600)
		# Redis was flushed mid-day: continue after today's highest number.
		done = frappe.db.sql(
			"""select count(*) from `tabAlphaX POS Order`
			where pos_outlet=%s and coalesce(order_source,'Till') != 'Till' and posting_date=%s""",
			(outlet, nowdate()),
		)[0][0]
		if done:
			n = cint(frappe.cache.incrby(key, cint(done)))
	return f"{n:03d}"


def _intake_terminal(outlet: str) -> frappe._dict:
	"""Terminal and customer guest orders are booked under.

	AlphaX POS Order requires both. Prefer a terminal with an open shift so the
	order lands where someone is working; else any terminal of the outlet.
	"""
	row = frappe.db.sql(
		"""select t.name, t.default_customer from `tabAlphaX POS Terminal` t
		left join `tabAlphaX POS Shift` s on s.pos_terminal = t.name and s.status = 'Open'
		where t.pos_outlet = %s
		order by (s.name is not null) desc, t.name asc limit 1""",
		outlet,
		as_dict=True,
	)
	if not row:
		frappe.throw(_("This outlet has no till set up to receive orders yet."))
	customer = row[0].default_customer
	if not customer:
		frappe.throw(_("Set a default customer on till {0} to receive guest orders.").format(row[0].name))
	return frappe._dict(terminal=row[0].name, customer=customer)


# ------------------------------------------------------------------ create


def create_order(*, source: str, outlet: str, lines: list[dict], customer_name: str = "", phone: str = "",
                 table: str | None = None, fulfilment: str = "Dine In", promised_at=None, note: str = "",
                 qr_token: str | None = None) -> frappe._dict:
	"""Validate and price a guest order, then queue it. Returns name, number, ref, total."""
	if source not in ("QR", "Online"):
		frappe.throw(_("Unknown order source."))
	if not isinstance(lines, list) or not lines:
		frappe.throw(_("Your order is empty."))
	if len(lines) > 50:
		frappe.throw(_("Too many lines in one order (50 at most)."))

	m = menu(outlet)
	catalogue = {i["item_code"]: i for i in m["items"]}
	o_doc = frappe.db.get_value("AlphaX POS Outlet", outlet,
	                            ["company", "warehouse", "qr_auto_confirm", "online_auto_confirm"], as_dict=True)

	intake = _intake_terminal(outlet)
	order = frappe.new_doc(ORDER)
	order.pos_terminal = intake.terminal
	order.customer = intake.customer
	order.pos_outlet = outlet
	order.company = o_doc.company
	order.warehouse = o_doc.warehouse
	order.posting_date = nowdate()
	order.posting_time = now_datetime().strftime("%H:%M:%S")
	order.order_status = "Hold"
	order.order_source = source
	order.queue_status = "New"
	order.fulfilment = fulfilment
	order.customer_name = (customer_name or "")[:140]
	order.customer_phone = (phone or "")[:30]
	order.table = (table or "")[:140]
	order.qr_token = qr_token
	order.queue_note = (note or "")[:500]
	order.promised_at = promised_at
	order.guest_ref = secrets.token_urlsafe(12)
	order.client_uuid = f"{source}-{order.guest_ref}"

	unavailable = []
	total = 0.0
	for ln in lines:
		code = str((ln or {}).get("item_code") or "")[:140]
		qty = flt((ln or {}).get("qty"))
		if not code or qty <= 0 or qty > 99:
			continue
		item = catalogue.get(code)
		if not item:
			continue
		if not item["available"]:
			unavailable.append(item["item_name"])
			continue
		order.append("items", {"item_code": code, "qty": qty, "rate": item["rate"],
		                       "notes": str((ln or {}).get("note") or "")[:140], "warehouse": o_doc.warehouse})
		total += qty * item["rate"]
	if unavailable:
		frappe.throw(_("Sorry, these are not available right now: {0}").format(", ".join(unavailable)))
	if not order.items:
		frappe.throw(_("None of the items in your order can be ordered here."))

	order.queue_number = ("Q-" if source == "QR" else "W-") + _queue_number(outlet)
	order.insert(ignore_permissions=True)
	frappe.publish_realtime("alphax_order_queue", {"order": order.name, "outlet": outlet, "event": "new",
	                        "number": order.queue_number, "source": source}, after_commit=True)

	auto = cint(o_doc.qr_auto_confirm) if source == "QR" else cint(o_doc.online_auto_confirm)
	if auto:
		frappe.enqueue("alphax_pos_suite.alphax_pos_suite.ordering.queue.confirm", queue="short",
		               order=order.name, enqueue_after_commit=True, as_system=True)
	return frappe._dict(name=order.name, number=order.queue_number, ref=order.guest_ref, total=round(total, 2))


# ------------------------------------------------------------------ transitions


def _set(order, status, **extra):
	order.db_set({"queue_status": status, **extra})
	frappe.publish_realtime("alphax_order_queue", {"order": order.name, "outlet": order.pos_outlet,
	                        "event": status.lower(), "number": order.queue_number}, after_commit=True)


def confirm(order: str, prep_minutes: int | None = None, as_system: bool = False):
	if as_system:
		frappe.set_user("Administrator")
	o = frappe.get_doc(ORDER, order)
	if o.queue_status != "New":
		return {"ok": o.queue_status in ("In Kitchen", "Ready"), "status": o.queue_status}
	from alphax_pos_suite.alphax_pos_suite.pos.kot_api import _guest_allergy_note, fan_out

	label = f"#{o.queue_number}" + (f" · {o.table}" if o.table else "") + (" · PICKUP" if o.fulfilment == "Pickup" else "")
	tickets = fan_out(
		[it for it in o.items if not cint(it.get("is_void"))], o.pos_outlet, customer=o.customer,
		pos_order=o.name, table=o.table or label, token_no=o.queue_number,
		business_date=str(o.posting_date or nowdate()), guest_note=(o.queue_note or "")[:500],
	)
	promised = o.promised_at
	if not promised or get_datetime(promised) < now_datetime():
		promised = add_to_date(now_datetime(), minutes=cint(prep_minutes) or 15)
	_set(o, "In Kitchen", promised_at=promised, kds_ticket=tickets[0] if tickets else None)
	if not tickets:
		# No KDS stations configured: nothing will report ready, so staff mark it.
		frappe.msgprint(_("No kitchen station routes these items. Mark the order ready from the queue."), alert=True)
	return {"ok": True, "tickets": tickets, "promised_at": str(promised)}


def reject(order: str, reason: str):
	o = frappe.get_doc(ORDER, order)
	if o.queue_status != "New":
		frappe.throw(_("Only a new order can be rejected; cancel it instead."))
	if not (reason or "").strip():
		frappe.throw(_("Give the guest a reason."))
	_set(o, "Rejected", reject_reason=reason.strip()[:140])
	return {"ok": True}


def cancel(order: str, reason: str):
	o = frappe.get_doc(ORDER, order)
	if o.queue_status not in OPEN_STATES:
		frappe.throw(_("This order is {0} and cannot be cancelled here.").format(o.queue_status))
	for t in frappe.get_all("AlphaX POS KDS Ticket", filters={"pos_order": o.name, "status": ["not in", ["Served", "Cancelled"]]}, pluck="name"):
		frappe.db.set_value("AlphaX POS KDS Ticket", t, "status", "Cancelled")
		frappe.publish_realtime("alphax_kds_update", {"ticket": t, "action": "cancelled"}, after_commit=True)
	_set(o, "Cancelled", reject_reason=(reason or "")[:140])
	return {"ok": True}


def mark_ready(order: str):
	o = frappe.get_doc(ORDER, order)
	if o.queue_status in ("New", "In Kitchen"):
		_set(o, "Ready")
	return {"ok": True}


def complete(order: str):
	o = frappe.get_doc(ORDER, order)
	if o.queue_status not in ("In Kitchen", "Ready"):
		frappe.throw(_("Only an order in the kitchen or ready can be completed."))
	for t in frappe.get_all("AlphaX POS KDS Ticket", filters={"pos_order": o.name, "status": ["in", ["Ready", "Packing"]]}, pluck="name"):
		frappe.db.set_value("AlphaX POS KDS Ticket", t, {"status": "Served", "served_on": now_datetime()})
	_set(o, "Completed")
	return {"ok": True}


def on_ticket_update(doc, method=None):
	"""KDS ticket changed: when every ticket of a queued order is ready, the order is ready."""
	if not doc.pos_order or doc.status not in ("Ready", "Served"):
		return
	status = frappe.db.get_value(ORDER, doc.pos_order, "queue_status")
	if status != "In Kitchen":
		return
	pending = frappe.db.count("AlphaX POS KDS Ticket", {"pos_order": doc.pos_order,
	                          "status": ["not in", ["Ready", "Served", "Cancelled"]]})
	if not pending:
		_set(frappe.get_doc(ORDER, doc.pos_order), "Ready")


# ------------------------------------------------------------------ settle


def _open_shift_terminal(outlet):
	r = frappe.db.sql(
		"""select s.pos_terminal from `tabAlphaX POS Shift` s
		join `tabAlphaX POS Terminal` t on t.name = s.pos_terminal
		where s.status='Open' and t.pos_outlet=%s order by s.opened_on desc limit 1""",
		outlet,
	)
	return r[0][0] if r else None


def settle(order: str, mode_of_payment: str, customer: str | None = None) -> str:
	"""Post the order as a POS Sales Invoice paid by one mode of payment."""
	o = frappe.get_doc(ORDER, order)
	if o.sales_invoice:
		return o.sales_invoice
	if o.queue_status not in ("In Kitchen", "Ready", "Completed"):
		frappe.throw(_("Confirm the order before taking payment."))
	terminal = _open_shift_terminal(o.pos_outlet)
	if not terminal:
		frappe.throw(_("Open a shift at {0} before taking payment.").format(o.pos_outlet))
	outlet = frappe.get_doc("AlphaX POS Outlet", o.pos_outlet)
	customer = customer or o.customer or frappe.db.get_value("AlphaX POS Terminal", terminal, "default_customer")
	if not customer:
		frappe.throw(_("Set a default customer on terminal {0}.").format(terminal))
	uuid = f"ORD-{o.name}"
	existing = frappe.db.get_value("Sales Invoice", {"alphax_client_uuid": uuid, "docstatus": ["<", 2]}, "name")
	if existing:
		o.db_set("sales_invoice", existing)
		return existing
	d = {
		"doctype": "Sales Invoice", "customer": customer, "company": outlet.company, "is_pos": 1,
		"update_stock": cint(outlet.update_stock), "set_warehouse": outlet.warehouse,
		"cost_center": outlet.cost_center, "selling_price_list": outlet.default_price_list,
		"taxes_and_charges": outlet.sales_taxes_and_charges_template, "ignore_pricing_rule": 1,
		"alphax_outlet": outlet.name, "alphax_pos_terminal": terminal, "alphax_client_uuid": uuid,
		"alphax_pos_order": o.name, "alphax_order_type": "Dine In" if o.fulfilment == "Dine In" else "Takeaway",
		"remarks": f"{o.order_source} order #{o.queue_number} ({o.name})",
		"items": [{"item_code": it.item_code, "qty": it.qty, "rate": it.rate, "price_list_rate": it.rate,
		           "warehouse": outlet.warehouse, "cost_center": outlet.cost_center}
		          for it in o.items if not cint(it.get("is_void"))],
	}
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	from alphax_pos_suite.alphax_pos_suite.pos.queue_api import _heal_customer, _preflight

	_heal_customer(d)
	_preflight(d)
	si = frappe.get_doc(d)
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	amount = flt(si.rounded_total or si.grand_total)
	si.set("payments", [{"mode_of_payment": mode_of_payment, "amount": amount,
	                     "account": (get_bank_cash_account(mode_of_payment, si.company) or {}).get("account")}])
	si.calculate_taxes_and_totals()
	si.insert()
	si.submit()
	o.db_set({"sales_invoice": si.name, "queue_status": "Settled", "order_status": "Active"})
	frappe.publish_realtime("alphax_order_queue", {"order": o.name, "outlet": o.pos_outlet, "event": "settled"}, after_commit=True)
	return si.name


# ------------------------------------------------------------------ guest view


def track(ref: str) -> dict:
	o = frappe.db.get_value(
		ORDER, {"guest_ref": ref},
		["name", "queue_number", "queue_status", "promised_at", "pos_outlet", "fulfilment", "reject_reason", "creation", "table"],
		as_dict=True,
	)
	if not o:
		return {"ok": False}
	items = frappe.get_all("AlphaX POS Order Item", filters={"parent": o.name, "parenttype": ORDER},
	                       fields=["item_code", "qty", "rate"], order_by="idx asc")
	names = dict(frappe.get_all("Item", filters={"name": ["in", [i.item_code for i in items] or [""]]},
	                            fields=["name", "item_name"], as_list=True))
	return {
		"ok": True, "number": o.queue_number, "status": o.queue_status, "fulfilment": o.fulfilment,
		"promised_at": str(o.promised_at) if o.promised_at else None,
		"outlet": frappe.db.get_value("AlphaX POS Outlet", o.pos_outlet, "outlet_name") or o.pos_outlet,
		"reason": o.reject_reason if o.queue_status in ("Rejected", "Cancelled") else "",
		"items": [{"name": names.get(i.item_code, i.item_code), "qty": i.qty, "amount": round(flt(i.qty) * flt(i.rate), 2)} for i in items],
		"total": round(sum(flt(i.qty) * flt(i.rate) for i in items), 2),
		"now": str(now_datetime()),
	}
