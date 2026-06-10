/*
 * AlphaX POS v3 — `pos` Pinia store.
 *
 * Holds the active sale state:
 *   - which terminal/profile is in use
 *   - cart line items
 *   - current customer
 *   - applied payments
 *   - sale mode (sale / return / hold-resume)
 *
 * Methods are stubbed in Phase 2 — they log to console so we can verify
 * wiring without a backend. Phase 3+ replaces stubs with real API calls.
 */

const { defineStore } = window.Pinia;
const { ref, computed } = window.Vue;

export const usePOSStore = defineStore('pos', () => {
    // Terminal & profile context (loaded from pos_boot in Phase 3)
    const terminal = ref(null);
    const profile = ref(null);
    const outlet = ref(null);
    const branch = ref(null);
    const domainPack = ref(null);
    const boot = ref(null);
    const bootLoading = ref(false);
    const bootError = ref(null);

    // Sale mode
    const mode = ref('sale'); // 'sale' | 'return' | 'hold-resume'
    const originalInvoice = ref(null); // for return mode

    // Cart
    const cart = ref([]); // [{ line_uuid, item_code, item_name, qty, rate, modifiers, ... }]
    const customer = ref(null);
    const payments = ref([]);

    // Computed totals (replaced with proper tax engine in Phase 5)
    const subtotal = computed(() =>
        cart.value.reduce((s, line) => s + (line.qty || 0) * (line.rate || 0), 0)
    );
    const taxAmount = computed(() => subtotal.value * 0.15); // KSA VAT 15% placeholder
    const total = computed(() => subtotal.value + taxAmount.value);
    const paymentsTotal = computed(() =>
        payments.value.reduce((s, p) => s + (p.amount || 0), 0)
    );
    const remaining = computed(() => Math.max(0, total.value - paymentsTotal.value));

    // -- Actions (Phase 2 stubs) -----------------------------------------

    async function loadBoot(terminalName) {
        bootLoading.value = true;
        bootError.value = null;
        try {
            console.info('[pos] loadBoot stub:', terminalName);
            // Phase 3 will replace this with: const r = await api.posBoot(terminalName)
            terminal.value = terminalName;
            // Mock minimal boot data so the UI can render
            boot.value = {
                terminal: { name: terminalName },
                outlet: { name: 'Coffee Shop', branch: 'Riyadh Mall' },
                _phase2_mock: true,
            };
            outlet.value = boot.value.outlet;
            branch.value = 'Riyadh Mall';
        } catch (e) {
            bootError.value = e.message || String(e);
        } finally {
            bootLoading.value = false;
        }
    }

    function addItem(item, opts = {}) {
        console.info('[pos] addItem stub:', item, opts);
        // Phase 4 will replace with real cart logic
    }

    function removeItem(lineUuid) {
        console.info('[pos] removeItem stub:', lineUuid);
    }

    function setMode(newMode) {
        if (!['sale', 'return', 'hold-resume'].includes(newMode)) return;
        mode.value = newMode;
        console.info('[pos] mode →', newMode);
    }

    function clearCart() {
        cart.value = [];
        payments.value = [];
        customer.value = null;
    }

    return {
        // State
        terminal, profile, outlet, branch, domainPack, boot,
        bootLoading, bootError,
        mode, originalInvoice,
        cart, customer, payments,
        // Computed
        subtotal, taxAmount, total, paymentsTotal, remaining,
        // Actions
        loadBoot, addItem, removeItem, setMode, clearCart,
    };
});
