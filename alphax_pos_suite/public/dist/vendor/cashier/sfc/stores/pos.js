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
    // shift state rides along with every boot refresh
    setTimeout(() => { loadShift() }, 0)
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
      const rows = await api.listItems({ item_groups: groupFilter })
      // Guard: a Frappe error dict is truthy but not iterable.
      menuItems.value = Array.isArray(rows) ? rows : []
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

  // ---- policy (AlphaX POS Settings, delivered via pos_boot) --------------
  // Empty object when the server predates the settings block — every
  // consumer must treat missing keys as "feature off / no gate".
  const settings = computed(() => boot.value?.settings || {})

  // ---- order type -----------------------------------------------------------
  // Dine In / Takeaway / Staff post normally (tender via PaymentDialog).
  // Delivery posts the full amount against the platform's Mode of
  // Payment (the app collects from the customer). Credit posts a
  // regular outstanding Sales Invoice (is_pos=0, no payments) and
  // REQUIRES a named customer.
  const ORDER_TYPES = ['Dine In', 'Takeaway', 'Delivery', 'Staff', 'Credit']
  const orderType = ref('Dine In')
  const deliveryPlatform = ref(null)   // row from boot.delivery_platforms

  const deliveryPlatforms = computed(() => boot.value?.delivery_platforms || [])

  function setOrderType(type, platform = null) {
    if (!ORDER_TYPES.includes(type)) return
    orderType.value = type
    deliveryPlatform.value = type === 'Delivery' ? platform : null
  }

  // ---- shift & cash management ---------------------------------------------
  // Server is the source of truth (blind close happens there); the
  // store keeps the latest summary for the sidebar chip and dialogs.
  const shift = ref(null)          // summary object from shift_api, or null
  const shiftLoading = ref(false)

  async function loadShift() {
    if (!terminal.value) return
    shiftLoading.value = true
    try {
      const res = await api.getShiftState(terminal.value)
      shift.value = res && res.open ? res.summary : null
    } catch (e) {
      // older server without shift_api — feature simply hides
      shift.value = null
    } finally {
      shiftLoading.value = false
    }
  }

  // Trading day for every document this register creates. Shift summary
  // is the fresh source (updated on open/close); boot payload covers the
  // window before the first shift state loads. Falls back to the device
  // date only if neither is known (shift-optional deployments).
  const combos = computed(() => boot.value?.combos || [])

  const businessDate = computed(() =>
    (shift.value && shift.value.summary && shift.value.summary.business_date)
    || (boot.value && boot.value.terminal && boot.value.terminal.business_date)
    || new Date().toISOString().slice(0, 10)
  )

  async function openShift(openingCash, forUser = null, notes = null) {
    const res = await api.openShift(terminal.value, openingCash, notes, forUser)
    shift.value = res.summary
    return res.summary
  }

  async function cashMovement(type, amount, remarks) {
    const res = await api.recordCashMovement(shift.value.shift, type, amount, remarks)
    shift.value = res.summary
    return res.summary
  }

  async function fetchXReport() {
    const s = await api.xReport(shift.value.shift)
    shift.value = s
    return s
  }

  async function closeShift(countedCash, notes, handoverTo = null) {
    const z = await api.closeShift(shift.value.shift, countedCash, notes, handoverTo)
    shift.value = null
    return z
  }

  async function runDayClose() {
    return await api.dayClose(terminal.value)
  }

  // ---- appearance -----------------------------------------------------------
  const theme = ref(localStorage.getItem('alphax_pos_theme') || 'emerald')
  function setTheme(name) {
    theme.value = name
    localStorage.setItem('alphax_pos_theme', name)
  }

  // ---- return mode --------------------------------------------------------
  // When active, the cart represents goods coming BACK: totals display
  // negative, and submitSale posts a return Sales Invoice (is_return=1,
  // negative quantities). Toggling is gated by settings.allow_returns and
  // (optionally) a manager PIN — enforced by the UI layer.
  const returnMode = ref(false)
  const returnReason = ref(null)

  function setReturnMode(on, reason = null) {
    returnMode.value = !!on
    returnReason.value = on ? reason : null
  }

  // ---- barcode scan (server-backed) -------------------------------------
  // Resolves product barcodes, scale/weight barcodes, and bare PLUs via the
  // server, then drops the result straight into the cart. Used by the
  // keyboard-wedge listener and the search box (when input is all digits).
  const lastScan = ref(null)      // { found, source, item_name, ... }
  const scanError = ref(null)     // human string when a scan misses

  async function scan(code) {
    code = (code || '').trim()
    if (!code) return null
    scanError.value = null
    try {
      const res = await api.scanBarcode(code, {
        pos_profile: boot.value?.profile?.name || null,
        outlet: boot.value?.outlet?.name || null,
      })
      lastScan.value = res
      if (res && res.found) {
        addToCart(
          {
            item_code: res.item_code,
            item_name: res.item_name,
            item_group: res.item_group,
            stock_uom: res.uom,
            standard_rate: res.rate,
          },
          {
            qty: res.qty || 1,
            override_rate: res.rate_overridden ? res.rate : res.rate,
          }
        )
        return res
      }
      // Fall back to the local in-menu scale parser for offline resilience.
      const local = tryScaleBarcode(code)
      if (local) {
        addToCart(local.item, { qty: local.qty, override_rate: local.override_rate })
        return { found: true, source: 'local-scale' }
      }
      scanError.value = (res && res.message) || `No item for ${code}`
      return res
    } catch (e) {
      scanError.value = e.message || String(e)
      return { found: false, error: scanError.value }
    }
  }

  function addComboToCart(combo, choice) {
    // One priced line on the billing item; components ride along for
    // display, zero-rate invoice lines, and per-station KOT explosion.
    cart.value.push({
      line_uuid: uuid(),
      is_combo: true,
      combo_name: combo.combo_name,
      item_code: combo.billing_item,
      item_name: combo.combo_name,
      item_group: null,
      qty: 1,
      rate: choice.price,
      base_rate: choice.price,
      uom: null,
      notes: '',
      modifiers: choice.components.map(c =>
        (c.substituted ? '⇄ ' : '') + c.qty + '× ' + c.item_name),
      combo_components: choice.components,
      unique: true,
    })
  }

  function addToCart(item, opts = {}) {
    const existing = cart.value.find(l => l.item_code === item.item_code && !l.unique && !opts.unique)
    if (existing) {
      existing.qty += (opts.qty || 1)
    } else {
      const rate = opts.override_rate ?? (item.standard_rate || 0)
      cart.value.push({
        line_uuid: uuid(),
        item_code: item.item_code,
        item_name: item.item_name || item.item_code,
        item_group: item.item_group,
        qty: opts.qty || 1,
        rate,
        base_rate: rate, // list price at add time — approvals compare against this
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
    returnMode.value = false
    returnReason.value = null
    orderType.value = 'Dine In'
    deliveryPlatform.value = null
    context.value = { rx_number: null, doctor: null, patient: null, batch: null, appointment: null }
  }

  // ---- totals -----------------------------------------------------------
  // ---- tax engine ---------------------------------------------------------
  // Sequential row engine, per LINE, honoring the KSA realities:
  //  * included_in_print_rate → menu prices are tax-INCLUSIVE: the net
  //    base is EXTRACTED from the shown price, never added on top.
  //  * Item Tax Templates override a row's rate per item — the tobacco
  //    fee row sits at rate 0 in the template and becomes 100% only for
  //    sheesha items carrying the tobacco Item Tax Template.
  //  * charge_type 'On Previous Row Total' compounds (KSA: VAT is
  //    computed on the tobacco-fee-INCLUSIVE amount).
  // ERPNext recomputes on insert from the same templates; this engine
  // exists so the till, the receipt, and the GL show identical figures.
  function lineTax(line) {
    const rows = boot.value?.taxes || []
    const tpl = (boot.value?.item_tax_templates || {})[
      (boot.value?.item_tax_map || {})[line.item_code]
    ] || null
    const gross = line.qty * line.rate
    if (!rows.length) return { net: gross, parts: [], gross }
    // simulate the chain on net=1 to learn the inclusive factor
    const rates = rows.map(r => {
      const override = tpl && r.account_head in tpl ? tpl[r.account_head] : null
      return { ...r, eff: Number(override != null ? override : r.rate) || 0 }
    })
    const factorParts = []
    let running = 1
    for (const r of rates) {
      const base = r.charge_type === 'On Previous Row Total' ? running : 1
      const amt = base * r.eff / 100
      factorParts.push(amt)
      running += amt
    }
    const inclusive = rates.some(r => r.included_in_print_rate && r.eff)
    const net = inclusive ? gross / running : gross
    let runTotal = net
    const parts = rates.map(r => {
      const base = r.charge_type === 'On Previous Row Total' ? runTotal : net
      const amt = base * r.eff / 100
      runTotal += amt
      return { account_head: r.account_head, label: r.description || r.account_head, amount: amt }
    })
    return { net, parts, gross: runTotal }
  }

  const taxBreakdown = computed(() => {
    const agg = {}
    for (const l of cart.value) {
      for (const p of lineTax(l).parts) {
        const k = p.account_head
        agg[k] = agg[k] || { label: p.label, account_head: k, amount: 0 }
        agg[k].amount += p.amount
      }
    }
    return Object.values(agg).filter(r => Math.abs(r.amount) > 0.004)
  })

  const subtotal = computed(() =>
    cart.value.reduce((s, l) => s + lineTax(l).net, 0))

  // Back-compat aggregate rate (approximate under per-item templates).
  const taxRate = computed(() =>
    (boot.value?.taxes || []).reduce((s, r) => s + (Number(r.rate) || 0), 0))

  const taxAmount = computed(() =>
    taxBreakdown.value.reduce((s, r) => s + r.amount, 0))

  const redeemValue = computed(() => redemption.value?.value || 0)
  const redeemPoints = computed(() => redemption.value?.points || 0)

  const total = computed(() =>
    Math.max(0, subtotal.value + taxAmount.value - redeemValue.value))
  // Cart line amounts keep showing the SHOWN price (qty × rate) — under
  // inclusive pricing that already contains the taxes above.

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
      // NOT `await import('./hardware')`: native dynamic import inside
      // loader-evaluated modules resolves as a raw URL
      // (…/cashier/hardware → 404, field report testneo.frappe.cloud,
      // "Failed to fetch dynamically imported module"). All store
      // factories are preloaded into window.AlphaXStores before mount;
      // looking them up at call time gives the same deferred resolution
      // the dynamic import was there for (pos.js loads first, so a
      // module-scope destructure would grab undefined).
      const { useHardwareStore } = window.AlphaXStores
      if (!useHardwareStore) return
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

    const isReturn = returnMode.value
    const isCredit = !isReturn && orderType.value === 'Credit'
    const isDelivery = !isReturn && orderType.value === 'Delivery'
    // ERPNext expects return invoices to carry negative quantities and
    // negative payment amounts; the tendering UI works in positive
    // numbers throughout, so we flip signs only here at the boundary.
    const sign = isReturn ? -1 : 1

    if (isCredit && !customer.value) {
      throw new Error('CREDIT_NEEDS_CUSTOMER')
    }

    // Payment rows:
    //  - Credit: none — a regular outstanding invoice on the customer.
    //  - Delivery: the full total against the platform's Mode of
    //    Payment (the platform collected from the customer).
    //  - Everything else: whatever was tendered.
    let paymentRows
    if (isCredit) {
      paymentRows = []
    } else if (isDelivery && deliveryPlatform.value) {
      const mop = deliveryPlatform.value.mode_of_payment
        || Object.keys(tendered.value)[0]
      paymentRows = [{ mode_of_payment: mop, amount: sign * total.value }]
    } else {
      paymentRows = Object.entries(tendered.value).map(([mode, amount]) => ({
        mode_of_payment: mode, amount: sign * amount,
      }))
    }

    if (!customer.value && !settings.value.default_customer) {
      throw new Error(
        'No customer selected and no default customer is configured. '
        + 'Set Default Customer on the AlphaX POS Terminal (or POS Settings) in the desk. '
        + 'لم يتم اختيار عميل ولا يوجد عميل افتراضي — حدد العميل الافتراضي في إعدادات الجهاز.'
      )
    }

    const invoice = {
      doctype: 'Sales Invoice',
      // Trading-day stamp, applied AT SALE TIME so offline-queued sales
      // keep their business date even when they sync after day close.
      // set_posting_time makes ERPNext honor it instead of resetting to
      // the server clock's date.
      posting_date: businessDate.value,
      set_posting_time: 1,
      is_pos: isCredit ? 0 : 1,
      is_return: isReturn ? 1 : 0,
      // No fabricated fallback: '__Walk-in' (a customer that exists on
      // no site) crashed ERPNext's set_pos_fields with a tuple-unpack
      // TypeError and poisoned the offline queue with unpostable
      // payloads. Boot now guarantees settings.default_customer is a
      // validated, existing customer or null — and null blocks the
      // sale below with a message a human can act on.
      customer: customer.value || settings.value.default_customer || null,
      company: outlet.company,
      cost_center: outlet.cost_center,
      update_stock: outlet.update_stock,
      selling_price_list: outlet.default_price_list,
      taxes_and_charges: outlet.sales_taxes_and_charges_template,
      alphax_outlet: outlet.name,
      alphax_pos_terminal: terminal.value,
      alphax_order_type: isReturn ? null : orderType.value,
      alphax_delivery_platform: isDelivery && deliveryPlatform.value
        ? deliveryPlatform.value.name : null,
      alphax_loyalty_program: program,
      alphax_loyalty_redeem_points: isReturn ? 0 : (redeemPoints.value || 0),
      alphax_loyalty_redeem_value: isReturn ? 0 : (redeemValue.value || 0),
      alphax_client_uuid: client_uuid,
      items: cart.value.flatMap(l => l.is_combo ? [
        {
          item_code: l.item_code, qty: sign * l.qty, rate: l.rate,
          item_name: l.combo_name, warehouse: outlet.warehouse,
        },
        // Components at zero rate: stock moves (when update_stock), the
        // kitchen and the customer both see what's inside, VAT stays on
        // the priced parent line.
        ...l.combo_components.map(c => ({
          item_code: c.item_code, qty: sign * c.qty * l.qty, rate: 0,
          warehouse: outlet.warehouse,
          item_name: (c.substituted ? '⇄ ' : '') + c.item_name + ' (' + l.combo_name + ')',
        })),
      ] : [{
        item_code: l.item_code, qty: sign * l.qty, rate: l.rate, warehouse: outlet.warehouse,
        item_tax_template: (boot.value?.item_tax_map || {})[l.item_code] || undefined,
      }]),
      payments: paymentRows,
    }
    if (isReturn && returnReason.value) {
      invoice.remarks = `Return reason: ${returnReason.value}`
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
      // Same registry lookup as the hardware store above — a native
      // dynamic import 404s under the SFC loader. This path is the
      // offline sale queue: it MUST work, so if the registry is somehow
      // empty we rethrow the original error rather than silently
      // losing the sale.
      const { useSyncStore } = window.AlphaXStores || {}
      if (!useSyncStore) throw onlineErr
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
  // ---- KOT routing (client-side, offline-capable) ----------------------
  // Rules and stations arrive in the boot payload; routing is a plain
  // dict walk over pre-expanded item-group ancestor chains. Paper KOTs
  // print AT SALE TIME through the bridge — the kitchen must get its
  // ticket even with no internet. Server-side KDS tickets are created
  // on invoice submit and mirror this routing for the display board.
  function routeCartToStations() {
    const kot = boot.value?.kot
    if (!kot || !kot.stations || !kot.stations.length) return []
    const stationByName = Object.fromEntries(kot.stations.map(s => [s.name, s]))
    const ruleMap = Object.fromEntries((kot.rules || []).map(r => [r.item_group, r.station]))
    const fallback = kot.stations.find(s => s.is_default) || null
    const groups = {}
    const overrides = kot.item_overrides || {}
    // Combos explode HERE: components route to their own stations
    // (burger → hot kitchen, drink → juice bar), each tagged with the
    // combo name so the stations know the pieces belong together. The
    // priced parent line never reaches a kitchen.
    const routable = cart.value.flatMap(l => l.is_combo
      ? l.combo_components.map(c => ({
          item_code: c.item_code, item_name: c.item_name, item_group: c.item_group,
          qty: c.qty * l.qty, modifiers: [],
          notes: 'COMBO: ' + l.combo_name + (c.substituted ? ' (swap)' : ''),
        }))
      : [l])
    for (const line of routable) {
      let station = overrides[line.item_code] || null
      const chain = (kot.group_chains || {})[line.item_group] || [line.item_group]
      if (!station) for (const g of chain) {
        if (ruleMap[g]) { station = ruleMap[g]; break }
      }
      if (!station && fallback) station = fallback.name
      if (!station) continue
      ;(groups[station] = groups[station] || []).push(line)
    }
    return Object.entries(groups).map(([name, lines]) => ({
      station: stationByName[name] || { name },
      lines,
    }))
  }

  function buildKotTicket(stationGroup, invoiceName) {
    return {
      kind: 'kot',
      header: { station: stationGroup.station.station_name || stationGroup.station.name },
      meta: {
        invoice_no: invoiceName,
        datetime: new Date().toISOString().slice(0, 19).replace('T', ' '),
        table: activeTable.value || '',
        order_type: orderType.value || '',
        business_date: businessDate.value,
      },
      items: stationGroup.lines.map(l => ({
        name: l.item_name,
        qty: l.qty,
        modifiers: l.modifiers || [],
        notes: l.notes || '',
      })),
    }
  }

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
        tax_breakdown: taxBreakdown.value.map(t => ({
          label: t.label,
          amount: +t.amount.toFixed(2),
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
    settings, returnMode, returnReason, setReturnMode,
    ORDER_TYPES, orderType, deliveryPlatform, deliveryPlatforms, setOrderType,
    theme, setTheme,
    shift, shiftLoading, businessDate, combos, taxBreakdown, lineTax, loadShift, openShift, cashMovement, fetchXReport, closeShift, runDayClose,
    customer, wallet, loyaltyQuote, redemption,
    activeTable, context,
    tendered, totalTendered, remaining, change,
    subtotal, taxRate, taxAmount, redeemValue, redeemPoints, total,
    // actions
    loadBoot, changeTerminal, switchDomain,
    loadMenu, tryScaleBarcode,
    scan, scanError, lastScan,
    addToCart, changeQty, setQty, setRate, setNotes, removeLine, clearCart,
    setCustomer, lookupLoyaltyCard, refreshLoyaltyQuote,
    previewRedemption, clearRedemption,
    setTable, applyModifiers, setContext, clearContext,
    tender, clearTender, submitSale, buildReceipt, routeCartToStations, buildKotTicket, addComboToCart,
    holdCart, listHeld, recallHeld,
  }
})
