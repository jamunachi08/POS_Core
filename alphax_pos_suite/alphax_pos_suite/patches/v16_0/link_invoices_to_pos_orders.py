"""v16.0.0 — create Sales Invoice.alphax_pos_order and backfill it.

Posting has always assigned ``si.alphax_pos_order``, but the custom field was
never created, so the value was dropped on insert. This creates the field (the
after_migrate seeder runs after patches, too late for the backfill) and fills it
from each order's own ``sales_invoice`` pointer. Idempotent.
"""

import frappe


def execute():
	if not frappe.db.table_exists("AlphaX POS Order") or not frappe.db.table_exists("Sales Invoice"):
		return

	if not frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "alphax_pos_order"}):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		create_custom_field(
			"Sales Invoice",
			{
				"fieldname": "alphax_pos_order",
				"label": "AlphaX POS Order",
				"fieldtype": "Link",
				"options": "AlphaX POS Order",
				"insert_after": "pos_profile",
				"read_only": 1,
				"no_copy": 1,
				"search_index": 1,
				"print_hide": 1,
			},
		)
		frappe.clear_cache(doctype="Sales Invoice")

	if not frappe.db.has_column("Sales Invoice", "alphax_pos_order"):
		return

	rows = frappe.db.sql(
		"""
		select o.name as order_name, o.sales_invoice
		from `tabAlphaX POS Order` o
		join `tabSales Invoice` si on si.name = o.sales_invoice
		where coalesce(o.sales_invoice, '') != ''
			and coalesce(si.alphax_pos_order, '') = ''
		""",
		as_dict=True,
	)
	for r in rows:
		frappe.db.set_value(
			"Sales Invoice", r.sales_invoice, "alphax_pos_order", r.order_name, update_modified=False
		)
	if rows:
		frappe.db.commit()
