<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['close'])

// State
const mode = ref('search')           // 'search' | 'detail'
const query = ref('')
const searching = ref(false)
const results = ref([])
const selectedRx = ref(null)         // current Rx detail
const lines = ref([])
const loadingLines = ref(false)
const error = ref('')

// On open: if context already has an Rx number, jump straight to detail.
onMounted(() => {
  if (store.context.rx_number) {
    loadPrescription(store.context.rx_number)
  } else {
    // Auto-focus search box and trigger empty search to show recent ones.
    runSearch()
  }
})

// -----------------------------------------------------------------
// Search
// -----------------------------------------------------------------

async function runSearch() {
  searching.value = true
  error.value = ''
  try {
    const r = await frappe.call({
      method: 'alphax_pos_suite.alphax_pos_suite.pharmacy.api.search_active_prescriptions',
      args: {
        query: query.value,
        outlet: store.boot?.outlet?.name || null,
        limit: 30,
      },
    })
    results.value = r.message || []
  } catch (e) {
    error.value = e.message || String(e)
    results.value = []
  } finally {
    searching.value = false
  }
}

let searchDebounce = null
function onQueryInput() {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(runSearch, 250)
}

// -----------------------------------------------------------------
// Detail
// -----------------------------------------------------------------

async function loadPrescription(rxName) {
  selectedRx.value = results.value.find(r => r.name === rxName) || { name: rxName }
  loadingLines.value = true
  error.value = ''
  try {
    const r = await frappe.call({
      method: 'alphax_pos_suite.alphax_pos_suite.pharmacy.api.get_prescription_lines',
      args: { prescription_name: rxName },
    })
    lines.value = r.message || []
    mode.value = 'detail'
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loadingLines.value = false
  }
}

function backToSearch() {
  mode.value = 'search'
  selectedRx.value = null
  lines.value = []
}

// -----------------------------------------------------------------
// Add a line to the cart
// -----------------------------------------------------------------

async function addLineToCart(line) {
  if (!line.linked_item) {
    error.value = t('pharmacy.no_linked_item', { drug: line.drug_name })
    return
  }
  if (line.refills_remaining <= 0 && line.already_dispensed) {
    error.value = t('pharmacy.no_refills_left', { drug: line.drug_name })
    return
  }

  // Authorize the dispense before adding to cart.
  const auth = await frappe.call({
    method: 'alphax_pos_suite.alphax_pos_suite.pharmacy.api.authorize_dispense',
    args: { drug_code: line.drug_code, prescription_name: selectedRx.value.name },
  })
  if (!auth.message?.ok) {
    error.value = auth.message?.reason || t('pharmacy.dispense_denied')
    return
  }

  // Stamp the prescription metadata onto the cart line so the
  // sales-invoice on_submit hook can call record_dispensing.
  store.addItem({
    item_code: line.linked_item,
    item_name: `${line.drug_name} ${line.strength || ''}${line.strength_unit || ''}`.trim(),
    qty:       line.quantity_dispensed,
    rate:      null,                       // pulled from item price list
    metadata: {
      alphax_prescription:      selectedRx.value.name,
      alphax_prescription_line: line.line_name,
      alphax_drug_code:         line.drug_code,
      alphax_is_controlled:     line.is_controlled,
    },
  })

  // Update local UI state so the user sees this line as added.
  line.added_to_cart = true
  error.value = ''
}

// -----------------------------------------------------------------
// Status helpers
// -----------------------------------------------------------------

function statusClass(status) {
  return {
    'rx-status': true,
    'rx-status-active': status === 'Active',
    'rx-status-partial': status === 'Partially Dispensed',
    'rx-status-done': status === 'Fully Dispensed',
    'rx-status-expired': status === 'Expired',
  }
}

const remaining = computed(() => {
  return lines.value.filter(l => !l.already_dispensed || l.refills_remaining > 0)
})
</script>

