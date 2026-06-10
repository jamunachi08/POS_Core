/**
 * AlphaX POS Cashier — bootstrap.
 *
 * This file runs LAST in the loader chain:
 *   1. Vue, Pinia, VueI18n loaded as globals
 *   2. sfc-loader.js loaded (exposes window.AlphaXSFC)
 *   3. main.js (this file) loaded
 *
 * Responsibilities:
 *   - Build window.AlphaXApi (bridge, queueDB, client, mock) by fetching
 *     and evaluating each api/*.js file as classic script
 *   - Build window.AlphaXComposables (haptics, useLongPress, useMoney, modifiers)
 *   - Build window.AlphaXLocales (i18n instance + applyLocale + ...)
 *   - Build window.AlphaXStores (every Pinia store factory)
 *   - Load every .vue component via AlphaXSFC.loadAll
 *   - Apply locale, mount the app
 *
 * The .js files in stores/, api/, composables/, locales/ are fetched at
 * runtime just like .vue files. Each is wrapped in a function that
 * captures its exports into the appropriate global namespace.
 */

(async function () {
  'use strict';

  const SPA_BASE = '/assets/alphax_pos_suite/dist/vendor/cashier/sfc';

  // -------------------------------------------------------------------
  // ESM-source loader — fetches a JS file and evaluates it in a sandbox
  // that turns its `import`s into global lookups and captures its
  // `export`s into a returned object.
  // -------------------------------------------------------------------

  async function loadESMAsObject(path) {
    const url = `${SPA_BASE}/${path}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`Could not fetch ${url}: HTTP ${r.status}`);
    const source = await r.text();

    // Use the same import-rewriter as the SFC loader.
    const rewritten = window.AlphaXSFC.rewriteImports
      ? rewriteWithSFCLoader(source, path)
      : source;

    // Replace `export const X = ...`, `export function X() {}`,
    // `export default ...` with assignments to a local __exports object.
    let body = rewritten;
    body = body.replace(/export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                        'const $1 = __exports.$1 =');
    body = body.replace(/export\s+let\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                        'let $1 = __exports.$1 =');
    body = body.replace(/export\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)/g,
                        'function $1'); // we re-export at end via a hoist scan
    body = body.replace(/export\s+default\s+/g, '__exports.default = ');

    // Find function declarations created by the export-function rule
    // so we can re-attach them to __exports.
    const fnNames = [];
    const fnRe = /^function\s+([A-Za-z_$][A-Za-z0-9_$]*)/gm;
    let mm;
    while ((mm = fnRe.exec(body))) fnNames.push(mm[1]);
    const tail = fnNames.length
      ? '\n' + fnNames.map(n => `__exports.${n} = ${n};`).join('\n')
      : '';

    const wrapped = `
      const __exports = {};
      ${body}
      ${tail}
      return __exports;
    `;
    try {
      const factory = new Function(wrapped);
      return factory();
    } catch (e) {
      console.error(`ESM load error in ${path}:\n`, e, '\nWrapped source:\n', wrapped.slice(0, 2000));
      throw new Error(`Could not evaluate ${path}: ${e.message}`);
    }
  }

  function rewriteWithSFCLoader(source, path) {
    // The SFC loader's rewriter expects a "filename" for resolving
    // relative .vue imports. .js files don't import .vue files (they
    // import other .js or 'vue' or 'pinia' etc), so any path works.
    return window.AlphaXSFC.rewriteImports(source, path);
  }


  // -------------------------------------------------------------------
  // Phase A: API namespace
  // -------------------------------------------------------------------

  window.AlphaXApi = {};
  for (const name of ['bridge', 'client', 'mock', 'queueDB']) {
    try {
      window.AlphaXApi[name] = await loadESMAsObject(`api/${name}.js`);
    } catch (e) {
      console.error(`Failed to load api/${name}.js:`, e);
      throw e;
    }
  }


  // -------------------------------------------------------------------
  // Phase B: Composables namespace
  // -------------------------------------------------------------------

  window.AlphaXComposables = {};
  for (const name of ['haptics', 'useLongPress', 'useMoney', 'modifiers']) {
    try {
      const mod = await loadESMAsObject(`composables/${name}.js`);
      Object.assign(window.AlphaXComposables, mod);
    } catch (e) {
      console.error(`Failed to load composables/${name}.js:`, e);
      throw e;
    }
  }


  // -------------------------------------------------------------------
  // Phase C: Locales namespace
  // -------------------------------------------------------------------

  // Locales are special: en.js and ar.js have no imports; they `export
  // default` an object of translation keys. locales/index.js imports
  // them and creates the i18n instance.
  const enModule = await loadESMAsObject('locales/en.js');
  const arModule = await loadESMAsObject('locales/ar.js');

  // We build the i18n instance directly here to avoid having locales/index.js
  // try to import its sibling files (which our resolver would handle but
  // is more fragile). The shape mirrors the original locales/index.js.
  const LOCALES = [
    { code: 'en', label: 'English', dir: 'ltr', native: 'English' },
    { code: 'ar', label: 'Arabic',  dir: 'rtl', native: 'العربية' },
  ];

  function getStoredLocale() {
    const stored = localStorage.getItem('alphax_locale');
    if (stored && LOCALES.find(l => l.code === stored)) return stored;
    const nav = (navigator.language || 'en').slice(0, 2);
    if (LOCALES.find(l => l.code === nav)) return nav;
    return 'en';
  }
  function setStoredLocale(code) { localStorage.setItem('alphax_locale', code); }
  function dirFor(code) {
    return (LOCALES.find(l => l.code === code) || LOCALES[0]).dir;
  }

  const i18n = window.VueI18n.createI18n({
    legacy: false,
    globalInjection: true,
    locale: getStoredLocale(),
    fallbackLocale: 'en',
    messages: { en: enModule.default, ar: arModule.default },
    numberFormats: {
      en: {
        currency: { style: 'currency', currency: 'USD', currencyDisplay: 'symbol' },
        decimal:  { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 },
        integer:  { style: 'decimal', maximumFractionDigits: 0 },
      },
      ar: {
        currency: { style: 'currency', currency: 'USD', currencyDisplay: 'symbol' },
        decimal:  { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 },
        integer:  { style: 'decimal', maximumFractionDigits: 0 },
      },
    },
  });

  function applyLocale(code) {
    i18n.global.locale.value = code;
    setStoredLocale(code);
    document.documentElement.setAttribute('dir', dirFor(code));
    document.documentElement.setAttribute('lang', code);
  }

  window.AlphaXLocales = {
    LOCALES, i18n, applyLocale, getStoredLocale, setStoredLocale, dirFor,
  };

  // Apply locale + dir BEFORE first paint.
  applyLocale(getStoredLocale());


  // -------------------------------------------------------------------
  // Phase D: Stores namespace
  // -------------------------------------------------------------------

  // Pinia stores have to be defined AFTER we have a Pinia instance bound
  // to the app. But each defineStore call is itself just a factory that
  // gets activated on first use(). So we can collect the factories now
  // and they activate when components call useFooStore().
  window.AlphaXStores = {};
  for (const name of ['pos', 'hardware', 'sync', 'kiosk']) {
    try {
      const mod = await loadESMAsObject(`stores/${name}.js`);
      Object.assign(window.AlphaXStores, mod);
    } catch (e) {
      console.error(`Failed to load stores/${name}.js:`, e);
      throw e;
    }
  }


  // -------------------------------------------------------------------
  // Phase E: Vue components
  // -------------------------------------------------------------------

  // Load every .vue file. Order matters when components import each
  // other — children must be in the cache when parents try to resolve
  // them. We load the leaf-level components first, then composite ones,
  // then App.vue last.
  const COMPONENTS_LEAF = [
    'components/AppModal.vue',
    'components/NumericKeypad.vue',
    'components/Toaster.vue',
    'components/LocaleSwitch.vue',
    'components/HardwarePill.vue',
    'components/SyncPill.vue',
    'components/KioskToggle.vue',
    'components/CartLineActions.vue',
    'components/ContextRibbon.vue',
  ];
  const COMPONENTS_MID = [
    'components/HardwareSettings.vue',
    'components/QueueInspector.vue',
    'components/CustomerPicker.vue',
    'components/TablePicker.vue',
    'components/ModifierPicker.vue',
    'components/HeldOrders.vue',
    'components/SplitBill.vue',
    'components/LoyaltyScan.vue',
    'components/RxCapture.vue',
    'components/BootScreen.vue',
  ];
  const COMPONENTS_TOP = [
    'components/MenuPanel.vue',
    'components/CartPanel.vue',
    'components/PaymentDialog.vue',
    'components/SidebarPanel.vue',
    'views/CashierView.vue',
    'App.vue',
  ];

  await window.AlphaXSFC.loadAll(COMPONENTS_LEAF);
  await window.AlphaXSFC.loadAll(COMPONENTS_MID);
  await window.AlphaXSFC.loadAll(COMPONENTS_TOP);

  const App = await window.AlphaXSFC.load('App.vue');


  // -------------------------------------------------------------------
  // Phase F: Mount
  // -------------------------------------------------------------------

  const app = window.Vue.createApp(App);
  const pinia = window.Pinia.createPinia();
  app.use(pinia);
  app.use(i18n);

  // Register all components globally so templates can refer to them
  // by name without needing a local `import`.
  for (const path of [...COMPONENTS_LEAF, ...COMPONENTS_MID, ...COMPONENTS_TOP]) {
    const name = path.split('/').pop().replace(/\.vue$/, '');
    if (name === 'App' || name === 'CashierView') continue;
    const comp = window.AlphaXSFC.cache[path];
    if (comp) app.component(name, comp);
  }
  app.component('CashierView', window.AlphaXSFC.cache['views/CashierView.vue']);

  // Install kiosk guards once globally.
  if (window.AlphaXStores.useKioskStore) {
    const kiosk = window.AlphaXStores.useKioskStore(pinia);
    if (kiosk.installGuards) kiosk.installGuards();
    if (kiosk.on) document.body.classList.add('alphax-kiosk-on');
  }

  // Boot the offline-sync worker.
  if (window.AlphaXStores.useSyncStore) {
    const sync = window.AlphaXStores.useSyncStore(pinia);
    if (sync.bindConnectivity) sync.bindConnectivity();
    if (sync.startBackgroundSync) sync.startBackgroundSync(15000);
    if (sync.refreshCounts) sync.refreshCounts();
    if (sync.online && sync.drain) sync.drain().catch(() => {});
  }

  // Replace the warm-up card and mount.
  const mountEl = document.getElementById('alphax-cashier-app');
  if (!mountEl) throw new Error('AlphaX cashier mount point not found.');
  mountEl.innerHTML = '';   // clear warm-up card
  app.mount('#alphax-cashier-app');

})().catch((err) => {
  console.error('AlphaX cashier failed to boot:', err);
  // Trigger the loader's error path by re-throwing, but we already
  // unwrapped that promise — show a basic fallback.
  const mountEl = document.getElementById('alphax-cashier-app');
  if (mountEl) {
    mountEl.innerHTML = `
      <div style="position:fixed; inset:0; display:grid; place-items:center;
                  background:#fafafa; font-family:-apple-system,sans-serif;
                  padding:20px;">
        <div style="background:#fff; border:1px solid #e5e7eb; border-radius:14px;
                    padding:28px 32px; max-width:480px;
                    box-shadow:0 4px 16px rgba(0,0,0,0.06);">
          <div style="font-size:30px; margin-bottom:8px;">⚠️</div>
          <h2 style="font-size:17px; font-weight:600; margin:0 0 6px;">
            The cashier UI couldn't start.
          </h2>
          <p style="font-size:13px; color:#555; line-height:1.55; margin:0 0 14px;">
            Please refresh the page. If the problem continues, check the browser
            console and contact your administrator.
          </p>
          <pre style="font-size:11px; color:#a02020; background:#fef0f0;
                      padding:8px 12px; border-radius:6px; overflow:auto;
                      max-height:120px; margin:0;">${String(err && err.message || err).replace(/[<>&]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</pre>
        </div>
      </div>
    `;
  }
});
