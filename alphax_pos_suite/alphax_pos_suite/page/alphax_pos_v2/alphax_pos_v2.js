/**
 * AlphaX POS Cashier — Frappe page wrapper.
 *
 * The cashier UI is a Vue 3 SPA. It loads in three phases:
 *
 *   1. Show the "warming up..." card immediately so the cashier never
 *      stares at a blank screen.
 *   2. Load Vue + Pinia + vue-i18n. We try the locally-installed
 *      vendor bundles first (offline-capable, instant), then fall
 *      back to a CDN if the local files are missing.
 *   3. Boot the SPA, which then takes over the entire viewport.
 *
 * No npm. No vite. No build step. Ever.
 *
 * If something goes wrong we show a calm message in two languages,
 * not a stack trace. The cashier should never see anything that looks
 * like a developer error.
 */

frappe.pages['alphax-pos-v2'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('AlphaX POS'),
        single_column: true,
    });

    const $main = $(page.main);

    // Hide Frappe chrome — the SPA owns the entire viewport.
    $main.closest('.layout-main').addClass('alphax-cashier-fullbleed');

    $main.html(`
        <div id="alphax-cashier-app" style="position:fixed; inset:0; z-index:5; background:#fafafa;"></div>
    `);

    if (!document.getElementById('alphax-cashier-page-css')) {
        const style = document.createElement('style');
        style.id = 'alphax-cashier-page-css';
        style.textContent = `
            .alphax-cashier-fullbleed .page-container { padding: 0 !important; max-width: none !important; }
            .alphax-cashier-fullbleed .page-head { display: none !important; }
            .alphax-cashier-fullbleed .layout-main-section-wrapper { padding: 0 !important; }
            .alphax-cashier-fullbleed .layout-main-section { padding: 0 !important; }

            #alphax-cashier-app .alphax-warmup {
                position: fixed; inset: 0; display: grid; place-items: center;
                background: #fafafa; color: #111;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
            }
            #alphax-cashier-app .alphax-warmup-card {
                text-align: center; padding: 28px 36px;
                display: flex; flex-direction: column; align-items: center; gap: 14px;
            }
            #alphax-cashier-app .alphax-warmup-spinner {
                width: 36px; height: 36px;
                border: 3px solid rgba(0,0,0,0.08);
                border-top-color: #0F6E56;
                border-radius: 50%;
                animation: alphax-spin 0.9s linear infinite;
            }
            @keyframes alphax-spin { to { transform: rotate(360deg); } }
            #alphax-cashier-app .alphax-warmup-title {
                font-size: 16px; font-weight: 600; margin: 0;
            }
            #alphax-cashier-app .alphax-warmup-sub {
                font-size: 13px; color: #6b6a65; margin: 0;
            }
            #alphax-cashier-app .alphax-warmup-banner {
                font-size: 12px; color: #b86a00;
                background: #fef6e6; border: 1px solid #f5e0a8;
                padding: 8px 14px; border-radius: 8px; max-width: 420px;
            }
            #alphax-cashier-app .alphax-error-card {
                background: #fff; border: 1px solid #e5e7eb; border-radius: 14px;
                padding: 28px 32px; max-width: 480px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.06);
                text-align: start;
            }
            #alphax-cashier-app .alphax-error-icon {
                font-size: 30px; margin-bottom: 8px;
            }
            #alphax-cashier-app .alphax-error-title {
                font-size: 17px; font-weight: 600; margin: 0 0 6px;
            }
            #alphax-cashier-app .alphax-error-body {
                font-size: 13px; color: #555; line-height: 1.55; margin: 0 0 14px;
            }
            #alphax-cashier-app .alphax-error-action {
                font-size: 12px; color: #0F6E56;
                background: #e8f5f0; padding: 8px 12px; border-radius: 6px;
                font-family: 'SF Mono', Menlo, monospace;
                word-break: break-all;
            }
            #alphax-cashier-app .alphax-error-retry {
                margin-top: 18px;
                background: #0F6E56; color: #fff;
                border: 0; border-radius: 8px;
                padding: 10px 22px;
                font-size: 13px; font-weight: 500;
                cursor: pointer;
                transition: background 0.15s;
            }
            #alphax-cashier-app .alphax-error-retry:hover {
                background: #0a5040;
            }
        `;
        document.head.appendChild(style);
    }

    // Phase 1: warm-up card. Visible within ~50ms of page load.
    const $app = $main.find('#alphax-cashier-app');
    showWarmup($app, false);

    // Phase 2 + 3: load vendor bundles, then boot the SPA.
    bootCashier($app).catch((err) => {
        console.error('AlphaX cashier boot failed:', err);
        showError($app, err);
    });
};


