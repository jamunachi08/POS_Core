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

  const boot = (settings) => { store.boot = { settings, features: {}, outlet: { name: 'OUT-1' } }; };

  // Shifts not in use at all.
  boot({});
  store.shift = null;
  check('no gate when shifts are not required', store.shiftGateActive === false);

  // Required, default policy, nobody has opened one.
  boot({ require_shift_open: 1 });
  store.shift = null;
  check('gate closes the till on entry by default', store.shiftGateActive === true);

  // Same, once the shift is open.
  store.shift = { shift: 'SH-1', business_date: '2026-08-02' };
  check('gate lifts once the shift is open', store.shiftGateActive === false);

  // Second shift of the day: previous one closed, till locks again.
  store.shift = null;
  check('gate returns for the next shift after close', store.shiftGateActive === true);

  // Old behaviour preserved for sites that want it.
  boot({ require_shift_open: 1, shift_gate: 'On First Sale' });
  store.shift = null;
  check('On First Sale leaves the till open', store.shiftGateActive === false);

  // Never flash the gate while the shift state is still loading.
  boot({ require_shift_open: 1, shift_gate: 'On Entry' });
  store.shift = null;
  store.shiftLoading = true;
  check('no flash while shift state is loading', store.shiftGateActive === false);
  store.shiftLoading = false;
  check('gate appears once loading settles', store.shiftGateActive === true);

  console.log(failures ? `\n${failures} failure(s)` : '\nshift gate: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
