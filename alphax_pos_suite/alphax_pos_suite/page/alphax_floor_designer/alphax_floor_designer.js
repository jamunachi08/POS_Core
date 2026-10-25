frappe.pages['alphax-floor-designer'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Floor Designer'),
        single_column: true
    });

    new AlphaXFloorDesigner(page);
};

class AlphaXFloorDesigner {
    constructor(page) {
        this.page = page;
        this.mode = 'live';
        this.current_floor = null;
        this.tables = [];
        this.floor_meta = null;
        this.selected = null;
        this.drag = null;
        this.dirty = false;

        this._build_layout();
        this._bind_realtime();
        this._load_floor_list();
    }

    _build_layout() {
        const $w = $(this.page.main).addClass('apos-floor-designer').html(`
            <div class="apos-fd-toolbar">
                <div class="form-group">
                    <select class="form-control floor-sel"></select>
                </div>
                <div class="btn-group" role="group">
                    <button class="btn btn-default mode-live active">Live</button>
                    <button class="btn btn-default mode-design">Design</button>
                </div>
                <div class="apos-fd-design-tools" style="display:none">
                    <button class="btn btn-default add-rect">+ Rect</button>
                    <button class="btn btn-default add-circle">+ Circle</button>
                    <button class="btn btn-default delete-sel">Delete</button>
                    <button class="btn btn-primary save-layout">Save</button>
                </div>
                <div class="apos-fd-stats text-muted ml-auto"></div>
            </div>
            <div class="apos-fd-canvas-wrap">
                <div class="apos-fd-canvas"></div>
            </div>
            <div class="apos-fd-detail"></div>
            <style>
              .apos-floor-designer .apos-fd-toolbar { display:flex; gap:10px; align-items:center; padding:10px; background:var(--bg-color); border-bottom:1px solid var(--border-color); flex-wrap:wrap; }
              .apos-floor-designer .apos-fd-toolbar .ml-auto { margin-left:auto; }
              .apos-floor-designer .floor-sel { min-width:220px; }
              .apos-floor-designer .apos-fd-canvas-wrap { padding:14px; }
              .apos-floor-designer .apos-fd-canvas { position:relative; width:100%; height:520px; background:#f4f5f6; border:1px solid var(--border-color); border-radius:6px; overflow:hidden; }
              .apos-floor-designer .apos-fd-canvas.designing { background-image:radial-gradient(circle, #d0d3d8 1px, transparent 1px); background-size:20px 20px; cursor:crosshair; }
              .apos-floor-designer .fd-table { position:absolute; display:flex; flex-direction:column; align-items:center; justify-content:center; border:2px solid; border-radius:6px; font-size:12px; font-weight:500; cursor:pointer; user-select:none; transition:transform .12s; }
              .apos-floor-designer .fd-table.round { border-radius:50%; }
              .apos-floor-designer .fd-table.selected { box-shadow:0 0 0 3px #4a90e2; }
              .apos-floor-designer .fd-table.s-Free { background:#e9f5d9; border-color:#639922; color:#27500a; }
              .apos-floor-designer .fd-table.s-Occupied { background:#faeed9; border-color:#ba7517; color:#633806; }
              .apos-floor-designer .fd-table.s-Reserved { background:#e6f1fb; border-color:#185fa5; color:#0c447c; }
              .apos-floor-designer .fd-table.s-Dirty { background:#f1efe8; border-color:#5f5e5a; color:#444441; }
              .apos-floor-designer .fd-table.s-Disabled { background:#fcebeb; border-color:#a32d2d; color:#791f1f; opacity:0.6; }
              .apos-floor-designer .fd-table .num { font-size:13px; }
              .apos-floor-designer .fd-table .seats { font-size:10px; opacity:0.7; }
              .apos-floor-designer .apos-fd-detail { padding:14px; min-height:80px; border-top:1px solid var(--border-color); }
              .apos-floor-designer .apos-fd-detail .row-line { display:flex; justify-content:space-between; padding:3px 0; font-size:13px; }
              .apos-floor-designer .apos-fd-detail .row-line span:first-child { color:var(--text-muted); }
            </style>
        `);

        this.$canvas = $w.find('.apos-fd-canvas');
        this.$stats = $w.find('.apos-fd-stats');
        this.$detail = $w.find('.apos-fd-detail');
        this.$floorSel = $w.find('.floor-sel');

        $w.find('.mode-live').on('click', () => this._set_mode('live'));
        $w.find('.mode-design').on('click', () => this._set_mode('design'));
        $w.find('.add-rect').on('click', () => this._add_table('Rectangle'));
        $w.find('.add-circle').on('click', () => this._add_table('Circle'));
        $w.find('.delete-sel').on('click', () => this._delete_selected());
        $w.find('.save-layout').on('click', () => this._save_layout());
        this.$floorSel.on('change', () => this._load_floor(this.$floorSel.val()));

        this.$canvas.on('mousemove', (e) => this._on_drag(e));
        $(document).on('mouseup.apos-fd', () => { this.drag = null; });
        this.$canvas.on('click', (e) => {
            if (e.target === this.$canvas[0]) {
                this.selected = null;
                this._render_detail(null);
                this._render_tables();
            }
        });
    }

