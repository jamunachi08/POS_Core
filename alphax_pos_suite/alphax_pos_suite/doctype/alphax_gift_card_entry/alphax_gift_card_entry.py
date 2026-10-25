import frappe
from frappe import _
from frappe.model.document import Document


class AlphaXGiftCardEntry(Document):
	"""Ledger row. Written by the gift card service only; never changed afterwards."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Gift card entries cannot be changed. Post a correcting entry instead."))
		if (self.amount or 0) <= 0:
			frappe.throw(_("Amount must be positive; the entry type gives the direction."))

	def on_trash(self):
		frappe.throw(_("Gift card entries cannot be deleted."))
