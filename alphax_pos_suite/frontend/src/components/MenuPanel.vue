<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useHardwareStore } from '../stores/hardware'
import { useMoney } from '../composables/useMoney'
import { haptics } from '../composables/haptics'

const store = usePOSStore()
const hw = useHardwareStore()
const { t } = useI18n()
const { fmt } = useMoney()

const emit = defineEmits(['pick'])

// Display preferences — persisted per terminal. 'cards' | 'list';
// images on/off (off keeps the grid dense for shops without item
// photos).
const viewMode = ref(localStorage.getItem('alphax_pos_view') || 'cards')
const showImages = ref(localStorage.getItem('alphax_pos_images') !== '0')
function setView(mode) {
  viewMode.value = mode
  localStorage.setItem('alphax_pos_view', mode)
}
function toggleImages() {
  showImages.value = !showImages.value
  localStorage.setItem('alphax_pos_images', showImages.value ? '1' : '0')
}
const searchRef = ref(null)
let idleTimer = null

function pickItem(item) {
  haptics.tap()
  emit('pick', item)
}

// Auto-detect scale barcode in search and emit immediately
watch(() => store.searchQuery, (q) => {
  if (!q) return
  if (/^\d{6,}$/.test(q.trim())) {
    const hit = store.tryScaleBarcode(q.trim())
    if (hit) {
      emit('pick', { ...hit.item, _scaleHit: hit })
      store.searchQuery = ''
    }
  }
})

function clearSearch() { store.searchQuery = '' }

// Focus management. After ~3 seconds of idle anywhere on the page, return
// focus to the search bar so HID barcode scanners always land here.
function refocus() {
  const active = document.activeElement
  // Don't fight the user if they're in another input or modal.
  if (active && active.tagName === 'INPUT' && active !== searchRef.value) return
  if (active && active.tagName === 'TEXTAREA') return
  if (document.querySelector('.modal-backdrop')) return
  searchRef.value?.focus()
}

function bumpIdle() {
  clearTimeout(idleTimer)
  idleTimer = setTimeout(refocus, 3000)
}

// Start scale polling when a scale is mapped + connected
function syncScalePolling() {
  if (hw.scaleReady) hw.startWeightPolling(1500)
  else hw.stopWeightPolling()
}
watch(() => hw.scaleReady, syncScalePolling, { immediate: true })

onMounted(() => {
  syncScalePolling()
  refocus()
  bumpIdle()
  document.addEventListener('mousedown', bumpIdle)
  document.addEventListener('touchstart', bumpIdle)
  document.addEventListener('keydown', bumpIdle)
})
onBeforeUnmount(() => {
  hw.stopWeightPolling()
  clearTimeout(idleTimer)
  document.removeEventListener('mousedown', bumpIdle)
  document.removeEventListener('touchstart', bumpIdle)
  document.removeEventListener('keydown', bumpIdle)
})
</script>

