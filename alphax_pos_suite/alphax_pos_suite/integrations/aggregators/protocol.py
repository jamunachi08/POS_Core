"""Delivery platform protocols — pure functions, testable without Frappe.

Delivery Hero (HungerStation in KSA) follows Delivery Hero's published POS
plugin contract:

* The middleware POSTs each order to ``{plugin base}/order/{remoteId}`` and
  retries until it gets a 2xx. The plugin must answer with the order's id on
  its side (``remoteResponse.remoteOrderId``) or no status updates follow.
* Requests carry ``Authorization: Bearer <JWT>``, HS512-signed with the plugin
  secret, with claim ``service`` = ``middleware``.
* Cancellations arrive as PUT ``/remoteId/{remoteId}/remoteOrder/{id}/posOrderStatus``.
* The plugin answers orders (accept, reject with a reason, picked up) on the
  callback URLs inside the order, with an OAuth token from the middleware.

Jahez and Keeta issue their integration specifications to onboarded partners
only. Their templates below follow the shape those integrations commonly take
(API key + secret, token exchange, order webhook, accept/reject calls) and are
**configuration, not certification**: every path and field name is editable on
the connection and must be checked against the spec the platform hands you.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

DH = "Delivery Hero (HungerStation)"

# ------------------------------------------------------------------ JWT


def _b64url_decode(s: str) -> bytes:
	return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64url(b: bytes) -> str:
	return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign_jwt_hs512(claims: dict, secret: str) -> str:
	header = _b64url(json.dumps({"alg": "HS512", "typ": "JWT"}, separators=(",", ":")).encode())
	body = _b64url(json.dumps(claims, separators=(",", ":")).encode())
	sig = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha512).digest()
	return f"{header}.{body}.{_b64url(sig)}"


def verify_dh_jwt(auth_header: str | None, secret: str | None, leeway: int = 300) -> tuple[bool, str]:
	"""Verify the middleware's bearer token. Returns (ok, reason)."""
	if not secret:
		return False, "plugin secret not configured"
	if not auth_header or not auth_header.lower().startswith("bearer "):
		return False, "missing bearer token"
	token = auth_header.split(" ", 1)[1].strip()
	parts = token.split(".")
	if len(parts) != 3:
		return False, "malformed token"
	try:
		header = json.loads(_b64url_decode(parts[0]))
		claims = json.loads(_b64url_decode(parts[1]))
		sig = _b64url_decode(parts[2])
	except Exception:
		return False, "undecodable token"
	if header.get("alg") != "HS512":
		return False, f"unexpected alg {header.get('alg')}"
	expected = hmac.new(secret.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha512).digest()
	if not hmac.compare_digest(expected, sig):
		return False, "bad signature"
	if claims.get("service") != "middleware":
		return False, "service claim is not middleware"
	exp = claims.get("exp")
	if exp is not None and time.time() > float(exp) + leeway:
		return False, "token expired"
	return True, "ok"


def verify_shared(headers: dict, raw: bytes, secret: str | None, auth: dict) -> tuple[bool, str]:
	"""Generic webhook auth: shared-secret header, HMAC-SHA256 of body, or Basic."""
	if not secret:
		return False, "webhook secret not configured"
	kind = (auth or {}).get("type", "header_secret")
	hname = (auth or {}).get("header", "X-Webhook-Secret")
	got = headers.get(hname) or headers.get(hname.lower()) or ""
	if kind == "header_secret":
		return (hmac.compare_digest(got.strip(), secret), "ok" if got else f"missing {hname}")
	if kind == "hmac_sha256":
		prefix = (auth or {}).get("prefix", "")
		val = got[len(prefix):] if prefix and got.startswith(prefix) else got
		exp = hmac.new(secret.encode(), raw or b"", hashlib.sha256).hexdigest()
		return (bool(val) and hmac.compare_digest(exp, val.strip().lower()), "ok")
	if kind == "basic":
		auth_h = headers.get("Authorization") or headers.get("authorization") or ""
		return (hmac.compare_digest(auth_h.strip(), "Basic " + secret), "ok")
	return False, f"unknown auth type {kind}"


