"""AlphaX Drug Interaction Rule — controller.

Validates that the two drugs are different and that the rule isn't a
duplicate of an existing one (in either A->B or B->A direction).
"""
import frappe
from frappe.model.document import Document


class AlphaXDrugInteractionRule(Document):

    def validate(self):
        if self.drug_a == self.drug_b:
            frappe.throw("A drug cannot interact with itself. Pick two different drugs.")

        # Defensive duplicate check — a rule for (paracetamol, warfarin) and
        # (warfarin, paracetamol) is the same rule, even if both directions
        # are saved by mistake.
        existing = frappe.db.sql("""
            SELECT name FROM `tabAlphaX Drug Interaction Rule`
            WHERE name != %(self_name)s
              AND (
                (drug_a = %(a)s AND drug_b = %(b)s)
                OR
                (drug_a = %(b)s AND drug_b = %(a)s)
              )
            LIMIT 1
        """, {
            "self_name": self.name or "__new__",
            "a": self.drug_a,
            "b": self.drug_b,
        })
        if existing:
            frappe.throw(
                f"A rule for this drug pair already exists ({existing[0][0]}). "
                f"Edit that rule instead of creating a duplicate."
            )
