import frappe
from frappe import _
from alphax_pos_suite.alphax_pos_suite.pos.redemption import validate_credit_note_redemption, apply_credit_notes_via_payment_entry

def _get_settings():
    if frappe.db.exists("DocType", "AlphaX POS Settings"):
        return frappe.get_single("AlphaX POS Settings")
    return None

def _ensure_role_allowed():
    allowed = {"AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"}
    roles = set(frappe.get_roles(frappe.session.user))
    if not (allowed & roles):
        frappe.throw(_("You are not permitted to submit POS Orders."))

def _ensure_shift_open(order_doc, settings):
    if not settings or int(getattr(settings, "require_shift_open", 0) or 0) != 1:
        return
    shift = frappe.db.get_value(
        "AlphaX POS Shift",
        {"pos_terminal": order_doc.pos_terminal, "user": frappe.session.user, "status": "Open"},
        "name",
    )
    if not shift:
        frappe.throw(_("Shift is not opened for this terminal/user. Please open a POS Shift first."))

def _needs_manager_approval(order_doc, settings):
    if not settings:
        return (False, None)

    reasons = []

    if int(getattr(settings, "require_manager_for_void", 1) or 1) == 1:
        if any(int(getattr(r, "is_void", 0) or 0) == 1 for r in (order_doc.items or [])):
            reasons.append("Void item(s) present")

    threshold = float(getattr(settings, "discount_threshold_percent", 0) or 0)
    if threshold > 0:
        if float(getattr(order_doc, "discount_percent", 0) or 0) > threshold:
            reasons.append(f"Order discount % > {threshold}")
        for r in (order_doc.items or []):
            if float(getattr(r, "discount_percent", 0) or 0) > threshold:
                reasons.append(f"Item discount % > {threshold}")

    if int(getattr(settings, "price_override_requires_approval", 1) or 1) == 1:
        if any(int(getattr(r, "price_overridden", 0) or 0) == 1 for r in (order_doc.items or [])):
            reasons.append("Price override used")

    if reasons:
        return (True, ", ".join(sorted(set(reasons))))
    return (False, None)

def _ensure_approved_if_required(order_doc, settings):
    needed, reason = _needs_manager_approval(order_doc, settings)
    if not needed:
        order_doc.db_set("approval_status", "Not Required", update_modified=False)
        order_doc.db_set("requires_approval", 0, update_modified=False)
        return

    order_doc.db_set("requires_approval", 1, update_modified=False)

    if order_doc.approval_status == "Approved":
        return

    roles = set(frappe.get_roles(frappe.session.user))
    if "AlphaX POS Manager" in roles or "System Manager" in roles:
        frappe.throw(_("Order requires approval. Set Approval Status = Approved, then submit."))
    else:
        order_doc.db_set("approval_status", "Pending", update_modified=False)
        order_doc.db_set("approval_reason", reason, update_modified=False)
        frappe.throw(_("Order requires manager approval: {0}").format(reason))

def on_order_submit(doc, method=None):
    _ensure_role_allowed()
    settings = _get_settings()

    if getattr(doc, "order_status", "Active") == "Hold":
        frappe.throw(_("This order is on Hold. Set Order Status to Active to submit/post."))

    _ensure_shift_open(doc, settings)
    _ensure_approved_if_required(doc, settings)

    enable_kds = bool(settings and int(getattr(settings, "enable_kds", 0) or 0) == 1)

    if doc.pos_outlet and frappe.db.exists("AlphaX POS Outlet", doc.pos_outlet):
        outlet = frappe.get_doc("AlphaX POS Outlet", doc.pos_outlet)
        ov = getattr(outlet, "enable_kds", "Use Global")
        if ov == "Yes":
            enable_kds = True
        elif ov == "No":
            enable_kds = False

    if enable_kds:
        _create_kds_ticket(doc)

    auto_post = True
    if settings and int(getattr(settings, "auto_create_sales_invoice", 1) or 1) == 0:
        auto_post = False

    if auto_post:
        si = create_sales_invoice_from_order(doc, settings=settings)
        doc.db_set("sales_invoice", si.name, update_modified=False)

