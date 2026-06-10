<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useHardwareStore } from '../stores/hardware'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const hw = useHardwareStore()
const { fmt, fmtNumber } = useMoney()
const emit = defineEmits(['close', 'sale-complete'])

const submitting = ref(false)
const error = ref('')

// Tender keypad
const tenderInput = ref('')
const selectedMode = ref(null)

function pressKey(key) {
  if (key === 'C') tenderInput.value = ''
  else if (key === '⌫') tenderInput.value = tenderInput.value.slice(0, -1)
  else if (key === '.') {
    if (!tenderInput.value.includes('.')) tenderInput.value += tenderInput.value === '' ? '0.' : '.'
  } else {
    tenderInput.value += key
  }
}

function pickMode(mode) {
  selectedMode.value = mode
  if (!tenderInput.value) tenderInput.value = store.remaining.toFixed(2)
}

// Modes that should be routed to the card terminal when one is connected.
// User can override by adding `is_card` to the AlphaX POS Profile payment mode.
const CARD_MODE_NAMES = ['Card', 'Credit Card', 'Debit Card', 'Mada', 'Visa', 'Mastercard', 'AMEX']

function isCardMode(mode) {
  if (!mode) return false
  // Check the boot doc's modes for an explicit is_card flag if the user set one.
  const conf = (store.boot?.payment_modes || []).find(m => m.mode_of_payment === mode)
  if (conf && conf.is_card) return true
  return CARD_MODE_NAMES.some(n => mode.toLowerCase().includes(n.toLowerCase().split(' ')[0]))
}

const terminalState = ref({ active: false, msg: '', txn: null })

async function applyTender() {
  if (!selectedMode.value) {
    error.value = t('payment.no_methods')
    return
  }
  const amount = parseFloat(tenderInput.value) || 0
  if (amount <= 0) return

  // If this is a card-style mode and a terminal is connected, route the
  // charge through the bridge instead of just adding tender locally.
  if (isCardMode(selectedMode.value) && hw.terminalReady) {
    await chargeOnTerminal(amount)
    return
  }

  store.tender(selectedMode.value, amount)
  tenderInput.value = ''
  selectedMode.value = null
  error.value = ''
}

async function chargeOnTerminal(amount) {
  terminalState.value = { active: true, msg: t('payment.terminal_waiting'), txn: null }
  error.value = ''
  try {
    const result = await hw.chargeOnTerminal({
      amount,
      currency: store.boot?.currency?.code || 'SAR',
      invoice_ref: store.cartUuid,
      idempotency_key: `${store.cartUuid}-${selectedMode.value}-${amount}`,
      timeout: 90,
    })
    terminalState.value = { active: false, msg: '', txn: result }
    if (result.ok || result.status === 'approved') {
      // Approved — record the tender. Stash the txn metadata so the
      // receipt and the Sales Invoice can carry it.
      store.tender(selectedMode.value, amount, {
        provider_txn_id: result.provider_txn_id,
        auth_code:       result.auth_code,
        masked_pan:      result.masked_pan,
        card_brand:      result.card_brand,
      })
      tenderInput.value = ''
      selectedMode.value = null
    } else if (result.status === 'declined') {
      error.value = t('payment.terminal_declined') + (result.decline_reason ? ` — ${result.decline_reason}` : '')
    } else if (result.status === 'cancelled') {
      error.value = t('payment.terminal_cancelled')
    } else {
      error.value = t('payment.terminal_error') + (result.decline_reason ? ` — ${result.decline_reason}` : '')
    }
  } catch (e) {
    terminalState.value = { active: false, msg: '', txn: null }
    error.value = e.message || t('payment.terminal_error')
  }
}

async function cancelTerminalCharge() {
  await hw.cancelTerminal()
  terminalState.value = { active: false, msg: '', txn: null }
}

function pressQuick(amount) {
  tenderInput.value = amount.toFixed(2)
}

const quickAmounts = computed(() => {
  const t = store.total
  if (t <= 0) return [10, 20, 50, 100]
  // useful denominations near the total
  return [
    Math.ceil(t),
    Math.ceil(t / 5) * 5,
    Math.ceil(t / 10) * 10,
    Math.ceil(t / 50) * 50
  ].filter((v, i, a) => a.indexOf(v) === i).slice(0, 4)
})

const tenderRows = computed(() =>
  Object.entries(store.tendered).map(([mode, amount]) => ({ mode, amount })))

