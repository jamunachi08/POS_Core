"""
AlphaX POS Card Reader — abstract base class.

Defines the interface every card-reader adapter must implement. Concrete
adapters live in this same package:

    base.py      <- this file
    geidea.py    <- MQTT-based Geidea Android-app terminal
    (future)     <- network_international.py, paytabs.py, tap.py, ...

Adapters are stateless. They receive a `card_reader_config` (a dict
loaded from an AlphaX POS Card Reader doctype) on every call.

Lifecycle of a card transaction
================================

   Cashier UI                Backend                  Card Reader
        |                       |                          |
        |--- request_payment -->|                          |
        |   (uuid, amount)      |                          |
        |                       |--- adapter.send_payment -|--->
        |                       |                          | (cardholder
        |                       |                          |  taps/inserts)
        |                       |                          |
        |                       |<-- adapter.callback -----|
        |                       |   (uuid matched)         |
        |<-- pending poll OK ---|                          |
        |   (or push via WS)    |                          |
        |                       |                          |
        v                       v                          v
    sale done            tx audited                  receipt printed

Adapters expose three operations:

    initiate_payment(...)   - kick off a sale; returns immediately with
                              {ok, sent} or {ok: False, error}.

    handle_callback(...)    - receive the reader's response (in a
                              vendor-specific format) and normalize it
                              to our standard shape. Called by the
                              whitelisted REST callback endpoint or by
                              a polling thread for transports that don't
                              support callbacks.

    cancel_payment(...)     - try to abort an in-flight transaction
                              (best-effort; many readers can't be
                              cancelled mid-flow). Returns {ok, error}.

The async flow is mediated by `transaction_uuid`:

    - The cashier generates a uuid.
    - `initiate_payment` stores {uuid: pending} in Frappe's cache and
       sends the request to the reader.
    - `handle_callback` looks up the uuid; if pending, normalizes the
       response and updates the AlphaX POS Card Transaction record.
    - The cashier polls until the record's status is final
       (Approved/Declined/Error/Timeout) or a WebSocket pushes it.
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import now_datetime


@dataclass
class CardPaymentRequest:
    """All the info an adapter needs to initiate a payment.

    Vendor-agnostic. Each adapter translates these fields into its
    own protocol.
    """
    transaction_uuid: str
    amount: float
    currency: str = "SAR"
    is_refund: bool = False
    original_rrn: str | None = None        # required for refunds in most vendors
    original_posting_date: str | None = None
    cashier_user: str | None = None        # who initiated
    metadata: dict | None = None           # free-form (e.g. invoice ref)


@dataclass
class CardPaymentResponse:
    """Normalized response shape returned by every adapter's
    handle_callback. Each adapter is responsible for mapping its
    vendor's response format to these fields.
    """
    transaction_uuid: str
    status: str                            # 'Approved' | 'Declined' | 'Error' | 'Timeout' | 'Cancelled'
    response_code: str | None = None       # vendor code
    response_message: str | None = None    # human-readable
    auth_code: str | None = None
    rrn: str | None = None
    trace_no: str | None = None
    batch_no: str | None = None
    card_brand: str | None = None          # Visa, Mastercard, Mada, ...
    masked_pan: str | None = None
    terminal_id: str | None = None
    merchant_id: str | None = None
    raw_response: dict | None = None       # the full vendor payload, for audit


class BaseCardReader(abc.ABC):
    """Abstract base class for card-reader adapters.

    Each subclass declares a class-level `vendor` string matching one
    of the values in the AlphaX POS Card Reader doctype's `vendor`
    Select field.
    """

    vendor: str = ""        # subclasses MUST override

    def __init__(self, reader_config: dict):
        """reader_config is a dict loaded from an AlphaX POS Card Reader
        doc (via .as_dict()). Keep all configuration external; the
        adapter itself is stateless across calls.
        """
        self.config = reader_config
        self.name = reader_config.get("name") or reader_config.get("reader_name") or "unknown"

    # ------------------------------------------------------------------ *
    # Required interface
    # ------------------------------------------------------------------ *

    @abc.abstractmethod
    def initiate_payment(self, req: CardPaymentRequest) -> dict:
        """Send the payment request to the card reader.

        Returns a dict:
            {"ok": True, "sent": True}              on success
            {"ok": False, "error": "..."}           on transport error

        Does NOT wait for the cardholder. The caller polls / waits for
        the callback to complete the transaction.
        """
        ...

    @abc.abstractmethod
    def parse_callback(self, raw_payload: dict) -> CardPaymentResponse:
        """Parse the raw callback payload from this vendor's protocol
        into a normalized CardPaymentResponse.

        Each vendor has its own field names (e.g. Geidea uses "uuid",
        Network International uses "merchantTransactionId"). This
        method does the translation.

        Should NOT have side effects — it's a pure parser. Callers
        that want to persist the response call commit_response().
        """
        ...

    def cancel_payment(self, transaction_uuid: str) -> dict:
        """Try to abort an in-flight transaction.

        Default implementation does nothing (most card readers can't
        be cancelled mid-flow once the cardholder has tapped). Override
        in subclasses that support cancel.

        Returns {"ok": bool, "error": str | None}.
        """
        return {"ok": False, "error": "Cancel not supported by this reader."}

    # ------------------------------------------------------------------ *
    # Shared infrastructure
    # ------------------------------------------------------------------ *

    @classmethod
    def commit_response(
        cls,
        response: CardPaymentResponse,
        card_reader_name: str | None = None,
    ) -> str | None:
        """Persist a normalized CardPaymentResponse to the
        AlphaX POS Card Transaction doctype.

        Looks up an existing 'Pending' transaction by uuid; if found,
        updates it. Otherwise creates a new record (for callbacks that
        arrive without a matching pending entry — late callbacks,
        terminal-initiated transactions, etc.).

        Returns the name of the updated/created transaction record.
        """
        try:
            existing = frappe.db.get_value(
                "AlphaX POS Card Transaction",
                {"transaction_uuid": response.transaction_uuid},
                "name",
            )
            now = now_datetime()
            if existing:
                doc = frappe.get_doc("AlphaX POS Card Transaction", existing)
                doc.status = response.status
                doc.response_code = response.response_code
                doc.response_message = response.response_message
                doc.auth_code = response.auth_code
                doc.rrn = response.rrn
                doc.trace_no = response.trace_no
                doc.batch_no = response.batch_no
                doc.card_brand = response.card_brand
                doc.masked_pan = response.masked_pan
                doc.terminal_id = response.terminal_id
                doc.merchant_id = response.merchant_id
                doc.responded_at = now
                if response.raw_response:
                    doc.raw_response = json.dumps(response.raw_response, indent=2)
                # Compute duration
                if doc.requested_at:
                    try:
                        from frappe.utils import time_diff_in_seconds
                        doc.duration_ms = int(
                            time_diff_in_seconds(now, doc.requested_at) * 1000
                        )
                    except Exception:
                        pass
                doc.save(ignore_permissions=True)
                frappe.db.commit()

                # Update card reader health stats
                if card_reader_name and frappe.db.exists("AlphaX POS Card Reader", card_reader_name):
                    if response.status == "Approved":
                        frappe.db.set_value(
                            "AlphaX POS Card Reader",
                            card_reader_name,
                            "last_seen_at",
                            now,
                        )
                    elif response.status in ("Error", "Timeout"):
                        frappe.db.set_value(
                            "AlphaX POS Card Reader",
                            card_reader_name,
                            {"last_error_at": now,
                             "last_error_message": response.response_message or ""},
                        )

                return doc.name
            else:
                # Late or orphan callback - create a record for audit
                doc = frappe.get_doc({
                    "doctype": "AlphaX POS Card Transaction",
                    "transaction_uuid": response.transaction_uuid,
                    "status": response.status,
                    "response_code": response.response_code,
                    "response_message": response.response_message,
                    "auth_code": response.auth_code,
                    "rrn": response.rrn,
                    "trace_no": response.trace_no,
                    "batch_no": response.batch_no,
                    "card_brand": response.card_brand,
                    "masked_pan": response.masked_pan,
                    "terminal_id": response.terminal_id,
                    "merchant_id": response.merchant_id,
                    "responded_at": now,
                    "amount": 0,  # we don't know — orphan
                    "raw_response": json.dumps(response.raw_response or {}, indent=2),
                })
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                return doc.name
        except Exception:
            frappe.log_error(
                title="Card transaction commit failed",
                message=frappe.get_traceback(),
            )
            return None

    @classmethod
    def create_pending_transaction(
        cls,
        req: CardPaymentRequest,
        vendor: str,
        card_reader_name: str | None = None,
    ) -> str:
        """Create an audit row in 'Pending' status before sending the
        request to the reader. Returns the transaction's name.

        Idempotent: if a transaction with the same uuid exists, returns
        its name rather than creating a duplicate.
        """
        existing = frappe.db.get_value(
            "AlphaX POS Card Transaction",
            {"transaction_uuid": req.transaction_uuid},
            "name",
        )
        if existing:
            return existing

        doc = frappe.get_doc({
            "doctype": "AlphaX POS Card Transaction",
            "transaction_uuid": req.transaction_uuid,
            "status": "Pending",
            "vendor": vendor,
            "card_reader": card_reader_name,
            "amount": req.amount,
            "currency": req.currency,
            "is_refund": 1 if req.is_refund else 0,
            "requested_at": now_datetime(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name


# Registry of available adapter classes. Adapters self-register via
# subclassing; the dispatcher iterates this dict to find the right one.
_ADAPTER_REGISTRY: dict[str, type[BaseCardReader]] = {}


def register_adapter(cls: type[BaseCardReader]) -> type[BaseCardReader]:
    """Decorator: register a concrete adapter class by its `vendor`
    field.

    Usage:
        @register_adapter
        class GeideaAdapter(BaseCardReader):
            vendor = "Geidea"
            ...
    """
    if not cls.vendor:
        raise ValueError(f"{cls.__name__} must define a `vendor` class attribute")
    _ADAPTER_REGISTRY[cls.vendor] = cls
    return cls


def get_adapter_for_reader(reader_config: dict) -> BaseCardReader:
    """Look up the adapter class for this reader's vendor and
    instantiate it with the reader's config.

    Raises frappe.ValidationError if no adapter is registered for
    the vendor.
    """
    vendor = (reader_config.get("vendor") or "").strip()
    if not vendor:
        frappe.throw("Card reader has no vendor configured.")
    adapter_cls = _ADAPTER_REGISTRY.get(vendor)
    if not adapter_cls:
        frappe.throw(
            f"No card reader adapter is installed for vendor '{vendor}'. "
            f"Available adapters: {sorted(_ADAPTER_REGISTRY.keys())}"
        )
    return adapter_cls(reader_config)


def list_available_vendors() -> list[str]:
    """Used by setup wizard / UI to show what vendors are wired up."""
    return sorted(_ADAPTER_REGISTRY.keys())
