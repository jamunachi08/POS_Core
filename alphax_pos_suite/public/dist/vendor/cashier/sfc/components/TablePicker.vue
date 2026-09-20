<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['close'])

const floors = ref([])
const layouts = ref({})
const loading = ref(true)
const search = ref('')
const freeOnly = ref(false)

// Table creation from the till. A restaurant that has just switched on
// mandatory tables has none, and the empty picker used to be a dead end:
// could not sell, could not fix it without a desk user.
const admin = ref({ can_manage: false, can_create_floor: false, suggested_code: 'T1', default_seats: 4 })
const adding = ref(false)
const addBusy = ref(false)
const addError = ref('')
const draft = ref({ table_code: '', seats: 4, floor: null })

async function loadFloors() {
  const outlet = store.boot?.outlet?.name
  floors.value = await api.listFloors(outlet) || []
  const next = {}
  for (const f of floors.value) {
    try { next[f.name] = await api.getFloorLayout(f.name) } catch {}
  }
  layouts.value = next
}

onMounted(async () => {
  loading.value = true
  try {
    await loadFloors()
  } catch {}
  try {
    const st = await api.tableAdminState(store.boot?.outlet?.name)
    if (st) {
      admin.value = st
      draft.value = {
        table_code: st.suggested_code || 'T1',
        seats: st.default_seats || 4,
        floor: floors.value[0]?.name || null,
      }
      // Nothing to pick and permission to fix it — open the form rather
      // than making someone hunt for the button mid-service.
      if (!totalTables.value && st.can_manage) adding.value = true
    }
  } catch { /* no permission endpoint on an older server — hide the form */ }
  loading.value = false
})

const totalTables = computed(() =>
  Object.values(layouts.value).reduce((n, l) => n + ((l?.tables || []).length), 0))

function visibleTables(floorName) {
  const q = search.value.trim().toLowerCase()
  return (layouts.value[floorName]?.tables || []).filter(tbl => {
    if (freeOnly.value && (tbl.status || 'Free') !== 'Free') return false
    if (!q) return true
    return String(tbl.table_code || '').toLowerCase().includes(q)
  })
}

const anyVisible = computed(() =>
  floors.value.some(f => visibleTables(f.name).length))

function pick(table) {
  store.setTable(table.table_code || table.name)
  // Seat count is the best first guess at the cover count, and it is
  // right often enough to save a tap. The cashier can still change it.
  if (store.activeOrderType?.requires_cover_count && !store.context.covers && table.seats) {
    store.setCovers(table.seats)
  }
  emit('close')
}

async function addTable() {
  addError.value = ''
  const code = (draft.value.table_code || '').trim()
  if (!code) { addError.value = t('table.code_required'); return }
  addBusy.value = true
  try {
    const r = await api.quickAddTable(
      code, Number(draft.value.seats) || 4,
      draft.value.floor || null, store.boot?.outlet?.name)
    await loadFloors()
    draft.value = {
      table_code: r?.next_code || '',
      seats: draft.value.seats,
      floor: r?.floor || draft.value.floor,
    }
    // Keep the form open: tables are added in runs of ten, not one.
    search.value = ''
  } catch (e) {
    addError.value = e?.message || String(e)
  } finally {
    addBusy.value = false
  }
}

function statusClass(t) {
  return `t-${(t.status || 'Free').toLowerCase()}`
}
</script>

<template>
  <AppModal :title="t('table.pick_table')" size="lg" @close="emit('close')">
    <div v-if="loading" class="muted">…</div>

    <template v-else>
      <!-- Filter bar. Twenty tables is a scroll; forty is a search. -->
      <div v-if="totalTables > 8" class="tp-bar">
        <input class="tp-search" v-model="search" :placeholder="t('table.search')" />
        <button class="tp-toggle" :class="{ on: freeOnly }" @click="freeOnly = !freeOnly">
          {{ t('table.free_only') }}
        </button>
      </div>

      <!-- Empty state that can actually be resolved from here. -->
      <div v-if="!totalTables && !adding" class="tp-empty">
        <div class="tp-empty-title">{{ t('table.none_yet') }}</div>
        <p class="muted small">
          {{ admin.can_manage ? t('table.none_yet_can_add') : t('table.none_yet_ask_manager') }}
        </p>
        <button v-if="admin.can_manage" class="tp-add-btn" @click="adding = true">
          + {{ t('table.add_table') }}
        </button>
      </div>

      <div v-else-if="totalTables && !anyVisible" class="muted">{{ t('table.none_match') }}</div>

      <div v-for="f in floors" :key="f.name" class="floor">
        <div class="floor-name" v-if="visibleTables(f.name).length">{{ f.floor_name }}</div>
        <div class="tables">
          <button
            v-for="tbl in visibleTables(f.name)"
            :key="tbl.name"
            class="table"
            :class="statusClass(tbl)"
            :disabled="['Disabled', 'Occupied'].includes(tbl.status)"
            @click="pick(tbl)"
          >
            <div class="t-code">{{ tbl.table_code }}</div>
            <div class="t-seats">{{ t('table.seats', tbl.seats || 0, { n: tbl.seats || 0 }) }}</div>
            <div class="t-status">{{ t(`table.${(tbl.status || 'Free').toLowerCase()}`) }}</div>
          </button>
        </div>
      </div>

      <!-- Add a table without leaving the till. -->
      <div v-if="admin.can_manage" class="tp-addwrap">
        <button v-if="!adding" class="tp-add-link" @click="adding = true">
          + {{ t('table.add_table') }}
        </button>

        <div v-else class="tp-form">
          <div class="tp-form-row">
            <label class="tp-f">
              <span>{{ t('table.code') }}</span>
              <input v-model="draft.table_code" class="tp-input" autofocus
                     @keyup.enter="addTable" />
            </label>
            <label class="tp-f narrow">
              <span>{{ t('table.seats_label') }}</span>
              <input v-model="draft.seats" class="tp-input" type="number" min="1" max="60"
                     inputmode="numeric" @keyup.enter="addTable" />
            </label>
            <label class="tp-f" v-if="floors.length > 1">
              <span>{{ t('table.floor') }}</span>
              <select v-model="draft.floor" class="tp-input">
                <option v-for="f in floors" :key="f.name" :value="f.name">{{ f.floor_name }}</option>
              </select>
            </label>
          </div>
          <div class="tp-form-actions">
            <button class="tp-save" :disabled="addBusy" @click="addTable">
              {{ addBusy ? '…' : t('table.add_table') }}
            </button>
            <button class="tp-cancel" @click="adding = false">{{ t('app.done') }}</button>
          </div>
          <div v-if="addError" class="tp-err">{{ addError }}</div>
          <p class="muted small">{{ t('table.add_hint') }}</p>
        </div>
      </div>
    </template>
  </AppModal>