async function complete() {
  if (store.remaining > 0.01) return
  submitting.value = true
  error.value = ''
  try {
    const result = await store.submitSale()
    const saleName = typeof result === 'string' ? result : result.name
    const queued = typeof result === 'object' && result.queued === true

    // Hardware: print receipt + kick drawer if cash was tendered.
    // Failures are non-fatal — the sale is already recorded (or queued).
    if (hw.online) {
      try {
        const receipt = store.buildReceipt(saleName)
        if (queued) receipt.footer = { ...(receipt.footer || {}), line2: 'OFFLINE — will sync' }
        if (hw.printerReady) hw.printReceipt(receipt).catch(() => {})
        const cashTendered = (store.tendered['Cash'] || 0) > 0
        if (cashTendered && hw.drawerReady) hw.kickDrawer().catch(() => {})
        if (hw.displayReady) hw.showOnDisplay({ action: 'thanks' }).catch(() => {})
      } catch {
        // never block sale completion on hardware
      }
    }

    emit('sale-complete', saleName, queued)
  } catch (e) {
    error.value = e.message || t('payment.submit_failed')
  } finally {
    submitting.value = false
  }
}

// Loyalty redemption sub-dialog
const showRedeem = ref(false)
const redeemInput = ref('')

async function applyRedemption() {
  const pts = parseFloat(redeemInput.value)
  if (!pts || pts <= 0) return
  try {
    await store.previewRedemption(pts)
    showRedeem.value = false
    redeemInput.value = ''
  } catch (e) {
    error.value = e.message || ''
  }
}
function clearRedemption() {
  store.clearRedemption()
}
</script>

<template>
  <AppModal :title="t('payment.title')" size="lg" @close="emit('close')">

    <!-- Terminal-waiting overlay: covers the dialog while charge is pending -->
    <div v-if="terminalState.active" class="terminal-overlay">
      <div class="terminal-card">
        <div class="terminal-icon">💳</div>
        <h3>{{ t('payment.terminal_waiting') }}</h3>
        <p class="muted">{{ t('payment.terminal_hint') }}</p>
        <div class="terminal-amount tnum">{{ fmt(parseFloat(tenderInput) || 0) }}</div>
        <div class="terminal-spinner"></div>
        <button class="btn" @click="cancelTerminalCharge">{{ t('app.cancel') }}</button>
      </div>
    </div>

    <div class="pay-grid">
      <!-- LEFT: tender keypad + mode selection -->
      <div class="pay-left">
        <div class="due-row">
          <div class="due-label">{{ t('payment.due') }}</div>
          <div class="due-amount tnum">{{ fmt(store.remaining) }}</div>
        </div>
        <div class="status-row">
          <span v-if="store.change > 0" class="change">
            {{ t('payment.change') }}: <strong class="tnum">{{ fmt(store.change) }}</strong>
          </span>
          <span v-else-if="store.remaining > 0" class="muted">
            {{ t('payment.tendered') }} {{ fmt(store.totalTendered) }} {{ t('payment.of_total', { amount: fmt(store.total) }) }}
          </span>
          <span v-else class="full">{{ t('payment.fully_tendered') }}</span>
        </div>

        <div class="entry-row">
          <input
            class="tender-input tnum"
            v-model="tenderInput"
            :placeholder="store.remaining.toFixed(2)"
          />
          <button class="btn btn-primary apply" @click="applyTender" :disabled="!selectedMode">
            {{ t('app.add') }}
          </button>
        </div>
        <div class="quick" v-if="store.total > 0">
          <button v-for="a in quickAmounts" :key="a" class="quick-btn" @click="pressQuick(a)">
            {{ fmt(a) }}
          </button>
        </div>

        <div class="keypad">
          <button v-for="k in ['1','2','3','4','5','6','7','8','9','.','0','⌫']"
            :key="k" class="key" @click="pressKey(k)">
            {{ k }}
          </button>
        </div>

        <div v-if="tenderRows.length" class="tendered-list">
          <div class="tendered-title">{{ t('payment.tendered') }}</div>
          <div v-for="r in tenderRows" :key="r.mode" class="tendered-row">
            <span>{{ r.mode }}</span>
            <span class="tnum">{{ fmt(r.amount) }}</span>
            <button class="x" @click="store.clearTender(r.mode)">×</button>
          </div>
        </div>
      </div>

      <!-- RIGHT: payment methods -->
      <div class="pay-right">
        <div class="muted-label">{{ t('payment.methods') }}</div>
        <div class="methods">
          <div v-if="(store.boot?.payment_methods || []).length === 0" class="muted">
            {{ t('payment.no_methods') }}
          </div>
          <button
            v-for="m in store.boot?.payment_methods || []"
            :key="m.mode_of_payment"
            class="method"
            :class="{ active: selectedMode === m.mode_of_payment, has: store.tendered[m.mode_of_payment] }"
            @click="pickMode(m.mode_of_payment)"
          >
            <div class="method-name">{{ m.mode_of_payment }}</div>
            <div class="method-amount tnum" v-if="store.tendered[m.mode_of_payment]">
              {{ fmt(store.tendered[m.mode_of_payment]) }}
            </div>
            <div class="method-hint" v-else>{{ t('payment.tap_to_tender') }}</div>
          </button>
        </div>

        <div v-if="store.boot?.features?.uses_loyalty && store.wallet" class="redemption">
          <div v-if="store.redeemValue > 0" class="redeemed-row">
            <span>{{ fmtNumber(store.redeemPoints) }} pts → {{ fmt(store.redeemValue) }}</span>
            <button class="link-danger" @click="clearRedemption">{{ t('app.remove') }}</button>
          </div>
          <button v-else class="btn btn-ghost redeem-btn" @click="showRedeem = true">
            ⭐ {{ t('payment.redeem_points') }} ({{ fmtNumber(store.wallet.current_balance) }} pts)
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-bar">{{ error }}</div>

    <template #footer>
      <button class="btn" @click="emit('close')" :disabled="submitting">
        {{ t('app.cancel') }}
      </button>
      <button
        class="btn btn-primary"
        @click="complete"
        :disabled="submitting || store.remaining > 0.01"
      >
        {{ submitting ? t('payment.submitting') : t('payment.complete_sale') }}
      </button>
    </template>
  </AppModal>

  <AppModal v-if="showRedeem" :title="t('payment.redemption_dialog')" size="sm" @close="showRedeem = false">
    <label class="label">{{ t('payment.points_to_redeem') }}</label>
    <input class="input tnum" type="number" v-model="redeemInput" autofocus />
    <div class="muted" style="margin-top: 8px; font-size: 12px;" v-if="store.wallet">
      Available: {{ fmtNumber(store.wallet.current_balance) }} pts
    </div>
    <template #footer>
      <button class="btn" @click="showRedeem = false">{{ t('app.cancel') }}</button>
      <button class="btn btn-primary" @click="applyRedemption">{{ t('payment.apply') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.terminal-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,0.96);
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-lg);
}
.terminal-card {
  text-align: center;
  padding: 30px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.terminal-icon { font-size: 48px; }
.terminal-card h3 { margin: 0; font-size: 17px; font-weight: 600; }
.terminal-amount {
  font-size: 32px;
  font-weight: 700;
  color: var(--accent);
}
.terminal-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: term-spin 1s linear infinite;
}
@keyframes term-spin { to { transform: rotate(360deg); } }
.pay-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  min-height: 400px;
}

