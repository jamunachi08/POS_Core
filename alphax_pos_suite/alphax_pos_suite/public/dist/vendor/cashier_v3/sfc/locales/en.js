/*
 * English locale strings for AlphaX POS v3.
 *
 * Organized by feature area. Add new strings here, then mirror in ar.js.
 * Each phase adds the keys it needs; this is the Phase 2 baseline.
 */

export default {
    app: {
        title: 'AlphaX POS Cashier',
        loading: 'Loading...',
        ready: 'Ready',
        error_generic: "Something didn't work as expected.",
        retry: 'Try again',
        cancel: 'Cancel',
        ok: 'OK',
        save: 'Save',
        close: 'Close',
        phase2_placeholder_title: 'AlphaX POS v3 — Foundation Ready',
        phase2_placeholder_body: 'The Vue runtime is loaded and the SPA is mounted. The cashier UI is being built next.',
    },

    boot: {
        warming_up: 'Starting AlphaX POS Cashier...',
        loading_terminal: 'Loading terminal configuration...',
        loading_catalog: 'Loading catalog...',
        loading_done: 'Almost ready...',
    },

    station: {
        not_configured: 'Station Not Configured',
        not_configured_body: "This PC hasn't been bound to a POS terminal yet.",
        ask_manager: 'A manager must complete a one-time setup before this station can take orders.',
    },

    nav: {
        sale: 'Sale',
        return_mode: 'Return',
        holds: 'Holds',
        shift: 'Shift',
        today: 'Today',
        settings: 'Settings',
    },

    cart: {
        title: 'Current Sale',
        empty: 'No items yet',
        empty_hint: 'Scan a barcode or pick from the menu',
        add_customer: 'Add Customer',
        subtotal: 'Subtotal',
        tax: 'Tax',
        total: 'TOTAL',
        hold: 'Hold',
        pay_card: 'Pay by Card',
        pay_submit: 'Pay & Submit',
    },

    return_mode: {
        banner: 'Return mode',
        original_label: 'Original',
        exit: 'Exit return mode',
    },

    catalog: {
        search_placeholder: 'Search items or scan barcode...',
        all_items: 'All Items',
        ready_to_scan: 'Ready to scan',
        no_results: 'No items match',
        loading: 'Loading catalog...',
    },

    shortcuts: {
        scan: 'Scan',
        customer: 'Customer',
        hold: 'Hold',
        pay: 'Pay',
        return_action: 'Return',
        cancel: 'Cancel',
    },
};
