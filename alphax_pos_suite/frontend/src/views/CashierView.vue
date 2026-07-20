<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useSyncStore } from '../stores/sync'
import { modifiersForItem } from '../composables/modifiers'
import { useBarcodeScanner } from '../composables/useBarcodeScanner'

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
import ManagerPinDialog from '../components/ManagerPinDialog.vue'
import ReturnDialog from '../components/ReturnDialog.vue'
import ConfigPanel from '../components/ConfigPanel.vue'
import DeliveryPlatformPicker from '../components/DeliveryPlatformPicker.vue'
import ShiftDialog from '../components/ShiftDialog.vue'
import Toaster       from '../components/Toaster.vue'

const { t } = useI18n()
const store = usePOSStore()
const sync = useSyncStore()
const toaster = ref(null)

// Hardware barcode scanners (keyboard-wedge) -> resolve & add to cart.
// Fires only when no text field is focused, so the search box still works.
useBarcodeScanner(async (code) => {
  const res = await store.scan(code)
  if (res && res.found) {
    toaster.value?.show?.(`${res.item_name} \u2713`, 'success')
  } else if (store.scanError) {
    toaster.value?.show?.(store.scanError, 'error')
  }
})

const showPayment   = ref(false)
const showCustomer  = ref(false)
const showLoyalty   = ref(false)
const showHeld      = ref(false)
const showSplit     = ref(false)
const showTable     = ref(false)
const showRx        = ref(false)
const showHardware  = ref(false)
const showQueue     = ref(false)
const showConfig    = ref(false)
const showHistory   = ref(false)
const showDayClose  = ref(false)
const showDelivery  = ref(false)
const showShift     = ref(false)
const shiftMode     = ref('auto')
const showReturn    = ref(false)
const lineActionsLine = ref(null)

// ---- manager approval broker --------------------------------------------
// Child components emit `request-approval` with { action, run }. We show
// the PIN dialog; on success we execute the continuation. One pending
// approval at a time — the POS is a single-operator surface.
const pendingApproval = ref(null)   // { action, run }

function requestApproval(req) {
  pendingApproval.value = req
}

function onApproved({ manager_name }) {
  const req = pendingApproval.value
  pendingApproval.value = null
  if (req?.run) req.run()
  toaster.value?.show(t('security.approved_by', { name: manager_name }), 'success')
}

// ---- return mode ----------------------------------------------------------
function startReturn() {
  // Toggle off is always free — it only ever makes the next sale a
  // normal one again.
  if (store.returnMode) {
    store.setReturnMode(false)
    return
  }
  if (!store.settings.allow_returns) {
    toaster.value?.show(t('returns.disabled'), 'error')
    return
  }
  if (store.cart.length > 0) {
    toaster.value?.show(t('returns.clear_cart_first'), 'warn')
    return
  }
  // Entering return mode is gated behind the same manager policy as
  // voids — a return is economically a void of a past sale.
  if (store.settings.require_manager_for_void) {
    requestApproval({ action: 'Return', run: () => (showReturn.value = true) })
  } else {
    showReturn.value = true
  }
}

function confirmReturn(reason) {
  store.setReturnMode(true, reason)
  toaster.value?.show(t('returns.active_toast'), 'warn', 3500)
}

const modifierLine  = ref(null)
const modifierItem  = ref(null)
const modifierGroups = ref([])

const isMockMode = computed(() => store.boot?._mock)

// ---- shell geometry --------------------------------------------------------
// v15.7.4 sized the shell with `top: var(--navbar-height, 60px)`, but
// nothing ever SET that variable — every install ran on the 60px guess.
// Branded navbars (client logo), zoom levels and OS font scaling make the
// real navbar taller, and `position: fixed` additionally stops being
// viewport-fixed the moment any desk ancestor carries a CSS transform or
// filter (it becomes relative to that ancestor). Both failure modes push
// the Pay footer below the fold with the page unscrollable (reported from
// production, WhiteHelmet site).
//
// The fix measures instead of guessing, then VERIFIES its own result:
//   pass 1: top = real navbar bottom, height = viewport − navbar bottom
//   pass 2 (next frame): read the shell's actual on-screen rect; any
//           residual delta (transformed-ancestor containing block) is
//           subtracted so the shell lands exactly where intended.
// Re-runs on window resize and whenever the navbar itself resizes.
// `overflow-y: auto` in CSS is the last-resort net: if geometry is ever
// wrong again, content scrolls — it can never be unreachable.
const shellEl = ref(null)
let _navRO = null

