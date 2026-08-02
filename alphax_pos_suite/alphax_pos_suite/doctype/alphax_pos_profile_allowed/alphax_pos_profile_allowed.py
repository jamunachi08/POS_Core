"""Child table linking Terminal/User to POS Profile entries.

Used in two places:
- AlphaX POS Terminal.allowed_pos_profiles
- User.allowed_pos_profiles (custom field)

Empty controller — no doc-level logic needed.
"""
from frappe.model.document import Document


class AlphaXPOSProfileAllowed(Document):
    pass
