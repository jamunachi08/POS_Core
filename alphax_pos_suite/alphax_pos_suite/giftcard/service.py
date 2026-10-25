"""AlphaX Wallet gift cards: sell, check, redeem at the till, reload, expire.

Accounting and VAT
------------------
* A gift card sold for money is a **liability**, not revenue: the sale posts
  Dr the tender's account / Cr the gift card liability account. No Sales
  Invoice, because nothing has been supplied yet.
* It is treated as a **multi-purpose voucher**: no VAT when the card is sold;
  VAT arises when it is spent, on the invoice for the goods, at their rates.
  (Confirm the treatment for your product mix with your tax adviser.)
* Spending: the Sales Invoice carries a payment line on the gift card Mode of
  Payment, whose account is the liability account, so the invoice itself
  releases the liability. The ledger entry here references the invoice and
  posts no journal of its own.
* Expiry moves any remaining balance to the breakage account (if set).

Security
--------
* Only an HMAC of the card number (keyed with the site's encryption key) is
  stored, plus the last four digits. The full number is returned once, when
  the card is created.
* Card numbers carry a Luhn check digit.
* Cards from the PIN threshold up need a 4-digit PIN; five wrong PINs lock the
  card for 30 minutes.
* The till gets a short-lived authorisation token after a successful check;
  the invoice carries the token, never the card number.
* Balance changes lock the card row and re-check the balance in the same
  transaction, so two tills cannot spend the same balance.
"""

from __future__ import annotations

import json
import secrets

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, now_datetime, nowdate

from alphax_pos_suite.alphax_pos_suite.giftcard import codes as C

CARD = "AlphaX Gift Card"
ENTRY = "AlphaX Gift Card Entry"
TOKEN_TTL = 24 * 3600  # offline tills may sync late; the balance is re-checked at submit anyway
MAX_PIN_TRIES = 5


# ------------------------------------------------------------------ settings


def settings():
	s = frappe.get_cached_doc("AlphaX POS Settings")
	return frappe._dict(
		mop=s.get("gift_card_mode_of_payment"),
		liability=s.get("gift_card_liability_account"),
		breakage=s.get("gift_card_breakage_account"),
		validity=cint(s.get("gift_card_validity_days") or 365),
		pin_from=flt(s.get("gift_card_pin_threshold") or 0),
		max_value=flt(s.get("gift_card_max_value") or 0),
	)


def _key() -> str:
	from frappe.utils.password import get_encryption_key

	return get_encryption_key()


def _hash(code: str) -> str:
	return C.keyed_hash("card:" + C.normalise(code), _key())


def _pin_hash(card_hash: str, pin: str) -> str:
	return C.keyed_hash(f"pin:{card_hash}:{pin}", _key())


def _liability(company: str) -> str:
	s = settings()
	acct = s.liability
	if not acct or frappe.db.get_value("Account", acct, "company") != company:
		frappe.throw(_("Set the gift card liability account for {0} in AlphaX POS Settings.").format(company))
	return acct


def _mop_account(mop: str, company: str) -> str:
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	acct = (get_bank_cash_account(mop, company) or {}).get("account")
	if not acct:
		frappe.throw(_("Mode of Payment {0} has no account for {1}.").format(mop, company))
	return acct


# ------------------------------------------------------------------ ledger


def _card_for_update(name: str):
	frappe.db.sql(f"select name from `tab{CARD}` where name=%s for update", name)
	return frappe.get_doc(CARD, name)


def _post(card, entry_type: str, amount: float, *, ref=None, mop=None, outlet=None, terminal=None,
          client_uuid=None, remarks="", journal=None) -> str:
	sign = 1 if entry_type in ("Issue", "Reload", "Reverse") else -1
	new_balance = round(flt(card.balance) + sign * flt(amount), 2)
	if new_balance < -0.005:
		frappe.throw(_("Gift card {0} has only {1} left.").format(card.masked_code, card.balance))
	e = frappe.get_doc({
		"doctype": ENTRY, "gift_card": card.name, "entry_type": entry_type, "amount": flt(amount),
		"balance_after": new_balance, "posting_date": nowdate(), "outlet": outlet, "terminal": terminal,
		"mode_of_payment": mop, "reference_doctype": ref[0] if ref else None,
		"reference_name": ref[1] if ref else None, "client_uuid": client_uuid, "remarks": remarks[:500],
		"journal_entry": journal,
	}).insert(ignore_permissions=True)
	status = card.status
	if new_balance <= 0.005 and entry_type == "Redeem":
		status = "Used Up"
	elif new_balance > 0 and card.status == "Used Up":
		status = "Active"
	card.db_set({"balance": max(new_balance, 0), "status": status}, update_modified=True)
	return e.name


