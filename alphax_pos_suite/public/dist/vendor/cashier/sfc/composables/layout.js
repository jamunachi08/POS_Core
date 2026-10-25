// AlphaX POS — domain-adaptive cashier layouts.
//
// NOTE ON LOCATION: this lives in composables/, not a layouts/ folder.
// The SFC loader rewrites imports to globals by directory and only maps
// stores/, api/, composables/ and locales/. An import from layouts/
// throws "unrecognized import source" at compile time.
//
// The cashier screen is not one screen. A supermarket till and a fine-
// dining terminal share a data model and share almost nothing else about
// how a human uses them:
//
//   Supermarket  — barcode-first. The scanner drives everything; the
//                  screen is a receipt tape plus a small pad of
//                  no-barcode items (produce, bakery). Tiles are a
//                  fallback, not the main event. Speed metric: items
//                  per minute.
//   Restaurant   — menu-first. Big tiles, modifiers, courses, table
//                  context always visible. Speed metric: order accuracy.
//   Hospitality  — folio-first. The "cart" is a room, not a basket.
//                  Charges post to a stay, not a sale.
//   Pharmacy     — search-first with Rx capture and batch/expiry.
//   Salon/Service— appointment-first.
//
// A layout is a *preset*: which panel occupies which slot, how dense the
// grid is, what the primary input is, and which chrome is visible. The
// Domain Pack doctype now carries `layout_preset`, so an operator can
// override per outlet without a code change.

export const SLOT = {
  RAIL: 'rail',
  MAIN: 'main',
  TICKET: 'ticket',
  STRIP: 'strip',      // full-width band above the columns
  FOOTER: 'footer',
}

/**
 * preset = {
 *   id, label,
 *   columns: css grid-template-columns,
 *   primaryInput: 'scan' | 'menu' | 'search' | 'room' | 'appointment',
 *   tile: { min, max, rows, showImage, showPrice, showStock },
 *   panels: { main, ticket, strip },
 *   chrome: { ... booleans that toggle whole regions ... },
 *   quick: { topMovers, count, source }
 * }
 */
const PRESETS = {

  // ---------------------------------------------------------------
  restaurant: {
    id: 'restaurant',
    label: 'Restaurant / Cafe',
    columns: '64px minmax(0,1.35fr) minmax(320px,0.85fr)',
    primaryInput: 'menu',
    tile: { min: 132, max: 190, showImage: true, showPrice: true, showStock: false },
    panels: { main: 'MenuPanel', ticket: 'CartPanel', strip: 'OrderTypeBar' },
    chrome: {
      categoryTabs: true, searchBar: true, scanBox: false,
      tableContext: true, courseBar: true, modifiers: true,
      weightBox: false, priceCheck: false, roomContext: false,
      customerBar: true, splitBill: true,
    },
    quick: { topMovers: false, count: 0 },
  },

  // ---------------------------------------------------------------
  // Supermarket: the scanner IS the interface. Everything else is
  // secondary. The tape is the largest element on screen because that's
  // what the cashier and the customer both look at.
  supermarket: {
    id: 'supermarket',
    label: 'Supermarket / Grocery',
    columns: '56px minmax(0,0.85fr) minmax(400px,1.15fr)',
    primaryInput: 'scan',
    tile: { min: 96, max: 120, showImage: false, showPrice: true, showStock: true },
    panels: { main: 'ScanPad', ticket: 'TapePanel', strip: 'ScanStrip' },
    chrome: {
      categoryTabs: false, searchBar: true, scanBox: true,
      tableContext: false, courseBar: false, modifiers: false,
      weightBox: true, priceCheck: true, roomContext: false,
      customerBar: true, splitBill: false,
      ageCheck: true, voidLastLine: true, quantityPad: true,
    },
    // The five-to-twelve items that are 60% of no-barcode volume:
    // bananas, bread, water, bags, newspapers. Computed from actual
    // sales velocity so it self-tunes per outlet.
    quick: { topMovers: true, count: 12, source: 'velocity', window_days: 28 },
  },

  // ---------------------------------------------------------------
  hospitality: {
    id: 'hospitality',
    label: 'Hotel Outlet',
    columns: '64px minmax(0,1.2fr) minmax(360px,1fr)',
    primaryInput: 'room',
    tile: { min: 128, max: 176, showImage: true, showPrice: true, showStock: false },
    panels: { main: 'MenuPanel', ticket: 'FolioPanel', strip: 'RoomStrip' },
    chrome: {
      categoryTabs: true, searchBar: true, scanBox: false,
      tableContext: true, courseBar: true, modifiers: true,
      weightBox: false, priceCheck: false, roomContext: true,
      customerBar: false, splitBill: true,
      chargeToRoom: true, guestLookup: true, cityLedger: true,
    },
    quick: { topMovers: false, count: 0 },
  },

  // ---------------------------------------------------------------
  pharmacy: {
    id: 'pharmacy',
    label: 'Pharmacy',
    columns: '64px minmax(0,1.1fr) minmax(360px,1fr)',
    primaryInput: 'search',
    tile: { min: 116, max: 150, showImage: false, showPrice: true, showStock: true },
    panels: { main: 'MenuPanel', ticket: 'CartPanel', strip: 'RxStrip' },
    chrome: {
      categoryTabs: true, searchBar: true, scanBox: true,
      tableContext: false, courseBar: false, modifiers: false,
      weightBox: false, priceCheck: true, roomContext: false,
      customerBar: true, splitBill: false,
      rxCapture: true, batchExpiry: true, interactionWarn: true,
    },
    quick: { topMovers: true, count: 8, source: 'velocity', window_days: 28 },
  },

  // ---------------------------------------------------------------
  retail: {
    id: 'retail',
    label: 'Retail / Fashion',
    columns: '64px minmax(0,1.2fr) minmax(340px,0.9fr)',
    primaryInput: 'scan',
    tile: { min: 128, max: 172, showImage: true, showPrice: true, showStock: true },
    panels: { main: 'MenuPanel', ticket: 'CartPanel', strip: 'ScanStrip' },
    chrome: {
      categoryTabs: true, searchBar: true, scanBox: true,
      tableContext: false, courseBar: false, modifiers: false,
      weightBox: false, priceCheck: true, roomContext: false,
      customerBar: true, splitBill: false,
      variantPicker: true, sizeGrid: true,
    },
    quick: { topMovers: false, count: 0 },
  },

  // ---------------------------------------------------------------
  service: {
    id: 'service',
    label: 'Salon / Service',
    columns: '64px minmax(0,1.1fr) minmax(360px,1fr)',
    primaryInput: 'appointment',
    tile: { min: 140, max: 200, showImage: true, showPrice: true, showStock: false },
    panels: { main: 'MenuPanel', ticket: 'CartPanel', strip: 'AppointmentStrip' },
    chrome: {
      categoryTabs: true, searchBar: true, scanBox: false,
      tableContext: false, courseBar: false, modifiers: true,
      weightBox: false, priceCheck: false, roomContext: false,
      customerBar: true, splitBill: false,
      appointments: true, staffPicker: true, tips: true,
    },
    quick: { topMovers: false, count: 0 },
  },
}

