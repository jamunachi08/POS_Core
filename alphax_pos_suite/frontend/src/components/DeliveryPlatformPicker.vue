<script setup>
// Delivery platform picker. Platforms come from the AlphaX Delivery
// Platform master (HungerStation, Keeta, Jahez, Jeeny, Noon, …) via
// pos_boot; picking one sets the order type to Delivery and routes the
// full sale amount to that platform's Mode of Payment on submit.
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['close'])

function pick(p) {
  store.setOrderType('Delivery', p)
  emit('close')
}
</script>

<template>
  <AppModal :title="t('order_type.pick_platform')" @close="emit('close')">
    <div class="dp-list" v-if="store.deliveryPlatforms.length">
      <button
        v-for="p in store.deliveryPlatforms"
        :key="p.name"
        class="dp-item"
        :class="{ active: store.deliveryPlatform && store.deliveryPlatform.name === p.name }"
        @click="pick(p)"
      >
        <span class="dp-icon">🛵</span>
        <span class="dp-name">{{ p.platform_name }}</span>
        <span class="dp-meta" v-if="p.commission_percent">
          {{ t('order_type.commission') }} {{ p.commission_percent }}%
        </span>
        <span class="dp-mop" v-if="p.mode_of_payment">{{ p.mode_of_payment }}</span>
      </button>
    </div>
    <div v-else class="dp-empty">
      {{ t('order_type.no_platforms') }}
      <div class="dp-empty-hint">{{ t('order_type.no_platforms_hint') }}</div>
    </div>
  </AppModal>
</template>

<style scoped>
.dp-list { display: flex; flex-direction: column; gap: 8px; min-width: 320px; }
.dp-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px; /* touch target */
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--text);
  font-size: 14px;
  text-align: start;
}
.dp-item:active { transform: scale(0.99); }
.dp-item.active { border-color: var(--accent); background: var(--accent-soft); }
.dp-icon { font-size: 18px; }
.dp-name { font-weight: 600; flex: 1; }
.dp-meta { font-size: 11.5px; color: var(--text-muted); }
.dp-mop {
  font-size: 10.5px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-muted);
}
.dp-empty { padding: 18px 6px; color: var(--text-muted); font-size: 13.5px; min-width: 300px; }
.dp-empty-hint { margin-top: 8px; font-size: 12px; }
</style>
