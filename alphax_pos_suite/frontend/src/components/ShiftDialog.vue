<script setup>
// Shift & cash management dialog.
//
// Modes (driven by shift state + user intent):
//   'open'   — no shift: declare the opening float.
//   'status' — shift open: live X-report view + action buttons.
//   'cash'   — record a drawer movement (Paid In / Paid Out /
//              Petty Cash Expense / Cash Drop To Safe).
//   'close'  — BLIND close: the cashier types the counted cash first;
//              expected cash and over/short appear only in the result.
//   'zdone'  — the Z report after close, printable.
//   'dayclose' — after Z, roll the date's closed shifts into a Day
//              Close document.
//
// Printing: renders the X/Z content into a hidden 80mm-styled
// container and calls window.print() with a print-only stylesheet —
// works on any OS printer share and on qz-tray kiosks alike.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const props = defineProps({ initialMode: { type: String, default: 'auto' } })
const emit = defineEmits(['close', 'request-approval'])
const { t } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()

const mode = ref(
  props.initialMode !== 'auto' ? props.initialMode : (store.shift ? 'status' : 'open')
)
// Supervisor override: managers may open a shift ON BEHALF of a
// cashier (their user becomes the shift owner) and may close a shift
// they don't own. Role check is server-enforced; the flag here only
// reveals the UI.
const isManager = ref(false)
const behalfUser = ref('')
import { api } from '../api/client'
api.getCashierSettings().then(r => { isManager.value = !!(r && r.can_edit) }).catch(() => {})
const busy = ref(false)
const error = ref('')

// open
const openingCash = ref('')
// cash movement
const moveType = ref('Paid In')
const moveAmount = ref('')
const moveRemarks = ref('')
const MOVE_TYPES = ['Paid In', 'Paid Out', 'Petty Cash Expense', 'Cash Drop To Safe']
// close
const countedCash = ref('')
const closeNotes = ref('')
const isHandover = ref(false)
const handoverTo = ref('')
const zData = ref(null)
// day close
const dayData = ref(null)

const s = computed(() => store.shift)

onMounted(() => { if (store.shift) store.fetchXReport().catch(() => {}) })

function fail(e) { error.value = e.message || String(e); busy.value = false }

async function doOpen() {
  error.value = ''; busy.value = true
  try {
    await store.openShift(parseFloat(openingCash.value || 0),
      isManager.value && behalfUser.value.trim() ? behalfUser.value.trim() : null)
    mode.value = 'status'
  } catch (e) { return fail(e) }
  busy.value = false
}

function startMovement() {
  moveType.value = 'Paid In'; moveAmount.value = ''; moveRemarks.value = ''
  mode.value = 'cash'
}

async function doMovement() {
  const amt = parseFloat(moveAmount.value)
  if (!amt || amt <= 0) return
  const run = async () => {
    error.value = ''; busy.value = true
    try {
      await store.cashMovement(moveType.value, amt, moveRemarks.value || null)
      mode.value = 'status'
    } catch (e) { return fail(e) }
    busy.value = false
  }
  // Cash LEAVING the drawer is manager-gated when void-gating is on —
  // same trust level as destroying a sale.
  if (moveType.value !== 'Paid In' && store.settings.require_manager_for_void) {
    emit('request-approval', { action: `${moveType.value} ${fmt(amt)}`, run })
    emit('close')
    return
  }
  await run()
}

async function refreshX() {
  busy.value = true
  try { await store.fetchXReport() } catch (e) { return fail(e) }
  busy.value = false
}

async function doClose() {
  const currentUser = (window.frappe && frappe.session && frappe.session.user) || ''
  if (s.value && s.value.user && s.value.user !== currentUser) {
    // Closing on behalf: approve once, then proceed (server re-checks role).
    emit('request-approval', {
      action: `Close shift of ${s.value.user}`,
      run: () => reallyClose(),
    })
    emit('close')
    return
  }
  await reallyClose()
}

