"""AlphaX Prescription Line — child table controller.

Auto-computes total dispense quantity from dose × frequency × duration
unless the user has explicitly overridden it.
"""
import frappe
from frappe.model.document import Document


class AlphaXPrescriptionLine(Document):

    def validate(self):
        # Auto-compute quantity_dispensed if not manually set
        if not self.quantity_dispensed and self.dose and self.frequency_per_day and self.duration_days:
            self.quantity_dispensed = (
                self.dose * self.frequency_per_day * self.duration_days
            )

        # Refills sanity
        if self.refills_used and self.refills_allowed is not None:
            if self.refills_used > self.refills_allowed:
                frappe.throw(
                    f"Refills used ({self.refills_used}) cannot exceed "
                    f"refills allowed ({self.refills_allowed})."
                )
