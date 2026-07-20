import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AlphaXPOSLoyaltyWallet(Document):
    def before_insert(self):
        if not self.enrolled_on:
            self.enrolled_on = now_datetime()

    def recalculate_balance(self):
        rows = frappe.db.sql(
            """
            select coalesce(sum(points), 0) as bal,
                   coalesce(sum(case when points > 0 then points else 0 end), 0) as earned,
                   coalesce(sum(case when points < 0 and entry_type = 'Redeem' then -points else 0 end), 0) as redeemed
            from `tabAlphaX POS Loyalty Ledger`
            where wallet = %s and docstatus = 1
            """,
            (self.name,),
            as_dict=True,
        )
        if rows:
            self.current_balance = float(rows[0]["bal"] or 0)
            self.lifetime_earned = float(rows[0]["earned"] or 0)
            self.lifetime_redeemed = float(rows[0]["redeemed"] or 0)
        self.last_activity_on = now_datetime()
        self._recalc_tier()
        self.db_update()

    def _recalc_tier(self):
        if not self.program:
            return
        prog = frappe.get_cached_doc("AlphaX POS Loyalty Program", self.program)
        tiers = sorted(
            [t for t in (prog.tiers or [])],
            key=lambda t: float(t.min_lifetime_points or 0),
            reverse=True,
        )
        for t in tiers:
            if float(self.lifetime_earned or 0) >= float(t.min_lifetime_points or 0):
                self.current_tier = t.tier_name
                return
        self.current_tier = None
