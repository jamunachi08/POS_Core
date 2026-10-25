/* AlphaX KDS v2 — station-filtered kitchen display.
 *
 * v1 was a single flat ticket list. v2 is the display twin of KOT
 * routing (v15.8.0): each screen binds to ONE Print Station of type
 * "Kitchen Display" and shows only that station's lines, in three
 * lanes — New / Preparing / Ready — with tap-to-bump, realtime pushes
 * from the server fan-out, and elapsed-time urgency colors so the pass
 * can see at a glance what's aging. Runs full-screen on any tablet or
 * wall screen logged into the desk (read access to KDS Ticket).
 */

frappe.pages['alphax-kds'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Kitchen Display'),
        single_column: true,
    });
    new AlphaXKDS(page);
};

const KDS_API = 'alphax_pos_suite.alphax_pos_suite.pos.kot_api';
const AVAIL_API = 'alphax_pos_suite.alphax_pos_suite.pos.availability';
const LANES = [
    { status: 'New', label: __('New'), next: 'Preparing', bump: __('Start') },
    { status: 'Preparing', label: __('Preparing'), next: 'Ready', bump: __('Ready') },
    { status: 'Ready', label: __('Ready'), next: 'Served', bump: __('Serve') },
];
// Aging thresholds (minutes since ticket creation) → urgency class.
const WARN_MIN = 8, LATE_MIN = 15;

class AlphaXKDS {
    constructor(page) {
        this.page = page;
        this.tickets = [];
        this.station = frappe.urllib.get_arg('station')
            || localStorage.getItem('alphax_kds_station') || null;
        this.sound = localStorage.getItem('alphax_kds_sound') !== 'off';

        this._shell();
        this._86_button();
        this._realtime();
        this.station ? this._bind_station() : this._pick_station();
        // Re-render every 20s so elapsed-time colors keep moving even
        // with no new tickets.
        this._timer = setInterval(() => this._render(), 20000);
        $(window).one('hashchange', () => clearInterval(this._timer));
    }

    _shell() {
        $(this.page.main).addClass('alphax-kds2').html(`
            <div class="kds2-bar">
                <button class="btn btn-sm kds2-station-btn"></button>
                <div class="kds2-counts"></div>
                <div class="kds2-spacer"></div>
                <button class="btn btn-sm kds2-sound">🔔</button>
                <button class="btn btn-sm kds2-full">⛶</button>
            </div>
            <div class="kds2-lanes"></div>
            <style>
                .alphax-kds2 { --gap: 12px; }
                .kds2-bar { display:flex; align-items:center; gap:10px; padding:8px 4px; position:sticky; top:0; background:var(--bg-color); z-index:3; }
                .kds2-spacer { flex:1; }
                .kds2-counts { display:flex; gap:8px; font-size:12px; color:var(--text-muted); }
                .kds2-lanes { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--gap); align-items:start; }
                .kds2-lane-h { font-weight:700; font-size:13px; text-transform:uppercase; letter-spacing:.05em; padding:6px 2px; }
                .kds2-lane { display:flex; flex-direction:column; gap:var(--gap); }
                .kds2-t { border:1px solid var(--border-color); border-radius:10px; background:var(--card-bg); overflow:hidden; }
                .kds2-t-head { display:flex; justify-content:space-between; align-items:center; padding:8px 12px; font-weight:700; }
                .kds2-warn { margin:0 8px 6px; padding:6px 9px; border-radius:6px; font-size:12px;
                    font-weight:700; letter-spacing:.02em; background:#fee2e2; color:#991b1b;
                    border:1px solid #fca5a5; }
                .kds2-ft { font-size:9px; margin-inline-end:5px; vertical-align:2px; }
                .kds2-ft.veg { color:#16a34a; }
                .kds2-ft.non { color:#dc2626; }
                .kds2-ft.egg { color:#d97706; }
                .kds2-alg { display:inline-block; margin-inline-start:6px; padding:0 6px;
                    border-radius:4px; font-size:10px; font-weight:700; letter-spacing:.04em;
                    background:#fef3c7; color:#92400e; }
                .kds2-age { font-size:12px; font-weight:700; padding:2px 8px; border-radius:999px; background:var(--bg-light-gray); }
                .kds2-t.warn .kds2-age { background:#b98317; color:#fff; }
                .kds2-t.late .kds2-age { background:#b3403c; color:#fff; }
                .kds2-t.late { border-color:#b3403c; }
                .kds2-lines { padding:4px 12px 8px; }
                .kds2-line { display:flex; gap:10px; padding:5px 0; border-top:1px dashed var(--border-color); font-size:15px; }
                .kds2-line:first-child { border-top:none; }
                .kds2-qty { font-weight:800; min-width:28px; }
                .kds2-mods { font-size:12px; color:var(--text-muted); }
                .kds2-bump { width:100%; border:none; padding:12px; font-weight:800; font-size:14px; cursor:pointer; background:var(--control-bg); }
                .kds2-lane[data-status="New"] .kds2-bump { background:#2e7d4f; color:#fff; }
                .kds2-lane[data-status="Preparing"] .kds2-bump { background:#b98317; color:#fff; }
                .kds2-lane[data-status="Ready"] .kds2-bump { background:#31708f; color:#fff; }
                .kds2-empty { color:var(--text-muted); font-size:13px; padding:14px 4px; }
            </style>
        `);
        this.$lanes = this.page.main.find('.kds2-lanes');
        this.page.main.find('.kds2-station-btn').on('click', () => this._pick_station());
        this.page.main.find('.kds2-full').on('click', () => {
            const el = document.documentElement;
            document.fullscreenElement ? document.exitFullscreen() : el.requestFullscreen();
        });
        this.page.main.find('.kds2-sound').on('click', (e) => {
            this.sound = !this.sound;
            localStorage.setItem('alphax_kds_sound', this.sound ? 'on' : 'off');
            $(e.currentTarget).css('opacity', this.sound ? 1 : 0.4);
        });
    }