def _journal(company, debit_acct, credit_acct, amount, remark, party_side=None, customer=None) -> str:
	rows = [
		{"account": debit_acct, "debit_in_account_currency": flt(amount)},
		{"account": credit_acct, "credit_in_account_currency": flt(amount)},
	]
	for r in rows:
		if customer and frappe.db.get_value("Account", r["account"], "account_type") == "Receivable":
			r.update({"party_type": "Customer", "party": customer})
	je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": company,
	                     "posting_date": nowdate(), "user_remark": remark, "accounts": rows})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


# ------------------------------------------------------------------ create & sell


def create_card(company: str, *, batch=None, pin_required=False, expires_on=None) -> tuple:
	"""A new inactive card. Returns (doc, number, pin). Number and PIN are not stored."""
	for _ in range(5):
		number = C.new_number()
		h = _hash(number)
		if not frappe.db.exists(CARD, {"code_hash": h}):
			break
	else:
		frappe.throw(_("Could not generate a unique card number; try again."))
	pin = C.new_pin() if pin_required else None
	doc = frappe.get_doc({
		"doctype": CARD, "masked_code": C.masked(number), "code_hash": h, "status": "Inactive",
		"company": company, "currency": frappe.get_cached_value("Company", company, "default_currency"),
		"batch": batch, "pin_required": 1 if pin else 0, "pin_hash": _pin_hash(h, pin) if pin else None,
		"expires_on": expires_on, "liability_account": settings().liability,
	}).insert(ignore_permissions=True)
	return doc, number, pin


def find(code: str):
	number = C.normalise(code)
	if not C.luhn_ok(number):
		frappe.throw(_("That is not a valid gift card number. Check the digits."))
	name = frappe.db.get_value(CARD, {"code_hash": _hash(number)})
	if not name:
		frappe.throw(_("No gift card with that number."))
	return name


def sell(*, value: float, mode_of_payment: str, outlet: str, terminal: str | None = None, code: str | None = None,
         purchaser=None, recipient_name="", recipient_phone="", message="", client_uuid=None) -> dict:
	s = settings()
	value = round(flt(value), 2)
	if value <= 0:
		frappe.throw(_("Enter the card value."))
	if s.max_value and value > s.max_value:
		frappe.throw(_("The largest card this store sells is {0}.").format(s.max_value))
	if client_uuid:
		done = frappe.db.get_value(ENTRY, {"client_uuid": client_uuid}, "gift_card")
		if done:
			c = frappe.get_doc(CARD, done)
			return {"ok": True, "duplicate": True, "masked": c.masked_code, "balance": c.balance}
	company = frappe.db.get_value("AlphaX POS Outlet", outlet, "company")
	liability = _liability(company)
	number = pin = None
	if code:
		card = _card_for_update(find(code))
		if card.status != "Inactive":
			frappe.throw(_("Card {0} is already {1}.").format(card.masked_code, card.status))
	else:
		card, number, pin = create_card(company, pin_required=bool(s.pin_from and value >= s.pin_from))
		card = _card_for_update(card.name)
	je = _journal(company, _mop_account(mode_of_payment, company), liability, value,
	              f"Gift card {card.masked_code} sold", customer=purchaser)
	card.db_set({
		"status": "Active", "initial_value": value, "issued_on": now_datetime(), "outlet": outlet,
		"expires_on": card.expires_on or add_days(nowdate(), s.validity), "purchaser": purchaser,
		"recipient_name": (recipient_name or "")[:140], "recipient_phone": (recipient_phone or "")[:30],
		"message": (message or "")[:500],
	})
	_post(card, "Issue", value, ref=("Journal Entry", je), mop=mode_of_payment, outlet=outlet, terminal=terminal,
	      client_uuid=client_uuid, journal=je, remarks="Sold")
	card.reload()
	return {"ok": True, "card": card.name, "masked": card.masked_code, "balance": card.balance,
	        "expires_on": str(card.expires_on), "number": C.pretty(number) if number else None, "pin": pin}


