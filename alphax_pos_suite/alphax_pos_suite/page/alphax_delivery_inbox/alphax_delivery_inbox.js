// AlphaX POS — Delivery Inbox (v16.2.0): HungerStation, Jahez, Keeta orders in one place.
frappe.pages['alphax-delivery-inbox'].on_page_load = function (wrapper) {
  const API = 'alphax_pos_suite.alphax_pos_suite.integrations.aggregators.api';
  const AR = (frappe.boot.lang || '').startsWith('ar');
  const T = (en, ar) => (AR ? ar : en);
  const esc = frappe.utils.escape_html;
  const page = frappe.ui.make_app_page({ parent: wrapper, title: T('Delivery Inbox', 'صندوق التوصيل'), single_column: true });
  const st = { outlet: localStorage.getItem('axdi.outlet') || '', data: null, skew: 0 };
  const fOutlet = page.add_field({ fieldname: 'outlet', label: T('Outlet', 'المنفذ'), fieldtype: 'Select', change: () => { st.outlet = fOutlet.get_value(); localStorage.setItem('axdi.outlet', st.outlet); load(); } });
  page.add_menu_item(T('Connections', 'الاتصالات'), () => frappe.set_route('List', 'AlphaX Aggregator Connection'));
  page.add_menu_item(T('Item mapping', 'ربط الأصناف'), () => frappe.set_route('List', 'AlphaX Aggregator Item Map', { item_code: ['is', 'not set'] }));
  page.add_menu_item(T('Request log', 'سجل الطلبات'), () => frappe.set_route('List', 'AlphaX Aggregator Log'));

  const $root = $(`<div class="axdi" dir="${AR ? 'rtl' : 'ltr'}"></div>`).appendTo(page.body);
  $(`<style>
    .axdi{padding:10px 2px 60px}
    .axdi-lane{margin-bottom:22px}.axdi-lane h4{font-size:13px;font-weight:600;color:var(--text-muted);margin:0 0 8px}
    .axdi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
    .axdi-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:12px;display:flex;flex-direction:column;gap:8px}
    .axdi-card.warn{border-color:var(--red-400)}
    .axdi-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
    .axdi-code{font-size:30px;font-weight:700;letter-spacing:.5px;font-variant-numeric:tabular-nums;line-height:1}
    .axdi-plat{font-size:12px;color:var(--text-muted);text-align:end}
    .axdi-clock{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
    .axdi-clock.g{color:var(--green-600)}.axdi-clock.a{color:var(--orange-600)}.axdi-clock.r{color:var(--red-600)}
    .axdi-items{font-size:13px;margin:0;padding:0;list-style:none}.axdi-items li{padding:2px 0}
    .axdi-items .m{color:var(--text-muted);padding-inline-start:14px;font-size:12px}
    .axdi-note{background:var(--yellow-50);border-radius:8px;padding:6px 8px;font-size:12px}
    .axdi-err{color:var(--red-600);font-size:12px}
    .axdi-test{background:var(--red-100);color:var(--red-700);border-radius:6px;padding:1px 8px;font-size:11px;font-weight:600}
    .axdi-btns{display:flex;gap:6px;flex-wrap:wrap}.axdi-btns .btn{flex:1}
    .axdi-empty{color:var(--text-muted);padding:24px;text-align:center;border:1px dashed var(--border-color);border-radius:12px}
  </style>`).appendTo($root);
  const $body = $('<div></div>').appendTo($root);
  const call = (m, a) => frappe.call({ method: `${API}.${m}`, args: a }).then((r) => r.message);

  function load() {
    return call('inbox', { outlet: st.outlet || null }).then((d) => {
      st.data = d; st.skew = moment(d.now).diff(moment());
      fOutlet.df.options = [''].concat(d.outlets); fOutlet.refresh(); fOutlet.set_value(st.outlet);
      render();
    });
  }
  const left = (o) => (o.expiry ? moment(o.expiry).diff(moment().add(st.skew, 'ms'), 'seconds') : null);
  function clock(o) {
    const s = left(o); if (s == null) return '';
    const cls = s > 300 ? 'g' : s > 120 ? 'a' : 'r';
    const t = s <= 0 ? T('expired', 'انتهى') : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    return `<span class="axdi-clock ${cls}" data-exp="${esc(o.name)}">${t}</span>`;
  }
  function card(o) {
    const items = (o.items || []).map((i) => `<li class="${i.is_modifier ? 'm' : ''}">${i.is_modifier ? '+ ' : ''}${esc(String(i.qty))} × ${esc(i.external_name || '')}${i.item_code ? '' : (i.is_modifier ? '' : ' <span class="axdi-err">' + T('unmapped', 'غير مربوط') + '</span>')}</li>`).join('');
    let btns = '';
    if (o.status === 'Received') btns = `<button class="btn btn-primary btn-sm" data-a="accept">${T('Accept', 'قبول')}</button><button class="btn btn-default btn-sm" data-a="reject">${T('Reject', 'رفض')}</button>`;
    else if (o.status === 'Accepted' && o.expedition !== 'Platform delivery') btns = `<button class="btn btn-primary btn-sm" data-a="picked_up">${T('Handed over', 'تم التسليم')}</button>`;
    else if (o.status === 'Accepted') btns = `<button class="btn btn-primary btn-sm" data-a="ready">${T('Food ready', 'الطلب جاهز')}</button>`;
    else if (o.status === 'Ready' && o.expedition !== 'Platform delivery') btns = `<button class="btn btn-primary btn-sm" data-a="picked_up">${T('Handed over', 'تم التسليم')}</button>`;
    if (o.needs_review && o.status === 'Accepted' && !o.sales_invoice) btns += `<button class="btn btn-default btn-sm" data-a="post_invoice">${T('Post invoice', 'ترحيل الفاتورة')}</button>`;
    return `<div class="axdi-card ${o.needs_review ? 'warn' : ''}" data-name="${esc(o.name)}">
      <div class="axdi-top"><div class="axdi-code">#${esc(o.short_code || '')}</div><div class="axdi-plat">${esc(o.platform || '')}<br>${esc(o.expedition || '')}</div></div>
      <div class="axdi-top">${o.status === 'Received' ? clock(o) : `<b>${esc(o.status)}</b>`}${o.is_test ? `<span class="axdi-test">${T('TEST — do not cook', 'اختبار — لا تطبخ')}</span>` : ''}</div>
      <ul class="axdi-items">${items}</ul>
      ${o.customer_note ? `<div class="axdi-note">${esc(o.customer_note)}</div>` : ''}
      ${o.review_note || o.last_error ? `<div class="axdi-err">${esc(o.last_error || o.review_note)}</div>` : ''}
      ${o.sales_invoice ? `<div class="axdi-plat"><a href="/app/sales-invoice/${encodeURIComponent(o.sales_invoice)}">${esc(o.sales_invoice)}</a></div>` : ''}
      <div class="axdi-btns">${btns}</div></div>`;
  }
  function render() {
    const os = st.data.orders;
    const lanes = [
      [T('Waiting for you', 'بانتظار الرد'), os.filter((o) => o.status === 'Received')],
      [T('In the kitchen', 'في المطبخ'), os.filter((o) => ['Accepted', 'Ready', 'Test'].includes(o.status))],
      [T('Needs attention', 'يحتاج انتباه'), os.filter((o) => o.needs_review && !['Received', 'Accepted', 'Ready'].includes(o.status))],
      [T('Done today', 'منتهية اليوم'), os.filter((o) => ['Picked Up', 'Delivered', 'Rejected', 'Cancelled', 'Expired'].includes(o.status) && !o.needs_review)],
    ];
    $body.html(lanes.map(([t, list]) => `<div class="axdi-lane"><h4>${t} (${list.length})</h4>${list.length ? `<div class="axdi-grid">${list.map(card).join('')}</div>` : `<div class="axdi-empty">—</div>`}</div>`).join(''));
    $body.find('[data-a]').on('click', function () { act($(this).closest('.axdi-card').data('name'), $(this).data('a')); });
  }
  function act(name, a) {
    const o = st.data.orders.find((x) => x.name === name);
    if (a === 'reject') {
      const reasons = st.data.reasons[o.connection] || ['OTHER'];
      const d = new frappe.ui.Dialog({ title: T('Reject order', 'رفض الطلب') + ' #' + o.short_code, fields: [
        { fieldname: 'reason', label: T('Reason', 'السبب'), fieldtype: 'Select', options: reasons, reqd: 1 },
        { fieldname: 'message', label: T('Message', 'رسالة'), fieldtype: 'Small Text' }],
        primary_action_label: T('Reject', 'رفض'), primary_action: (v) => { d.hide(); run('reject', { order: name, reason: v.reason, message: v.message || '' }); } });
      return d.show();
    }
    if (a === 'accept') {
      const d = new frappe.ui.Dialog({ title: T('Accept', 'قبول') + ' #' + o.short_code, fields: [
        { fieldname: 'prep', label: T('Ready in (minutes)', 'جاهز خلال (دقائق)'), fieldtype: 'Int', default: 15 }],
        primary_action_label: T('Accept', 'قبول'), primary_action: (v) => { d.hide(); run('accept', { order: name, prep_minutes: v.prep }); } });
      return d.show();
    }
    if (a === 'picked_up' && o.expedition === 'Platform delivery') return;
    run(a, { order: name });
  }
  function run(m, args) {
    call(m, args).then((r) => {
      const ok = r === true || (r && (r.ok || typeof r === 'string'));
      frappe.show_alert({ message: ok ? T('Done', 'تم') : esc((r && r.message) || T('Failed', 'فشل')), indicator: ok ? 'green' : 'red' }, 7);
      load();
    });
  }
  frappe.realtime.on('alphax_aggregator_order', (m) => {
    if (m.event === 'new') { frappe.utils.play_sound('alert'); frappe.show_alert({ message: T('New delivery order #', 'طلب توصيل جديد #') + esc(m.short_code || ''), indicator: 'blue' }, 8); }
    load();
  });
  setInterval(() => { if (st.data) $body.find('[data-exp]').each(function () { const o = st.data.orders.find((x) => x.name === $(this).data('exp')); if (o) $(this).replaceWith(clock(o)); }); }, 1000);
  setInterval(load, 30000);
  load();
};
