"""Guest endpoints: QR table menu/ordering, online store, order tracking.

Guest-callable by necessity. Each one is bounded:
* QR: an active table token, 30 orders per token per hour.
* Online: the outlet must have online ordering on and not paused, inside its
  opening hours, under its open-order cap; 5 orders per phone and 20 per IP
  per hour.
* Tracking: a 16-character random reference; returns no personal data.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, get_time, now_datetime

from alphax_pos_suite.alphax_pos_suite.ordering import queue as Q
from alphax_pos_suite.alphax_pos_suite.ordering import rules



def _limit(key: str, limit: int, seconds: int = 3600) -> bool:
	k = frappe.cache.make_key(f"alphax_guest_rl:{key}")
	n = int(frappe.cache.incr(k))
	if n == 1:
		frappe.cache.expire(k, seconds)
	return n <= limit


def _ip() -> str:
	return getattr(frappe.local, "request_ip", None) or "unknown"


def _parse(lines):
	if isinstance(lines, str):
		lines = frappe.parse_json(lines or "[]")
	return lines or []


# ------------------------------------------------------------------ QR


def _token(token: str):
	t = frappe.db.get_value("AlphaX POS QR Table Token", {"token": token, "is_active": 1},
	                        ["name", "table", "outlet"], as_dict=True) if token else None
	if not t:
		frappe.throw(_("This table code is not active. Ask a member of staff."))
	outlet = t.outlet or (frappe.db.get_value("AlphaX POS Table", t.table, "outlet") if t.table else None)
	if not outlet:
		frappe.throw(_("This table is not linked to an outlet."))
	return t, outlet


@frappe.whitelist(allow_guest=True)
def qr_menu(token: str):
	t, outlet = _token(token)
	m = Q.menu(outlet)
	m["table"] = t.table
	return m


@frappe.whitelist(allow_guest=True, methods=["POST"])
def qr_place(token: str, items, customer_name: str = "", note: str = ""):
	t, outlet = _token(token)
	if not _limit(f"qr:{token}", 30):
		frappe.throw(_("Too many orders from this table. Ask a member of staff."))
	res = Q.create_order(source="QR", outlet=outlet, lines=_parse(items), customer_name=customer_name,
	                     table=t.table, fulfilment="Dine In", note=note, qr_token=token)
	frappe.db.set_value("AlphaX POS QR Table Token", t.name, "last_used_on", now_datetime(), update_modified=False)
	return {"ok": True, "order": res.name, "number": res.number, "ref": res.ref, "total": res.total,
	        "track_url": f"/track/{res.ref}"}


# ------------------------------------------------------------------ online


def _store(slug: str):
	o = frappe.db.get_value(
		"AlphaX POS Outlet", {"online_slug": slug},
		["name", "outlet_name", "online_ordering", "online_paused", "online_lead_minutes", "online_max_open",
		 "opening_time", "closing_time", "enforce_opening_time", "enforce_closing_time",
		 "online_message_en", "online_message_ar"],
		as_dict=True,
	) if slug else None
	if not o or not cint(o.online_ordering):
		frappe.throw(_("This store does not take online orders."), frappe.DoesNotExistError)
	return o


def _open_now(o) -> tuple[bool, str]:
	if cint(o.online_paused):
		return False, _("Online orders are paused for a short while. Please try again soon.")
	now = now_datetime().time()
	if o.opening_time and o.closing_time:
		op, cl = get_time(o.opening_time), get_time(o.closing_time)
		if not rules.within_hours(op, cl, now):
			return False, _("We are closed now. Orders open at {0}.").format(op.strftime("%H:%M"))
	open_count = frappe.db.count(Q.ORDER, {"pos_outlet": o.name, "order_source": "Online",
	                              "queue_status": ["in", list(Q.OPEN_STATES)]})
	if cint(o.online_max_open) and open_count >= cint(o.online_max_open):
		return False, _("The kitchen is at capacity. Please try again in a few minutes.")
	return True, ""


@frappe.whitelist(allow_guest=True)
def store(slug: str):
	o = _store(slug)
	ok, why = _open_now(o)
	m = Q.menu(o.name)
	m.update({"open": ok, "closed_reason": why, "lead_minutes": cint(o.online_lead_minutes) or 20,
	          "message_en": o.online_message_en or "", "message_ar": o.online_message_ar or ""})
	return m


@frappe.whitelist(allow_guest=True, methods=["POST"])
def place(slug: str, items, name: str, phone: str, pickup_at: str | None = None, note: str = ""):
	o = _store(slug)
	ok, why = _open_now(o)
	if not ok:
		frappe.throw(why)
	phone = rules.normalise_phone(phone)
	if not rules.valid_phone(phone):
		frappe.throw(_("Enter a mobile number we can call when your order is ready."))
	if not (name or "").strip():
		frappe.throw(_("Enter the name for the order."))
	if not _limit(f"web-ip:{_ip()}", 20) or not _limit(f"web-phone:{phone}", 5):
		frappe.throw(_("Too many orders in the last hour. Please call the store."))
	earliest = add_to_date(now_datetime(), minutes=cint(o.online_lead_minutes) or 20)
	promised = earliest
	if pickup_at:
		try:
			wanted = get_datetime(pickup_at)
		except Exception:
			wanted = None
		if wanted and wanted > earliest:
			if wanted > add_to_date(now_datetime(), hours=12):
				frappe.throw(_("Pickup can be at most 12 hours ahead."))
			promised = wanted
	res = Q.create_order(source="Online", outlet=o.name, lines=_parse(items), customer_name=name.strip(),
	                     phone=phone, fulfilment="Pickup", promised_at=promised, note=note)
	return {"ok": True, "number": res.number, "ref": res.ref, "total": res.total, "track_url": f"/track/{res.ref}"}


# ------------------------------------------------------------------ tracking


@frappe.whitelist(allow_guest=True)
def track(ref: str):
	if not ref or len(ref) < 12 or not _limit(f"track:{_ip()}", 600):
		return {"ok": False}
	return Q.track(ref)
