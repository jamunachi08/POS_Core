from frappe import _

def get_data():
    return [
        {
            "module_name": "AlphaX POS Suite",
            "category": "Modules",
            "label": _("AlphaX POS Suite"),
            "icon": "octicon octicon-device-mobile",
            "type": "module",
            "description": _("Unified POS Suite for ERPNext"),
        }
    ]