# ------------------------------------------------------------------ helpers


def pick(obj, path: str | None, default=None):
	"""Dotted-path getter: 'price.grandTotal', 'items.0.id'."""
	if not path:
		return default
	cur = obj
	for part in path.split("."):
		if isinstance(cur, dict):
			cur = cur.get(part)
		elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
			cur = cur[int(part)]
		else:
			return default
		if cur is None:
			return default
	return cur


def _num(v) -> float:
	try:
		return float(v)
	except (TypeError, ValueError):
		return 0.0


def parse_dt(v) -> datetime | None:
	if not v:
		return None
	if isinstance(v, (int, float)):
		return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
	s = str(v).replace("Z", "+00:00")
	try:
		d = datetime.fromisoformat(s)
	except ValueError:
		return None
	return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ normal form
# Every adapter produces the same dict, so posting and the inbox see one shape:
# {external_order_id, order_token, short_code, remote_store_id, platform_store_ref,
#  is_test, expiry, pickup_time, expedition, customer_name, customer_note,
#  gross_total, delivery_fee, discount_total, vat_total, callbacks,
#  lines: [{external_code, external_name, qty, rate, note, toppings: [same]}]}


def normalize_dh(order: dict, remote_id: str) -> dict:
	exp = (order.get("expeditionType") or "").lower()
	expedition = "Pickup" if exp == "pickup" else (
		"Vendor delivery" if pick(order, "delivery.expressDelivery") is False and exp == "vendor" else "Platform delivery"
	)
	if exp in ("vendor", "own_delivery", "vendor_delivery"):
		expedition = "Vendor delivery"

	def toppings(lst):
		out = []
		for t in lst or []:
			out.append(
				{
					"external_code": str(t.get("remoteCode") or t.get("id") or t.get("name")),
					"external_name": t.get("name") or "",
					"qty": _num(t.get("quantity")) or 1,
					"rate": _num(t.get("price")),
					"note": "",
					"toppings": toppings(t.get("children")),
				}
			)
		return out

	lines = []
	for p in order.get("products") or []:
		lines.append(
			{
				"external_code": str(p.get("remoteCode") or p.get("id") or p.get("name")),
				"external_name": p.get("name") or "",
				"qty": _num(p.get("quantity")) or 1,
				"rate": _num(p.get("unitPrice") or p.get("paidPrice")),
				"note": p.get("comment") or "",
				"toppings": toppings(p.get("selectedToppings")),
			}
		)
	cust = order.get("customer") or {}
	fees = sum(_num(f.get("value")) for f in (pick(order, "price.deliveryFees") or []) if isinstance(f, dict))
	return {
		"external_order_id": str(order.get("code") or order.get("token")),
		"order_token": str(order.get("token") or order.get("code")),
		"short_code": str(order.get("shortCode") or order.get("code") or "")[:30],
		"remote_store_id": str(remote_id),
		"platform_store_ref": str(pick(order, "platformRestaurant.id") or ""),
		"is_test": bool(order.get("test")),
		"expiry": parse_dt(order.get("expiryDate")),
		"pickup_time": parse_dt(pick(order, "delivery.riderPickupTime")),
		"expedition": expedition,
		"customer_name": " ".join(x for x in (cust.get("firstName"), cust.get("lastName")) if x)[:140],
		"customer_note": pick(order, "comments.customerComment") or "",
		"gross_total": _num(pick(order, "price.grandTotal")),
		"delivery_fee": fees,
		"discount_total": sum(_num(d.get("amount")) for d in (order.get("discounts") or []) if isinstance(d, dict)),
		"vat_total": _num(pick(order, "price.vatTotal")),
		"callbacks": order.get("callbackUrls") or {},
		"lines": lines,
	}