def reload(*, code: str, value: float, mode_of_payment: str, outlet: str, terminal=None, client_uuid=None) -> dict:
	s = settings()
	card = _card_for_update(find(code))
	if card.status not in ("Active", "Used Up"):
		frappe.throw(_("Card {0} is {1} and cannot be reloaded.").format(card.masked_code, card.status))
	value = round(flt(value), 2)
	if value <= 0 or (s.max_value and flt(card.balance) + value > s.max_value):
		frappe.throw(_("A card can hold at most {0}.").format(s.max_value))
	je = _journal(card.company, _mop_account(mode_of_payment, card.company), _liability(card.company), value,
	              f"Gift card {card.masked_code} reloaded")
	_post(card, "Reload", value, ref=("Journal Entry", je), mop=mode_of_payment, outlet=outlet, terminal=terminal,
	      client_uuid=client_uuid, journal=je, remarks="Reloaded")
	card.reload()
	return {"ok": True, "masked": card.masked_code, "balance": card.balance}


# ------------------------------------------------------------------ check & authorise


def check(code: str, pin: str | None = None, *, authorise: bool = True) -> dict:
	card = frappe.get_doc(CARD, find(code))
	if card.locked_until and get_datetime(card.locked_until) > now_datetime():
		frappe.throw(_("Too many wrong PINs. The card is locked for a few minutes."))
	if card.status not in ("Active",):
		frappe.throw(_("Card {0} is {1}.").format(card.masked_code, _(card.status)))
	if card.expires_on and str(card.expires_on) < nowdate():
		frappe.throw(_("Card {0} expired on {1}.").format(card.masked_code, card.expires_on))
	if card.pin_required:
		if not pin:
			return {"ok": False, "pin_required": True, "masked": card.masked_code}
		if _pin_hash(card.code_hash, str(pin).strip()) != card.pin_hash:
			tries = cint(card.failed_attempts) + 1
			upd = {"failed_attempts": tries}
			if tries >= MAX_PIN_TRIES:
				upd = {"failed_attempts": 0, "locked_until": add_to_date(now_datetime(), minutes=30)}
			card.db_set(upd, update_modified=False)
			frappe.db.commit()
			frappe.throw(_("Wrong PIN."))
		if card.failed_attempts:
			card.db_set("failed_attempts", 0, update_modified=False)
	out = {"ok": True, "masked": card.masked_code, "balance": flt(card.balance), "expires_on": str(card.expires_on or ""),
	       "currency": card.currency}
	if authorise:
		token = secrets.token_urlsafe(18)
		frappe.cache.set_value(f"alphax_gc_auth:{token}", card.code_hash, expires_in_sec=TOKEN_TTL)
		out["token"] = token
	return out


# ------------------------------------------------------------------ till hooks (Sales Invoice)


def _parse(doc) -> list[dict]:
	raw = doc.get("alphax_gift_cards")
	if not raw:
		return []
	try:
		rows = json.loads(raw)
	except ValueError:
		frappe.throw(_("Gift card data on this invoice is unreadable."))
	return rows if isinstance(rows, list) else []


