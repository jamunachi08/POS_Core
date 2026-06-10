// Mock data so the SPA can run with `npm run dev` or be demoed in
// isolation. Activated by adding `?mock=1` to the URL, or by setting
// localStorage.alphax_mock = '1'.
//
// All data shapes match what pos_boot returns from Frappe so swapping
// mock for real backend is transparent to every component.

const FEATURE_KEYS = [
  'uses_floor_plan','uses_kds','uses_modifiers','uses_recipes','uses_scale',
  'uses_batch_expiry','uses_serial','uses_appointments','uses_tips',
  'uses_service_charge','uses_courses','uses_table_qr','uses_split_bill',
  'uses_loyalty','uses_prescription'
]

const FAKE_DOMAINS = [
  { domain_code: 'Restaurant', label: 'Restaurant', enabled: 1, default_item_group: null,
    uses_floor_plan: 1, uses_kds: 1, uses_modifiers: 1, uses_recipes: 1,
    uses_tips: 1, uses_service_charge: 1, uses_courses: 1, uses_table_qr: 1,
    uses_split_bill: 1, uses_loyalty: 1 },
  { domain_code: 'Cafe', label: 'Café', enabled: 1, default_item_group: null,
    uses_kds: 1, uses_modifiers: 1, uses_recipes: 1, uses_tips: 1,
    uses_loyalty: 1, uses_split_bill: 1 },
  { domain_code: 'Retail', label: 'Retail', enabled: 1, default_item_group: null,
    uses_serial: 1, uses_loyalty: 1 },
  { domain_code: 'Pharmacy', label: 'Pharmacy', enabled: 1, default_item_group: null,
    uses_batch_expiry: 1, uses_prescription: 1, uses_loyalty: 1 },
  { domain_code: 'Salon', label: 'Salon', enabled: 1, default_item_group: null,
    uses_appointments: 1, uses_tips: 1, uses_loyalty: 1 },
]

function unionFeatures(domains) {
  const out = {}
  for (const k of FEATURE_KEYS) out[k] = 0
  for (const d of domains) for (const k of FEATURE_KEYS) if (d[k]) out[k] = 1
  return out
}

const FAKE_ITEMS = [
  { item_code: 'CAP-MD',  item_name: 'Cappuccino',     item_group: 'Coffee',     standard_rate: 18 },
  { item_code: 'LAT-MD',  item_name: 'Latte',          item_group: 'Coffee',     standard_rate: 20 },
  { item_code: 'AMR-MD',  item_name: 'Americano',      item_group: 'Coffee',     standard_rate: 16 },
  { item_code: 'ESP-SH',  item_name: 'Espresso',       item_group: 'Coffee',     standard_rate: 12 },
  { item_code: 'MCH-MD',  item_name: 'Mocha',          item_group: 'Coffee',     standard_rate: 22 },
  { item_code: 'TEA-CH',  item_name: 'Chai latte',     item_group: 'Tea',        standard_rate: 17 },
  { item_code: 'TEA-GR',  item_name: 'Green tea',      item_group: 'Tea',        standard_rate: 14 },
  { item_code: 'JU-OR',   item_name: 'Orange juice',   item_group: 'Cold drinks',standard_rate: 16 },
  { item_code: 'WTR-SP',  item_name: 'Sparkling water',item_group: 'Cold drinks',standard_rate: 8 },
  { item_code: 'CRO',     item_name: 'Croissant',      item_group: 'Bakery',     standard_rate: 12 },
  { item_code: 'MUF-CH',  item_name: 'Choc muffin',    item_group: 'Bakery',     standard_rate: 14 },
  { item_code: 'CAKE-CRT',item_name: 'Carrot cake',    item_group: 'Bakery',     standard_rate: 22 },
  { item_code: 'SAND-CH', item_name: 'Chicken sandwich',item_group: 'Food',      standard_rate: 38 },
  { item_code: 'SAL-CES', item_name: 'Caesar salad',   item_group: 'Food',       standard_rate: 42 },
  { item_code: 'PASTA-AL',item_name: 'Pasta Alfredo',  item_group: 'Food',       standard_rate: 48 },
  { item_code: 'BURG-CL', item_name: 'Classic burger', item_group: 'Food',       standard_rate: 45 },
  { item_code: 'TOM-LOOSE',item_name: 'Tomatoes (loose)', item_group:'Produce',  standard_rate: 8.5,
    alphax_is_weighing_item: 1, alphax_scale_item_code: '001231' },
  { item_code: 'APPL-LOOSE',item_name: 'Apples (loose)',  item_group:'Produce',  standard_rate: 12,
    alphax_is_weighing_item: 1 },
  { item_code: 'PARA-500',item_name: 'Paracetamol 500mg', item_group: 'OTC',     standard_rate: 8 },
  { item_code: 'IBU-200', item_name: 'Ibuprofen 200mg',   item_group: 'OTC',     standard_rate: 10 },
  { item_code: 'VIT-D3',  item_name: 'Vitamin D3 1000IU', item_group: 'Vitamins',standard_rate: 32 },
  { item_code: 'HC-200',  item_name: 'Haircut (men)',     item_group: 'Salon',   standard_rate: 75 },
  { item_code: 'HC-300',  item_name: 'Haircut + beard',   item_group: 'Salon',   standard_rate: 110 },
  { item_code: 'COL-150', item_name: 'Hair color',        item_group: 'Salon',   standard_rate: 220 },
]

