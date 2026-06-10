from __future__ import annotations

import frappe
import math
from frappe.model.document import Document
from frappe.utils import now_datetime, time_diff_in_seconds

class AlphaXPOSKDSTicket(Document):
    def validate(self):
        self._apply_sla_timestamps()
        self._compute_sla_metrics()

    def _apply_sla_timestamps(self):
        # Set timestamps based on status transitions
        status = (self.status or "").strip()
        if status == "In Progress" and not self.started_on:
            self.started_on = now_datetime()
        if status == "Ready" and not self.ready_on:
            # If kitchen never marked in-progress, start it now
            if not self.started_on:
                self.started_on = now_datetime()
            self.ready_on = now_datetime()
        if status == "Served" and not self.served_on:
            if not self.started_on:
                self.started_on = now_datetime()
            if not self.ready_on:
                self.ready_on = now_datetime()
            self.served_on = now_datetime()

    def _compute_sla_metrics(self):
        # Compute actual minutes from started_on -> ready_on (preferred) else served_on
        if not self.started_on:
            self.actual_minutes = 0
            self.sla_status = ""
            return

        end = self.ready_on or self.served_on
        if not end:
            self.actual_minutes = 0
            self.sla_status = ""
            return

        secs = max(0, time_diff_in_seconds(end, self.started_on))
        minutes = int(round(secs / 60.0))
        self.actual_minutes = minutes

        sla = int(self.sla_minutes or 0) or 0
        if sla <= 0:
            self.sla_status = ""
            return

        # Classification: <= SLA = On Time, <= SLA*1.5 = Delayed, else Critical
        if minutes <= sla:
            self.sla_status = "On Time"
        elif minutes <= int(math.ceil(sla * 1.5)):
            self.sla_status = "Delayed"
        else:
            self.sla_status = "Critical"
