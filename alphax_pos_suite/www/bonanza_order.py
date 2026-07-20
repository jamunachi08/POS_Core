import frappe
from frappe.website.page_renderers.template_page import TemplatePage

def get_context(context):
    # token is provided in route param via frappe.local.form_dict or request.path
    path = frappe.request.path if hasattr(frappe, "request") else ""
    token = (frappe.form_dict.get("token") if hasattr(frappe, "form_dict") else None) or ""
    if not token:
        # try parse /bonanza/order/<token>
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[-2] == "order":
            token = parts[-1]
    context.token = token
    context.no_cache = 1
    return context
