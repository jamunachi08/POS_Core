import frappe


def _get_settings():
    try:
        return frappe.get_single("AlphaX POS Settings")
    except Exception:
        return None


def _log(status, sales_invoice, stock_entry=None, error=None, company=None):
    try:
        log = frappe.new_doc("AlphaX POS Processing Log")
        log.sales_invoice = sales_invoice
        log.stock_entry = stock_entry
        log.status = status
        log.error = (error or "")[:2000]
        log.company = company
        log.insert(ignore_permissions=True)
        return log.name
    except Exception:
        # don't block invoice submit
        frappe.log_error(frappe.get_traceback(), title="AlphaX POS Processing: logging failed")
        return None


def on_sales_invoice_submit(doc, method=None):
    """Create Material Issue Stock Entry for recipe-based consumption.

    Booster improvements:
    - Configurable via AlphaX POS Settings
    - Prevent duplicate posting per invoice
    - Write a processing log for audit & troubleshooting
    """
    try:
        if not doc.get("is_pos"):
            return

        settings = _get_settings()
        if settings and not settings.get("enable_recipe_consumption"):
            return

        # prevent duplicates
        if frappe.db.exists("AlphaX POS Processing Log", {"sales_invoice": doc.name, "status": "Done"}):
            return

        process_wh = None
        if settings and settings.get("use_invoice_set_warehouse"):
            process_wh = doc.get("set_warehouse") or doc.get("warehouse")
        if not process_wh:
            process_wh = settings.get("consumption_warehouse") if settings else None
        if not process_wh:
            return

        consumption = []
        for it in doc.items:
            recipe = frappe.db.get_value(
                "AlphaX POS Recipe",
                {"item_code": it.item_code, "disabled": 0},
                "name",
            )
            if not recipe:
                continue
            recipe_doc = frappe.get_doc("AlphaX POS Recipe", recipe)
            for r in recipe_doc.items:
                qty = (r.qty or 0) * (it.qty or 0)
                if qty <= 0:
                    continue
                consumption.append(
                    {
                        "item_code": r.material_item,
                        "qty": qty,
                        "s_warehouse": process_wh,
                        "cost_center": settings.get("consumption_cost_center") if settings else None,
                    }
                )

        if not consumption:
            return

        _log("Queued", doc.name, company=doc.company)

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.company = doc.company
        se.posting_date = doc.posting_date
        se.posting_time = doc.posting_time
        se.set_posting_time = 1
        for row in consumption:
            se.append("items", row)

        se.insert(ignore_permissions=True)
        se.submit()

        # store link on invoice if custom field exists
        if frappe.db.has_column("Sales Invoice", "aps_consumption_stock_entry"):
            frappe.db.set_value("Sales Invoice", doc.name, "aps_consumption_stock_entry", se.name)

        _log("Done", doc.name, stock_entry=se.name, company=doc.company)
    except Exception:
        tb = frappe.get_traceback()
        _log("Error", doc.name, error=tb, company=getattr(doc, "company", None))
        frappe.log_error(title="AlphaX Bonanza POS processing failed", message=tb)