const FAKE_BOOT = {
  _mock: true,
  terminal: { name: 'TERM-DEMO', terminal_name: 'Demo Terminal' },
  outlet: {
    name: 'OUT-DEMO',
    outlet_name: 'Demo Outlet',
    company: 'Demo Co',
    branch: null,
    warehouse: 'Stores - DC',
    cost_center: 'Main - DC',
    primary_domain: 'Cafe',
    update_stock: 1,
    default_price_list: 'Standard Selling',
    default_loyalty_program: 'CAFE-LOY',
    sales_taxes_and_charges_template: null,
  },
  domains: FAKE_DOMAINS,
  features: unionFeatures(FAKE_DOMAINS),
  profile: { name: 'PROF-DEMO', currency: 'USD' },
  theme: null,
  loyalty_programs: [
    { name: 'CAFE-LOY', program_code: 'CAFE-LOY', program_name: 'Café Loyalty',
      domain_scope: 'All Domains', earn_basis: 'Per Currency Spent',
      default_earn_points: 1, default_earn_per_amount: 10, redemption_value: 0.05,
      min_points_to_redeem: 100, max_redeem_percent: 50, expiry_days: 365 }
  ],
  payment_methods: [
    { mode_of_payment: 'Cash',   default: 1 },
    { mode_of_payment: 'Card',   default: 0 },
    { mode_of_payment: 'MADA',   default: 0 },
    { mode_of_payment: 'STC Pay',default: 0 },
  ],
  scale_rules: [
    { name: 'PROD-WEIGHT', prefix: '21', total_length: 13, code_start: 2, code_length: 6,
      value_start: 8, value_length: 5, value_kind: 'Weight', value_divisor: 1000 }
  ],
  taxes: [
    { charge_type: 'On Net Total', account_head: 'VAT - DC', rate: 15,
      description: 'VAT 15%', included_in_print_rate: 0, cost_center: 'Main - DC' }
  ],
  currency: { currency: 'USD', symbol: '$', precision: 2 },
  server_time: new Date().toISOString(),
  from_cache: false,
}

const FAKE_FLOORS = [
  {
    name: 'GROUND', floor_name: 'Ground floor', outlet: 'OUT-DEMO',
    canvas_width: 800, canvas_height: 500
  },
  {
    name: 'PATIO', floor_name: 'Patio', outlet: 'OUT-DEMO',
    canvas_width: 800, canvas_height: 500
  }
]

