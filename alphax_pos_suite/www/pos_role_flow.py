"""Route controller for /pos_role_flow.

Login required. The payload is resolved per user, so two people opening the
same URL get different pages: a cashier gets one lane and a trimmed matrix,
a manager gets every lane and the full grid.
"""

import frappe

from alphax_pos_suite.alphax_pos_suite.pos.role_flow import get_context_payload

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/pos_role_flow"
        raise frappe.Redirect

    payload = get_context_payload()

    context.no_cache = 1
    context.show_sidebar = False
    context.title = "AlphaX POS \u2014 Role Flow"
    context.lanes = payload["lanes"]
    context.columns = payload["columns"]
    context.matrix = payload["matrix"]
    context.full_matrix = payload["full_matrix"]
    context.user_roles = payload["user_roles"]
    context.has_access = payload["has_access"]
    context.current_user = frappe.session.user

    return context