// Domain code (as stored on AlphaX POS Domain Pack) -> preset id.
const DOMAIN_TO_PRESET = {
  Restaurant: 'restaurant',
  Cafe: 'restaurant',
  Bakery: 'supermarket',
  Supermarket: 'supermarket',
  Grocery: 'supermarket',
  Retail: 'retail',
  Clothing: 'retail',
  Electronics: 'retail',
  Pharmacy: 'pharmacy',
  Salon: 'service',
  Service: 'service',
  Garage: 'service',
  Hotel: 'hospitality',
  Hospitality: 'hospitality',
  Generic: 'restaurant',
}

export function listPresets() {
  return Object.values(PRESETS).map(p => ({ id: p.id, label: p.label }))
}

/**
 * Resolve the layout for the booted terminal.
 *
 * Precedence:
 *   1. explicit `layout_preset` on the active domain pack (operator override)
 *   2. mapping from the domain code
 *   3. restaurant (the historical default — never break an existing install)
 *
 * Feature flags from the domain pack are merged INTO chrome, so an
 * operator ticking "uses_scale" on a restaurant gets the weight box
 * without needing a new preset.
 */
export function resolveLayout(boot) {
  const domains = boot?.domains || []
  const primary = domains[0] || {}
  const explicit = primary.layout_preset
  const presetId = PRESETS[explicit]
    ? explicit
    : (DOMAIN_TO_PRESET[primary.domain_code] || 'restaurant')

  const base = PRESETS[presetId]
  const f = boot?.features || {}

  const chrome = {
    ...base.chrome,
    // feature flags win where they are explicitly on
    ...(f.uses_scale ? { weightBox: true } : {}),
    ...(f.uses_modifiers ? { modifiers: true } : {}),
    ...(f.uses_courses ? { courseBar: true } : {}),
    ...(f.uses_split_bill ? { splitBill: true } : {}),
    ...(f.uses_prescription ? { rxCapture: true } : {}),
    ...(f.uses_batch_expiry ? { batchExpiry: true } : {}),
    ...(f.uses_appointments ? { appointments: true } : {}),
    ...(f.uses_floor_plan ? { tableContext: true } : {}),
  }

  // Density override: a 10" tablet cannot show 190px tiles usefully.
  const tile = { ...base.tile }
  if (window.innerWidth < 1100) {
    tile.min = Math.max(88, Math.round(tile.min * 0.78))
    tile.max = Math.round(tile.max * 0.8)
  }

  return {
    ...base,
    id: presetId,
    tile,
    chrome,
    quick: { ...base.quick, ...(primary.quick_override || {}) },
    domain_code: primary.domain_code || 'Generic',
  }
}

export default PRESETS
