<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useHardwareStore } from '../stores/hardware'
import { useMoney } from '../composables/useMoney'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

// View-only by design: this dialog exposes no edit, void, or return
// action — cashiers verify and reprint, nothing else. The server side
// (pos/history_api.py) is equally read-only, so even a modified client
// cannot mutate through it.

const emit = defineEmits(['close'])
const { t } = useI18n()
const store = usePOSStore()
const hw = useHardwareStore()
const { fmt } = useMoney()

const TABS = ['history', 'unpaid', 'drafts', 'returns']
const tab = ref('history')
const rows = ref([])
const counts = ref({})
const kpi = ref(null)
const loading = ref(false)
const error = ref('')
const search = ref('')
// Default both bounds to the shift's TRADING day (business date) —
// what a cashier means by "today" even at 12:40 AM. Clearing either
// widens the range.
const fromDate = ref(store.businessDate || '')
const toDate = ref(store.businessDate || '')
const printingRow = ref('')

let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 350)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.listInvoiceHistory({
      terminal: store.terminal,
      tab: tab.value,
      search: search.value || null,
      from_date: fromDate.value || null,
      to_date: toDate.value || null,
    })
    rows.value = res.rows || []
    counts.value = res.counts || {}
    kpi.value = res.kpi || null
  } catch (e) {
    error.value = (e && e.message) || String(e)
    rows.value = []
  }
  loading.value = false
}

function setTab(name) {
  tab.value = name
  load()
}

function statusClass(r) {
  if (r.docstatus === 0) return 'st-draft'
  if (r.is_return) return 'st-return'
  if ((r.outstanding_amount || 0) > 0.005) return 'st-unpaid'
  return 'st-paid'
}
function statusLabel(r) {
  if (r.docstatus === 0) return t('history.st_draft')
  if (r.is_return) return t('history.st_return')
  if ((r.outstanding_amount || 0) > 0.005) return t('history.st_unpaid')
  return t('history.st_paid')
}

async function reprint(r) {
  printingRow.value = r.name
  try {
    const receipt = await api.getInvoiceReceipt(r.name)
    if (hw.printerReady) {
      await hw.printReceipt(receipt, { kind: 'receipt' })
    } else {
      browserPrint(receipt)
    }
  } catch (e) {
    error.value = (e && e.message) || String(e)
  }
  printingRow.value = ''
}

