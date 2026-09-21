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

const BOOT_ORDER_TYPES = [
  { order_type_name: 'Dine In', icon: '🍽', sort_order: 10, is_default: 1,
    table_policy: 'Mandatory', prints_kot: 1, opens_tab: 1, requires_cover_count: 1 },
  { order_type_name: 'Takeaway', icon: '🥡', sort_order: 20,
    table_policy: 'Not Applicable', prints_kot: 1 },
  { order_type_name: 'Delivery', icon: '🛵', sort_order: 30,
    table_policy: 'Not Applicable', requires_delivery_platform: 1 },
  { order_type_name: 'Credit', icon: '📒', sort_order: 40,
    table_policy: 'Not Applicable', requires_customer: 1, posts_credit: 1 },
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
  ctx.AlphaXStores = {};
  const posMod = await loadESMAsObject('stores/pos.js');
  Object.assign(ctx.AlphaXStores, posMod);

  const pinia = ctx.Pinia.createPinia();
  ctx.Vue.createApp({}).use(pinia);
  ctx.Pinia.setActivePinia(pinia);
  const store = posMod.usePOSStore();

  // Floor-plan venue with the modes above.
  store.boot = {
    order_types: BOOT_ORDER_TYPES,
    features: { uses_floor_plan: true },
    outlet: { name: 'OUT-1' },
  };
  store.features.uses_floor_plan = true;

  check('modes come from the server', store.ORDER_TYPES.length === 4,
    store.ORDER_TYPES.join(', '));
  check('default mode is the flagged one', store.defaultOrderType === 'Dine In',
    store.defaultOrderType);

  store.setOrderType('Dine In');
  check('Dine In is mandatory-table', store.tablePolicy === 'Mandatory', store.tablePolicy);
  check('table chip is shown for Dine In', store.tableApplies === true);
  check('payment blocked with no table',
    store.blockingRequirements.includes('table'),
    JSON.stringify(store.blockingRequirements));

  store.setTable('T-12');
  check('table accepted for Dine In', store.activeTable === 'T-12', String(store.activeTable));
  check('cover count still required',
    store.blockingRequirements.includes('covers'),
    JSON.stringify(store.blockingRequirements));
  store.setCovers(4);
  check('clear to tender once seated and counted',
    store.blockingRequirements.length === 0,
    JSON.stringify(store.blockingRequirements));

  store.setOrderType('Takeaway');
  check('Takeaway hides the table chip', store.tableApplies === false, store.tablePolicy);
  check('switching to Takeaway releases the held table',
    store.activeTable === null, String(store.activeTable));
  check('Takeaway is clear to tender immediately',
    store.blockingRequirements.length === 0,
    JSON.stringify(store.blockingRequirements));

  store.setTable('T-9');
  check('a table cannot be attached to Takeaway',
    store.activeTable === null, String(store.activeTable));

  store.setOrderType('Delivery');
  check('Delivery needs a platform, not a table',
    store.blockingRequirements.includes('platform')
    && !store.blockingRequirements.includes('table'),
    JSON.stringify(store.blockingRequirements));

  store.setOrderType('Credit');
  check('Credit needs a named customer',
    store.blockingRequirements.includes('customer'),
    JSON.stringify(store.blockingRequirements));

  // A venue with no floor plan never asks, whatever the mode says.
  store.features.uses_floor_plan = false;
  store.boot.features.uses_floor_plan = false;
  store.setOrderType('Dine In');
  check('no floor plan means no table prompt',
    store.tablePolicy === 'Not Applicable'
    && !store.blockingRequirements.includes('table'),
    store.tablePolicy + ' / ' + JSON.stringify(store.blockingRequirements));

  // Legacy site: server sends no order_types at all.
  store.boot = { features: { uses_floor_plan: true } };
  store.features.uses_floor_plan = true;
  check('unmigrated site falls back to the five modes',
    store.ORDER_TYPES.length === 5 && store.ORDER_TYPES.includes('Dine In'),
    store.ORDER_TYPES.join(', '));
  store.setOrderType('Dine In');
  check('legacy Dine In stays optional (old behaviour preserved)',
    store.tablePolicy === 'Optional' && store.blockingRequirements.length === 0,
    store.tablePolicy);

  console.log(failures ? `\n${failures} failure(s)` : '\nservice-mode gate: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
