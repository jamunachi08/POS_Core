<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'

const { t } = useI18n()
const store = usePOSStore()

const emit = defineEmits([
  'pick-table', 'add-rx', 'pick-batch', 'pick-appointment'
])

const showTable    = computed(() => store.activeFeatures.uses_floor_plan)
const showRx       = computed(() => store.activeFeatures.uses_prescription)
const showBatch    = computed(() => store.activeFeatures.uses_batch_expiry)
const showAppt     = computed(() => store.activeFeatures.uses_appointments)

const anyVisible = computed(() =>
  showTable.value || showRx.value || showBatch.value || showAppt.value)
</script>

<template>
  <div v-if="anyVisible" class="ribbon">
    <button v-if="showTable" class="chip" :class="{ filled: store.activeTable }" @click="emit('pick-table')">
      <span class="chip-icon">⬚</span>
      <span class="chip-label">
        <span class="chip-title">{{ t('context.table_chip') }}</span>
        <span class="chip-value">{{ store.activeTable || t('context.pick_table_short') }}</span>
      </span>
    </button>

    <button v-if="showRx" class="chip" :class="{ filled: store.context.rx_number }" @click="emit('add-rx')">
      <span class="chip-icon">℞</span>
      <span class="chip-label">
        <span class="chip-title">{{ t('context.rx_chip') }}</span>
        <span class="chip-value">{{ store.context.rx_number || t('context.add_rx_short') }}</span>
      </span>
    </button>

    <button v-if="showBatch" class="chip" :class="{ filled: store.context.batch }" @click="emit('pick-batch')">
      <span class="chip-icon">⌬</span>
      <span class="chip-label">
        <span class="chip-title">{{ t('context.batch_chip') }}</span>
        <span class="chip-value">{{ store.context.batch || t('context.pick_batch_short') }}</span>
      </span>
    </button>

    <button v-if="showAppt" class="chip" :class="{ filled: store.context.appointment }" @click="emit('pick-appointment')">
      <span class="chip-icon">⏱</span>
      <span class="chip-label">
        <span class="chip-title">{{ t('context.appt_chip') }}</span>
        <span class="chip-value">{{ store.context.appointment || t('context.pick_appt_short') }}</span>
      </span>
    </button>
  </div>
</template>

<style scoped>
.ribbon {
  display: flex;
  gap: 6px;
  padding: 10px 18px;
  background: var(--surface);
  border-block-end: 1px solid var(--border);
  overflow-x: auto;
  scrollbar-width: none;
}
.ribbon::-webkit-scrollbar { display: none; }
.chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  border: 1px solid transparent;
  font-size: 12px;
  color: var(--text);
  flex-shrink: 0;
  transition: background var(--t-fast), border-color var(--t-fast);
}
.chip:hover { background: var(--surface); border-color: var(--accent); }
.chip.filled { background: var(--accent-soft); color: var(--accent); }
.chip-icon { font-size: 14px; line-height: 1; }
.chip-label { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.1; gap: 1px; }
.chip-title { font-size: 9px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.4px; }
.chip-value { font-size: 12px; font-weight: 500; }
</style>