def on_order_cancel(doc, method=None):
    if doc.sales_invoice and frappe.db.exists("Sales Invoice", doc.sales_invoice):
        try:
            si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
            if si.docstatus == 1 and si.get("alphax_pos_order") == doc.name:
                si.cancel()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "AlphaX POS: cancel linked SI failed")

def _apply_offer(si, order_doc):
    offer_code = (getattr(order_doc, "offer_code", None) or "").strip()
    if not offer_code:
        return

    offer = frappe.db.get_value(
        "AlphaX POS Offer",
        {"offer_code": offer_code, "enabled": 1},
        ["apply_on", "discount_type", "discount_value", "min_order_total", "item_code", "item_group"],
        as_dict=True,
    )
    if not offer:
        return

    min_total = float(offer.get("min_order_total") or 0)
    if min_total and float(si.net_total or 0) < min_total:
        return

    dtype = offer.get("discount_type")
    dval = float(offer.get("discount_value") or 0)

    if offer.get("apply_on") == "Order Total":
        if dtype == "Percent":
            si.additional_discount_percentage = dval
        else:
            si.discount_amount = dval

def create_sales_invoice_from_order(order_doc, settings=None):
    if not order_doc.customer:
        frappe.throw(_("Customer is required."))

    outlet = None
    terminal = None
    if order_doc.pos_terminal:
        terminal = frappe.get_doc("AlphaX POS Terminal", order_doc.pos_terminal)
        if terminal.pos_outlet:
            outlet = frappe.get_doc("AlphaX POS Outlet", terminal.pos_outlet)

    company = (outlet.company if outlet else getattr(order_doc, "company", None)) or frappe.defaults.get_global_default("company")
    if not company:
        frappe.throw(_("Company could not be determined. Set it on Outlet or Order."))

    si = frappe.new_doc("Sales Invoice")
    si.customer = order_doc.customer
    si.company = company
    si.set_posting_time = 1
    si.posting_date = order_doc.posting_date
    si.posting_time = order_doc.posting_time
    si.alphax_pos_order = order_doc.name

    si.is_pos = 1
    si.update_stock = 1 if (outlet and int(getattr(outlet, "update_stock", 1) or 1) == 1) else int(getattr(order_doc, "update_stock", 1) or 1)

    if int(getattr(order_doc, "is_return", 0) or 0) == 1:
        if not getattr(order_doc, "return_against", None):
            frappe.throw(_("Return Against Invoice is required for returns."))
        si.is_return = 1
        si.return_against = order_doc.return_against

    default_warehouse = (getattr(outlet, "warehouse", None) if outlet else None) or getattr(order_doc, "warehouse", None)

    if outlet:
        si.branch = getattr(outlet, "branch", None) or getattr(order_doc, "branch", None)
        si.cost_center = getattr(outlet, "cost_center", None) or getattr(order_doc, "cost_center", None)
        if getattr(outlet, "default_price_list", None):
            si.selling_price_list = outlet.default_price_list
        if getattr(outlet, "sales_taxes_and_charges_template", None):
            si.taxes_and_charges = outlet.sales_taxes_and_charges_template

    if not order_doc.items:
        frappe.throw(_("Order has no items."))

    for row in order_doc.items:
        if int(getattr(row, "is_void", 0) or 0) == 1:
            continue
        if not row.item_code:
            continue

        item_row = {
            "item_code": row.item_code,
            "qty": row.qty or 0,
            "rate": row.rate or 0,
            "warehouse": row.warehouse or default_warehouse,
        }

        if getattr(row, "batch_no", None):
            item_row["batch_no"] = row.batch_no
        if getattr(row, "serial_no", None):
            item_row["serial_no"] = row.serial_no

        dp = float(getattr(row, "discount_percent", 0) or 0)
        da = float(getattr(row, "discount_amount", 0) or 0)
        if dp:
            item_row["discount_percentage"] = dp
        if da:
            item_row["discount_amount"] = da

        si.append("items", item_row)

    if float(getattr(order_doc, "discount_percent", 0) or 0):
        si.additional_discount_percentage = float(order_doc.discount_percent or 0)
    if float(getattr(order_doc, "discount_amount", 0) or 0):
        si.discount_amount = float(order_doc.discount_amount or 0)

    # Service charge & tips as items (if configured)
    if settings and outlet:
        if int(getattr(settings, "enable_service_charge", 0) or 0) == 1 and float(getattr(order_doc, "service_charge_amount", 0) or 0) > 0 and getattr(outlet, "service_charge_item", None):
            si.append("items", {"item_code": outlet.service_charge_item, "qty": 1, "rate": float(order_doc.service_charge_amount or 0), "warehouse": default_warehouse})
        if int(getattr(settings, "enable_tips", 0) or 0) == 1 and float(getattr(order_doc, "tip_amount", 0) or 0) > 0 and getattr(outlet, "tips_item", None):
            si.append("items", {"item_code": outlet.tips_item, "qty": 1, "rate": float(order_doc.tip_amount or 0), "warehouse": default_warehouse})

    _apply_offer(si, order_doc)

    # Payments: for return, only if Cash Refund
    if order_doc.payments:
        for pay in order_doc.payments:
            if not pay.mode_of_payment:
                continue

            if int(getattr(order_doc, "is_return", 0) or 0) == 1:
                if getattr(order_doc, "return_settlement_mode", "Credit Note") != "Cash Refund":
                    continue
                amt = abs(float(pay.amount or 0))
            else:
                amt = float(pay.amount or 0)

            si.append("payments", {"mode_of_payment": pay.mode_of_payment, "amount": amt, "reference_no": getattr(pay, "reference_no", None)})

    si.set_missing_values()
    si.calculate_taxes_and_totals()

    validate_credit_note_redemption(order_doc.payments, si.grand_total)


    si.insert(ignore_permissions=True)
    si.submit()

    try:
        apply_credit_notes_via_payment_entry(si, order_doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AlphaX POS: credit note redemption posting failed")

    return si

def _find_station_for_item(item_code):
    return frappe.db.get_value("AlphaX POS Item Station", {"item_code": item_code}, "station")

def _create_kds_ticket(order_doc):
    ticket = frappe.new_doc("AlphaX POS KDS Ticket")
    ticket.pos_order = order_doc.name
    ticket.customer = order_doc.customer
    ticket.outlet = order_doc.pos_outlet
    ticket.table = getattr(order_doc, "table", None)
    ticket.status = "New"

    for row in order_doc.items:
        if int(getattr(row, "is_void", 0) or 0) == 1:
            continue
        station = _find_station_for_item(row.item_code)
        ticket.append("items", {"item_code": row.item_code, "qty": row.qty, "notes": getattr(row, "notes", None), "status": "Queued", "station": station})

    ticket.insert(ignore_permissions=True)
    order_doc.db_set("kds_ticket", ticket.name, update_modified=False)

    try:
        frappe.publish_realtime("alphax_pos_kds_new_ticket", {"ticket": ticket.name, "outlet": ticket.outlet})
    except Exception:
        pass

    return ticket

@frappe.whitelist()
def update_kds_item_status(ticket_name, rowname, status):
    ticket = frappe.get_doc("AlphaX POS KDS Ticket", ticket_name)
    for r in ticket.items:
        if r.name == rowname:
            r.status = status
            break
    ticket.save(ignore_permissions=True)
    try:
        frappe.publish_realtime("alphax_pos_kds_status", {"ticket": ticket.name, "row": rowname, "status": status})
    except Exception:
        pass
    return {"ok": True}
