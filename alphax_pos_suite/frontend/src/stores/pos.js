import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { api } from '../api/client'

const uuid = () =>
  ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4))).toString(16))

const STORAGE_KEYS = {
  terminal: 'alphax_pos_terminal',
  held: 'alphax_held_orders',
}

export const usePOSStore = defineStore('pos', () => {

  // ---- terminal & boot --------------------------------------------------
  const terminal = ref(localStorage.getItem(STORAGE_KEYS.terminal) || null)
  const boot = ref(null)
  const bootError = ref(null)
  const bootLoading = ref(false)

  async function loadBoot() {
    if (!terminal.value) return
    bootLoading.value = true
    bootError.value = null
    try {
      boot.value = await api.posBoot(terminal.value)
      localStorage.setItem(STORAGE_KEYS.terminal, terminal.value)
      // pick a sensible starting domain
      activeDomain.value =
        boot.value?.outlet?.primary_domain ||
        boot.value?.domains?.[0]?.domain_code ||
        'Generic'
    } catch (e) {
      bootError.value = e.message || String(e)
    } finally {
      bootLoading.value = false
    }
  }

  function changeTerminal(name) {
    terminal.value = name
    boot.value = null
    cart.value = []
    customer.value = null
    wallet.value = null
    loadBoot()
  }

  // ---- domain switching --------------------------------------------------
  const activeDomain = ref(null)
  const activeDomainPack = computed(() =>
    (boot.value?.domains || []).find(d => d.domain_code === activeDomain.value) || null)

  // Feature flags = OR across all active domains, but the *active* domain's
  // own flags drive contextual UI (table picker only when the active domain
  // uses_floor_plan, batch picker when uses_batch_expiry, etc.)
  const features = computed(() => boot.value?.features || {})
  const activeFeatures = computed(() => {
    const p = activeDomainPack.value
    if (!p) return features.value
    const out = {}
    for (const k of Object.keys(features.value)) out[k] = !!p[k]
    return out
  })

  function switchDomain(code) {
    activeDomain.value = code
  }

  // ---- menu loading -----------------------------------------------------
  const menuItems = ref([])
  const menuLoading = ref(false)
  const itemGroups = ref([])
  const activeCategory = ref('')

  async function ensureItemGroups() {
    if (itemGroups.value.length) return
    try { itemGroups.value = await api.listItemGroups() || [] } catch (e) {}
  }

  async function loadMenu() {
    if (!boot.value) return
    menuLoading.value = true
    activeCategory.value = ''
    try {
      await ensureItemGroups()
      const pack = activeDomainPack.value
      let groupFilter = null
      if (pack?.default_item_group) {
        const target = itemGroups.value.find(g => g.name === pack.default_item_group)
        if (target) {
          groupFilter = itemGroups.value
            .filter(g => g.lft >= target.lft && g.rgt <= target.rgt)
            .map(g => g.name)
        }
      }
      menuItems.value = await api.listItems({ item_groups: groupFilter }) || []
    } catch (e) {
      menuItems.value = []
    } finally {
      menuLoading.value = false
    }
  }

  // Categories present in the loaded menu
  const categories = computed(() => {
    const seen = new Set()
    const out = []
    for (const it of menuItems.value) {
      if (it.item_group && !seen.has(it.item_group)) {
        seen.add(it.item_group)
        out.push(it.item_group)
      }
    }
    return out
  })

  const filteredMenu = computed(() => {
    let items = menuItems.value
    if (activeCategory.value) items = items.filter(i => i.item_group === activeCategory.value)
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      items = items.filter(i =>
        (i.item_name || '').toLowerCase().includes(q) ||
        (i.item_code || '').toLowerCase().includes(q))
    }
    return items
  })

  watch(activeDomain, () => loadMenu())

  // ---- search & barcode -------------------------------------------------
  const searchQuery = ref('')

  function tryScaleBarcode(code) {
    if (!/^\d+$/.test(code)) return null
    const rules = boot.value?.scale_rules || []
    for (const r of rules) {
      if (!r.prefix || !r.total_length) continue
      if (code.length !== r.total_length) continue
      if (!code.startsWith(r.prefix)) continue
      const itemPart = code.substr(r.code_start || 0, r.code_length || 0)
      const valuePart = code.substr(r.value_start || 0, r.value_length || 0)
      const value = parseInt(valuePart, 10) / (r.value_divisor || 1)
      const match = menuItems.value.find(i =>
        i.item_code === itemPart || i.alphax_scale_item_code === itemPart)
      if (!match) continue
      if (r.value_kind === 'Weight') return { item: match, qty: value, override_rate: null }
      if (r.value_kind === 'Price')  return { item: match, qty: 1, override_rate: value }
    }
    return null
  }

  // ---- cart -------------------------------------------------------------
  const cart = ref([])
  const cartUuid = ref(uuid())

  function addToCart(item, opts = {}) {
    const existing = cart.value.find(l => l.item_code === item.item_code && !l.unique && !opts.unique)
    if (existing) {
      existing.qty += (opts.qty || 1)
    } else {
      cart.value.push({
        line_uuid: uuid(),
        item_code: item.item_code,
        item_name: item.item_name || item.item_code,
        item_group: item.item_group,
        qty: opts.qty || 1,
        rate: opts.override_rate ?? (item.standard_rate || 0),
        uom: item.stock_uom,
        notes: '',
        modifiers: opts.modifiers || [],
        unique: !!opts.unique,
      })
    }
  }

  function changeQty(line_uuid, delta) {
    const line = cart.value.find(l => l.line_uuid === line_uuid)
    if (!line) return
    line.qty = Math.max(0, +(line.qty + delta).toFixed(3))
    if (line.qty === 0) cart.value = cart.value.filter(l => l.line_uuid !== line_uuid)
  }

  function setQty(line_uuid, qty) {
    const line = cart.value.find(l => l.line_uuid === line_uuid)
    if (line) line.qty = Math.max(0, +qty)
  }

  function setRate(line_uuid, rate) {
    const line = cart.value.find(l => l.line_uuid === line_uuid)
    if (line) line.rate = Math.max(0, +rate)
  }

  function setNotes(line_uuid, notes) {
    const line = cart.value.find(l => l.line_uuid === line_uuid)
    if (line) line.notes = notes
  }

  function removeLine(line_uuid) {
    cart.value = cart.value.filter(l => l.line_uuid !== line_uuid)
  }

  function clearCart() {
    cart.value = []
    cartUuid.value = uuid()
    customer.value = null
    wallet.value = null
    loyaltyQuote.value = null
    redemption.value = null
    tendered.value = {}
    activeTable.value = null
    context.value = { rx_number: null, doctor: null, patient: null, batch: null, appointment: null }
  }

  // ---- totals -----------------------------------------------------------
  const subtotal = computed(() =>
    cart.value.reduce((s, l) => s + l.qty * l.rate, 0))

  const taxRate = computed(() =>
    (boot.value?.taxes || []).reduce((s, r) => s + (Number(r.rate) || 0), 0))

  const taxAmount = computed(() => subtotal.value * (taxRate.value / 100))

  const redeemValue = computed(() => redemption.value?.value || 0)
  const redeemPoints = computed(() => redemption.value?.points || 0)

  const total = computed(() =>
    Math.max(0, subtotal.value + taxAmount.value - redeemValue.value))

  // ---- customer & wallet ------------------------------------------------
  const customer = ref(null)
  const wallet = ref(null)
  const loyaltyQuote = ref(null)
  const redemption = ref(null)

  async function setCustomer(name) {
    customer.value = name
    wallet.value = null
    redemption.value = null
    if (!name) return refreshLoyaltyQuote()
    const programs = boot.value?.loyalty_programs || []
    if (!programs.length) return refreshLoyaltyQuote()
    try {
      const rows = await api.lookupWallet({ customer: name, program: programs[0].name })
      wallet.value = (rows || [])[0] || null
    } catch (e) {}
    refreshLoyaltyQuote()
  }

  async function lookupLoyaltyCard(card) {
    try {
      const rows = await api.lookupWallet({ card_number: card })
      const w = (rows || [])[0]
      if (!w) return null
      wallet.value = w
      customer.value = w.customer
      refreshLoyaltyQuote()
      return w
    } catch (e) {
      return null
    }
  }

  async function refreshLoyaltyQuote() {
    const programs = boot.value?.loyalty_programs || []
    if (!programs.length || cart.value.length === 0) {
      loyaltyQuote.value = null
      return
    }
    try {
      const items = cart.value.map(l => ({
        item_code: l.item_code, qty: l.qty, rate: l.rate, amount: l.qty * l.rate
      }))
      loyaltyQuote.value = await api.quotePoints(programs[0].name, items, {
        net_total: subtotal.value,
        tax_total: taxAmount.value,
        domain: activeDomain.value,
        customer: customer.value,
      })
    } catch (e) {
      loyaltyQuote.value = null
    }
  }

  watch(cart, () => refreshLoyaltyQuote(), { deep: true })

  // Mirror cart-state changes to the customer pole display.
  // Lazy-imported to avoid a circular store import at module load.
  let _lastDisplaySig = ''
  watch([cart, () => total.value, () => taxAmount.value], async () => {
    try {
      const { useHardwareStore } = await import('./hardware')
      const hw = useHardwareStore()
      if (!hw.online || !hw.displayReady) return
      const cur = boot.value?.currency?.symbol || ''
      let payload
      if (cart.value.length === 0) {
        payload = { action: 'raw', top: 'Welcome', bottom: '' }
      } else {
        // Show running subtotal until tendering, then total.
        payload = { action: 'subtotal', amount: total.value, currency: cur }
      }
      const sig = JSON.stringify(payload)
      if (sig !== _lastDisplaySig) {
        _lastDisplaySig = sig
        hw.showOnDisplay(payload)
      }
    } catch {}
  }, { deep: true })

  async function previewRedemption(points) {
    const programs = boot.value?.loyalty_programs || []
    if (!programs.length || !customer.value) return null
    try {
      redemption.value = await api.quoteRedemption(
        programs[0].name, customer.value, points, total.value + redeemValue.value)
      return redemption.value
    } catch (e) {
      return null
    }
  }

  function clearRedemption() {
    redemption.value = null
  }

  // ---- table (for restaurant domain) ------------------------------------
  const activeTable = ref(null)
  function setTable(tableName) { activeTable.value = tableName }

  // ---- modifiers --------------------------------------------------------
  // Modifiers are loaded lazily per item. The cashier opens the modifier
  // dialog from a cart line; on close we replace the cart line with the
  // chosen options + price deltas applied.
  function applyModifiers(line_uuid, chosen) {
    const line = cart.value.find(l => l.line_uuid === line_uuid)
    if (!line) return
    line.modifiers = chosen
    line.unique = true // modifier-bearing lines never merge
    // recompute rate: base + sum of modifier deltas
    const base = chosen.base_rate ?? line.rate
    const delta = (chosen.options || []).reduce(
      (s, o) => s + (Number(o.price_delta) || 0), 0)
    line.rate = +(base + delta).toFixed(4)
  }

  // ---- contextual state (per-domain) ------------------------------------
  // Lightweight slots that the contextual ribbon writes into. The store
  // doesn't enforce semantics — these are pass-throughs surfaced on the
  // sale payload at submit time.
  const context = ref({
    rx_number: null,
    doctor: null,
    patient: null,
    batch: null,
    appointment: null,
  })
  function setContext(key, value) { context.value[key] = value }
  function clearContext() {
    context.value = { rx_number: null, doctor: null, patient: null, batch: null, appointment: null }
  }

  // ---- payment / tendering ----------------------------------------------
  const tendered = ref({})
  // Per-tender-mode metadata captured from the card terminal (auth code,
  // masked PAN, brand, txn id) so we can stamp the receipt and the
  // Sales Invoice payment row.
  const tenderMeta = ref({})

  function tender(mode, amount, meta = null) {
    tendered.value[mode] = (tendered.value[mode] || 0) + Number(amount)
    if (tendered.value[mode] <= 0) delete tendered.value[mode]
    if (meta) tenderMeta.value[mode] = { ...(tenderMeta.value[mode] || {}), ...meta }
  }

  function clearTender(mode) {
    if (mode) {
      delete tendered.value[mode]
      delete tenderMeta.value[mode]
    } else {
      tendered.value = {}
      tenderMeta.value = {}
    }
  }

  const totalTendered = computed(() =>
    Object.values(tendered.value).reduce((a, b) => a + b, 0))
  const remaining = computed(() =>
    Math.max(0, total.value - totalTendered.value))
  const change = computed(() =>
    Math.max(0, totalTendered.value - total.value))

  async function submitSale() {
    const outlet = boot.value?.outlet
    if (!outlet) throw new Error('No outlet')
    const programs = boot.value?.loyalty_programs || []
    const program = programs[0]?.name || null

    // The cart_uuid identifies this sale across retries. The server's
    // before_insert dedupe uses this same field, so retrying is safe.
    const client_uuid = cartUuid.value

    const invoice = {
      doctype: 'Sales Invoice',
      is_pos: 1,
      customer: customer.value || '__Walk-in',
      company: outlet.company,
      cost_center: outlet.cost_center,
      update_stock: outlet.update_stock,
      selling_price_list: outlet.default_price_list,
      taxes_and_charges: outlet.sales_taxes_and_charges_template,
      alphax_outlet: outlet.name,
      alphax_loyalty_program: program,
      alphax_loyalty_redeem_points: redeemPoints.value || 0,
      alphax_loyalty_redeem_value: redeemValue.value || 0,
      alphax_client_uuid: client_uuid,
      items: cart.value.map(l => ({
        item_code: l.item_code, qty: l.qty, rate: l.rate, warehouse: outlet.warehouse,
      })),
      payments: Object.entries(tendered.value).map(([mode, amount]) => ({
        mode_of_payment: mode, amount,
      })),
    }
    if (boot.value?.taxes?.length) {
      invoice.taxes = boot.value.taxes.map(t => ({
        charge_type: t.charge_type, account_head: t.account_head, rate: t.rate,
        description: t.description, included_in_print_rate: t.included_in_print_rate,
        cost_center: t.cost_center,
      }))
    }

    // Try online first.
    try {
      const inserted = await api.insertDoc(invoice)
      await api.submitDoc('Sales Invoice', inserted.name)
      return { name: inserted.name, queued: false }
    } catch (onlineErr) {
      // Online attempt failed. Queue it for later sync, but the sale is
      // still considered "complete" from the cashier's perspective —
      // receipt still prints, drawer still kicks. The queue worker will
      // push to the server when connectivity returns.
      const { useSyncStore } = await import('./sync')
      const sync = useSyncStore()
      try {
        await sync.enqueueSale(invoice, client_uuid)
        return { name: client_uuid, queued: true }
      } catch (queueErr) {
        // If even queueing fails (storage full, IndexedDB blocked), we
        // have to surface the original error.
        throw onlineErr
      }
    }
  }

  /** Build the structured receipt JSON for the bridge to print. */
  function buildReceipt(invoiceName) {
    const outlet = boot.value?.outlet || {}
    const cur = boot.value?.currency?.symbol || ''
    return {
      header: {
        store_name: outlet.outlet_name || outlet.name,
        branch:     outlet.branch || '',
        address:    outlet.address || '',
        vat_no:     outlet.vat_no || outlet.tax_id || '',
        phone:      outlet.phone  || '',
      },
      meta: {
        invoice_no: invoiceName,
        datetime:   new Date().toISOString().slice(0, 19).replace('T', ' '),
        cashier:    (window.frappe?.session?.user_fullname) || (window.frappe?.session?.user) || '',
        terminal:   terminal.value || '',
        table:      activeTable.value || '',
        customer:   customer.value || 'Walk-in',
      },
      items: cart.value.map(l => ({
        name:      l.item_name,
        qty:       l.qty,
        rate:      l.rate,
        amount:    +(l.qty * l.rate).toFixed(2),
        modifiers: l.modifiers || [],
      })),
      totals: {
        subtotal: subtotal.value,
        tax:      taxAmount.value,
        total:    total.value,
        tendered: totalTendered.value,
        change:   change.value,
        tax_breakdown: (boot.value?.taxes || []).map(t => ({
          label: t.description || `${t.rate || 0}%`,
          amount: +(subtotal.value * (Number(t.rate || 0) / 100)).toFixed(2),
        })),
      },
      payments: Object.entries(tendered.value).map(([mode, amount]) => {
        const m = tenderMeta.value[mode] || {}
        const tail = []
        if (m.card_brand)  tail.push(m.card_brand)
        if (m.masked_pan)  tail.push(m.masked_pan)
        if (m.auth_code)   tail.push(`auth ${m.auth_code}`)
        return {
          mode: tail.length ? `${mode} (${tail.join(' · ')})` : mode,
          amount,
        }
      }),
      loyalty:  loyaltyQuote.value ? {
        earned:   loyaltyQuote.value.points || 0,
        redeemed: redeemPoints.value || 0,
        balance:  wallet.value?.current_balance || null,
      } : null,
      footer: {
        line1: 'Thank you!',
      },
    }
  }

  // ---- hold / recall ----------------------------------------------------
  function holdCart() {
    if (cart.value.length === 0) return false
    const all = JSON.parse(localStorage.getItem(STORAGE_KEYS.held) || '[]')
    all.push({
      uuid: cartUuid.value,
      ts: new Date().toISOString(),
      customer: customer.value,
      cart: JSON.parse(JSON.stringify(cart.value)),
      domain: activeDomain.value,
    })
    localStorage.setItem(STORAGE_KEYS.held, JSON.stringify(all.slice(-30)))
    clearCart()
    return true
  }

  function listHeld() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.held) || '[]')
  }

  function recallHeld(idx) {
    const all = listHeld()
    const h = all[idx]
    if (!h) return
    cart.value = h.cart
    cartUuid.value = h.uuid
    customer.value = h.customer
    if (h.domain) switchDomain(h.domain)
    all.splice(idx, 1)
    localStorage.setItem(STORAGE_KEYS.held, JSON.stringify(all))
    refreshLoyaltyQuote()
    if (customer.value) setCustomer(customer.value)
  }

  return {
    // state
    terminal, boot, bootError, bootLoading,
    activeDomain, activeDomainPack, features, activeFeatures,
    menuItems, menuLoading, itemGroups, activeCategory,
    categories, filteredMenu, searchQuery,
    cart, cartUuid,
    customer, wallet, loyaltyQuote, redemption,
    activeTable, context,
    tendered, totalTendered, remaining, change,
    subtotal, taxRate, taxAmount, redeemValue, redeemPoints, total,
    // actions
    loadBoot, changeTerminal, switchDomain,
    loadMenu, tryScaleBarcode,
    addToCart, changeQty, setQty, setRate, setNotes, removeLine, clearCart,
    setCustomer, lookupLoyaltyCard, refreshLoyaltyQuote,
    previewRedemption, clearRedemption,
    setTable, applyModifiers, setContext, clearContext,
    tender, clearTender, submitSale, buildReceipt,
    holdCart, listHeld, recallHeld,
  }
})
