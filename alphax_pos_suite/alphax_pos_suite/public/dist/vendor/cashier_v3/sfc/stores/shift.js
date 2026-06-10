/*
 * AlphaX POS v3 — `shift` Pinia store.
 *
 * Tracks the cashier's current shift:
 *   - active shift document (or null if none open)
 *   - opening cash float
 *   - mid-shift cash moves
 *
 * Phase 2: stubs. Phase 9 wires real shift endpoints.
 */

const { defineStore } = window.Pinia;
const { ref, computed } = window.Vue;

export const useShiftStore = defineStore('shift', () => {
    const shift = ref(null);
    const openingCash = ref(0);
    const cashMoves = ref([]); // each: { kind: 'drop'|'lift', amount, time, reason }
    const loading = ref(false);

    const isOpen = computed(() => !!shift.value);
    const expectedCash = computed(() => {
        // Phase 9 will compute this properly from sales + cash moves
        return openingCash.value;
    });

    async function openShift(initialCash) {
        loading.value = true;
        try {
            console.info('[shift] openShift stub:', initialCash);
            // Phase 9: real call
            shift.value = { name: 'TEMP-SHIFT-STUB', opening_cash: initialCash };
            openingCash.value = initialCash;
        } finally {
            loading.value = false;
        }
    }

    async function closeShift(actualCash) {
        loading.value = true;
        try {
            console.info('[shift] closeShift stub:', actualCash);
            shift.value = null;
            openingCash.value = 0;
            cashMoves.value = [];
        } finally {
            loading.value = false;
        }
    }

    function addCashMove(kind, amount, reason) {
        cashMoves.value.push({
            kind,
            amount: Number(amount) || 0,
            time: new Date().toISOString(),
            reason: reason || '',
        });
    }

    return {
        shift, openingCash, cashMoves, loading,
        isOpen, expectedCash,
        openShift, closeShift, addCashMove,
    };
});
