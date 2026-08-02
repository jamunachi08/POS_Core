"""
AlphaX POS Manager PIN — controller.

The PIN itself is set via the API method `set_manager_pin()` (in
boot/api.py), which hashes it before storing. The form view never
shows the plain PIN — only the audit fields (last used, lockouts).

Lockout logic lives in `boot/api.py::verify_manager_pin()`. This
controller is intentionally thin: validation, naming, and
permissions only.
"""
from __future__ import annotations

import frappe
from frappe.model.document import Document


class AlphaXPOSManagerPIN(Document):
    def validate(self):
        # Sanity: only one PIN per user
        if self.user and not self.is_new():
            return
        if self.user:
            existing = frappe.db.get_value(
                "AlphaX POS Manager PIN",
                {"user": self.user, "name": ["!=", self.name or ""]},
                "name",
            )
            if existing:
                frappe.throw(
                    f"User {self.user} already has a PIN ({existing}). "
                    f"Edit that record to reset it instead of creating a new one."
                )

    def on_trash(self):
        # Audit deletion — every PIN delete leaves a log entry even if the
        # PIN doc itself is gone.
        try:
            frappe.get_doc({
                "doctype": "AlphaX POS Manager Authorization Log",
                "manager": self.user,
                "action_type": "PIN Deleted",
                "result": "Success",
                "notes": f"PIN record deleted by {frappe.session.user}",
                "cashier_user": frappe.session.user,
            }).insert(ignore_permissions=True)
        except Exception:
            # Don't block the delete on audit log failure
            frappe.log_error(
                title="AlphaX POS: failed to log PIN deletion",
                message=frappe.get_traceback(),
            )
