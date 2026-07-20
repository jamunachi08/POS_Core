"""AlphaX Controlled Substance Log — controller.

Append-only audit trail. Once written, these records cannot be
modified or deleted (except by System Manager for emergency
corrections, which are still tracked via Frappe's standard change log).

This is the legal record of every controlled-substance dispense and
must be inspectable by the Ministry of Health / SFDA / DEA / equivalent
local authority on request. Tampering would be a regulatory violation,
so the controller refuses any update that mutates a non-trivial field.
"""
import frappe
from frappe.model.document import Document


class AlphaXControlledSubstanceLog(Document):

    # Fields a System Manager can fix (typos, additional notes).
    # Everything else is locked once the record is created.
    EDITABLE_AFTER_INSERT = {"notes"}

    def validate(self):
        if self.is_new():
            # Sanity: every required link must resolve. (Frappe's `reqd`
            # enforces presence, but we double-check existence.)
            for f in ("drug", "prescription", "sales_invoice", "outlet"):
                value = self.get(f)
                if value:
                    doctype = self.meta.get_field(f).options
                    if not frappe.db.exists(doctype, value):
                        frappe.throw(f"{f}={value} does not exist in {doctype}.")
            return

        # On update — verify nothing immutable changed.
        old = self.get_doc_before_save()
        if not old:
            return
        for field in self.meta.get("fields", []):
            fname = field.fieldname
            if fname in self.EDITABLE_AFTER_INSERT:
                continue
            if field.fieldtype in ("Section Break", "Column Break"):
                continue
            if self.get(fname) != old.get(fname):
                frappe.throw(
                    f"Field '{field.label or fname}' cannot be modified on "
                    f"a Controlled Substance Log entry. This is an audit "
                    f"trail; only 'Notes' may be edited after creation."
                )

    def on_trash(self):
        # Block deletes outright. A System Manager can override via
        # raw SQL if there's a true emergency, but the UI never lets it
        # happen.
        frappe.throw(
            "Controlled Substance Log entries cannot be deleted. "
            "This is a legal audit trail."
        )
