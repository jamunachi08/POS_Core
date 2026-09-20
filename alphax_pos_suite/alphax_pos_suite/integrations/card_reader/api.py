"""
AlphaX POS — Card payment whitelisted endpoints.

These three endpoints implement the cashier-side card flow:

    request_card_payment(...)   - cashier kicks off a transaction
    card_payment_callback(...)  - card reader posts back (called by reader)
    get_card_payment_status(...) - cashier polls for the final result

The cashier UI's flow:
    1. Build a uuid (uuid4)
    2. POST request_card_payment with {uuid, amount, terminal}
    3. Show "Waiting for card..." dialog
    4. Poll get_card_payment_status every 1s until status != 'Pending'
    5. If 'Approved', complete the sale and record the card_transaction
       link on the Sales Invoice
"""
from __future__ import annotations

import json
import time

import frappe
from frappe import _
from frappe.utils import now_datetime

# Import adapters to trigger their @register_adapter side effects
from . import base, geidea  # noqa: F401  (registration happens on import)
from .base import (
    CardPaymentRequest,
    get_adapter_for_reader,
    list_available_vendors,
)


def _resolve_card_reader_for_context(
    card_reader: str | None,
    alphax_terminal: str | None,
    user: str | None,
) -> dict | None:
    """Find the right card reader doc for this transaction.

    Resolution order:
        1. Explicit card_reader name (passed by cashier UI)
        2. By alphax_terminal — find the active reader linked to it
        3. By user — find the active reader linked to this user

    Returns the reader's full doc as a dict, or None if not found.
    """
    if card_reader:
        if frappe.db.exists("AlphaX POS Card Reader", card_reader):
            return frappe.get_doc("AlphaX POS Card Reader", card_reader).as_dict()

    # By terminal
    if alphax_terminal:
        name = frappe.db.get_value(
            "AlphaX POS Card Reader",
            {"alphax_terminal": alphax_terminal, "is_active": 1},
            "name",
        )
        if name:
            return frappe.get_doc("AlphaX POS Card Reader", name).as_dict()

    # By user
    if user:
        name = frappe.db.get_value(
            "AlphaX POS Card Reader",
            {"user": user, "is_active": 1},
            "name",
        )
        if name:
            return frappe.get_doc("AlphaX POS Card Reader", name).as_dict()

    return None


