"""AlphaX POS Card Reader controller.

The card reader is mostly a config record — the runtime logic lives
in the adapter classes under integrations/card_reader/.
"""
from __future__ import annotations

import json

import frappe
from frappe.model.document import Document


class AlphaXPOSCardReader(Document):
    def validate(self):
        # Validate transport-specific required fields
        if self.transport == "MQTT":
            if not self.mqtt_broker_url:
                frappe.throw("MQTT Broker URL is required for MQTT transport.")
            if not self.mqtt_topic:
                frappe.throw("Device Topic is required for MQTT transport.")
        elif self.transport == "HTTP Webhook":
            if not self.http_endpoint:
                frappe.throw("HTTP Endpoint URL is required for HTTP transport.")
        elif self.transport == "Serial / USB":
            if not self.serial_port:
                frappe.throw("Serial Port is required for Serial/USB transport.")

        # Validate extra_config_json is parseable
        if self.extra_config_json:
            try:
                json.loads(self.extra_config_json)
            except (ValueError, TypeError) as e:
                frappe.throw(f"Extra Config must be valid JSON: {e}")
