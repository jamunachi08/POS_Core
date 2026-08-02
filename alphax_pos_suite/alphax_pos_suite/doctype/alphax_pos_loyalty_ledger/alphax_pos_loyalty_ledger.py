import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AlphaXPOSLoyaltyLedger(Document):
    def validate(self):
        if not self.points or self.points == 0:
            frappe.throw(_("Points must be non-zero."))

        if self.entry_type == "Earn" and self.points <= 0:
            frappe.throw(_("Earn entries must have positive points."))
        if self.entry_type in ("Redeem", "Expire") and self.points >= 0:
            frappe.throw(_("Redeem and Expire entries must have negative points."))

        if not self.posted_by:
            self.posted_by = frappe.session.user

    def before_submit(self):
        wallet = frappe.get_doc("AlphaX POS Loyalty Wallet", self.wallet)

        new_balance = float(wallet.current_balance or 0) + float(self.points)

        if self.entry_type == "Redeem" and new_balance < -1e-6:
            frappe.throw(
                _("Insufficient points. Wallet balance is {0}, attempted to redeem {1}.").format(
                    wallet.current_balance, abs(self.points)
                )
            )

        self.balance_after = round(new_balance, 4)

    def on_submit(self):
        self._update_wallet()

    def on_cancel(self):
        self._update_wallet()

    def _update_wallet(self):
        wallet = frappe.get_doc("AlphaX POS Loyalty Wallet", self.wallet)
        wallet.recalculate_balance()
