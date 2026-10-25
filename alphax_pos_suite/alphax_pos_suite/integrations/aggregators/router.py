"""Inbound HTTP for delivery platforms, served at /aggregator/<connection>/...

Served from a ``before_request`` hook, ahead of Frappe's own routing, because
the platforms call fixed paths and methods that Frappe would refuse:

* Delivery Hero appends /order/{remoteId} to the plugin base URL, which an
  /api/method route cannot express;
* its cancellation call is a PUT, and Frappe serves website paths for GET,
  HEAD and POST only;
* it authenticates with ``Authorization: Bearer <JWT>``, which Frappe's own
  auth would try to resolve as an OAuth token and reject with 401.

The hook answers only paths under /aggregator/ and leaves every other request
untouched. It commits its own writes before handing the response back.

    POST /aggregator/<conn>/order/<remoteId>                                 DH dispatch
    PUT  /aggregator/<conn>/remoteId/<rid>/remoteOrder/<oid>/posOrderStatus  DH status (cancel)
    POST /aggregator/<conn>/webhook                                          Jahez / Keeta / generic
    GET  /aggregator/<conn>/health                                           liveness
"""

from __future__ import annotations

import json

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import protocol as P
from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import service as S

PREFIX = "aggregator/"


def _json(status: int, body: dict) -> Response:
	return Response(json.dumps(body), status=status, mimetype="application/json")


class _Answer(HTTPException):
	"""Carries a finished response out of before_request."""

	code = 200

	def __init__(self, response: Response):
		super().__init__(response=response)


def before_request():
	req = getattr(frappe.local, "request", None)
	if not req or not (req.path or "").lstrip("/").startswith(PREFIX):
		return
	raise _Answer(AggregatorRenderer(req.path).render())


class AggregatorRenderer:
	def __init__(self, path=None, http_status_code=None):
		self.path = (path or frappe.local.request.path or "").strip("/ ")

	def can_render(self) -> bool:
		return self.path.startswith(PREFIX)

	def render(self) -> Response:
		try:
			resp = self._handle()
			frappe.db.commit()
			return resp
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="AlphaX aggregator: inbound failed", message=frappe.get_traceback())
			return _json(500, {"error": "internal error"})

	def _handle(self) -> Response:
		req = frappe.local.request
		parts = self.path[len(PREFIX):].split("/")
		conn_name = parts[0] if parts else ""
		rest = parts[1:]
		if not conn_name or not frappe.db.exists(S.CONN, conn_name):
			return _json(404, {"error": "unknown connection"})
		conn = S.conn_doc(conn_name)
		if rest[:1] == ["health"]:
			return _json(200, {"ok": True, "enabled": bool(conn.enabled)})

		raw = req.get_data() or b""
		headers = {k: v for k, v in req.headers.items()}
		try:
			body = json.loads(raw) if raw else {}
		except ValueError:
			S.log(conn_name, "Inbound", "/" + self.path, 400, False, raw.decode(errors="ignore")[:4000], note="bad json")
			return _json(400, {"error": "invalid json"})

		# --- authenticate before anything touches the database
		if conn.adapter == P.DH:
			ok, why = P.verify_dh_jwt(headers.get("Authorization"), S.secret(conn, "webhook_secret"))
		else:
			ok, why = P.verify_shared(headers, raw, S.secret(conn, "webhook_secret"), S.proto(conn).get("auth"))
		if not ok:
			S.log(conn_name, "Inbound", "/" + self.path, 401, False, body, note=f"auth: {why}")
			return _json(401, {"error": "unauthorized"})
		if not conn.enabled:
			S.log(conn_name, "Inbound", "/" + self.path, 503, False, body, note="connection disabled")
			return _json(503, {"error": "integration disabled"})

		if conn.adapter == P.DH:
			return self._dh(conn, rest, body, req.method)
		return self._generic(conn, rest, body)

	# ------------------------------------------------------------ Delivery Hero
	def _dh(self, conn, rest, body, method):
		if method == "POST" and len(rest) == 2 and rest[0] == "order":
			normal = P.normalize_dh(body, rest[1])
			if not normal["order_token"] or normal["order_token"] == "None":
				S.log(conn.name, "Inbound", "/" + self.path, 400, False, body, note="no token")
				return _json(400, {"error": "order token missing"})
			name, created = S.ingest(conn.name, normal, body)
			S.log(conn.name, "Inbound", "/" + self.path, 200, True, body, order=name,
			      note="dispatch" if created else "dispatch retry (idempotent)")
			return _json(200, {"remoteResponse": {"remoteOrderId": name}})

		if method == "PUT" and len(rest) == 5 and rest[0] == "remoteId" and rest[4] == "posOrderStatus":
			order = rest[3] if frappe.db.exists(S.ORDER, rest[3]) else None
			status = str(body.get("status") or "").upper()
			if order and "CANCEL" in status:
				S.platform_cancelled(order, body.get("message") or status)
			S.log(conn.name, "Inbound", "/" + self.path, 200 if order else 404, bool(order), body, order=order, note=status)
			return _json(200 if order else 404, {} if order else {"error": "unknown order"})

		S.log(conn.name, "Inbound", "/" + self.path, 404, False, body, note=f"unsupported {method}")
		return _json(404, {"error": "not supported"})

	# ------------------------------------------------------------ generic
	def _generic(self, conn, rest, body):
		if rest[:1] != ["webhook"]:
			return _json(404, {"error": "not supported"})
		cfg = S.proto(conn)
		event = P.generic_event(body, cfg)
		normal = P.normalize_generic(body, cfg)
		if event == "new":
			if not normal["external_order_id"]:
				S.log(conn.name, "Inbound", "/" + self.path, 400, False, body, note="no order id")
				return _json(400, {"error": "order id missing"})
			name, created = S.ingest(conn.name, normal, body)
			S.log(conn.name, "Inbound", "/" + self.path, 200, True, body, order=name, note="new" if created else "retry")
			return _json(200, {"ok": True, "reference": name})
		if event == "cancelled":
			name = frappe.db.get_value(S.ORDER, {"order_token": normal["order_token"] or normal["external_order_id"]})
			if name:
				S.platform_cancelled(name, "cancelled by platform")
			S.log(conn.name, "Inbound", "/" + self.path, 200, bool(name), body, order=name, note="cancel")
			return _json(200, {"ok": bool(name)})
		S.log(conn.name, "Inbound", "/" + self.path, 200, True, body, note=f"ignored event {event}")
		return _json(200, {"ok": True, "ignored": True})
