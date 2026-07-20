<script setup>
import { ref, onMounted } from 'vue'
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

onMounted(async () => {
  loading.value = true
  try {
    const outlet = store.boot?.outlet?.name
    floors.value = await api.listFloors(outlet) || []
    for (const f of floors.value) {
      try {
        layouts.value[f.name] = await api.getFloorLayout(f.name)
      } catch {}
    }
  } catch {}
  loading.value = false
})

function pick(table) {
  store.setTable(table.table_code || table.name)
  emit('close')
}

function statusClass(t) {
  return `t-${(t.status || 'Free').toLowerCase()}`
}
</script>

<template>
  <AppModal :title="t('table.pick_table')" size="lg" @close="emit('close')">
    <div v-if="loading" class="muted">…</div>
    <div v-else-if="floors.length === 0" class="muted">{{ t('table.no_table') }}</div>

    <div v-for="f in floors" :key="f.name" class="floor">
      <div class="floor-name">{{ f.floor_name }}</div>
      <div class="tables">
        <button
          v-for="tbl in (layouts[f.name]?.tables || [])"
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
  </AppModal>
</template>

<style scoped>
.muted { color: var(--text-dim); padding: 30px; text-align: center; font-size: 13px; }
.floor { margin-block-end: 16px; }
.floor:last-child { margin-block-end: 0; }
.floor-name { font-size: 12px; color: var(--text-muted); margin-block-end: 8px; text-transform: uppercase; letter-spacing: 0.5px; }

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
