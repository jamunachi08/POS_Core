<script setup>
// Manager PIN approval gate.
//
// Any flow that needs supervisor sign-off (void line, discount above
// threshold, price override, entering return mode) mounts this dialog
// with an `action` label. On success we emit `authorized` with the
// manager identity returned by the server; the caller then proceeds.
//
// Verification is entirely server-side (security/manager_pin.py):
// per-manager exponential lockout, per-IP rate limit, audit log. We
// never learn WHY a rejection happened — by design.
import { ref, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { api } from '../api/client'
import AppModal from './AppModal.vue'

const props = defineProps({
  // Human-readable action shown in the dialog and logged server-side,
  // e.g. 'Void Line', 'Discount', 'Price Override', 'Return'
  action: { type: String, required: true },
})
const emit = defineEmits(['close', 'authorized'])

const { t } = useI18n()
const store = usePOSStore()

const user = ref('')
const pin = ref('')
const busy = ref(false)
const error = ref('')
const userInput = ref(null)

onMounted(() => nextTick(() => userInput.value?.focus?.()))

async function submit() {
  error.value = ''
  if (!user.value.trim() || !pin.value.trim()) return
  busy.value = true
  try {
    const res = await api.verifyManagerPin({
      user: user.value.trim(),
      pin: pin.value.trim(),
      action_type: props.action,
      terminal: store.terminal || null,
      outlet: store.boot?.outlet?.name || null,
    })
    if (res && res.authorized) {
      emit('authorized', { manager: res.manager, manager_name: res.manager_name })
      emit('close')
    } else {
      error.value = (res && res.message) || t('security.incorrect')
      pin.value = ''
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="t('security.approval_needed')" @close="emit('close')">
    <div class="pin-body">
      <div class="pin-action">{{ t('security.action_label') }}: <b>{{ action }}</b></div>

      <label class="field">
        <span class="field-label">{{ t('security.manager_user') }}</span>
        <input
          ref="userInput"
          class="input"
          v-model="user"
          type="text"
          autocomplete="username"
          :placeholder="t('security.manager_user_ph')"
          @keyup.enter="submit"
        />
      </label>

      <label class="field">
        <span class="field-label">{{ t('security.pin') }}</span>
        <input
          class="input pin-input tnum"
          v-model="pin"
          type="password"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="12"
          @keyup.enter="submit"
        />
      </label>

      <div v-if="error" class="pin-error">{{ error }}</div>

      <div class="pin-actions">
        <button class="btn" @click="emit('close')">{{ t('app.cancel') }}</button>
        <button class="btn btn-primary" :disabled="busy || !user || !pin" @click="submit">
          {{ busy ? t('security.verifying') : t('security.authorize') }}
        </button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.pin-body { display: flex; flex-direction: column; gap: 14px; min-width: 300px; }
.pin-action { font-size: 13px; color: var(--text-muted); }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; color: var(--text-muted); }
.pin-input { letter-spacing: 6px; font-size: 18px; text-align: center; }
.pin-error {
  padding: 8px 12px;
  border-radius: var(--r-md);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}
.pin-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
