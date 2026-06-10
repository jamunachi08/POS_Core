<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import { haptics } from '../composables/haptics'
import AppModal from './AppModal.vue'
import NumericKeypad from './NumericKeypad.vue'

const props = defineProps({
  line: { type: Object, required: true }
})
const emit = defineEmits(['close', 'edit-modifiers'])

const { t } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()

const mode = ref('menu')   // 'menu' | 'qty' | 'discount' | 'note'
const buf = ref('')
const note = ref(props.line.notes || '')

function showQty()      { mode.value = 'qty';      buf.value = String(props.line.qty); }
function showDiscount() { mode.value = 'discount'; buf.value = '0'; }
function showNote()     { mode.value = 'note';     note.value = props.line.notes || ''; }

function applyQty() {
  const v = parseFloat(buf.value)
  if (!isNaN(v) && v > 0) {
    store.setQty(props.line.line_uuid, v)
    haptics.success()
  }
  emit('close')
}

function applyDiscount() {
  // Treat the entered number as a percentage off the original rate.
  // Multiplicative — keeps modifier deltas intact.
  const pct = parseFloat(buf.value)
  if (isNaN(pct) || pct <= 0) return emit('close')
  const factor = Math.max(0, Math.min(100, pct)) / 100
  const newRate = +(props.line.rate * (1 - factor)).toFixed(4)
  store.setRate(props.line.line_uuid, newRate)
  haptics.success()
  emit('close')
}

function applyNote() {
  store.setNotes(props.line.line_uuid, note.value)
  haptics.success()
  emit('close')
}

function voidLine() {
  if (confirm(t('cart_actions.confirm_void'))) {
    store.removeLine(props.line.line_uuid)
    haptics.warn()
    emit('close')
  }
}

function gotoModifiers() {
  emit('edit-modifiers', props.line)
  emit('close')
}

const title = computed(() => props.line.item_name)
</script>

<template>
  <AppModal :title="title" size="sm" @close="emit('close')">

    <!-- Main menu -->
    <div v-if="mode === 'menu'" class="action-grid">
      <button class="action" @click="showQty">
        <span class="ic">×</span>
        <span class="lbl">{{ t('cart_actions.set_qty') }}</span>
      </button>
      <button class="action" @click="showDiscount">
        <span class="ic">%</span>
        <span class="lbl">{{ t('cart_actions.discount') }}</span>
      </button>
      <button class="action" @click="gotoModifiers" v-if="store.activeFeatures.uses_modifiers">
        <span class="ic">⚙</span>
        <span class="lbl">{{ t('cart.edit_modifiers') }}</span>
      </button>
      <button class="action" @click="showNote">
        <span class="ic">✎</span>
        <span class="lbl">{{ t('cart_actions.note') }}</span>
      </button>
      <button class="action danger" @click="voidLine">
        <span class="ic">⌫</span>
        <span class="lbl">{{ t('cart_actions.void') }}</span>
      </button>
    </div>

    <!-- Qty entry -->
    <div v-else-if="mode === 'qty'" class="entry">
      <div class="entry-label">{{ t('cart.qty') }}</div>
      <div class="entry-display tnum">{{ buf || '0' }}</div>
      <NumericKeypad v-model="buf" @clear="buf = ''" />
      <div class="entry-actions">
        <button class="btn" @click="mode = 'menu'">{{ t('app.back') }}</button>
        <button class="btn btn-primary" @click="applyQty">{{ t('app.confirm') }}</button>
      </div>
    </div>

    <!-- Discount entry -->
    <div v-else-if="mode === 'discount'" class="entry">
      <div class="entry-label">{{ t('cart_actions.discount_percent') }}</div>
      <div class="entry-display tnum">{{ buf || '0' }}%</div>
      <NumericKeypad v-model="buf" @clear="buf = ''" />
      <div class="entry-actions">
        <button class="btn" @click="mode = 'menu'">{{ t('app.back') }}</button>
        <button class="btn btn-primary" @click="applyDiscount">{{ t('payment.apply') }}</button>
      </div>
    </div>

    <!-- Note entry -->
    <div v-else-if="mode === 'note'" class="entry">
      <div class="entry-label">{{ t('cart.notes') }}</div>
      <textarea class="input note-input" v-model="note" rows="4"
        :placeholder="t('cart.line_note_placeholder')" autofocus></textarea>
      <div class="entry-actions">
        <button class="btn" @click="mode = 'menu'">{{ t('app.back') }}</button>
        <button class="btn btn-primary" @click="applyNote">{{ t('app.save') }}</button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.action-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 18px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--text);
  min-height: 90px;
  transition: background var(--t-fast), border-color var(--t-fast);
}
.action:hover { background: var(--surface-2); border-color: var(--accent); }
.action:active { transform: scale(0.97); }
.action.danger { color: var(--danger); }
.action.danger:hover { background: var(--danger-soft); border-color: var(--danger); }
.ic { font-size: 24px; line-height: 1; opacity: 0.7; }
.lbl { font-size: 12px; font-weight: 500; }

.entry { display: flex; flex-direction: column; gap: 12px; }
.entry-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}
.entry-display {
  font-size: 32px;
  font-weight: 600;
  text-align: center;
  padding: 14px;
  background: var(--surface-2);
  border-radius: var(--r-md);
  color: var(--text);
}
.entry-actions { display: flex; gap: 8px; }
.entry-actions .btn { flex: 1; padding: 12px; }
.note-input {
  resize: vertical;
  font-family: var(--font-sans);
}
</style>