def normalize_generic(payload: dict, mapping: dict) -> dict:
	m = mapping or {}
	g = lambda key, default=None: pick(payload, m.get(key), default)  # noqa: E731
	lines = []
	for it in g("items", []) or []:
		im = m.get("item", {})
		tops = []
		for t in pick(it, im.get("toppings"), []) or []:
			tops.append(
				{
					"external_code": str(pick(t, im.get("topping_code", "id")) or pick(t, "name")),
					"external_name": pick(t, im.get("topping_name", "name"), ""),
					"qty": _num(pick(t, im.get("topping_qty", "quantity"))) or 1,
					"rate": _num(pick(t, im.get("topping_price", "price"))),
					"note": "",
					"toppings": [],
				}
			)
		lines.append(
			{
				"external_code": str(pick(it, im.get("code", "id")) or pick(it, im.get("name", "name"))),
				"external_name": pick(it, im.get("name", "name"), ""),
				"qty": _num(pick(it, im.get("qty", "quantity"))) or 1,
				"rate": _num(pick(it, im.get("price", "price"))),
				"note": pick(it, im.get("note", "notes"), "") or "",
				"toppings": tops,
			}
		)
	oid = str(g("order_id") or "")
	return {
		"external_order_id": oid,
		"order_token": str(g("order_token") or oid),
		"short_code": str(g("short_code") or oid)[:30],
		"remote_store_id": str(g("store_id") or ""),
		"platform_store_ref": str(g("store_ref") or ""),
		"is_test": bool(g("is_test", False)),
		"expiry": parse_dt(g("expiry")),
		"pickup_time": parse_dt(g("pickup_time")),
		"expedition": {"pickup": "Pickup", "vendor": "Vendor delivery"}.get(str(g("expedition") or "").lower(), "Platform delivery"),
		"customer_name": str(g("customer_name") or "")[:140],
		"customer_note": g("note") or "",
		"gross_total": _num(g("total")),
		"delivery_fee": _num(g("delivery_fee")),
		"discount_total": _num(g("discount")),
		"vat_total": _num(g("vat")),
		"callbacks": {},
		"lines": lines,
	}


def generic_event(payload: dict, mapping: dict) -> str:
	"""Map a platform event/status to: new | cancelled | other."""
	raw = str(pick(payload, (mapping or {}).get("event")) or "new").lower()
	for ours, theirs in ((mapping or {}).get("events") or {}).items():
		if raw in [str(x).lower() for x in (theirs if isinstance(theirs, list) else [theirs])]:
			return ours
	return "new" if raw in ("new", "created", "order_created", "placed") else (
		"cancelled" if "cancel" in raw else "other"
	)


# ------------------------------------------------------------------ templates

