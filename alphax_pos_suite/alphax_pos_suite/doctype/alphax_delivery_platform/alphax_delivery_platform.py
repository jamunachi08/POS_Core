import frappe
from frappe.model.document import Document


class AlphaXDeliveryPlatform(Document):
    def validate(self):
        if self.commission_percent and not (0 <= self.commission_percent <= 100):
            frappe.throw("Commission % must be between 0 and 100")
