frappe.pages['alphax-kds'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Kitchen Display'),
        single_column: true
    });
    new AlphaXKDS(page);
};

class AlphaXKDS {
    constructor(page) {
        this.page = page;
        this.tickets = [];
        this.station = frappe.urllib.get_arg('station') || localStorage.getItem('alphax_kds_station') || null;
        this.sound_enabled = localStorage.getItem('alphax_kds_sound') !== 'off';

        this._render_shell();
        this._bind_realtime();
        if (!this.station) this._prompt_station();
        else this._load_tickets();
        this._tick_timer();
    }

    _render_shell() {
        $(this.page.main).addClass('alphax-kds-page').html(`
            <div class="kds-root">
                <div class="kds-toolbar">
                    <div class="kds-station-name"></div>
                    <div class="kds-stats">
                        <span class="kds-stat-pill kds-stat-active">0 active</span>
                        <span class="kds-stat-pill kds-stat-overdue">0 overdue</span>
                    </div>
                    <div class="kds-toolbar-spacer"></div>
                    <button class="kds-btn kds-btn-sound">${this.sound_enabled ? '🔔' : '🔕'}</button>
                    <button class="kds-btn kds-btn-station">Station</button>
                </div>
                <div class="kds-grid"></div>
            </div>
            <style>
                .alphax-kds-page { background:#0e1217; }
                .alphax-kds-page .layout-main-section { padding:0; }
                .kds-root { color:#e5e7eb; min-height:calc(100vh - 80px); }
                .kds-toolbar { display:flex; align-items:center; padding:14px 18px; background:#1a1f29; border-bottom:1px solid #232936; gap:14px; }
                .kds-station-name { font-size:18px; font-weight:600; color:#fff; }
                .kds-stats { display:flex; gap:8px; }
                .kds-stat-pill { padding:5px 12px; border-radius:14px; font-size:12px; background:#232936; color:#cbd5e1; }
                .kds-stat-pill.kds-stat-overdue { background:#7f1d1d; color:#fecaca; }
                .kds-toolbar-spacer { flex:1; }
                .kds-btn { padding:8px 14px; background:#232936; color:#e5e7eb; border:1px solid #2d3441; border-radius:6px; cursor:pointer; font-size:13px; }
                .kds-btn:hover { background:#2d3441; }
                .kds-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px; padding:14px; }
                .kds-empty { padding:60px; text-align:center; color:#6b7280; grid-column:1/-1; font-size:14px; }
                .kds-ticket { background:#1a1f29; border:2px solid #2d3441; border-radius:8px; overflow:hidden; display:flex; flex-direction:column; min-height:180px; transition:border-color 0.2s; }
                .kds-ticket.s-Sent { border-color:#2d3441; }
                .kds-ticket.s-In-Progress { border-color:#185fa5; }
                .kds-ticket.s-Ready { border-color:#3b6d11; }
                .kds-ticket.overdue { border-color:#a32d2d; animation:kds-pulse 1.5s ease-in-out infinite; }
                @keyframes kds-pulse { 50% { background:#2a1414; } }
                .kds-ticket .head { padding:10px 14px; background:#232936; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #2d3441; }
                .kds-ticket .head .ord { font-weight:600; font-size:14px; }
                .kds-ticket .head .timer { font-size:13px; font-variant-numeric:tabular-nums; padding:2px 8px; border-radius:10px; background:#0e1217; }
                .kds-ticket.overdue .timer { background:#7f1d1d; color:#fee; font-weight:600; }
                .kds-ticket .meta { padding:6px 14px; font-size:11px; color:#9ca3af; border-bottom:1px solid #2d3441; }
                .kds-ticket .body { flex:1; padding:8px 14px; }
                .kds-ticket .item { padding:4px 0; font-size:14px; }
                .kds-ticket .item .qty { color:#fbbf24; margin-right:8px; font-weight:500; }
                .kds-ticket .item .modifiers { display:block; padding-left:18px; color:#9ca3af; font-size:12px; }
                .kds-ticket .actions { display:flex; gap:1px; background:#0e1217; }
                .kds-ticket .actions button { flex:1; padding:12px; background:#232936; color:#e5e7eb; border:none; cursor:pointer; font-size:13px; font-weight:500; }
                .kds-ticket .actions button:hover { background:#2d3441; }
                .kds-ticket .actions button.bump { background:#0F6E56; color:#fff; }
                .kds-ticket .actions button.bump:hover { background:#0a5a47; }
                .kds-ticket .actions button.recall { background:transparent; color:#9ca3af; }
            </style>
        `);

        this.$grid = this.page.main.find('.kds-grid');
        this.$stationName = this.page.main.find('.kds-station-name');
        this.$active = this.page.main.find('.kds-stat-active');
        this.$overdue = this.page.main.find('.kds-stat-overdue');

        this.page.main.find('.kds-btn-station').on('click', () => this._prompt_station());
        this.page.main.find('.kds-btn-sound').on('click', () => this._toggle_sound());
    }

    _prompt_station() {
        frappe.prompt([
            { fieldname: 'station', label: 'Pick a kitchen station', fieldtype: 'Link', options: 'AlphaX POS Kitchen Station' }
        ], (vals) => {
            this.station = vals.station || null;
            if (this.station) localStorage.setItem('alphax_kds_station', this.station);
            else localStorage.removeItem('alphax_kds_station');
            this._load_tickets();
        }, 'Kitchen station', 'Continue');
    }

