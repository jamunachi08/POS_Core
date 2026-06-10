/*
 * AlphaX POS v3 — `ui` Pinia store.
 *
 * Cross-cutting UI state:
 *   - theme (light/dark — dark deferred to v15.6.1)
 *   - locale (en/ar) — synced with vue-i18n
 *   - modal stack (which modals are open; supports Esc-to-close)
 *   - toast queue
 */

const { defineStore } = window.Pinia;
const { ref, computed } = window.Vue;

export const useUIStore = defineStore('ui', () => {
    // Theme — light only for v15.6.0; toggle deferred
    const theme = ref(_loadString('alphax_v3_theme', 'light'));

    // Locale - synced from vue-i18n on mount
    const locale = ref(_loadString('alphax_v3_locale', 'en'));

    // Modal stack: array of modal IDs in z-order. The top one is active.
    const modalStack = ref([]);
    const topModal = computed(() => modalStack.value[modalStack.value.length - 1] || null);

    // Toast queue
    const toasts = ref([]);

    // -- Theme actions --
    function setTheme(t) {
        theme.value = t;
        _saveString('alphax_v3_theme', t);
        document.documentElement.setAttribute('data-theme', t);
    }

    // -- Locale actions --
    function setLocale(lang) {
        locale.value = lang;
        _saveString('alphax_v3_locale', lang);
        document.documentElement.setAttribute('lang', lang);
        document.documentElement.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    }

    // -- Modal actions --
    function openModal(id) {
        if (!modalStack.value.includes(id)) {
            modalStack.value.push(id);
        }
    }

    function closeModal(id) {
        modalStack.value = modalStack.value.filter(m => m !== id);
    }

    function closeTopModal() {
        modalStack.value.pop();
    }

    function isModalOpen(id) {
        return modalStack.value.includes(id);
    }

    // -- Toast actions --
    function showToast(message, opts = {}) {
        const toast = {
            id: Math.random().toString(36).slice(2, 10),
            message,
            type: opts.type || 'info',  // 'info' | 'success' | 'warning' | 'error'
            duration: opts.duration || 4000,
        };
        toasts.value.push(toast);
        if (toast.duration > 0) {
            setTimeout(() => {
                dismissToast(toast.id);
            }, toast.duration);
        }
        return toast.id;
    }

    function dismissToast(id) {
        toasts.value = toasts.value.filter(t => t.id !== id);
    }

    return {
        theme, locale,
        modalStack, topModal,
        toasts,
        setTheme, setLocale,
        openModal, closeModal, closeTopModal, isModalOpen,
        showToast, dismissToast,
    };
});

// -- localStorage helpers (defensive) --
function _loadString(key, fallback) {
    try { return localStorage.getItem(key) || fallback; }
    catch (e) { return fallback; }
}

function _saveString(key, value) {
    try { localStorage.setItem(key, value); }
    catch (e) { /* localStorage blocked or full; non-fatal */ }
}
