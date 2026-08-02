<script setup>
// Order-type selector shown at the top of the cart.
//
// Behavior contract (mirrors the store's submitSale):
//   Dine In / Takeaway / Staff → normal tender flow.
//   Delivery → must pick a platform (parent opens the picker); posts
//              the full amount to that platform's Mode of Payment.
//   Credit   → requires a named customer; posts an outstanding
//              Sales Invoice with no payments.
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['pick-delivery', 'need-customer'])

const ICONS = { 'Dine In': '🍽', 'Takeaway': '🥡', 'Delivery': '🛵', 'Staff': '🧑‍🍳', 'Credit': '📒' }

function choose(type) {
  if (type === 'Delivery') {
    // Parent opens the platform picker; type is set on confirm.
    emit('pick-delivery')
    return
  }
  if (type === 'Credit' && !store.customer) {
    emit('need-customer')
    return
  }
  store.setOrderType(type)
}
</script>

<template>
  <div class="otb">
    <button
      v-for="type in store.ORDER_TYPES"
      :key="type"
      class="otb-btn"
      :class="{ active: store.orderType === type }"
      @click="choose(type)"
    >
      <span class="otb-icon">{{ ICONS[type] }}</span>
      <span class="otb-label">{{ t(`order_type.${type.toLowerCase().replace(' ', '_')}`) }}</span>
    </button>
  </div>
  <div v-if="store.orderType === 'Delivery' && store.deliveryPlatform" class="otb-platform">
    🛵 {{ store.deliveryPlatform.platform_name }}
    <button class="otb-platform-change" @click="emit('pick-delivery')">{{ t('order_type.change') }}</button>
  </div>
</template>

<style scoped>
.otb {
  display: flex;
  gap: 6px;
  padding: 10px 12px 6px;
  background: var(--surface);
  overflow-x: auto;
  scrollbar-width: none;
}
.otb::-webkit-scrollbar { display: none; }
.otb-btn {
  flex: 1;
  min-width: 64px;
  min-height: 52px; /* touch target */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 6px 8px;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  transition: all 0.12s ease;
}
.otb-btn:active { transform: scale(0.97); }
.otb-btn.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}
.otb-icon { font-size: 17px; line-height: 1; }
.otb-label { white-space: nowrap; }
.otb-platform {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12.5px;
  font-weight: 600;
}
.otb-platform-change {
  margin-inline-start: auto;
  font-size: 11.5px;
  color: var(--accent);
  text-decoration: underline;
  min-height: 32px;
}
</style>
