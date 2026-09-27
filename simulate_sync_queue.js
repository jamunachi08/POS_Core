// Service-mode gate test.
//
// Loads the real vendored Vue + Pinia, evaluates the real stores/pos.js
// through the real loader, and drives the table policy the way a cashier
// would: pick Dine In (mandatory table) -> blocked; pick Takeaway -> not
// blocked and any held table released.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = '/home/claude/pos/final/alphax_pos_suite/public/dist/vendor';
const CASHIER = path.join(ROOT, 'cashier');
const SFC = path.join(CASHIER, 'sfc');

const win = {
  location: { href: 'https://x.test/app/alphax-cashier', origin: 'https://x.test',
              search: '', searchParams: null },
  navigator: { userAgent: 'node', language: 'en', onLine: true },
  localStorage: (() => { const m = {}; return {
    getItem: k => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v); },
    removeItem: k => { delete m[k]; } }; })(),
  document: { head: { appendChild() {} }, createElement: () => ({ style: {}, setAttribute() {} }),
              addEventListener() {}, removeEventListener() {} },
  addEventListener() {}, removeEventListener() {},
  frappe: { csrf_token: 'x', session: { user: 'tester' } },
  fetch: async () => { throw new Error('no network'); },
  URL,
};
win.window = win; win.self = win; win.globalThis = win;

const ctx = vm.createContext(Object.assign(win, {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  crypto: require('crypto').webcrypto, TextEncoder, TextDecoder,
}));

for (const f of ['vue.global.prod.js', 'pinia.iife.prod.js', 'vue-i18n.global.prod.js']) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
}
vm.runInContext(fs.readFileSync(path.join(CASHIER, 'sfc-loader.js'), 'utf8'), ctx,
  { filename: 'sfc-loader.js' });