def invoice_validate(doc, method=None):
	rows = _parse(doc)
	if not rows:
		return
	if doc.get("is_return"):
		frappe.throw(_("Refunds cannot be paid back onto a gift card here. Refund to store credit or cash."))
	s = settings()
	if not s.mop:
		frappe.throw(_("Set the gift card Mode of Payment in AlphaX POS Settings."))
	resolved, per_card = [], {}
	for r in rows:
		amount = round(flt(r.get("amount")), 2)
		h = r.get("hash")
		if not h:
			h = frappe.cache.get_value(f"alphax_gc_auth:{r.get('token')}") if r.get("token") else None
			if not h:
				frappe.throw(_("A gift card on this sale was not authorised or its check has expired. Check the card again."))
		card = frappe.db.get_value(CARD, {"code_hash": h}, ["name", "masked_code", "balance", "status", "expires_on", "company"], as_dict=True)
		if not card:
			frappe.throw(_("Unknown gift card on this sale."))
		if card.company != doc.company:
			frappe.throw(_("Gift card {0} belongs to another company.").format(card.masked_code))
		per_card[card.name] = per_card.get(card.name, 0) + amount
		if card.status != "Active" or (card.expires_on and str(card.expires_on) < str(doc.posting_date)):
			frappe.throw(_("Gift card {0} cannot be used ({1}).").format(card.masked_code, card.status))
		if per_card[card.name] > flt(card.balance) + 0.005:
			frappe.throw(_("Gift card {0} has only {1} left.").format(card.masked_code, card.balance))
		resolved.append({"hash": h, "amount": amount, "masked": card.masked_code})
	paid = round(sum(flt(p.amount) for p in doc.get("payments") or [] if p.mode_of_payment == s.mop), 2)
	used = round(sum(r["amount"] for r in resolved), 2)
	if abs(paid - used) > 0.01:
		frappe.throw(_("Gift card payments ({0}) do not match the cards applied ({1}).").format(paid, used))
	doc.alphax_gift_cards = json.dumps(resolved)  # tokens are spent; the invoice keeps hashes only


def invoice_on_submit(doc, method=None):
	for r in _parse(doc):
		name = frappe.db.get_value(CARD, {"code_hash": r["hash"]})
		card = _card_for_update(name)
		_post(card, "Redeem", flt(r["amount"]), ref=("Sales Invoice", doc.name), outlet=doc.get("alphax_outlet"),
		      terminal=doc.get("alphax_pos_terminal"), remarks="Spent at the till")


def invoice_on_cancel(doc, method=None):
	for e in frappe.get_all(ENTRY, filters={"reference_doctype": "Sales Invoice", "reference_name": doc.name,
	                        "entry_type": "Redeem"}, fields=["gift_card", "amount"]):
		card = _card_for_update(e.gift_card)
		if card.status == "Used Up":
			card.status = "Active"
		_post(card, "Reverse", flt(e.amount), ref=("Sales Invoice", doc.name), remarks="Invoice cancelled")


# ------------------------------------------------------------------ void, expiry, batches


def refund_and_void(card_name: str, mode_of_payment: str, reason: str) -> dict:
	card = _card_for_update(card_name)
	if card.status in ("Voided", "Expired"):
		frappe.throw(_("Card is already {0}.").format(card.status))
	je = None
	if flt(card.balance) > 0:
		je = _journal(card.company, _liability(card.company), _mop_account(mode_of_payment, card.company), card.balance,
		              f"Gift card {card.masked_code} refunded and voided: {reason}")
		_post(card, "Refund", flt(card.balance), ref=("Journal Entry", je), mop=mode_of_payment, journal=je, remarks=reason)
	card.db_set("status", "Voided")
	return {"ok": True, "journal_entry": je}


def expire_cards():
	"""Daily: retire balances on expired cards to the breakage account."""
	s = settings()
	for c in frappe.get_all(CARD, filters={"status": "Active", "expires_on": ["<", nowdate()]}, pluck="name"):
		card = _card_for_update(c)
		je = None
		if flt(card.balance) > 0 and s.breakage and s.liability:
			je = _journal(card.company, _liability(card.company), s.breakage, card.balance,
			              f"Gift card {card.masked_code} expired")
		if flt(card.balance) > 0:
			_post(card, "Expiry", flt(card.balance), ref=("Journal Entry", je) if je else None, journal=je,
			      remarks="Expired" + ("" if je else " — no breakage account set; balance kept as liability"))
		card.db_set("status", "Expired")
		frappe.db.commit()


