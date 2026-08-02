<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHardwareStore } from '../stores/hardware'
import { getBridgeURL, setBridgeURL, getBridgeToken, setBridgeToken, bridge } from '../api/bridge'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const hw = useHardwareStore()
const emit = defineEmits(['close'])

const url = ref(getBridgeURL())
const token = ref(getBridgeToken())
const busy = ref(false)
const testResult = ref({})  // device -> {ok, msg}

const ROLES = [
  { key: 'receipt_printer', kind: 'printer' },
  { key: 'kitchen_printer', kind: 'printer' },
  { key: 'drawer',          kind: 'drawer' },
  { key: 'display',         kind: 'display' },
  { key: 'scale',           kind: 'scale' },
  { key: 'terminal',        kind: 'terminal' },
]

function devicesByKind(kind) {
  // Card terminals live in registry._terminals; the bridge exposes them
  // separately in /devices payload as `terminals[]`.
  if (kind === 'terminal') return (hw.bridgeInfo && hw.bridgeInfo.terminals)
    ? hw.bridgeInfo.terminals.map(t => t.name)
    : []
  return hw.devices.filter(d => d.kind === kind).map(d => d.name)
}

async function connect() {
  busy.value = true
  setBridgeURL(url.value.trim())
  setBridgeToken(token.value.trim())
  await hw.ping()
  if (hw.online) {
    await hw.refreshDevices()
    await hw.autodetectMapping()
  }
  busy.value = false
}

async function refresh() {
  busy.value = true
  await hw.ping()
  if (hw.online) await hw.refreshDevices()
  busy.value = false
}

async function autoMap() {
  await hw.refreshDevices()
  // Reset before re-detecting so unmapped roles get filled in
  await hw.autodetectMapping()
}

async function runTest(role, action) {
  const device = hw.mapping[role]
  if (!device) return
  testResult.value = { ...testResult.value, [device]: { pending: true } }
  try {
    if (action === 'print')   await bridge.testPrint(device)
    if (action === 'kick')    await bridge.testKick(device)
    if (action === 'display') await bridge.testDisplay(device)
    if (action === 'weight') {
      const r = await bridge.testWeight(device)
      const w = r?.weight
      testResult.value = { ...testResult.value, [device]: {
        ok: true,
        msg: w ? `${w.weight} ${w.unit}${w.stable ? '' : ' · ' + t('hardware.weight_unstable')}` : 'no reading'
      }}
      return
    }
    testResult.value = { ...testResult.value, [device]: { ok: true } }
  } catch (e) {
    testResult.value = { ...testResult.value, [device]: { ok: false, msg: e.message || String(e) } }
  }
}

const showInstall = computed(() => !hw.online && !busy.value && !hw.checking)
</script>

