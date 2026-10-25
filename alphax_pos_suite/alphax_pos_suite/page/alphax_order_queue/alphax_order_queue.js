// AlphaX POS — Order Queue (v16.3.0): table (QR) and online pickup orders.
frappe.pages['alphax-order-queue'].on_page_load = function (wrapper) {
  const API = 'alphax_pos_suite.alphax_pos_suite.ordering.api';
  const AR = (frappe.boot.lang || '').startsWith('ar');
  const T = (en, ar) => (AR ? ar : en);
  const esc = frappe.utils.escape_html;
  const page = frappe.ui.make_app_page({ parent: wrapper, title: T('Order Queue', 'قائمة الطلبات'), single_column: true });
  const st = { outlet: localStorage.getItem('axoq.outlet') || '', data: null };
  const fOutlet = page.add_field({ fieldname: 'outlet', label: T('Outlet', 'المنفذ'), fieldtype: 'Select', change: () => { st.outlet = fOutlet.get_value(); localStorage.setItem('axoq.outlet', st.outlet); load(); } });
  page.add_menu_item(T('Outlet online settings', 'إعدادات الطلب الإلكتروني'), () => st.outlet && frappe.set_route('Form', 'AlphaX POS Outlet', st.outlet));
  page.add_menu_item(T('Table QR codes', 'رموز الطاولات'), () => frappe.set_route('List', 'AlphaX POS QR Table Token'));
  const $root = $(`<div class="axoq" dir="${AR ? 'rtl' : 'ltr'}"></div>`).appendTo(page.body);
  $(`<style>
    .axoq{padding:10px 2px 60px}
    .axoq-cols{display:grid;grid-template-columns:repeat(4,minmax(240px,1fr));gap:14px}
    @media(max-width:1100px){.axoq-cols{grid-template-columns:repeat(2,1fr)}}@media(max-width:640px){.axoq-cols{grid-template-columns:1fr}}
    .axoq-col h4{font-size:13px;font-weight:600;color:var(--text-muted);margin:0 0 8px;display:flex;justify-content:space-between}
    .axoq-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:12px;margin-bottom:10px}
    .axoq-card.late{border-color:var(--red-400)}
    .axoq-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
    .axoq-no{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
    .axoq-meta{font-size:12px;color:var(--text-muted);text-align:end}
    .axoq-items{list-style:none;padding:0;margin:8px 0;font-size:13px}.axoq-items small{color:var(--text-muted)}
    .axoq-note{background:var(--yellow-50);border-radius:8px;padding:6px 8px;font-size:12px;margin-bottom:8px}
    .axoq-btns{display:flex;gap:6px;flex-wrap:wrap}.axoq-btns .btn{flex:1}
    .axoq-src{font-size:11px;border-radius:6px;padding:1px 7px;background:var(--gray-100)}
    .axoq-src.Online{background:var(--blue-100);color:var(--blue-700)}.axoq-src.QR{background:var(--green-100);color:var(--green-700)}
    .axoq-due{font-weight:600;font-variant-numeric:tabular-nums}.axoq-due.late{color:var(--red-600)}
  </style>`).appendTo($root);
  const $body = $('<div></div>').appendTo($root);
  const call = (m, a) => frappe.call({ method: `${API}.${m}`, args: a }).then((r) => r.message);

  function load() {
    return call('board', { outlet: st.outlet || null }).then((d) => {
      st.data = d; fOutlet.df.options = [''].concat(d.outlets); fOutlet.refresh(); fOutlet.set_value(st.outlet); render();
    });
  }
  function due(o) {
    if (!o.promised_at) return '';
    const m = moment(o.promised_at).diff(moment(), 'minutes');
    return `<span class="axoq-due ${m < 0 ? 'late' : ''}">${m < 0 ? T('late ', 'متأخر ') + -m + T(' min', ' د') : T('in ', 'خلال ') + m + T(' min', ' د')}</span>`;
  }
  function card(o) {
    const late = o.promised_at && moment(o.promised_at).isBefore(moment()) && ['In Kitchen', 'Ready'].includes(o.queue_status);
    const where = o.fulfilment === 'Pickup' ? T('Pickup', 'استلام') + (o.customer_name ? ' · ' + esc(o.customer_name) : '') : T('Table ', 'طاولة ') + esc(o.table || '');
    let b = '';
    if (o.queue_status === 'New') b = `<button class="btn btn-primary btn-sm" data-a="confirm">${T('Send to kitchen', 'إرسال للمطبخ')}</button><button class="btn btn-default btn-sm" data-a="reject">${T('Reject', 'رفض')}</button>`;
    else if (o.queue_status === 'In Kitchen') b = `<button class="btn btn-default btn-sm" data-a="ready">${T('Mark ready', 'جاهز')}</button>`;
    else if (o.queue_status === 'Ready') b = `<button class="btn btn-primary btn-sm" data-a="complete">${o.fulfilment === 'Pickup' ? T('Collected', 'تم الاستلام') : T('Served', 'تم التقديم')}</button>`;
    if (['In Kitchen', 'Ready', 'Completed'].includes(o.queue_status) && !o.sales_invoice) b += `<button class="btn btn-default btn-sm" data-a="settle">${T('Take payment', 'تحصيل')} ${esc(String(o.total))}</button>`;
    if (['In Kitchen', 'Ready'].includes(o.queue_status)) b += `<button class="btn btn-default btn-sm" data-a="cancel">${T('Cancel', 'إلغاء')}</button>`;
    return `<div class="axoq-card ${late ? 'late' : ''}" data-name="${esc(o.name)}">
      <div class="axoq-top"><div class="axoq-no">${esc(o.queue_number || '')}</div><div class="axoq-meta"><span class="axoq-src ${esc(o.order_source)}">${o.order_source === 'QR' ? T('Table', 'طاولة') : T('Online', 'أونلاين')}</span><br>${where}</div></div>
      <div class="axoq-top" style="margin-top:6px"><small>${moment(o.creation).format('HH:mm')}</small>${due(o)}</div>
      <ul class="axoq-items">${o.items.map((i) => `<li>${esc(String(i.qty))} × ${esc(i.name)}${i.note ? ` <small>(${esc(i.note)})</small>` : ''}</li>`).join('')}</ul>
      ${o.queue_note ? `<div class="axoq-note">${esc(o.queue_note)}</div>` : ''}
      ${o.sales_invoice ? `<div class="axoq-meta"><a href="/app/sales-invoice/${encodeURIComponent(o.sales_invoice)}">${esc(o.sales_invoice)}</a></div>` : ''}
      <div class="axoq-btns">${b}</div></div>`;
  }
  function render() {
    const os = st.data.orders;
    const cols = [
      [T('New', 'جديد'), os.filter((o) => o.queue_status === 'New')],
      [T('In the kitchen', 'في المطبخ'), os.filter((o) => o.queue_status === 'In Kitchen')],
      [T('Ready', 'جاهز'), os.filter((o) => o.queue_status === 'Ready')],
      [T('Done / to pay', 'منتهٍ / للتحصيل'), os.filter((o) => ['Completed', 'Settled', 'Rejected', 'Cancelled'].includes(o.queue_status)).slice(0, 40)],
    ];
    $body.html(`<div class="axoq-cols">${cols.map(([t, l]) => `<div class="axoq-col"><h4><span>${t}</span><span>${l.length}</span></h4>${l.map(card).join('')}</div>`).join('')}</div>`);
    $body.find('[data-a]').on('click', function () { act($(this).closest('.axoq-card').data('name'), $(this).data('a')); });
  }
  function act(name, a) {
    const o = st.data.orders.find((x) => x.name === name);
    const ask = (title, fields, fn) => { const d = new frappe.ui.Dialog({ title: `${title} ${o.queue_number}`, fields, primary_action_label: title, primary_action: (v) => { d.hide(); fn(v); } }); d.show(); };
    if (a === 'confirm') return ask(T('Send to kitchen', 'إرسال للمطبخ'), [{ fieldname: 'm', fieldtype: 'Int', label: T('Ready in (minutes)', 'جاهز خلال (دقائق)'), default: 15 }], (v) => run('confirm', { order: name, prep_minutes: v.m }));
    if (a === 'reject' || a === 'cancel') return ask(a === 'reject' ? T('Reject', 'رفض') : T('Cancel', 'إلغاء'), [{ fieldname: 'r', fieldtype: 'Data', label: T('Reason shown to the guest', 'السبب الظاهر للضيف'), reqd: 1 }], (v) => run(a, { order: name, reason: v.r }));
    if (a === 'settle') return ask(T('Take payment', 'تحصيل'), [{ fieldname: 'mop', fieldtype: 'Select', label: T('Paid by', 'طريقة الدفع'), options: st.data.modes_of_payment, reqd: 1 }], (v) => run('settle', { order: name, mode_of_payment: v.mop }));
    run(a, { order: name });
  }
  function run(m, args) { call(m, args).then(() => { frappe.show_alert({ message: T('Done', 'تم'), indicator: 'green' }); load(); }); }
  frappe.realtime.on('alphax_order_queue', (m) => {
    if (m.event === 'new' && (!st.outlet || m.outlet === st.outlet)) { frappe.utils.play_sound('alert'); frappe.show_alert({ message: T('New order ', 'طلب جديد ') + esc(m.number || ''), indicator: 'blue' }, 8); }
    load();
  });
  setInterval(load, 30000);
  load();
};