    _toggle_sound() {
        this.sound_enabled = !this.sound_enabled;
        localStorage.setItem('alphax_kds_sound', this.sound_enabled ? 'on' : 'off');
        this.page.main.find('.kds-btn-sound').text(this.sound_enabled ? '🔔' : '🔕');
    }

    _bind_realtime() {
        frappe.realtime.on('alphax_pos_kds_new_ticket', (data) => {
            this._load_tickets();
            this._beep();
        });
        frappe.realtime.on('alphax_pos_kds_ticket_updated', () => this._load_tickets());
    }

    _load_tickets() {
        this.$stationName.text(this.station || 'All stations');
        const filters = { status: ['in', ['Sent', 'In Progress', 'Ready']] };
        frappe.db.get_list('AlphaX POS KDS Ticket', {
            filters,
            fields: ['name', 'pos_order', 'outlet', 'table', 'customer', 'status', 'sla_minutes', 'started_on', 'creation'],
            limit: 80,
            order_by: 'creation asc'
        }).then(async (tickets) => {
            this.tickets = [];
            for (const t of tickets) {
                const items = await frappe.db.get_list('AlphaX POS KDS Ticket Item', {
                    filters: { parent: t.name },
                    fields: ['item_code', 'qty', 'modifiers', 'station'],
                    limit: 30,
                    order_by: 'idx asc'
                });
                if (this.station) {
                    const matchItems = items.filter(i => !i.station || i.station === this.station);
                    if (matchItems.length === 0) continue;
                    t._items = matchItems;
                } else {
                    t._items = items;
                }
                this.tickets.push(t);
            }
            this._render();
        });
    }

    _render() {
        this.$grid.empty();
        if (this.tickets.length === 0) {
            this.$grid.html('<div class="kds-empty">No active tickets</div>');
            this.$active.text('0 active');
            this.$overdue.text('0 overdue');
            return;
        }
        let overdue = 0;
        const now = new Date();
        this.tickets.forEach(t => {
            const created = new Date(t.creation);
            const sla = t.sla_minutes || 15;
            const ageMin = (now - created) / 60000;
            const isOverdue = ageMin > sla;
            if (isOverdue) overdue++;
            const $card = $(`
                <div class="kds-ticket s-${t.status.replace(' ', '-')} ${isOverdue ? 'overdue' : ''}" data-id="${t.name}">
                    <div class="head">
                        <div class="ord">${frappe.utils.escape_html(t.table || t.pos_order || 'order')}</div>
                        <div class="timer" data-created="${t.creation}">${this._fmt_age(ageMin)}</div>
                    </div>
                    <div class="meta">${t.customer ? frappe.utils.escape_html(t.customer) + ' · ' : ''}SLA ${sla}m</div>
                    <div class="body">
                        ${t._items.map(i => `
                            <div class="item">
                                <span class="qty">${i.qty}×</span>${frappe.utils.escape_html(i.item_code)}
                                ${i.modifiers ? `<span class="modifiers">${frappe.utils.escape_html(i.modifiers)}</span>` : ''}
                            </div>
                        `).join('')}
                    </div>
                    <div class="actions">
                        ${t.status === 'Sent' ? `<button class="start">Start</button>` : ''}
                        ${t.status === 'In Progress' ? `<button class="bump">Ready</button>` : ''}
                        ${t.status === 'Ready' ? `<button class="bump">Served</button>` : ''}
                        <button class="recall">Recall</button>
                    </div>
                </div>
            `);
            $card.find('.start').on('click', () => this._update(t.name, 'In Progress'));
            $card.find('.bump').on('click', () => {
                const next = t.status === 'In Progress' ? 'Ready' : 'Served';
                this._update(t.name, next);
            });
            $card.find('.recall').on('click', () => this._update(t.name, 'Sent'));
            this.$grid.append($card);
        });
        this.$active.text(`${this.tickets.length} active`);
        this.$overdue.text(`${overdue} overdue`);
    }

    _fmt_age(min) {
        if (min < 1) return 'just now';
        if (min < 60) return `${Math.floor(min)}m`;
        return `${Math.floor(min/60)}h ${Math.floor(min%60)}m`;
    }

    _tick_timer() {
        setInterval(() => {
            const now = new Date();
            let overdue = 0;
            this.page.main.find('.kds-ticket').each((_, el) => {
                const $el = $(el);
                const $timer = $el.find('.timer');
                const created = new Date($timer.data('created'));
                const ageMin = (now - created) / 60000;
                const ticketName = $el.data('id');
                const t = this.tickets.find(x => x.name === ticketName);
                const sla = t?.sla_minutes || 15;
                const isOverdue = ageMin > sla;
                $timer.text(this._fmt_age(ageMin));
                $el.toggleClass('overdue', isOverdue);
                if (isOverdue) overdue++;
            });
            this.$overdue.text(`${overdue} overdue`);
        }, 5000);
    }

    _update(ticket, status) {
        frappe.call({
            method: 'frappe.client.set_value',
            args: { doctype: 'AlphaX POS KDS Ticket', name: ticket, fieldname: 'status', value: status },
            callback: () => {
                if (status === 'Served') {
                    this.tickets = this.tickets.filter(t => t.name !== ticket);
                    this._render();
                } else {
                    this._load_tickets();
                }
            }
        });
    }

    _beep() {
        if (!this.sound_enabled) return;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain).connect(ctx.destination);
            osc.frequency.value = 880;
            gain.gain.setValueAtTime(0.001, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
            osc.start();
            osc.stop(ctx.currentTime + 0.3);
        } catch (e) {}
    }
}
