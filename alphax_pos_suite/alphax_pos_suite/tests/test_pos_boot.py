"""
Tests for the unified pos_boot endpoint.
"""

import unittest

import frappe

from alphax_pos_suite.alphax_pos_suite.boot.api import (
    _collect_active_domains,
    _union_features,
)
from alphax_pos_suite.alphax_pos_suite.tests.fixtures import (
    ensure_company,
    ensure_domain_packs,
    make_outlet,
)


class TestPOSBoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.company = ensure_company()
        ensure_domain_packs()

    def test_single_domain_outlet_features(self):
        outlet = make_outlet(
            "TEST-BOOT-RESTO", self.company, domains=["Restaurant"], primary="Restaurant"
        )
        domains = _collect_active_domains(outlet)
        feats = _union_features(domains)
        self.assertEqual(feats["uses_floor_plan"], 1)
        self.assertEqual(feats["uses_kds"], 1)
        self.assertEqual(feats["uses_modifiers"], 1)
        self.assertEqual(feats["uses_prescription"], 0)
        self.assertEqual(feats["uses_appointments"], 0)

    def test_multi_domain_outlet_unions_features(self):
        outlet = make_outlet(
            "TEST-BOOT-MIX",
            self.company,
            domains=["Cafe", "Pharmacy", "Salon"],
            primary="Cafe",
        )
        domains = _collect_active_domains(outlet)
        feats = _union_features(domains)
        self.assertEqual(feats["uses_modifiers"], 1)
        self.assertEqual(feats["uses_prescription"], 1)
        self.assertEqual(feats["uses_appointments"], 1)
        self.assertEqual(feats["uses_loyalty"], 1)

    def test_outlet_with_no_domains_falls_back_to_generic(self):
        outlet = frappe.new_doc("AlphaX POS Outlet")
        outlet.outlet_name = "TEST-BOOT-EMPTY"
        outlet.company = self.company
        outlet.primary_domain = "Generic"
        outlet.insert(ignore_permissions=True)
        try:
            domains = _collect_active_domains(outlet)
            self.assertEqual(len(domains), 1)
            self.assertEqual(domains[0]["domain_code"], "Generic")
        finally:
            frappe.delete_doc(
                "AlphaX POS Outlet",
                outlet.name,
                force=True,
                ignore_permissions=True,
            )


if __name__ == "__main__":
    unittest.main()
