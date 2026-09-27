import frappe
from frappe.model.document import Document


class AlphaXPOSLoyaltyProgram(Document):
    def validate(self):
        if self.default_earn_per_amount is not None and self.default_earn_per_amount <= 0:
            self.default_earn_per_amount = 1.0

        seen = set()
        for r in (self.rules or []):
            if r.scope == "Item" and r.item_code:
                k = ("item", r.item_code)
            elif r.scope == "Item Group" and r.item_group:
                k = ("group", r.item_group)
            elif r.scope == "Brand" and r.brand:
                k = ("brand", r.brand)
            elif r.scope == "Domain" and r.domain:
                k = ("domain", r.domain)
            else:
                continue
            if k in seen:
                frappe.throw(f"Duplicate loyalty rule for {k[0]} {k[1]}")
            seen.add(k)
