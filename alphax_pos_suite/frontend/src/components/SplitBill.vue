<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()
const emit = defineEmits(['close'])

// Local seat structure: { id, label, line_uuids: [] }
// Lines not assigned to any seat fall into "unassigned".
const seatCount = ref(2)
const assignments = ref({})   // line_uuid -> seat_id (or null)

function seatId(n) { return `S${n + 1}` }
const seats = computed(() => {
  const out = []
  for (let i = 0; i < seatCount.value; i++) {
    const id = seatId(i)
    out.push({
      id,
      label: t('split.seat_n', { n: i + 1 }),
      lines: store.cart.filter(l => assignments.value[l.line_uuid] === id),
    })
  }
  return out
})
const unassigned = computed(() =>
  store.cart.filter(l => !assignments.value[l.line_uuid]))

function assign(line_uuid, seat_id) { assignments.value[line_uuid] = seat_id }
function unassign(line_uuid) { delete assignments.value[line_uuid] }

function seatTotal(seat) {
  return seat.lines.reduce((s, l) => s + l.qty * l.rate, 0)
}
function unassignedTotal() {
  return unassigned.value.reduce((s, l) => s + l.qty * l.rate, 0)
}

function addSeat() { seatCount.value++ }
function removeSeat() {
  if (seatCount.value <= 1) return
  const removed = seatId(seatCount.value - 1)
  for (const k of Object.keys(assignments.value)) {
    if (assignments.value[k] === removed) delete assignments.value[k]
  }
  seatCount.value--
}

function evenSplit() {
  // Distribute lines round-robin
  let i = 0
  for (const l of store.cart) {
    assignments.value[l.line_uuid] = seatId(i % seatCount.value)
    i++
  }
}
</script>

<template>
  <AppModal :title="t('split.title')" size="xl" @close="emit('close')">
    <div class="split-toolbar">
      <div class="muted">{{ t('split.drag_hint') }}</div>
      <div class="seat-controls">
        <button class="btn" @click="evenSplit">{{ t('split.even') }}</button>
        <button class="btn" @click="removeSeat" :disabled="seatCount <= 1">−</button>
        <span class="seat-count tnum">{{ seatCount }}</span>
        <button class="btn" @click="addSeat">+</button>
      </div>
    </div>

    <div class="split-grid">
      <!-- seats -->
      <div v-for="s in seats" :key="s.id" class="seat-col">
        <div class="seat-head">
          <div class="seat-name">{{ s.label }}</div>
          <div class="seat-total tnum">{{ fmt(seatTotal(s)) }}</div>
        </div>
        <div class="seat-body">
          <div v-if="s.lines.length === 0" class="empty-seat">∅</div>
          <button
            v-for="l in s.lines"
            :key="l.line_uuid"
            class="seat-line"
            @click="unassign(l.line_uuid)"
          >
            <span class="sl-qty tnum">{{ l.qty }}×</span>
            <span class="sl-name">{{ l.item_name }}</span>
            <span class="sl-amt tnum">{{ fmt(l.qty * l.rate) }}</span>
          </button>
        </div>
      </div>

      <!-- unassigned column (always visible) -->
      <div class="seat-col unassigned-col">
        <div class="seat-head">
          <div class="seat-name">{{ t('split.unassigned') }}</div>
          <div class="seat-total tnum">{{ fmt(unassignedTotal()) }}</div>
        </div>
        <div class="seat-body">
          <button
            v-for="l in unassigned"
            :key="l.line_uuid"
            class="seat-line"
            @click="assign(l.line_uuid, seats[0]?.id)"
          >
            <span class="sl-qty tnum">{{ l.qty }}×</span>
            <span class="sl-name">{{ l.item_name }}</span>
            <span class="sl-amt tnum">{{ fmt(l.qty * l.rate) }}</span>
          </button>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn" @click="emit('close')">{{ t('app.close') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.split-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-block-end: 12px;
}
.muted { color: var(--text-muted); font-size: 12px; }
.seat-controls { display: flex; align-items: center; gap: 6px; }
.seat-count {
  min-width: 28px;
  text-align: center;
  font-weight: 600;
  font-size: 14px;
}

.split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  max-height: 60vh;
  overflow-y: auto;
}
.seat-col {
  background: var(--surface-2);
  border-radius: var(--r-md);
  display: flex;
  flex-direction: column;
  min-height: 240px;
}
.seat-col.unassigned-col {
  background: var(--bg);
  border: 1px dashed var(--border-strong);
}
.seat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-block-end: 1px solid var(--border);
}
.seat-name { font-size: 12px; font-weight: 600; color: var(--text); }
.seat-total { font-size: 13px; font-weight: 600; color: var(--accent); }

.seat-body {
  flex: 1;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.empty-seat {
  flex: 1;
  display: grid;
  place-items: center;
  color: var(--text-dim);
  font-size: 24px;
  opacity: 0.4;
}
.seat-line {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  text-align: start;
  font-size: 12px;
  color: var(--text);
  width: 100%;
}
.seat-line:hover { border-color: var(--accent); }
.sl-qty { color: var(--text-muted); font-weight: 600; }
.sl-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sl-amt { color: var(--text-muted); font-size: 11px; }
</style>
