// AlphaX Wallet — Gift Cards (v16.4.0): sell, reload, check, refund, set up.
frappe.pages['alphax-gift-cards'].on_page_load = function (wrapper) {
  const A = 'alphax_pos_suite.alphax_pos_suite.giftcard.api';
  const esc = frappe.utils.escape_html;
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Gift Cards'), single_column: true });
  const fOutlet = page.add_field({ fieldname: 'outlet', label: __('Outlet'), fieldtype: 'Link', options: 'AlphaX POS Outlet', reqd: 1,
    default: localStorage.getItem('axgc.outlet') || '', change: () => localStorage.setItem('axgc.outlet', fOutlet.get_value() || '') });
  page.add_menu_item(__('All cards'), () => frappe.set_route('List', 'AlphaX Gift Card'));
  page.add_menu_item(__('Batches'), () => frappe.set_route('List', 'AlphaX Gift Card Batch'));
  page.add_menu_item(__('Ledger'), () => frappe.set_route('List', 'AlphaX Gift Card Entry'));
  page.add_menu_item(__('Set up gift cards for a company'), () => frappe.prompt(
    { fieldname: 'c', label: __('Company'), fieldtype: 'Link', options: 'Company', reqd: 1 },
    (v) => frappe.call({ method: `${A}.setup`, args: { company: v.c } }).then((r) => frappe.msgprint((r.message || []).map(esc).join('<br>') || __('Already set up.')))));
  const $b = $(`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;padding:10px 0 60px">
    <div class="frappe-card p-3"><h5>${__('Sell a card')}</h5><div class="sell"></div></div>
    <div class="frappe-card p-3"><h5>${__('Check, reload or refund')}</h5><div class="chk"></div><div class="out" style="margin-top:12px"></div></div>
  </div>`).appendTo(page.body);
  const need = () => { const o = fOutlet.get_value(); if (!o) frappe.throw(__('Choose the outlet first.')); return o; };
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());

  const sell = new frappe.ui.FieldGroup({ body: $b.find('.sell'), fields: [
    { fieldname: 'value', label: __('Value'), fieldtype: 'Currency', reqd: 1 },
    { fieldname: 'mop', label: __('Paid by'), fieldtype: 'Link', options: 'Mode of Payment', reqd: 1 },
    { fieldname: 'code', label: __('Pre-printed card number (optional)'), fieldtype: 'Data' },
    { fieldname: 'purchaser', label: __('Purchaser'), fieldtype: 'Link', options: 'Customer' },
    { fieldname: 'recipient_name', label: __('Recipient'), fieldtype: 'Data' },
    { fieldname: 'recipient_phone', label: __('Recipient mobile'), fieldtype: 'Data' },
    { fieldname: 'message', label: __('Message'), fieldtype: 'Small Text' },
    { fieldname: 'go', label: __('Sell card'), fieldtype: 'Button' },
  ] });
  sell.make();
  sell.fields_dict.go.$input.addClass('btn-primary').on('click', () => {
    const v = sell.get_values(); if (!v) return;
    frappe.call({ method: `${A}.sell`, freeze: true, args: { value: v.value, mode_of_payment: v.mop, outlet: need(), code: v.code || null,
      purchaser: v.purchaser || null, recipient_name: v.recipient_name || '', recipient_phone: v.recipient_phone || '', message: v.message || '', client_uuid: uuid() } })
      .then((r) => {
        const m = r.message;
        frappe.msgprint({ title: __('Card sold'), indicator: 'green', message:
          (m.number ? `<div style="font-size:24px;font-weight:700;letter-spacing:2px;font-variant-numeric:tabular-nums">${esc(m.number)}</div>
            ${m.pin ? `<div>${__('PIN')}: <b>${esc(m.pin)}</b></div>` : ''}
            <p class="text-muted">${__('Write the number on the card or give it to the customer now. It is not shown again.')}</p>` : '') +
          `<p>${esc(m.masked)} — ${format_currency(m.balance)} · ${__('expires')} ${esc(m.expires_on)}</p>` });
        sell.clear();
      });
  });

  const chk = new frappe.ui.FieldGroup({ body: $b.find('.chk'), fields: [
    { fieldname: 'code', label: __('Card number'), fieldtype: 'Data', reqd: 1 },
    { fieldname: 'go', label: __('Look up'), fieldtype: 'Button' },
  ] });
  chk.make();
  chk.fields_dict.go.$input.on('click', () => {
    const v = chk.get_values(); if (!v) return;
    frappe.call({ method: `${A}.lookup`, args: { code: v.code } }).then((r) => show(r.message, v.code));
  });
  function show(card, code) {
    frappe.call({ method: `${A}.statement`, args: { card } }).then((r) => {
      const s = r.message;
      const $o = $b.find('.out').html(`<div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:18px">${esc(s.card)}</b>
        <span>${esc(s.status)}</span></div><div style="font-size:28px;font-weight:700">${format_currency(s.balance)}</div>
        <div class="text-muted small">${__('Expires')} ${esc(s.expires_on || '—')}</div>
        <div style="display:flex;gap:6px;margin:10px 0"><button class="btn btn-sm btn-default" data-reload>${__('Reload')}</button>
        <button class="btn btn-sm btn-default" data-void>${__('Refund and void')}</button></div>
        <table class="table table-sm small">${s.entries.map((e) => `<tr><td>${esc(moment(e.creation).format('YYYY-MM-DD HH:mm'))}</td><td>${esc(e.entry_type)}</td>
        <td class="text-right">${format_currency(e.amount)}</td><td class="text-right">${format_currency(e.balance_after)}</td><td>${esc(e.reference_name || '')}</td></tr>`).join('')}</table>`);
      $o.find('[data-reload]').on('click', () => frappe.prompt([
        { fieldname: 'value', label: __('Amount'), fieldtype: 'Currency', reqd: 1 },
        { fieldname: 'mop', label: __('Paid by'), fieldtype: 'Link', options: 'Mode of Payment', reqd: 1 }],
        (v) => frappe.call({ method: `${A}.reload`, args: { code, value: v.value, mode_of_payment: v.mop, outlet: need(), client_uuid: uuid() } }).then(() => show(card, code))));
      $o.find('[data-void]').on('click', () => frappe.prompt([
        { fieldname: 'mop', label: __('Refund by'), fieldtype: 'Link', options: 'Mode of Payment', reqd: 1 },
        { fieldname: 'reason', label: __('Reason'), fieldtype: 'Data', reqd: 1 }],
        (v) => frappe.call({ method: `${A}.refund_and_void`, args: { card, mode_of_payment: v.mop, reason: v.reason } }).then(() => show(card, code))));
    });
  }
};
