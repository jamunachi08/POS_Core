// AlphaX POS — Receipt Designer (v16.4.0): arrange receipt blocks, preview at paper width, ZATCA check.
frappe.pages['alphax-receipt-designer'].on_page_load = function (wrapper) {
  const R = 'alphax_pos_suite.alphax_pos_suite.receipts.render';
  const TYPES = ['Logo', 'Title', 'Company & VAT', 'Outlet & Address', 'Invoice Details', 'Customer', 'Items', 'Totals',
    'VAT Breakdown', 'Payments', 'ZATCA QR', 'Loyalty & Gift Balance', 'Text', 'Divider', 'Spacer'];
  const esc = frappe.utils.escape_html;
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Receipt Designer'), single_column: true });
  const st = { name: null, doc: null, invoice: null, dirty: false };
  const fT = page.add_field({ fieldname: 't', label: __('Template'), fieldtype: 'Link', options: 'AlphaX Receipt Template', change: () => open(fT.get_value()) });
  const fInv = page.add_field({ fieldname: 'inv', label: __('Preview with invoice'), fieldtype: 'Link', options: 'Sales Invoice',
    get_query: () => ({ filters: { docstatus: 1, is_pos: 1 } }), change: () => { st.invoice = fInv.get_value() || null; preview(); } });
  page.set_primary_action(__('Save'), save, 'save');
  page.add_inner_button(__('New template'), () => {
    frappe.prompt({ fieldname: 'n', label: __('Template name'), fieldtype: 'Data', reqd: 1 }, (v) => {
      frappe.call(`${R}.default_blocks`).then((r) => {
        st.name = null; st.doc = { doctype: 'AlphaX Receipt Template', template_name: v.n, paper_width_mm: '80', language: 'Arabic and English', base_font_pt: 9, blocks: r.message.map((b) => ({ ...b })) };
        draw(); preview();
      });
    });
  });
  const $b = $(`<div class="axrd"><style>
    .axrd{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;padding:10px 0 60px}
    @media(max-width:900px){.axrd{grid-template-columns:1fr}}
    .axrd-row{display:grid;grid-template-columns:26px 1.3fr .8fr 60px 44px 1.4fr 1.4fr 54px 82px;gap:6px;align-items:center;border-bottom:1px solid var(--border-color);padding:6px 0}
    .axrd-row input,.axrd-row select{width:100%;font-size:12px;padding:3px 5px;border:1px solid var(--border-color);border-radius:6px;background:var(--control-bg)}
    .axrd-row.off{opacity:.45}.axrd-head{font-size:11px;color:var(--text-muted);font-weight:600}
    .axrd-paper{background:#fff;color:#000;box-shadow:0 2px 10px rgba(0,0,0,.15);padding:4mm 0;margin:0 auto}
    .axrd-miss{border-radius:10px;padding:10px 12px;font-size:13px;margin-bottom:12px}
    .axrd-miss.bad{background:var(--orange-50);color:var(--orange-800)}.axrd-miss.ok{background:var(--green-50);color:var(--green-800)}
    .axrd-set{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px}.axrd-set label{font-size:12px;color:var(--text-muted)}
    .axrd-set select,.axrd-set input{display:block;font-size:13px;padding:4px 6px;border:1px solid var(--border-color);border-radius:6px}
  </style><div class="axrd-l"></div><div class="axrd-r"></div></div>`).appendTo(page.body);
  const $l = $b.find('.axrd-l'), $r = $b.find('.axrd-r');

  function open(name) {
    if (!name) return;
    frappe.db.get_doc('AlphaX Receipt Template', name).then((d) => { st.name = name; st.doc = d; draw(); preview(); });
  }
  function draw() {
    const d = st.doc; if (!d) { $l.html(`<p class="text-muted">${__('Pick a template or create one.')}</p>`); return; }
    const sel = (opts, v) => opts.map((o) => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('');
    let h = `<div class="axrd-set">
      <label>${__('Paper (mm)')}<select data-s="paper_width_mm">${sel(['80', '58', '76'], String(d.paper_width_mm))}</select></label>
      <label>${__('Language')}<select data-s="language">${sel(['Arabic and English', 'Arabic', 'English'], d.language)}</select></label>
      <label>${__('Base font (pt)')}<input type="number" data-s="base_font_pt" value="${esc(d.base_font_pt || 9)}" style="width:70px"></label>
      <label><input type="checkbox" data-s="is_default" ${d.is_default ? 'checked' : ''}> ${__('Default')}</label></div>
      <div class="axrd-row axrd-head"><span></span><span>${__('Block')}</span><span>${__('Align')}</span><span>${__('Size')}</span><span>${__('Bold')}</span><span>${__('English text')}</span><span>${__('Arabic text')}</span><span>${__('Hide')}</span><span></span></div>`;
    (d.blocks || []).forEach((b, i) => {
      h += `<div class="axrd-row ${b.hidden ? 'off' : ''}" data-i="${i}"><span class="text-muted">${i + 1}</span>
        <select data-f="block_type">${sel(TYPES, b.block_type)}</select>
        <select data-f="align">${sel(['Center', 'Start', 'End'], b.align || 'Center')}</select>
        <input type="number" data-f="font_size" value="${esc(b.font_size || '')}">
        <input type="checkbox" data-f="bold" ${b.bold ? 'checked' : ''}>
        <input data-f="text_en" value="${esc(b.text_en || '')}" placeholder="${['Title', 'Text'].includes(b.block_type) ? '' : '—'}">
        <input data-f="text_ar" dir="rtl" value="${esc(b.text_ar || '')}">
        <input type="checkbox" data-f="hidden" ${b.hidden ? 'checked' : ''}>
        <span><button class="btn btn-xs btn-default" data-m="-1">↑</button> <button class="btn btn-xs btn-default" data-m="1">↓</button> <button class="btn btn-xs btn-default" data-x>✕</button></span></div>`;
    });
    h += `<button class="btn btn-sm btn-default" style="margin-top:10px" data-add>+ ${__('Add block')}</button>`;
    $l.html(h);
    $l.find('[data-s]').on('change', function () { d[this.dataset.s] = this.type === 'checkbox' ? (this.checked ? 1 : 0) : this.value; changed(); });
    $l.find('[data-f]').on('change', function () {
      const b = d.blocks[$(this).closest('[data-i]').data('i')];
      b[this.dataset.f] = this.type === 'checkbox' ? (this.checked ? 1 : 0) : (this.type === 'number' ? parseInt(this.value) || null : this.value);
      changed(this.dataset.f === 'hidden' || this.dataset.f === 'block_type');
    });
    $l.find('[data-m]').on('click', function () {
      const i = $(this).closest('[data-i]').data('i'), j = i + Number(this.dataset.m);
      if (j < 0 || j >= d.blocks.length) return; [d.blocks[i], d.blocks[j]] = [d.blocks[j], d.blocks[i]]; changed(true);
    });
    $l.find('[data-x]').on('click', function () { d.blocks.splice($(this).closest('[data-i]').data('i'), 1); changed(true); });
    $l.find('[data-add]').on('click', () => { d.blocks.push({ block_type: 'Text', align: 'Center' }); changed(true); });
  }
  let timer;
  function changed(redraw) { st.dirty = true; if (redraw) draw(); clearTimeout(timer); timer = setTimeout(preview, 300); }
  function preview() {
    if (!st.doc) return;
    const t = { ...st.doc, blocks: (st.doc.blocks || []).map((b) => ({ ...b })) };
    frappe.call({ method: `${R}.preview`, args: { template: JSON.stringify(t), invoice: st.invoice } }).then((r) => {
      const m = r.message, w = parseInt(st.doc.paper_width_mm) || 80;
      $r.html(`<div class="axrd-miss ${m.missing.length ? 'bad' : 'ok'}">${m.missing.length
        ? '<b>' + __('ZATCA simplified invoice — missing:') + '</b><br>' + m.missing.map(esc).join('<br>')
        : __('All ZATCA simplified-invoice elements present.')}</div>
        <div class="axrd-paper" style="width:${w}mm">${m.html}</div>
        <div class="text-muted small" style="margin-top:8px">${m.invoice ? __('Preview: {0}', [esc(m.invoice)]) : ''}</div>`);
    });
  }
  function save() {
    if (!st.doc) return;
    frappe.call({ method: 'frappe.client.save', args: { doc: st.doc } }).then((r) => {
      st.doc = r.message; st.name = r.message.name; st.dirty = false; fT.set_value(st.name);
      frappe.show_alert({ message: __('Saved'), indicator: 'green' }); draw(); preview();
    });
  }
  frappe.db.get_value('AlphaX Receipt Template', { is_default: 1 }, 'name').then((r) => { if (r.message && r.message.name) fT.set_value(r.message.name); else draw(); });
};
