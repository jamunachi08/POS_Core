"""Route controller for /pos_lock — the till's lock screen.

Guest-accessible, because the point is that nobody is signed in. It shows
a keypad and nothing else: no staff list, no names, no PIN hints. Whether
the keypad does anything at all is decided by the server, so a site that
has not enabled PIN sign-in gets the password form instead of a keypad
that silently rejects everything.
"""

import frappe

no_cache = 1


def get_context(context):
    terminal = (frappe.form_dict.get("terminal") or "").strip()

    ctx = {"enabled": False, "terminal": None, "outlet": None, "locked_for": 0}
    try:
        from alphax_pos_suite.alphax_pos_suite.security.staff_pin import signin_context
        ctx = signin_context(terminal) or ctx
    except Exception:
        frappe.log_error(title="AlphaX POS: lock screen context failed",
                         message=frappe.get_traceback())

    brand = {"title": "AlphaX POS", "subtitle": "", "logo": None, "image": None}
    try:
        ws = frappe.get_cached_doc("Website Settings")
        brand["logo"] = ws.get("app_logo") or None
        brand["title"] = ws.get("app_name") or brand["title"]
        # The hero image is whatever the property already set as its
        # website banner. One upload, two places, nothing new to manage.
        brand["image"] = ws.get("banner_image") or None
    except Exception:
        pass

    if ctx.get("outlet"):
        brand["subtitle"] = ctx["outlet"]

    context.no_cache = 1
    context.pin_enabled = bool(ctx.get("enabled"))
    context.terminal = ctx.get("terminal") or terminal
    context.locked_for = int(ctx.get("locked_for") or 0)
    context.brand = brand
    context.already_signed_in = frappe.session.user != "Guest"
    context.current_user = frappe.session.user
    return context
