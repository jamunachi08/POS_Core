import frappe
from frappe.model.document import Document


class AlphaXPOSDomainPack(Document):
    def autoname(self):
        if self.domain_code and not self.name:
            self.name = self.domain_code