async function reallyClose() {
  error.value = ''; busy.value = true
  try {
    zData.value = await store.closeShift(parseFloat(countedCash.value || 0), closeNotes.value || null, isHandover.value ? (handoverTo.value || null) : null)
    mode.value = 'zdone'
  } catch (e) { return fail(e) }
  busy.value = false
}

async function doDayClose() {
  error.value = ''; busy.value = true
  try {
    dayData.value = await store.runDayClose()
    mode.value = 'dayclose'
  } catch (e) { return fail(e) }
  busy.value = false
}

function printReport(kind) {
  const el = document.getElementById('alphax-shift-print')
  if (!el) return
  el.setAttribute('data-kind', kind)
  document.body.classList.add('alphax-printing-shift')
  window.print()
  setTimeout(() => document.body.classList.remove('alphax-printing-shift'), 400)
}

const varianceClass = (v) => (Math.abs(v) < 0.005 ? 'ok' : v > 0 ? 'over' : 'short')
</script>

<!-- Blind close: the server strips totals/expected/variance from the
     summary for non-managers; every row below is presence-guarded, so
     cashiers see only opening float, movements, and the counted-cash
     entry. X report and Run day close render for supervisors only —
     and the server enforces both regardless of what the UI shows. -->
<template>
  <AppModal :title="t('shift.title')" size="lg" @close="emit('close')">
    <div class="sh-body">

      <!-- OPEN -->
      <template v-if="mode === 'open'">
        <div class="sh-lead">{{ t('shift.open_lead') }}</div>
        <!-- The trading day this shift will open under: the terminal's
             current business date when one is carried over (post-
             midnight second shift), otherwise today starts fresh. -->
        <div class="sh-bd-note">
          {{ t('shift.opens_under') }}
          <b>{{ store.boot?.terminal?.business_date || new Date().toISOString().slice(0, 10) }}</b>
          <template v-if="store.boot?.terminal?.business_date"> · {{ t('shift.carried_over') }}</template>
        </div>
        <label class="field">
          <span class="field-label">{{ t('shift.opening_float') }}</span>
          <input class="input tnum sh-big" type="number" inputmode="decimal" min="0"
            v-model="openingCash" :placeholder="fmt(0)" @keyup.enter="doOpen" autofocus />
        </label>
        <label class="field" v-if="isManager">
          <span class="field-label">{{ t('shift.on_behalf') }}</span>
          <input class="input" v-model="behalfUser" :placeholder="t('shift.on_behalf_ph')" />
        </label>
        <div class="sh-actions">
          <button class="btn" @click="emit('close')">{{ t('app.cancel') }}</button>
          <button class="btn btn-primary" :disabled="busy || openingCash === ''" @click="doOpen">
            {{ t('shift.open_btn') }}
          </button>
        </div>
      </template>

      <!-- STATUS / X REPORT -->
      <template v-else-if="mode === 'status' && s">
        <div class="sh-grid" id="alphax-shift-x">
          <div class="sh-kv"><span>{{ t('shift.opened') }}</span><b>{{ s.opened_on }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.cashier') }}</span><b>{{ s.user }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.opening_float') }}</span><b class="tnum">{{ fmt(s.opening_cash) }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.sales_count') }}</span><b class="tnum">{{ s.sale_count }} / {{ s.return_count }}↩ / {{ s.credit_count }}📒</b></div>
          <div class="sh-kv"><span>{{ t('shift.net_sales') }}<!--mgr--></span><b class="tnum">{{ fmt(s.net_sales) }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.credit_sales') }}</span><b class="tnum">{{ fmt(s.credit_sales) }}</b></div>
        </div>

        <h4 class="sh-h">{{ t('shift.by_mop') }}</h4>
        <div class="sh-rows">
          <div class="sh-row" v-for="m in s.by_mop" :key="m.mode_of_payment">
            <span>{{ m.mode_of_payment }}</span><b class="tnum">{{ fmt(m.amount) }}</b>
          </div>
          <div class="sh-row muted" v-if="!s.by_mop.length">—</div>
        </div>

        <h4 class="sh-h">{{ t('shift.movements') }}</h4>
        <div class="sh-rows">
          <div class="sh-row" v-for="(v, k) in s.movements" :key="k" v-show="v">
            <span>{{ t(`shift.mv.${k.toLowerCase().replace(/ /g, '_')}`) }}</span><b class="tnum">{{ fmt(v) }}</b>
          </div>
        </div>

        <div class="sh-expected">
          <span>{{ t('shift.expected_cash') }}</span>
          <b class="tnum">{{ fmt(s.expected_cash) }}</b>
        </div>

        <div class="sh-actions wrap">
          <button class="btn" @click="startMovement">💵 {{ t('shift.cash_in_out') }}</button>
          <button class="btn" :disabled="busy" @click="refreshX(); printReport('x')">🖨 {{ t('shift.print_x') }}</button>
          <div class="spacer"></div>
          <button class="btn btn-danger" @click="mode = 'close'">{{ t('shift.close_btn') }}</button>
        </div>
      </template>

      <!-- CASH MOVEMENT -->
      <template v-else-if="mode === 'cash'">
        <div class="sh-movetypes">
          <button v-for="mt in MOVE_TYPES" :key="mt" class="sh-movetype"
            :class="{ active: moveType === mt, out: mt !== 'Paid In' }"
            @click="moveType = mt">
            {{ mt === 'Paid In' ? '⬇' : '⬆' }} {{ t(`shift.mv.${mt.toLowerCase().replace(/ /g, '_')}`) }}
          </button>
        </div>
        <label class="field">
          <span class="field-label">{{ t('shift.amount') }}</span>
          <input class="input tnum sh-big" type="number" inputmode="decimal" min="0"
            v-model="moveAmount" @keyup.enter="doMovement" autofocus />
        </label>
        <label class="field">
          <span class="field-label">{{ t('shift.reason') }}</span>
          <input class="input" v-model="moveRemarks" :placeholder="t('shift.reason_ph')" @keyup.enter="doMovement" />
        </label>
        <div class="sh-actions">
          <button class="btn" @click="mode = 'status'">{{ t('app.cancel') }}</button>
          <button class="btn btn-primary" :disabled="busy || !moveAmount" @click="doMovement">
            {{ t('shift.record') }}
          </button>
        </div>
      </template>

      <!-- BLIND CLOSE -->
      <template v-else-if="mode === 'close'">
        <div class="sh-lead">{{ t('shift.blind_lead') }}</div>
        <label class="field">
          <span class="field-label">{{ t('shift.counted_cash') }}</span>
          <input class="input tnum sh-big" type="number" inputmode="decimal" min="0"
            v-model="countedCash" @keyup.enter="doClose" autofocus />
        <!-- Handover: A leaves mid-day, C takes the desk with own login.
             A's count closes A's accountability; C's shift opens with
             that exact float. Handover closes never trigger day close. -->
        <label class="field sh-handover">
          <span class="field-label">
            <input type="checkbox" v-model="isHandover" />
            {{ t('shift.handover_toggle') }}
          </span>
          <input v-if="isHandover" class="input" v-model="handoverTo"
                 :placeholder="t('shift.handover_user_ph')" />
        </label>
        </label>
        <label class="field">
          <span class="field-label">{{ t('shift.notes') }}</span>
          <input class="input" v-model="closeNotes" />
        </label>
        <div class="sh-actions">
          <button class="btn" @click="mode = 'status'">{{ t('app.cancel') }}</button>
          <button class="btn btn-danger" :disabled="busy || countedCash === ''" @click="doClose">
            {{ t('shift.confirm_close') }}
          </button>
        </div>
      </template>

      <!-- Z REPORT -->
      <template v-else-if="mode === 'zdone' && zData">
        <div class="sh-variance" :class="varianceClass(zData.variance)">
          <div class="sh-variance-label">{{ t('shift.variance') }}</div>
          <div class="sh-variance-value tnum">{{ fmt(zData.variance) }}</div>
          <div class="sh-variance-sub">
            {{ t('shift.counted') }} {{ fmt(zData.counted_cash) }} · {{ t('shift.expected') }} {{ fmt(zData.expected_cash) }}
          </div>
        </div>
        <div class="sh-grid">
          <div class="sh-kv"><span>{{ t('shift.net_sales') }}<!--mgr--></span><b class="tnum">{{ fmt(zData.net_sales) }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.returns') }}</span><b class="tnum">{{ fmt(zData.returns) }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.credit_sales') }}</span><b class="tnum">{{ fmt(zData.credit_sales) }}</b></div>
          <div class="sh-kv"><span>{{ t('shift.vat') }}</span><b class="tnum">{{ fmt(zData.vat) }}</b></div>
        </div>
        <div class="sh-actions wrap">
          <button class="btn" @click="printReport('z')">🖨 {{ t('shift.print_z') }}</button>
          <!-- Day close moved to the sidebar (supervisor-only) — it is a
               terminal-day action, not part of any one shift's Z panel. -->
          <div class="spacer"></div>
          <button class="btn btn-primary" @click="emit('close')">{{ t('app.done') }}</button>
        </div>
      </template>

      <!-- DAY CLOSE -->
      <template v-else-if="mode === 'dayclose' && dayData">
        <div class="sh-lead"><b>{{ t('shift.day_close_done', { id: dayData.day_close }) }}</b></div>
        <div class="sh-rows">
          <div class="sh-row" v-for="sh2 in dayData.shifts" :key="sh2.shift">
            <span>{{ sh2.shift }} · {{ sh2.user }}</span>
            <b class="tnum" :class="varianceClass(sh2.variance)">{{ fmt(sh2.variance) }}</b>
          </div>
        </div>
        <div class="sh-expected">
          <span>{{ t('shift.day_variance') }}</span>
          <b class="tnum" :class="varianceClass(dayData.variance)">{{ fmt(dayData.variance) }}</b>
        </div>
        <div class="sh-actions">
          <button class="btn" @click="printReport('day')">🖨 {{ t('shift.print_day') }}</button>
          <div class="spacer"></div>
          <button class="btn btn-primary" @click="emit('close')">{{ t('app.done') }}</button>
        </div>
      </template>

      <div v-if="error" class="sh-error">{{ error }}</div>

      <!-- 80mm print surface -->
      <div id="alphax-shift-print" class="sh-print">
        <div class="p-center p-bold">{{ t('app.name') }}</div>
        <div class="p-center">{{ (s || zData || {}).terminal }} · {{ (s || zData || {}).user }}</div>
        <div class="p-hr"></div>
        <template v-if="zData">
          <div class="p-center p-bold">{{ t('shift.print_z') }}</div>
          <div class="p-line"><span>{{ t('shift.net_sales') }}<!--mgr--></span><span>{{ fmt(zData.net_sales) }}</span></div>
          <div class="p-line"><span>{{ t('shift.returns') }}</span><span>{{ fmt(zData.returns) }}</span></div>
          <div class="p-line"><span>{{ t('shift.credit_sales') }}</span><span>{{ fmt(zData.credit_sales) }}</span></div>
          <div class="p-line" v-for="m in zData.by_mop" :key="m.mode_of_payment">
            <span>{{ m.mode_of_payment }}</span><span>{{ fmt(m.amount) }}</span>
          </div>
          <div class="p-hr"></div>
          <div class="p-line"><span>{{ t('shift.expected') }}</span><span>{{ fmt(zData.expected_cash) }}</span></div>
          <div class="p-line"><span>{{ t('shift.counted') }}</span><span>{{ fmt(zData.counted_cash) }}</span></div>
          <div class="p-line p-bold"><span>{{ t('shift.variance') }}</span><span>{{ fmt(zData.variance) }}</span></div>
        </template>
        <template v-else-if="s">
          <div class="p-center p-bold">{{ t('shift.print_x') }}</div>
          <div class="p-line"><span>{{ t('shift.net_sales') }}<!--mgr--></span><span>{{ fmt(s.net_sales) }}</span></div>
          <div class="p-line" v-for="m in s.by_mop" :key="m.mode_of_payment">
            <span>{{ m.mode_of_payment }}</span><span>{{ fmt(m.amount) }}</span>
          </div>
          <div class="p-hr"></div>
          <div class="p-line p-bold"><span>{{ t('shift.expected_cash') }}</span><span>{{ fmt(s.expected_cash) }}</span></div>
        </template>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.sh-body { display: flex; flex-direction: column; gap: 14px; min-width: 380px; }
