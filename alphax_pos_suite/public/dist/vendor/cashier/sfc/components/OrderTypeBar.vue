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
const emit = defineEmits(['pick-delivery', 'need-customer', 'pick-table'])

// Fallback glyphs for a site whose modes predate the icon field.
const ICONS = { 'Dine In': '🍽', 'Takeaway': '🥡', 'Delivery': '🛵', 'Staff': '🧑‍🍳', 'Credit': '📒', 'Room Service': '🛎' }

function iconFor(def) {
  return def.icon || ICONS[def.order_type_name] || '•'
}

// Modes carry their own translations for the five shipped names; anything
// an operator adds falls back to the name as typed on the doctype.
function labelFor(def) {
  const key = `order_type.${def.order_type_name.toLowerCase().replace(/\s+/g, '_')}`
  const translated = t(key)
  return translated === key ? def.order_type_name : translated
}

function choose(def) {
  const type = def.order_type_name
  // Requirements are declared on the mode, so the bar asks for whatever
  // that mode needs rather than testing for two hard-coded names.
  if (def.requires_delivery_platform) {
    // Parent opens the platform picker; type is set on confirm.
    emit('pick-delivery')
    return
  }
  if (def.requires_customer && !store.customer) {
    emit('need-customer')
    return
  }
  store.setOrderType(type)
  // A mode that must be seated opens the floor plan straight away —
  // one tap instead of a rejected payment two minutes later.
  if (def.table_policy === 'Mandatory' && !store.activeTable) emit('pick-table')
}
</script>

<template>
  <div class="otb">
    <button
      v-for="def in store.orderTypeDefs"
      :key="def.order_type_name"
      class="otb-btn"
      :class="{ active: store.orderType === def.order_type_name }"
      @click="choose(def)"
    >
      <span class="otb-icon">{{ iconFor(def) }}</span>
      <span class="otb-label">{{ labelFor(def) }}</span>
    </button>
  </div>
  <div v-if="store.activeOrderType.requires_delivery_platform && store.deliveryPlatform" class="otb-platform">
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
