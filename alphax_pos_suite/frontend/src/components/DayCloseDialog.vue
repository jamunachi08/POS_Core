<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

// Day close as a first-class, role-gated action (owner decision): it
// belongs to the TERMINAL's trading day, not to any one shift's Z
// panel. The sidebar button rendering this dialog is supervisor-only,
// and the server enforces the role again regardless.

const emit = defineEmits(['close'])
const { t } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()

const running = ref(false)
const error = ref('')
const result = ref(null)

function printReport() {
  const r = result.value
  const esc = (x) => String(x ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
  const rows = (r.shifts || []).map(s =>
    `<tr><td>${esc(s.user)}</td><td style="text-align:end">${(s.net_sales||0).toFixed(2)}</td>` +
    `<td style="text-align:end">${(s.counted_cash||0).toFixed(2)}</td>` +
    `<td style="text-align:end">${(s.variance||0).toFixed(2)}</td></tr>`).join('')
  const html = `<html><head><style>
    body{font-family:monospace;width:72mm;margin:0 auto;font-size:12px}
    table{width:100%;border-collapse:collapse}
    th{text-align:start;border-bottom:1px solid #000;font-size:11px}
    td{padding:2px 0}
    .tot{display:flex;justify-content:space-between;font-size:13px}
  </style></head><body>
    <h3 style="text-align:center;margin:4px 0">DAY CLOSE</h3>
    <div style="text-align:center">${esc(r.day_close)} · ${esc(r.posting_date)}</div>
    <div style="text-align:center">${esc(store.terminal)}</div><hr>
    <div class="tot"><span>Net sales</span><b>${(r.net_sales||0).toFixed(2)}</b></div>
    <div class="tot"><span>VAT</span><b>${(r.vat_amount||0).toFixed(2)}</b></div>
    <div class="tot"><span>Counted cash</span><b>${(r.counted_cash||0).toFixed(2)}</b></div>
    <div class="tot"><span>Over/Short</span><b>${(r.variance||0).toFixed(2)}</b></div><hr>
    <table><tr><th>Cashier</th><th style="text-align:end">Net</th><th style="text-align:end">Counted</th><th style="text-align:end">±</th></tr>${rows}</table>
    <hr><div style="text-align:center">${new Date().toLocaleString()}</div>
  </body></html>`
  const f = document.createElement('iframe')
  f.style.position = 'fixed'; f.style.right = '-10000px'
  document.body.appendChild(f)
  f.contentDocument.write(html); f.contentDocument.close()
  f.contentWindow.focus(); f.contentWindow.print()
  setTimeout(() => f.remove(), 2000)
}

async function run() {
  running.value = true
  error.value = ''
  try {
    result.value = await api.dayClose(store.terminal)
    store.loadShift()
  } catch (e) {
    error.value = (e && e.message) || String(e)
  }
  running.value = false
}
</script>

<template>
  <AppModal :title="t('dayclose.title')" size="md" @close="emit('close')">
    <template v-if="!result">
      <p class="dc-lead">
        {{ t('dayclose.lead') }} <b>{{ store.businessDate || '—' }}</b>.
        {{ t('dayclose.lead2') }}
      </p>
      <div v-if="store.shift" class="dc-warn">{{ t('dayclose.open_shift_warn') }}</div>
      <div v-if="error" class="dc-error">{{ error }}</div>
    </template>

    <template v-else>
      <div class="dc-done">✓ {{ t('dayclose.done') }} <b>{{ result.day_close }}</b></div>
      <div class="dc-grid">
        <div><span>{{ t('dayclose.net') }}</span><b class="tnum">{{ fmt(result.net_sales || result.summary?.net_sales || 0) }}</b></div>
        <div><span>{{ t('dayclose.vat') }}</span><b class="tnum">{{ fmt(result.vat_amount || result.summary?.vat || 0) }}</b></div>
      </div>
      <div v-if="(result.shifts || []).length" class="dc-shifts">
        <div class="dc-sh-h">{{ t('dayclose.shiftwise') }}</div>
        <div v-for="s in result.shifts" :key="s.shift" class="dc-sh">
          <span>{{ s.user }}</span>
          <span class="tnum">{{ fmt(s.net_sales || 0) }}</span>
          <span class="tnum" :class="{ neg: (s.variance || 0) < 0 }">{{ fmt(s.variance || 0) }}</span>
        </div>
      </div>
    </template>

    <template #footer>
      <button class="btn" @click="emit('close')">{{ result ? t('dayclose.close_btn') : t('dayclose.cancel') }}</button>
      <button v-if="result" class="btn" @click="printReport">🖨 {{ t('dayclose.print') }}</button>
      <button v-if="!result" class="btn btn-danger" :disabled="running" @click="run">
        {{ running ? '…' : t('dayclose.run') }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.dc-lead { font-size: 14px; color: var(--text); }
.dc-warn { margin-block-start: 10px; padding: 10px 12px; border-radius: var(--r-sm);
  background: #b9831722; color: #b98317; font-size: 13px; font-weight: 600; }
.dc-error { margin-block-start: 10px; padding: 10px 12px; border-radius: var(--r-sm);
  background: #b3403c22; color: #b3403c; font-size: 13px; }
.dc-done { font-weight: 800; color: var(--accent); margin-block-end: 10px; }
.dc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-block-end: 12px; }
.dc-grid span { display: block; font-size: 11px; color: var(--text-dim); text-transform: uppercase; }
.dc-shifts { border-top: 1px solid var(--border); padding-block-start: 8px; }
.dc-sh-h { font-size: 11px; color: var(--text-dim); text-transform: uppercase; margin-block-end: 6px; }
.dc-sh { display: grid; grid-template-columns: 1fr auto auto; gap: 12px; padding: 4px 0; font-size: 13px; }
.neg { color: #b3403c; }
</style>