.sh-bd-note {
  font-size: 12.5px; color: var(--text-dim);
  margin-block: -4px 10px;
}
.sh-bd-note b { color: var(--accent); font-weight: 600; }

.sh-lead { font-size: 13px; color: var(--text-muted); line-height: 1.5; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; color: var(--text-muted); }
.sh-big { font-size: 24px; text-align: center; min-height: 56px; }
.sh-actions { display: flex; gap: 8px; align-items: center; }
.sh-actions .spacer { flex: 1; }
.sh-actions.wrap { flex-wrap: wrap; }
.sh-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sh-kv { display: flex; justify-content: space-between; gap: 8px; font-size: 12.5px;
  padding: 8px 10px; background: var(--surface-2); border-radius: var(--r-md); }
.sh-kv span { color: var(--text-muted); }
.sh-h { margin: 4px 0 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }
.sh-rows { display: flex; flex-direction: column; gap: 4px; }
.sh-row { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 10px;
  border-block-end: 1px dashed var(--border); }
.sh-row.muted { color: var(--text-dim); }
.sh-expected { display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px; background: var(--accent-soft); color: var(--accent);
  border-radius: var(--r-md); font-weight: 700; font-size: 15px; }
.sh-movetypes { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sh-movetype { min-height: 52px; border: 1px solid var(--border); border-radius: var(--r-md);
  background: var(--surface); font-size: 13px; font-weight: 600; color: var(--text-muted); }
.sh-movetype.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.sh-movetype.out.active { border-color: var(--danger); background: var(--danger-soft); color: var(--danger); }
.sh-variance { text-align: center; padding: 18px; border-radius: var(--r-lg); }
.sh-variance.ok { background: var(--accent-soft); color: var(--accent); }
.sh-variance.over { background: var(--warn-soft); color: var(--warn); }
.sh-variance.short { background: var(--danger-soft); color: var(--danger); }
.sh-variance-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }
.sh-variance-value { font-size: 34px; font-weight: 800; }
.sh-variance-sub { font-size: 12px; opacity: 0.85; margin-top: 4px; }
.btn-danger { background: var(--danger); border-color: var(--danger); color: #fff; }
.sh-error { padding: 8px 12px; border-radius: var(--r-md); background: var(--danger-soft); color: var(--danger); font-size: 12.5px; }
.tnum.ok { color: var(--accent); } .tnum.over { color: var(--warn); } .tnum.short { color: var(--danger); }

/* print surface — hidden on screen, exclusive in print */
.sh-print { display: none; }
@media print {
  :global(body.alphax-printing-shift *) { visibility: hidden !important; }
  .sh-print, .sh-print * { visibility: visible !important; }
  .sh-print { display: block; position: fixed; inset: 0 auto auto 0; width: 76mm;
    font-family: 'Courier New', monospace; font-size: 11px; color: #000; background: #fff; padding: 4mm; }
  .p-center { text-align: center; }
  .p-bold { font-weight: 700; }
  .p-hr { border-block-start: 1px dashed #000; margin: 3px 0; }
  .p-line { display: flex; justify-content: space-between; }
}
</style>
