"""
AlphaX POS — Geidea card reader adapter.

Geidea is one of the dominant card-acquiring providers in the Gulf
region. Their terminals run an Android app that listens to an MQTT
topic; AlphaX publishes a payment request, the terminal app processes
the card, and posts back via the REST callback endpoint.

This is a clean re-implementation of the MQTT pattern. The protocol
shape is publicly documented in Geidea's terminal API and was also
observable in third-party integrations we reviewed. None of the code
here is copied from any specific third-party app — only the protocol
understanding is borrowed.

Transport: MQTT (typically on port 1883 plain or 8883 TLS).

Payload (request published to MQTT):
    {
        "uuid": "<transaction uuid>",
        "amount": 12.50,
        "currency": "SAR",
        "refund": 0 | 1,
        "transaction_id": "<original RRN if refund>",
        "posting_date": "<YYYY-MM-DD if refund>",
        "device_topic": "<the topic we published to>",
        ... vendor-specific extras from extra_config_json
    }

Callback (HTTP POST received from the Android app):
    {
        "uuid": "<matches request>",
        "status": "Approved" | "Declined" | ...,
        "auth_code": "...",
        "rrn": "...",
        "card_brand": "Visa" | "Mastercard" | "Mada",
        "masked_pan": "**** **** **** 1234",
        ... and other vendor fields
    }
"""
from __future__ import annotations

import json
import ssl
from typing import Any

import frappe
from frappe.utils import now_datetime

from .base import (
    BaseCardReader,
    CardPaymentRequest,
    CardPaymentResponse,
    register_adapter,
)


@register_adapter
class GeideaAdapter(BaseCardReader):
    """MQTT-based adapter for Geidea card-reader Android terminals."""

    vendor = "Geidea"

    def initiate_payment(self, req: CardPaymentRequest) -> dict:
        if not self.config.get("mqtt_broker_url"):
            return {"ok": False, "error": "Card reader has no MQTT broker URL configured."}
        if not self.config.get("mqtt_topic"):
            return {"ok": False, "error": "Card reader has no MQTT topic configured."}

        # Build the payload Geidea expects. Required fields come from
        # the request; optional fields from the reader's extra config.
        payload = {
            "uuid": req.transaction_uuid,
            "amount": float(req.amount),
            "currency": req.currency or "SAR",
            "refund": 1 if req.is_refund else 0,
            "device_topic": self.config["mqtt_topic"],
        }
        if req.is_refund:
            if not req.original_rrn or not req.original_posting_date:
                return {
                    "ok": False,
                    "error": "Refunds require original RRN and posting date.",
                }
            payload["transaction_id"] = req.original_rrn
            payload["posting_date"] = req.original_posting_date

        # Merge extra vendor config
        extra = self._load_extra_config()
        for k, v in extra.items():
            if k not in payload:
                payload[k] = v

        # Publish via MQTT. We import paho here so the module loads
        # even when paho-mqtt isn't installed yet (adapter registration
        # still works; only the actual call needs paho).
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return {
                "ok": False,
                "error": "paho-mqtt is not installed. Run `pip install paho-mqtt` "
                         "or add it to your bench's requirements.",
            }

        broker_url = self.config["mqtt_broker_url"]
        host, port = self._parse_broker_url(broker_url)
        use_tls = bool(self.config.get("mqtt_use_tls"))

        try:
            client = mqtt.Client()
            username = self.config.get("mqtt_username")
            password = self.config.get("mqtt_password")
            if username and password:
                client.username_pw_set(username, password)
            if use_tls:
                client.tls_set(
                    "/etc/ssl/certs/ca-certificates.crt",
                    tls_version=ssl.PROTOCOL_TLSv1_2,
                )
                client.tls_insecure_set(False)

            client.connect(host, port, 60)
            client.loop_start()
            result = client.publish(self.config["mqtt_topic"], json.dumps(payload))
            result.wait_for_publish(timeout=5)
            client.loop_stop()
            client.disconnect()

            return {"ok": True, "sent": True}
        except Exception as e:
            frappe.log_error(
                title=f"Geidea MQTT publish failed for {self.name}",
                message=frappe.get_traceback(),
            )
            return {"ok": False, "error": f"MQTT publish failed: {e}"}

    def parse_callback(self, raw_payload: dict) -> CardPaymentResponse:
        """Map Geidea's response shape to our normalized form.

        Geidea responses vary slightly by terminal firmware; we try
        several field names and use the first present value.
        """
        uuid = raw_payload.get("uuid") or raw_payload.get("transactionId") or ""

        # Status mapping. Geidea sometimes uses string status, sometimes
        # numeric. We do a case-insensitive lookup.
        raw_status = (raw_payload.get("status") or
                      raw_payload.get("transactionStatus") or
                      raw_payload.get("paymentStatus") or "").strip()
        status_lower = str(raw_status).lower()
        # Some responses use 'approved' verb in 'message' field
        message_lower = str(raw_payload.get("message", "")).lower()

        if "approved" in status_lower or "approved" in message_lower or "success" in status_lower:
            status = "Approved"
        elif "decline" in status_lower or "decline" in message_lower:
            status = "Declined"
        elif "cancel" in status_lower:
            status = "Cancelled"
        elif "timeout" in status_lower:
            status = "Timeout"
        elif raw_status:
            status = "Error"
        else:
            status = "Error"

        return CardPaymentResponse(
            transaction_uuid=uuid,
            status=status,
            response_code=str(raw_payload.get("responseCode") or
                              raw_payload.get("response_code") or
                              raw_payload.get("code") or ""),
            response_message=str(raw_payload.get("message") or
                                 raw_payload.get("responseMessage") or
                                 raw_payload.get("description") or ""),
            auth_code=raw_payload.get("authCode") or raw_payload.get("auth_code"),
            rrn=raw_payload.get("rrn") or raw_payload.get("RRN"),
            trace_no=raw_payload.get("traceNo") or raw_payload.get("trace_no") or
                     raw_payload.get("stan"),
            batch_no=raw_payload.get("batchNo") or raw_payload.get("batch_no"),
            card_brand=raw_payload.get("cardBrand") or raw_payload.get("card_brand") or
                       raw_payload.get("scheme"),
            masked_pan=raw_payload.get("maskedPan") or raw_payload.get("masked_pan") or
                       raw_payload.get("cardNumber"),
            terminal_id=raw_payload.get("terminalId") or raw_payload.get("tid"),
            merchant_id=raw_payload.get("merchantId") or raw_payload.get("mid"),
            raw_response=raw_payload,
        )

    # -- internals --

    def _load_extra_config(self) -> dict:
        raw = self.config.get("extra_config_json")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}

    @staticmethod
    def _parse_broker_url(url: str) -> tuple[str, int]:
        """Parse 'tcp://host:1883' or 'ssl://host:8883' → (host, port).

        Returns sensible defaults if the URL is malformed.
        """
        url = (url or "").strip()
        host = "localhost"
        port = 1883
        if url:
            # strip scheme
            if "://" in url:
                _, url = url.split("://", 1)
            if ":" in url:
                h, p = url.rsplit(":", 1)
                host = h
                try:
                    port = int(p)
                except (ValueError, TypeError):
                    pass
            else:
                host = url
        return host, port
