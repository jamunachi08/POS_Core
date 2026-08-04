<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useOnboardingStore } from '../stores/onboarding'
import { launchInstaller, copyToClipboard } from '../api/bridgeInstall'
import LocaleSwitch from './LocaleSwitch.vue'

const { t } = useI18n()
const store = usePOSStore()
const ob = useOnboardingStore()

const label = ref('')
const outlet = ref('')
const profile = ref('')
const tokenInput = ref('')
const showToken = ref(false)
const copied = ref('')

onMounted(async () => {
  await ob.detect()
  label.value = ob.probeResult?.suggested_name || ''
  outlet.value = ob.probeResult?.defaults?.outlet || ''
  profile.value = ob.probeResult?.defaults?.pos_profile || ''
  if (ob.step === 'bridge') await ob.loadInstallPlan()
  if (ob.step === 'ready') enter()
})

const defaults = computed(() => ob.probeResult?.defaults || {})
const candidates = computed(() => ob.probeResult?.candidates || [])
const serverInfo = computed(() => ob.probeResult?.server || {})

async function confirmCandidate(force = false) {
  const name = ob.terminal?.name || candidates.value[0]?.name
  if (!name) return
  if (await ob.claim(name, force)) postBind()
}

async function pickCandidate(name) {
  if (await ob.claim(name)) postBind()
}

async function doProvision() {
  if (await ob.provision({ label: label.value, outlet: outlet.value, pos_profile: profile.value })) {
    postBind()
  }
}

async function postBind() {
  if (ob.step === 'bridge') await ob.loadInstallPlan()
  if (ob.step === 'ready') enter()
}

function enter() {
  ob.startHeartbeat()
  store.changeTerminal(ob.terminal.name)
}

async function runMethod(method) {
  await ob.noteInstallAttempt(method.id)
  if (method.id === 'installer') {
    launchInstaller(method)
    ob.watchForBridge().then(ok => { if (ok) setTimeout(enter, 900) })
  } else {
    const ok = await copyToClipboard(method.command)
    copied.value = ok ? method.id : ''
    setTimeout(() => (copied.value = ''), 2500)
    ob.watchForBridge().then(ok2 => { if (ok2) setTimeout(enter, 900) })
  }
}

async function recheck() {
  if (await ob.recheckBridge()) enter()
}

async function submitToken() {
  if (await ob.pasteToken(tokenInput.value.trim())) enter()
}
</script>

