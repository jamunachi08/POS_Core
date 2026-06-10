app_name = "alphax_pos_suite"
app_title = "AlphaX Bonanza POS Pack"
app_publisher = "AlphaX"
app_description = "Bonanza POS Pack (XPOS + αPOS): unified Restaurant/Cafe/Retail POS extensions for ERPNext"
app_email = "support@alphax.local"
app_license = "MIT"

# NOTE:
# We intentionally do NOT ship Role / Custom Field as fixtures because the
# standard fixture importer expects full exported docs including a `name`.
# Instead, we create required Roles & Custom Fields during app installation.
fixtures = [
    "Print Format",
    {
        "doctype": "Workspace",
        "filters": {"name": ["in", ["AlphaX POS Hub"]]}
    },
]

# Create required roles / custom fields programmatically
after_install = "alphax_pos_suite.alphax_pos_suite.install.after_install"

# Re-fetch vendor bundles AND rebuild asset symlinks on every bench migrate
# so upgrades stay current. The rebuild is the critical one — without it,
# Frappe Cloud sometimes serves /assets/<app>/... as the desk HTML and
# the cashier page can't load anything.
after_migrate = [
    "alphax_pos_suite.alphax_pos_suite.install.force_rebuild_assets",
    "alphax_pos_suite.alphax_pos_suite.install.fetch_vendor_bundles_silently",
    "alphax_pos_suite.alphax_pos_suite.install.ensure_workspace_visible",
    "alphax_pos_suite.alphax_pos_suite.install.repair_orphaned_modules_silently",
]

doc_events = {
    "Sales Invoice": {
        "before_insert": "alphax_pos_suite.alphax_pos_suite.pos.dedupe.sales_invoice_before_insert",
        "validate": "alphax_pos_suite.alphax_pos_suite.integrations.card_capture.sales_invoice_validate",
        "before_submit": "alphax_pos_suite.alphax_pos_suite.integrations.card_capture.sales_invoice_before_submit",
        "on_submit": [
            "alphax_pos_suite.alphax_pos_suite.integrations.card_capture.sales_invoice_on_submit",
            "alphax_pos_suite.alphax_pos_suite.pos.processing.on_sales_invoice_submit",
            "alphax_pos_suite.alphax_pos_suite.loyalty.hooks.on_sales_invoice_submit",
            "alphax_pos_suite.alphax_pos_suite.integrations.zatca_adapter.on_pos_invoice_submit",
        ],
        "on_cancel": [
            "alphax_pos_suite.alphax_pos_suite.loyalty.hooks.on_sales_invoice_cancel",
        ],
    },
    "AlphaX POS Order": {
        "on_submit": "alphax_pos_suite.alphax_pos_suite.pos.posting.on_order_submit",
        "on_cancel": "alphax_pos_suite.alphax_pos_suite.pos.posting.on_order_cancel",
    },
}

scheduler_events = {
    "daily": [
        "alphax_pos_suite.alphax_pos_suite.pos.maintenance.daily_cleanup",
        "alphax_pos_suite.alphax_pos_suite.loyalty.hooks.expire_points",
        "alphax_pos_suite.alphax_pos_suite.security.manager_pin.reset_daily_counters",
    ],
}

app_include_js = [
    "/assets/alphax_pos_suite/dist/vendor/_js/sales_invoice_terminal_capture.js",
    "/assets/alphax_pos_suite/dist/vendor/_js/bonanza_pos_warnings.js",
    "/assets/alphax_pos_suite/dist/vendor/_js/alphax_workspace_theme_apply.js",
    # v15.5.16 — qz-tray client wrapper (window.AlphaXPrint global).
    # Loads qz.js from CDN lazily; falls back to browser print dialog
    # when the local qz-tray daemon isn't installed. Safe to ship to
    # all pages — the actual qz.js fetch only happens on first print.
    "/assets/alphax_pos_suite/dist/vendor/_js/alphax_qz_print.js",
]

# Workspace theme CSS — always shipped to the browser, but every selector
# inside is scoped to body[data-page-route^="Workspaces/AlphaX POS Hub"]
# AND requires the body class .alphax-pos-themed to take effect. The class
# is added by boot_session below only when the AlphaX POS Settings toggle
# is on. So:
#   - Toggle ON  -> body class set -> CSS applies -> mauve theme visible.
#   - Toggle OFF -> body class absent -> CSS is dead weight, stock styling.
# We accept the small bandwidth cost (~3KB) in exchange for not needing
# Frappe to support callable hook values.
app_include_css = [
    "/assets/alphax_pos_suite/dist/vendor/_css/alphax_pos_hub.css",
    "/assets/alphax_pos_suite/dist/vendor/_css/alphax_pos_classic.css",
    "/assets/alphax_pos_suite/dist/vendor/_css/alphax_pos_setup_wizard.css",
]

# Inject the .alphax-pos-themed body class into the desk boot payload
# when the toggle is on. The desk's bootinfo handler reads the returned
# dict, and we use a small JS in app_include_js to apply the class on
# document ready.
boot_session = "alphax_pos_suite.alphax_pos_suite.appearance.workspace_theme_css.boot_workspace_theme"


website_route_rules = [
    {"from_route": "/bonanza/order/<token>", "to_route": "bonanza_order"},
]
