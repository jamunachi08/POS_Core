// Sync store. Handles offline queueing of submitted sales and replays them
// when the network returns. Server-side idempotency (the `client_uuid`
// uniqueness check) guarantees safe retries.

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { queueDB } from '../api/queueDB'

export const useSyncStore = defineStore('sync', () => {

  const online = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)
  const syncing = ref(false)
  const counts = ref({ total: 0, pending: 0, synced: 0, failed: 0 })
  const lastError = ref(null)

  // ---- connectivity ----------------------------------------------------
  function bindConnectivity() {
    if (typeof window === 'undefined') return
    window.addEventListener('online',  () => { online.value = true;  drain() })
    window.addEventListener('offline', () => { online.value = false })
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

  /** Try to push every pending row to the server. */
  async function drain() {
    if (syncing.value) return
    if (!online.value) return
    syncing.value = true
    lastError.value = null
    try {
      const rows = await queueDB.pending()
      for (const row of rows) {
        try {
          await pushOne(row)
        } catch (e) {
          lastError.value = e.message || String(e)
          // don't break the loop on transient errors — try the next row
        }
      }
    } finally {
      syncing.value = false
      await refreshCounts()
    }
  }

  async function pushOne(row) {
    // Tag the doc with our client_uuid so the server can dedupe.
    const doc = { ...row.payload, alphax_client_uuid: row.client_uuid }
    try {
      const inserted = await api.insertDoc(doc)
      // Submit if it's a Sales Invoice
      if (doc.doctype === 'Sales Invoice') {
        try {
          await api.submitDoc('Sales Invoice', inserted.name)
        } catch (e) {
          // Insert succeeded but submit failed — record the inserted name.
          await queueDB.update(row.id, {
            status: 'failed',
            attempts: (row.attempts || 0) + 1,
            last_error: 'submit failed: ' + (e.message || String(e)),
            server_name: inserted.name,
          })
          return
        }
      }
      await queueDB.update(row.id, {
        status: 'synced',
        attempts: (row.attempts || 0) + 1,
        server_name: inserted.name,
        synced_at: new Date().toISOString(),
      })
    } catch (e) {
      const msg = e.message || String(e)
      // If the server rejects with a duplicate-uuid error, treat as already synced.
      if (msg.toLowerCase().includes('duplicate')) {
        await queueDB.update(row.id, {
          status: 'synced',
          last_error: 'already submitted (duplicate uuid)',
          attempts: (row.attempts || 0) + 1,
        })
        return
      }
      // Network or 5xx — keep pending, bump attempts, record error.
      await queueDB.update(row.id, {
        attempts: (row.attempts || 0) + 1,
        last_error: msg,
      })
      throw e
    }
  }

  /** Manual retry of failed rows. */
  async function retryFailed() {
    const rows = (await queueDB.all()).filter(r => r.status === 'failed')
    for (const r of rows) {
      await queueDB.update(r.id, { status: 'pending', last_error: null })
    }
    await drain()
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
    timer = setInterval(() => { drain().catch(() => {}) }, intervalMs)
  }
  function stopBackgroundSync() {
    if (timer) { clearInterval(timer); timer = null }
  }

  return {
    online, syncing, counts, lastError,
    bindConnectivity, refreshCounts,
    enqueueSale, drain, pushOne, retryFailed, dropRow, listAll,
    startBackgroundSync, stopBackgroundSync,
  }
})