    _pick_station() {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'AlphaX POS Print Station',
                filters: { enabled: 1, station_type: 'Kitchen Display' },
                fields: ['name', 'station_name'],
            },
            callback: (r) => {
                const stations = r.message || [];
                if (!stations.length) {
                    frappe.msgprint(__('No Kitchen Display stations configured. Create an AlphaX POS Print Station with type "Kitchen Display".'));
                    return;
                }
                const d = new frappe.ui.Dialog({
                    title: __('Choose station'),
                    fields: [{
                        fieldname: 'station', fieldtype: 'Select', label: __('Station'),
                        options: stations.map(s => s.name).join('\n'), reqd: 1,
                        default: this.station || stations[0].name,
                    }],
                    primary_action_label: __('Bind this screen'),
                    primary_action: (v) => {
                        this.station = v.station;
                        localStorage.setItem('alphax_kds_station', v.station);
                        d.hide();
                        this._bind_station();
                    },
                });
                d.show();
            },
        });
    }

    _bind_station() {
        this.page.main.find('.kds2-station-btn').text(this.station);
        this._load();
    }

    _realtime() {
        frappe.realtime.on('alphax_kds_update', (data) => {
            if (!this.station || !data || data.station !== this.station) return;
            if (data.action === 'new' && this.sound) {
                try { new Audio('data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU'
                    + 'A' .repeat(80)).play().catch(() => {}); } catch (e) { /* silent */ }
            }
            this._load();
        });
    }

    _load() {
        if (!this.station) return;
        frappe.call({
            method: `${KDS_API}.kds_board`,
            args: { station: this.station },
            callback: (r) => { this.tickets = r.message || []; this._render(); },
        });
    }

    // The 86 list belongs on the pass, not in the back office. The person
    // who knows the salmon has run out is standing here, and the till must
    // find out in the same minute rather than at the next stock count.
    _86_button() {
        this.$btn86 = this.page.add_inner_button(__('86 List'), () => this._86_dialog());
        this._86_refresh();
    }

    _86_refresh() {
        frappe.call({
            method: `${AVAIL_API}.board`,
            args: { outlet: this.outlet || null },
            callback: (r) => {
                const b = r.message || {};
                this.board86 = b;
                if (this.$btn86) {
                    this.$btn86.text(b.count ? __('86 List ({0})', [b.count]) : __('86 List'));
                    this.$btn86.toggleClass('btn-danger', !!(b.off || []).length);
                }
            },
        });
    }

    _86_dialog() {
        const b = this.board86 || { off: [], low: [] };
        const esc = frappe.utils.escape_html;
        const d = new frappe.ui.Dialog({
            title: __('Off the menu'),
            size: 'large',
            fields: [{ fieldtype: 'HTML', fieldname: 'b' }],
            primary_action_label: __('Take an item off'),
            primary_action: () => { d.hide(); this._86_add(); },
        });
        const row = (x, status) => `
            <div class="kds86-row">
                <div>
                    <b>${esc(x.item_name || x.item)}</b>
                    <span class="kds86-${status}">${status === 'off' ? __('OFF') : __('LOW')}</span>
                    ${x.reason ? `<div class="kds86-why">${esc(x.reason)}</div>` : ''}
                </div>
                <button class="btn btn-xs" data-on="${esc(x.item)}">${__('Back on')}</button>
            </div>`;
        d.fields_dict.b.$wrapper.html(`
            <style>
                .kds86-row{display:flex;justify-content:space-between;align-items:center;gap:12px;
                    padding:8px 0;border-bottom:1px solid var(--border-color)}
                .kds86-off,.kds86-low{font-size:10px;font-weight:700;letter-spacing:.05em;
                    border-radius:4px;padding:1px 7px;margin-inline-start:7px}
                .kds86-off{background:#fee2e2;color:#991b1b}
                .kds86-low{background:#fef3c7;color:#92400e}
                .kds86-why{font-size:11.5px;color:var(--text-muted);margin-top:2px}
                .kds86-none{padding:14px 0;color:var(--text-muted)}
            </style>
            ${(b.off || []).map((x) => row(x, 'off')).join('')}
            ${(b.low || []).map((x) => row(x, 'low')).join('')}
            ${!(b.off || []).length && !(b.low || []).length
                ? `<div class="kds86-none">${__('Everything is on. Nothing has been taken off today.')}</div>` : ''}`);
        d.fields_dict.b.$wrapper.find('[data-on]').on('click', function () {
            const item = $(this).data('on');
            frappe.call({
                method: `${AVAIL_API}.set_availability`,
                args: { item, outlet: b.outlet, status: 'On' },
                callback: () => { d.hide(); frappe.show_alert({
                    message: __('{0} is back on', [item]), indicator: 'green' }, 5); },
            });
        });
        d.show();
    }

    _86_add() {
        const outlet = (this.board86 || {}).outlet;
        frappe.prompt([
            { fieldtype: 'Link', fieldname: 'item', label: __('Item'), options: 'Item', reqd: 1 },
            { fieldtype: 'Select', fieldname: 'status', label: __('State'), reqd: 1,
              options: 'Off\nLow', default: 'Off',
              description: __('Off hides it at the till. Low still sells but warns the cashier.') },
            { fieldtype: 'Data', fieldname: 'reason', label: __('Reason'),
              description: __('Shown to the cashier and on this board.') },
            { fieldtype: 'Datetime', fieldname: 'until', label: __('Back on at'),
              description: __('Leave blank to hold until someone puts it back.') },
        ], (v) => {
            frappe.call({
                method: `${AVAIL_API}.set_availability`,
                args: { item: v.item, outlet, status: v.status,
                        reason: v.reason || null, until: v.until || null },
                callback: () => {
                    frappe.show_alert({ indicator: 'orange',
                        message: __('{0} taken off at the till', [v.item]) }, 6);
                    this._86_refresh();
                },
            });
        }, __('Take an item off'), __('Confirm'));
    }

    _render() {
        if (!this.$lanes) return;
        const counts = {};
        const now = Date.now();
        this.$lanes.empty();
        for (const lane of LANES) {
            const $lane = $(`<div class="kds2-lane" data-status="${lane.status}">
                <div class="kds2-lane-h">${lane.label}</div></div>`);
            const mine = this.tickets.filter(t => t.status === lane.status);
            counts[lane.status] = mine.length;
            if (!mine.length) $lane.append(`<div class="kds2-empty">—</div>`);
            for (const t of mine) {
                const ageMin = Math.floor((now - new Date(t.creation).getTime()) / 60000);
                const cls = ageMin >= LATE_MIN ? 'late' : ageMin >= WARN_MIN ? 'warn' : '';
                const lines = (t.lines || []).map(l => {
                    // Food type is a dot, not a word: the pass reads a
                    // ticket at arm's length and in a hurry.
                    const ft = l.food_type === 'Veg' ? '<span class="kds2-ft veg" title="Veg">●</span>'
                        : l.food_type === 'Non-Veg' ? '<span class="kds2-ft non" title="Non-Veg">●</span>'
                        : l.food_type === 'Egg' ? '<span class="kds2-ft egg" title="Egg">●</span>' : '';
                    const alg = l.allergens
                        ? `<span class="kds2-alg" title="${frappe.utils.escape_html(l.allergens)}">${
                            frappe.utils.escape_html(l.allergens)}</span>` : '';
                    return `
                    <div class="kds2-line">
                        <span class="kds2-qty">${l.qty}×</span>
                        <span>${ft}${frappe.utils.escape_html(l.item_code)}${alg}
                            ${l.notes ? `<div class="kds2-mods">${frappe.utils.escape_html(l.notes)}</div>` : ''}
                        </span>
                    </div>`;
                }).join('');

                // The guest's own words sit above the lines, not beside
                // them. An allergy warning the pass can scroll past is a
                // warning that will eventually be missed.
                const warn = t.guest_allergy_note
                    ? `<div class="kds2-warn">⚠ ${__('ALLERGY')} — ${
                        frappe.utils.escape_html(t.guest_allergy_note)}</div>` : '';
                const $t = $(`
                    <div class="kds2-t ${cls}">
                        <div class="kds2-t-head">
                            <span>${frappe.utils.escape_html(t.token_no || t.sales_invoice || t.name)}</span>
                            <span class="kds2-age">${ageMin}m</span>
                        </div>
                        ${warn}
                        <div class="kds2-lines">${lines}</div>
                        <button class="kds2-bump">${lane.bump}</button>
                    </div>`);
                $t.find('.kds2-bump').on('click', () => {
                    frappe.call({
                        method: `${KDS_API}.bump_ticket`,
                        args: { ticket: t.name, status: lane.next },
                        callback: () => this._load(),
                    });
                });
                $lane.append($t);
            }
            this.$lanes.append($lane);
        }
        this.page.main.find('.kds2-counts').html(
            LANES.map(l => `<span>${l.label}: <b>${counts[l.status] || 0}</b></span>`).join(''));
    }
}
