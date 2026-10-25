"""Gift card endpoints: till, desk and the public balance check."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from alphax_pos_suite.alphax_pos_suite.giftcard import service as S

TILL = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}
MGR = {"AlphaX POS Manager", "Accounts Manager", "System Manager"}


def _require(roles):
	if not roles & set(frappe.get_roles()):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def check(code: str, pin: str | None = None):
	"""Till: balance and a spend authorisation for this sale."""
	_require(TILL)
	return S.check(code, pin)


@frappe.whitelist(methods=["POST"])
def sell(value, mode_of_payment: str, outlet: str, terminal: str | None = None, code: str | None = None,
         purchaser: str | None = None, recipient_name: str = "", recipient_phone: str = "", message: str = "",
         client_uuid: str | None = None):
	_require(TILL)
	return S.sell(value=value, mode_of_payment=mode_of_payment, outlet=outlet, terminal=terminal, code=code,
	              purchaser=purchaser, recipient_name=recipient_name, recipient_phone=recipient_phone,
	              message=message, client_uuid=client_uuid)


@frappe.whitelist(methods=["POST"])
def reload(code: str, value, mode_of_payment: str, outlet: str, terminal: str | None = None, client_uuid: str | None = None):
	_require(TILL)
	return S.reload(code=code, value=value, mode_of_payment=mode_of_payment, outlet=outlet, terminal=terminal,
	                client_uuid=client_uuid)


@frappe.whitelist()
def statement(card: str):
	_require(TILL)
	c = frappe.get_doc(S.CARD, card)
	return {"card": c.masked_code, "status": c.status, "balance": c.balance, "expires_on": str(c.expires_on or ""),
	        "entries": frappe.get_all(S.ENTRY, filters={"gift_card": card},
	                                  fields=["creation", "entry_type", "amount", "balance_after", "reference_doctype",
	                                          "reference_name", "outlet", "remarks"], order_by="creation desc", limit=100)}


@frappe.whitelist(methods=["POST"])
def lookup(code: str):
	"""Desk: find a card by number (for statement or void)."""
	_require(TILL)
	return S.find(code)


@frappe.whitelist(methods=["POST"])
def refund_and_void(card: str, mode_of_payment: str, reason: str):
	_require(MGR)
	if not (reason or "").strip():
		frappe.throw(_("Give a reason."))
	return S.refund_and_void(card, mode_of_payment, reason)


@frappe.whitelist(methods=["POST"])
def generate_batch(batch: str):
	_require(MGR)
	return S.generate_batch(batch)


@frappe.whitelist(methods=["POST"])
def activate_batch(batch: str, outlet: str):
	_require(MGR)
	return S.activate_batch(batch, outlet)


@frappe.whitelist(methods=["POST"])
def setup(company: str):
	_require({"System Manager", "Accounts Manager"})
	return S.ensure_setup(company)


@frappe.whitelist(allow_guest=True)
def balance(code: str, pin: str | None = None):
	"""Public balance check: masked number, balance and expiry only; 10 per hour per IP."""
	ip = getattr(frappe.local, "request_ip", None) or "unknown"
	k = frappe.cache.make_key(f"alphax_gc_balance:{ip}")
	n = cint(frappe.cache.incr(k))
	if n == 1:
		frappe.cache.expire(k, 3600)
	if n > 10:
		frappe.throw(_("Too many balance checks. Try again later."))
	res = S.check(code, pin, authorise=False)
	return {k2: res.get(k2) for k2 in ("ok", "pin_required", "masked", "balance", "expires_on", "currency")}
