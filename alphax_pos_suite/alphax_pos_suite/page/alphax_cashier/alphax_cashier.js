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

frappe.pages['alphax-cashier'].on_page_load = function (wrapper) {
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

// Reclaim the page-title band ("AlphaX POS" heading) — dead vertical
// space on a register. The SPA is a fixed overlay below the navbar, so
// the desk page content under it only causes stray scrollbars.
(function injectCashierPageCss() {
    if (document.getElementById('alphax-cashier-page-css')) return;
    const st = document.createElement('style');
    st.id = 'alphax-cashier-page-css';
    st.textContent = `
        #page-alphax-cashier .page-head { display: none !important; }
        #page-alphax-cashier .page-body { margin: 0 !important; }
        body[data-route="alphax-cashier"] { overflow: hidden; }
    `;
    document.head.appendChild(st);
})();

const VENDOR_LOCAL_BASE = '/assets/alphax_pos_suite/dist/vendor';
const SPA_LOCAL_BASE    = '/assets/alphax_pos_suite/dist/vendor/cashier';

// Cache-busting version stamp. Frappe's own bundles get ?v=<hash>; ours
// historically did NOT, which let browsers and Frappe Cloud's edge cache
// pin an old main.js across releases (observed on neotectest: repo at
// v15.6.4, browser executing v15.6.3). The installed app version changes
// every release, so stamping it on each URL gives stable caching within
// a release and an instant bust on upgrade.
const ASSET_VER = encodeURIComponent(
    (window.frappe && frappe.boot && frappe.boot.versions
        && frappe.boot.versions.alphax_pos_suite) || Date.now()
);
function versioned(url) {
    return url + (url.includes('?') ? '&' : '?') + 'v=' + ASSET_VER;
}
// The SFC loader and main.js run as separate scripts — share the stamp.
window.ALPHAX_ASSET_VER = ASSET_VER;

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
            await loadScript(versioned(bundle.local));
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
    //
    // Supply lines, in order:
    //   1. /assets/... (nginx static — fast, cacheable, the normal path)
    //   2. /api/method/...cashier.assets.* (Python reads the same files
    //      from the installed app package — bypasses the entire asset
    //      pipeline). Exists because Frappe Cloud deploys have repeatedly
    //      served the app code while 404ing our committed public files.
    //
    // window.ALPHAX_SPA_FETCH is the single fetch used by this loader,
    // sfc-loader.js, and main.js. Once /assets fails ONCE, we pull the
    // full manifest through the API in one round-trip and every later
    // file is served from that in-memory cache.

    const API_BASE = '/api/method/alphax_pos_suite.alphax_pos_suite.cashier.assets';
    let manifestCache = null;      // { 'cashier/sfc/App.vue': '...', ... }
    let assetsBroken = false;

    async function fetchManifest() {
        if (manifestCache) return manifestCache;
        const r = await fetch(`${API_BASE}.spa_manifest`, {
            headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
        });
        if (!r.ok) throw new Error(`Asset fallback API failed: HTTP ${r.status}`);
        const data = await r.json();
        manifestCache = (data.message && data.message.files) || {};
        console.warn(`AlphaX Cashier: /assets is not serving SPA files — ` +
            `switched to API fallback (${Object.keys(manifestCache).length} files).`);
        return manifestCache;
    }

    // rel is vendor-relative, e.g. 'cashier/sfc/App.vue'
    window.ALPHAX_SPA_FETCH = async function (rel) {
        if (!assetsBroken) {
            try {
                const r = await fetch(versioned(`${VENDOR_LOCAL_BASE}/${rel}`));
                if (r.ok) return await r.text();
                assetsBroken = true;
            } catch (e) {
                assetsBroken = true;
            }
        }
        const files = await fetchManifest();
        if (rel in files) return files[rel];
        // Not in manifest (e.g. an image) — single-file endpoint.
        const r = await fetch(`${API_BASE}.spa_asset?path=${encodeURIComponent(rel)}`, {
            headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
        });
        if (!r.ok) throw new Error(`Failed to load ${rel} via assets AND API fallback (HTTP ${r.status})`);
        const data = await r.json();
        return data.message.content;
    };

    // Global stylesheet — through the same supply lines.
    try {
        const cssText = await window.ALPHAX_SPA_FETCH('cashier/sfc/styles/globals.css');
        const styleEl = document.createElement('style');
        styleEl.setAttribute('data-alphax', 'globals');
        styleEl.textContent = cssText;
        document.head.appendChild(styleEl);
    } catch (e) {
        console.error('AlphaX Cashier: could not load globals.css', e);
    }

    // Bootstrap scripts — try the fast <script src> path first; if the
    // asset path is broken, fetch the text through the fallback and
    // inject inline (inline scripts execute regardless of how the text
    // was obtained).
    for (const rel of ['cashier/sfc-loader.js', 'cashier/main.js']) {
        let injected = false;
        if (!assetsBroken) {
            try {
                await loadScript(versioned(`${VENDOR_LOCAL_BASE}/${rel}`));
                injected = true;
            } catch (e) {
                assetsBroken = true;
            }
        }
        if (!injected) {
            const code = await window.ALPHAX_SPA_FETCH(rel);
            const s = document.createElement('script');
            s.setAttribute('data-alphax', rel);
            s.textContent = code;
            document.head.appendChild(s);
        }
    }
    // main.js mounts onto #alphax-cashier-app and clears the warm-up card.
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
    const bodyEn = "Please refresh. If it keeps happening, share the diagnosis below with your administrator.";
    const bodyAr = "يرجى التحديث. إذا استمرّت المشكلة، شارك التشخيص أدناه مع مسؤول النظام.";

    // Show the actual failing resource so an admin can see WHY, without a
    // scary stack trace. e.g. "Failed to load /assets/.../cashier/main.js".
    const detail = (err && (err.message || String(err))) || '';
    const detailBlock = detail
        ? `<div class="alphax-error-action" title="Technical detail">${escapeHtml(detail)}</div>`
        : '';

    $app.html(`
        <div class="alphax-warmup">
            <div class="alphax-error-card">
                <div class="alphax-error-icon">⚠️</div>
                <h2 class="alphax-error-title">${escapeHtml(titleEn)}</h2>
                <p class="alphax-error-body">${escapeHtml(bodyEn)}</p>
                ${detailBlock}
                <div id="alphax-asset-health" class="alphax-error-action" style="display:none; text-align:start; white-space:pre-wrap;"></div>
                <h2 class="alphax-error-title" dir="rtl" style="margin-top:18px;">${escapeHtml(titleAr)}</h2>
                <p class="alphax-error-body" dir="rtl">${escapeHtml(bodyAr)}</p>
                <div style="margin-top:18px; display:flex; gap:10px; flex-wrap:wrap;">
                    <button class="alphax-error-retry" onclick="window.location.reload()">Retry / إعادة المحاولة</button>
                    <a class="alphax-error-retry" href="/app/alphax-pos"
                       style="background:#fff; color:#0F6E56; border:1px solid #0F6E56; text-decoration:none; display:inline-block;">
                       Open POS Home / فتح لوحة نقاط البيع</a>
                </div>
            </div>
        </div>
    `);

    // Self-diagnosis: ask the server what IT can see of the asset
    // pipeline, and print it on the card. Turns a screenshot of this
    // card into an actionable bug report.
    frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.cashier.assets.asset_health',
        callback(r) {
            const h = r.message;
            if (!h) return;
            const lines = [];
            (h.roots || []).forEach((root, i) => {
                lines.push(`root ${i + 1}: ${root.has_spa ? 'HAS SPA' : (root.exists ? 'exists, NO SPA' : 'missing')} — ${root.path}`);
            });
            lines.push(`serving from: ${h.chosen_has_spa ? h.chosen_root : 'NOWHERE (no root has the SPA files)'}`);
            if (h.package_file) lines.push(`python package: ${h.package_file}`);
            if (h.sites_assets_link) {
                lines.push(`sites/assets link: ${h.sites_assets_link.kind || h.sites_assets_link.error || '?'}`);
            }
            if (h.assets_sample_file) {
                lines.push(`file visible via assets path: ${h.assets_sample_file.exists ? 'YES' : 'NO'}`);
            }
            const el = document.getElementById('alphax-asset-health');
            if (el) {
                el.style.display = 'block';
                el.textContent = 'Server diagnosis:\n' + lines.join('\n');
            }
        },
        error() { /* even diagnostics are down — nothing more to show */ },
    });

    // Auto-retry at most ONCE per session — covers a transient network blip
    // but never loops forever when the files are genuinely missing (so the
    // cashier can read this card and escalate).
    try {
        const tries = parseInt(sessionStorage.getItem('alphax_v2_retries') || '0', 10);
        if (tries < 1) {
            sessionStorage.setItem('alphax_v2_retries', String(tries + 1));
            setTimeout(() => window.location.reload(), 8000);
        }
    } catch (e) { /* sessionStorage unavailable — skip auto-retry */ }
}


function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
