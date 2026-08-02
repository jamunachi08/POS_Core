// Frappe API client. When `?mock=1` is in the URL, or when the global
// `frappe` object is missing (e.g. running `npm run dev` outside Frappe),
// we transparently fall back to the mock provider in ./mock.js.
//
// All callers see the same async signatures.

import { mock } from './mock'

const useMock = () => mock.isMockMode() || typeof window.frappe === 'undefined'
const csrf = () => (window.frappe && window.frappe.csrf_token) || ''

async function call(method, args = {}, { type = 'POST' } = {}) {
  const url = `/api/method/${method}`
  const options = {
    method: type,
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrf(),
      'X-Requested-With': 'XMLHttpRequest'
    },
    credentials: 'same-origin'
  }
  if (type === 'POST') options.body = JSON.stringify(args)
  const res = await fetch(url, options)
  if (!res.ok) {
    const txt = await res.text().catch(() => '')
    // Frappe packs the human message into JSON (_server_messages /
    // exception). Unpack it so boot cards and toasts show "Your user
    // has no read access to …" instead of a wall of escaped JSON.
    throw new Error(frappeErrorText(txt) || `${res.status} ${res.statusText}`)
  }
  const json = await res.json()
  return json.message
}

function frappeErrorText(raw) {
  try {
    const body = JSON.parse(raw)
    if (body._server_messages) {
      const msgs = JSON.parse(body._server_messages)
      const first = typeof msgs[0] === 'string' ? JSON.parse(msgs[0]) : msgs[0]
      if (first && first.message) return stripHtml(first.message)
    }
    if (body.exception) return String(body.exception).split(':').slice(1).join(':').trim() || body.exception
    if (body.message) return stripHtml(String(body.message))
  } catch { /* not JSON — fall through */ }
  return ''
}

function stripHtml(s) {
  return String(s).replace(/<[^>]*>/g, '').trim()
}

