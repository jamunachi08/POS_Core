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
                const lines = (t.lines || []).map(l => `
                    <div class="kds2-line">
                        <span class="kds2-qty">${l.qty}×</span>
                        <span>${frappe.utils.escape_html(l.item_code)}
                            ${l.notes ? `<div class="kds2-mods">${frappe.utils.escape_html(l.notes)}</div>` : ''}
                        </span>
                    </div>`).join('');
                const $t = $(`
                    <div class="kds2-t ${cls}">
                        <div class="kds2-t-head">
                            <span>${frappe.utils.escape_html(t.token_no || t.sales_invoice || t.name)}</span>
                            <span class="kds2-age">${ageMin}m</span>
                        </div>
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