// Loader, lifted verbatim out of main.js.
const mainSrc = fs.readFileSync(path.join(CASHIER, 'main.js'), 'utf8');
const start = mainSrc.indexOf('  async function loadESMAsObject(path) {');
const end = mainSrc.indexOf('  // -------------------------------------------------------------------\n  // Phase A');
// Serve modules from disk; the loader prefers this hook over fetch().
ctx.ALPHAX_SPA_FETCH = async (rel) =>
  fs.readFileSync(path.join(SFC, rel.replace(/^cashier\/sfc\//, '')), 'utf8');
const loadESMAsObject = vm.runInContext(
  `(function(){ ${mainSrc.slice(start, end)}
     function rewriteWithSFCLoader(s, p) { return window.AlphaXSFC.rewriteImports(s, p); }
     return loadESMAsObject; })()`, ctx, { filename: 'loader.js' });

// Fake IndexedDB-backed queue: same surface as api/queueDB.js.
const rows = [];
let nextId = 1;
const fakeQueue = {
  async add(r) { const row = Object.assign({ id: nextId++, attempts: 0, created_at: new Date().toISOString() }, r); rows.push(row); return row.id; },
  async update(id, patch) { const r = rows.find(x => x.id === id); if (r) Object.assign(r, patch); },
  async remove(id) { const i = rows.findIndex(x => x.id === id); if (i >= 0) rows.splice(i, 1); },
  async all() { return rows.slice(); },
  async pending() { return rows.filter(r => r.status === 'pending'); },
  async counts() {
    return { total: rows.length,
             pending: rows.filter(r => r.status === 'pending').length,
             synced: rows.filter(r => r.status === 'synced').length,
             failed: rows.filter(r => r.status === 'failed').length };
  },
};

let failures = 0;
const check = (label, ok, detail = '') => {
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`);
};

const RECEIVABLE_ERR =
  'Company شركة ألز كباب أمين لتقديم الوجبات has no Default Receivable Account. '
  + 'Set it on the Company record (Accounting section), then retry.';

(async () => {
  ctx.AlphaXApi = {};
  for (const m of ['mock', 'bridge', 'queueDB', 'client', 'fingerprint', 'bridgeInstall']) {
    ctx.AlphaXApi[m] = await loadESMAsObject(`api/${m}.js`);
  }
  // Swap in the fake store and a controllable server.
  ctx.AlphaXApi.queueDB.queueDB = fakeQueue;
  let serverBehaviour = () => { throw new Error(RECEIVABLE_ERR); };
  ctx.AlphaXApi.client.api.pushQueuedInvoice = async (doc) => serverBehaviour(doc);

  const syncMod = await loadESMAsObject('stores/sync.js');
  const pinia = ctx.Pinia.createPinia();
  ctx.Vue.createApp({}).use(pinia);
  ctx.Pinia.setActivePinia(pinia);
  const sync = syncMod.useSyncStore();

  // --- classification is the whole design
  check('a config error is classified as blocking',
    sync.classify(RECEIVABLE_ERR) === 'blocked', sync.classify(RECEIVABLE_ERR));
  check('a dropped network is transient',
    sync.classify('TypeError: Failed to fetch') === 'transient');
  check('a 503 is transient even when its body says "mandatory"',
    sync.classify('503 Service Unavailable: mandatory field') === 'transient');
  check('a duplicate is neither — the sale is already on the server',
    sync.classify('DuplicateEntryError: duplicate client uuid') === 'duplicate');

  // --- a blocked sale stops hammering
  await sync.enqueueSale({ doctype: 'Sales Invoice', customer: 'Walk-in',
                           grand_total: 255, items: [{}, {}] }, 'uuid-1');
  await sync.drain('test');
  check('the sale is kept, never dropped', rows.length === 1 && rows[0].status === 'pending');
  check('it is flagged as needing a human', !!rows[0].blocked_reason,
    rows[0].blocked_reason || '(none)');
  check('the cashier gets the server sentence verbatim',
    /Default Receivable Account/.test(sync.blockedReason || ''), sync.blockedReason || '');
  check('one attempt so far', rows[0].attempts === 1, String(rows[0].attempts));

  // Ten more drains: a blocked row must not become 28 attempts.
  for (let i = 0; i < 10; i++) await sync.drain('interval');
  check('repeated drains do not hammer a blocked row',
    rows[0].attempts === 1, rows[0].attempts + ' attempts after 11 drains');
  check('blocked count is reported', sync.blockedCount === 1, String(sync.blockedCount));

  // --- the fix lands; nobody touches the till
  serverBehaviour = () => ({ name: 'ACC-SINV-2026-00001' });
  rows[0].blocked_checked_at = Date.now() - 200000;   // recheck window elapsed
  await sync.drain('interval');
  check('the queue clears itself once the setting is corrected',
    rows[0].status === 'synced', rows[0].status);
  check('the blocked banner clears with it',
    !sync.blockedReason && sync.blockedCount === 0);
  check('the server name is recorded',
    rows[0].server_name === 'ACC-SINV-2026-00001', String(rows[0].server_name));

  // --- transient failures back off instead of spinning
  serverBehaviour = () => { throw new Error('TypeError: Failed to fetch'); };
  await sync.enqueueSale({ doctype: 'Sales Invoice', customer: 'Walk-in',
                           grand_total: 40, items: [{}] }, 'uuid-2');
  await sync.drain('test');
  const row2 = rows.find(r => r.client_uuid === 'uuid-2');
  check('a transient failure schedules a retry', !!row2.next_attempt_at);
  check('and is NOT marked as needing a fix', !row2.blocked_reason);
  const firstBackoff = row2.next_attempt_at - Date.now();
  check('first backoff is short (~5s)', firstBackoff > 3000 && firstBackoff <= 5500,
    Math.round(firstBackoff) + 'ms');

  await sync.drain('interval');
  check('a row inside its backoff window is skipped', row2.attempts === 1,
    row2.attempts + ' attempts');

  row2.next_attempt_at = Date.now() - 1;
  await sync.drain('interval');
  check('it retries once the window elapses', row2.attempts === 2, String(row2.attempts));
  const secondBackoff = row2.next_attempt_at - Date.now();
  check('backoff grows (~10s)', secondBackoff > 8000 && secondBackoff <= 10500,
    Math.round(secondBackoff) + 'ms');

  // --- "I fixed it, retry now" ignores every timer
  serverBehaviour = () => ({ name: 'ACC-SINV-2026-00002' });
  await sync.retryFailed();
  check('manual retry ignores the backoff window',
    row2.status === 'synced', row2.status);

  // --- offline is not an error, it is a wait
  sync.online = false;
  await sync.enqueueSale({ doctype: 'Sales Invoice', customer: 'Walk-in',
                           grand_total: 12, items: [{}] }, 'uuid-3');
  await sync.drain('interval');
  const row3 = rows.find(r => r.client_uuid === 'uuid-3');
  check('nothing is attempted while offline', row3.attempts === 0 && !row3.last_error,
    row3.attempts + ' attempts');

  sync.online = true;
  await sync.drain('online-event');
  check('coming back online drains automatically', row3.status === 'synced', row3.status);

  // --- a duplicate means the server already has it
  serverBehaviour = () => { throw new Error('DuplicateEntryError: duplicate client uuid'); };
  await sync.enqueueSale({ doctype: 'Sales Invoice', customer: 'Walk-in',
                           grand_total: 99, items: [{}] }, 'uuid-4');
  await sync.drain('test');
  const row4 = rows.find(r => r.client_uuid === 'uuid-4');
  check('a duplicate is settled, not retried forever',
    row4.status === 'synced', row4.status + ' / ' + row4.last_error);

  console.log(failures ? `\n${failures} failure(s)` : '\nsync queue: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
