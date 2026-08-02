import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { collectHints, detectOS } from '../api/fingerprint'
import { probeBridge, waitForBridge, applyToken } from '../api/bridgeInstall'

/**
 * The onboarding state machine.
 *
 *   detecting -> [bound] ---------------------------> ready
 *             -> [candidate]    -> confirm  --------> ready
 *             -> [provisionable]-> provision -------> ready
 *             -> [ambiguous]    -> pick ------------> ready
 *
 * Bridge track runs in parallel and never blocks the sale path — a
 * cashier with no printer can still ring up and queue receipts.
 */
export const useOnboardingStore = defineStore('onboarding', () => {

  const step = ref('detecting')     // detecting|choose|provision|bridge|ready|error
  const busy = ref(false)
  const error = ref('')

  const probeResult = ref(null)     // server decision payload
  const hints = ref({})
  const terminal = ref(null)        // bound terminal identity

  // ---- bridge track --------------------------------------------------
  const bridge = ref({ online: false, checked: false })
  const installPlan = ref(null)
  const installing = ref(false)
  const installMessage = ref('')

  const osName = computed(() => detectOS())
  const needsBridge = computed(() => bridge.value.checked && !bridge.value.online)
  const bridgeVersion = computed(() => bridge.value.version || '')

  // ---------------------------------------------------------------
  // 1. detect
  // ---------------------------------------------------------------
  async function detect() {
    step.value = 'detecting'
    error.value = ''
    busy.value = true
    try {
      // Probe the bridge FIRST — if it's there it gives us hard identity,
      // which upgrades the whole decision from a guess to a fact.
      const b = await probeBridge()
      bridge.value = { ...b, checked: true }

      hints.value = collectHints(b)
      const res = await api.call('alphax_pos_suite.alphax_pos_suite.onboarding.api.probe', {
        client_hints: JSON.stringify(hints.value),
      })
      probeResult.value = res

      switch (res.decision) {
        case 'bound':
          terminal.value = res.terminal
          await afterBind()
          break
        case 'candidate':
          terminal.value = res.terminal
          step.value = 'choose'
          break
        case 'provisionable':
          step.value = res.can_provision ? 'provision' : 'choose'
          break
        default:
          step.value = 'choose'
      }
    } catch (e) {
      error.value = e?.message || String(e)
      step.value = 'error'
    } finally {
      busy.value = false
    }
  }

  // ---------------------------------------------------------------
  // 2. bind
  // ---------------------------------------------------------------
  async function claim(terminalName, force = false) {
    busy.value = true
    error.value = ''
    try {
      const r = await api.call('alphax_pos_suite.alphax_pos_suite.onboarding.api.claim', {
        terminal: terminalName,
        client_hints: JSON.stringify(hints.value),
        force: force ? 1 : 0,
      })
      terminal.value = r.terminal
      await afterBind()
      return true
    } catch (e) {
      error.value = e?.message || String(e)
      return false
    } finally {
      busy.value = false
    }
  }

  async function provision({ label, outlet, pos_profile } = {}) {
    busy.value = true
    error.value = ''
    try {
      const r = await api.call('alphax_pos_suite.alphax_pos_suite.onboarding.api.auto_provision', {
        client_hints: JSON.stringify(hints.value),
        terminal_label: label || undefined,
        outlet: outlet || undefined,
        pos_profile: pos_profile || undefined,
      })
      if (!r.ok && r.reason === 'exists') {
        error.value = 'This machine already has a terminal. Pick it from the list.'
        step.value = 'choose'
        return false
      }
      terminal.value = r.terminal
      await afterBind()
      return true
    } catch (e) {
      error.value = e?.message || String(e)
      return false
    } finally {
      busy.value = false
    }
  }

  async function afterBind() {
    await reportBridge()
    // Bridge missing is a soft stop: we surface the install card but the
    // cashier can skip straight through to selling.
    step.value = bridge.value.online ? 'ready' : 'bridge'
  }

  // ---------------------------------------------------------------
  // 3. bridge install
  // ---------------------------------------------------------------
  async function reportBridge() {
    if (!terminal.value?.name) return
    const b = bridge.value
    try {
      await api.call('alphax_pos_suite.alphax_pos_suite.onboarding.api.report_bridge_state', {
        terminal: terminal.value.name,
        state: JSON.stringify({
          online: !!b.online,
          version: b.version || '',
          port: b.url ? Number(new URL(b.url).port) : null,
          url: b.url || '',
          os: b.system?.os || osName.value,
          hostname: b.system?.hostname || '',
          machine_uuid: b.system?.machine_uuid || '',
          mac_address: b.system?.mac_address || '',
          devices: b.devices || [],
        }),
      })
    } catch { /* telemetry must never block the till */ }
  }

  async function loadInstallPlan() {
    if (installPlan.value) return installPlan.value
    installPlan.value = await api.call(
      'alphax_pos_suite.alphax_pos_suite.onboarding.api.get_bridge_installers',
      { os_hint: osName.value },
    )
    return installPlan.value
  }

  async function noteInstallAttempt(method) {
    if (!terminal.value?.name) return
    try {
      await api.call('alphax_pos_suite.alphax_pos_suite.onboarding.api.mark_bridge_install_attempt', {
        terminal: terminal.value.name,
        method,
        os_name: osName.value,
      })
    } catch {}
  }

  /** Watch for the daemon appearing after the cashier runs the installer. */
  async function watchForBridge() {
    installing.value = true
    installMessage.value = 'Waiting for the bridge to start…'
    const r = await waitForBridge({
      onTick: (ms) => {
        const s = Math.round(ms / 1000)
        installMessage.value = s < 60
          ? `Waiting for the bridge to start… ${s}s`
          : `Still waiting (${Math.round(s / 60)} min). Finish the installer, then this will continue on its own.`
      },
    })
    installing.value = false
    if (r.online) {
      bridge.value = { ...r, checked: true }
      installMessage.value = `Bridge ${r.version} connected — ${r.devices?.length || 0} device(s) found.`
      await reportBridge()
      return true
    }
    installMessage.value = 'Gave up waiting. Start the bridge, then press Check again.'
    return false
  }

  async function recheckBridge() {
    const r = await probeBridge()
    bridge.value = { ...r, checked: true }
    await reportBridge()
    return r.online
  }

  async function pasteToken(token) {
    const r = await applyToken(token)
    bridge.value = { ...r, checked: true }
    await reportBridge()
    return r.online && !r.needs_token
  }

  function skipBridge() {
    step.value = 'ready'
  }

  // ---------------------------------------------------------------
  // 4. heartbeat
  // ---------------------------------------------------------------
  let hbTimer = null
  function startHeartbeat(intervalMs = 5 * 60 * 1000) {
    stopHeartbeat()
    hbTimer = setInterval(async () => {
      const r = await probeBridge()
      bridge.value = { ...r, checked: true }
      await reportBridge()
    }, intervalMs)
  }
  function stopHeartbeat() {
    if (hbTimer) { clearInterval(hbTimer); hbTimer = null }
  }

  return {
    step, busy, error, probeResult, terminal, hints,
    bridge, installPlan, installing, installMessage,
    osName, needsBridge, bridgeVersion,
    detect, claim, provision, reportBridge,
    loadInstallPlan, noteInstallAttempt, watchForBridge, recheckBridge,
    pasteToken, skipBridge, startHeartbeat, stopHeartbeat,
  }
})
