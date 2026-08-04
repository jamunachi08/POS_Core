import frappe

no_cache = 1


def get_context(context):
    """Guest-facing table ordering page.

    Two things must reach the template: the table token (from the query
    string, or from a /bonanza/order/<token> style path) and a CSRF token.
    Frappe rejects unsafe methods once the session carries a CSRF token,
    and a guest session does carry one — without this the page's POSTs
    come back 400 and the guest sees a dead menu.
    """
    path = getattr(frappe.request, "path", "") if getattr(frappe, "request", None) else ""
    token = (frappe.form_dict.get("token") if hasattr(frappe, "form_dict") else None) or ""

    if not token and path:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[-2] == "order":
            token = parts[-1]

    csrf = ""
    try:
        csrf = frappe.sessions.get_csrf_token()
    except Exception:
        # Older/leaner session backends: no token means no CSRF check either.
        csrf = ""

    context.token = token
    context.csrf_token = csrf
    context.no_cache = 1
    context.show_sidebar = False
    return context
