import frappe

no_cache = 1


def get_context(context):
	"""Guest order tracking: /track/<ref>. Shows status only; the reference is the secret."""
	context.ref = (frappe.form_dict.get("ref") or "").strip()
	context.no_cache = 1
	context.show_sidebar = False
	return context
