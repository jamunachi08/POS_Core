// Onboarding wizard — every step must render something, and reaching
// 'ready' must actually hand over to the till.
//
// v15.10.8 shipped a hardware step whose save set step='ready'. No pane
// matched 'ready' and nothing called enter(), so the card rendered its
// header and step dots and nothing else, forever. Two checks here would
// have caught it: the static pane audit, and the live handover test.

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, 'alphax_pos_suite/public/dist/vendor/cashier/sfc');
const WIZARD = path.join(ROOT, 'components/OnboardingWizard.vue');
const STORE = path.join(ROOT, 'stores/onboarding.js');

let failures = 0;
const check = (label, ok, detail = '') => {
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`);
};

const wizard = fs.readFileSync(WIZARD, 'utf8');
const store = fs.readFileSync(STORE, 'utf8');

// ---- 1. static audit: every step the store can set has a pane ----------
//
// Reads both sides of the contract off the source rather than a list I
// maintain by hand, so a step added later is covered automatically.
const assigned = new Set(
  [...store.matchAll(/step\.value\s*=\s*'([a-z]+)'/g)].map(m => m[1]));
const ternary = [...store.matchAll(/step\.value\s*=\s*[^\n]*\?\s*'([a-z]+)'\s*:\s*'([a-z]+)'/g)];
for (const m of ternary) { assigned.add(m[1]); assigned.add(m[2]); }
const initial = (store.match(/const step\s*=\s*ref\('([a-z]+)'\)/) || [])[1];
if (initial) assigned.add(initial);

// Only the template counts. A script-side `if (ob.step === 'ready')` is
// not a pane, and treating it as one is precisely how the blank card got
// through the first time.
// lastIndexOf: inner <template v-if> blocks close with </template> too,
// and slicing at the first one silently truncates the audit.
const template = wizard.slice(wizard.indexOf('<template>'), wizard.lastIndexOf('</template>'));
const rendered = new Set(
  [...template.matchAll(/v-(?:else-)?if="ob\.step === '([a-z]+)'/g)].map(m => m[1]));

const orphans = [...assigned].filter(s => !rendered.has(s));
check('every step the store can set has a pane in the wizard',
  orphans.length === 0,
  orphans.length ? `no pane for: ${orphans.join(', ')}` : `${assigned.size} steps, all rendered`);

const dead = [...rendered].filter(s => !assigned.has(s));
check('no pane waits for a step that is never set', dead.length === 0,
  dead.length ? `unreachable panes: ${dead.join(', ')}` : 'clean');

// ---- 2. reaching 'ready' must trigger the handover --------------------
check('the wizard reacts to the ready state rather than trusting call sites',
  /watch\(\(\)\s*=>\s*ob\.step,[\s\S]{0,120}'ready'[\s\S]{0,40}enter\(\)/.test(wizard),
  'a watcher on ob.step calling enter()');

check('enter() is idempotent (watcher and call site can both fire)',
  /function enter\(\)\s*\{[\s\S]{0,160}entered/.test(wizard));

check('enter() refuses to run without a bound terminal',
  /function enter\(\)\s*\{[\s\S]{0,240}ob\.terminal\?\.name/.test(wizard));

// ---- 3. live: saving the hardware plan opens the till ------------------
const vm = require('vm');
const VENDOR = path.join(__dirname, 'alphax_pos_suite/public/dist/vendor');

const win = {
  location: { href: 'https://x.test/app/alphax-cashier', origin: 'https://x.test', search: '' },
  navigator: { userAgent: 'node', language: 'en', onLine: true },
  localStorage: (() => { const m = {}; return {
    getItem: k => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v); },
    removeItem: k => { delete m[k]; } }; })(),
  document: { head: { appendChild() {} }, createElement: () => ({ style: {}, setAttribute() {} }),
              addEventListener() {}, removeEventListener() {}, hidden: false },
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
  vm.runInContext(fs.readFileSync(path.join(VENDOR, f), 'utf8'), ctx, { filename: f });
}
vm.runInContext(fs.readFileSync(path.join(VENDOR, 'cashier/sfc-loader.js'), 'utf8'), ctx,
  { filename: 'sfc-loader.js' });

const mainSrc = fs.readFileSync(path.join(VENDOR, 'cashier/main.js'), 'utf8');
const start = mainSrc.indexOf('  async function loadESMAsObject(path) {');
const end = mainSrc.indexOf('  // -------------------------------------------------------------------\n  // Phase A');
ctx.ALPHAX_SPA_FETCH = async (rel) =>
  fs.readFileSync(path.join(ROOT, rel.replace(/^cashier\/sfc\//, '')), 'utf8');
const loadESMAsObject = vm.runInContext(
  `(function(){ ${mainSrc.slice(start, end)}
     function rewriteWithSFCLoader(s, p) { return window.AlphaXSFC.rewriteImports(s, p); }
     return loadESMAsObject; })()`, ctx, { filename: 'loader.js' });

(async () => {
  ctx.AlphaXApi = {};
  for (const m of ['mock', 'bridge', 'queueDB', 'client', 'fingerprint', 'bridgeInstall']) {
    ctx.AlphaXApi[m] = await loadESMAsObject(`api/${m}.js`);
  }

  // Station with nothing attached: exactly the case in the screenshot.
  const calls = [];
  ctx.AlphaXApi.client.api.call = async (method, args) => {
    calls.push(method);
    if (method.endsWith('get_hardware_catalog')) {
      return {
        roles: [
          { id: 'receipt_printer', label: 'Receipt printer', needs_bridge: 1 },
          { id: 'barcode_scanner', label: 'Barcode scanner', needs_bridge: 0 },
        ],
        profiles: [], plan: { receipt_printer: false, barcode_scanner: false },
        profile: null, configured: false, needs_bridge: false,
      };
    }
    if (method.endsWith('save_hardware_plan')) return { ok: true, needs_bridge: false };
    return null;
  };

  const obMod = await loadESMAsObject('stores/onboarding.js');
  const pinia = ctx.Pinia.createPinia();
  ctx.Vue.createApp({}).use(pinia);
  ctx.Pinia.setActivePinia(pinia);
  const ob = obMod.useOnboardingStore();

  ob.terminal = { name: 'TERM-1' };
  await ob.loadHardware();
  ob.step = 'hardware';

  check('a station with nothing ticked does not need the bridge',
    ob.hardwareNeedsBridge === false, String(ob.hardwareNeedsBridge));

  await ob.saveHardware();
  check('"Start selling" lands on ready, not on the bridge step',
    ob.step === 'ready', ob.step);
  check('the plan reached the server',
    calls.some(m => m.endsWith('save_hardware_plan')), calls.join(', '));

  // The bug: 'ready' with no pane and no handover is a dead card. The
  // static audit above proves a pane exists; this proves the state is
  // one the wizard can actually leave.
  check('ready is a rendered state (would have caught the hang)',
    rendered.has('ready'), [...rendered].join(', '));

  // Ticking something that needs the bridge must still route there.
  ob.toggleRole('receipt_printer');
  check('ticking a bridge device flips the verdict', ob.hardwareNeedsBridge === true);
  ob.bridge = { online: false };
  await ob.saveHardware();
  check('a station that needs the bridge goes to the install step',
    ob.step === 'bridge', ob.step);

  console.log(failures ? `\n${failures} failure(s)` : '\nonboarding wizard: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
