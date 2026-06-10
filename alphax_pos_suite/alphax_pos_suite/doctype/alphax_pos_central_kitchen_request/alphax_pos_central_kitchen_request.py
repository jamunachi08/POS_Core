import frappe
from frappe.model.document import Document
from alphax_pos_suite.alphax_pos_suite.integrations.erpnext_stock import create_material_request_from_ck_request, create_stock_entry_from_ck_request, is_erpnext_available

class AlphaxPosCentralKitchenRequest(Document):
    def after_insert(self):
        # Ensure Requested On is captured
        if not getattr(self, "requested_on", None):
            try:
                self.db_set("requested_on", frappe.utils.now_datetime())
            except Exception:
                pass

    def on_update(self):
        # When status becomes Submitted, try auto-create Material Request
        try:
            if (self.status or "") == "Submitted" and not getattr(self, "erpnext_material_request", None):
                create_material_request_from_ck_request(self.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "CK Request auto MR on_update failed")

        # When status becomes Fulfilled, try auto-create Stock Entry
        try:
            if (self.status or "") == "Fulfilled" and not getattr(self, "erpnext_stock_entry", None):
                create_stock_entry_from_ck_request(self.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "CK Request auto Stock Entry on_update failed")
