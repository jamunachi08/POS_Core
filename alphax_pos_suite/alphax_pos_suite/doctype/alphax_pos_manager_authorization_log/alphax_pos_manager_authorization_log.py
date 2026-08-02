"""
AlphaX POS Manager Authorization Log — controller.

Append-only audit log. Even a System Manager has only `read` permission
(write/create/delete are disabled in the doctype JSON), so log entries
can only be created by server-side code via `frappe.get_doc(...).insert(
ignore_permissions=True)`.

This is an intentional security property: an attacker who somehow gets
manager-level access cannot delete their own audit trail through the
normal Frappe UI.
"""
from __future__ import annotations

from frappe.model.document import Document


class AlphaXPOSManagerAuthorizationLog(Document):
    pass
