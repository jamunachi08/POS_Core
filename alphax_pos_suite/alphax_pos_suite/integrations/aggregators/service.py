"""Delivery platform orders: receive, answer, post.

Rules learned the hard way by every team that has built one of these:

* **Idempotent by order token.** Platforms retry dispatch until they get a
  2xx; a retry must return the same order, never create a second.
* **Answer the platform before cooking.** If the kitchen started and the
  acceptance then failed, the platform cancels for no response with the food
  made. The reverse failure (accepted, posting failed) is visible and fixable.
* **Local state follows the platform.** An order is marked Accepted only after
  the platform confirmed it, never optimistically.
* **Test orders never reach a kitchen.** A platform ``test`` flag or a store
  marked as a test store blocks posting; the store flag wins.
* **Cancellations after posting are flagged, not reversed.** The food may
  have left; reversing revenue is a manager's decision.
* **Every request is logged**, including rejected ones, so a misconfigured
  secret shows up as a log line, not silence.

Posting reuses the till's own path: a POS Sales Invoice with the outlet,
order type Delivery and the delivery platform set, so kitchen tickets, ZATCA,
tobacco fee, loyalty and the delivery reconciliation report all apply.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime

from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import protocol as P

CONN = "AlphaX Aggregator Connection"
ORDER = "AlphaX Aggregator Order"
MAP = "AlphaX Aggregator Item Map"
LOG = "AlphaX Aggregator Log"


# ------------------------------------------------------------------ config


def conn_doc(name: str):
	return frappe.get_cached_doc(CONN, name)


def proto(conn) -> dict:
	cfg = P.template_for(conn.adapter)
	try:
		cfg.update(json.loads(conn.protocol_json or "{}"))
	except ValueError:
		pass
	return cfg


def secret(conn, field):
	try:
		return conn.get_password(field, raise_exception=False)
	except Exception:
		return None


def log(conn_name, direction, path, status, ok, body=None, order=None, note=None):
	try:
		frappe.get_doc(
			{
				"doctype": LOG,
				"connection": conn_name,
				"direction": direction,
				"path": (path or "")[:140],
				"http_status": status,
				"ok": 1 if ok else 0,
				"order": order,
				"note": (note or "")[:1000],
				"body": (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str))[:20000] if body is not None else "",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="AlphaX aggregator: log write failed", message=frappe.get_traceback())


def _naive(dt: datetime | None):
	if not dt:
		return None
	return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _to_site_tz(dt: datetime | None):
	if not dt:
		return None
	from frappe.utils.data import convert_utc_to_system_timezone

	return convert_utc_to_system_timezone(_naive(dt)).replace(tzinfo=None)


# ------------------------------------------------------------------ store & items


def resolve_store(conn, remote_store_id: str, store_ref: str):
	stores = conn.get("stores") or []
	for s in stores:
		if remote_store_id and s.remote_store_id == remote_store_id:
			return s, "remote id"
	for s in stores:
		if store_ref and s.platform_store_ref and s.platform_store_ref == store_ref:
			return s, "platform restaurant id (add the remote id to the store row)"
	return None, "unmapped"


def map_codes(conn_name: str, lines: list[dict]) -> dict:
	"""{code: row} for every product and topping code; unknown codes are registered unmapped."""
	codes = {}
	for line in lines:
		codes[line["external_code"]] = (line["external_name"], 0)
		for t in line.get("toppings") or []:
			codes.setdefault(t["external_code"], (t["external_name"], 1))
	rows = {
		r.external_code: r
		for r in frappe.get_all(
			MAP,
			filters={"connection": conn_name, "external_code": ["in", list(codes) or [""]]},
			fields=["name", "external_code", "item_code", "is_modifier", "ignore"],
		)
	}
	for code, (name, is_mod) in codes.items():
		if code not in rows:
			doc = frappe.get_doc(
				{"doctype": MAP, "connection": conn_name, "external_code": code, "external_name": name,
				 "is_modifier": is_mod, "last_seen": now_datetime()}
			).insert(ignore_permissions=True)
			rows[code] = frappe._dict(name=doc.name, external_code=code, item_code=None, is_modifier=is_mod, ignore=0)
	return rows


def unmapped(order) -> list[str]:
	rows = {
		r.external_code: r
		for r in frappe.get_all(MAP, filters={"connection": order.connection},
		                        fields=["external_code", "item_code", "ignore"])
	}
	out = []
	for it in order.items:
		r = rows.get(it.external_code)
		if (r and (r.ignore or r.item_code)) or it.item_code:
			continue
		if it.is_modifier and not flt(it.rate):
			continue  # a free topping without a mapping travels as a kitchen note
		out.append(it.external_name or it.external_code)
	return out


# ------------------------------------------------------------------ inbound


def ingest(conn_name: str, normal: dict, raw: dict) -> tuple[str, bool]:
	"""Create (or return) the order. Returns (order name, created)."""
	existing = frappe.db.get_value(ORDER, {"order_token": normal["order_token"]})
	if existing:
		return existing, False
	conn = conn_doc(conn_name)
	store, route = resolve_store(conn, normal["remote_store_id"], normal["platform_store_ref"])
	map_codes(conn_name, normal["lines"])
	doc = frappe.new_doc(ORDER)
	doc.update(
		{
			"connection": conn_name,
			"platform": conn.delivery_platform,
			"outlet": store.outlet if store else None,
			"short_code": normal["short_code"],
			"status": "Received",
			"expiry": _to_site_tz(normal["expiry"]),
			"pickup_time": _to_site_tz(normal["pickup_time"]),
			"is_test": 1 if (normal["is_test"] or (store and store.is_test_store) or conn.sandbox) else 0,
			"external_order_id": normal["external_order_id"],
			"order_token": normal["order_token"],
			"remote_store_id": normal["remote_store_id"],
			"expedition": normal["expedition"],
			"customer_name": normal["customer_name"],
			"customer_note": normal["customer_note"],
			"gross_total": normal["gross_total"],
			"delivery_fee": normal["delivery_fee"],
			"discount_total": normal["discount_total"],
			"vat_total": normal["vat_total"],
			"callbacks_json": json.dumps(normal["callbacks"]),
			"payload_json": json.dumps({**raw, "_normal_lines": normal["lines"]}, ensure_ascii=False, default=str)[:140000],
			"needs_review": 0 if store else 1,
			"review_note": "" if store and route == "remote id" else f"Store routing: {route}",
		}
	)
	idx_map = {}
	for i, line in enumerate(normal["lines"], start=1):
		doc.append("items", {"external_code": line["external_code"], "external_name": line["external_name"],
		                     "qty": line["qty"], "rate": line["rate"], "note": line["note"]})
		idx_map[i] = len(doc.items)
		for t in line.get("toppings") or []:
			doc.append("items", {"external_code": t["external_code"], "external_name": t["external_name"],
			                     "qty": t["qty"] * line["qty"], "rate": t["rate"], "is_modifier": 1,
			                     "parent_line": idx_map[i]})
	doc.insert(ignore_permissions=True)
	_fill_item_codes(doc)
	frappe.db.set_value(CONN, conn_name, "last_order_at", now_datetime(), update_modified=False)
	frappe.publish_realtime("alphax_aggregator_order", {"name": doc.name, "outlet": doc.outlet,
	                        "short_code": doc.short_code, "event": "new"}, after_commit=True)
	if cint(conn.auto_accept) and store and not store.paused:
		frappe.enqueue(
			"alphax_pos_suite.alphax_pos_suite.integrations.aggregators.service.auto_accept",
			queue="short", order=doc.name, enqueue_after_commit=True,
		)
	return doc.name, True


def _fill_item_codes(doc):
	rows = {r.external_code: r for r in frappe.get_all(MAP, filters={"connection": doc.connection},
	                                                       fields=["external_code", "item_code"])}
	for it in doc.items:
		r = rows.get(it.external_code)
		if r and r.item_code and not it.item_code:
			frappe.db.set_value("AlphaX Aggregator Order Item", it.name, "item_code", r.item_code, update_modified=False)


def platform_cancelled(order_name: str, note: str = ""):
	o = frappe.get_doc(ORDER, order_name)
	if o.status in ("Cancelled", "Rejected"):
		return
	posted = o.sales_invoice and frappe.db.get_value("Sales Invoice", o.sales_invoice, "docstatus") == 1
	o.status = "Cancelled"
	if posted:
		o.needs_review = 1
		o.review_note = _("Cancelled by the platform after posting {0}. The invoice was not reversed: check whether the food left, then cancel or return it.").format(o.sales_invoice)
	o.last_error = note[:500]
	o.save(ignore_permissions=True)
	frappe.publish_realtime("alphax_aggregator_order", {"name": o.name, "outlet": o.outlet, "event": "cancelled",
	                        "short_code": o.short_code}, after_commit=True)


# ------------------------------------------------------------------ outbound


def _http(method, url, body=None, headers=None, form=False, timeout=15):
	data = None
	h = {"Accept": "application/json", **(headers or {})}
	if body is not None:
		if form:
			data = urllib.parse.urlencode(body).encode()
			h["Content-Type"] = "application/x-www-form-urlencoded"
		else:
			data = json.dumps(body).encode()
			h["Content-Type"] = "application/json"
	req = urllib.request.Request(url, data=data, headers=h, method=method)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — platform URLs from config
			txt = r.read().decode() or "{}"
			return r.status, txt
	except urllib.error.HTTPError as e:
		return e.code, (e.read() or b"").decode(errors="ignore")
	except (urllib.error.URLError, TimeoutError) as e:
		return 0, str(e)


def _token(conn) -> str | None:
	key = f"alphax_agg_token:{conn.name}"
	cached = frappe.cache.get_value(key)
	if cached:
		return cached
	cfg = proto(conn)
	base = (conn.api_base_url or "").rstrip("/")
	if conn.adapter == P.DH:
		status, txt = _http("POST", base + cfg.get("login_path", "/v2/login"),
		                    {"username": conn.username, "password": secret(conn, "password"),
		                     "grant_type": "client_credentials"}, form=True)
		log(conn.name, "Outbound", base + cfg.get("login_path", "/v2/login"), status, status == 200, note="login")
		if status != 200:
			return None
		data = json.loads(txt)
		tok, ttl = data.get("access_token"), cint(data.get("expires_in")) or 7200
	else:
		t = cfg.get("token")
		if not t:
			return None
		vals = {"api_key": conn.api_key, "api_secret": secret(conn, "api_secret"),
		        "username": conn.username, "password": secret(conn, "password")}
		status, txt = _http(t.get("method", "POST"), base + t["path"], P.fill(t.get("body") or {}, vals))
		log(conn.name, "Outbound", base + t["path"], status, status in (200, 201), note="token")
		if status not in (200, 201):
			return None
		tok, ttl = P.pick(json.loads(txt), t.get("token_field", "access_token")), cint(t.get("ttl_seconds")) or 3000
	if tok:
		frappe.cache.set_value(key, tok, expires_in_sec=max(ttl - cint(cfg.get("token_ttl_margin_seconds") or 300), 60))
	return tok


def _send(order, action: str, extra: dict | None = None) -> tuple[bool, str]:
	"""Tell the platform. Returns (confirmed, message)."""
	conn = conn_doc(order.connection)
	cfg = proto(conn)
	if order.is_test and conn.sandbox and not (order.callbacks_json or "").strip("{} "):
		return True, "sandbox: nothing sent"
	tok = _token(conn)
	if not tok:
		return False, _("Could not get a token from the platform. Check the connection credentials.")
	headers = {"Authorization": f"Bearer {tok}"}
	extra = extra or {}

	if conn.adapter == P.DH:
		cb = json.loads(order.callbacks_json or "{}")
		now = datetime.now(timezone.utc)
		if action == "accept":
			url = cb.get("orderAcceptedUrl")
			pickup = order.pickup_time and frappe.utils.get_datetime(order.pickup_time)
			pickup_utc = None
			if pickup:
				import zoneinfo

				from frappe.utils.data import get_system_timezone

				pickup_utc = pickup.replace(tzinfo=zoneinfo.ZoneInfo(get_system_timezone())).astimezone(timezone.utc)
			body = {"status": "order_accepted", "remoteOrderId": order.name,
			        "acceptanceTime": P.dh_acceptance_time(now, cint(extra.get("prep_minutes") or conn.default_prep_minutes or 15),
			                                               pickup_utc, cint(cfg.get("min_prep_minutes") or 3))}
		elif action == "reject":
			url = cb.get("orderRejectedUrl")
			body = {"status": "order_rejected", "reason": extra.get("reason") or "OTHER", "message": extra.get("message") or ""}
		elif action == "picked_up":
			url = cb.get("orderPickedUpUrl")
			body = {"status": "order_picked_up"}
		elif action == "ready":
			url = cb.get("orderPreparedUrl")
			body = {}
		else:
			return False, f"unknown action {action}"
		if not url:
			return False, _("The order carries no callback URL for {0}.").format(action)
		method = cfg.get("callback_method", "POST")
	else:
		act = (cfg.get("actions") or {}).get(action)
		if not act:
			return True, _("This platform has no {0} call configured; nothing sent.").format(action)
		vals = {"order_id": order.external_order_id, "order_token": order.order_token,
		        "prep_minutes": extra.get("prep_minutes") or conn.default_prep_minutes or 15,
		        "reason": extra.get("reason") or "OTHER", "message": extra.get("message") or ""}
		url = (conn.api_base_url or "").rstrip("/") + P.fill(act["path"], vals)
		body = P.fill(act.get("body") or {}, vals)
		method = act.get("method", "POST")

	status, txt = _http(method, url, body, headers)
	if status == 401:
		frappe.cache.delete_value(f"alphax_agg_token:{conn.name}")
		tok = _token(conn)
		if tok:
			status, txt = _http(method, url, body, {"Authorization": f"Bearer {tok}"})
	ok = 200 <= status < 300
	log(conn.name, "Outbound", url, status, ok, body={"sent": body, "reply": txt[:4000]}, order=order.name, note=action)
	return ok, ("ok" if ok else f"HTTP {status}: {txt[:300]}")


# ------------------------------------------------------------------ actions


def _outlet_open_shift(outlet: str):
	return frappe.db.sql(
		"""
		select s.name, s.pos_terminal from `tabAlphaX POS Shift` s
		join `tabAlphaX POS Terminal` t on t.name = s.pos_terminal
		where s.status = 'Open' and t.pos_outlet = %s
		order by s.opened_on desc limit 1
		""",
		outlet,
		as_dict=True,
	)


def can_cook(order) -> tuple[bool, str]:
	if not order.outlet:
		return False, _("The platform store is not mapped to an outlet.")
	if order.is_test:
		return True, "test"
	if not _outlet_open_shift(order.outlet):
		return False, _("No shift is open at {0}.").format(order.outlet)
	missing = unmapped(order)
	if missing:
		return False, _("Map these platform items first: {0}").format(", ".join(missing[:8]))
	return True, "ok"


def accept(order_name: str, prep_minutes: int | None = None, user: str | None = None) -> dict:
	o = frappe.get_doc(ORDER, order_name)
	if o.status not in ("Received", "Failed"):
		return {"ok": o.status == "Accepted", "status": o.status}
	ok, why = can_cook(o)
	if not ok:
		o.db_set({"last_error": why, "needs_review": 1})
		return {"ok": False, "message": why}
	confirmed, msg = _send(o, "accept", {"prep_minutes": prep_minutes})
	if not confirmed:
		o.db_set({"last_error": msg, "status": "Failed" if o.status == "Failed" else o.status})
		return {"ok": False, "message": msg}
	o.db_set({"status": "Test" if o.is_test else "Accepted", "accepted_by": user or frappe.session.user,
	          "accepted_at": now_datetime(), "last_error": ""})
	if o.is_test:
		return {"ok": True, "status": "Test", "message": _("Test order accepted. Nothing was sent to the kitchen.")}
	try:
		si = post_invoice(o.name)
		return {"ok": True, "status": "Accepted", "sales_invoice": si}
	except Exception as e:
		frappe.db.rollback()
		frappe.db.set_value(ORDER, o.name, {"needs_review": 1,
		                    "last_error": f"Accepted on the platform but posting failed: {str(e)[:400]}"})
		frappe.db.commit()
		frappe.log_error(title="AlphaX aggregator: posting failed after accept", message=frappe.get_traceback())
		return {"ok": False, "status": "Accepted", "message": _("Accepted on the platform, but the invoice failed: {0}. Post it from the order.").format(str(e)[:200])}


def auto_accept(order: str):
	frappe.set_user("Administrator")
	res = accept(order, user="Administrator")
	if not res.get("ok"):
		frappe.publish_realtime("alphax_aggregator_order", {"name": order, "event": "needs_attention",
		                        "message": res.get("message")}, after_commit=True)


def reject(order_name: str, reason: str, message: str = "") -> dict:
	o = frappe.get_doc(ORDER, order_name)
	if o.status != "Received":
		frappe.throw(_("Only a received order can be rejected (this one is {0}).").format(o.status))
	if not reason:
		frappe.throw(_("Choose a reject reason; platforms refuse a rejection without one."))
	confirmed, msg = _send(o, "reject", {"reason": reason, "message": message})
	if not confirmed:
		o.db_set("last_error", msg)
		return {"ok": False, "message": msg}
	o.db_set({"status": "Rejected", "reject_reason": reason, "last_error": ""})
	return {"ok": True}


def mark_ready(order_name: str) -> dict:
	o = frappe.get_doc(ORDER, order_name)
	confirmed, msg = _send(o, "ready")
	if confirmed:
		o.db_set("status", "Ready")
	return {"ok": confirmed, "message": msg}


def mark_picked_up(order_name: str, force: int = 0) -> dict:
	o = frappe.get_doc(ORDER, order_name)
	if o.expedition == "Platform delivery" and o.status not in ("Ready",) and not force:
		frappe.throw(_("Mark the order ready first. Picked up is final on the platform."))
	confirmed, msg = _send(o, "picked_up") if o.expedition != "Platform delivery" else (True, "rider pickup is reported by the platform")
	if confirmed:
		o.db_set("status", "Picked Up")
	return {"ok": confirmed, "message": msg}


# ------------------------------------------------------------------ posting


def post_invoice(order_name: str) -> str:
	o = frappe.get_doc(ORDER, order_name)
	if o.sales_invoice:
		return o.sales_invoice
	if o.is_test:
		frappe.throw(_("Test orders are never posted."))
	conn = conn_doc(o.connection)
	outlet = frappe.get_doc("AlphaX POS Outlet", o.outlet)
	platform = frappe.get_cached_doc("AlphaX Delivery Platform", conn.delivery_platform)
	if not platform.mode_of_payment:
		frappe.throw(_("Set a Mode of Payment on delivery platform {0}.").format(platform.name))
	customer = conn.customer or frappe.db.get_value("AlphaX POS Terminal", {"pos_outlet": o.outlet}, "default_customer")
	if not customer:
		frappe.throw(_("Set the invoice customer on connection {0}.").format(conn.name))

	uuid = f"AGG-{o.name}"
	existing = frappe.db.get_value("Sales Invoice", {"alphax_client_uuid": uuid, "docstatus": ["<", 2]}, "name")
	if existing:
		o.db_set("sales_invoice", existing)
		return existing

	rows = {r.external_code: r for r in frappe.get_all(MAP, filters={"connection": o.connection},
	                                                       fields=["external_code", "item_code", "ignore"])}
	shift = _outlet_open_shift(o.outlet)
	items, notes = [], []
	for it in o.items:
		r = rows.get(it.external_code)
		if r and r.ignore:
			continue
		code = (r and r.item_code) or it.item_code
		if not code:
			if it.is_modifier and not flt(it.rate):
				notes.append(it.external_name)
				continue
			frappe.throw(_("Platform item {0} is not mapped.").format(it.external_name or it.external_code))
		items.append({
			"item_code": code, "qty": flt(it.qty) or 1, "rate": flt(it.rate), "price_list_rate": flt(it.rate),
			"warehouse": outlet.warehouse, "cost_center": outlet.cost_center,
			"description": (it.note or "")[:500] or None,
		})
	if not items:
		frappe.throw(_("The order has no postable items."))

	d = {
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": outlet.company,
		"is_pos": 1,
		"update_stock": cint(outlet.update_stock),
		"set_warehouse": outlet.warehouse,
		"cost_center": outlet.cost_center,
		"selling_price_list": outlet.default_price_list,
		"taxes_and_charges": outlet.sales_taxes_and_charges_template,
		"ignore_pricing_rule": 1,
		"alphax_outlet": o.outlet,
		"alphax_order_type": "Delivery",
		"alphax_delivery_platform": platform.name,
		"alphax_client_uuid": uuid,
		"alphax_pos_terminal": shift[0].pos_terminal if shift else None,
		"remarks": f"{platform.name} #{o.short_code} ({o.name})" + (f" — {', '.join(notes)}" if notes else ""),
		"items": items,
	}
	from alphax_pos_suite.alphax_pos_suite.pos.queue_api import _heal_customer, _preflight

	_heal_customer(d)
	_preflight(d)
	si = frappe.get_doc(d)
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	amount = flt(si.rounded_total or si.grand_total)
	si.set("payments", [])
	si.append("payments", {"mode_of_payment": platform.mode_of_payment, "amount": amount,
	                       "account": (get_bank_cash_account(platform.mode_of_payment, si.company) or {}).get("account")})
	si.calculate_taxes_and_totals()
	si.flags.ignore_permissions = True
	si.insert()
	si.submit()
	o.db_set("sales_invoice", si.name)
	if abs(amount - flt(o.gross_total) + flt(o.delivery_fee)) > 1 and flt(o.gross_total):
		o.db_set({"needs_review": 1, "review_note": _("Invoice {0} totals {1}; the platform says the customer paid {2} (delivery fee {3}). Check prices and VAT on mapped items.").format(si.name, amount, o.gross_total, o.delivery_fee)})
	return si.name


# ------------------------------------------------------------------ housekeeping


def expire_unanswered():
	now = now_datetime()
	for name in frappe.get_all(ORDER, filters={"status": "Received", "expiry": ["<", now]}, pluck="name"):
		frappe.db.set_value(ORDER, name, {"status": "Expired", "needs_review": 1,
		                    "review_note": _("Nobody answered before the platform's deadline.")})


def purge_logs(days: int = 30):
	frappe.db.delete(LOG, {"creation": ["<", add_days(now_datetime(), -days)]})
