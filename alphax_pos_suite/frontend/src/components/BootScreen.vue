<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { api } from '../api/client'
import LocaleSwitch from './LocaleSwitch.vue'

const { t } = useI18n()
const store = usePOSStore()
const terminals = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try { terminals.value = await api.listTerminals() || [] }
  catch { terminals.value = [] }
  loading.value = false
})

function pick(name) {
  store.changeTerminal(name)
}
</script>

<template>
  <div class="boot-screen">
    <div class="boot-top-right"><LocaleSwitch /></div>
    <div class="boot-card">
      <div class="boot-mark">α</div>
      <div class="boot-title">{{ t('app.name') }}</div>

      <div v-if="store.bootLoading" class="boot-spinner">
        <div class="spinner"></div>
        <div class="spinner-label">{{ t('app.loading') }}</div>
      </div>

      <div v-else-if="store.bootError" class="boot-error">
        <div class="error-title">{{ t('errors.boot_failed') }}</div>
        <div class="error-detail">{{ store.bootError }}</div>
        <button class="btn btn-primary" @click="store.loadBoot">{{ t('app.retry') }}</button>
      </div>

      <div v-else class="terminal-picker">
        <div class="picker-label">{{ t('app.pick_terminal') }}</div>
        <div v-if="loading" class="muted">…</div>
        <div v-else-if="terminals.length === 0" class="muted">No terminals configured</div>
        <div v-else class="terminal-list">
          <button
            v-for="t in terminals"
            :key="t.name"
            class="terminal"
            @click="pick(t.name)"
          >
            <div class="t-mark">⌥</div>
            <div class="t-name">{{ t.name }}</div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.boot-screen {
  position: fixed;
  inset: 0;
  background: linear-gradient(135deg, var(--bg) 0%, var(--surface-2) 100%);
  display: grid;
  place-items: center;
  padding: 20px;
}
.boot-top-right {
  position: absolute;
  inset-block-start: 16px;
  inset-inline-end: 16px;
}
.boot-card {
  background: var(--surface);
  border-radius: var(--r-lg);
  padding: 40px 32px;
  width: 100%;
  max-width: 460px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.boot-mark {
  width: 56px; height: 56px;
  border-radius: var(--r-lg);
  background: var(--accent);
  color: #fff;
  display: grid; place-items: center;
  font-size: 28px;
  font-weight: 600;
  margin-block-end: 4px;
}
.boot-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin-block-end: 12px;
}

.boot-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 30px 0;
}
.spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.spinner-label { font-size: 13px; color: var(--text-muted); }
@keyframes spin { to { transform: rotate(360deg); } }

.boot-error {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 20px 0;
}
.error-title { font-size: 14px; font-weight: 600; color: var(--danger); }
.error-detail { font-size: 12px; color: var(--text-muted); text-align: center; max-width: 280px; }

.terminal-picker { width: 100%; }
.picker-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-block-end: 10px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.terminal-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.terminal {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  border: 1px solid transparent;
  border-radius: var(--r-md);
  text-align: start;
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
}
.terminal:hover { background: var(--surface); border-color: var(--accent); }
.t-mark {
  width: 32px; height: 32px;
  border-radius: var(--r-sm);
  background: var(--accent-soft);
  color: var(--accent);
  display: grid; place-items: center;
  font-size: 14px;
}
.muted { color: var(--text-dim); padding: 16px; text-align: center; font-size: 13px; }
</style>
