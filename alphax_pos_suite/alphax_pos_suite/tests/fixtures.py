"""
Shared test fixtures for AlphaX POS test cases.

Designed to run inside `bench --site <site> run-tests --app alphax_pos_suite`.
Each helper is idempotent and cleans up after itself when the test class tears
down.
"""

import frappe
from frappe.utils import nowdate


def ensure_company(company_name="AlphaX Test Co"):
    if frappe.db.exists("Company", company_name):
        return company_name
    doc = frappe.get_doc({
        "doctype": "Company",
        "company_name": company_name,
        "abbr": "ATC",
        "default_currency": "USD",
        "country": "United States",
    })
    doc.insert(ignore_permissions=True)
    return company_name


def ensure_item_group(name, parent="All Item Groups"):
    if frappe.db.exists("Item Group", name):
        return name
    doc = frappe.get_doc({
        "doctype": "Item Group",
        "item_group_name": name,
        "parent_item_group": parent,
        "is_group": 0,
    })
    doc.insert(ignore_permissions=True)
    return name


def ensure_item(item_code, item_group="All Item Groups", rate=10.0, is_sales=1):
    if frappe.db.exists("Item", item_code):
        return item_code
    doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_code,
        "item_group": item_group,
        "stock_uom": "Unit",
        "is_sales_item": is_sales,
        "is_stock_item": 0,
        "standard_rate": rate,
    })
    doc.insert(ignore_permissions=True)
    return item_code


def ensure_customer(name="Test Customer"):
    if frappe.db.exists("Customer", name):
        return name
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_type": "Individual",
        "customer_group": "All Customer Groups",
        "territory": "All Territories",
    })
    doc.insert(ignore_permissions=True)
    return name


def ensure_domain_packs():
    """Seed the eight domain packs."""
    from alphax_pos_suite.alphax_pos_suite.patches.v15_0.upgrade_to_vertical_platform import (
        _seed_domain_packs,
    )
    _seed_domain_packs()


def make_loyalty_program(code="TEST-LOY", company=None, **overrides):
    """Create or get a test loyalty program."""
    company = company or ensure_company()
    if frappe.db.exists("AlphaX POS Loyalty Program", code):
        frappe.delete_doc(
            "AlphaX POS Loyalty Program", code, force=True, ignore_permissions=True
        )
    base = {
        "doctype": "AlphaX POS Loyalty Program",
        "program_code": code,
        "program_name": code,
        "enabled": 1,
        "company": company,
        "domain_scope": "All Domains",
        "earn_basis": "Per Currency Spent",
        "default_earn_points": 1,
        "default_earn_per_amount": 1,
        "redemption_value": 0.01,
        "min_points_to_redeem": 100,
        "max_redeem_percent": 50,
        "expiry_days": 365,
    }
    base.update(overrides)
    doc = frappe.get_doc(base)
    doc.insert(ignore_permissions=True)
    return doc


def make_outlet(outlet_name="TEST-OUT", company=None, domains=None, primary="Generic"):
    company = company or ensure_company()
    ensure_domain_packs()
    if frappe.db.exists("AlphaX POS Outlet", outlet_name):
        frappe.delete_doc(
            "AlphaX POS Outlet", outlet_name, force=True, ignore_permissions=True
        )
    doc = frappe.new_doc("AlphaX POS Outlet")
    doc.outlet_name = outlet_name
    doc.company = company
    doc.primary_domain = primary
    for d in (domains or [primary]):
        doc.append("domains", {"domain": d})
    doc.insert(ignore_permissions=True)
    return doc