export const api = {

  posBoot(terminal) {
    if (useMock()) return mock.posBoot(terminal)
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.pos_boot', { terminal })
  },

  // ---- shift & cash management --------------------------------------------
  getShiftState(terminal) {
    if (useMock()) return Promise.resolve({ open: false })
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.get_shift_state', { terminal })
  },
  openShift(terminal, opening_cash, notes = null, for_user = null) {
    if (useMock()) return Promise.resolve({ open: true, summary: { shift: 'MOCK-SH', opening_cash, expected_cash: opening_cash, by_mop: [], movements: {} } })
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.open_shift', { terminal, opening_cash, notes, for_user })
  },
  recordCashMovement(shift, movement_type, amount, remarks = null) {
    if (useMock()) return Promise.resolve({ summary: {} })
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.record_cash_movement', { shift, movement_type, amount, remarks })
  },
  xReport(shift) {
    if (useMock()) return Promise.resolve({})
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.x_report', { shift })
  },
  closeShift(shift, counted_cash, notes = null, handover_to = null) {
    if (useMock()) return Promise.resolve({ variance: 0 })
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.close_shift', { shift, counted_cash, notes, handover_to })
  },
  dayClose(terminal, posting_date = null) {
    if (useMock()) return Promise.resolve({})
    return call('alphax_pos_suite.alphax_pos_suite.pos.shift_api.day_close', { terminal, posting_date })
  },

  // ---- security: manager PIN --------------------------------------------
  // Two-step: manager identifies with their User (email), then PIN.
  // Server enforces lockout + audit logging; we just pass context.
  verifyManagerPin({ user, pin, action_type = 'Verify Only', terminal = null, outlet = null }) {
    if (useMock()) return Promise.resolve({ authorized: true, manager: user, manager_name: 'Mock Manager' })
    return call('alphax_pos_suite.alphax_pos_suite.security.manager_pin.verify_manager_pin', {
      user, pin, action_type, terminal, outlet
    })
  },

  // ---- config panel ------------------------------------------------------
  getCashierSettings() {
    if (useMock()) return Promise.resolve({ settings: {}, can_edit: false, editable_fields: [] })
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.get_cashier_settings')
  },

  updateCashierSettings(changes) {
    if (useMock()) return Promise.resolve({ applied: changes, settings: changes })
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.update_cashier_settings', {
      changes: JSON.stringify(changes)
    })
  },

  invalidateBootCache(terminal = null) {
    if (useMock()) return Promise.resolve({ ok: true })
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.invalidate_boot_cache', { terminal })
  },

  // ---- returns ------------------------------------------------------------
  listReturnReasons() {
    if (useMock()) return Promise.resolve([{ name: 'Damaged' }, { name: 'Wrong item' }])
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.list_return_reasons')
  },

  // Resolve a scanned/typed barcode (product, scale, or PLU) into a
  // cashier-ready line. Falls back to the mock provider in dev.
  scanBarcode(code, { pos_profile = null, outlet = null } = {}) {
    if (useMock()) return mock.scanBarcode ? mock.scanBarcode(code) : Promise.resolve({ found: false, code })
    return call('alphax_pos_suite.alphax_pos_suite.barcode.api.scan_barcode', {
      code, pos_profile, outlet
    })
  },

  listInvoiceHistory(args) {
    if (useMock()) return mock.listInvoiceHistory()
    return call('alphax_pos_suite.alphax_pos_suite.pos.history_api.list_invoices', args)
  },

  getInvoiceReceipt(name) {
    if (useMock()) return mock.getInvoiceReceipt(name)
    return call('alphax_pos_suite.alphax_pos_suite.pos.history_api.get_invoice_receipt', { name })
  },

  pushQueuedInvoice(doc) {
    if (useMock()) return Promise.resolve({ ok: true, name: 'SINV-MOCK-0001' })
    return call('alphax_pos_suite.alphax_pos_suite.pos.queue_api.push_queued_invoice', { doc })
  },

  listTerminals() {
    if (useMock()) return mock.listTerminals()
    // Dedicated endpoint (v15.7.6): raw frappe.client.get_list returned
    // [] on permission gaps, indistinguishable from "no terminals".
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.list_terminals')
  },

  listItems({ item_groups = null, limit = 200 } = {}) {
    if (useMock()) return mock.listItems()
    const filters = { disabled: 0, is_sales_item: 1, has_variants: 0 }
    if (item_groups && item_groups.length) {
      filters.item_group = ['in', item_groups]
    }
    return call('frappe.client.get_list', {
      doctype: 'Item',
      fields: [
        'name', 'item_code', 'item_name', 'item_group', 'standard_rate',
        'image', 'description', 'stock_uom',
        'alphax_is_weighing_item', 'alphax_scale_item_code'
      ],
      filters,
      limit_page_length: limit,
      order_by: 'item_name asc'
    })
  },

  listItemGroups() {
    if (useMock()) return mock.listItemGroups()
    return call('frappe.client.get_list', {
      doctype: 'Item Group',
      fields: ['name', 'parent_item_group', 'lft', 'rgt'],
      limit_page_length: 0
    })
  },

  listFloors(outlet) {
    if (useMock()) return mock.listFloors(outlet)
    return call('alphax_pos_suite.alphax_pos_suite.floor.api.list_floors', { outlet })
  },

  getFloorLayout(floor) {
    if (useMock()) return mock.getFloorLayout(floor)
    return call('alphax_pos_suite.alphax_pos_suite.floor.api.get_floor_layout', { floor })
  },

  searchCustomers(query) {
    if (useMock()) return mock.searchCustomers(query)
    return call('frappe.client.get_list', {
      doctype: 'Customer',
      fields: ['name', 'customer_name', 'mobile_no'],
      filters: query ? [['customer_name', 'like', `%${query}%`]] : [],
      limit_page_length: 20
    })
  },

  quotePoints(program, items, opts = {}) {
    if (useMock()) return mock.quotePoints(program, items, opts)
    return call('alphax_pos_suite.alphax_pos_suite.loyalty.engine.quote_points', {
      program,
      items: JSON.stringify(items),
      net_total: opts.net_total || 0,
      tax_total: opts.tax_total || 0,
      service_charge: opts.service_charge || 0,
      tips: opts.tips || 0,
      domain: opts.domain || null,
      customer: opts.customer || null
    })
  },

  lookupWallet(params) {
    if (useMock()) return mock.lookupWallet(params)
    return call('alphax_pos_suite.alphax_pos_suite.loyalty.engine.lookup_wallet', params)
  },

  quoteRedemption(program, customer, points, bill_total) {
    if (useMock()) return mock.quoteRedemption(program, customer, points, bill_total)
    return call('alphax_pos_suite.alphax_pos_suite.loyalty.engine.quote_redemption', {
      program, customer, points, bill_total
    })
  },

  insertDoc(doc) {
    if (useMock()) return mock.insertDoc(doc)
    return call('frappe.client.insert', { doc: JSON.stringify(doc) })
  },

  submitDoc(doctype, name) {
    if (useMock()) return mock.submitDoc(doctype, name)
    return call('frappe.client.submit', { doc: JSON.stringify({ doctype, name }) })
  },
}
