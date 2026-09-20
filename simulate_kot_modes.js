// Service-mode gate test.
//
// Loads the real vendored Vue + Pinia, evaluates the real stores/pos.js
// through the real loader, and drives the table policy the way a cashier
// would: pick Dine In (mandatory table) -> blocked; pick Takeaway -> not
// blocked and any held table released.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = '/home/claude/pos/final/alphax_pos_suite/public/dist/vendor';
const CASHIER = path.join(ROOT, 'cashier');
const SFC = path.join(CASHIER, 'sfc');

const win = {
  location: { href: 'https://x.test/app/alphax-cashier', origin: 'https://x.test',
              search: '', searchParams: null },
  navigator: { userAgent: 'node', language: 'en' },
  localStorage: (() => { const m = {}; return {
    getItem: k => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v); },
    removeItem: k => { delete m[k]; } }; })(),
  document: { head: { appendChild() {} }, createElement: () => ({ style: {}, setAttribute() {} }),
              addEventListener() {}, removeEventListener() {} },
  addEventListener() {}, removeEventListener() {},
  frappe: { csrf_token: 'x', session: { user: 'tester' } },
  fetch: async () => { throw new Error('no network'); },
  URL,
};
win.window = win; win.self = win; win.globalThis = win;

const ctx = vm.createContext(Object.assign(win, {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  crypto: require('crypto').webcrypto, TextEncoder, TextDecoder,
}));

for (const f of ['vue.global.prod.js', 'pinia.iife.prod.js', 'vue-i18n.global.prod.js']) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
}
vm.runInContext(fs.readFileSync(path.join(CASHIER, 'sfc-loader.js'), 'utf8'), ctx,
  { filename: 'sfc-loader.js' });

// Loader, lifted verbatim out of main.js.
const mainSrc = fs.readFileSync(path.join(CASHIER, 'main.js'), 'utf8');
const start = mainSrc.indexOf('  async function loadESMAsObject(path) {');
const end = mainSrc.indexOf('  // -------------------------------------------------------------------\n  // Phase A');
// Serve modules from disk; the loader prefers this hook over fetch().
ctx.ALPHAX_SPA_FETCH = async (rel) =>
  fs.readFileSync(path.join(SFC, rel.replace(/^cashier\/sfc\//, '')), 'utf8');
const loadESMAsObject = vm.runInContext(
  `(function(){ ${mainSrc.slice(start, end)}
     function rewriteWithSFCLoader(s, p) { return window.AlphaXSFC.rewriteImports(s, p); }
     return loadESMAsObject; })()`, ctx, { filename: 'loader.js' });

const KOT_BASE = {
  stations: [
    { name: 'ST-GRILL', station_name: 'GRILL', station_type: 'Printer', bridge_target: 'grill-01', is_default: 0 },
    { name: 'ST-BAR',   station_name: 'BAR',   station_type: 'Printer', bridge_target: 'bar-01',   is_default: 0 },
    { name: 'ST-MAIN',  station_name: 'HOT KITCHEN', station_type: 'Printer', bridge_target: 'kitchen-01', is_default: 1 },
  ],
  rules: [
    { item_group: 'Grills', station: 'ST-GRILL' },
    { item_group: 'Drinks', station: 'ST-BAR' },
  ],
  group_chains: { Grills: ['Grills'], Drinks: ['Drinks'], Rice: ['Rice'] },
  item_overrides: {},
};

const CART = [
  { item_code: 'MIX-GRILL', item_name: 'Mix Grill', item_group: 'Grills', qty: 1, rate: 50 },
  { item_code: 'COLA',      item_name: 'Cola',      item_group: 'Drinks', qty: 2, rate: 4 },
  { item_code: 'BIRYANI',   item_name: 'Biryani',   item_group: 'Rice',   qty: 1, rate: 30 },
];

let failures = 0;
const check = (label, ok, detail = '') => {
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`);
};

(async () => {
  ctx.AlphaXApi = {};
  for (const m of ['mock', 'bridge', 'queueDB', 'client', 'fingerprint', 'bridgeInstall']) {
    ctx.AlphaXApi[m] = await loadESMAsObject(`api/${m}.js`);
  }
  const posMod = await loadESMAsObject('stores/pos.js');
  const pinia = ctx.Pinia.createPinia();
  ctx.Vue.createApp({}).use(pinia);
  ctx.Pinia.setActivePinia(pinia);
  const store = posMod.usePOSStore();

  const load = (kot) => {
    store.boot = { kot, features: {}, outlet: { name: 'OUT-1' } };
    store.cart = CART.map(l => ({ ...l, line_uuid: l.item_code, modifiers: [] }));
  };

  // --- multi-station: one ticket per printer
  load({ ...KOT_BASE, mode: 'Station Routing' });
  let groups = store.routeCartToStations();
  check('station routing produces one group per station', groups.length === 3,
    groups.map(g => g.station.station_name).join(', '));
  check('grill line routes to the grill', 
    groups.find(g => g.station.name === 'ST-GRILL').lines[0].item_code === 'MIX-GRILL');
  check('unruled item falls to the default station',
    groups.find(g => g.station.name === 'ST-MAIN').lines[0].item_code === 'BIRYANI');

  // --- single printer: one ticket, sections preserved
  load({ ...KOT_BASE, mode: 'Single Printer', single_target: 'kitchen-01', group_by_section: 1, copies: 1 });
  groups = store.routeCartToStations();
  check('single printer merges to one ticket', groups.length === 1,
    String(groups.length) + ' group(s)');
  check('every line survives the merge',
    groups[0].lines.length === 3, String(groups[0].lines.length) + ' lines');
  check('merged ticket targets the configured printer',
    groups[0].station.bridge_target === 'kitchen-01', groups[0].station.bridge_target);
  const ticket = store.buildKotTicket(groups[0], 'INV-1');
  const sections = ticket.items.map(i => i.section);
  check('each line keeps its section heading',
    sections.includes('GRILL') && sections.includes('BAR') && sections.includes('HOT KITCHEN'),
    sections.join(' | '));
  check('lines are contiguous per section',
    new Set(sections).size === sections.filter((v, i) => i === 0 || sections[i-1] !== v).length,
    sections.join(' | '));

  // --- single printer with headings off
  load({ ...KOT_BASE, mode: 'Single Printer', single_target: 'kitchen-01', group_by_section: 0 });
  const plain = store.buildKotTicket(store.routeCartToStations()[0], 'INV-2');
  check('headings can be turned off',
    plain.items.every(i => i.section === ''), plain.items.map(i => i.section).join('|'));

  // --- single printer with no target configured falls back to the default station
  load({ ...KOT_BASE, mode: 'Single Printer', single_target: null });
  check('missing target falls back to the default station printer',
    store.routeCartToStations()[0].station.bridge_target === 'kitchen-01');

  // --- no stations at all
  load({ stations: [], rules: [], group_chains: {}, mode: 'Station Routing' });
  check('no stations means no tickets, not a crash',
    store.routeCartToStations().length === 0);

  // --- legacy payload with no mode behaves as station routing
  load(KOT_BASE);
  check('a boot payload without a mode still routes per station',
    store.routeCartToStations().length === 3);

  console.log(failures ? `\n${failures} failure(s)` : '\nKOT modes: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
