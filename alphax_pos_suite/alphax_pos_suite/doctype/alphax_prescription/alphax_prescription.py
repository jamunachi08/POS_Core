"""AlphaX Prescription — controller.

On save: runs the clinical validator over the prescribed lines and
collects warnings into the validator_messages field. Sets the expiry
date based on whether any line is a controlled substance. Auto-updates
fully_dispensed flag.
"""
from datetime import timedelta

import frappe
from frappe.utils import getdate, today
from frappe.model.document import Document


class AlphaXPrescription(Document):

    def validate(self):
        self._set_company_from_outlet()
        self._set_expiry_date()
        self._validate_lines()
        self._run_clinical_validator()
        self._update_dispensed_status()

    def before_submit(self):
        # Force re-validation on submit; status moves out of Draft.
        if self.status == "Draft":
            self.status = "Active"

    # -- helpers -----------------------------------------------------------

    def _set_company_from_outlet(self):
        if self.outlet and not self.company:
            self.company = frappe.db.get_value(
                "AlphaX POS Outlet", self.outlet, "company"
            )

    def _set_expiry_date(self):
        if self.expiry_date:
            return
        # Controlled-substance prescriptions get a shorter window.
        has_controlled = any(
            frappe.db.get_value("AlphaX Drug Master", line.drug, "is_controlled")
            for line in self.lines if line.drug
        )
        days = 30 if has_controlled else 90
        self.expiry_date = getdate(self.prescription_date) + timedelta(days=days)

    def _validate_lines(self):
        if not self.lines:
            frappe.throw("A prescription must have at least one drug line.")
        seen = set()
        for line in self.lines:
            if line.drug in seen:
                frappe.throw(
                    f"Drug {line.drug} appears multiple times in this prescription. "
                    f"Combine the doses into a single line instead."
                )
            seen.add(line.drug)

    def _run_clinical_validator(self):
        # Defer import — validator is in the pharmacy package
        from alphax_pos_suite.alphax_pos_suite.pharmacy.validator import (
            validate_prescription,
        )
        warnings = validate_prescription(self)
        if warnings:
            self.validator_messages = "\n".join(warnings)
        else:
            self.validator_messages = ""

    def _update_dispensed_status(self):
        if not self.lines:
            self.fully_dispensed = 0
            return
        # A line is fully dispensed when refills_used >= refills_allowed
        # AND its dispensed_qty matches quantity_dispensed.
        all_done = True
        for line in self.lines:
            if (line.refills_used or 0) <= (line.refills_allowed or 0):
                # Has at least one refill remaining if refills_used < allowed
                if (line.refills_used or 0) < (line.refills_allowed or 0):
                    all_done = False
                    break
                # No refills remaining; check that initial fill happened
                if not line.dispensed_at:
                    all_done = False
                    break
        self.fully_dispensed = 1 if all_done else 0
        if self.fully_dispensed and self.status in ("Active", "Partially Dispensed"):
            self.status = "Fully Dispensed"

    # -- public API for cashier dispensing ---------------------------------

    def record_dispense(self, line_name: str, qty: float, sales_invoice: str):
        """Mark one prescription line as dispensed via a Sales Invoice.
        Increments refills_used, updates fully_dispensed, writes the
        controlled-substance log if applicable.

        Caller (cashier flow) is responsible for stock movement; this
        only updates the prescription audit trail."""
        for line in self.lines:
            if line.name == line_name:
                line.refills_used = (line.refills_used or 0) + 1
                line.dispensed_qty = qty
                line.dispensed_invoice = sales_invoice
                line.dispensed_at = frappe.utils.now()

                # If this drug is controlled, write to the log.
                is_controlled = frappe.db.get_value(
                    "AlphaX Drug Master", line.drug, "is_controlled"
                )
                if is_controlled:
                    frappe.get_doc({
                        "doctype": "AlphaX Controlled Substance Log",
                        "prescription": self.name,
                        "prescription_line": line.name,
                        "drug": line.drug,
                        "patient_name": self.patient_name,
                        "patient_id": self.patient_id,
                        "prescriber_name": self.prescriber_name,
                        "prescriber_license": self.prescriber_license,
                        "outlet": self.outlet,
                        "quantity": qty,
                        "sales_invoice": sales_invoice,
                        "dispensed_at": frappe.utils.now(),
                    }).insert(ignore_permissions=True)

                # Update parent dispensed status
                self.fills_count = (self.fills_count or 0) + 1
                self.last_fill_date = frappe.utils.now()
                self._update_dispensed_status()
                if not self.fully_dispensed:
                    self.status = "Partially Dispensed"
                self.save(ignore_permissions=True)
                return

        frappe.throw(f"Prescription line {line_name} not found in {self.name}.")
