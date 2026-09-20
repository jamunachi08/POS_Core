"""One Include/Exclude line of a menu.

Row-level validation lives on the parent (AlphaX POS Menu), because a rule
only means anything in the context of the set it contributes to: an Exclude
with no Include is a menu that sells nothing, and that is a parent-level
fact.

Empty controller — but not an optional one. Frappe imports a module for
every DocType, child tables included, and refuses to install the app
without it.
"""
from frappe.model.document import Document


class AlphaXPOSMenuRule(Document):
    pass
