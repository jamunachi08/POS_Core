// Sync store. Handles offline queueing of submitted sales and replays them
// when the network returns. Server-side idempotency (the `client_uuid`
// uniqueness check) guarantees safe retries.

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { queueDB } from '../api/queueDB'

function isMethodMissing(e) {
  const m = (e && e.message || '').toLowerCase()
  return m.includes('404') || m.includes('not found') || m.includes('does not exist')
}

// A queue that retries everything forever is not resilient, it is loud.
// Twenty-eight attempts against "Company has no Default Receivable
// Account" produced twenty-eight identical failures and no information;
// the same twenty-eight against a dropped wifi would have been correct.
// The difference is whether a human has to do something first.
const BLOCKING_PATTERNS = [
  'has no default receivable account',
  'does not exist on this site',
  'no fiscal year',
  'is not a valid',
  'mandatory',
  'is required',
  'please set',
  'not permitted',
  'permissionerror',
  'validationerror',
  'linkvalidationerror',
  'mandatoryerror',
  'duplicateentryerror',
  'cannot be negative',
  'not allowed to',
  'must be one of',
  'has no company',
  'closed accounting period',
  'stock not available',
  'negative stock',
]

const TRANSIENT_PATTERNS = [
  'failed to fetch', 'networkerror', 'network error', 'load failed',
  'timeout', 'timed out', 'aborted', 'econnreset', 'econnrefused',
  '502', '503', '504', 'bad gateway', 'service unavailable',
  'gateway time-out', 'deadlock', 'lock wait', 'document has been modified',
  'too many requests', '429', 'site is being updated', 'maintenance mode',
]

/** 'duplicate' | 'blocked' | 'transient' */
function classify(message) {
  const m = String(message || '').toLowerCase()
  if (m.includes('duplicate')) return 'duplicate'
  // Transient wins over blocking: a 503 whose HTML body happens to
  // contain the word "mandatory" is still a 503.
  if (TRANSIENT_PATTERNS.some(p => m.includes(p))) return 'transient'
  if (BLOCKING_PATTERNS.some(p => m.includes(p))) return 'blocked'
  return 'transient'
}

// Exponential backoff, capped. 5s, 10s, 20s … 2 min.
function backoffMs(attempts) {
  return Math.min(120000, 5000 * Math.pow(2, Math.max(0, (attempts || 1) - 1)))
}

// A blocked row is re-tried on a slow clock rather than never: the whole
// point is that the moment somebody sets the receivable account, the
// queue clears itself with nobody tapping anything.
const BLOCKED_RECHECK_MS = 180000

