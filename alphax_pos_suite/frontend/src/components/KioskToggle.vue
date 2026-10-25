<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKioskStore } from '../stores/kiosk'
import { haptics } from '../composables/haptics'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const kiosk = useKioskStore()

const showSetup = ref(false)
const newPin = ref('')
const exitPin = ref('')
const pinError = ref('')

function openToggle() {
  haptics.tap()
  if (!kiosk.on) {
    if (!kiosk.hasPin) {
      // First time — ask user to set a PIN before enabling.
      newPin.value = ''
      showSetup.value = true
      return
    }
    kiosk.enable()
  } else {
    kiosk.requestExit()
    exitPin.value = ''
    pinError.value = ''
  }
}

async function applyPinAndEnable() {
  const v = (newPin.value || '').replace(/\D/g, '')
  if (v.length < 4) {
    pinError.value = t('kiosk.set_pin')
    return
  }
  kiosk.setPin(v)
  showSetup.value = false
  await kiosk.enable()
}

async function tryExit() {
  const ok = await kiosk.tryDisable(exitPin.value)
  if (!ok) {
    pinError.value = t('kiosk.wrong_pin')
    haptics.error()
  } else {
    haptics.success()
  }
}

function skipPin() {
  // Allow opting out — write a sticky note in the UI but don't block.
  kiosk.setPin('')
  showSetup.value = false
  kiosk.enable()
}
</script>

<template>
  <button class="kiosk-btn" :class="{ on: kiosk.on }" @click="openToggle"
    :title="kiosk.on ? t('kiosk.disable') : t('kiosk.enable')">
    <span class="ic">{{ kiosk.on ? '⛶' : '⛶' }}</span>
    <span class="lbl">{{ kiosk.on ? t('kiosk.disable') : t('kiosk.enable') }}</span>
  </button>

  <!-- First-time PIN setup -->
  <AppModal v-if="showSetup" :title="t('kiosk.set_pin')" size="sm" @close="showSetup = false">
    <input class="input pin-input tnum" v-model="newPin" inputmode="numeric"
      maxlength="6" autofocus :placeholder="'••••'" />
    <div v-if="pinError" class="pin-error">{{ pinError }}</div>
    <div class="muted no-pin-warn">{{ t('kiosk.no_pin_warning') }}</div>
    <template #footer>
      <button class="btn" @click="skipPin">{{ t('app.cancel') }}</button>
      <button class="btn btn-primary" @click="applyPinAndEnable">{{ t('app.confirm') }}</button>
    </template>
  </AppModal>

  <!-- Exit PIN prompt -->
  <AppModal v-if="kiosk.showExitPrompt" :title="t('kiosk.enter_pin')" size="sm"
    @close="kiosk.cancelExit">
    <input class="input pin-input tnum" v-model="exitPin" inputmode="numeric"
      maxlength="6" autofocus type="password" :placeholder="'••••'"
      @keydown.enter="tryExit" />
    <div v-if="pinError" class="pin-error">{{ pinError }}</div>
    <template #footer>
      <button class="btn" @click="kiosk.cancelExit">{{ t('app.cancel') }}</button>
      <button class="btn btn-primary" @click="tryExit">{{ t('kiosk.disable') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.kiosk-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  text-align: start;
}
.kiosk-btn:hover { background: var(--surface); border-color: var(--accent); }
.kiosk-btn.on { background: var(--warn-soft); border-color: var(--warn); color: var(--warn); }
.kiosk-btn .ic { font-size: 14px; }
.kiosk-btn .lbl { flex: 1; }

.pin-input {
  font-size: 28px;
  text-align: center;
  letter-spacing: 8px;
  font-weight: 600;
  padding: 16px;
}
.pin-error {
  margin-block-start: 8px;
  padding: 8px 12px;
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: var(--r-md);
  font-size: 12px;
  text-align: center;
}
.no-pin-warn {
  margin-block-start: 10px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}
.muted { color: var(--text-muted); }
</style>