/* LEFT */
.pay-left { display: flex; flex-direction: column; gap: 12px; }
.due-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.due-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.due-amount {
  font-size: 32px;
  font-weight: 600;
  color: var(--accent);
}
.status-row { font-size: 13px; color: var(--text-muted); min-height: 18px; }
.change { color: var(--accent); }
.full { color: var(--accent); font-weight: 500; }

.entry-row {
  display: flex;
  gap: 8px;
}
.tender-input {
  flex: 1;
  padding: 14px 16px;
  font-size: 20px;
  font-weight: 600;
  border-radius: var(--r-md);
  border: 1px solid var(--border-strong);
  background: var(--surface);
  outline: none;
  text-align: end;
}
.tender-input:focus { border-color: var(--accent); }
.apply { padding-inline: 22px; }

.quick { display: flex; gap: 6px; }
.quick-btn {
  flex: 1;
  padding: 8px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.quick-btn:hover { background: var(--surface); border-color: var(--accent); }

.keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.key {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 18px;
  font-weight: 500;
  transition: background var(--t-fast);
}
.key:hover { background: var(--surface-2); }
.key:active { transform: scale(0.96); }

.tendered-list {
  background: var(--surface-2);
  border-radius: var(--r-md);
  padding: 8px 12px;
}
.tendered-title { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-block-end: 4px; }
.tendered-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 13px;
  gap: 8px;
}
.x {
  background: transparent;
  border: none;
  width: 22px; height: 22px;
  border-radius: 50%;
  color: var(--text-dim);
  font-size: 16px;
  line-height: 1;
}
.x:hover { background: var(--danger-soft); color: var(--danger); }

/* RIGHT */
.pay-right { display: flex; flex-direction: column; gap: 12px; }
.muted-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.muted {
  font-size: 13px;
  color: var(--text-dim);
  padding: 20px;
  text-align: center;
}
.methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.method {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 14px 12px;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color var(--t-fast);
}
.method:hover { border-color: var(--accent); }
.method.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.method.has {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.method-name { font-size: 13px; font-weight: 500; color: var(--text); }
.method-amount { font-size: 12px; color: var(--accent); font-weight: 600; }
.method-hint { font-size: 11px; color: var(--text-dim); }

.redemption { margin-block-start: auto; padding-block-start: 12px; border-block-start: 1px solid var(--border); }
.redeemed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--accent-soft);
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--accent);
  font-weight: 500;
}
.link-danger {
  background: transparent;
  border: none;
  color: var(--danger);
  font-size: 12px;
  font-weight: 500;
}
.redeem-btn { width: 100%; justify-content: center; padding: 12px; }

.error-bar {
  margin-block-start: 14px;
  padding: 10px 14px;
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: var(--r-md);
  font-size: 13px;
}
</style>
