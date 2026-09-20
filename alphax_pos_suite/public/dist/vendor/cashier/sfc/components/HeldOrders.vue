<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const { t, locale } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()
const emit = defineEmits(['close'])

const held = ref(store.listHeld())

function recall(idx) {
  store.recallHeld(idx)
  emit('close')
}

function lineCount(h) { return h.cart.length }
function total(h) { return h.cart.reduce((s, l) => s + l.qty * l.rate, 0) }
function timeStr(ts) {
  return new Date(ts).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <AppModal :title="t('cart.held_orders')" size="md" @close="emit('close')">
    <div v-if="held.length === 0" class="muted">{{ t('cart.no_held_orders') }}</div>
    <div v-else class="list">
      <button
        v-for="(h, idx) in held"
        :key="h.uuid"
        class="held-card"
        @click="recall(idx)"
      >
        <div class="row">
          <div class="customer">{{ h.customer || t('cart.walk_in') }}</div>
          <div class="amount tnum">{{ fmt(total(h)) }}</div>
        </div>
        <div class="row sub">
          <div class="meta">{{ t('cart.item_count', lineCount(h), { n: lineCount(h) }) }}</div>
          <div class="meta">{{ t('cart.held_at', { time: timeStr(h.ts) }) }}</div>
        </div>
        <div v-if="h.domain" class="domain-tag">{{ t(`domains.${h.domain}`) }}</div>
      </button>
    </div>
  </AppModal>
</template>

<style scoped>
.muted { color: var(--text-dim); padding: 30px; text-align: center; font-size: 13px; }
.list { display: flex; flex-direction: column; gap: 8px; max-height: 60vh; overflow-y: auto; }
.held-card {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 12px 14px;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
}
.held-card:hover { background: var(--surface-2); border-color: var(--accent); }
.row { display: flex; justify-content: space-between; align-items: center; }
.customer { font-size: 13px; font-weight: 500; color: var(--text); }
.amount { font-size: 14px; font-weight: 600; }
.sub { font-size: 11px; color: var(--text-muted); }
.domain-tag {
  position: absolute;
  inset-block-start: 8px;
  inset-inline-end: 12px;
  font-size: 10px;
  color: var(--text-muted);
  padding: 1px 8px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
}
</style>
