import frappe
from frappe import _

@frappe.whitelist()
def get_credit_note_available(credit_note):
    if not credit_note or not frappe.db.exists("Sales Invoice", credit_note):
        frappe.throw(_("Credit note not found."))

    si = frappe.get_doc("Sales Invoice", credit_note)
    if si.docstatus != 1:
        frappe.throw(_("Credit note must be submitted."))
    if int(getattr(si, "is_return", 0) or 0) != 1:
        frappe.throw(_("Selected Sales Invoice is not a credit note (return)."))

    outstanding = float(getattr(si, "outstanding_amount", 0) or 0)
    available = abs(outstanding)
    return {"available": available}

def validate_credit_note_redemption(payments, invoice_total):
    total_cn = 0.0
    for p in (payments or []):
        if getattr(p, "payment_type", "Payment") != "Credit Note Redeem":
            continue
        cn = getattr(p, "credit_note", None)
        amt = float(getattr(p, "amount", 0) or 0)
        if not cn:
            frappe.throw(_("Credit Note is required for Credit Note Redeem."))
        available = get_credit_note_available(cn)["available"]
        if amt <= 0:
            frappe.throw(_("Credit note redeem amount must be greater than 0."))
        if amt > available + 1e-6:
            frappe.throw(_("Credit note amount cannot exceed available credit ({0}).").format(available))
        total_cn += amt

    if invoice_total is not None and total_cn > float(invoice_total or 0) + 1e-6:
        frappe.throw(_("Credit note redemption cannot exceed invoice total."))
    return total_cn

def _get_default_receivable(company):
    acc = frappe.db.get_value("Company", company, "default_receivable_account")
    if not acc:
        rows = frappe.db.sql("""select name from `tabAccount`
                              where company=%s and account_type='Receivable' and is_group=0
                              order by lft asc limit 1""", (company,))
        acc = rows[0][0] if rows else None
    return acc

def apply_credit_notes_via_payment_entry(sales_invoice, order_doc):
    cn_rows = [p for p in (order_doc.payments or []) if getattr(p, "payment_type", "Payment") == "Credit Note Redeem"]
    if not cn_rows:
        return None

    total_redeem = sum(float(getattr(p, "amount", 0) or 0) for p in cn_rows)
    if total_redeem <= 0:
        return None

    company = sales_invoice.company
    receivable = _get_default_receivable(company)
    if not receivable:
        frappe.throw(_("Could not determine Receivable account for company {0}. Set Company.default_receivable_account.").format(company))

    mop = "Credit Note"
    if not frappe.db.exists("Mode of Payment", mop):
        try:
            frappe.get_doc({"doctype":"Mode of Payment","mode_of_payment":mop,"enabled":1}).insert(ignore_permissions=True)
        except Exception:
            pass

    try:
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = sales_invoice.customer
        pe.company = company
        pe.posting_date = sales_invoice.posting_date
        pe.mode_of_payment = mop

        # Best-effort netting within receivable
        pe.paid_from = receivable
        pe.paid_to = receivable
        pe.paid_amount = total_redeem
        pe.received_amount = total_redeem

        pe.append("references", {"reference_doctype":"Sales Invoice","reference_name":sales_invoice.name,"allocated_amount":total_redeem})

        remaining = total_redeem
        for p in cn_rows:
            if remaining <= 0:
                break
            cn = p.credit_note
            amt = min(float(p.amount or 0), remaining)
            remaining -= amt
            pe.append("references", {"reference_doctype":"Sales Invoice","reference_name":cn,"allocated_amount":amt})

        pe.set_missing_values()
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AlphaX POS: Payment Entry credit note netting failed, fallback to JE")
        return _apply_credit_notes_via_journal_entry(sales_invoice, total_redeem, receivable)

def _apply_credit_notes_via_journal_entry(sales_invoice, total_redeem, receivable):
    if total_redeem <= 0:
        return None
    je = frappe.new_doc("Journal Entry")
    je.company = sales_invoice.company
    je.posting_date = sales_invoice.posting_date
    je.voucher_type = "Journal Entry"
    je.user_remark = f"Credit note redemption against {sales_invoice.name} (AlphaX POS)"
    je.append("accounts", {"account":receivable,"party_type":"Customer","party":sales_invoice.customer,
                           "debit_in_account_currency":total_redeem,"reference_type":"Sales Invoice","reference_name":sales_invoice.name})
    je.append("accounts", {"account":receivable,"party_type":"Customer","party":sales_invoice.customer,
                           "credit_in_account_currency":total_redeem,"reference_type":"Sales Invoice","reference_name":sales_invoice.name})
    je.insert(ignore_permissions=True)
    je.submit()
    return je.name
