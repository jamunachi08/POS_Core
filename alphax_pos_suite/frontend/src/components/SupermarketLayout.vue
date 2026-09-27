<script setup>
/**
 * Supermarket layout — scan-first.
 *
 * Design rules, taken from what high-throughput grocery tills actually do:
 *
 *  - The tape (line list) is the biggest thing on screen and it grows
 *    downward with the newest line pinned in view. The cashier's eyes
 *    live there, not on a tile grid.
 *  - The scan field owns focus permanently. Any keystroke that isn't in
 *    another input goes to it. Losing focus is the #1 cause of "the
 *    scanner stopped working".
 *  - No-barcode items live in a small, fixed, high-contrast pad computed
 *    from real sales velocity — produce, bread, bags. Twelve of them
 *    cover the overwhelming majority of manual entries.
 *  - Quantity is a modifier on the LAST line (x3 then scan), not a
 *    separate flow.
 *  - Void-last-line is a single dedicated button because it is the most
 *    frequent correction in grocery and hunting for it costs seconds
 *    on every occurrence.
 *  - Weight comes from the scale automatically when a scale-flagged item
 *    is added; the cashier never types grams.
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useHardwareStore } from '../stores/hardware'
import { api } from '../api/client'
import TopMoversPad from './TopMoversPad.vue'
import NumericKeypad from './NumericKeypad.vue'

const props = defineProps({ layout: { type: Object, required: true } })
const emit = defineEmits(['pay', 'add-customer', 'line-actions', 'price-check'])

const { t } = useI18n()
const store = usePOSStore()
const hw = useHardwareStore()

const scanEl = ref(null)
const scanValue = ref('')
const qtyPrefix = ref(0)          // "3 x" pending multiplier
const lastError = ref('')
const tapeEl = ref(null)
const movers = ref([])
const showKeypad = ref(false)

// ---- permanent focus on the scan field --------------------------------
// A supermarket till has exactly one input that matters. We re-grab focus
// whenever it is lost to anything that isn't another text field.
function grabFocus() {
  const active = document.activeElement
  const typing = active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName) && active !== scanEl.value
  if (!typing) scanEl.value?.focus()
}
let focusTimer = null
onMounted(async () => {
  grabFocus()
  focusTimer = setInterval(grabFocus, 1200)
  document.addEventListener('click', grabFocus)
  if (props.layout.quick?.topMovers) await loadMovers()
})
onUnmounted(() => {
  clearInterval(focusTimer)
  document.removeEventListener('click', grabFocus)
})

async function loadMovers() {
  try {
    movers.value = await api.call(
      'alphax_pos_suite.alphax_pos_suite.pos.top_movers.get_top_movers',
      {
        terminal: store.terminal,
        limit: props.layout.quick.count || 12,
        window_days: props.layout.quick.window_days || 28,
      },
    ) || []
  } catch { movers.value = [] }
}

// ---- scanning ----------------------------------------------------------
async function onScanEnter() {
  const raw = scanValue.value.trim()
  scanValue.value = ''
  if (!raw) return

  // "3*" or "3x" sets a quantity multiplier for the next scan.
  const m = raw.match(/^(\d{1,3})\s*[*x]$/i)
  if (m) { qtyPrefix.value = Number(m[1]); return }

  // A bare number while the tape has lines = change qty of last line.
  if (/^\d{1,3}$/.test(raw) && qtyPrefix.value === 0 && store.cart.length && raw.length <= 2) {
    qtyPrefix.value = Number(raw)
    return
  }

  lastError.value = ''
  const res = await store.scan(raw, { qty: qtyPrefix.value || 1 })
  qtyPrefix.value = 0

  if (!res?.found) {
    lastError.value = store.scanError || t('scan.not_found', { code: raw })
    return
  }
  // Scale-flagged item and a scale is mapped: read weight, don't ask.
  if (res.weighed && hw.scaleReady) {
    const w = await hw.readWeight()
    if (w?.weight) store.setLineQty(store.cart[store.cart.length - 1].line_uuid, w.weight)
  }
  await nextTick()
  tapeEl.value?.scrollTo({ top: tapeEl.value.scrollHeight, behavior: 'smooth' })
}

function voidLast() {
  const last = store.cart[store.cart.length - 1]
  if (last) store.removeLine(last.line_uuid)
}

function bumpQty(line, delta) {
  const next = (line.qty || 0) + delta
  if (next <= 0) store.removeLine(line.line_uuid)
  else store.setLineQty(line.line_uuid, next)
}

const lineCount = computed(() => store.cart.reduce((s, l) => s + (l.qty || 0), 0))
const canPay = computed(() => store.cart.length > 0)

watch(() => store.cart.length, async () => {
  await nextTick()
  tapeEl.value?.scrollTo({ top: tapeEl.value.scrollHeight })
})
</script>

<template>
  <div class="sm-shell" :style="{ gridTemplateColumns: layout.columns }">

    <!-- ============ LEFT: compact action rail ============ -->
    <aside class="sm-rail">
      <button class="rail-btn danger" @click="voidLast" :disabled="!store.cart.length"
              :title="t('supermarket.void_last')">⌫</button>
      <button class="rail-btn" @click="showKeypad = !showKeypad" :title="t('supermarket.qty')">×N</button>
      <button class="rail-btn" @click="$emit('price-check')" :title="t('supermarket.price_check')">?₪</button>
      <button class="rail-btn" @click="$emit('add-customer')" :title="t('cart.customer')">☺</button>
      <div class="rail-spacer"></div>
      <div class="rail-hw" :class="{ ok: hw.online }" :title="hw.online ? 'Bridge online' : 'Bridge offline'">
        {{ hw.online ? '●' : '○' }}
      </div>
    </aside>

    <!-- ============ MIDDLE: scan pad + top movers ============ -->
    <section class="sm-pad">
      <div class="scan-box" :class="{ error: !!lastError }">
        <span class="scan-icon">▤</span>
        <input ref="scanEl" v-model="scanValue" class="scan-input"
               :placeholder="t('supermarket.scan_placeholder')"
               inputmode="none" autocomplete="off" spellcheck="false"
               @keyup.enter="onScanEnter" />
        <span v-if="qtyPrefix" class="qty-chip">{{ qtyPrefix }} ×</span>
      </div>
      <div v-if="lastError" class="scan-error">{{ lastError }}</div>

      <div v-if="hw.liveWeight" class="weight-strip">
        <span class="w-label">{{ t('supermarket.weight') }}</span>
        <span class="w-val">{{ hw.liveWeight.weight }} {{ hw.liveWeight.unit || 'kg' }}</span>
        <span class="w-stable" :class="{ on: hw.liveWeight.stable }">
          {{ hw.liveWeight.stable ? t('supermarket.stable') : t('supermarket.settling') }}
        </span>
      </div>

      <TopMoversPad
        v-if="layout.quick?.topMovers"
        :items="movers"
        :tile="layout.tile"
        @pick="(it) => store.addToCart(it, { qty: qtyPrefix || 1 }) || (qtyPrefix = 0)"
      />

      <NumericKeypad v-if="showKeypad" class="pad-keys"
        @digit="(d) => (scanValue += d)"
        @clear="scanValue = ''"
        @enter="onScanEnter" />
    </section>

    <!-- ============ RIGHT: the tape ============ -->
    <section class="sm-tape-wrap">
      <header class="tape-head">
        <span class="th-count">{{ t('supermarket.items', { n: lineCount }) }}</span>
        <span v-if="store.customer" class="th-cust">{{ store.customerName }}</span>
      </header>

      <div ref="tapeEl" class="tape">
        <div v-if="!store.cart.length" class="tape-empty">
          {{ t('supermarket.tape_empty') }}
        </div>
        <div v-for="(line, i) in store.cart" :key="line.line_uuid"
             class="tape-line" :class="{ last: i === store.cart.length - 1 }"
             @click="$emit('line-actions', line)">
          <div class="tl-main">
            <span class="tl-name">{{ line.item_name }}</span>
            <span class="tl-amt">{{ store.fmt(line.amount) }}</span>
          </div>
          <div class="tl-sub">
            <button class="qbtn" @click.stop="bumpQty(line, -1)">−</button>
            <span class="tl-qty">{{ line.qty }}{{ line.uom && line.uom !== 'Nos' ? ' ' + line.uom : '' }}</span>
            <button class="qbtn" @click.stop="bumpQty(line, 1)">+</button>
            <span class="tl-rate">@ {{ store.fmt(line.rate) }}</span>
            <span v-if="line.discount_amount" class="tl-disc">−{{ store.fmt(line.discount_amount) }}</span>
          </div>
        </div>
      </div>

      <footer class="tape-foot">
        <div class="tf-row"><span>{{ t('cart.subtotal') }}</span><b>{{ store.fmt(store.subtotal) }}</b></div>
        <div class="tf-row" v-if="store.totalDiscount">
          <span>{{ t('cart.discount') }}</span><b>−{{ store.fmt(store.totalDiscount) }}</b>
        </div>
        <div class="tf-row"><span>{{ t('cart.tax') }}</span><b>{{ store.fmt(store.taxTotal) }}</b></div>
        <div class="tf-total"><span>{{ t('cart.total') }}</span><b>{{ store.fmt(store.grandTotal) }}</b></div>
        <button class="pay-btn" :disabled="!canPay" @click="$emit('pay')">
          {{ t('cart.pay') }} · {{ store.fmt(store.grandTotal) }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.sm-shell { display: grid; gap: 10px; height: 100%; min-height: 0; padding: 10px; }

/* rail */
.sm-rail { display: flex; flex-direction: column; gap: 8px; align-items: center; }
.rail-btn { width: 44px; height: 44px; border-radius: var(--r-md); background: var(--surface-2);
  color: var(--text); font-size: 17px; border: 1px solid var(--border); }
