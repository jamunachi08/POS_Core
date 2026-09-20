"""AlphaX Drug Master — controller.

Holds the formulary entry for a single drug. Validates the
controlled-substance / requires-prescription invariant: if it's
controlled, it always requires a prescription.
"""
import frappe
from frappe.model.document import Document


class AlphaXDrugMaster(Document):

    def validate(self):
        # Controlled substances ALWAYS require a prescription. Don't
        # allow the user to uncheck requires_prescription for one.
        if self.is_controlled and not self.requires_prescription:
            self.requires_prescription = 1

        # Strength sanity
        if self.strength is not None and self.strength < 0:
            frappe.throw("Strength cannot be negative.")
        if self.max_daily_dose is not None and self.max_daily_dose < 0:
            frappe.throw("Max Daily Dose cannot be negative.")

        # min_age_years sanity
        if self.min_age_years is not None and self.min_age_years < 0:
            frappe.throw("Min Age cannot be negative.")
