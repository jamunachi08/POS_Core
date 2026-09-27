import frappe
from frappe.utils import flt, now_datetime

def _is_capture_mop(mop_name: str) -> bool:
    fields = ["capture_terminal_data", "aps_capture_terminal_data", "act_capture_terminal_data"]
    for fn in fields:
        try:
            val = frappe.db.get_value("Mode of Payment", mop_name, fn)
            if val is not None:
                return bool(val)
        except Exception:
            continue
    return False

def _autofill_payment_row(p):
    if getattr(p, "aps_captured_on", None):
        return
    rrn = (getattr(p, "aps_rrn", None) or "").strip()
    if not rrn:
        rrn = (getattr(p, "reference_no", None) or "").strip()
        if rrn:
            p.aps_rrn = rrn

    if rrn or (getattr(p, "aps_auth_code", None) or "").strip():
        p.aps_captured_on = now_datetime()
        if not (getattr(p, "aps_txn_status", None) or "").strip():
            p.aps_txn_status = "Approved"

def sales_invoice_validate(doc, method=None):
    for p in (doc.payments or []):
        mop = getattr(p, "mode_of_payment", None)
        if not mop or not _is_capture_mop(mop):
            continue
        _autofill_payment_row(p)

def sales_invoice_on_submit(doc, method=None):
    for p in (doc.payments or []):
        mop = getattr(p, "mode_of_payment", None)
        if not mop or not _is_capture_mop(mop):
            continue

        exists = frappe.db.exists("AlphaX POS Card Transaction", {
            "reference_doctype": "Sales Invoice",
            "reference_name": doc.name,
            "mode_of_payment": mop
        })
        if exists:
            continue

        tx = frappe.new_doc("AlphaX POS Card Transaction")
        tx.status = getattr(p, "aps_txn_status", None) or "Approved"
        tx.amount = flt(getattr(p, "amount", 0))
        tx.currency = doc.currency
        tx.reference_doctype = "Sales Invoice"
        tx.reference_name = doc.name
        tx.mode_of_payment = mop
        tx.rrn = getattr(p, "aps_rrn", None) or getattr(p, "reference_no", None) or ""
        tx.auth_code = getattr(p, "aps_auth_code", None) or ""
        tx.terminal_id = getattr(p, "aps_terminal_id", None) or ""
        tx.merchant_id = getattr(p, "aps_merchant_id", None) or ""
        tx.tender_brand = getattr(p, "aps_card_brand", None) or mop
        tx.response_message = "Auto-logged from Sales Invoice submit"
        tx.insert(ignore_permissions=True)

        try:
            if getattr(p, "name", None):
                frappe.db.set_value("Sales Invoice Payment", p.name, "aps_card_transaction", tx.name, update_modified=False)
        except Exception:
            pass

@frappe.whitelist()
def update_sales_invoice_payment_capture(sales_invoice: str, payment_row: str, payload: dict):
    if not (sales_invoice and payment_row):
        frappe.throw("Missing sales_invoice or payment_row")

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    row = None
    for p in (si.payments or []):
        if p.name == payment_row:
            row = p
            break
    if not row:
        frappe.throw("Payment row not found on Sales Invoice")

    safe_map = {
        "aps_txn_status": "status",
        "aps_rrn": "rrn",
        "aps_auth_code": "auth_code",
        "aps_terminal_id": "terminal_id",
        "aps_merchant_id": "merchant_id",
        "aps_card_brand": "tender_brand",
    }
    for target, src in safe_map.items():
        v = (payload or {}).get(src)
        if v is not None:
            setattr(row, target, v)

    row.aps_captured_on = frappe.utils.now_datetime()
    si.save(ignore_permissions=True)
    return {"ok": True, "sales_invoice": si.name, "payment_row": payment_row}


def sales_invoice_before_submit(doc, method=None):
    # Enforcement toggle sits on ERPNext POS Profile
    if not getattr(doc, "is_pos", None):
        return

    require_rrn = False
    require_approved = False
    try:
        if getattr(doc, "pos_profile", None):
            require_rrn = bool(frappe.db.get_value("POS Profile", doc.pos_profile, "aps_require_rrn_before_submit"))
            require_approved = bool(frappe.db.get_value("POS Profile", doc.pos_profile, "aps_require_approved_status_before_submit"))
    except Exception:
        pass

    if not (require_rrn or require_approved):
        return

    missing = []
    bad_status = []
    for p in (doc.payments or []):
        mop = getattr(p, "mode_of_payment", None)
        if not mop or not _is_capture_mop(mop):
            continue
        if flt(getattr(p, "amount", 0)) <= 0:
            continue

        rrn = (getattr(p, "aps_rrn", None) or getattr(p, "reference_no", None) or "").strip()
        status = (getattr(p, "aps_txn_status", None) or "").strip()

        if require_rrn and not rrn:
            missing.append(mop)
        if require_approved and (not status or status != "Approved"):
            bad_status.append(f"{mop} ({status or 'no status'})")

    if missing:
        frappe.throw("Terminal reference (RRN) is required before submitting this POS invoice. Missing for: " + ", ".join(sorted(set(missing))))
    if bad_status:
        frappe.throw("Terminal status must be Approved before submitting this POS invoice. Issue(s): " + ", ".join(sorted(set(bad_status))))
