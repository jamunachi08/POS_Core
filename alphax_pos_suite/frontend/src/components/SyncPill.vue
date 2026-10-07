<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSyncStore } from '../stores/sync'

const { t } = useI18n()
const sync = useSyncStore()
defineEmits(['open-inspector'])

let refreshTimer = null

onMounted(() => {
  sync.bindConnectivity()
  sync.refreshCounts()
  sync.startBackgroundSync(15000)
  // refresh counts every 5s for the badge
  refreshTimer = setInterval(() => sync.refreshCounts(), 5000)
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  sync.stopBackgroundSync()
})

const state = computed(() => {
  if (!sync.online) return 'offline'
  if (sync.counts.failed > 0) return 'failed'
  if (sync.counts.pending > 0) return 'pending'
  return 'ok'
})

const label = computed(() => {
  if (state.value === 'offline') return t('sync.offline')
  if (state.value === 'failed')  return t('sync.n_failed', sync.counts.failed, { n: sync.counts.failed })
  if (state.value === 'pending') return t('sync.n_pending', sync.counts.pending, { n: sync.counts.pending })
  return t('sync.online')
})
</script>

<template>
  <button class="sync-pill" :class="`s-${state}`" @click="$emit('open-inspector')"
    :title="label">
    <span class="dot"></span>
    <span class="label">{{ label }}</span>
    <span v-if="sync.syncing" class="syncing">⟲</span>
  </button>
</template>

<style scoped>
.sync-pill {
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
.sync-pill:hover { background: var(--surface); border-color: var(--accent); }
.dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-dim); flex-shrink: 0;
}
.sync-pill.s-ok      { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.sync-pill.s-ok      .dot { background: var(--accent); }
.sync-pill.s-pending { background: var(--warn-soft); border-color: transparent; color: var(--warn); }
.sync-pill.s-pending .dot { background: var(--warn); animation: sync-pulse 1.5s ease-in-out infinite; }
.sync-pill.s-failed  { background: var(--danger-soft); border-color: transparent; color: var(--danger); }
.sync-pill.s-failed  .dot { background: var(--danger); animation: sync-pulse 1.5s ease-in-out infinite; }
.sync-pill.s-offline { background: var(--surface-2); }
.sync-pill.s-offline .dot { background: var(--text-dim); }
@keyframes sync-pulse { 50% { opacity: 0.4; } }
.label { flex: 1; }
.syncing {
  font-size: 12px;
  animation: spin 1s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
