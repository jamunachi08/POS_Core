import frappe
from frappe import _
from datetime import date

def is_erpnext_available() -> bool:
    try:
        return "erpnext" in frappe.get_installed_apps()
    except Exception:
        return False

def get_settings():
    # Single doctype
    try:
        return frappe.get_single("AlphaX POS Settings")
    except Exception:
        return None

def _resolve_company(settings, request_doc):
    return getattr(request_doc, "company", None) or getattr(settings, "central_kitchen_company", None) or frappe.defaults.get_user_default("Company")

def _resolve_warehouses(settings, request_doc):
    from_wh = getattr(request_doc, "from_warehouse", None) or getattr(settings, "central_kitchen_default_from_warehouse", None)
    to_wh = getattr(request_doc, "to_warehouse", None) or getattr(settings, "central_kitchen_default_to_warehouse", None)
    return from_wh, to_wh

def ensure_mapping_or_throw(settings, request_doc):
    from_wh, to_wh = _resolve_warehouses(settings, request_doc)
    require = int(getattr(settings, "central_kitchen_require_mapping", 1) or 0)
    if require and (not from_wh or not to_wh):
        frappe.throw(_("Central Kitchen warehouses are not mapped. Please set From/To warehouses in the request or in AlphaX POS Settings."))
    return from_wh, to_wh

def create_material_request_from_ck_request(request_name: str, force: bool = False) -> str:
    """Create an ERPNext Material Request from a Central Kitchen Request.

    - If `force` is False, this respects the setting `central_kitchen_auto_create_material_request`.
    - If `force` is True, it creates the Material Request even when auto-create is disabled.

    The created MR is linked back to the Central Kitchen Request.
    """
    if not is_erpnext_available():
        return None

    settings = get_settings()
    if not settings or not int(getattr(settings, "enable_central_kitchen_integration", 0) or 0):
        return None
    if not force and not int(getattr(settings, "central_kitchen_auto_create_material_request", 0) or 0):
        return None

    req = frappe.get_doc("AlphaX POS Central Kitchen Request", request_name)
    if getattr(req, "erpnext_material_request", None):
        return req.erpnext_material_request

    from_wh, to_wh = ensure_mapping_or_throw(settings, req)
    company = _resolve_company(settings, req)
    mr_type = getattr(settings, "central_kitchen_material_request_type", None) or "Material Transfer"

    mr = frappe.new_doc("Material Request")
    mr.material_request_type = mr_type
    mr.company = company
    # For Material Transfer requests, target warehouse is typically set in items
    mr.schedule_date = date.today()
    mr.set_warehouse = to_wh

    for row in getattr(req, "items", []) or []:
        if not row.item_code or not row.qty:
            continue
        it = mr.append("items", {})
        it.item_code = row.item_code
        it.qty = float(row.qty)
        if row.uom:
            it.uom = row.uom
        it.warehouse = to_wh
        it.schedule_date = date.today()

    mr.insert(ignore_permissions=True)
    try:
        mr.submit()
    except Exception:
        # Some sites restrict auto submit; keep as Draft if submit fails
        pass

    req.db_set("erpnext_material_request", mr.name)
    req.db_set("company", company)
    req.db_set("requested_on", frappe.utils.now_datetime())
    if getattr(req, "status", None) == "Draft":
        req.db_set("status", "Submitted")
    return mr.name

def create_stock_entry_from_ck_request(request_name: str) -> str:
    """Creates ERPNext Stock Entry (Material Transfer/Issue) and links it."""
    if not is_erpnext_available():
        return None

    settings = get_settings()
    if not settings or not int(getattr(settings, "enable_central_kitchen_integration", 0) or 0):
        return None
    if not int(getattr(settings, "central_kitchen_auto_create_stock_entry_on_fulfill", 0) or 0):
        return None

    req = frappe.get_doc("AlphaX POS Central Kitchen Request", request_name)
    if getattr(req, "erpnext_stock_entry", None):
        return req.erpnext_stock_entry

    from_wh, to_wh = ensure_mapping_or_throw(settings, req)
    company = _resolve_company(settings, req)
    purpose = getattr(settings, "central_kitchen_stock_entry_purpose", None) or "Material Transfer"

    se = frappe.new_doc("Stock Entry")
    se.purpose = purpose
    se.company = company

    for row in getattr(req, "items", []) or []:
        if not row.item_code or not row.qty:
            continue
        it = se.append("items", {})
        it.item_code = row.item_code
        it.qty = float(row.qty)
        if row.uom:
            it.uom = row.uom
        if purpose == "Material Issue":
            it.s_warehouse = from_wh
        else:
            it.s_warehouse = from_wh
            it.t_warehouse = to_wh

    se.insert(ignore_permissions=True)
    try:
        se.submit()
    except Exception:
        pass

    req.db_set("erpnext_stock_entry", se.name)
    req.db_set("company", company)
    req.db_set("fulfilled_on", frappe.utils.now_datetime())
    req.db_set("status", "Fulfilled")
    return se.name