<template>
  <section class="menu-panel">
    <div class="search-row">
      <div class="search-wrap">
        <span class="search-icon">⌕</span>
        <input
          ref="searchRef"
          class="search"
          v-model="store.searchQuery"
          :placeholder="t('menu.search_placeholder')"
          autocomplete="off"
          spellcheck="false"
        />
        <button v-if="store.searchQuery" class="clear" @click="clearSearch">×</button>
      </div>
      <div v-if="hw.scaleReady && hw.liveWeight" class="weight-chip"
        :class="{ unstable: hw.liveWeight && hw.liveWeight.stable === false }">
        <span class="scale-icon">⚖</span>
        <span class="weight-value tnum">{{ hw.liveWeight.weight.toFixed(3) }}</span>
        <span class="weight-unit">{{ hw.liveWeight.unit || 'kg' }}</span>
      </div>
    </div>

    <div class="cats-bar">
      <div class="cats" v-if="store.categories.length">
        <button
          class="cat"
          :class="{ active: !store.activeCategory }"
          @click="store.activeCategory = ''"
        >{{ t('menu.all_categories') }}</button>
        <button
          v-for="g in store.categories"
          :key="g"
          class="cat"
          :class="{ active: store.activeCategory === g }"
          @click="store.activeCategory = g"
        >{{ g }}</button>
      </div>
      <div v-else class="cats-spacer"></div>
      <div class="view-toggle">
        <button class="vt-btn" :class="{ active: viewMode === 'cards' }" @click="setView('cards')">
          <span class="vt-glyph">▦</span><span class="vt-txt">{{ t('menu.view_cards_short') }}</span>
        </button>
        <button class="vt-btn" :class="{ active: viewMode === 'list' }" @click="setView('list')">
          <span class="vt-glyph">≡</span><span class="vt-txt">{{ t('menu.view_list_short') }}</span>
        </button>
        <button class="vt-btn" :class="{ active: showImages }" @click="toggleImages">
          <span class="vt-glyph">◪</span><span class="vt-txt">{{ t('menu.toggle_images_short') }}</span>
        </button>
      </div>
    </div>

    <div class="grid-wrap">
      <div v-if="store.menuLoading" class="grid-empty">…</div>
      <div v-else-if="store.filteredMenu.length === 0" class="grid-empty">
        <div class="grid-empty-icon">∅</div>
        <div>{{ store.searchQuery ? t('menu.no_results') : t('menu.no_items') }}</div>
      </div>
      <!-- Combos strip: Fixed adds straight to cart; Customizable opens
           the picker (emit up — CashierView owns dialogs). -->
      <div v-if="store.combos.length" class="combo-strip">
        <button v-for="cb in store.combos" :key="cb.name" class="combo-card"
                @click="$emit('pick-combo', cb)">
          <span class="combo-tag">{{ t('combo.tag') }}</span>
          <span class="combo-nm">{{ cb.combo_name }}</span>
          <span class="combo-pr tnum">{{ fmt(cb.combo_price) }}</span>
        </button>
      </div>
      <div v-else-if="false"></div>
      <div v-if="store.filteredMenu.length" :class="viewMode === 'list' ? 'ilist' : 'grid'">
        <button
          v-for="it in store.filteredMenu"
          :key="it.item_code"
          class="item"
          :class="{ 'item-row': viewMode === 'list' }"
          @click="pickItem(it)"
        >
          <div v-if="showImages" class="item-img" :class="{ 'img-row': viewMode === 'list' }">
            <img v-if="it.image" :src="it.image" :alt="it.item_name" loading="lazy" />
            <span v-else class="img-ph">{{ (it.item_name || it.item_code || '?').slice(0, 2) }}</span>
          </div>
          <div class="item-body">
            <div class="item-name">{{ it.item_name || it.item_code }}</div>
            <div class="item-meta">
              <span class="item-rate">
                {{ fmt(it.standard_rate || 0) }}<span v-if="it.alphax_is_weighing_item" class="suffix">/kg</span>
              </span>
              <span v-if="it.alphax_is_weighing_item" class="pill pill-info" style="font-size: 9px; padding: 1px 7px;">
                {{ t('menu.weighed_item') }}
              </span>
            </div>
          </div>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.menu-panel {
  background: var(--bg);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.search-row {
  background: var(--surface);
  border-block-end: 1px solid var(--border);
  padding: 12px 18px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
}
.weight-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
}
.weight-chip.unstable { background: var(--warn-soft); color: var(--warn); }
.weight-chip .scale-icon { font-size: 14px; }
.weight-chip .weight-unit { font-size: 11px; opacity: 0.75; }
.search-icon {
  position: absolute;
  inset-inline-start: 12px;
  font-size: 16px;
  color: var(--text-dim);
}
.search {
  width: 100%;
  padding: 11px 40px 11px 38px;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 14px;
  outline: none;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
[dir="rtl"] .search { padding-inline-start: 38px; padding-inline-end: 40px; }
.clear {
  position: absolute;
  inset-inline-end: 8px;
  width: 24px; height: 24px;
  border-radius: 50%;
  background: var(--surface-2);
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  line-height: 1;
}

.cats {
  background: var(--surface);
  border-block-end: 1px solid var(--border);
  padding: 8px 18px;
  display: flex;
  gap: 6px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}
.cats::-webkit-scrollbar { display: none; }
.cat {
  padding: 6px 14px;
  border-radius: var(--r-pill);
  background: transparent;
  border: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  flex-shrink: 0;
}
.cat:hover { background: var(--surface-2); }
.cat.active {
  background: var(--text);
  color: #fff;
  border-color: var(--text);
}

.grid-wrap { flex: 1; overflow-y: auto; padding: 16px 18px; min-height: 0; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 14px 12px;
  text-align: start;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  min-height: 92px;
  transition: border-color var(--t-fast), transform var(--t-fast);
}
.item:hover { border-color: var(--accent); }
.item:active { transform: scale(0.97); }
.item-name {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.item-rate {
  font-size: 13px;
  color: var(--accent);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.item-rate .suffix {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
  margin-inline-start: 2px;
}

.grid-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-dim);
  font-size: 14px;
}
.grid-empty-icon {
  font-size: 36px;
  opacity: 0.3;
}
.cats-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-inline-end: 14px;
  background: var(--surface);
}
.cats-bar .cats { flex: 1; min-width: 0; }
.cats-spacer { flex: 1; }
.view-toggle {
  display: flex;
  gap: 4px;
  flex: none;
  padding: 6px 0;
}
.vt-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.vt-glyph { font-size: 14px; line-height: 1; }
.vt-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
@media (max-width: 980px) { .vt-txt { display: none; } .vt-btn { padding: 0 10px; } }

.item { min-height: 96px; } /* touch-first sizing */
.item-img {
  width: 100%; height: 74px;
  border-radius: var(--r-sm, 8px);
  overflow: hidden;
  background: var(--surface-2);
  display: grid; place-items: center;
  margin-block-end: 6px;
}
.item-img img { width: 100%; height: 100%; object-fit: cover; }
.img-ph { font-size: 18px; font-weight: 700; color: var(--text-dim); text-transform: uppercase; }
.item-body { min-width: 0; width: 100%; }

.ilist { display: flex; flex-direction: column; gap: 8px; padding: 14px 18px; }
.item-row {
  display: flex !important;
  flex-direction: row !important;
  align-items: center;
  gap: 12px;
  min-height: 64px;
  text-align: start;
}
.item-row .item-img { width: 52px; height: 52px; flex: none; margin: 0; }
.item-row .item-body { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cat { min-height: 40px; }
.combo-strip { display: flex; gap: 8px; flex-wrap: wrap; margin-block-end: 10px; }
.combo-card {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 10px 14px; min-width: 150px; cursor: pointer;
  border: 1.5px dashed var(--accent); border-radius: var(--r-md);
  background: var(--accent-soft); color: var(--text);
}
.combo-tag { font-size: 10px; font-weight: 800; letter-spacing: .08em; color: var(--accent); text-transform: uppercase; }
.combo-nm { font-weight: 700; font-size: 13px; }
.combo-pr { font-weight: 800; font-size: 14px; color: var(--accent); }
</style>
