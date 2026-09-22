"""Money owed to a customer.

Deliberately separate from AlphaX POS Loyalty Wallet. Points are a
marketing accrual the business may devalue or expire at will; store credit
is cash the customer already handed over, or a refund they are owed. They
have different balances, different rules and — the part that matters —
different accounting. Merging them into one "wallet" is convenient right
up to the first audit.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class AlphaXPOSStoreCredit(Document):
    def validate(self):
        if not self.currency:
            self.currency = frappe.db.get_value("Company", self.company, "default_currency")
        if self.status == "Closed" and flt(self.balance) > 0.005:
            frappe.throw(_("Cannot close a credit that still holds {0}.")
                         .format(frappe.format_value(self.balance, {"fieldtype": "Currency"})))
        if self.card_code:
            self.card_code = self.card_code.strip().upper()

    def recompute(self):
        """Authoritative balance: the sum of the entries, never anything else.

        The `balance` field is a cache for list views and the till. A
        stored balance that drifts from its ledger is unfixable after the
        fact because nobody knows which of the two was right.
        """
        rows = frappe.get_all(
            "AlphaX POS Store Credit Entry",
            filters={"store_credit": self.name, "docstatus": ["<", 2]},
            fields=["entry_type", "amount"],
        )
        issued = sum(flt(r.amount) for r in rows if r.entry_type in ("Issue", "Adjustment"))
        spent = sum(flt(r.amount) for r in rows if r.entry_type in ("Redeem", "Expiry", "Reversal"))
        self.db_set("total_issued", issued, update_modified=False)
        self.db_set("total_redeemed", spent, update_modified=False)
        self.db_set("balance", issued - spent, update_modified=False)
        self.db_set("last_activity_on", now_datetime(), update_modified=False)
        return issued - spent
