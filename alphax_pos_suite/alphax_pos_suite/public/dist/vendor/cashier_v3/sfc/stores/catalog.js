/*
 * AlphaX POS v3 — `catalog` Pinia store.
 *
 * Holds the product catalog the cashier picks from:
 *   - items list (loaded once on boot, refreshed on demand)
 *   - item groups (for category tabs)
 *   - active category filter
 *   - search query (text or scanned barcode)
 *
 * Computed `filteredItems` provides the live filtered set for the
 * ProductGrid component.
 *
 * Phase 2: stubs only. Phase 4 wires real `list_items` API calls.
 */

const { defineStore } = window.Pinia;
const { ref, computed } = window.Vue;

export const useCatalogStore = defineStore('catalog', () => {
    const items = ref([]);
    const itemGroups = ref([]);
    const activeCategory = ref('');
    const searchQuery = ref('');
    const loading = ref(false);

    const filteredItems = computed(() => {
        let list = items.value;
        if (activeCategory.value) {
            list = list.filter(i => i.item_group === activeCategory.value);
        }
        if (searchQuery.value) {
            const q = searchQuery.value.toLowerCase();
            list = list.filter(i =>
                (i.item_code || '').toLowerCase().includes(q) ||
                (i.item_name || '').toLowerCase().includes(q)
            );
        }
        return list;
    });

    async function loadCatalog() {
        loading.value = true;
        try {
            console.info('[catalog] loadCatalog stub');
            // Phase 4: real API call
            items.value = [];
            itemGroups.value = [];
        } finally {
            loading.value = false;
        }
    }

    function setCategory(group) {
        activeCategory.value = group;
    }

    function setSearch(q) {
        searchQuery.value = (q || '').trim();
    }

    function lookupBarcode(code) {
        console.info('[catalog] lookupBarcode stub:', code);
        // Phase 4: real call. Returns the matched item or null.
        return null;
    }

    return {
        items, itemGroups, activeCategory, searchQuery, loading,
        filteredItems,
        loadCatalog, setCategory, setSearch, lookupBarcode,
    };
});
