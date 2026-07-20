"""AlphaX POS Printer Profile controller.

Mostly a config record — printing logic lives in the client-side
alphax_qz_print.js, with optional server-side helpers in
alphax_pos_suite.integrations.printing.
"""
from frappe.model.document import Document


class AlphaXPOSPrinterProfile(Document):
    pass
