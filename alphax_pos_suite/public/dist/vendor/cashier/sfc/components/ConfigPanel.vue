<script setup>
// One-stop configuration panel for the cashier screen.
//
// Read side (everyone): terminal, outlet, POS profile, active domains,
// the feature flags currently in effect, and the policy settings from
// AlphaX POS Settings — so a cashier or support engineer can see at a
// glance WHY a button is disabled, without opening the desk.
//
// Write side (manager roles only, enforced server-side): the safe
// subset of policy toggles — manager gates, returns, tips, service
// charge. Accounting-critical settings deliberately stay desk-only.
//
// Saving invalidates the server boot cache and reloads the boot payload
// so changes take effect immediately on this terminal.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

const emit = defineEmits(['close'])
const { t } = useI18n()
const store = usePOSStore()

const loading = ref(true)
const saving = ref(false)
const canEdit = ref(false)
const editable = ref([])
const form = ref({})
const savedFlash = ref(false)
const error = ref('')

const TOGGLES = [
  'require_manager_for_void',
  'require_manager_for_discount',
  'price_override_requires_approval',
  'allow_returns',
  'require_shift_open',
  'enable_tips',
  'enable_service_charge',
]

const outlet = computed(() => store.boot?.outlet || {})
const terminal = computed(() => store.boot?.terminal || {})
const profile = computed(() => store.boot?.profile || {})
const domains = computed(() => store.boot?.domains || [])
const features = computed(() => store.activeFeatures || {})

const activeFeatureKeys = computed(() =>
  Object.entries(features.value).filter(([, v]) => v).map(([k]) => k))

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.getCashierSettings()
    canEdit.value = !!res.can_edit
    editable.value = res.editable_fields || []
    form.value = { ...(res.settings || {}) }
  } catch (e) {
    // Older server without the endpoint — fall back to the boot copy,
    // read-only.
    canEdit.value = false
    form.value = { ...(store.settings || {}) }
  } finally {
    loading.value = false
  }
}

function isEditable(field) {
  return canEdit.value && editable.value.includes(field)
}

