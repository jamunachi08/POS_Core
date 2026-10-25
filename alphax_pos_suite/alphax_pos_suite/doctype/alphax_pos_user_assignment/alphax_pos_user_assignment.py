"""Where a person is allowed to sell.

Resolution and permission checks live in
alphax_pos_suite.alphax_pos_suite.session.api, which is the only consumer:
a row on its own carries no meaning until it is read against the terminals
that actually exist in that branch.

Empty controller — no doc-level logic needed.
"""
from frappe.model.document import Document


class AlphaXPOSUserAssignment(Document):
    pass
