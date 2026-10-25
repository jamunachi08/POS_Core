import frappe

def get_shift_expected_cash(shift_name):
    settings = frappe.get_single('AlphaX POS Settings') if frappe.db.exists('DocType','AlphaX POS Settings') else None
    cash_mop = getattr(settings, 'cash_mode_of_payment', None) if settings else 'Cash'

    if not shift_name or not frappe.db.exists("AlphaX POS Shift", shift_name):
        return 0.0

    sh = frappe.get_doc("AlphaX POS Shift", shift_name)
    opened_on = sh.opened_on
    terminal = sh.pos_terminal
    user = sh.user

    cash_sales = frappe.db.sql(
        """select sum(p.amount)
           from `tabAlphaX POS Order` o
           join `tabAlphaX POS Payment` p on p.parent = o.name
          where o.docstatus = 1
            and o.pos_terminal = %s
            and o.owner = %s
            and o.modified >= %s
            and p.payment_type = 'Payment'
            and p.mode_of_payment = %s""",
        (terminal, user, opened_on, cash_mop)
    )[0][0] or 0

    mv = frappe.db.sql(
        """select movement_type, sum(amount) amt
           from `tabAlphaX POS Cash Movement`
          where shift = %s and docstatus < 2
          group by movement_type""",
        (shift_name,),
        as_dict=True
    )

    def s(t):
        return float(sum(x.amt for x in mv if x.movement_type == t) or 0)

    expected = float(cash_sales) + s("Paid In") - s("Paid Out") - s("Petty Cash Expense") - s("Cash Drop To Safe")
    return expected
