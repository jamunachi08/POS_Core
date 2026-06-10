import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { bridge, getBridgeURL } from '../api/bridge'

const MAPPING_KEY = 'alphax_hardware_mapping'

const defaultMapping = () => ({
  receipt_printer: null,
  kitchen_printer: null,
  drawer:          null,
  display:         null,
  scale:           null,
  terminal:        null,
})

function loadMapping() {
  try {
    return { ...defaultMapping(), ...JSON.parse(localStorage.getItem(MAPPING_KEY) || '{}') }
  } catch {
    return defaultMapping()
  }
}

export const useHardwareStore = defineStore('hardware', () => {

  // ---- bridge connection state -----------------------------------------
  const online = ref(false)
  const checking = ref(false)
  const lastError = ref(null)
  const bridgeInfo = ref(null)
  const devices = ref([])

  // ---- user's logical-to-physical mapping ------------------------------
  const mapping = ref(loadMapping())

  watch(mapping, (m) => {
    localStorage.setItem(MAPPING_KEY, JSON.stringify(m))
  }, { deep: true })

  // ---- live state ------------------------------------------------------
  const liveWeight = ref(null) // { weight, unit, stable } | null

  // ---- derived ---------------------------------------------------------
  const printerReady = computed(() => online.value && !!mapping.value.receipt_printer)
  const drawerReady  = computed(() => online.value && !!mapping.value.drawer)
  const displayReady = computed(() => online.value && !!mapping.value.display)
  const scaleReady   = computed(() => online.value && !!mapping.value.scale)
  const terminalReady = computed(() => online.value && !!mapping.value.terminal)

  // ---- actions ---------------------------------------------------------

  async function ping() {
    checking.value = true
    lastError.value = null
    try {
      bridgeInfo.value = await bridge.status()
      online.value = true
    } catch (e) {
      bridgeInfo.value = null
      online.value = false
      lastError.value = e.message || String(e)
    } finally {
      checking.value = false
    }
    return online.value
  }

  async function refreshDevices() {
    if (!online.value) return
    try {
      const r = await bridge.listDevices()
      devices.value = r.devices || []
      // Stash the full payload so the settings dialog can read terminals[]
      bridgeInfo.value = { ...(bridgeInfo.value || {}), ...r }
    } catch (e) {
      lastError.value = e.message || String(e)
    }
  }

  async function autodetectMapping() {
    // Pick the first device of each kind if the user hasn't chosen yet.
    if (devices.value.length === 0) await refreshDevices()
    const m = { ...mapping.value }
    let changed = false
    const byKind = {}
    for (const d of devices.value) {
      (byKind[d.kind] ||= []).push(d.name)
    }
    if (!m.receipt_printer && byKind.printer?.[0]) { m.receipt_printer = byKind.printer[0]; changed = true }
    if (!m.kitchen_printer && byKind.printer?.[1]) { m.kitchen_printer = byKind.printer[1]; changed = true }
    if (!m.drawer  && byKind.drawer?.[0])  { m.drawer  = byKind.drawer[0];  changed = true }
    if (!m.display && byKind.display?.[0]) { m.display = byKind.display[0]; changed = true }
    if (!m.scale   && byKind.scale?.[0])    { m.scale    = byKind.scale[0];    changed = true }
    if (!m.terminal && byKind.terminal?.[0]) { m.terminal = byKind.terminal[0]; changed = true }
    if (changed) mapping.value = m
  }

  function setMapping(role, deviceName) {
    mapping.value = { ...mapping.value, [role]: deviceName || null }
  }

  // ---- high-level operations the SPA calls -----------------------------

  async function printReceipt(receipt, { kind = 'receipt' } = {}) {
    if (!online.value) return { ok: false, reason: 'bridge offline' }
    const target = kind === 'kitchen' ? mapping.value.kitchen_printer : mapping.value.receipt_printer
    if (!target) return { ok: false, reason: `no ${kind} printer mapped` }
    try {
      await bridge.print(target, receipt)
      return { ok: true, device: target }
    } catch (e) {
      return { ok: false, reason: e.message || String(e) }
    }
  }

  async function kickDrawer() {
    if (!online.value) return { ok: false, reason: 'bridge offline' }
    if (!mapping.value.drawer) return { ok: false, reason: 'no drawer mapped' }
    try {
      await bridge.drawer(mapping.value.drawer)
      return { ok: true, device: mapping.value.drawer }
    } catch (e) {
      return { ok: false, reason: e.message || String(e) }
    }
  }

  async function showOnDisplay(payload) {
    if (!online.value || !mapping.value.display) return
    try {
      await bridge.display(mapping.value.display, payload)
    } catch (e) {
      // display failures are non-fatal
      lastError.value = e.message || String(e)
    }
  }

  async function readWeight() {
    if (!online.value) return null
    if (!mapping.value.scale) return null
    try {
      const r = await bridge.scale(mapping.value.scale, 2)
      liveWeight.value = r.weight || null
      return liveWeight.value
    } catch (e) {
      liveWeight.value = null
      return null
    }
  }

  /** Run a card-terminal charge through the bridge. Returns the
   *  ChargeResult dict (status, auth_code, masked_pan, etc.) so the
   *  caller can decide whether to consider the sale paid. */
  async function chargeOnTerminal({ amount, currency, invoice_ref, idempotency_key, metadata, timeout = 90 }) {
    if (!online.value) return { ok: false, status: 'error', decline_reason: 'bridge offline' }
    if (!mapping.value.terminal) return { ok: false, status: 'error', decline_reason: 'no terminal mapped' }
    try {
      const r = await bridge.charge(mapping.value.terminal, {
        amount, currency, invoice_ref, idempotency_key, metadata, timeout
      })
      return r
    } catch (e) {
      return { ok: false, status: 'error', decline_reason: e.message || String(e) }
    }
  }

  async function cancelTerminal(current_txn_id = '') {
    if (!online.value) return { ok: false }
    if (!mapping.value.terminal) return { ok: false }
    try {
      return await bridge.terminalCancel(mapping.value.terminal, current_txn_id)
    } catch (e) {
      return { ok: false, decline_reason: e.message || String(e) }
    }
  }

  // ---- live weight polling ---------------------------------------------
  let weightTimer = null
  function startWeightPolling(intervalMs = 1500) {
    stopWeightPolling()
    if (!scaleReady.value) return
    weightTimer = setInterval(() => {
      readWeight().catch(() => {})
    }, intervalMs)
  }
  function stopWeightPolling() {
    if (weightTimer) {
      clearInterval(weightTimer)
      weightTimer = null
      liveWeight.value = null
    }
  }

  return {
    // state
    online, checking, lastError, bridgeInfo, devices,
    mapping, liveWeight,
    // computed
    printerReady, drawerReady, displayReady, scaleReady, terminalReady,
    // actions
    ping, refreshDevices, autodetectMapping, setMapping,
    printReceipt, kickDrawer, showOnDisplay, readWeight,
    chargeOnTerminal, cancelTerminal,
    startWeightPolling, stopWeightPolling,
  }
})
