/* Cross-check sim on happy-dom: does the phantom modal close reproduce? */
const fs = require('fs'); const path = require('path');
const { Window } = require('happy-dom');
const VENDOR = path.join(__dirname, 'alphax_pos_suite/public/dist/vendor');
const read = (p) => fs.readFileSync(path.join(VENDOR, p), 'utf8');

const w = new Window({ url: 'http://localhost/app/alphax-cashier?mock=1' });
const window = w; global.window = window;
window.document.body.innerHTML = '<header class="navbar"></header><div id="alphax-cashier-app"></div>';
window.console.error = (...a) => console.log('PAGE ERROR:', a.map(x => (x && x.stack) ? x.stack.split('\n')[0] : String(x)).join(' '));
window.console.warn = (...a) => console.log('PAGE WARN:', a.map(String).join(' ').slice(0, 250));
window.structuredClone = window.structuredClone || structuredClone;
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener(){}, removeListener(){} }));
if (!window.ResizeObserver) window.ResizeObserver = class { observe(){} disconnect(){} unobserve(){} };
window.indexedDB = window.indexedDB || { open: () => ({ onsuccess: null, onerror: null, onupgradeneeded: null }) };
window.localStorage.setItem('alphax_pos_terminal', 'TERM-DEMO');
window.fetch = async (url) => {
  const m = String(url).split('?')[0].match(/dist\/vendor\/(.+)$/);
  if (m && fs.existsSync(path.join(VENDOR, m[1])))
    return { ok: true, status: 200, text: async () => fs.readFileSync(path.join(VENDOR, m[1]), 'utf8') };
  return { ok: false, status: 404, text: async () => 'nf' };
};
const run = (rel) => window.eval(read(rel));
run('vue.global.prod.js'); run('pinia.iife.prod.js'); run('vue-i18n.global.prod.js');
run('cashier/sfc-loader.js'); run('cashier/main.js');

