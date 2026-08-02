<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSyncStore } from '../stores/sync'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const { t, locale } = useI18n()
const sync = useSyncStore()
const { fmt } = useMoney()
const emit = defineEmits(['close'])

const rows = ref([])
const filter = ref('all')

async function refresh() {
  rows.value = (await sync.listAll()).sort((a, b) =>
    (b.created_at || '').localeCompare(a.created_at || ''))
  await sync.refreshCounts()
}

const filtered = computed(() => {
  if (filter.value === 'all') return rows.value
  return rows.value.filter(r => r.status === filter.value)
})

onMounted(refresh)

async function syncNow() {
  await sync.drain()
  await refresh()
}
async function retryAll() {
  await sync.retryFailed()
  await refresh()
}
async function discard(row) {
  if (!confirm(t('sync.confirm_discard'))) return
  await sync.dropRow(row.id)
  await refresh()
}

function fmtTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString(locale.value, {
    hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric'
  })
}
function rowTotal(r) {
  const items = r.payload?.items || []
  return items.reduce((s, l) => s + (l.qty || 0) * (l.rate || 0), 0)
}
</script>

<template>
  <AppModal :title="t('sync.queue_inspector')" size="lg" @close="emit('close')">

    <div class="head-row">
      <div class="status-pills">
        <span class="status-pill" :class="{ active: sync.online }">
          <span class="dot"></span>
          {{ sync.online ? t('sync.online') : t('sync.offline') }}
        </span>
        <span class="counter pending" v-if="sync.counts.pending">
          {{ sync.counts.pending }} {{ t('sync.queued') }}
        </span>
        <span class="counter failed" v-if="sync.counts.failed">
          {{ sync.counts.failed }} {{ t('sync.failed') }}
        </span>
      </div>
      <div class="actions">
        <button class="btn" :disabled="!sync.online || sync.syncing" @click="syncNow">
          {{ sync.syncing ? t('sync.syncing') : t('sync.sync_now') }}
        </button>
        <button class="btn" :disabled="!sync.online || sync.counts.failed === 0" @click="retryAll">
          {{ t('sync.retry_all') }}
        </button>
      </div>
    </div>

    <div class="filter-row">
      <button class="filter" :class="{ active: filter === 'all' }" @click="filter = 'all'">
        {{ t('app.search') === 'Search' ? 'All' : 'الكل' }}
      </button>
      <button class="filter" :class="{ active: filter === 'pending' }" @click="filter = 'pending'">
        {{ t('sync.queued') }}
      </button>
      <button class="filter" :class="{ active: filter === 'synced' }" @click="filter = 'synced'">
        {{ t('sync.synced') }}
      </button>
      <button class="filter" :class="{ active: filter === 'failed' }" @click="filter = 'failed'">
        {{ t('sync.failed') }}
      </button>
    </div>

    <div v-if="filtered.length === 0" class="empty">
      {{ t('sync.no_queued_items') }}
    </div>

    <div v-else class="rows">
      <div v-for="row in filtered" :key="row.id" class="row" :class="`r-${row.status}`">
        <div class="row-main">
          <div class="row-top">
            <span class="status-tag" :class="`tag-${row.status}`">{{ t(`sync.${row.status}`) }}</span>
            <span class="amount tnum">{{ fmt(rowTotal(row)) }}</span>
          </div>
          <div class="row-meta">
            <span>{{ row.payload?.customer || 'Walk-in' }}</span>
            <span>·</span>
            <span>{{ (row.payload?.items || []).length }} items</span>
            <span>·</span>
            <span>{{ row.status === 'synced' ? t('sync.synced_at', { time: fmtTime(row.synced_at || row.updated_at) })
                                              : t('sync.queued_at', { time: fmtTime(row.created_at) }) }}</span>
            <span v-if="row.attempts > 1">·</span>
            <span v-if="row.attempts > 1">{{ t('sync.attempts', row.attempts, { n: row.attempts }) }}</span>
          </div>
          <div v-if="row.last_error" class="row-error">
            {{ t('sync.last_error') }}: {{ row.last_error }}
          </div>
          <div v-if="row.server_name" class="row-server">→ {{ row.server_name }}</div>
        </div>
        <div class="row-actions">
          <button v-if="row.status !== 'synced'" class="btn btn-ghost x"
            @click="discard(row)" :title="t('sync.discard')">×</button>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn btn-primary" @click="emit('close')">{{ t('app.close') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-block-end: 14px;
  gap: 12px;
}
.status-pills { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: var(--r-pill);
  background: var(--surface-2); color: var(--text-muted);
  font-size: 11px; font-weight: 500;
}
.status-pill.active { background: var(--accent-soft); color: var(--accent); }
.status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-dim); }
.status-pill.active .dot { background: var(--accent); }

.counter {
  padding: 4px 10px; border-radius: var(--r-pill);
  font-size: 11px; font-weight: 500;
}
.counter.pending { background: var(--warn-soft); color: var(--warn); }
.counter.failed  { background: var(--danger-soft); color: var(--danger); }

.actions { display: flex; gap: 6px; }

.filter-row {
  display: flex; gap: 4px;
  margin-block-end: 10px;
  padding-block-end: 8px;
  border-block-end: 1px solid var(--border);
}
.filter {
  padding: 5px 12px;
  border: 1px solid var(--border);
  background: transparent;
  border-radius: var(--r-pill);
  font-size: 12px;
  color: var(--text-muted);
}
.filter.active {
  background: var(--text);
  color: #fff;
  border-color: var(--text);
}

.rows { display: flex; flex-direction: column; gap: 6px; max-height: 50vh; overflow-y: auto; }
.row {
  display: flex;
  background: var(--surface-2);
  border-radius: var(--r-md);
  padding: 10px 12px;
  gap: 10px;
}
.row.r-failed { background: var(--danger-soft); }
.row.r-synced { opacity: 0.7; }

.row-main { flex: 1; min-width: 0; }
.row-top {
  display: flex; align-items: center; gap: 8px;
  margin-block-end: 4px;
}
.status-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--r-sm);
  font-weight: 500;
}
.tag-pending { background: var(--warn-soft); color: var(--warn); }
.tag-synced  { background: var(--accent-soft); color: var(--accent); }
.tag-failed  { background: var(--danger); color: #fff; }
.amount { margin-inline-start: auto; font-size: 13px; font-weight: 600; }

.row-meta {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.row-error {
  margin-block-start: 6px;
  font-size: 11px;
  color: var(--danger);
  font-family: var(--font-mono);
  word-break: break-word;
}
.row-server { font-size: 11px; color: var(--text-muted); margin-block-start: 4px; }

.row-actions { display: flex; align-items: flex-start; }
.x { width: 28px; height: 28px; border-radius: 50%; padding: 0; font-size: 16px; }

.empty {
  padding: 30px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
}
</style>
