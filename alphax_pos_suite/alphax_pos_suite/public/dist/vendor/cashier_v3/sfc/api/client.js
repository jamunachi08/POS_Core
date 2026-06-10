/*
 * AlphaX POS v3 — API client.
 *
 * Thin wrapper around `frappe.call`. Each method maps to one whitelisted
 * backend endpoint. The client falls back to mock data when:
 *   1. `?mock=1` is in the URL (developer override)
 *   2. `frappe.call` is undefined (running outside Frappe Desk, e.g.
 *      from the static mockup or a unit test)
 *
 * Phase 2: skeleton + mock fallbacks. Phase 3+ adds real calls.
 */

import * as mock from './mock.js';

function useMock() {
    try {
        if (new URL(location.href).searchParams.get('mock') === '1') return true;
    } catch (e) {}
    return typeof frappe === 'undefined' || !frappe.call;
}

async function call(method, args = {}, type = 'POST') {
    if (useMock()) {
        const fn = mock[_mockKey(method)];
        if (fn) return fn(args);
        throw new Error(`Mock not implemented for ${method}`);
    }
    return new Promise((resolve, reject) => {
        frappe.call({
            method,
            args,
            type,
            callback: (r) => resolve(r.message),
            error: (err) => reject(err),
        });
    });
}

function _mockKey(method) {
    // alphax_pos_suite.alphax_pos_suite.boot.api.pos_boot → posBoot
    const last = method.split('.').pop();
    return last.replace(/_(.)/g, (_, c) => c.toUpperCase());
}

export const api = {
    posBoot(terminal) {
        return call('alphax_pos_suite.alphax_pos_suite.boot.api.pos_boot', { terminal });
    },

    resolveProfile(terminal) {
        return call(
            'alphax_pos_suite.alphax_pos_suite.boot.api.resolve_session_pos_profile',
            { terminal }
        );
    },

    listTerminalsForPicker() {
        return call('alphax_pos_suite.alphax_pos_suite.boot.api.list_terminals_for_picker');
    },

    listItems({ item_groups = null, limit = 200 } = {}) {
        // Phase 4 will implement; backend endpoint may need to be added
        return call('frappe.client.get_list', {
            doctype: 'Item',
            filters: { disabled: 0, is_sales_item: 1 },
            fields: ['item_code', 'item_name', 'item_group', 'standard_rate', 'image'],
            limit_page_length: limit,
        });
    },

    listItemGroups() {
        return call('frappe.client.get_list', {
            doctype: 'Item Group',
            filters: { is_group: 0 },
            fields: ['name'],
            limit_page_length: 50,
        });
    },

    // Card payment endpoints (already shipped in v15.5.16)
    requestCardPayment(args) {
        return call(
            'alphax_pos_suite.alphax_pos_suite.integrations.card_reader.api.request_card_payment',
            args
        );
    },

    getCardPaymentStatus(transaction_uuid) {
        return call(
            'alphax_pos_suite.alphax_pos_suite.integrations.card_reader.api.get_card_payment_status',
            { transaction_uuid }
        );
    },
};
