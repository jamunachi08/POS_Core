"""
Tests for the loyalty engine.

Run with:
    bench --site test-site run-tests --app alphax_pos_suite \\
        --module alphax_pos_suite.alphax_pos_suite.tests.test_loyalty_engine
"""

import unittest

import frappe

from alphax_pos_suite.alphax_pos_suite.loyalty import engine
from alphax_pos_suite.alphax_pos_suite.tests.fixtures import (
    ensure_company,
    ensure_customer,
    ensure_item,
    ensure_item_group,
    make_loyalty_program,
)


class TestLoyaltyEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.company = ensure_company()
        cls.customer = ensure_customer("Loyalty Test Customer")
        ensure_item_group("Beverages")
        ensure_item_group("Coffee", parent="Beverages")
        ensure_item("LATTE", item_group="Coffee", rate=20)
        ensure_item("TEA", item_group="Beverages", rate=10)
        ensure_item("PASTRY", item_group="All Item Groups", rate=15)

    def tearDown(self):
        for prog in frappe.get_all(
            "AlphaX POS Loyalty Program", filters={"program_code": ["like", "TLE-%"]}
        ):
            try:
                frappe.delete_doc(
                    "AlphaX POS Loyalty Program",
                    prog.name,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                pass

    # ---- earn rate resolution ---------------------------------------------

    def test_default_earn_with_no_rules(self):
        prog = make_loyalty_program(
            code="TLE-DEFAULT",
            company=self.company,
            earn_basis="Per Currency Spent",
            default_earn_points=2,
            default_earn_per_amount=10,
        )
        order = {
            "items": [
                {"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20},
                {"item_code": "PASTRY", "qty": 2, "rate": 15, "amount": 30},
            ],
            "net_total": 50,
        }
        result = engine.compute_points_for_order(prog.name, order)
        self.assertAlmostEqual(result["points"], 10.0)

    def test_item_rule_beats_item_group_rule(self):
        prog = make_loyalty_program(code="TLE-PRECEDENCE", company=self.company)
        prog.append(
            "rules",
            {
                "scope": "Item Group",
                "item_group": "Beverages",
                "earn_basis": "Per Item Quantity",
                "points": 5,
                "priority": 10,
            },
        )
        prog.append(
            "rules",
            {
                "scope": "Item",
                "item_code": "LATTE",
                "earn_basis": "Per Item Quantity",
                "points": 50,
                "priority": 10,
            },
        )
        prog.save(ignore_permissions=True)

        order = {
            "items": [
                {"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20},
                {"item_code": "TEA", "qty": 2, "rate": 10, "amount": 20},
            ],
            "net_total": 40,
        }
        result = engine.compute_points_for_order(prog.name, order)
        self.assertEqual(result["points"], 60.0)

    def test_no_earn_rule_zeros_item(self):
        prog = make_loyalty_program(code="TLE-NOEARN", company=self.company)
        prog.append(
            "rules",
            {"scope": "No Earn", "item_code": "PASTRY", "points": 0, "priority": 10},
        )
        prog.save(ignore_permissions=True)

        order = {
            "items": [
                {"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20},
                {"item_code": "PASTRY", "qty": 1, "rate": 15, "amount": 15},
            ],
            "net_total": 35,
        }
        result = engine.compute_points_for_order(prog.name, order)
        self.assertEqual(result["points"], 20.0)

    def test_item_group_ancestor_match(self):
        prog = make_loyalty_program(code="TLE-IGANC", company=self.company)
        prog.append(
            "rules",
            {
                "scope": "Item Group",
                "item_group": "Beverages",
                "earn_basis": "Per Item Quantity",
                "points": 3,
                "priority": 10,
            },
        )
        prog.save(ignore_permissions=True)

        order = {
            "items": [{"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20}],
            "net_total": 20,
        }
        result = engine.compute_points_for_order(prog.name, order)
        self.assertEqual(result["points"], 3.0)

    def test_domain_scope_filters_program(self):
        prog = make_loyalty_program(
            code="TLE-DOMAIN",
            company=self.company,
            domain_scope="Restaurant",
            default_earn_points=5,
        )
        order_match = {
            "items": [{"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20}],
            "net_total": 20,
            "domain": "Restaurant",
        }
        order_miss = {
            "items": [{"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20}],
            "net_total": 20,
            "domain": "Pharmacy",
        }
        self.assertGreater(
            engine.compute_points_for_order(prog.name, order_match)["points"], 0
        )
        self.assertEqual(
            engine.compute_points_for_order(prog.name, order_miss)["points"], 0
        )

    def test_min_purchase_blocks_earn(self):
        prog = make_loyalty_program(
            code="TLE-MIN",
            company=self.company,
            min_purchase_to_earn=100,
        )
        order = {
            "items": [{"item_code": "LATTE", "qty": 1, "rate": 20, "amount": 20}],
            "net_total": 20,
        }
        result = engine.compute_points_for_order(prog.name, order)
        self.assertEqual(result["points"], 0)
        self.assertEqual(result["reason"], "below_min_purchase")

    # ---- redemption preview -----------------------------------------------

    def test_redemption_below_minimum_throws(self):
        prog = make_loyalty_program(
            code="TLE-MIN-REDEEM",
            company=self.company,
            min_points_to_redeem=100,
        )
        engine._ensure_wallet(self.customer, prog.name)
        engine.post_earn(self.customer, prog.name, 50, remarks="seed")

        with self.assertRaises(frappe.exceptions.ValidationError):
            engine.preview_redemption(prog.name, self.customer, 50, 100)

    def test_redemption_cap_enforced(self):
        prog = make_loyalty_program(
            code="TLE-CAP",
            company=self.company,
            min_points_to_redeem=10,
            max_redeem_percent=20,
            redemption_value=0.1,
        )
        engine._ensure_wallet(self.customer, prog.name)
        engine.post_earn(self.customer, prog.name, 1000, remarks="seed")

        with self.assertRaises(frappe.exceptions.ValidationError):
            engine.preview_redemption(prog.name, self.customer, 500, 100)

    def test_redemption_within_cap(self):
        prog = make_loyalty_program(
            code="TLE-OK",
            company=self.company,
            min_points_to_redeem=10,
            max_redeem_percent=100,
            redemption_value=0.1,
        )
        engine._ensure_wallet(self.customer, prog.name)
        engine.post_earn(self.customer, prog.name, 100, remarks="seed")

        result = engine.preview_redemption(prog.name, self.customer, 50, 100)
        self.assertEqual(result["points"], 50)
        self.assertAlmostEqual(result["value"], 5.0)

    # ---- ledger atomicity --------------------------------------------------

    def test_redeem_more_than_balance_throws(self):
        prog = make_loyalty_program(code="TLE-OVER", company=self.company)
        engine._ensure_wallet(self.customer, prog.name)
        engine.post_earn(self.customer, prog.name, 50, remarks="seed")

        with self.assertRaises(frappe.exceptions.ValidationError):
            engine.post_redeem(self.customer, prog.name, 100)

    def test_wallet_balance_recalculates_on_submit(self):
        prog = make_loyalty_program(code="TLE-BAL", company=self.company)
        wallet = engine._ensure_wallet(self.customer, prog.name)

        engine.post_earn(self.customer, prog.name, 30)
        engine.post_earn(self.customer, prog.name, 20)
        engine.post_redeem(self.customer, prog.name, 15)

        wallet.reload()
        self.assertEqual(wallet.current_balance, 35)
        self.assertEqual(wallet.lifetime_earned, 50)
        self.assertEqual(wallet.lifetime_redeemed, 15)

    def test_reverse_zeros_out_balance(self):
        prog = make_loyalty_program(code="TLE-REV", company=self.company)
        wallet = engine._ensure_wallet(self.customer, prog.name)

        engine.post_earn(
            self.customer,
            prog.name,
            40,
            reference_doctype="Sales Invoice",
            reference_name="SINV-TEST-001",
        )
        engine.post_reverse_for_invoice("SINV-TEST-001")

        wallet.reload()
        self.assertEqual(wallet.current_balance, 0)


if __name__ == "__main__":
    unittest.main()