</template>

<style scoped>
.muted { color: var(--text-dim); padding: 30px; text-align: center; font-size: 13px; }
.floor { margin-block-end: 16px; }
.floor:last-child { margin-block-end: 0; }
.floor-name { font-size: 12px; color: var(--text-muted); margin-block-end: 8px; text-transform: uppercase; letter-spacing: 0.5px; }

.tp-bar { display: flex; gap: 8px; margin-block-end: 12px; }
.tp-search { flex: 1; height: 38px; padding: 0 12px; font-size: 13px;
  border: 1px solid var(--border); border-radius: var(--r-md); background: var(--surface); color: var(--text); }
.tp-toggle { height: 38px; padding: 0 14px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--border); border-radius: var(--r-md); background: var(--surface); color: var(--text-muted); }
.tp-toggle.on { border-color: var(--brand, #0B6B5B); color: var(--brand, #0B6B5B);
  background: color-mix(in srgb, var(--brand, #0B6B5B) 8%, transparent); }

.tp-empty { text-align: center; padding: 26px 20px; }
.tp-empty-title { font-weight: 700; font-size: 15px; margin-block-end: 4px; }
.tp-add-btn { margin-block-start: 12px; height: 40px; padding: 0 20px; font-weight: 700;
  border-radius: var(--r-md); background: var(--brand, #0B6B5B); color: #fff; }

.tp-addwrap { margin-block-start: 14px; border-block-start: 1px solid var(--border); padding-block-start: 12px; }
.tp-add-link { font-size: 13px; font-weight: 600; color: var(--brand, #0B6B5B); padding: 4px 0; }
.tp-form-row { display: flex; gap: 8px; flex-wrap: wrap; }
.tp-f { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 120px; font-size: 11px; color: var(--text-muted); }
.tp-f.narrow { flex: 0 0 90px; min-width: 90px; }
.tp-input { height: 38px; padding: 0 10px; font-size: 13px; border: 1px solid var(--border);
  border-radius: var(--r-md); background: var(--surface); color: var(--text); }
.tp-form-actions { display: flex; gap: 8px; margin-block-start: 10px; }
.tp-save { height: 38px; padding: 0 18px; font-weight: 700; border-radius: var(--r-md);
  background: var(--brand, #0B6B5B); color: #fff; }
.tp-save:disabled { opacity: .5; }
.tp-cancel { height: 38px; padding: 0 14px; border-radius: var(--r-md);
  border: 1px solid var(--border); color: var(--text-muted); }
.tp-err { margin-block-start: 8px; font-size: 12px; color: var(--danger, #C0392B); }
.small { font-size: 11px; }

.tables { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
.table {
  padding: 12px;
  border-radius: var(--r-md);
  border: 1.5px solid;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  transition: transform var(--t-fast);
}
.table:not(:disabled):hover { transform: scale(1.02); }
.table:disabled { opacity: 0.45; cursor: not-allowed; }
.table.t-free      { background: #EAF3DE; border-color: #639922; color: #27500A; }
.table.t-occupied  { background: #FAEEDA; border-color: #BA7517; color: #633806; }
.table.t-reserved  { background: #E6F1FB; border-color: #185FA5; color: #0C447C; }
.table.t-dirty     { background: #F1EFE8; border-color: #5F5E5A; color: #444441; }
.table.t-disabled  { background: #FCEBEB; border-color: #A32D2D; color: #791F1F; }
.t-code { font-weight: 600; font-size: 14px; }
.t-seats { font-size: 11px; opacity: 0.75; }
.t-status { font-size: 10px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.4px; }
</style>