(async () => {
  const deadline = Date.now() + 60000; let shell = null;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 300));
    shell = window.document.querySelector('.cashier-shell');
    if (shell) break;
  }
  if (!shell) { console.log('HD FAIL: no shell:', (window.document.getElementById('alphax-cashier-app').textContent||'').slice(0,200)); process.exit(1); }
  console.log('HD BOOT OK');
  // wait for menu, click first item
  let card = null; const d2 = Date.now() + 20000;
  while (Date.now() < d2) { card = window.document.querySelector('button.item'); if (card) break; await new Promise(r => setTimeout(r, 250)); }
  if (!card) { console.log('HD: no item card'); process.exit(1); }
  console.log('HD CARD:', (card.textContent||'').trim().slice(0,30));
  card.click();
  await new Promise(r => setTimeout(r, 600));
  const modal = window.document.querySelector('.modal-backdrop');
  console.log('HD MODAL PRESENT:', !!modal);
  if (modal) {
    const oat = Array.from(modal.querySelectorAll('button')).find(b => /oat/i.test(b.textContent||''));
    if (oat) { const b4 = oat.className; oat.click(); await new Promise(r => setTimeout(r, 200));
      console.log('HD OPTION CLICK:', oat.className !== b4 ? 'REACTIVE' : 'dead'); }
    const add = Array.from(modal.querySelectorAll('button')).find(b => /add to order/i.test(b.textContent||''));
    console.log('HD confirm present:', !!add, add ? '| disabled=' + add.disabled : '');
    if (add) { add.click(); await new Promise(r => setTimeout(r, 400)); }
    console.log('HD CART LINES:', window.document.querySelectorAll('.lines .line').length);
    console.log('HD MODAL STILL OPEN:', !!window.document.querySelector('.modal-backdrop'));
  }
  // v15.8.0: KOT client-side routing — cappuccino (Hot Beverages →
  // Beverages chain) must route to Juice Bar per the mock rule.
  const kotRoute = window.eval(`(function(){ try {
    var s = window.__ALPHAX_PINIA__._s.get('pos');
    var groups = s.routeCartToStations();
    return groups.map(g => g.station.name + ':' + g.lines.length + ':' + g.lines.map(l=>l.item_name).join('+')).join(' | ') || 'NO GROUPS';
  } catch(e){ return 'ERR ' + e.message } })()`);
  console.log('HD KOT ROUTING:', kotRoute,
    kotRoute.startsWith('Hot Kitchen') ? '(override beats group rule: OK)' : '(OVERRIDE FAILED)');

  // v15.9.2: tax engine — inclusive compound math. Sheesha @115 gross,
  // tobacco 100% + VAT 15% on previous row, inclusive: net 50, fee 50,
  // VAT 15, total 115. Cappuccino @18 inclusive VAT-only: net 15.65.
  const taxCheck = window.eval(`(function(){
    var s = window.__ALPHAX_PINIA__._s.get('pos');
    var she = { item_code: 'SHE-01', qty: 1, rate: 115 };
    var lt = s.lineTax(she);
    return 'net=' + lt.net.toFixed(2) + ' parts=' + lt.parts.map(p=>p.label+':'+p.amount.toFixed(2)).join(',');
  })()`);
  console.log('HD TAX DEBUG:', window.eval(`(function(){
    var s = window.__ALPHAX_PINIA__._s.get('pos');
    var it = s.menuItems.find(i => i.item_code === 'SHE-01');
    var tpls = s.boot && s.boot.item_tax_templates;
    var rows = s.boot && s.boot.taxes;
    return 'item=' + JSON.stringify(it) + ' tplKeys=' + (tpls?Object.keys(tpls):null)
      + ' rows=' + (rows?rows.map(r=>r.account_head+':'+r.rate+':'+r.charge_type).join('|'):null);
  })()`));
  console.log('HD TAX SHEESHA:', taxCheck,
    /net=50\.00 parts=Tobacco fee:50\.00,VAT 15%:15\.00/.test(taxCheck) ? '(compound inclusive OK)' : '(MATH WRONG)');

  // v15.9.0: combos — Fixed adds directly; Customizable routing check
  const comboBtns = Array.from(window.document.querySelectorAll('.combo-card'));
  console.log('HD COMBOS VISIBLE:', comboBtns.length);
  const fixed = comboBtns.find(b => /Combo B/.test(b.textContent || ''));
  if (fixed) {
    fixed.click(); await new Promise(r => setTimeout(r, 400));
    const comboState = window.eval(`(function(){
      var s = window.__ALPHAX_PINIA__._s.get('pos');
      var l = s.cart.find(x => x.is_combo);
      if (!l) return 'NO COMBO LINE';
      var kot = s.routeCartToStations().map(g => g.station.name + ':' + g.lines.map(x=>x.item_name+(x.notes?'['+x.notes+']':'')).join('+')).join(' | ');
      return 'line=' + l.item_name + '@' + l.rate + ' comps=' + l.combo_components.length + ' || KOT: ' + kot;
    })()`);
    console.log('HD COMBO:', comboState);
  }

  // v15.7.13: sales history modal (view-only) — open, list, reprint btn
  const histBtn = Array.from(window.document.querySelectorAll('button'))
    .find(b => /sales history|سجل المبيعات/i.test((b.textContent || '') + ' ' + (b.getAttribute('title') || '')));
  console.log('HD HISTORY BTN:', !!histBtn);
  if (histBtn) {
    histBtn.click(); await new Promise(r => setTimeout(r, 900));
    const backs = window.document.querySelectorAll('.modal-backdrop');
    console.log('HD HISTORY MODAL OPEN:', backs.length,
      backs.length ? (backs[backs.length-1].querySelector('.modal-title')||{}).textContent : '-');
    const mb = backs[backs.length-1];
    if (mb) console.log('HD HISTORY BODY:', (mb.textContent || '').replace(/\s+/g,' ').slice(0, 160));
    const cards = window.document.querySelectorAll('.ih-card');
    console.log('HD HISTORY CARDS:', cards.length);
    if (!cards.length) {
      const err = window.document.querySelector('.ih-error, .ih-empty');
      console.log('HD HISTORY STATE:', err ? err.textContent.trim().slice(0, 120) : 'no state el');
    }
    const printBtn = window.document.querySelector('.ih-print');
    console.log('HD REPRINT BTN:', !!printBtn);
    const closeBtn = window.document.querySelector('.modal-close');
    if (closeBtn) { closeBtn.click(); await new Promise(r => setTimeout(r, 300)); }
  }

  const pay = window.document.querySelector('.pay-btn');
  console.log('HD PAY disabled:', pay ? pay.disabled : 'no btn');
  if (pay && !pay.disabled) {
    pay.click(); await new Promise(r => setTimeout(r, 400));
    console.log('HD PAYMENT DIALOG:', !!window.document.querySelector('.modal-backdrop'));
  }
  process.exit(0);
})().catch(e => { console.log('HD SIM ERROR:', e.stack ? e.stack.split('\n').slice(0,3).join(' | ') : e); process.exit(1); });
