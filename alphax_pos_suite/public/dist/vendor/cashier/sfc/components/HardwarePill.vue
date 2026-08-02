<script setup>
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHardwareStore } from '../stores/hardware'

const { t } = useI18n()
const hw = useHardwareStore()
defineEmits(['open-settings'])

onMounted(() => {
  // Try once on mount; don't block the UI on it.
  hw.ping().then((ok) => {
    if (ok) {
      hw.refreshDevices().then(() => hw.autodetectMapping())
    }
  })
})

const tooltip = computed(() => {
  if (!hw.online) return t('hardware.offline')
  const parts = []
  if (hw.printerReady) parts.push('🖨')
  if (hw.drawerReady)  parts.push('💰')
  if (hw.displayReady) parts.push('📺')
  if (hw.scaleReady)   parts.push('⚖')
  return t('hardware.online') + (parts.length ? ' · ' + parts.join(' ') : '')
})
</script>

<template>
  <button class="hw-pill" :class="{ on: hw.online }" @click="$emit('open-settings')" :title="tooltip">
    <span class="dot"></span>
    <span class="label">
      <span v-if="!hw.online">{{ t('hardware.offline') }}</span>
      <span v-else class="indicators">
        <span :class="{ ready: hw.printerReady }" :title="t('hardware.role_receipt_printer')">🖨</span>
        <span :class="{ ready: hw.drawerReady }"  :title="t('hardware.role_drawer')">💰</span>
        <span :class="{ ready: hw.displayReady }" :title="t('hardware.role_display')">📺</span>
        <span :class="{ ready: hw.scaleReady }"   :title="t('hardware.role_scale')">⚖</span>
      </span>
    </span>
  </button>
</template>

<style scoped>
.hw-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
  text-align: start;
  transition: background var(--t-fast), border-color var(--t-fast);
}
.hw-pill:hover { background: var(--surface); border-color: var(--accent); }
.hw-pill.on { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-dim); flex-shrink: 0;
}
.hw-pill.on .dot { background: var(--accent); animation: hw-pulse 2s ease-in-out infinite; }
@keyframes hw-pulse { 50% { opacity: 0.4; } }
.label { flex: 1; }
.indicators { display: inline-flex; gap: 6px; font-size: 12px; }
.indicators span {
  opacity: 0.25;
  filter: grayscale(1);
  transition: opacity var(--t-fast), filter var(--t-fast);
}
.indicators span.ready {
  opacity: 1;
  filter: none;
}
</style>
