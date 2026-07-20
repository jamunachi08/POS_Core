/*
 * Apply the AlphaX POS workspace theme body class.
 *
 * Reads `frappe.boot.alphax_workspace_theme_enabled` (set by our
 * boot_session hook in workspace_theme_css.py) and adds the body class
 * `alphax-pos-themed` when on.
 *
 * The CSS in alphax_pos_hub.css scopes every selector under that class
 * AND under [data-page-route^="Workspaces/AlphaX POS Hub"], so the
 * mauve theme only appears on our workspace and only when the toggle
 * is on.
 *
 * Toggling the setting takes effect after a page reload (the boot
 * payload is generated once per session). That's a fine UX trade-off
 * for an admin setting that's flipped maybe once per install.
 */
(function () {
    "use strict";

    function applyTheme() {
        try {
            var enabled = !!(window.frappe
                && window.frappe.boot
                && window.frappe.boot.alphax_workspace_theme_enabled);
            if (enabled) {
                document.body.classList.add("alphax-pos-themed");
            } else {
                document.body.classList.remove("alphax-pos-themed");
            }
        } catch (e) {
            // Never break the desk over a styling toggle.
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", applyTheme);
    } else {
        applyTheme();
    }
})();