export const useSyncStore = defineStore('sync', () => {

  // Default to online when the runtime does not say otherwise. An
  // undefined navigator.onLine must not read as "offline", or the queue
  // sits still forever on a platform that simply does not report it.
  const online = ref(typeof navigator === 'undefined' || navigator.onLine !== false)
  const syncing = ref(false)
  const counts = ref({ total: 0, pending: 0, synced: 0, failed: 0 })
  const lastError = ref(null)
  // The one message worth putting in front of the cashier: something is
  // wrong that retrying cannot fix.
  const blockedReason = ref(null)
  const blockedCount = ref(0)
  const lastSyncAt = ref(null)

  // ---- connectivity ----------------------------------------------------
  // "Even if the system disconnects and connects, it should sync
  // automatically." The `online` event alone does not deliver that: a
  // laptop lid closed for an hour fires nothing, a tab in the background
  // is throttled to near-zero timers, and captive-portal wifi reports
  // online while nothing routes. So: listen to everything that means
  // "we might be back", and let drain() be cheap and idempotent.
  let bound = false
  function bindConnectivity() {
    if (typeof window === 'undefined' || bound) return
    bound = true

    const wake = (why) => {
      if (typeof navigator !== 'undefined') online.value = navigator.onLine !== false
      if (online.value) drain(why).catch(() => {})
    }

    window.addEventListener('online', () => { online.value = true; wake('online-event') })
    window.addEventListener('offline', () => { online.value = false })
    // Tab brought back to the front — the usual shape of "the cashier
    // came back to the till after the router was rebooted".
    window.addEventListener('focus', () => wake('focus'))
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) wake('visible')
      })
    }
    // Machine resumed from sleep: a timer that should have fired every
    // 15s and instead jumped an hour is the tell.
    let lastTick = Date.now()
    setInterval(() => {
      const now = Date.now()
      if (now - lastTick > 90000) wake('resume')
      lastTick = now
    }, 15000)
    // Network type changed (wifi -> LTE on a tablet).
    const conn = navigator && (navigator.connection || navigator.mozConnection)
    if (conn && conn.addEventListener) {
      conn.addEventListener('change', () => wake('connection-change'))
    }
  }

  // ---- queue operations ------------------------------------------------

  async function refreshCounts() {
    counts.value = await queueDB.counts()
  }

  /** Queue a complete sale for later submission.
   *  invoice = the doc payload that pos.js builds.
   *  client_uuid identifies it so idempotent retries are safe. */
  async function enqueueSale(invoice, client_uuid) {
    await queueDB.add({
      kind: 'sales_invoice',
      client_uuid,
      payload: invoice,
      status: 'pending',
    })
    await refreshCounts()
  }

  /** Try to push everything that is due.
   *
   *  Safe to call from anywhere, as often as anything likes: it returns
   *  immediately if a drain is already running, skips rows whose backoff
   *  has not elapsed, and re-checks blocked rows on a slow clock so a
   *  fixed configuration clears the queue without anyone pressing retry.
   */
  async function drain(reason = 'manual') {
    if (syncing.value) return
    if (!online.value) return
    syncing.value = true
    lastError.value = null
    try {
      const now = Date.now()
      const rows = await queueDB.pending()
      let blocked = 0
      let blockedMsg = null

      for (const row of rows) {
        // Blocked: something a human has to fix. Re-attempt occasionally
        // rather than never — the fix usually happens on another screen
        // and nobody comes back to tell the till.
        if (row.blocked_reason) {
          const due = (row.blocked_checked_at || 0) + BLOCKED_RECHECK_MS
          if (now < due && reason !== 'retry') {
            blocked++
            blockedMsg = blockedMsg || row.blocked_reason
            continue
          }
        } else if (row.next_attempt_at && now < row.next_attempt_at && reason !== 'retry') {
          continue   // still inside its backoff window
        }

        try {
          await pushOne(row)
        } catch (e) {
          const msg = e.message || String(e)
          if (classify(msg) === 'blocked') {
            blocked++
            blockedMsg = blockedMsg || msg
          } else {
            lastError.value = msg
          }
          // One bad row must never hold up the rest of the queue.
        }
      }

      blockedCount.value = blocked
      blockedReason.value = blocked ? blockedMsg : null
      lastSyncAt.value = new Date().toISOString()
    } finally {
      syncing.value = false
      await refreshCounts()
    }
  }


  async function pushOne(row) {
    // Tag the doc with our client_uuid so the server can dedupe.
    const doc = { ...row.payload, alphax_client_uuid: row.client_uuid }
    try {
      let serverName
      if (doc.doctype === 'Sales Invoice') {
        // v15.7.10: one server call does insert + submit + dedupe +
        // preflight, and logs full tracebacks to Error Log — the old
        // insert/submit pair returned bare core exceptions ("cannot
        // unpack non-iterable NoneType object") with no way to
        // diagnose from the till. Falls back for older servers.
        try {
          const res = await api.pushQueuedInvoice(doc)
          serverName = res && res.name
        } catch (e) {
          if (!isMethodMissing(e)) throw e
          const inserted = await api.insertDoc(doc)
          serverName = inserted.name
          await api.submitDoc('Sales Invoice', inserted.name)
        }
      } else {
        const inserted = await api.insertDoc(doc)
        serverName = inserted.name
      }
      await queueDB.update(row.id, {
        status: 'synced',
        attempts: (row.attempts || 0) + 1,
        server_name: serverName,
        synced_at: new Date().toISOString(),
        last_error: null,
        blocked_reason: null,
        next_attempt_at: null,
      })
    } catch (e) {
      const msg = e.message || String(e)
      const attempts = (row.attempts || 0) + 1
      const kind = classify(msg)

      if (kind === 'duplicate') {
        // The server already has it; the uuid check did its job.
        await queueDB.update(row.id, {
          status: 'synced',
          last_error: 'already submitted (duplicate uuid)',
          blocked_reason: null,
          attempts,
        })
        return
      }

      if (kind === 'blocked') {
        // Retrying changes nothing until a person changes something.
        // Keep the row pending (never lose a sale), stop the hammering,
        // and record when we last looked so the slow re-check works.
        await queueDB.update(row.id, {
          attempts,
          last_error: msg,
          blocked_reason: msg,
          blocked_checked_at: Date.now(),
          next_attempt_at: Date.now() + BLOCKED_RECHECK_MS,
        })
        throw e
      }

      // Transient: back off, and clear any stale blocked flag — the
      // configuration may well have been fixed since.
      await queueDB.update(row.id, {
        attempts,
        last_error: msg,
        blocked_reason: null,
        next_attempt_at: Date.now() + backoffMs(attempts),
      })
      throw e
    }
  }

  /** Manual retry: "I have fixed it, try now."
   *  Clears every hold — failed status, blocked flag, backoff window —
   *  and drains immediately, ignoring timers. */
  async function retryFailed() {
    const rows = await queueDB.all()
    for (const r of rows) {
      if (r.status === 'synced') continue
      await queueDB.update(r.id, {
        status: 'pending',
        last_error: null,
        blocked_reason: null,
        blocked_checked_at: null,
        next_attempt_at: null,
      })
    }
    blockedReason.value = null
    blockedCount.value = 0
    await drain('retry')
  }

  /** Discard a row (e.g. cashier confirmed it was a duplicate test). */
  async function dropRow(id) {
    await queueDB.remove(id)
    await refreshCounts()
  }

  /** All rows for the queue inspector UI. */
  async function listAll() {
    return queueDB.all()
  }

  // ---- periodic drain --------------------------------------------------
  let timer = null
  function startBackgroundSync(intervalMs = 15000) {
    stopBackgroundSync()
    timer = setInterval(() => { drain('interval').catch(() => {}) }, intervalMs)
    // Do not wait a full interval to try the first time: a till that has
    // just booted with a queue should clear it now.
    drain('startup').catch(() => {})
  }
  function stopBackgroundSync() {
    if (timer) { clearInterval(timer); timer = null }
  }

  return {
    online, syncing, counts, lastError,
    blockedReason, blockedCount, lastSyncAt, classify,
    bindConnectivity, refreshCounts,
    enqueueSale, drain, pushOne, retryFailed, dropRow, listAll,
    startBackgroundSync, stopBackgroundSync,
  }
})