def generate_batch(batch_name: str) -> str:
	b = frappe.get_doc("AlphaX Gift Card Batch", batch_name)
	if b.status != "Draft":
		frappe.throw(_("Batch {0} is already {1}.").format(b.name, b.status))
	if cint(b.quantity) <= 0 or cint(b.quantity) > 5000:
		frappe.throw(_("A batch holds 1 to 5000 cards."))
	s = settings()
	lines = ["number,pin,value,expires_on"]
	for _ in range(cint(b.quantity)):
		card, number, pin = create_card(b.company, batch=b.name, pin_required=bool(s.pin_from and flt(b.value) >= s.pin_from),
		                                expires_on=b.expires_on)
		lines.append(f"{C.pretty(number)},{pin or ''},{flt(b.value):.2f},{b.expires_on or ''}")
	f = frappe.get_doc({"doctype": "File", "file_name": f"{b.name}-cards.csv", "is_private": 1,
	                    "attached_to_doctype": "AlphaX Gift Card Batch", "attached_to_name": b.name,
	                    "content": "\n".join(lines)}).insert(ignore_permissions=True)
	b.db_set({"status": "Generated", "codes_file": f.file_url})
	return f.file_url


def activate_batch(batch_name: str, outlet: str) -> dict:
	b = frappe.get_doc("AlphaX Gift Card Batch", batch_name)
	if b.status != "Generated":
		frappe.throw(_("Generate the batch first."))
	if not b.mode_of_payment:
		frappe.throw(_("Set how the batch was paid for."))
	cards = frappe.get_all(CARD, filters={"batch": b.name, "status": "Inactive"}, pluck="name")
	total = round(flt(b.value) * len(cards), 2)
	je = _journal(b.company, _mop_account(b.mode_of_payment, b.company), _liability(b.company), total,
	              f"Gift card batch {b.name}: {len(cards)} × {b.value}", customer=b.customer)
	s = settings()
	for name in cards:
		card = _card_for_update(name)
		card.db_set({"status": "Active", "initial_value": flt(b.value), "issued_on": now_datetime(), "outlet": outlet,
		             "expires_on": b.expires_on or add_days(nowdate(), s.validity), "purchaser": b.customer})
		_post(card, "Issue", flt(b.value), ref=("Journal Entry", je), mop=b.mode_of_payment, outlet=outlet, journal=je,
		      remarks=f"Batch {b.name}")
	b.db_set("status", "Activated")
	return {"ok": True, "cards": len(cards), "journal_entry": je}


# ------------------------------------------------------------------ setup


def ensure_setup(company: str) -> list[str]:
	"""Create the gift card Mode of Payment and wire it to the liability account."""
	notes = []
	s = frappe.get_doc("AlphaX POS Settings")
	abbr = frappe.get_cached_value("Company", company, "abbr")
	acct = s.get("gift_card_liability_account")
	if not acct:
		parent = frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1,
		                             "account_name": ["in", ["Current Liabilities", "Duties and Taxes"]]}, "name")
		name = f"Gift Cards Payable - {abbr}"
		if not frappe.db.exists("Account", name) and parent:
			frappe.get_doc({"doctype": "Account", "account_name": "Gift Cards Payable", "parent_account": parent,
			                "company": company, "root_type": "Liability", "account_type": ""}).insert(ignore_permissions=True)
			notes.append(_("Created account {0}.").format(name))
		if frappe.db.exists("Account", name):
			s.gift_card_liability_account = name
			acct = name
	mop = s.get("gift_card_mode_of_payment") or "Gift Card"
	if not frappe.db.exists("Mode of Payment", mop):
		frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": mop, "type": "General", "enabled": 1}).insert(ignore_permissions=True)
		notes.append(_("Created Mode of Payment {0}.").format(mop))
	s.gift_card_mode_of_payment = mop
	if acct:
		m = frappe.get_doc("Mode of Payment", mop)
		row = next((r for r in m.accounts if r.company == company), None)
		if not row:
			m.append("accounts", {"company": company, "default_account": acct})
			m.save(ignore_permissions=True)
			notes.append(_("Linked {0} to {1} for {2}.").format(mop, acct, company))
		elif row.default_account != acct:
			notes.append(_("Mode of Payment {0} points to {1}, not the gift card liability {2}. Change it, or gift card sales will hit the wrong account.").format(mop, row.default_account, acct))
	else:
		notes.append(_("No liability account could be created; pick one in AlphaX POS Settings."))
	s.save(ignore_permissions=True)
	return notes
