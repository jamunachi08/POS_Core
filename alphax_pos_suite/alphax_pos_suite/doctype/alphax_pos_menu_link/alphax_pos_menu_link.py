"""Attaches a menu to an outlet or a terminal.

Used in two places:
- AlphaX POS Outlet.menus      — what this place sells
- AlphaX POS Terminal.menus    — an override that REPLACES the outlet's

Empty controller — no doc-level logic needed.
"""
from frappe.model.document import Document


class AlphaXPOSMenuLink(Document):
    pass
