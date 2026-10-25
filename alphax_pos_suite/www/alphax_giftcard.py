no_cache = 1


def get_context(context):
	"""Public gift card balance check: /giftcard."""
	context.no_cache = 1
	context.show_sidebar = False
	return context
