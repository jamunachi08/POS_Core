import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url

from alphax_pos_suite.alphax_pos_suite.integrations.aggregators import protocol as P


class AlphaXAggregatorConnection(Document):
	def validate(self):
		base = f"{get_url()}/aggregator/{self.name or self.connection_name}"
		self.webhook_url = base if self.adapter == P.DH else f"{base}/webhook"
		if not (self.protocol_json or "").strip():
			self.protocol_json = json.dumps(P.template_for(self.adapter), indent=2, ensure_ascii=False)
		else:
			try:
				json.loads(self.protocol_json)
			except ValueError as e:
				frappe.throw(_("Protocol settings are not valid JSON: {0}").format(e))
		seen = set()
		for s in self.stores or []:
			if s.remote_store_id in seen:
				frappe.throw(_("Platform store id {0} is listed twice.").format(s.remote_store_id))
			seen.add(s.remote_store_id)
		if self.enabled and not self.sandbox and not self.customer:
			frappe.throw(_("Set the invoice customer before taking live orders."))

	def on_update(self):
		frappe.cache.delete_value(f"alphax_agg_token:{self.name}")
