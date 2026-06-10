<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useSyncStore } from '../stores/sync'
import { modifiersForItem } from '../composables/modifiers'

import SidebarPanel  from '../components/SidebarPanel.vue'
import MenuPanel     from '../components/MenuPanel.vue'
import CartPanel     from '../components/CartPanel.vue'
import PaymentDialog from '../components/PaymentDialog.vue'
import CustomerPicker from '../components/CustomerPicker.vue'
import LoyaltyScan   from '../components/LoyaltyScan.vue'
import HeldOrders    from '../components/HeldOrders.vue'
import ModifierPicker from '../components/ModifierPicker.vue'
import SplitBill     from '../components/SplitBill.vue'
import TablePicker   from '../components/TablePicker.vue'
import RxCapture     from '../components/RxCapture.vue'
import HardwareSettings from '../components/HardwareSettings.vue'
import CartLineActions from '../components/CartLineActions.vue'
import QueueInspector from '../components/QueueInspector.vue'
import Toaster       from '../components/Toaster.vue'

const { t } = useI18n()
const store = usePOSStore()
const sync = useSyncStore()
const toaster = ref(null)

const showPayment   = ref(false)
const showCustomer  = ref(false)
const showLoyalty   = ref(false)
const showHeld      = ref(false)
const showSplit     = ref(false)
const showTable     = ref(false)
const showRx        = ref(false)
const showHardware  = ref(false)
const showQueue     = ref(false)
const lineActionsLine = ref(null)
const modifierLine  = ref(null)
const modifierItem  = ref(null)
const modifierGroups = ref([])

const isMockMode = computed(() => store.boot?._mock)

onMounted(() => {
  if (store.boot) store.loadMenu()
})

watch(() => store.boot, (b) => { if (b) store.loadMenu() })

function pickFromMenu(item) {
  if (item._scaleHit) {
    store.addToCart(item, { qty: item._scaleHit.qty, override_rate: item._scaleHit.override_rate })
    toaster.value?.show(
      t('scale.detected_weight', { weight: item._scaleHit.qty }),
      'success'
    )
    return
  }
  // If the item has modifiers AND the active domain uses them, open the dialog
  const groups = modifiersForItem(item)
  if (groups.length > 0 && store.activeFeatures.uses_modifiers) {
    modifierItem.value = item
    modifierGroups.value = groups
    modifierLine.value = null
    return
  }
  store.addToCart(item)
}

function editModifiers(line) {
  const item = (store.menuItems || []).find(i => i.item_code === line.item_code) ||
    { item_code: line.item_code, item_name: line.item_name, standard_rate: line.rate }
  modifierItem.value = item
  modifierGroups.value = modifiersForItem(item)
  modifierLine.value = line
}

function applyModifierChoice(chosen) {
  if (modifierLine.value) {
    store.applyModifiers(modifierLine.value.line_uuid, chosen)
  } else {
    // brand-new line, with modifiers
    store.addToCart(modifierItem.value, {
      qty: 1,
      override_rate: chosen.base_rate,
      modifiers: chosen.options || [],
      unique: true,
    })
    // re-apply rate including deltas
    const lastLine = store.cart[store.cart.length - 1]
    if (lastLine) store.applyModifiers(lastLine.line_uuid, chosen)
  }
  modifierLine.value = null
  modifierItem.value = null
  modifierGroups.value = []
}

function holdOrder() {
  if (store.holdCart()) toaster.value?.show(t('cart.hold'), 'success')
}

function onSaleComplete(name, queued) {
  showPayment.value = false
  store.clearCart()
  if (queued) {
    toaster.value?.show(t('sync.sale_queued', { name }), 'warn', 5000)
  } else {
    toaster.value?.show(t('payment.sale_complete', { name }), 'success', 4000)
  }
}

function openFloorPlan() {
  window.open('/app/alphax-floor-designer', '_blank')
}
</script>

<template>
  <div class="cashier-shell">
    <div v-if="isMockMode" class="mock-banner">{{ t('dev.mock_banner') }}</div>
    <div v-if="!sync.online" class="offline-banner">
      <span class="offline-icon">⚠</span>
      <span>{{ t('sync.offline_banner') }}</span>
      <span v-if="sync.counts.pending > 0" class="offline-count">
        ({{ t('sync.n_pending', sync.counts.pending, { n: sync.counts.pending }) }})
      </span>
    </div>

    <div class="three-col">
      <SidebarPanel
        @hold="holdOrder"
        @recall="showHeld = true"
        @open-held="showHeld = true"
        @add-customer="showCustomer = true"
        @scan-loyalty="showLoyalty = true"
        @open-floor="openFloorPlan"
        @open-hardware="showHardware = true"
        @open-queue="showQueue = true"
      />
      <MenuPanel @pick="pickFromMenu" />
      <CartPanel
        @pay="showPayment = true"
        @add-customer="showCustomer = true"
        @scan-loyalty="showLoyalty = true"
        @pick-table="showTable = true"
        @add-rx="showRx = true"
        @pick-batch="() => {}"
        @pick-appointment="() => {}"
        @edit-modifiers="editModifiers"
        @split-bill="showSplit = true"
        @line-actions="(line) => lineActionsLine = line"
      />
    </div>

    <PaymentDialog v-if="showPayment"
      @close="showPayment = false"
      @sale-complete="onSaleComplete"
    />
    <CustomerPicker v-if="showCustomer" @close="showCustomer = false" />
    <LoyaltyScan v-if="showLoyalty" @close="showLoyalty = false" />
    <HeldOrders v-if="showHeld" @close="showHeld = false" />

    <ModifierPicker v-if="modifierItem && modifierGroups.length"
      :item-name="modifierItem.item_name || modifierItem.item_code"
      :base-rate="modifierItem.standard_rate || 0"
      :groups="modifierGroups"
      @close="modifierItem = null; modifierGroups = []; modifierLine = null"
      @apply="applyModifierChoice"
    />

    <SplitBill v-if="showSplit" @close="showSplit = false" />
    <TablePicker v-if="showTable" @close="showTable = false" />
    <RxCapture v-if="showRx" @close="showRx = false" />
    <HardwareSettings v-if="showHardware" @close="showHardware = false" />
    <CartLineActions v-if="lineActionsLine" :line="lineActionsLine"
      @close="lineActionsLine = null"
      @edit-modifiers="(line) => { lineActionsLine = null; editModifiers(line) }" />
    <QueueInspector v-if="showQueue" @close="showQueue = false" />

    <Toaster ref="toaster" />
  </div>
</template>

<style scoped>
.cashier-shell {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.mock-banner {
  padding: 6px 14px;
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 12px;
  font-weight: 500;
  text-align: center;
  border-block-end: 1px solid var(--border);
}
.offline-banner {
  padding: 8px 14px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12px;
  font-weight: 500;
  text-align: center;
  border-block-end: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.offline-icon { font-size: 14px; }
.offline-count { opacity: 0.8; }
.three-col {
  flex: 1;
  display: grid;
  grid-template-columns: 220px 1fr 380px;
  min-height: 0;
}
@media (max-width: 1100px) {
  .three-col { grid-template-columns: 200px 1fr 340px; }
}
@media (max-width: 900px) {
  .three-col { grid-template-columns: 64px 1fr 300px; }
}
</style>
