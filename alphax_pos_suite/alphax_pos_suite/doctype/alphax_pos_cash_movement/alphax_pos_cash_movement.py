import frappe
from frappe.model.document import Document

class AlphaXPOSCashMovement(Document):
    def before_insert(self):
        if not self.posting_datetime:
            self.posting_datetime = frappe.utils.now_datetime()
        if self.shift and frappe.db.exists("AlphaX POS Shift", self.shift):
            sh = frappe.get_doc("AlphaX POS Shift", self.shift)
            self.pos_terminal = sh.pos_terminal
            self.user = sh.user
