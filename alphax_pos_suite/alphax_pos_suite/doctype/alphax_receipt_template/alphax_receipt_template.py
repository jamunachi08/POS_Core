import frappe
from frappe import _
from frappe.model.document import Document

from alphax_pos_suite.alphax_pos_suite.receipts import render


class AlphaXReceiptTemplate(Document):
	def validate(self):
		if not self.blocks:
			for b in render.DEFAULT_BLOCKS:
				self.append("blocks", b)
		missing = render.compliance([b.as_dict() for b in self.blocks])
		self.compliance = (_("Missing for a simplified tax invoice: ") + "; ".join(missing)) if missing else _("All ZATCA simplified-invoice elements present.")
		if missing:
			frappe.msgprint(self.compliance, indicator="orange", alert=True)
		if self.is_default:
			frappe.db.sql("update `tabAlphaX Receipt Template` set is_default=0 where name!=%s", self.name)

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)