<template>
  <div class="ob-screen">
    <div class="ob-top-right"><LocaleSwitch /></div>

    <div class="ob-card" :class="{ wide: ob.step === 'bridge' }">
      <div class="ob-head">
        <div class="ob-mark">α</div>
        <div>
          <div class="ob-title">{{ t('app.name') }}</div>
          <div class="ob-sub">{{ t('onboarding.subtitle') }}</div>
        </div>
      </div>

      <!-- progress rail -->
      <div class="ob-rail">
        <div class="dot" :class="{ done: ob.step !== 'detecting', active: ob.step === 'detecting' }">
          <span>1</span><label>{{ t('onboarding.step_detect') }}</label>
        </div>
        <div class="bar"></div>
        <div class="dot" :class="{ done: !!ob.terminal, active: ['choose','provision'].includes(ob.step) }">
          <span>2</span><label>{{ t('onboarding.step_station') }}</label>
        </div>
        <div class="bar"></div>
        <div class="dot" :class="{ done: ob.hardware.configured && (!ob.hardwareNeedsBridge || ob.bridge.online),
                                   active: ['hardware','bridge'].includes(ob.step) }">
          <span>3</span><label>{{ t('onboarding.step_hardware') }}</label>
        </div>
      </div>

      <!-- ===================== 1. DETECTING ===================== -->
      <section v-if="ob.step === 'detecting'" class="pane center">
        <div class="spinner"></div>
        <p class="muted">{{ t('onboarding.detecting') }}</p>
      </section>

      <!-- ===================== ERROR ===================== -->
      <section v-else-if="ob.step === 'error'" class="pane center">
        <div class="err-title">{{ t('errors.boot_failed') }}</div>
        <div class="err-detail">{{ ob.error }}</div>
        <button class="btn btn-primary" @click="ob.detect">{{ t('app.retry') }}</button>
      </section>

      <!-- ===================== 2a. CONFIRM CANDIDATE ===================== -->
      <section v-else-if="ob.step === 'choose' && ob.terminal" class="pane">
        <div class="lead">{{ t('onboarding.recognised') }}</div>
        <div class="station-card">
          <div class="st-mark">⌥</div>
          <div>
            <div class="st-name">{{ ob.terminal.name }}</div>
            <div class="st-sub">
              {{ [ob.terminal.pos_outlet, ob.terminal.branch].filter(Boolean).join(' · ') }}
            </div>
            <div class="st-meta" v-if="ob.terminal.last_bound_at">
              {{ t('onboarding.last_bound', { at: ob.terminal.last_bound_at, by: ob.terminal.last_bound_by }) }}
            </div>
          </div>
        </div>
        <div class="row-actions">
          <button class="btn btn-primary lg" :disabled="ob.busy" @click="confirmCandidate(false)">
            {{ t('onboarding.use_this') }}
          </button>
          <button class="btn ghost" @click="ob.probeResult.decision = 'ambiguous'; ob.step='choose'; ob.terminal=null">
            {{ t('onboarding.different_station') }}
          </button>
        </div>
        <div v-if="ob.error" class="inline-err">
          {{ ob.error }}
          <button class="btn tiny danger" @click="confirmCandidate(true)">{{ t('onboarding.rebind') }}</button>
        </div>
      </section>

      <!-- ===================== 2b. PICK FROM LIST ===================== -->
      <section v-else-if="ob.step === 'choose'" class="pane">
        <div class="lead">{{ t('onboarding.pick_station') }}</div>
        <div class="station-list">
          <button v-for="c in candidates" :key="c.name" class="station-row"
                  :disabled="ob.busy" @click="pickCandidate(c.name)">
            <div class="st-mark sm">⌥</div>
            <div class="grow">
              <div class="st-name">{{ c.name }}</div>
              <div class="st-sub">{{ [c.pos_outlet, c.branch].filter(Boolean).join(' · ') }}</div>
            </div>
            <span v-if="c.already_bound" class="pill warn">{{ t('onboarding.in_use') }}</span>
          </button>
        </div>
        <button v-if="ob.probeResult?.can_provision" class="btn ghost full"
                @click="ob.step = 'provision'">
          + {{ t('onboarding.new_station') }}
        </button>
        <div v-if="ob.error" class="inline-err">{{ ob.error }}</div>
      </section>

      <!-- ===================== 2c. AUTO PROVISION ===================== -->
      <section v-else-if="ob.step === 'provision'" class="pane">
        <div class="lead">{{ t('onboarding.new_station_lead') }}</div>

        <div class="detected">
          <div class="d-row"><label>{{ t('onboarding.f_machine') }}</label>
            <b>{{ ob.hints.bridge_hostname || ob.hints.platform || '—' }}</b></div>
          <div class="d-row"><label>{{ t('onboarding.f_ip') }}</label>
            <b>{{ serverInfo.client_ip || '—' }}</b></div>
          <div class="d-row"><label>{{ t('onboarding.f_id') }}</label>
            <b class="mono">{{ (ob.probeResult?.fingerprint || '').slice(0, 22) }}…</b></div>
          <div class="d-row"><label>{{ t('onboarding.f_screen') }}</label>
            <b>{{ ob.hints.screen }}{{ ob.hints.tablet ? ' · tablet' : '' }}</b></div>
        </div>

        <label class="fld">
          <span>{{ t('onboarding.station_name') }}</span>
          <input v-model="label" type="text" />
        </label>

        <label v-if="(defaults.outlet_count || 0) !== 1" class="fld">
          <span>{{ t('onboarding.outlet') }}</span>
          <select v-model="outlet">
            <option value="">—</option>
            <option v-for="o in defaults.outlets" :key="o.name" :value="o.name">{{ o.name }}</option>
          </select>
        </label>

        <label v-if="(defaults.profile_count || 0) !== 1" class="fld">
          <span>{{ t('onboarding.pos_profile') }}</span>
          <select v-model="profile">
            <option value="">—</option>
            <option v-for="p in defaults.profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </label>

        <button class="btn btn-primary lg full" :disabled="ob.busy" @click="doProvision">
          {{ ob.busy ? t('app.loading') : t('onboarding.create_and_bind') }}
        </button>
        <div v-if="ob.error" class="inline-err">{{ ob.error }}</div>
      </section>

      <!-- ============== 3a. HARDWARE SELECTION ============== -->
      <section v-else-if="ob.step === 'hardware'" class="pane">
        <div class="lead">{{ t('onboarding.hardware_lead') }}</div>
        <p class="muted small">{{ t('onboarding.hardware_body') }}</p>

        <!-- One tap for the common shapes, then tune below. -->
        <div class="hw-profiles">
          <button v-for="p in ob.hardware.profiles" :key="p.id"
                  class="hw-profile" :class="{ on: ob.hardware.profile === p.id }"
                  @click="ob.applyProfile(p.id)">
            <div class="hw-p-label">{{ p.label }}</div>
            <div class="hw-p-sub">{{ p.sublabel }}</div>
          </button>
        </div>

        <div class="hw-list">
          <button v-for="r in ob.hardware.roles" :key="r.id"
                  class="hw-row" :class="{ on: ob.hardware.plan[r.id] }"
                  @click="ob.toggleRole(r.id)">
            <span class="hw-box" :class="{ on: ob.hardware.plan[r.id] }">
              {{ ob.hardware.plan[r.id] ? '✓' : '' }}
            </span>
            <span class="grow">
              <span class="hw-label">{{ r.label }}</span>
              <span class="hw-sub">{{ r.sublabel }}</span>
            </span>
            <span v-if="r.needs_bridge" class="pill faint">{{ t('onboarding.needs_bridge') }}</span>
          </button>
        </div>

        <div class="hw-verdict" :class="{ none: !ob.hardwareNeedsBridge }">
          {{ ob.hardwareNeedsBridge
             ? t('onboarding.hardware_needs_bridge')
             : t('onboarding.hardware_no_bridge') }}
        </div>

        <button class="btn btn-primary lg full" :disabled="ob.busy" @click="ob.saveHardware()">
          {{ ob.busy ? t('app.loading')
             : (ob.hardwareNeedsBridge ? t('onboarding.hardware_continue')
                                       : t('onboarding.hardware_done')) }}
        </button>
        <div v-if="ob.error" class="inline-err">{{ ob.error }}</div>
      </section>

      <!-- ===================== 3b. BRIDGE ===================== -->
      <section v-else-if="ob.step === 'bridge'" class="pane">
        <div class="lead">{{ t('onboarding.bridge_missing_lead') }}</div>
        <p class="muted small">{{ t('onboarding.bridge_missing_body') }}</p>

        <!-- Why this station needs the daemon at all, in its own terms. -->
        <div v-if="ob.chosenRoles.length" class="hw-chosen">
          <span class="hw-chosen-label">{{ t('onboarding.installing_for') }}</span>
          <span v-for="r in ob.chosenRoles" :key="r.id" class="pill">{{ r.label }}</span>
          <button class="btn link sm" @click="ob.reopenHardware()">
            {{ t('onboarding.change_hardware') }}
          </button>
        </div>

        <div class="os-pill">
          {{ t('onboarding.detected_os') }}: <b>{{ ob.installPlan?.os_label || ob.osName }}</b>
          <span class="ver" v-if="ob.installPlan">v{{ ob.installPlan.version }}</span>
        </div>

        <div class="methods">
          <div v-for="m in (ob.installPlan?.methods || [])" :key="m.id"
               class="method" :class="{ primary: m.rank === 1 }">
            <div class="m-head">
              <div>
                <div class="m-label">{{ m.label }}</div>
                <div class="m-sub">{{ m.sublabel }}</div>
              </div>
              <button class="btn" :class="m.rank === 1 ? 'btn-primary' : 'ghost'"
                      @click="runMethod(m)">
                {{ m.id === 'installer' ? t('onboarding.download') :
                   (copied === m.id ? t('onboarding.copied') : t('onboarding.copy')) }}
              </button>
            </div>
            <code v-if="m.command" class="m-cmd">{{ m.command }}</code>
            <ol v-if="m.steps?.length" class="m-steps">
              <li v-for="(s, i) in m.steps" :key="i">{{ s }}</li>
            </ol>
          </div>
        </div>

        <div class="watch" v-if="ob.installing">
          <div class="spinner sm"></div><span>{{ ob.installMessage }}</span>
        </div>
        <div class="watch ok" v-else-if="ob.installMessage">{{ ob.installMessage }}</div>

        <div class="bridge-actions">
          <button class="btn ghost" @click="recheck">{{ t('onboarding.check_again') }}</button>
          <button class="btn ghost" @click="showToken = !showToken">{{ t('onboarding.have_token') }}</button>
          <button class="btn link" @click="ob.skipBridge(); enter()">
            {{ t('onboarding.skip_for_now') }}
          </button>
        </div>

        <div v-if="showToken" class="token-row">
          <input v-model="tokenInput" :placeholder="t('onboarding.token_placeholder')" />
          <button class="btn btn-primary" @click="submitToken">{{ t('onboarding.connect') }}</button>
        </div>

        <p class="muted tiny">{{ t('onboarding.skip_note') }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.ob-screen { position: fixed; inset: 0; display: grid; place-items: center; padding: 20px;
  background: linear-gradient(135deg, var(--bg) 0%, var(--surface-2) 100%); overflow-y: auto; }
.ob-top-right { position: absolute; inset-block-start: 16px; inset-inline-end: 16px; }
.ob-card { background: var(--surface); border-radius: var(--r-lg); padding: 28px 30px;
  width: 100%; max-width: 480px; box-shadow: var(--shadow-lg); }
.ob-card.wide { max-width: 640px; }

.ob-head { display: flex; align-items: center; gap: 14px; margin-block-end: 22px; }
.ob-mark { width: 46px; height: 46px; border-radius: var(--r-md); background: var(--accent);
  color: #fff; display: grid; place-items: center; font-size: 24px; font-weight: 600; flex: none; }
.ob-title { font-size: 17px; font-weight: 600; color: var(--text); }
.ob-sub { font-size: 12px; color: var(--text-dim); margin-block-start: 2px; }

.ob-rail { display: flex; align-items: center; gap: 6px; margin-block-end: 24px; }
.ob-rail .dot { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: none; }
.ob-rail .dot span { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
  font-size: 11px; font-weight: 600; background: var(--surface-2); color: var(--text-dim);
  border: 1px solid var(--border); }
.ob-rail .dot.active span { background: var(--accent); color: #fff; border-color: var(--accent); }
.ob-rail .dot.done span { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
.ob-rail .dot label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .4px; }
.ob-rail .bar { height: 1px; background: var(--border); flex: 1; margin-block-start: -14px; }

.pane { display: flex; flex-direction: column; gap: 14px; }
.pane.center { align-items: center; padding: 26px 0; gap: 12px; }
.lead { font-size: 14px; font-weight: 600; color: var(--text); }
.muted { color: var(--text-dim); font-size: 13px; }
.muted.small { font-size: 12px; line-height: 1.5; margin: 0; }
.muted.tiny { font-size: 11px; text-align: center; margin: 4px 0 0; }
.mono { font-family: ui-monospace, monospace; font-size: 11px; }

.spinner { width: 30px; height: 30px; border: 3px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin .8s linear infinite; }
.spinner.sm { width: 16px; height: 16px; border-width: 2px; }
@keyframes spin { to { transform: rotate(360deg); } }

.station-card { display: flex; gap: 12px; align-items: center; padding: 14px;
  background: var(--surface-2); border-radius: var(--r-md); border: 1px solid var(--accent); }
.st-mark { width: 38px; height: 38px; border-radius: var(--r-sm); background: var(--accent-soft);
  color: var(--accent); display: grid; place-items: center; flex: none; }
.st-mark.sm { width: 30px; height: 30px; font-size: 13px; }
.st-name { font-weight: 600; font-size: 14px; color: var(--text); }
.st-sub { font-size: 12px; color: var(--text-dim); margin-block-start: 2px; }
.st-meta { font-size: 11px; color: var(--text-dim); margin-block-start: 4px; opacity: .8; }

.station-list { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; }
.station-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  background: var(--surface-2); border: 1px solid transparent; border-radius: var(--r-md); text-align: start; }
.station-row:hover { border-color: var(--accent); }
.grow { flex: 1; min-width: 0; }
.pill { font-size: 10px; padding: 2px 7px; border-radius: 99px; }
.pill.warn { background: var(--warn-soft, #fef3c7); color: var(--warn, #92400e); }

.detected { background: var(--surface-2); border-radius: var(--r-md); padding: 12px 14px;
  display: flex; flex-direction: column; gap: 7px; }
.d-row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
.d-row label { color: var(--text-dim); }
.d-row b { color: var(--text); font-weight: 500; text-align: end; }

.fld { display: flex; flex-direction: column; gap: 5px; }
.fld span { font-size: 12px; color: var(--text-dim); }
.fld input, .fld select { padding: 9px 11px; border: 1px solid var(--border);
  border-radius: var(--r-sm); background: var(--surface); color: var(--text); font-size: 14px; }

.row-actions { display: flex; gap: 8px; }
.btn.lg { padding: 12px 18px; font-size: 14px; }
.btn.full { width: 100%; }
.btn.tiny { padding: 3px 8px; font-size: 11px; }
.btn.link { background: none; color: var(--text-dim); text-decoration: underline; }
.inline-err { font-size: 12px; color: var(--danger); display: flex; align-items: center;
  gap: 8px; flex-wrap: wrap; }
.err-title { font-weight: 600; color: var(--danger); font-size: 14px; }
.err-detail { font-size: 12px; color: var(--text-dim); text-align: center; }

.os-pill { font-size: 12px; color: var(--text-dim); background: var(--surface-2);
  padding: 7px 11px; border-radius: var(--r-sm); display: flex; gap: 8px; align-items: center; }
.os-pill .ver { margin-inline-start: auto; opacity: .7; }

.methods { display: flex; flex-direction: column; gap: 10px; }
.method { border: 1px solid var(--border); border-radius: var(--r-md); padding: 13px; }
.method.primary { border-color: var(--accent); background: var(--accent-soft); }
.m-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.m-label { font-size: 13px; font-weight: 600; color: var(--text); }
.m-sub { font-size: 11px; color: var(--text-dim); margin-block-start: 2px; }
.m-cmd { display: block; margin-block-start: 10px; padding: 9px 10px; background: var(--bg);
  border-radius: var(--r-sm); font-family: ui-monospace, monospace; font-size: 11px;
  color: var(--text); word-break: break-all; line-height: 1.5; }
.hw-profiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 14px; }
.hw-profile { text-align: start; padding: 10px 12px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--surface); }
.hw-profile.on { border-color: var(--brand, #0B6B5B);
  background: color-mix(in srgb, var(--brand, #0B6B5B) 8%, transparent); }
.hw-p-label { font-weight: 700; font-size: 13px; }
.hw-p-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

.hw-list { display: flex; flex-direction: column; gap: 6px; }
.hw-row { display: flex; align-items: center; gap: 10px; text-align: start;
  padding: 11px 12px; border-radius: 12px; border: 1px solid var(--border);
  background: var(--surface); }
.hw-row.on { border-color: var(--brand, #0B6B5B); }
.hw-box { width: 22px; height: 22px; flex: none; border-radius: 7px;
  border: 1.5px solid var(--border); display: grid; place-items: center;
  font-size: 13px; font-weight: 800; color: #fff; }
.hw-box.on { background: var(--brand, #0B6B5B); border-color: var(--brand, #0B6B5B); }
.hw-label { display: block; font-weight: 650; font-size: 13px; }
.hw-sub { display: block; font-size: 11px; color: var(--text-muted); margin-top: 1px; }
.hw-row .grow { flex: 1; }

.hw-verdict { margin: 14px 0 10px; padding: 10px 12px; border-radius: 10px;
  font-size: 12px; font-weight: 600;
  background: color-mix(in srgb, var(--brand, #0B6B5B) 8%, transparent);
  color: var(--brand-deep, #084A3F); }
.hw-verdict.none { background: color-mix(in srgb, #6B6760 10%, transparent);
  color: var(--text-muted); }

.hw-chosen { display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  margin: 10px 0 4px; }
.hw-chosen-label { font-size: 11.5px; color: var(--text-muted); font-weight: 600; }
.pill.faint { opacity: .65; }
.btn.link.sm { font-size: 11.5px; padding: 0 4px; }

.m-steps { margin: 10px 0 0; padding-inline-start: 18px; font-size: 11.5px;
  color: var(--text-dim); line-height: 1.7; }

.watch { display: flex; align-items: center; gap: 9px; font-size: 12px; color: var(--text-dim);
  background: var(--surface-2); padding: 10px 12px; border-radius: var(--r-sm); }
.watch.ok { color: var(--accent); }
.bridge-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.token-row { display: flex; gap: 8px; }
.token-row input { flex: 1; padding: 9px 11px; border: 1px solid var(--border);
  border-radius: var(--r-sm); background: var(--surface); color: var(--text); font-size: 13px; }
</style>
