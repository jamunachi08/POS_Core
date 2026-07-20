// Tiny Promise wrapper around IndexedDB. Keeps the bundle dep-free.
//
// We use a single store "queue" with auto-incrementing keys.

const DB_NAME = 'alphax-pos'
const DB_VERSION = 1
const STORE = 'queue'

let _db = null

function open() {
  if (_db) return Promise.resolve(_db)
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      if (!db.objectStoreNames.contains(STORE)) {
        const os = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true })
        os.createIndex('status', 'status', { unique: false })
        os.createIndex('client_uuid', 'client_uuid', { unique: true })
        os.createIndex('created_at', 'created_at', { unique: false })
      }
    }
    req.onsuccess = (e) => { _db = e.target.result; resolve(_db) }
    req.onerror   = (e) => reject(e.target.error)
  })
}

function tx(mode = 'readwrite') {
  return open().then(db => {
    const t = db.transaction(STORE, mode)
    return [t.objectStore(STORE), t]
  })
}

export const queueDB = {

  async put(record) {
    const [store, t] = await tx('readwrite')
    return new Promise((resolve, reject) => {
      const r = store.put({ ...record, updated_at: new Date().toISOString() })
      r.onsuccess = () => resolve(r.result)
      r.onerror   = () => reject(r.error)
    })
  },

  async add(record) {
    const [store, t] = await tx('readwrite')
    const row = {
      ...record,
      status: record.status || 'pending',
      created_at: record.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
      attempts: 0,
      last_error: null,
    }
    return new Promise((resolve, reject) => {
      const r = store.add(row)
      r.onsuccess = () => resolve({ ...row, id: r.result })
      r.onerror   = () => reject(r.error)
    })
  },

  async getByUuid(client_uuid) {
    const [store] = await tx('readonly')
    return new Promise((resolve, reject) => {
      const idx = store.index('client_uuid')
      const r = idx.get(client_uuid)
      r.onsuccess = () => resolve(r.result || null)
      r.onerror   = () => reject(r.error)
    })
  },

  async pending() {
    const [store] = await tx('readonly')
    return new Promise((resolve, reject) => {
      const idx = store.index('status')
      const out = []
      const r = idx.openCursor(IDBKeyRange.only('pending'))
      r.onsuccess = (e) => {
        const c = e.target.result
        if (c) { out.push(c.value); c.continue() }
        else resolve(out)
      }
      r.onerror = () => reject(r.error)
    })
  },

  async all() {
    const [store] = await tx('readonly')
    return new Promise((resolve, reject) => {
      const out = []
      const r = store.openCursor()
      r.onsuccess = (e) => {
        const c = e.target.result
        if (c) { out.push(c.value); c.continue() }
        else resolve(out)
      }
      r.onerror = () => reject(r.error)
    })
  },

  async update(id, patch) {
    const [store] = await tx('readwrite')
    return new Promise((resolve, reject) => {
      const g = store.get(id)
      g.onsuccess = () => {
        const row = g.result
        if (!row) return resolve(null)
        const merged = { ...row, ...patch, updated_at: new Date().toISOString() }
        const u = store.put(merged)
        u.onsuccess = () => resolve(merged)
        u.onerror = () => reject(u.error)
      }
      g.onerror = () => reject(g.error)
    })
  },

  async remove(id) {
    const [store] = await tx('readwrite')
    return new Promise((resolve, reject) => {
      const r = store.delete(id)
      r.onsuccess = () => resolve(true)
      r.onerror   = () => reject(r.error)
    })
  },

  async counts() {
    const rows = await this.all()
    return {
      total:   rows.length,
      pending: rows.filter(r => r.status === 'pending').length,
      synced:  rows.filter(r => r.status === 'synced').length,
      failed:  rows.filter(r => r.status === 'failed').length,
    }
  }
}
