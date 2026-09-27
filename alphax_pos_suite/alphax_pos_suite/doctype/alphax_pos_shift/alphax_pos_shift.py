import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from alphax_pos_suite.alphax_pos_suite.reporting.close_reports import (
    build_shift_close_context,
    maybe_send_close_email,
)

class AlphaXPOSShift(Document):
    def on_submit(self):
        # mark close time if not set
        if not self.closed_on:
            self.db_set("closed_on", now_datetime(), update_modified=False)

        ctx = build_shift_close_context(self)
        maybe_send_close_email(
            report_type="Shift Close",
            company=ctx.get("company"),
            terminal=ctx.get("terminal"),
            pos_profile=ctx.get("pos_profile"),
            reference_doctype=self.doctype,
            reference_name=self.name,
            context=ctx,
            print_doctype=self.doctype,
            print_name=self.name,
            print_format="AlphaX POS Shift Close"
        )