// ---------------------------------------------------------------------------
// Warm-up card
// ---------------------------------------------------------------------------

function showWarmup($app, usingFallback) {
    const banner = usingFallback
        ? `<div class="alphax-warmup-banner">
             First-time setup: downloading the cashier UI. Future loads will be instant.
           </div>`
        : '';
    $app.html(`
        <div class="alphax-warmup">
            <div class="alphax-warmup-card">
                <div class="alphax-warmup-spinner"></div>
                <h2 class="alphax-warmup-title">Warming up the register…</h2>
                <p class="alphax-warmup-sub">جارٍ التحضير…</p>
                ${banner}
            </div>
        </div>
    `);
}


// ---------------------------------------------------------------------------
// Boot — local vendor first, CDN fallback, then SPA
// ---------------------------------------------------------------------------

const VENDOR_LOCAL_BASE = '/assets/alphax_pos_suite/dist/vendor';
const SPA_LOCAL_BASE    = '/assets/alphax_pos_suite/dist/vendor/cashier';

// Pinned versions — must match cashier/vendor.py BUNDLES.
const VUE_VERSION      = '3.5.13';
const PINIA_VERSION    = '3.0.3';
const VUE_I18N_VERSION = '9.14.0';

const VENDOR_BUNDLES = [
    {
        global: 'Vue',
        local:  `${VENDOR_LOCAL_BASE}/vue.global.prod.js`,
        cdns:   [
            `https://unpkg.com/vue@${VUE_VERSION}/dist/vue.global.prod.js`,
            `https://cdn.jsdelivr.net/npm/vue@${VUE_VERSION}/dist/vue.global.prod.js`,
            `https://cdnjs.cloudflare.com/ajax/libs/vue/${VUE_VERSION}/vue.global.prod.min.js`,
        ],
    },
    {
        global: 'Pinia',
        local:  `${VENDOR_LOCAL_BASE}/pinia.iife.prod.js`,
        cdns:   [
            `https://unpkg.com/pinia@${PINIA_VERSION}/dist/pinia.iife.prod.js`,
            `https://cdn.jsdelivr.net/npm/pinia@${PINIA_VERSION}/dist/pinia.iife.prod.js`,
        ],
    },
    {
        global: 'VueI18n',
        local:  `${VENDOR_LOCAL_BASE}/vue-i18n.global.prod.js`,
        cdns:   [
            `https://unpkg.com/vue-i18n@${VUE_I18N_VERSION}/dist/vue-i18n.global.prod.js`,
            `https://cdn.jsdelivr.net/npm/vue-i18n@${VUE_I18N_VERSION}/dist/vue-i18n.global.prod.js`,
        ],
    },
];