async function save() {
  if (!canEdit.value) return
  saving.value = true
  error.value = ''
  try {
    const changes = {}
    for (const f of editable.value) {
      if (f in form.value) changes[f] = form.value[f]
    }
    await api.updateCashierSettings(changes)
    await store.loadBoot()
    savedFlash.value = true
    setTimeout(() => (savedFlash.value = false), 1800)
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

async function refreshBoot() {
  saving.value = true
  try {
    await api.invalidateBootCache(store.terminal || null)
    await store.loadBoot()
    savedFlash.value = true
    setTimeout(() => (savedFlash.value = false), 1800)
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

function openDeskSettings() {
  window.open('/app/alphax-pos-settings', '_blank')
}
</script>

<template>
  <AppModal :title="t('config.title')" size="lg" @close="emit('close')">
    <div class="cfg-body" v-if="!loading">

      <!-- Appearance -->
      <section class="cfg-section">
        <h4 class="cfg-h">{{ t('config.appearance') }}</h4>
        <div class="cfg-themes">
          <button
            v-for="th in ['emerald', 'ocean', 'sand', 'dark', 'graphite', 'rose', 'violet', 'gold']"
            :key="th"
            class="cfg-theme"
            :class="{ active: store.theme === th }"
            @click="store.setTheme(th)"
          >
            <span class="cfg-swatch" :data-theme="th"></span>
            <span>{{ t(`config.themes.${th}`) }}</span>
          </button>
        </div>
      </section>

      <!-- Identity: what am I running on? -->
      <section class="cfg-section">
        <h4 class="cfg-h">{{ t('config.this_terminal') }}</h4>
        <div class="cfg-grid">
          <div class="cfg-kv"><span>{{ t('config.terminal') }}</span><b>{{ terminal.terminal_name || terminal.name || '—' }}</b></div>
          <div class="cfg-kv"><span>{{ t('config.outlet') }}</span><b>{{ outlet.outlet_name || outlet.name || '—' }}</b></div>
          <div class="cfg-kv"><span>{{ t('config.company') }}</span><b>{{ outlet.company || '—' }}</b></div>
          <div class="cfg-kv"><span>{{ t('config.pos_profile') }}</span><b>{{ profile.name || '—' }}</b></div>
          <div class="cfg-kv"><span>{{ t('config.warehouse') }}</span><b>{{ outlet.warehouse || '—' }}</b></div>
          <div class="cfg-kv"><span>{{ t('config.price_list') }}</span><b>{{ outlet.default_price_list || '—' }}</b></div>
        </div>
      </section>

      <!-- Domains + features currently in effect -->
      <section class="cfg-section">
        <h4 class="cfg-h">{{ t('config.domains_features') }}</h4>
        <div class="cfg-chips">
          <span v-for="d in domains" :key="d.domain_code" class="chip chip-domain"
            :class="{ active: store.activeDomain === d.domain_code }">
            {{ t(`domains.${d.domain_code}`) }}
          </span>
        </div>
        <div class="cfg-chips">
          <span v-for="f in activeFeatureKeys" :key="f" class="chip">{{ f.replace(/^uses_/, '').replace(/_/g, ' ') }}</span>
          <span v-if="!activeFeatureKeys.length" class="cfg-muted">{{ t('config.no_features') }}</span>
        </div>
      </section>

      <!-- Policy settings -->
      <section class="cfg-section">
        <h4 class="cfg-h">
          {{ t('config.policy') }}
          <span v-if="!canEdit" class="cfg-ro">{{ t('config.read_only') }}</span>
        </h4>
        <div class="cfg-toggles">
          <label v-for="f in TOGGLES" :key="f" class="cfg-toggle" :class="{ disabled: !isEditable(f) }">
            <input type="checkbox" :disabled="!isEditable(f)"
              :checked="!!form[f]" @change="form[f] = $event.target.checked ? 1 : 0" />
            <span>{{ t(`config.fields.${f}`) }}</span>
          </label>
        </div>
        <div class="cfg-grid">
          <label class="cfg-kv cfg-input-kv">
            <span>{{ t('config.fields.discount_threshold_percent') }}</span>
            <input class="input cfg-num tnum" type="number" min="0" max="100" step="0.5"
              :disabled="!isEditable('discount_threshold_percent')"
              v-model.number="form.discount_threshold_percent" />
          </label>
          <label class="cfg-kv cfg-input-kv">
            <span>{{ t('config.fields.return_settlement_modes') }}</span>
            <select class="input" :disabled="!isEditable('return_settlement_modes')"
              v-model="form.return_settlement_modes">
              <option>Cash Refund Only</option>
              <option>Credit Note Only</option>
              <option>Cash Refund or Credit Note</option>
            </select>
          </label>
        </div>
      </section>

      <div v-if="error" class="cfg-error">{{ error }}</div>

      <div class="cfg-actions">
        <button class="btn" @click="openDeskSettings">{{ t('config.open_desk') }}</button>
        <button class="btn" :disabled="saving" @click="refreshBoot">{{ t('config.reload_boot') }}</button>
        <div class="spacer"></div>
        <span v-if="savedFlash" class="cfg-saved">✓ {{ t('app.save') }}d</span>
        <button v-if="canEdit" class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? '…' : t('app.save') }}
        </button>
      </div>
    </div>
    <div v-else class="cfg-loading">{{ t('app.loading') }}</div>
  </AppModal>
</template>

<style scoped>
.cfg-body { display: flex; flex-direction: column; gap: 18px; min-width: 420px; }
.cfg-loading { padding: 30px; text-align: center; color: var(--text-muted); }
.cfg-section { display: flex; flex-direction: column; gap: 10px; }
.cfg-h {
  margin: 0; font-size: 12px; font-weight: 600; letter-spacing: 0.4px;
  text-transform: uppercase; color: var(--text-muted);
  display: flex; align-items: center; gap: 8px;
}
.cfg-ro {
  font-size: 10px; padding: 2px 8px; border-radius: 999px;
  background: var(--surface-2); text-transform: none; letter-spacing: 0;
}
.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.cfg-kv {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  font-size: 12.5px; padding: 7px 10px;
  background: var(--surface-2); border-radius: var(--r-md);
}
.cfg-kv span { color: var(--text-muted); }
.cfg-kv b { font-weight: 600; text-align: end; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.cfg-input-kv { cursor: default; }
.cfg-num { width: 90px; text-align: end; }
.cfg-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 11.5px; padding: 4px 10px; border-radius: 999px;
  background: var(--surface-2); color: var(--text);
  border: 1px solid var(--border);
}
.chip-domain.active { background: var(--accent-soft, var(--surface-2)); border-color: var(--accent); color: var(--accent); }
.cfg-muted { font-size: 12px; color: var(--text-muted); }
.cfg-toggles { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.cfg-toggle {
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; padding: 9px 10px;
  background: var(--surface-2); border-radius: var(--r-md);
  cursor: pointer;
}
.cfg-toggle.disabled { opacity: 0.65; cursor: default; }
.cfg-toggle input { width: 16px; height: 16px; accent-color: var(--accent); }
.cfg-error {
  padding: 8px 12px; border-radius: var(--r-md);
  background: var(--danger-soft); color: var(--danger); font-size: 12.5px;
}
.cfg-actions { display: flex; align-items: center; gap: 8px; }
.cfg-actions .spacer { flex: 1; }
.cfg-saved { font-size: 12.5px; color: var(--success, #2e7d4f); }
@media (max-width: 640px) {
  .cfg-body { min-width: 0; }
  .cfg-grid, .cfg-toggles { grid-template-columns: 1fr; }
}
.cfg-themes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.cfg-theme {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  min-height: 64px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-2);
  font-size: 11.5px;
  color: var(--text-muted);
}
.cfg-theme.active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
.cfg-swatch {
  width: 28px; height: 28px; border-radius: 50%;
  border: 2px solid var(--border-strong);
  background: var(--accent);
}
.cfg-swatch[data-theme="emerald"] { background: #0F6E56; }
.cfg-swatch[data-theme="ocean"]   { background: #185FA5; }
.cfg-swatch[data-theme="sand"]    { background: #8C5A18; }
.cfg-swatch[data-theme="dark"]    { background: #1C1F1D; }
.cfg-swatch[data-theme="graphite"]{ background: #6E9BFF; }
.cfg-swatch[data-theme="rose"]    { background: #B0355C; }
.cfg-swatch[data-theme="violet"]  { background: #5B3FA8; }
.cfg-swatch[data-theme="gold"]    { background: #D9A62E; }
@media (max-width: 640px) { .cfg-themes { grid-template-columns: repeat(2, 1fr); } }
</style>
