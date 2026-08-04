import frappe
from frappe.model.document import Document


class AlphaXPOSProcessingLog(Document):
    pass


@frappe.whitelist()
def get_latest_errors(limit=20):
    limit = int(limit or 20)
    return frappe.get_all(
        "AlphaX POS Processing Log",
        filters={"status": ["in", ["Error", "Retry"]]},
        fields=["name", "sales_invoice", "stock_entry", "status", "error", "modified"],
        order_by="modified desc",
        limit_page_length=min(limit, 200),
    )