const FAKE_TABLES_BY_FLOOR = {
  GROUND: Array.from({ length: 12 }, (_, i) => ({
    name: `T${i + 1}`, table_code: `T${i + 1}`,
    seats: i % 3 === 0 ? 2 : (i % 3 === 1 ? 4 : 6),
    shape: i % 4 === 3 ? 'Circle' : 'Rectangle',
    status: i % 5 === 0 ? 'Occupied' : (i % 7 === 0 ? 'Dirty' : 'Free')
  })),
  PATIO: Array.from({ length: 6 }, (_, i) => ({
    name: `P${i + 1}`, table_code: `P${i + 1}`, seats: 2,
    shape: 'Circle', status: i === 2 ? 'Reserved' : 'Free'
  }))
}

const FAKE_CUSTOMERS = [
  { name: 'CUST-001', customer_name: 'Layla Hassan',  mobile_no: '+966 50 100 0001' },
  { name: 'CUST-002', customer_name: 'Omar Khalid',   mobile_no: '+966 50 100 0002' },
  { name: 'CUST-003', customer_name: 'Sara Ahmed',    mobile_no: '+966 50 100 0003' },
  { name: 'CUST-004', customer_name: 'Yousef Ali',    mobile_no: '+966 50 100 0004' },
  { name: 'CUST-005', customer_name: 'Hana Mohammed', mobile_no: '+966 50 100 0005' },
]

const FAKE_WALLETS = {
  'CUST-001': { name: 'LW-CUST-001', customer: 'CUST-001', program: 'CAFE-LOY',
    card_number: 'L1001', current_balance: 542, lifetime_earned: 1840,
    lifetime_redeemed: 1298, current_tier: 'Silver' },
}

export const mock = {
  isMockMode() {
    const url = new URL(window.location.href)
    return url.searchParams.get('mock') === '1' || localStorage.getItem('alphax_mock') === '1'
  },
  posBoot: async () => structuredClone(FAKE_BOOT),
  listTerminals: async () => [{ name: 'TERM-DEMO' }, { name: 'TERM-DEMO-2' }],
  listItems: async () => structuredClone(FAKE_ITEMS),
  listItemGroups: async () => {
    const seen = new Set(['All Item Groups'])
    const out = [{ name: 'All Item Groups', parent_item_group: null, lft: 1, rgt: 100 }]
    let lft = 2
    for (const it of FAKE_ITEMS) {
      if (it.item_group && !seen.has(it.item_group)) {
        seen.add(it.item_group)
        out.push({
          name: it.item_group,
          parent_item_group: 'All Item Groups',
          lft, rgt: lft + 1
        })
        lft += 2
      }
    }
    return out
  },
  listFloors: async () => structuredClone(FAKE_FLOORS),
  getFloorLayout: async (floor) => ({
    floor: FAKE_FLOORS.find(f => f.name === floor),
    tables: FAKE_TABLES_BY_FLOOR[floor] || []
  }),
  searchCustomers: async (q) => {
    if (!q) return FAKE_CUSTOMERS
    const lc = q.toLowerCase()
    return FAKE_CUSTOMERS.filter(c =>
      (c.customer_name || '').toLowerCase().includes(lc) ||
      (c.name || '').toLowerCase().includes(lc))
  },
  lookupWallet: async ({ card_number, customer }) => {
    if (card_number) {
      return Object.values(FAKE_WALLETS).filter(w => w.card_number === card_number)
    }
    if (customer) {
      const w = FAKE_WALLETS[customer]
      return w ? [w] : []
    }
    return []
  },
  quotePoints: async (program, items, opts = {}) => {
    const subtotal = items.reduce((s, l) => s + (l.amount || l.qty * l.rate || 0), 0)
    const points = Math.floor(subtotal / 10)
    return {
      points,
      breakdown: items.map(it => ({
        item_code: it.item_code,
        points: Math.floor((it.amount || it.qty * it.rate || 0) / 10),
        rule_used: 'program_default'
      })).filter(b => b.points > 0)
    }
  },
  quoteRedemption: async (program, customer, points, billTotal) => {
    return { wallet: 'LW-' + customer, points, value: +(points * 0.05).toFixed(2),
             redeem_value_multiplier: 1 }
  },
  insertDoc: async (doc) => ({ name: 'SINV-DEMO-' + Math.floor(Math.random() * 1e6) }),
  submitDoc: async () => ({ ok: true }),
}
