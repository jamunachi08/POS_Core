/**
 * AlphaX POS v3 Cashier — Frappe page wrapper.
 *
 * The v3 cashier UI is a Vue 3 SPA built with Tailwind + Headless UI,
 * loaded at runtime by an SFC loader (no Vite, no npm at deploy time).
 *
 * Loading sequence:
 *   1. Show a warming-up card immediately so the cashier never sees a
 *      blank screen.
 *   2. Load Vue + Pinia + vue-i18n from local vendor bundles (committed
 *      to the repo at v15.5.7+). CDN fallback if local fails.
 *   3. Load the precompiled Tailwind CSS.
 *   4. Load the SFC loader and the SPA bootstrap.
 *   5. The SPA takes over the viewport.
 *
 * If anything fails to load, we show a calm, two-language message
 * instead of a stack trace. The cashier should never see a developer
 * error.
 *
 * Why a separate folder (cashier_v3 vs cashier):
 *   v2 lives at /assets/.../cashier/. v3 lives at /assets/.../cashier_v3/.
 *   Parallel folders mean v2 and v3 never share assets, so v3 changes
 *   can never accidentally break v2.
 */

frappe.pages['alphax-pos-v3'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('AlphaX POS Cashier'),
        single_column: true,
    });

    const $main = $(page.main);

    // Hide Frappe chrome — the SPA owns the entire viewport
    $main.closest('.layout-main').addClass('alphax-v3-fullbleed');

    // Mount point + warming-up card
    $main.html(`
        <div id="alphax-pos-v3-app" style="position:fixed; inset:0; z-index:5; background:#FAF7F9;">
            <div class="alphax-v3-warmup">
                <div class="alphax-v3-warmup-card">
                    <div class="alphax-v3-warmup-spinner"></div>
                    <div class="alphax-v3-warmup-title">Starting AlphaX POS Cashier...</div>
                    <div class="alphax-v3-warmup-sub">جاري تشغيل نقطة البيع</div>
                </div>
            </div>
        </div>
    `);

    // Inject the warmup + fullbleed CSS (scoped to this page only)
    if (!document.getElementById('alphax-pos-v3-page-css')) {
        const style = document.createElement('style');
        style.id = 'alphax-pos-v3-page-css';
        style.textContent = `
            .alphax-v3-fullbleed .page-container { padding: 0 !important; max-width: none !important; }
            .alphax-v3-fullbleed .page-head { display: none !important; }
            .alphax-v3-fullbleed .layout-main-section-wrapper { padding: 0 !important; }
            .alphax-v3-fullbleed .layout-main-section { padding: 0 !important; }

            #alphax-pos-v3-app .alphax-v3-warmup {
                position: fixed; inset: 0;
                display: grid; place-items: center;
                background: #FAF7F9;
                color: #1F2937;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, sans-serif;
            }
            #alphax-pos-v3-app .alphax-v3-warmup-card {
                text-align: center; padding: 28px 36px;
                display: flex; flex-direction: column; align-items: center; gap: 14px;
            }
            #alphax-pos-v3-app .alphax-v3-warmup-spinner {
                width: 36px; height: 36px;
                border: 3px solid rgba(113, 75, 103, 0.10);
                border-top-color: #714B67;
                border-radius: 50%;
                animation: alphax-v3-spin 0.9s linear infinite;
            }
            @keyframes alphax-v3-spin { to { transform: rotate(360deg); } }
            #alphax-pos-v3-app .alphax-v3-warmup-title {
                font-size: 14px; color: #5C3D54; font-weight: 600;
            }
            #alphax-pos-v3-app .alphax-v3-warmup-sub {
                font-size: 13px; color: #9088A0;
            }
            #alphax-pos-v3-app .alphax-v3-error {
                position: fixed; inset: 0;
                display: grid; place-items: center;
                background: #FAF7F9;
                padding: 24px;
            }
            #alphax-pos-v3-app .alphax-v3-error-card {
                max-width: 480px; padding: 28px 32px;
                background: white;
                border: 1px solid #EAE5E9;
                border-radius: 12px;
                text-align: center;
            }
            #alphax-pos-v3-app .alphax-v3-error-icon { font-size: 32px; margin-bottom: 12px; }
            #alphax-pos-v3-app .alphax-v3-error-title {
                font-size: 16px; font-weight: 600; color: #1F2937; margin-bottom: 8px;
            }
            #alphax-pos-v3-app .alphax-v3-error-detail {
                font-size: 13px; color: #6B7280; margin-bottom: 4px;
            }
            #alphax-pos-v3-app .alphax-v3-error-detail-ar {
                font-size: 13px; color: #9088A0;
            }
        `;
        document.head.appendChild(style);
    }

    // Asset paths
    const VENDOR_BASE = '/assets/alphax_pos_suite/dist/vendor';
    const SPA_BASE = `${VENDOR_BASE}/cashier_v3`;

    // Vendor bundles: local first, CDN fallback. Versions match v2's
    // proven set; do NOT change without testing.
    const VUE_VERSION = '3.5.13';
    const PINIA_VERSION = '3.0.3';
    const VUE_I18N_VERSION = '9.14.0';

    const VENDOR_LOCAL = {
        vue: `${VENDOR_BASE}/vue.global.prod.js`,
        pinia: `${VENDOR_BASE}/pinia.iife.prod.js`,
        i18n: `${VENDOR_BASE}/vue-i18n.global.prod.js`,
    };
    const VENDOR_CDN = {
        vue: `https://cdn.jsdelivr.net/npm/vue@${VUE_VERSION}/dist/vue.global.prod.js`,
        pinia: `https://cdn.jsdelivr.net/npm/pinia@${PINIA_VERSION}/dist/pinia.iife.prod.js`,
        i18n: `https://cdn.jsdelivr.net/npm/vue-i18n@${VUE_I18N_VERSION}/dist/vue-i18n.global.prod.js`,
    };

    function loadScript(src, fallback) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.async = false;
            s.onload = () => resolve();
            s.onerror = () => {
                if (fallback) {
                    const s2 = document.createElement('script');
                    s2.src = fallback;
                    s2.async = false;
                    s2.onload = () => resolve();
                    s2.onerror = () => reject(new Error(`Failed to load ${src} and ${fallback}`));
                    document.head.appendChild(s2);
                } else {
                    reject(new Error(`Failed to load ${src}`));
                }
            };
            document.head.appendChild(s);
        });
    }

    function loadStyle(href) {
        return new Promise((resolve, reject) => {
            // If already loaded, skip
            if (document.querySelector(`link[href="${href}"]`)) return resolve();
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.onload = () => resolve();
            link.onerror = () => reject(new Error(`Failed to load ${href}`));
            document.head.appendChild(link);
        });
    }

    function showError(title, detail, detail_ar) {
        const mount = document.getElementById('alphax-pos-v3-app');
        if (!mount) return;
        mount.innerHTML = `
            <div class="alphax-v3-error">
                <div class="alphax-v3-error-card">
                    <div class="alphax-v3-error-icon">⚠</div>
                    <div class="alphax-v3-error-title">${title}</div>
                    <div class="alphax-v3-error-detail">${detail}</div>
                    ${detail_ar ? `<div class="alphax-v3-error-detail-ar">${detail_ar}</div>` : ''}
                </div>
            </div>
        `;
    }

    async function boot() {
        try {
            // Load vendor bundles (Vue, Pinia, vue-i18n)
            await loadScript(VENDOR_LOCAL.vue, VENDOR_CDN.vue);
            await loadScript(VENDOR_LOCAL.pinia, VENDOR_CDN.pinia);
            await loadScript(VENDOR_LOCAL.i18n, VENDOR_CDN.i18n);

            // Load Tailwind CSS (precompiled, committed to repo) + theme
            await loadStyle(`${SPA_BASE}/tailwind.css`);
            await loadStyle(`${SPA_BASE}/sfc/styles/theme.css`);

            // Load the SFC loader (exposes window.AlphaXSFC). v3 reuses
            // v2's loader file — it's a generic Vue SFC compiler.
            await loadScript(`${VENDOR_BASE}/cashier/sfc-loader.js`);

            // Load the SPA bootstrap (defines window.AlphaXV3SPA)
            await loadScript(`${SPA_BASE}/sfc/main.js`);

            // Bootstrap the SPA — this does its own component loading
            if (window.AlphaXV3SPA && window.AlphaXV3SPA.start) {
                await window.AlphaXV3SPA.start('#alphax-pos-v3-app', SPA_BASE);
            } else {
                throw new Error('AlphaXV3SPA.start is not defined — main.js failed to register itself');
            }
        } catch (err) {
            console.error('AlphaX POS v3 boot failed:', err);
            showError(
                "Couldn't start the cashier",
                err.message || String(err),
                'تعذر تشغيل نقطة البيع'
            );
        }
    }

    boot();
};
