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
    throw new Error(`${res.status} ${res.statusText}: ${txt.slice(0, 300)}`)
  }
  const json = await res.json()
  return json.message
}

export const api = {

  posBoot(terminal) {
    if (useMock()) return mock.posBoot(terminal)
    return call('alphax_pos_suite.alphax_pos_suite.boot.api.pos_boot', { terminal })
  },

  listTerminals() {
    if (useMock()) return mock.listTerminals()
    return call('frappe.client.get_list', {
      doctype: 'AlphaX POS Terminal',
      fields: ['name'],
      limit_page_length: 50
    })
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
