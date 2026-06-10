/*
 * AlphaX POS v3 — Mock API.
 *
 * Returns fixture data for any endpoint when:
 *   - URL contains ?mock=1
 *   - frappe.call is unavailable (running standalone)
 *
 * Each function name matches the camelCase form of the backend method's
 * last path segment (api.client.js does the conversion).
 */

const DELAY = 200; // simulated network delay (ms)

function delay(value) {
    return new Promise(resolve => setTimeout(() => resolve(value), DELAY));
}

export function posBoot(args) {
    return delay({
        terminal: { name: args.terminal || 'A07', pos_outlet: 'Coffee Shop' },
        outlet: {
            name: 'Coffee Shop',
            branch: 'Riyadh Mall',
            primary_domain: 'Cafe',
        },
        profile: { name: 'Coffee Shop Profile', currency: 'SAR' },
        domain_pack: { domain_code: 'Cafe', uses_modifiers: 1 },
        payment_methods: [
            { name: 'Cash', type: 'cash' },
            { name: 'Card', type: 'card' },
            { name: 'Mada', type: 'card' },
        ],
        _phase2_mock: true,
    });
}

export function resolveSessionPosProfile() {
    return delay({
        profile: 'Coffee Shop Profile',
        candidates: ['Coffee Shop Profile'],
        needs_picker: false,
    });
}

export function listTerminalsForPicker() {
    return delay([
        { name: 'A07', breadcrumb: 'Riyadh Mall > Coffee Shop > A07' },
        { name: 'A08', breadcrumb: 'Riyadh Mall > Coffee Shop > A08' },
    ]);
}

export function listItems() {
    return delay([
        { item_code: 'COF-LAT-001', item_name: 'Latte',          item_group: 'Hot Drinks', standard_rate: 12.00 },
        { item_code: 'COF-MOC-002', item_name: 'Mocha',          item_group: 'Hot Drinks', standard_rate: 14.00 },
        { item_code: 'COF-CAP-003', item_name: 'Cappuccino',     item_group: 'Hot Drinks', standard_rate: 11.00 },
        { item_code: 'COF-ESP-004', item_name: 'Espresso',       item_group: 'Hot Drinks', standard_rate: 8.00 },
        { item_code: 'COF-AME-005', item_name: 'Americano',      item_group: 'Hot Drinks', standard_rate: 9.00 },
        { item_code: 'COF-CHO-006', item_name: 'Hot Chocolate',  item_group: 'Hot Drinks', standard_rate: 13.00 },
        { item_code: 'TEA-EAR-001', item_name: 'Earl Grey Tea',  item_group: 'Hot Drinks', standard_rate: 7.00 },
        { item_code: 'TEA-GRN-002', item_name: 'Green Tea',      item_group: 'Hot Drinks', standard_rate: 7.00 },
        { item_code: 'COF-ICL-007', item_name: 'Iced Latte',     item_group: 'Cold Drinks', standard_rate: 13.00 },
        { item_code: 'PST-CRO-001', item_name: 'Croissant',      item_group: 'Pastry', standard_rate: 10.00 },
        { item_code: 'PST-CRA-002', item_name: 'Almond Croissant', item_group: 'Pastry', standard_rate: 14.00 },
        { item_code: 'PST-MUF-001', item_name: 'Chocolate Muffin', item_group: 'Pastry', standard_rate: 9.00 },
    ]);
}

export function listItemGroups() {
    return delay([
        { name: 'Hot Drinks' },
        { name: 'Cold Drinks' },
        { name: 'Pastry' },
        { name: 'Sandwiches' },
        { name: 'Desserts' },
    ]);
}

export function requestCardPayment(args) {
    return delay({
        ok: true,
        transaction_uuid: args.transaction_uuid,
        transaction: 'ACT-2026-MOCK-001',
        status: 'Pending',
        card_reader: 'Mock Reader',
        vendor: 'Mock',
    });
}

export function getCardPaymentStatus(args) {
    return delay({
        transaction_uuid: args.transaction_uuid,
        status: 'Approved',
        auth_code: '123456',
        rrn: 'RRN001',
        card_brand: 'Visa',
        masked_pan: '**** **** **** 4242',
    });
}
