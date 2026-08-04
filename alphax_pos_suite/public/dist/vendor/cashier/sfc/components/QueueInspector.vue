<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
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

// Countdown ticker for the backoff label. A static "retry in 42s" reads
// as stuck; a moving one reads as working.
const nowTs = ref(Date.now())
let tick = null
onMounted(() => { tick = setInterval(() => { nowTs.value = Date.now() }, 1000) })
onUnmounted(() => { if (tick) clearInterval(tick) })

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
  await sync.drain('manual')
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
        <button class="btn"
          :disabled="!sync.online || (sync.counts.failed === 0 && !sync.blockedCount)"
          @click="retryAll">
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

    <!-- One thing needs a person; retrying will not do it. Say so once,
         at the top, with the fix in the sentence. -->
    <div v-if="sync.blockedReason" class="blocked-banner">
      <div class="bb-title">{{ t('sync.blocked_title', sync.blockedCount, { n: sync.blockedCount }) }}</div>
      <div class="bb-msg">{{ sync.blockedReason }}</div>
      <div class="bb-foot">
        <button class="btn btn-primary sm" :disabled="sync.syncing" @click="retryAll">
          {{ t('sync.fixed_retry') }}
        </button>
        <span class="bb-hint">{{ t('sync.blocked_hint') }}</span>
      </div>
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
          <div v-if="row.blocked_reason" class="row-error blocked">
            <span class="tag-blocked">{{ t('sync.needs_fix') }}</span>
            {{ row.blocked_reason }}
          </div>
          <div v-else-if="row.last_error" class="row-error">
            {{ t('sync.last_error') }}: {{ row.last_error }}
            <span v-if="row.next_attempt_at" class="retry-in">
              · {{ t('sync.retry_in', { s: Math.max(0, Math.round((row.next_attempt_at - nowTs) / 1000)) }) }}
            </span>
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
.blocked-banner {
  border: 1px solid var(--warn, #C97A0A);
  background: color-mix(in srgb, var(--warn, #C97A0A) 9%, transparent);
  border-radius: var(--r-md, 10px);
  padding: 12px 14px;
  margin-block-end: 12px;
}
.bb-title { font-weight: 700; font-size: 13px; margin-block-end: 4px; }
.bb-msg { font-size: 12.5px; line-height: 1.5; }
.bb-foot { display: flex; align-items: center; gap: 10px; margin-block-start: 10px; flex-wrap: wrap; }
.bb-hint { font-size: 11.5px; color: var(--text-muted); }
.btn.sm { height: 30px; padding: 0 14px; font-size: 12px; }
.tag-blocked {
  display: inline-block; font-size: 10.5px; font-weight: 800; letter-spacing: .04em;
  text-transform: uppercase; padding: 1px 6px; border-radius: 5px; margin-inline-end: 6px;
  background: var(--warn, #C97A0A); color: #fff;
}
.row-error.blocked { color: var(--text); }
.retry-in { color: var(--text-muted); }

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
