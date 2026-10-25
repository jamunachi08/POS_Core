// AlphaX POS — Demand & Prep Planner (v16.1.0)
// Forecasts come from the on-site statistical engine; nothing here calls out.
frappe.pages['alphax-pos-forecast'].on_page_load = function (wrapper) {
  const API = 'alphax_pos_suite.alphax_pos_suite.forecast.api';
  const AR = (frappe.boot.lang || '').startsWith('ar');
  const T = (en, ar) => (AR ? ar : en);
  const esc = frappe.utils.escape_html;
  const num = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString(AR ? 'ar-SA' : 'en-US', { maximumFractionDigits: d }));

  const page = frappe.ui.make_app_page({ parent: wrapper, title: T('Demand & Prep Planner', 'مخطط الطلب والتحضير'), single_column: true });
  const state = { outlet: null, date: frappe.datetime.get_today(), data: null, poll: null };

  const fOutlet = page.add_field({ fieldname: 'outlet', label: T('Outlet', 'المنفذ'), fieldtype: 'Select', change: () => { state.outlet = fOutlet.get_value(); load(); } });
  const fDate = page.add_field({ fieldname: 'date', label: T('Date', 'التاريخ'), fieldtype: 'Date', default: state.date, change: () => { state.date = fDate.get_value() || frappe.datetime.get_today(); load(); } });

  const btnRun = page.set_primary_action(T('Run forecast', 'تشغيل التنبؤ'), runNow, 'refresh');
  page.add_inner_button(T('Build prep plan', 'إنشاء خطة التحضير'), () => buildPrep(false));
  page.add_inner_button(T('Request shortfall', 'طلب النواقص'), createMR);
  page.add_inner_button(T('Print prep sheet', 'طباعة ورقة التحضير'), () => window.print());
  page.add_menu_item(T('Calendar events', 'أحداث التقويم'), () => frappe.set_route('List', 'AlphaX POS Calendar Event'));
  page.add_menu_item(T('Planner settings', 'إعدادات المخطط'), () => frappe.set_route('Form', 'AlphaX POS Forecast Settings'));
  page.add_menu_item(T('Test local AI connection', 'اختبار اتصال الذكاء المحلي'), testAI);

  const $root = $(`<div class="axf ${AR ? 'axf-rtl' : ''}" dir="${AR ? 'rtl' : 'ltr'}"></div>`).appendTo(page.body);
  $(`<style>
    .axf{padding:12px 4px 60px;color:var(--text-color)}
    .axf-head{display:flex;flex-wrap:wrap;gap:24px;align-items:flex-end;margin-bottom:18px}
    .axf-total{font-size:44px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
    .axf-sub{color:var(--text-muted);font-size:13px;margin-top:6px}
    .axf-tags{display:flex;gap:6px;flex-wrap:wrap}
    .axf-tag{background:var(--bg-orange);color:var(--text-on-orange);border-radius:999px;padding:2px 10px;font-size:12px}
    .axf-kpi{min-width:120px}.axf-kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
    .axf-kpi span{font-size:12px;color:var(--text-muted)}
    .axf-week{display:grid;grid-template-columns:repeat(7,minmax(70px,1fr));gap:6px;margin-bottom:20px}
    .axf-day{border:1px solid var(--border-color);border-radius:10px;padding:8px;cursor:pointer;background:var(--card-bg)}
    .axf-day.on{border-color:var(--primary);box-shadow:0 0 0 1px var(--primary)}
    .axf-day small{display:block;color:var(--text-muted)} .axf-day b{font-size:16px;font-variant-numeric:tabular-nums}
    .axf-day i{display:block;font-style:normal;font-size:10px;color:var(--text-on-orange);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .axf-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px}
    @media(max-width:991px){.axf-grid{grid-template-columns:1fr}.axf-week{grid-template-columns:repeat(4,1fr)}}
    .axf-card{border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);padding:14px}
    .axf-card h4{font-size:14px;font-weight:600;margin:0 0 10px}
    .axf-t{width:100%;font-size:13px;border-collapse:collapse}
    .axf-t td,.axf-t th{padding:7px 6px;border-bottom:1px solid var(--border-color);vertical-align:top}
    .axf-t th{color:var(--text-muted);font-weight:500;text-align:start}
    .axf-n{text-align:end;font-variant-numeric:tabular-nums;white-space:nowrap}
    .axf-band{position:relative;height:6px;background:var(--gray-100);border-radius:3px;margin-top:6px;min-width:80px}
    .axf-band i{position:absolute;top:0;height:6px;background:var(--blue-200);border-radius:3px}
    .axf-band b{position:absolute;top:-2px;width:2px;height:10px;background:var(--blue-600)}
    .axf-why{color:var(--text-muted);font-size:12px}
    .axf-slot{font-weight:600;margin:12px 0 4px;font-size:13px}
    .axf-short{color:var(--red-600);font-weight:600}
    .axf-done{opacity:.45;text-decoration:line-through}
    .axf-brief{white-space:pre-wrap;font-size:14px;line-height:1.6}
    .axf-src{font-size:11px;color:var(--text-muted);margin-top:8px}
    .axf-empty{padding:40px;text-align:center;color:var(--text-muted)}
    @media print{.page-head,.axf-week,.axf-fc,.axf-brief-card,.navbar{display:none!important}.axf-grid{display:block}}
  </style>`).appendTo($root);
  const $body = $('<div></div>').appendTo($root);

  function call(method, args) {
    return frappe.call({ method: `${API}.${method}`, args, freeze: false }).then((r) => r.message);
  }

  function load() {
    return call('get_planner', { outlet: state.outlet, date: state.date }).then((d) => {
      state.data = d;
      if (!state.outlet && d.outlet) state.outlet = d.outlet;
      fOutlet.df.options = d.outlets; fOutlet.refresh(); fOutlet.set_value(d.outlet);
      btnRun.toggle(!!d.can_plan);
      render();
    });
  }

  function render() {
    const d = state.data;
    if (!d.outlet) { $body.html(`<div class="axf-empty">${T('Create an outlet first.', 'أنشئ منفذاً أولاً.')}</div>`); return; }
    const fc = d.forecast;
    const tags = (fc && fc.events ? fc.events.split(', ') : []).filter(Boolean);
    const acc = d.accuracy || {};
    let h = `<div class="axf-head">
      <div><div class="axf-total">${fc ? num(fc.total_forecast) : '—'}</div>
        <div class="axf-sub">${T('items expected', 'صنف متوقع')} · ${esc(frappe.datetime.str_to_user(d.date))} · ${esc(d.hijri || '')} ${T('AH', 'هـ')}</div></div>
      <div class="axf-tags">${tags.map((t) => `<span class="axf-tag">${esc(t)}</span>`).join('')}</div>
      <div class="axf-kpi"><b>${acc.days ? num(acc.wape, 1) + '%' : '—'}</b><span>${T('error, last', 'الخطأ، آخر')} ${acc.days || 0} ${T('days', 'يوماً')}</span></div>
      <div class="axf-kpi"><b>${acc.days ? (acc.bias > 0 ? '+' : '') + num(acc.bias, 1) + '%' : '—'}</b><span>${T('bias', 'الانحياز')}</span></div>
      <div class="axf-kpi"><b>${esc(fc ? fc.plan_to : '—')}</b><span>${T('prep planned to', 'التحضير حتى')}</span></div>
    </div>`;
    h += `<div class="axf-week">${weekStrip(d)}</div>`;
    if (!fc) {
      h += `<div class="axf-card axf-empty">${d.enabled ? T('No forecast for this day yet. Run the forecast, or wait for tonight’s run.', 'لا يوجد تنبؤ لهذا اليوم بعد. شغّل التنبؤ أو انتظر تشغيل الليلة.') : T('Forecasting is switched off in Planner settings.', 'التنبؤ متوقف في إعدادات المخطط.')}</div>`;
      $body.html(h); bindWeek(); return;
    }
    h += `<div class="axf-grid"><div class="axf-card axf-fc"><h4>${T('Forecast by item', 'التنبؤ حسب الصنف')}</h4>${itemTable(fc)}</div>
      <div><div class="axf-card axf-brief-card" style="margin-bottom:20px"><h4>${T('Briefing', 'الملخص')}</h4>
        <div class="axf-brief">${esc(fc.briefing || '')}</div><div class="axf-src">${esc(fc.briefing_source || '')}</div></div>
        <div class="axf-card"><h4>${T('Prep list', 'قائمة التحضير')}${d.prep ? ` · ${esc(d.prep.status)}` : ''}</h4>${prepList(d.prep)}</div></div></div>`;
    $body.html(h); bindWeek(); bindPrep();
  }

  function weekStrip(d) {
    const by = {}; (d.week || []).forEach((w) => (by[w.forecast_date] = w));
    let s = '';
    for (let i = 0; i < 7; i++) {
      const day = frappe.datetime.add_days(d.date, i), w = by[day];
      const lbl = moment(day).locale(AR ? 'ar' : 'en').format('ddd D');
      s += `<div class="axf-day ${i === 0 ? 'on' : ''}" data-day="${day}"><small>${esc(lbl)}</small><b>${w ? num(w.total_forecast) : '—'}</b><i>${esc((w && w.events) || '')}</i></div>`;
    }
    return s;
  }
  function bindWeek() { $body.find('.axf-day').on('click', function () { fDate.set_value($(this).data('day')); }); }

  function itemTable(fc) {
    const rows = fc.lines || [];
    if (!rows.length) return `<div class="axf-empty">${T('No items cleared the minimum. Check history and settings.', 'لا توجد أصناف فوق الحد الأدنى.')}</div>`;
    const max = Math.max(...rows.map((r) => r.high_qty || r.forecast_qty || 0), 1);
    return `<table class="axf-t"><thead><tr><th>${T('Item', 'الصنف')}</th><th class="axf-n">${T('Forecast', 'المتوقع')}</th><th class="axf-n">${T('Plan', 'الخطة')}</th><th class="axf-n">${T('Actual', 'الفعلي')}</th></tr></thead><tbody>${rows.map((r) => `
      <tr><td><div>${esc(r.item_name || r.item_code)}</div>
        <div class="axf-band" title="${num(r.low_qty)}–${num(r.high_qty)}"><i style="${AR ? 'right' : 'left'}:${(100 * r.low_qty) / max}%;width:${(100 * (r.high_qty - r.low_qty)) / max}%"></i><b style="${AR ? 'right' : 'left'}:${(100 * r.forecast_qty) / max}%"></b></div>
        <div class="axf-why">${esc(r.drivers || r.method || '')}${r.peak_slot ? ' · ' + T('busiest', 'الذروة') + ' ' + esc(r.peak_slot) : ''}</div></td>
        <td class="axf-n">${num(r.forecast_qty)}</td><td class="axf-n"><b>${num(r.planned_qty)}</b></td><td class="axf-n">${r.actual_qty ? num(r.actual_qty) : '—'}</td></tr>`).join('')}</tbody></table>`;
  }

  function prepList(p) {
    if (!p) return `<div class="axf-empty">${T('No prep plan yet. Build one from this forecast.', 'لا توجد خطة تحضير بعد.')}</div>`;
    const slotsAr = { Morning: 'الصباح', Lunch: 'الغداء', Evening: 'المساء' };
    let h = '', cur = null;
    (p.lines || []).forEach((l) => {
      if (l.prep_slot !== cur) { if (cur) h += '</tbody></table>'; cur = l.prep_slot;
        h += `<div class="axf-slot">${esc(AR ? slotsAr[cur] || cur : cur)}</div><table class="axf-t"><tbody>`; }
      h += `<tr class="${l.done ? 'axf-done' : ''}"><td style="width:22px"><input type="checkbox" data-line="${l.name}" ${l.done ? 'checked' : ''}></td>
        <td>${esc(l.material_item)}<div class="axf-why">${esc(l.station || '')}${l.for_items ? ' · ' + esc(l.for_items) : ''}</div></td>
        <td class="axf-n">${num(l.required_qty, 2)} ${esc(l.uom || '')}</td>
        <td class="axf-n ${l.shortfall_qty > 0 ? 'axf-short' : ''}">${l.shortfall_qty > 0 ? T('short ', 'نقص ') + num(l.shortfall_qty, 2) : T('in stock', 'متوفر')}</td></tr>`;
    });
    if (cur) h += '</tbody></table>';
    if (p.unrecipe_items) h += `<div class="axf-why" style="margin-top:10px">${T('No recipe: ', 'بدون وصفة: ')}${esc(p.unrecipe_items)}</div>`;
    if (p.material_request) h += `<div class="axf-why" style="margin-top:6px">${T('Material Request', 'طلب مواد')}: <a href="/app/material-request/${encodeURIComponent(p.material_request)}">${esc(p.material_request)}</a></div>`;
    return h;
  }
  function bindPrep() {
    $body.find('input[data-line]').on('change', function () {
      call('mark_prep_line', { prep_plan: state.data.prep.name, line: $(this).data('line'), done: this.checked ? 1 : 0 });
      $(this).closest('tr').toggleClass('axf-done', this.checked);
    });
  }

  function runNow() {
    const before = state.data && state.data.forecast ? state.data.forecast.generated_on : null;
    call('run_now', { outlet: state.outlet }).then(() => {
      frappe.show_alert({ message: T('Forecast running on this server…', 'التنبؤ يعمل على هذا الخادم…'), indicator: 'blue' });
      clearInterval(state.poll); let n = 0;
      state.poll = setInterval(() => {
        if (++n > 60) return clearInterval(state.poll);
        load().then(() => { const f = state.data.forecast; if (f && f.generated_on !== before) { clearInterval(state.poll); frappe.show_alert({ message: T('Forecast updated', 'تم تحديث التنبؤ'), indicator: 'green' }); } });
      }, 5000);
    });
  }
  function buildPrep(force) {
    call('build_prep', { outlet: state.outlet, date: state.date, force: force ? 1 : 0 })
      .then(() => { frappe.show_alert({ message: T('Prep plan built', 'تم إنشاء خطة التحضير'), indicator: 'green' }); load(); });
  }
  function createMR() {
    if (!state.data || !state.data.prep) return frappe.msgprint(T('Build the prep plan first.', 'أنشئ خطة التحضير أولاً.'));
    call('create_material_request', { prep_plan: state.data.prep.name }).then((mr) => {
      frappe.show_alert({ message: T('Material Request ', 'طلب مواد ') + mr, indicator: 'green' }); load();
    });
  }
  function testAI() {
    call('test_ai_connection').then((r) => frappe.msgprint({ title: T('Local AI', 'الذكاء المحلي'), message: esc(r.message), indicator: r.ok ? 'green' : 'red' }));
  }

  load();
};
