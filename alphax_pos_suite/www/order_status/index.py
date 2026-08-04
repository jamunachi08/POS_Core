import frappe

no_cache = 1


def get_context(context):
    """Lobby order-status screen.

    Guest page by design — it runs on a TV stick that nobody logs into.
    Authorisation is the outlet's display key, checked on every data call;
    this page only carries the parameters through to the browser.
    """
    context.outlet = frappe.form_dict.get("outlet") or ""
    context.display_key = frappe.form_dict.get("key") or ""
    context.lang_mode = frappe.form_dict.get("lang") or "both"   # both | en | ar
    context.no_cache = 1
    context.show_sidebar = False
    return context