<template>
  <AppModal :title="t('hardware.settings')" size="lg" @close="emit('close')">

    <!-- connection -->
    <section class="section">
      <div class="section-head">
        <h4>{{ t('hardware.bridge') }}</h4>
        <span class="status-pill" :class="{ online: hw.online }">
          <span class="status-dot"></span>
          {{ hw.online ? t('hardware.online') : t('hardware.offline') }}
        </span>
      </div>

      <div class="grid-2">
        <div>
          <label class="label">{{ t('hardware.bridge_url') }}</label>
          <input class="input" v-model="url" placeholder="http://localhost:8420" />
        </div>
        <div>
          <label class="label">{{ t('hardware.auth_token') }}</label>
          <input class="input" type="password" v-model="token" autocomplete="off" />
        </div>
      </div>

      <div class="actions-row">
        <button class="btn btn-primary" @click="connect" :disabled="busy">
          {{ busy ? '…' : t('hardware.connect') }}
        </button>
        <button class="btn" @click="refresh" :disabled="busy || !hw.online">
          {{ t('hardware.refresh') }}
        </button>
        <button class="btn" @click="autoMap" :disabled="busy || !hw.online">
          {{ t('hardware.auto_map') }}
        </button>
      </div>

      <div v-if="showInstall" class="install-hint">
        <div>{{ t('hardware.install_prompt') }}</div>
        <a href="https://docs.alphax.local/pos/bridge/getting-started" target="_blank" class="link">
          {{ t('hardware.install_link') }} →
        </a>
      </div>
      <div v-if="hw.lastError && !hw.online" class="error-bar">{{ hw.lastError }}</div>
    </section>

    <!-- role mapping -->
    <section v-if="hw.online" class="section">
      <h4>{{ t('hardware.devices') }}</h4>
      <div v-if="hw.devices.length === 0" class="muted">{{ t('hardware.no_devices') }}</div>
      <div v-else class="role-table">
        <div v-for="role in ROLES" :key="role.key" class="role-row">
          <div class="role-name">{{ t(`hardware.role_${role.key}`) }}</div>
          <select class="input role-select"
            :value="hw.mapping[role.key]"
            @change="hw.setMapping(role.key, $event.target.value || null)">
            <option :value="''">{{ t('hardware.none') }}</option>
            <option v-for="d in devicesByKind(role.kind)" :key="d" :value="d">{{ d }}</option>
          </select>
          <div class="role-tests">
            <button v-if="role.kind === 'printer'" class="btn btn-ghost test-btn"
              :disabled="!hw.mapping[role.key]" @click="runTest(role.key, 'print')">
              {{ t('hardware.test_print') }}
            </button>
            <button v-if="role.kind === 'drawer'" class="btn btn-ghost test-btn"
              :disabled="!hw.mapping[role.key]" @click="runTest(role.key, 'kick')">
              {{ t('hardware.test_kick') }}
            </button>
            <button v-if="role.kind === 'display'" class="btn btn-ghost test-btn"
              :disabled="!hw.mapping[role.key]" @click="runTest(role.key, 'display')">
              {{ t('hardware.test_display') }}
            </button>
            <button v-if="role.kind === 'scale'" class="btn btn-ghost test-btn"
              :disabled="!hw.mapping[role.key]" @click="runTest(role.key, 'weight')">
              {{ t('hardware.test_weight') }}
            </button>
            <span v-if="testResult[hw.mapping[role.key]]" class="test-result"
              :class="{ ok: testResult[hw.mapping[role.key]].ok,
                        bad: testResult[hw.mapping[role.key]].ok === false }">
              {{ testResult[hw.mapping[role.key]].ok === false ? '✗' : '✓' }}
              {{ testResult[hw.mapping[role.key]].msg || '' }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <template #footer>
      <button class="btn btn-primary" @click="emit('close')">{{ t('app.close') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.section { margin-block-end: 18px; }
.section:last-child { margin-block-end: 0; }
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-block-end: 10px;
}
h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); text-transform: uppercase; letter-spacing: 0.5px; }

.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; border-radius: var(--r-pill);
  background: var(--surface-2); color: var(--text-muted);
  font-size: 11px; font-weight: 500;
}
.status-pill.online { background: var(--accent-soft); color: var(--accent); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-dim); }
.status-pill.online .status-dot { background: var(--accent); }

.grid-2 { display: grid; grid-template-columns: 2fr 1fr; gap: 10px; margin-block-end: 10px; }

.actions-row { display: flex; gap: 8px; }
.install-hint {
  margin-block-start: 12px;
  padding: 14px;
  background: var(--info-soft);
  color: var(--info);
  border-radius: var(--r-md);
  font-size: 13px;
  line-height: 1.55;
}
.install-hint .link { display: inline-block; margin-block-start: 8px; color: var(--info); font-weight: 500; }
.error-bar {
  margin-block-start: 10px;
  padding: 10px 12px;
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: var(--r-md);
  font-size: 12px;
  font-family: var(--font-mono);
}

.role-table { display: flex; flex-direction: column; gap: 8px; }
.role-row {
  display: grid;
  grid-template-columns: 130px 200px 1fr;
  gap: 10px;
  align-items: center;
  padding: 8px 4px;
  border-block-end: 1px solid var(--border);
}
.role-row:last-child { border-block-end: none; }
.role-name { font-size: 13px; font-weight: 500; color: var(--text); }
.role-select { width: 100%; }

.role-tests { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.test-btn { padding: 5px 10px; font-size: 11px; }
.test-result {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
}
.test-result.ok  { background: var(--accent-soft); color: var(--accent); }
.test-result.bad { background: var(--danger-soft); color: var(--danger); }

.muted { color: var(--text-dim); padding: 16px; text-align: center; font-size: 13px; }
</style>
