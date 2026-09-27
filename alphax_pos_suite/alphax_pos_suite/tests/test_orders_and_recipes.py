"""
Tests for order idempotency (client_uuid dedupe) and recipe cost computation
(the bug-fix for the item / item_code mismatch).
"""

import unittest

import frappe

from alphax_pos_suite.alphax_pos_suite.tests.fixtures import (
    ensure_company,
    ensure_item,
)


class TestRecipeCostFix(unittest.TestCase):
    """The pre-fix code queried Recipe by 'item' (wrong) and child by
    'item_code' (wrong). Both are now correct."""

    @classmethod
    def setUpClass(cls):
        ensure_company()
        ensure_item("TEST-DRINK", rate=20)
        ensure_item("TEST-CUP", rate=0.45)
        ensure_item("TEST-LID", rate=0.18)

        if frappe.db.exists("AlphaX POS Recipe", "TEST-DRINK"):
            frappe.delete_doc(
                "AlphaX POS Recipe", "TEST-DRINK", force=True, ignore_permissions=True
            )
        rec = frappe.new_doc("AlphaX POS Recipe")
        rec.item_code = "TEST-DRINK"
        rec.disabled = 0
        rec.append("items", {"material_item": "TEST-CUP", "qty": 1})
        rec.append("items", {"material_item": "TEST-LID", "qty": 1})
        rec.insert(ignore_permissions=True)

        frappe.db.set_value("Item", "TEST-CUP", "valuation_rate", 0.45)
        frappe.db.set_value("Item", "TEST-LID", "valuation_rate", 0.18)

    def test_recipe_lookup_finds_recipe(self):
        from alphax_pos_suite.alphax_pos_suite.api import compute_recipe_cost
        result = compute_recipe_cost("TEST-DRINK")
        self.assertTrue(result["ok"])
        self.assertEqual(result["recipe"], "TEST-DRINK")
        self.assertAlmostEqual(result["cost"], 0.63, places=2)
        self.assertEqual(len(result["breakdown"]), 2)

    def test_recipe_breakdown_returns_each_material(self):
        from alphax_pos_suite.alphax_pos_suite.api import compute_recipe_cost
        result = compute_recipe_cost("TEST-DRINK")
        materials = {row["material_item"] for row in result["breakdown"]}
        self.assertEqual(materials, {"TEST-CUP", "TEST-LID"})

    def test_recipe_missing_falls_back_to_valuation(self):
        from alphax_pos_suite.alphax_pos_suite.api import compute_recipe_cost
        ensure_item("TEST-NORECIPE", rate=5)
        frappe.db.set_value("Item", "TEST-NORECIPE", "valuation_rate", 5)
        result = compute_recipe_cost("TEST-NORECIPE")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["recipe"])
        self.assertAlmostEqual(result["cost"], 5.0, places=2)


class TestOrderIdempotency(unittest.TestCase):
    """Submitting the same client_uuid twice must not create two orders."""

    @classmethod
    def setUpClass(cls):
        ensure_company()

        if not frappe.db.exists("AlphaX POS Terminal", "TEST-TERM"):
            t = frappe.new_doc("AlphaX POS Terminal")
            t.terminal_name = "TEST-TERM"
            t.insert(ignore_permissions=True)
            cls.terminal = t.name
        else:
            cls.terminal = "TEST-TERM"

    def tearDown(self):
        for o in frappe.get_all(
            "AlphaX POS Order", filters={"client_uuid": ["like", "TEST-IDEMP-%"]}
        ):
            try:
                frappe.delete_doc(
                    "AlphaX POS Order", o.name, force=True, ignore_permissions=True
                )
            except Exception:
                pass

    def test_duplicate_client_uuid_throws(self):
        first = frappe.new_doc("AlphaX POS Order")
        first.pos_terminal = self.terminal
        first.client_uuid = "TEST-IDEMP-001"
        first.status = "Draft"
        first.insert(ignore_permissions=True)

        second = frappe.new_doc("AlphaX POS Order")
        second.pos_terminal = self.terminal
        second.client_uuid = "TEST-IDEMP-001"
        second.status = "Draft"
        with self.assertRaises(frappe.exceptions.DuplicateEntryError):
            second.insert(ignore_permissions=True)

    def test_lookup_returns_existing_order(self):
        from alphax_pos_suite.alphax_pos_suite.doctype.alphax_pos_order.alphax_pos_order import (
            find_by_client_uuid,
        )
        order = frappe.new_doc("AlphaX POS Order")
        order.pos_terminal = self.terminal
        order.client_uuid = "TEST-IDEMP-LOOKUP"
        order.status = "Draft"
        order.insert(ignore_permissions=True)

        found = find_by_client_uuid("TEST-IDEMP-LOOKUP")
        self.assertIsNotNone(found)
        self.assertEqual(found["client_uuid"], "TEST-IDEMP-LOOKUP")

        missing = find_by_client_uuid("TEST-IDEMP-DOES-NOT-EXIST")
        self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