async function bootCashier($app) {
    // Step 1: ask the server whether vendor bundles are present locally.
    // This is a HINT, not a gate — we'll try the local files anyway, because
    // they might be there even if vendor_status couldn't be reached (e.g.
    // path issues, slow Redis, transient errors). Don't punish the user
    // for our backend hiccups.
    const vendorStatus = await checkVendorStatus();

    // Show the warm-up spinner only if we genuinely don't know whether
    // bundles are present. If the server says "yes they're here", we
    // can probably load fast enough that we skip the spinner.
    const certain = vendorStatus && vendorStatus.ok;
    if (!certain) {
        showWarmup($app, true);
    }

    // Step 2: load each vendor bundle. Try local first, always.
    // CDN is the fallback. Show the calm error card only if BOTH paths
    // fail for a single bundle.
    for (const bundle of VENDOR_BUNDLES) {
        if (window[bundle.global]) continue;

        let loaded = false;

        // Always try the local file first. The browser will return 404
        // immediately if it isn't there, so the cost of trying is tiny.
        try {
            await loadScript(bundle.local);
            loaded = !!window[bundle.global];
        } catch (e) { /* fall through to CDN */ }

        // CDN fallback.
        if (!loaded) {
            for (const cdn of bundle.cdns) {
                try {
                    await loadScript(cdn);
                    if (window[bundle.global]) { loaded = true; break; }
                } catch (e) { /* try next CDN */ }
            }
        }

        if (!loaded) {
            throw new VendorLoadError(bundle.global, bundle.cdns);
        }
    }

    // Step 3: load the SFC loader, then boot the SPA.
    // First load the global stylesheet so it's in place before the SPA mounts.
    const cssLink = document.createElement('link');
    cssLink.rel = 'stylesheet';
    cssLink.href = `${SPA_LOCAL_BASE}/sfc/styles/globals.css`;
    document.head.appendChild(cssLink);

    await loadScript(`${SPA_LOCAL_BASE}/sfc-loader.js`);
    await loadScript(`${SPA_LOCAL_BASE}/main.js`);
    // The SPA's main.js is responsible for mounting onto #alphax-cashier-app
    // and clearing the warm-up card as part of its mount.
}


function bundleNameFromLocal(localPath) {
    return localPath.split('/').pop();
}


function loadScript(src) {
    return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.async = false;   // preserve execution order
        s.onload = () => resolve();
        s.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(s);
    });
}


function checkVendorStatus() {
    return new Promise((resolve) => {
        frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.cashier.vendor.vendor_status',
            callback: (r) => resolve(r && r.message ? r.message : null),
            error: () => resolve(null),
        });
    });
}


class VendorLoadError extends Error {
    constructor(globalName, cdns) {
        super(`Could not load ${globalName} from local files or any CDN.`);
        this.name = 'VendorLoadError';
        this.globalName = globalName;
        this.cdns = cdns;
    }
}


// ---------------------------------------------------------------------------
// Error card — calm, bilingual, actionable. No stack traces.
// ---------------------------------------------------------------------------

function showError($app, err) {
    const isVendorErr = err && err.name === 'VendorLoadError';
    const titleEn = isVendorErr
        ? "The cashier couldn't reach its display files."
        : "Something went wrong loading the register.";
    const titleAr = isVendorErr
        ? "تعذر على الكاشير الوصول إلى ملفات العرض."
        : "حدث خطأ أثناء تحميل الكاشير.";
    const bodyEn = isVendorErr
        ? "This usually clears up on its own in a moment. The system will retry automatically. If it keeps happening, check that the device has internet access."
        : "Please refresh the page. If the problem continues, contact your administrator.";
    const bodyAr = isVendorErr
        ? "غالبًا ما تُحَل هذه المشكلة من تلقاء نفسها بعد لحظات. سيُعاد المحاولة تلقائيًا. إذا استمرت المشكلة، تأكد من اتصال الجهاز بالإنترنت."
        : "يرجى تحديث الصفحة. إذا استمرت المشكلة، يرجى التواصل مع المسؤول.";

    $app.html(`
        <div class="alphax-warmup">
            <div class="alphax-error-card">
                <div class="alphax-error-icon">⚠️</div>
                <h2 class="alphax-error-title">${escapeHtml(titleEn)}</h2>
                <p class="alphax-error-body">${escapeHtml(bodyEn)}</p>
                <h2 class="alphax-error-title" dir="rtl" style="margin-top:18px;">${escapeHtml(titleAr)}</h2>
                <p class="alphax-error-body" dir="rtl">${escapeHtml(bodyAr)}</p>
                <button class="alphax-error-retry" onclick="window.location.reload()">Retry / إعادة المحاولة</button>
            </div>
        </div>
    `);

    // Auto-retry once after 8 seconds — covers transient network blips.
    if (!window.__alphax_retried) {
        window.__alphax_retried = true;
        setTimeout(() => window.location.reload(), 8000);
    }
}


function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
