"""One movement on a store credit balance.

Append-only by intent: `on_update_after_submit` is not implemented, and a
mistake is corrected with a Reversal entry rather than an edit. An
auditable balance is one whose history cannot be rewritten.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

INCREASES = ("Issue", "Adjustment")
DECREASES = ("Redeem", "Expiry", "Reversal")


class AlphaXPOSStoreCreditEntry(Document):
    def validate(self):
        if flt(self.amount) <= 0:
            frappe.throw(_("Amount must be positive. Direction comes from the entry type."))

        credit = frappe.get_doc("AlphaX POS Store Credit", self.store_credit)
        self.customer = credit.customer
        self.currency = credit.currency
        self.posted_by = frappe.session.user

        if self.entry_type in DECREASES and self.entry_type != "Expiry":
            if credit.status != "Active":
                frappe.throw(_("Store credit {0} is {1}; it cannot be redeemed.")
                             .format(credit.name, credit.status))
            # Read the ledger, not the cached field: two tills redeeming
            # the same card at once would both see a stale cache.
            live = credit.recompute()
            if flt(self.amount) > live + 0.005:
                frappe.throw(_("Only {0} remains on this credit.")
                             .format(frappe.format_value(live, {"fieldtype": "Currency"})))

    def on_submit(self):
        credit = frappe.get_doc("AlphaX POS Store Credit", self.store_credit)
        balance = credit.recompute()
        self.db_set("balance_after", balance, update_modified=False)

    def on_cancel(self):
        frappe.get_doc("AlphaX POS Store Credit", self.store_credit).recompute()