@frappe.whitelist()
def request_card_payment(
    transaction_uuid: str,
    amount: float,
    currency: str = "SAR",
    is_refund: int | bool = 0,
    original_rrn: str | None = None,
    original_posting_date: str | None = None,
    alphax_terminal: str | None = None,
    card_reader: str | None = None,
) -> dict:
    """Initiate a card payment.

    Parameters
    ----------
    transaction_uuid : str
        Client-generated unique ID. Use uuid.uuid4() in the cashier.
        Used as the idempotency key — calling this twice with the same
        uuid won't trigger a double charge.
    amount : float
        Transaction amount in the reader's currency.
    currency : str
        ISO currency code. Defaults to SAR.
    is_refund : bool
        If true, requires original_rrn and original_posting_date.
    alphax_terminal : str
        The AlphaX terminal this cashier is on. Used to look up the
        right card reader if `card_reader` is not specified.
    card_reader : str
        Explicit card reader name. Overrides terminal-based lookup.

    Returns
    -------
    dict
        {
          "ok": True,
          "transaction_uuid": str,
          "transaction": str,        # AlphaX POS Card Transaction name
          "status": "Pending",
          "card_reader": str,        # which reader was used
          "vendor": str,
        }
        Or on failure:
        {"ok": False, "error": "..."}
    """
    if not transaction_uuid:
        return {"ok": False, "error": _("transaction_uuid is required")}

    try:
        amount_f = float(amount)
    except (ValueError, TypeError):
        return {"ok": False, "error": _("amount must be a number")}

    if amount_f <= 0:
        return {"ok": False, "error": _("amount must be > 0")}

    # Find a card reader
    reader_cfg = _resolve_card_reader_for_context(
        card_reader=card_reader,
        alphax_terminal=alphax_terminal,
        user=frappe.session.user,
    )
    if not reader_cfg:
        return {
            "ok": False,
            "error": _("No card reader configured for this terminal or user. "
                       "Ask your administrator to add an AlphaX POS Card Reader."),
        }
    if not reader_cfg.get("is_active"):
        return {"ok": False, "error": _("Card reader is not active.")}

    # Get the right adapter
    try:
        adapter = get_adapter_for_reader(reader_cfg)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Build the request
    req = CardPaymentRequest(
        transaction_uuid=str(transaction_uuid),
        amount=amount_f,
        currency=currency or "SAR",
        is_refund=bool(int(is_refund)) if is_refund else False,
        original_rrn=original_rrn,
        original_posting_date=original_posting_date,
        cashier_user=frappe.session.user,
        metadata={"alphax_terminal": alphax_terminal},
    )

    # Audit FIRST — so even if the publish fails, we have a record
    txn_name = adapter.create_pending_transaction(
        req,
        vendor=adapter.vendor,
        card_reader_name=reader_cfg.get("name"),
    )

    # Now publish to the reader
    publish_result = adapter.initiate_payment(req)
    if not publish_result.get("ok"):
        # Mark the transaction as errored
        try:
            doc = frappe.get_doc("AlphaX POS Card Transaction", txn_name)
            doc.status = "Error"
            doc.response_message = publish_result.get("error", "Unknown publish error")
            doc.responded_at = now_datetime()
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass
        return {"ok": False, "error": publish_result.get("error"), "transaction": txn_name}

    return {
        "ok": True,
        "transaction_uuid": req.transaction_uuid,
        "transaction": txn_name,
        "status": "Pending",
        "card_reader": reader_cfg.get("name"),
        "vendor": adapter.vendor,
    }


@frappe.whitelist(allow_guest=True)
def card_payment_callback() -> dict:
    """Callback endpoint for card readers to post their response.

    Public (allow_guest=True) because card readers can't authenticate
    as Frappe users. Security is via the transaction UUID being
    long-lived and unguessable.

    The reader POSTs a JSON body. We dispatch to the right adapter
    based on the matching pending transaction's vendor field.

    Returns
    -------
    dict
        {"ok": True, "uuid": <uuid>, "transaction": <name>}
        Or {"ok": False, "error": "..."}
    """
    try:
        data = json.loads(frappe.request.data) if frappe.request.data else {}
    except Exception:
        return {"ok": False, "error": "Invalid JSON payload"}

    uuid = data.get("uuid") or data.get("transactionId") or data.get("transaction_uuid")
    if not uuid:
        return {"ok": False, "error": "uuid is required in callback"}

    # Look up the pending transaction to find which adapter to use
    existing = frappe.db.get_value(
        "AlphaX POS Card Transaction",
        {"transaction_uuid": uuid},
        ["name", "vendor", "card_reader"],
        as_dict=True,
    )
    if not existing:
        # Log but don't error — late callback
        frappe.log_error(
            title=f"Card callback for unknown uuid {uuid}",
            message=f"Callback payload: {json.dumps(data)[:500]}",
        )
        # Still record it as an orphan for audit
        from .base import CardPaymentResponse
        resp = CardPaymentResponse(
            transaction_uuid=uuid,
            status="Error",
            response_message=f"Callback received but no pending transaction matched uuid {uuid}",
            raw_response=data,
        )
        from .base import BaseCardReader
        BaseCardReader.commit_response(resp)
        return {"ok": False, "error": "No pending transaction for this uuid"}

    if not existing.get("vendor"):
        return {"ok": False, "error": "Pending transaction has no vendor — can't dispatch"}

    if not existing.get("card_reader"):
        return {"ok": False, "error": "Pending transaction has no card reader link"}

    # Load reader config and adapter
    reader_cfg = frappe.get_doc("AlphaX POS Card Reader", existing["card_reader"]).as_dict()
    try:
        adapter = get_adapter_for_reader(reader_cfg)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Parse the response
    response = adapter.parse_callback(data)
    # parse_callback may have come back with empty uuid; reattach
    if not response.transaction_uuid:
        response.transaction_uuid = uuid

    name = adapter.commit_response(response, card_reader_name=existing["card_reader"])
    return {"ok": True, "uuid": uuid, "transaction": name, "status": response.status}