function browserPrint(rc) {
  // Bridge offline → 80mm-styled browser print in a throwaway iframe.
  // Deliberately plain: verification copy, not the thermal original.
  const esc = (s) => String(s ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  const lines = []
  lines.push(`<h2>${esc(rc.header.store_name)}</h2>`)
  if (rc.header.branch) lines.push(`<div>${esc(rc.header.branch)}</div>`)
  if (rc.header.vat_no) lines.push(`<div>VAT: ${esc(rc.header.vat_no)}</div>`)
  lines.push(`<hr><div><b>${esc(rc.meta.invoice_no)}</b></div>`)
  lines.push(`<div>${esc(rc.meta.datetime)} · ${esc(rc.meta.customer)}</div><hr>`)
  lines.push('<table style="width:100%;border-collapse:collapse">')
  for (const it of rc.items) {
    lines.push(`<tr><td>${esc(it.name)}</td><td style="text-align:end">${it.qty} × ${it.rate}</td><td style="text-align:end">${it.amount.toFixed(2)}</td></tr>`)
  }
  lines.push('</table><hr>')
  lines.push(`<div style="display:flex;justify-content:space-between"><span>${esc(t('history.subtotal'))}</span><b>${rc.totals.subtotal.toFixed(2)}</b></div>`)
  lines.push(`<div style="display:flex;justify-content:space-between"><span>${esc(t('history.tax'))}</span><b>${rc.totals.tax.toFixed(2)}</b></div>`)
  lines.push(`<div style="display:flex;justify-content:space-between;font-size:1.15em"><span>${esc(t('history.total'))}</span><b>${rc.totals.total.toFixed(2)}</b></div>`)
  for (const p of rc.payments) {
    lines.push(`<div style="display:flex;justify-content:space-between"><span>${esc(p.mode)}</span><span>${p.amount.toFixed(2)}</span></div>`)
  }
  if (rc.zatca_qr) {
    // TLV base64 is data, not an image; the bridge renders the actual
    // QR. The browser copy notes its presence so the verification copy
    // is honest about what the thermal original carries.
    lines.push(`<hr><div style="text-align:center;font-size:10px;word-break:break-all">ZATCA: ${esc(rc.zatca_qr.slice(0, 48))}…</div>`)
  }
  lines.push(`<hr><div style="text-align:center;font-weight:700">${esc(rc.footer.line1)}</div>`)
  const frame = document.createElement('iframe')
  frame.style.position = 'fixed'
  frame.style.right = '-10000px'
  document.body.appendChild(frame)
  frame.contentDocument.write(
    `<html><head><style>body{font-family:monospace;width:72mm;margin:0 auto;font-size:12px}</style></head><body>${lines.join('')}</body></html>`
  )
  frame.contentDocument.close()
  frame.contentWindow.focus()
  frame.contentWindow.print()
  setTimeout(() => frame.remove(), 2000)
}

const kpiCards = computed(() => kpi.value ? [
  { label: t('history.kpi_invoices'), value: String(kpi.value.invoices), cls: 'k-inv' },
  { label: t('history.kpi_gross'), value: fmt(kpi.value.gross), cls: 'k-gross' },
  { label: t('history.kpi_tendered'), value: fmt(kpi.value.tendered), cls: 'k-tender' },
  { label: t('history.kpi_change'), value: fmt(kpi.value.change_returned), cls: 'k-change' },
  { label: t('history.kpi_outstanding'), value: fmt(kpi.value.outstanding), cls: 'k-out' },
] : [])

onMounted(load)
</script>

<template>
  <AppModal :title="t('history.title')" size="lg" @close="emit('close')">
    <div class="ih-tabs">
      <button v-for="name in TABS" :key="name"
        class="ih-tab" :class="{ active: tab === name }" @click="setTab(name)">
        {{ t('history.tab_' + name) }}
        <span class="ih-count" :class="'c-' + name">{{ counts[name] ?? '·' }}</span>
      </button>
    </div>

    <div class="ih-filters">
      <input class="input" :placeholder="t('history.search_ph')"
        v-model="search" @input="onSearchInput" />
      <input class="input" type="date" v-model="fromDate" @change="load" />
      <input class="input" type="date" v-model="toDate" @change="load" />
    </div>

    <!-- Blind-close policy: daily totals are supervisor information.
         Cashiers keep search, cards, and reprint. -->
    <div v-if="kpiCards.length && store.boot?.is_manager" class="ih-kpis">
      <div v-for="k in kpiCards" :key="k.label" class="ih-kpi" :class="k.cls">
        <div class="k-label">{{ k.label }}</div>
        <div class="k-value tnum">{{ k.value }}</div>
      </div>
    </div>

    <div v-if="error" class="ih-error">{{ error }}</div>
    <div v-else-if="loading" class="ih-empty">…</div>
    <div v-else-if="rows.length === 0" class="ih-empty">{{ t('history.empty') }}</div>

    <div v-else class="ih-grid">
      <div v-for="r in rows" :key="r.name" class="ih-card">
        <div class="ih-card-top">
          <div>
            <div class="ih-name">{{ r.name }}</div>
            <span class="ih-status" :class="statusClass(r)">{{ statusLabel(r) }}</span>
          </div>
          <div class="ih-total tnum">{{ fmt(r.grand_total) }}</div>
        </div>
        <div class="ih-meta">
          <span>{{ r.posting_date }} {{ (r.posting_time || '').slice(0, 8) }}</span>
          <span class="ih-cust">{{ r.customer_name || r.customer }}</span>
        </div>
        <div class="ih-figures">
          <div><span>{{ t('history.tendered') }}</span><b class="tnum">{{ fmt(r.paid_amount) }}</b></div>
          <div><span>{{ t('history.outstanding') }}</span><b class="tnum">{{ fmt(r.outstanding_amount) }}</b></div>
        </div>
        <button class="btn ih-print" :disabled="printingRow === r.name" @click="reprint(r)">
          🖨 {{ printingRow === r.name ? '…' : t('history.reprint') }}
        </button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.ih-tabs { display: flex; gap: 6px; margin-block-end: 10px; flex-wrap: wrap; }
.ih-tab {
  padding: 8px 12px; border-radius: var(--r-sm);
  border: 1px solid var(--border); background: var(--surface-2);
  color: var(--text); font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
}
.ih-tab.active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
.ih-count { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: var(--surface-3); }
.c-unpaid { background: #b98317; color: #fff; }
.c-returns { background: #b3403c; color: #fff; }
.c-drafts { background: #2e7d4f; color: #fff; }

.ih-filters { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 8px; margin-block-end: 10px; }
.ih-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-block-end: 12px; }
.ih-kpi { border-radius: var(--r-md); padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); }
.k-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .04em; }
.k-value { font-size: 16px; font-weight: 700; margin-block-start: 2px; }
.k-gross .k-value { color: var(--accent); }
.k-out .k-value { color: #b98317; }

.ih-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; max-height: 46vh; overflow-y: auto; }
.ih-card { border: 1px solid var(--border); border-radius: var(--r-md); padding: 12px; background: var(--surface-1); display: flex; flex-direction: column; gap: 8px; }
.ih-card-top { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
.ih-name { font-weight: 700; font-size: 13px; word-break: break-all; }
.ih-total { font-size: 16px; font-weight: 700; }
.ih-status { display: inline-block; margin-block-start: 4px; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }
.st-paid { background: #1f6e43; color: #fff; }
.st-unpaid { background: #b98317; color: #fff; }
.st-draft { background: var(--surface-3); color: var(--text); }
.st-return { background: #b3403c; color: #fff; }
.ih-meta { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--text-dim); }
.ih-cust { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 55%; }
.ih-figures { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 12px; }
.ih-figures span { color: var(--text-dim); display: block; font-size: 11px; }
.ih-print { margin-block-start: auto; }
.ih-error { color: #b3403c; padding: 14px; font-size: 13px; }
.ih-empty { color: var(--text-dim); text-align: center; padding: 28px; }
</style>
