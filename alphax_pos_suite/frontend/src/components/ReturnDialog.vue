<script setup>
// Return-mode entry dialog.
//
// The cashier picks (or types) a return reason, sees the settlement
// policy configured in AlphaX POS Settings, and confirms. The manager
// PIN gate — when require_manager_for_void is on — is handled by
// CashierView BEFORE this dialog opens, so by the time we're mounted
// the action is already authorized.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

const emit = defineEmits(['close', 'confirm'])
const { t } = useI18n()
const store = usePOSStore()

const reasons = ref([])
const loading = ref(true)
const picked = ref('')
const freeText = ref('')

const settlement = computed(() =>
  store.settings.return_settlement_modes || t('returns.settlement_default'))

const reason = computed(() => picked.value || freeText.value.trim())

onMounted(async () => {
  try {
    const rows = await api.listReturnReasons()
    reasons.value = (rows || []).map(r => r.reason || r.reason_title || r.title || r.description || r.name)
  } catch (e) {
    reasons.value = []
  } finally {
    loading.value = false
  }
})

function pickReason(r) {
  picked.value = picked.value === r ? '' : r
  if (picked.value) freeText.value = ''
}

function confirm() {
  if (!reason.value) return
  emit('confirm', reason.value)
  emit('close')
}
</script>

<template>
  <AppModal :title="t('returns.title')" @close="emit('close')">
    <div class="ret-body">
      <div class="ret-policy">
        <span class="ret-policy-label">{{ t('returns.settlement') }}:</span>
        <b>{{ settlement }}</b>
      </div>

      <div class="ret-reasons" v-if="!loading && reasons.length">
        <button
          v-for="r in reasons" :key="r"
          class="ret-reason"
          :class="{ active: picked === r }"
          @click="pickReason(r)"
        >{{ r }}</button>
      </div>
      <div v-else-if="loading" class="ret-loading">{{ t('app.loading') }}</div>

      <label class="field">
        <span class="field-label">{{ t('returns.other_reason') }}</span>
        <input class="input" v-model="freeText" :placeholder="t('returns.other_reason_ph')"
          @focus="picked = ''" @keyup.enter="confirm" />
      </label>

      <div class="ret-note">{{ t('returns.note') }}</div>

      <div class="ret-actions">
        <button class="btn" @click="emit('close')">{{ t('app.cancel') }}</button>
        <button class="btn btn-danger" :disabled="!reason" @click="confirm">
          {{ t('returns.start') }}
        </button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.ret-body { display: flex; flex-direction: column; gap: 14px; min-width: 320px; }
.ret-policy {
  display: flex; gap: 6px; align-items: center;
  padding: 8px 12px;
  background: var(--surface-2);
  border-radius: var(--r-md);
  font-size: 12.5px;
}
.ret-policy-label { color: var(--text-muted); }
.ret-reasons { display: flex; flex-wrap: wrap; gap: 8px; }
.ret-reason {
  padding: 9px 14px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  font-size: 13px;
  color: var(--text);
}
.ret-reason:hover { border-color: var(--danger); }
.ret-reason.active { background: var(--danger-soft); border-color: var(--danger); color: var(--danger); }
.ret-loading { font-size: 12px; color: var(--text-muted); }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; color: var(--text-muted); }
.ret-note { font-size: 11.5px; color: var(--text-muted); line-height: 1.5; }
.ret-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn-danger {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}
.btn-danger:disabled { opacity: 0.5; }
</style>
