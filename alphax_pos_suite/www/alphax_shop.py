import frappe

no_cache = 1


def get_context(context):
	"""Online pickup store for one outlet: /shop/<slug>. Guest page; data via ordering.public."""
	context.slug = (frappe.form_dict.get("slug") or "").strip()
	context.no_cache = 1
	context.show_sidebar = False
	return context
