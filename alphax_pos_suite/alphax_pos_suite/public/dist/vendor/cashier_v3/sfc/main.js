/*
 * AlphaX POS v3 — SPA bootstrap.
 *
 * Pattern adopted from v2's main.js (proven to work on Frappe Cloud).
 * Loads in this order:
 *   Phase A: API namespace      → window.AlphaXV3Api
 *   Phase B: Composables        → window.AlphaXV3Composables
 *   Phase C: Locales + i18n     → window.AlphaXV3Locales
 *   Phase D: Stores             → window.AlphaXV3Stores
 *   Phase E: Vue components     → loaded into AlphaXSFC.cache
 *   Phase F: Mount
 *
 * The v3- namespace prefix (AlphaXV3*) keeps us cleanly separate from
 * v2's globals (AlphaX*). Both cashiers can coexist on the same page
 * if needed without colliding.
 *
 * SFC loader: we use the same loader file as v2 — it's a generic Vue
 * SFC compiler. But we need to teach it our v3-specific globals; we
 * do that by monkey-patching its namespace-resolver before loading
 * any .vue files.
 */

(function () {
    'use strict';

    const SPA = {
        async start(rootSelector, baseUrl) {
            const root = document.querySelector(rootSelector);
            if (!root) throw new Error(`AlphaXV3SPA: mount "${rootSelector}" not found`);
            if (!window.Vue) throw new Error('Vue 3 is not loaded');
            if (!window.Pinia) throw new Error('Pinia is not loaded');
            if (!window.VueI18n) throw new Error('vue-i18n is not loaded');
            if (!window.AlphaXSFC) throw new Error('SFC loader is not loaded');

            const SPA_BASE = `${baseUrl}/sfc`;

            // Override the SFC loader's import resolver to use v3 namespaces
            _patchSFCLoaderForV3();

            // -- ESM-as-classic loader (same trick v2 uses) -------------
            async function loadESM(path) {
                const url = `${SPA_BASE}/${path}`;
                const r = await fetch(url);
                if (!r.ok) throw new Error(`Could not fetch ${url}: HTTP ${r.status}`);
                const source = await r.text();

                let body = window.AlphaXSFC.rewriteImports
                    ? window.AlphaXSFC.rewriteImports(source, path)
                    : source;

                body = body.replace(/export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                                    'const $1 = __exports.$1 =');
                body = body.replace(/export\s+let\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                                    'let $1 = __exports.$1 =');
                body = body.replace(/export\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)/g,
                                    'function $1');
                body = body.replace(/export\s+default\s+/g, '__exports.default = ');

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
                    return new Function(wrapped)();
                } catch (e) {
                    console.error(`v3 ESM load error in ${path}:`, e);
                    throw new Error(`Could not evaluate ${path}: ${e.message}`);
                }
            }

            // -- Phase A: API ----------------------------------------------
            window.AlphaXV3Api = {};
            for (const name of ['client', 'mock']) {
                window.AlphaXV3Api[name] = await loadESM(`api/${name}.js`);
            }

            // -- Phase B: Composables (Phase 2: empty, populated later)
            window.AlphaXV3Composables = {};

            // -- Phase C: Locales + i18n -----------------------------------
            const enModule = await loadESM('locales/en.js');
            const arModule = await loadESM('locales/ar.js');

            const LOCALES = [
                { code: 'en', label: 'English', dir: 'ltr', native: 'English' },
                { code: 'ar', label: 'Arabic',  dir: 'rtl', native: 'العربية' },
            ];

            function getStoredLocale() {
                try {
                    const stored = localStorage.getItem('alphax_v3_locale');
                    if (stored && LOCALES.find(l => l.code === stored)) return stored;
                } catch (e) {}
                return 'en';
            }
            function setStoredLocale(code) {
                try { localStorage.setItem('alphax_v3_locale', code); } catch (e) {}
            }
            function dirFor(code) {
                return (LOCALES.find(l => l.code === code) || LOCALES[0]).dir;
            }

            const i18n = window.VueI18n.createI18n({
                legacy: false,
                globalInjection: true,
                locale: getStoredLocale(),
                fallbackLocale: 'en',
                messages: { en: enModule.default, ar: arModule.default },
            });

            function applyLocale(code) {
                i18n.global.locale.value = code;
                setStoredLocale(code);
                document.documentElement.setAttribute('dir', dirFor(code));
                document.documentElement.setAttribute('lang', code);
            }

            window.AlphaXV3Locales = {
                LOCALES, i18n, applyLocale, getStoredLocale, setStoredLocale, dirFor,
            };

            applyLocale(getStoredLocale());

            // -- Phase D: Stores -------------------------------------------
            window.AlphaXV3Stores = {};
            for (const name of ['pos', 'catalog', 'shift', 'ui']) {
                const mod = await loadESM(`stores/${name}.js`);
                Object.assign(window.AlphaXV3Stores, mod);
            }

            // -- Phase E: Vue components -----------------------------------
            // Phase 2 ships with just App.vue (which shows a placeholder).
            // Later phases add the real component tree.
            await window.AlphaXSFC.loadAll(['App.vue'], SPA_BASE);
            const App = await window.AlphaXSFC.load('App.vue', SPA_BASE);

            // -- Phase F: Mount --------------------------------------------
            const app = window.Vue.createApp(App);
            const pinia = window.Pinia.createPinia();
            app.use(pinia);
            app.use(i18n);

            root.innerHTML = '';
            app.mount(root);

            console.info('AlphaX POS v3: SPA mounted (Phase 2 — foundation only)');
        },
    };

    /**
     * The SFC loader was written for v2's namespace names (AlphaXStores,
     * AlphaXApi, etc.). For v3 we want AlphaXV3Stores, AlphaXV3Api, etc.
     * Rather than fork the loader, we wrap its rewriteImports to rename
     * the namespace references in the rewritten output.
     */
    function _patchSFCLoaderForV3() {
        if (!window.AlphaXSFC || !window.AlphaXSFC.rewriteImports) return;
        if (window.AlphaXSFC.__v3_patched) return;
        const original = window.AlphaXSFC.rewriteImports;
        window.AlphaXSFC.rewriteImports = function (source, filename) {
            const rewritten = original.call(window.AlphaXSFC, source, filename);
            return rewritten
                .replace(/window\.AlphaXStores/g, 'window.AlphaXV3Stores')
                .replace(/window\.AlphaXApi/g, 'window.AlphaXV3Api')
                .replace(/window\.AlphaXComposables/g, 'window.AlphaXV3Composables')
                .replace(/window\.AlphaXLocales/g, 'window.AlphaXV3Locales');
        };
        window.AlphaXSFC.__v3_patched = true;
    }

    window.AlphaXV3SPA = SPA;
})();