    _bind_realtime() {
        frappe.realtime.on('alphax_pos_table_status', (data) => {
            if (!this.current_floor || data.floor !== this.current_floor) return;
            const t = this.tables.find(x => x.name === data.table);
            if (t) {
                t.status = data.to_status;
                this._render_tables();
                this._render_stats();
            }
        });
    }

    _load_floor_list() {
        frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.floor.api.list_floors',
            callback: (r) => {
                const floors = r.message || [];
                this.$floorSel.empty();
                if (floors.length === 0) {
                    this.$floorSel.append('<option>No floors configured</option>');
                    return;
                }
                floors.forEach(f => {
                    this.$floorSel.append(`<option value="${f.name}">${f.floor_name}${f.outlet ? ' · ' + f.outlet : ''}</option>`);
                });
                this._load_floor(floors[0].name);
            }
        });
    }

    _load_floor(name) {
        if (!name) return;
        if (this.dirty) {
            if (!confirm('You have unsaved changes. Discard?')) {
                this.$floorSel.val(this.current_floor);
                return;
            }
        }
        this.current_floor = name;
        this.dirty = false;
        frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.floor.api.get_floor_layout',
            args: { floor: name },
            callback: (r) => {
                const data = r.message || {};
                this.floor_meta = data.floor;
                this.tables = data.tables || [];
                this._apply_canvas_size();
                this._render_tables();
                this._render_stats();
            }
        });
    }

    _apply_canvas_size() {
        if (!this.floor_meta) return;
        this.$canvas.css({
            width: (this.floor_meta.canvas_width || 800) + 'px',
            height: (this.floor_meta.canvas_height || 500) + 'px',
            background: this.floor_meta.background_color || '#f4f5f6'
        });
    }

    _set_mode(m) {
        this.mode = m;
        this.page.main.find('.mode-live').toggleClass('active', m === 'live');
        this.page.main.find('.mode-design').toggleClass('active', m === 'design');
        this.page.main.find('.apos-fd-design-tools').toggle(m === 'design');
        this.$canvas.toggleClass('designing', m === 'design');
        this.selected = null;
        this._render_detail(null);
        this._render_tables();
    }

    _render_tables() {
        this.$canvas.find('.fd-table').remove();
        this.tables.forEach(t => {
            const $t = $(`
                <div class="fd-table s-${t.status} ${t.shape === 'Circle' ? 'round' : ''} ${this.selected === t.name ? 'selected' : ''}" data-name="${t.name}">
                    <div class="num">${frappe.utils.escape_html(t.table_code)}</div>
                    <div class="seats">${t.seats || 0} seats</div>
                </div>
            `).css({
                left: (t.pos_x || 0) + 'px',
                top: (t.pos_y || 0) + 'px',
                width: (t.width || 60) + 'px',
                height: (t.height || 60) + 'px',
                transform: t.rotation ? `rotate(${t.rotation}deg)` : ''
            });
            $t.on('mousedown', (e) => this._on_down(e, t.name));
            $t.on('click', (e) => {
                e.stopPropagation();
                this.selected = t.name;
                this._render_tables();
                this._render_detail(t);
            });
            this.$canvas.append($t);
        });
    }

    _render_stats() {
        const c = { Free: 0, Occupied: 0, Reserved: 0, Dirty: 0, Disabled: 0 };
        this.tables.forEach(t => { c[t.status] = (c[t.status] || 0) + 1; });
        this.$stats.text(`${c.Free} free · ${c.Occupied} occupied · ${c.Reserved} reserved · ${c.Dirty} cleaning`);
    }

    _render_detail(t) {
        if (!t) {
            this.$detail.html('<div class="text-muted">Tap a table to see status. Switch to Design to drag tables, add new ones, or change capacity.</div>');
            return;
        }
        const actions = (this.mode === 'live')
            ? `<div style="margin-top:10px">
                ${t.status === 'Free' ? `<button class="btn btn-sm btn-primary act-occupy">Seat guests</button>` : ''}
                ${t.status === 'Occupied' ? `<button class="btn btn-sm btn-default act-bill">Mark bill printed</button>` : ''}
                ${t.status !== 'Free' ? `<button class="btn btn-sm btn-default act-free">Mark free</button>` : ''}
                <button class="btn btn-sm btn-default act-clean">Mark dirty</button>
              </div>`
            : `<div style="margin-top:10px" class="text-muted">Drag the table to reposition. Use the toolbar to delete or change shape.</div>`;
        this.$detail.html(`
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px">
                <strong>${frappe.utils.escape_html(t.table_code)}</strong>
                <span class="badge">${t.status}</span>
            </div>
            <div class="row-line"><span>Seats</span><span>${t.seats || 0}</span></div>
            <div class="row-line"><span>Shape</span><span>${t.shape}</span></div>
            <div class="row-line"><span>Position</span><span>${t.pos_x}, ${t.pos_y} · ${t.width}×${t.height}</span></div>
            ${actions}
        `);
        this.$detail.find('.act-occupy').on('click', () => this._set_status(t.name, 'Occupied'));
        this.$detail.find('.act-bill').on('click', () => this._set_status(t.name, 'Reserved'));
        this.$detail.find('.act-free').on('click', () => this._set_status(t.name, 'Free'));
        this.$detail.find('.act-clean').on('click', () => this._set_status(t.name, 'Dirty'));
    }

    _set_status(name, status) {
        frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.floor.api.update_table_status',
            args: { table: name, status: status },
            callback: () => {
                const t = this.tables.find(x => x.name === name);
                if (t) {
                    t.status = status;
                    this._render_tables();
                    this._render_stats();
                    this._render_detail(t);
                }
            }
        });
    }

    _add_table(shape) {
        if (!this.current_floor) return;
        frappe.prompt([
            { fieldname: 'table_code', label: 'Table code', fieldtype: 'Data', reqd: 1 },
            { fieldname: 'seats', label: 'Seats', fieldtype: 'Int', default: 4 }
        ], (vals) => {
            frappe.call({
                method: 'alphax_pos_suite.alphax_pos_suite.floor.api.add_table',
                args: {
                    floor: this.current_floor,
                    table_code: vals.table_code,
                    seats: vals.seats,
                    shape: shape,
                    pos_x: 60, pos_y: 60,
                    width: shape === 'Circle' ? 70 : 80,
                    height: shape === 'Circle' ? 70 : 60
                },
                callback: () => this._load_floor(this.current_floor)
            });
        }, 'Add table', 'Create');
    }

    _delete_selected() {
        if (!this.selected) return frappe.show_alert('Select a table first');
        frappe.confirm(`Delete table ${this.selected}?`, () => {
            frappe.call({
                method: 'frappe.client.delete',
                args: { doctype: 'AlphaX POS Table', name: this.selected },
                callback: () => {
                    this.selected = null;
                    this._load_floor(this.current_floor);
                }
            });
        });
    }

    _save_layout() {
        if (!this.current_floor) return;
        frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.floor.api.save_floor_layout',
            args: {
                floor: this.current_floor,
                tables: JSON.stringify(this.tables.map(t => ({
                    name: t.name, pos_x: t.pos_x, pos_y: t.pos_y,
                    width: t.width, height: t.height, rotation: t.rotation,
                    shape: t.shape, seats: t.seats
                })))
            },
            callback: () => {
                this.dirty = false;
                frappe.show_alert({ message: 'Layout saved', indicator: 'green' });
            }
        });
    }

    _on_down(e, name) {
        if (this.mode !== 'design') return;
        this.selected = name;
        const t = this.tables.find(x => x.name === name);
        if (!t) return;
        const rect = this.$canvas[0].getBoundingClientRect();
        this.drag = {
            name: name,
            ox: e.clientX - rect.left - (t.pos_x || 0),
            oy: e.clientY - rect.top - (t.pos_y || 0)
        };
        e.preventDefault();
    }

    _on_drag(e) {
        if (!this.drag) return;
        const t = this.tables.find(x => x.name === this.drag.name);
        if (!t) return;
        const rect = this.$canvas[0].getBoundingClientRect();
        const grid = (this.floor_meta && this.floor_meta.grid_size) || 10;
        const cw = (this.floor_meta && this.floor_meta.canvas_width) || 800;
        const ch = (this.floor_meta && this.floor_meta.canvas_height) || 500;
        const nx = Math.max(0, Math.min(cw - (t.width || 60), Math.round((e.clientX - rect.left - this.drag.ox) / grid) * grid));
        const ny = Math.max(0, Math.min(ch - (t.height || 60), Math.round((e.clientY - rect.top - this.drag.oy) / grid) * grid));
        if (nx !== t.pos_x || ny !== t.pos_y) {
            t.pos_x = nx;
            t.pos_y = ny;
            this.dirty = true;
            this._render_tables();
            this._render_detail(t);
        }
    }
}