@frappe.whitelist()
def get_card_payment_status(transaction_uuid: str) -> dict:
    """Cashier polls this to learn the outcome of an in-flight payment.

    Returns
    -------
    dict
        {
          "transaction_uuid": str,
          "status": "Pending" | "Approved" | "Declined" | "Error" | "Timeout" | "Cancelled",
          "transaction": str,         # name of the audit record
          # ...all the standard response fields if final:
          "auth_code", "rrn", "card_brand", "masked_pan", "response_message"
        }
    """
    name = frappe.db.get_value(
        "AlphaX POS Card Transaction",
        {"transaction_uuid": transaction_uuid},
        "name",
    )
    if not name:
        return {
            "transaction_uuid": transaction_uuid,
            "status": "NotFound",
            "error": "No transaction with this uuid.",
        }

    doc = frappe.get_doc("AlphaX POS Card Transaction", name)
    return {
        "transaction_uuid": transaction_uuid,
        "transaction": name,
        "status": doc.status,
        "auth_code": doc.auth_code,
        "rrn": doc.rrn,
        "card_brand": doc.card_brand,
        "masked_pan": doc.masked_pan,
        "amount": doc.amount,
        "currency": doc.currency,
        "response_code": doc.response_code,
        "response_message": doc.response_message,
        "requested_at": str(doc.requested_at) if doc.requested_at else None,
        "responded_at": str(doc.responded_at) if doc.responded_at else None,
        "duration_ms": doc.duration_ms,
    }


@frappe.whitelist()
def cancel_card_payment(transaction_uuid: str) -> dict:
    """Try to cancel an in-flight card payment.

    Most card readers don't support cancel mid-flow (once the cardholder
    has tapped, you can't undo it). This is best-effort; the cashier
    UI shows the result.

    Always marks the transaction as 'Cancelled' regardless — the user
    explicitly asked to cancel, and a stuck Pending row is worse than
    a Cancelled that turned out to actually be Approved (which the
    audit log will show with response time).
    """
    name = frappe.db.get_value(
        "AlphaX POS Card Transaction",
        {"transaction_uuid": transaction_uuid},
        "name",
    )
    if not name:
        return {"ok": False, "error": "No transaction"}

    doc = frappe.get_doc("AlphaX POS Card Transaction", name)
    if doc.status != "Pending":
        return {"ok": False, "error": f"Cannot cancel — status is {doc.status}"}

    # Try adapter-level cancel
    if doc.card_reader and frappe.db.exists("AlphaX POS Card Reader", doc.card_reader):
        try:
            reader_cfg = frappe.get_doc("AlphaX POS Card Reader", doc.card_reader).as_dict()
            adapter = get_adapter_for_reader(reader_cfg)
            adapter.cancel_payment(transaction_uuid)
        except Exception:
            pass

    doc.status = "Cancelled"
    doc.responded_at = now_datetime()
    doc.response_message = (doc.response_message or "") + " [Cancelled by user]"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def list_card_readers_available() -> dict:
    """Return list of registered vendors + list of configured readers.

    Used by setup tooling and the cashier for diagnostics.
    """
    return {
        "registered_vendors": list_available_vendors(),
        "configured_readers": frappe.get_all(
            "AlphaX POS Card Reader",
            filters={"is_active": 1},
            fields=["name", "reader_name", "vendor", "transport", "alphax_terminal"],
        ),
    }
