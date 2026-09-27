"""Route controller for /pos_login.

A cashier's first screen. Frappe's own /login is a desk login and reads
like one; this is the till's front door — branded, bilingual, and it lands
the user straight on the cashier screen rather than on a desk workspace.

Guest-accessible by design. Nothing here reveals whether an account
exists: the page never calls the server until the form is submitted, and
the submit goes through Frappe's own /api/method/login, which keeps its
rate limiting and its deliberately vague failure message.
"""

import frappe

no_cache = 1


def _brand() -> dict:
    """Branding, from the property's own records where they exist."""
    out = {"title": "AlphaX POS", "subtitle": "", "logo": None}

    try:
        ws = frappe.get_cached_doc("Website Settings")
        out["logo"] = ws.get("app_logo") or ws.get("banner_image") or None
        out["title"] = ws.get("app_name") or out["title"]
    except Exception:
        pass

    try:
        outlet = frappe.db.get_value(
            "AlphaX POS Outlet", {}, ["name", "company"], as_dict=True, order_by="creation asc")
        if outlet:
            out["subtitle"] = outlet.get("company") or outlet.get("name") or ""
    except Exception:
        pass

    return out


def get_context(context):
    redirect = frappe.form_dict.get("redirect-to") or "/app/alphax-cashier"
    # Only same-site paths: an open redirect on a login page is a phishing
    # gift, and the next parameter is entirely attacker-controlled.
    if not redirect.startswith("/") or redirect.startswith("//"):
        redirect = "/app/alphax-cashier"

    context.no_cache = 1
    context.redirect_to = redirect
    context.already_signed_in = frappe.session.user != "Guest"
    context.current_user = frappe.session.user
    context.brand = _brand()
    return context