function _navbarBottom() {
  const nav = document.querySelector('header.navbar, .navbar')
  if (!nav) return 60
  const b = nav.getBoundingClientRect().bottom
  // A hidden/detached navbar reports 0 — keep the fallback then.
  return b > 8 ? Math.round(b) : 60
}

function layoutShell() {
  const el = shellEl.value
  if (!el) return
  const navBottom = _navbarBottom()
  const vh = window.innerHeight
  el.style.top = navBottom + 'px'
  el.style.left = '0px'
  el.style.bottom = 'auto'
  el.style.height = Math.max(320, vh - navBottom) + 'px'
  requestAnimationFrame(() => {
    if (!shellEl.value) return
    const rect = el.getBoundingClientRect()
    const dTop = Math.round(rect.top - navBottom)
    if (Math.abs(dTop) > 1) el.style.top = (parseFloat(el.style.top) - dTop) + 'px'
    const dLeft = Math.round(rect.left)
    if (Math.abs(dLeft) > 1) el.style.left = (parseFloat(el.style.left) - dLeft) + 'px'
  })
}

// ---- collapsible sidebar rail ---------------------------------------------
// Collapsed 64px icon rail by default: labels stop being read after day
// two, grid space never stops mattering. Tap the rail toggle to pin it
// open; state persists per terminal. Mouse users additionally get
// hover-expand (300ms intent delay) as an overlay that does not reflow
// the grid — see SidebarPanel.
const RAIL_KEY = 'alphax_rail_pinned'
const railPinned = ref(localStorage.getItem(RAIL_KEY) === '1')
function toggleRail() {
  railPinned.value = !railPinned.value
  localStorage.setItem(RAIL_KEY, railPinned.value ? '1' : '0')
}

onMounted(() => {
  if (store.boot) store.loadMenu()
  layoutShell()
  window.addEventListener('resize', layoutShell)
  const nav = document.querySelector('header.navbar, .navbar')
  if (nav && window.ResizeObserver) {
    _navRO = new ResizeObserver(layoutShell)
    _navRO.observe(nav)
  }
  // Fonts landing late can change navbar height by a pixel or two.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layoutShell)
})

onUnmounted(() => {
  window.removeEventListener('resize', layoutShell)
  if (_navRO) { _navRO.disconnect(); _navRO = null }
})

watch(() => store.boot, (b) => { if (b) store.loadMenu() })

const comboToPick = ref(null)
function pickCombo(cb) {
  if (cb.combo_type === 'Fixed') {
    // Combo B: delivered exactly as configured — no editing surface.
    store.addComboToCart(cb, {
      components: cb.components.map(k => ({
        item_code: k.item_code,
        item_name: (store.menuItems.find(i => i.item_code === k.item_code) || {}).item_name || k.item_code,
        item_group: (store.menuItems.find(i => i.item_code === k.item_code) || {}).item_group,
        qty: k.qty || 1, substituted: false, default_item: k.item_code,
      })),
      price: cb.combo_price,
    })
    return
  }
  comboToPick.value = cb
}
function applyCombo(choice) {
  store.addComboToCart(comboToPick.value, choice)
  comboToPick.value = null
}

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

async function startPay() {
  // Policy: no sale without an open shift when the setting demands it.
  if (store.settings.require_shift_open && !store.shift) {
    toaster.value?.show(t('shift.required_toast'), 'warn')
    shiftMode.value = 'open'
    showShift.value = true
    return
  }
  // Credit and Delivery bypass the tender screen: Credit posts an
  // outstanding invoice on the customer; Delivery posts the full
  // amount to the platform's Mode of Payment (already collected by
  // the app). Everything else tenders normally.
  if (store.orderType === 'Credit') {
    if (!store.customer) {
      toaster.value?.show(t('order_type.credit_needs_customer'), 'warn')
      showCustomer.value = true
      return
    }
    await directSubmit()
    return
  }
  if (store.orderType === 'Delivery') {
    if (!store.deliveryPlatform) {
      showDelivery.value = true
      return
    }
    await directSubmit()
    return
  }
  showPayment.value = true
}