TEMPLATES = {
	DH: {
		"login_path": "/v2/login",
		"token_ttl_margin_seconds": 300,
		"min_prep_minutes": 3,
		"reject_reasons": [
			"CLOSED", "ITEM_UNAVAILABLE", "TOO_BUSY", "ADDRESS_INCOMPLETE_MISSTYPED",
			"BLACKLISTED", "CONTENT_WRONG_MISLEADING", "FOOD_QUALITY_SPOILAGE", "NO_COURIER",
			"OUTSIDE_DELIVERY_AREA", "TECHNICAL_PROBLEM", "UNREACHABLE", "OTHER",
		],
		"_note": "Delivery Hero POS plugin contract. Status calls go to the callback URLs inside each order.",
	},
	"Jahez": {
		"_note": "TEMPLATE — confirm every path and field with the integration spec Jahez issues (integration@jahez.net).",
		"auth": {"type": "header_secret", "header": "X-Jahez-Secret"},
		"token": {"method": "POST", "path": "/token", "body": {"api_key": "{api_key}", "secret": "{api_secret}"},
		          "token_field": "data.token", "header": "Authorization", "prefix": "Bearer ", "ttl_seconds": 3000},
		"event": "event",
		"events": {"new": ["order_created", "new_order"], "cancelled": ["order_cancelled", "cancelled"]},
		"order_id": "order.id", "short_code": "order.order_number", "store_id": "order.branch_id",
		"items": "order.items", "item": {"code": "product_id", "name": "name", "qty": "quantity", "price": "price",
		                                 "note": "notes", "toppings": "modifiers", "topping_code": "id"},
		"total": "order.total", "delivery_fee": "order.delivery_fee", "vat": "order.vat",
		"customer_name": "order.customer.name", "note": "order.notes", "is_test": "order.is_test",
		"actions": {
			"accept": {"method": "POST", "path": "/orders/{order_id}/accept", "body": {"prep_time": "{prep_minutes}"}},
			"reject": {"method": "POST", "path": "/orders/{order_id}/reject", "body": {"reason": "{reason}"}},
			"ready": {"method": "POST", "path": "/orders/{order_id}/ready", "body": {}},
		},
		"reject_reasons": ["BUSY", "ITEM_UNAVAILABLE", "CLOSED", "OTHER"],
	},
	"Keeta": {
		"_note": "TEMPLATE — confirm every path and field with the Keeta open-platform spec issued at onboarding.",
		"auth": {"type": "hmac_sha256", "header": "X-Keeta-Signature", "prefix": ""},
		"token": {"method": "POST", "path": "/oauth/token",
		          "body": {"client_id": "{username}", "client_secret": "{password}", "grant_type": "client_credentials"},
		          "token_field": "access_token", "header": "Authorization", "prefix": "Bearer ", "ttl_seconds": 3000},
		"event": "event_type",
		"events": {"new": ["ORDER_CREATED"], "cancelled": ["ORDER_CANCELLED"]},
		"order_id": "data.order_id", "short_code": "data.pickup_code", "store_id": "data.shop_id",
		"items": "data.items", "item": {"code": "sku_id", "name": "name", "qty": "count", "price": "price",
		                                "note": "remark", "toppings": "options", "topping_code": "option_id"},
		"total": "data.total_amount", "delivery_fee": "data.delivery_fee", "customer_name": "data.customer_name",
		"note": "data.remark", "is_test": "data.is_test",
		"actions": {
			"accept": {"method": "POST", "path": "/order/confirm", "body": {"order_id": "{order_id}", "prep_minutes": "{prep_minutes}"}},
			"reject": {"method": "POST", "path": "/order/reject", "body": {"order_id": "{order_id}", "reason": "{reason}"}},
			"ready": {"method": "POST", "path": "/order/ready", "body": {"order_id": "{order_id}"}},
		},
		"reject_reasons": ["SHOP_BUSY", "OUT_OF_STOCK", "SHOP_CLOSED", "OTHER"],
	},
	"Generic JSON": {
		"_note": "Map any platform's webhook by dotted paths.",
		"auth": {"type": "header_secret", "header": "X-Webhook-Secret"},
		"event": "event", "order_id": "order.id", "store_id": "order.store_id", "items": "order.items",
		"item": {"code": "id", "name": "name", "qty": "quantity", "price": "price"},
		"total": "order.total", "actions": {}, "reject_reasons": ["OTHER"],
	},
}


def template_for(adapter: str) -> dict:
	return copy.deepcopy(TEMPLATES.get(adapter) or TEMPLATES["Generic JSON"])


def fill(obj, values: dict):
	"""Substitute {placeholders} in strings inside a JSON-like structure."""
	if isinstance(obj, str):
		for k, v in values.items():
			obj = obj.replace("{" + k + "}", str(v if v is not None else ""))
		return obj
	if isinstance(obj, dict):
		return {k: fill(v, values) for k, v in obj.items()}
	if isinstance(obj, list):
		return [fill(v, values) for v in obj]
	return obj


def dh_acceptance_time(now: datetime, prep_minutes: int, pickup: datetime | None, min_minutes: int = 3) -> str:
	"""Acceptance time for Delivery Hero: rider pickup when given, else now + prep (never under the minimum)."""
	from datetime import timedelta

	floor = now + timedelta(minutes=max(min_minutes, 1))
	target = pickup if pickup and pickup > floor else max(floor, now + timedelta(minutes=max(prep_minutes, min_minutes)))
	return target.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
