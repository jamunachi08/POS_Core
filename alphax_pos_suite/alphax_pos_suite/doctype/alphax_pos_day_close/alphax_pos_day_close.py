import frappe
from frappe.model.document import Document
from alphax_pos_suite.alphax_pos_suite.reporting.close_reports import (
    build_day_close_context,
    recompute_day_close,
    maybe_send_close_email,
)

class AlphaXPOSDayClose(Document):
    def validate(self):
        recompute_day_close(self)

    def on_submit(self):
        ctx = build_day_close_context(self)
        maybe_send_close_email(
            report_type="Day Close",
            company=ctx.get("company"),
            terminal=ctx.get("terminal"),
            pos_profile=ctx.get("pos_profile"),
            reference_doctype=self.doctype,
            reference_name=self.name,
            context=ctx,
            print_doctype=self.doctype,
            print_name=self.name,
            print_format="AlphaX POS Day Close"
        )