async function directSubmit() {
  try {
    const res = await store.submitSale()
    onSaleComplete(res.name, res.queued)
  } catch (e) {
    if (String(e.message) === 'CREDIT_NEEDS_CUSTOMER') {
      toaster.value?.show(t('order_type.credit_needs_customer'), 'warn')
      showCustomer.value = true
    } else {
      toaster.value?.show(e.message || String(e), 'error', 6000)
    }
  }
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
  <div class="cashier-shell" ref="shellEl">
    <div v-if="isMockMode" class="mock-banner">{{ t('dev.mock_banner') }}</div>
    <div v-if="!sync.online" class="offline-banner">
      <span class="offline-icon">⚠</span>
      <span>{{ t('sync.offline_banner') }}</span>
      <span v-if="sync.counts.pending > 0" class="offline-count">
        ({{ t('sync.n_pending', sync.counts.pending, { n: sync.counts.pending }) }})
      </span>
    </div>

    <div class="three-col" :class="{ 'rail-collapsed': !railPinned }">
      <div class="rail-cell">
      <SidebarPanel
        :collapsed="!railPinned"
        @toggle-rail="toggleRail"
        @hold="holdOrder"
        @recall="showHeld = true"
        @open-held="showHeld = true"
        @add-customer="showCustomer = true"
        @scan-loyalty="showLoyalty = true"
        @open-floor="openFloorPlan"
        @open-hardware="showHardware = true"
        @open-queue="showQueue = true"
        @open-history="showHistory = true"
        @open-dayclose="showDayClose = true"
        @start-return="startReturn"
        @open-shift="(m) => { shiftMode = m || 'auto'; showShift = true }"
        @open-config="showConfig = true"
      />
      </div>
      <MenuPanel @pick="pickFromMenu" @pick-combo="pickCombo" />
      <CartPanel
        @pick-delivery="showDelivery = true"
        @pay="startPay"
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
    <InvoiceHistory v-if="showHistory" @close="showHistory = false" />
    <ComboPicker v-if="comboToPick" :combo="comboToPick"
      @close="comboToPick = null" @apply="applyCombo" />
    <DayCloseDialog v-if="showDayClose" @close="showDayClose = false" />
    <TablePicker v-if="showTable" @close="showTable = false" />
    <RxCapture v-if="showRx" @close="showRx = false" />
    <HardwareSettings v-if="showHardware" @close="showHardware = false" />
    <CartLineActions v-if="lineActionsLine" :line="lineActionsLine"
      @close="lineActionsLine = null"
      @request-approval="requestApproval"
      @edit-modifiers="(line) => { lineActionsLine = null; editModifiers(line) }" />
    <QueueInspector v-if="showQueue" @close="showQueue = false" />

    <ManagerPinDialog v-if="pendingApproval"
      :action="pendingApproval.action"
      @close="pendingApproval = null"
      @authorized="onApproved"
    />
    <ReturnDialog v-if="showReturn"
      @close="showReturn = false"
      @confirm="confirmReturn"
    />
    <ConfigPanel v-if="showConfig" @close="showConfig = false" />
    <DeliveryPlatformPicker v-if="showDelivery" @close="showDelivery = false" />
    <ShiftDialog v-if="showShift" :initial-mode="shiftMode" @close="showShift = false" @request-approval="requestApproval" />

    <Toaster ref="toaster" />
  </div>
</template>

<style scoped>
.cashier-shell {
  /* Fill everything BELOW the desk navbar. The values here are only
     first-paint fallbacks — layoutShell() (script above) measures the
     real navbar at runtime, sets top/height explicitly, and verifies
     its own result against the on-screen rect to survive transformed
     desk ancestors. overflow-y:auto is the last-resort net: if
     geometry is ever wrong, content scrolls instead of clipping —
     Pay can never be unreachable again. */
  position: fixed;
  top: 60px;
  left: 0; right: 0;
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  background: var(--bg);
  overflow-y: auto;
  overscroll-behavior: none;
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
/* Collapsed rail: 64px icon column. The freed ~156px goes straight to
   the item grid — a full extra card column at current sizing. */
.three-col.rail-collapsed { grid-template-columns: 64px 1fr 380px; }
/* Positioning context so the hover-expanded sidebar can overlay the
   menu grid without reflowing it. */
.rail-cell { position: relative; min-height: 0; display: flex; }
@media (max-width: 1100px) {
  .three-col { grid-template-columns: 200px 1fr 340px; }
  .three-col.rail-collapsed { grid-template-columns: 64px 1fr 340px; }
}
@media (max-width: 900px) {
  .three-col, .three-col.rail-collapsed { grid-template-columns: 64px 1fr 300px; }
}
</style>