<template>
  <AppModal :title="t('pharmacy.prescription_lookup')" size="lg" @close="emit('close')">

    <!-- SEARCH MODE -->
    <div v-if="mode === 'search'">
      <input
        class="rx-search"
        v-model="query"
        @input="onQueryInput"
        :placeholder="t('pharmacy.search_placeholder')"
        autofocus
      />
      <div v-if="searching" class="rx-loading">{{ t('app.loading') }}…</div>
      <div v-else-if="results.length === 0" class="rx-empty">
        {{ query ? t('pharmacy.no_matches') : t('pharmacy.no_active_rx') }}
      </div>
      <div v-else class="rx-results">
        <div v-for="r in results" :key="r.name"
             class="rx-row" @click="loadPrescription(r.name)">
          <div class="rx-row-main">
            <div class="rx-name">{{ r.patient_name }}</div>
            <div class="rx-sub">
              {{ r.patient_id || r.patient_phone || '—' }} · {{ r.prescriber_name }}
            </div>
          </div>
          <div class="rx-row-meta">
            <span :class="statusClass(r.status)">{{ r.status }}</span>
            <span class="rx-date">{{ r.prescription_date }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- DETAIL MODE -->
    <div v-else-if="mode === 'detail'">
      <button class="rx-back" @click="backToSearch">← {{ t('pharmacy.back_to_search') }}</button>

      <div class="rx-header">
        <div>
          <div class="rx-name">{{ selectedRx.patient_name }}</div>
          <div class="rx-sub">
            {{ selectedRx.patient_id || '—' }} · {{ selectedRx.prescriber_name }}
          </div>
        </div>
        <div class="rx-meta">
          <div class="rx-id">{{ selectedRx.name }}</div>
          <div class="rx-date">{{ t('pharmacy.expires') }}: {{ selectedRx.expiry_date || '—' }}</div>
        </div>
      </div>

      <div v-if="loadingLines" class="rx-loading">{{ t('app.loading') }}…</div>
      <div v-else-if="!lines.length" class="rx-empty">{{ t('pharmacy.no_lines') }}</div>
      <div v-else class="rx-lines">
        <div v-for="line in lines" :key="line.line_name" class="rx-line">
          <div class="rx-line-head">
            <span class="rx-drug">{{ line.drug_name }}</span>
            <span v-if="line.is_controlled" class="rx-ctrl">{{ t('pharmacy.controlled') }}</span>
          </div>
          <div class="rx-line-detail">
            {{ line.dose }}{{ line.dose_unit }} ×
            {{ line.frequency_per_day }}/{{ t('pharmacy.day') }} ×
            {{ line.duration_days }}{{ t('pharmacy.days_short') }}
            = {{ line.quantity_dispensed }} {{ line.dose_unit }}
          </div>
          <div class="rx-line-foot">
            <span class="rx-refills">
              {{ t('pharmacy.refills_remaining') }}: <b>{{ line.refills_remaining }}</b>
            </span>
            <button
              class="rx-add-btn"
              :disabled="line.added_to_cart || (line.already_dispensed && line.refills_remaining <= 0)"
              @click="addLineToCart(line)"
            >
              {{ line.added_to_cart ? '✓ ' + t('pharmacy.added') : t('pharmacy.add_to_cart') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="rx-error">{{ error }}</div>
  </AppModal>
</template>

<style scoped>
.rx-search {
  width: 100%;
  padding: 12px 14px;
  font-size: 16px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  margin-bottom: 12px;
}
.rx-loading, .rx-empty {
  text-align: center;
  padding: 32px;
  color: var(--muted, #888);
  font-size: 14px;
}
.rx-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 400px;
  overflow-y: auto;
}
.rx-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.1s;
}
.rx-row:hover { background: #f9fafb; }
.rx-row-main { flex: 1; }
.rx-name { font-weight: 600; font-size: 15px; }
.rx-sub { font-size: 12px; color: var(--muted, #888); margin-top: 2px; }
.rx-row-meta { text-align: end; font-size: 11px; }
.rx-status {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
}
.rx-status-active { background: #d1fae5; color: #065f46; }
.rx-status-partial { background: #fef3c7; color: #92400e; }
.rx-status-done { background: #e5e7eb; color: #374151; }
.rx-status-expired { background: #fee2e2; color: #991b1b; }
.rx-date { display: block; margin-top: 4px; color: var(--muted, #888); }

.rx-back {
  background: none;
  border: none;
  color: var(--accent, #0F6E56);
  cursor: pointer;
  font-size: 13px;
  padding: 0;
  margin-bottom: 10px;
}
.rx-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}
.rx-id { font-family: monospace; font-size: 13px; color: var(--muted, #888); }

.rx-lines { display: flex; flex-direction: column; gap: 10px; }
.rx-line {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
}
.rx-line-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.rx-drug { font-weight: 600; font-size: 15px; }
.rx-ctrl {
  background: #fef2f2;
  color: #991b1b;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.rx-line-detail { font-size: 13px; color: #444; margin-bottom: 8px; }
.rx-line-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.rx-refills { font-size: 12px; color: var(--muted, #888); }
.rx-add-btn {
  background: var(--accent, #0F6E56);
  color: #fff;
  border: none;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 13px;
  cursor: pointer;
}
.rx-add-btn:disabled { background: #9ca3af; cursor: not-allowed; }

.rx-error {
  margin-top: 14px;
  padding: 10px 12px;
  background: #fef2f2;
  color: #991b1b;
  border-radius: 8px;
  font-size: 13px;
}
</style>