.rail-btn:hover { border-color: var(--accent); }
.rail-btn.danger { color: var(--danger); }
.rail-btn:disabled { opacity: .35; }
.rail-spacer { flex: 1; }
.rail-hw { font-size: 13px; color: var(--danger); }
.rail-hw.ok { color: var(--success, #16a34a); }

/* scan pad */
.sm-pad { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.scan-box { display: flex; align-items: center; gap: 10px; background: var(--surface);
  border: 2px solid var(--accent); border-radius: var(--r-md); padding: 0 14px; height: 62px; flex: none; }
.scan-box.error { border-color: var(--danger); }
.scan-icon { font-size: 20px; color: var(--accent); }
.scan-input { flex: 1; border: none; background: transparent; outline: none;
  font-size: 22px; font-weight: 500; color: var(--text); letter-spacing: .5px; }
.qty-chip { background: var(--accent); color: #fff; padding: 4px 10px; border-radius: var(--r-sm);
  font-size: 15px; font-weight: 700; }
.scan-error { font-size: 13px; color: var(--danger); padding-inline-start: 4px; }

.weight-strip { display: flex; align-items: center; gap: 12px; background: var(--surface-2);
  padding: 9px 14px; border-radius: var(--r-sm); flex: none; }
.w-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .5px; }
.w-val { font-size: 20px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.w-stable { font-size: 11px; color: var(--text-dim); margin-inline-start: auto; }
.w-stable.on { color: var(--success, #16a34a); }

.pad-keys { flex: none; }

/* tape */
.sm-tape-wrap { display: flex; flex-direction: column; background: var(--surface);
  border-radius: var(--r-md); overflow: hidden; min-height: 0; }
.tape-head { display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid var(--border); flex: none; }
.th-count { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .5px; }
.th-cust { font-size: 12px; color: var(--accent); font-weight: 600; }

.tape { flex: 1; overflow-y: auto; padding: 4px 0; min-height: 0; }
.tape-empty { padding: 40px 20px; text-align: center; color: var(--text-dim); font-size: 13px; }
.tape-line { padding: 8px 14px; border-bottom: 1px solid var(--border-soft, rgba(0,0,0,.05)); }
.tape-line.last { background: var(--accent-soft); }
.tl-main { display: flex; justify-content: space-between; gap: 10px; }
.tl-name { font-size: 14px; font-weight: 500; color: var(--text); }
.tl-amt { font-size: 15px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.tl-sub { display: flex; align-items: center; gap: 7px; margin-block-start: 3px; }
.qbtn { width: 22px; height: 22px; border-radius: var(--r-sm); background: var(--surface-2);
  color: var(--text); font-size: 13px; line-height: 1; }
.tl-qty { font-size: 13px; font-weight: 600; min-width: 34px; text-align: center;
  font-variant-numeric: tabular-nums; }
.tl-rate { font-size: 11px; color: var(--text-dim); }
.tl-disc { font-size: 11px; color: var(--success, #16a34a); margin-inline-start: auto; }

.tape-foot { padding: 12px 14px; border-top: 1px solid var(--border);
  background: var(--surface-2); flex: none; }
.tf-row { display: flex; justify-content: space-between; font-size: 12.5px;
  color: var(--text-dim); padding: 2px 0; }
.tf-row b { color: var(--text); font-variant-numeric: tabular-nums; }
.tf-total { display: flex; justify-content: space-between; align-items: baseline;
  margin-block: 8px 10px; padding-block-start: 8px; border-top: 1px solid var(--border); }
.tf-total span { font-size: 13px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .5px; }
.tf-total b { font-size: 26px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.pay-btn { width: 100%; height: 56px; border-radius: var(--r-md); background: var(--accent);
  color: #fff; font-size: 17px; font-weight: 600; }
.pay-btn:disabled { opacity: .4; }
</style>
