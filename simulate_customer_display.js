// Customer display board — announcement behaviour.
//
// Loads the real www/order_status page in jsdom with a stubbed board
// endpoint and a stubbed speech engine, then walks orders through the
// lanes and checks what gets said, when, and how often.

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const PAGE = path.join(__dirname,
  'alphax_pos_suite/www/order_status/index.html');

// Strip the Jinja wrappers the way the server would render them.
function render(vars) {
  let html = fs.readFileSync(PAGE, 'utf8');
  html = html.replace(/\{%\s*raw\s*%\}|\{%\s*endraw\s*%\}/g, '');
  for (const [k, v] of Object.entries(vars)) {
    html = html.replace(new RegExp('\\{\\{\\s*' + k + '\\s*\\}\\}', 'g'), v);
  }
  if (/\{\{|\{%/.test(html)) throw new Error('unrendered Jinja left in page');
  return html;
}

let failures = 0;
const check = (label, ok, detail = '') => {
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`);
};

const spoken = [];        // every utterance text, in order
let board = null;         // current fake payload

function payload(ready = [], preparing = [], packing = []) {
  const card = (id, label, elapsed = 60) => ({
    id, label, order: 'APOS-ORD-2026-' + label, elapsed,
    progress: 50, late: false, ready_on: null,
  });
  return {
    ok: true,
    server_time: '2026-08-02 22:30:00',
    outlet: { name: 'OUT-1', label: 'CashOutlet', branch: 'Riyadh' },
    lanes: {
      preparing: preparing.map((l, i) => card('P' + l, l, 90 + i)),
      packing: packing.map((l, i) => card('K' + l, l, 120 + i)),
      ready: ready.map((l, i) => card('R' + l, l, 30 + i)),
    },
    counts: {},
    announce: { enabled: true, repeat: 2 },
    ticker: { en: 'Buy 2 get 1 free', ar: 'اشتر ٢ واحصل على ١ مجاناً' },
    feedback_url: 'https://example.test/feedback',
  };
}

(async () => {
  const dom = new JSDOM(render({ outlet: 'OUT-1', display_key: 'KEY123', lang_mode: 'both' }), {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'https://site.test/order_status?outlet=OUT-1&key=KEY123',
    beforeParse(win) {
      // Stubbed board endpoint.
      win.fetch = async (url) => {
        if (!String(url).includes('display.api.board')) throw new Error('unexpected fetch ' + url);
        return { ok: true, json: async () => ({ message: board }) };
      };
      // Stubbed speech engine with both languages present.
      win.SpeechSynthesisUtterance = function (text) { this.text = text; };
      win.speechSynthesis = {
        getVoices: () => ([
          { lang: 'en-US', name: 'Stub EN', localService: true },
          { lang: 'ar-SA', name: 'Stub AR', localService: true },
        ]),
        // The blank priming utterance is engine warm-up, not a call.
        speak(u) { if (String(u.text).trim()) spoken.push(u.text); if (u.onend) setTimeout(u.onend, 0); },
        cancel() {},
      };
      // WebAudio is optional for the test; a missing constructor must not
      // break the page, which is itself worth asserting.
      win.AudioContext = undefined;
    },
  });

  const win = dom.window;
  const doc = win.document;
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const q = (id) => doc.getElementById(id);

  // --- first load: two orders already ready
  board = payload(['00063', '00064'], ['00076'], ['00079']);
  q('unlockBtn').dispatchEvent(new win.Event('click'));
  await wait(400);

  check('page renders without a WebAudio context', !!q('lane-ready'));
  check('lanes are populated from the payload',
    q('lane-ready').querySelectorAll('.card').length === 2,
    q('lane-ready').querySelectorAll('.card').length + ' ready cards');
  check('lane counters match', q('n-ready').textContent === '2'
    && q('n-preparing').textContent === '1' && q('n-packing').textContent === '1',
    `${q('n-preparing').textContent}/${q('n-packing').textContent}/${q('n-ready').textContent}`);
  check('outlet and branch reach the header',
    /RIYADH/.test(q('where').textContent), q('where').textContent);
  check('ticker shows both languages',
    q('tickerEn').textContent.length > 0 && q('tickerAr').textContent.length > 0);

  // The seeding rule: a screen that reboots must not shout eleven numbers.
  check('orders already ready on first load are NOT announced',
    spoken.length === 0, spoken.join(' | '));

  // --- a new order becomes ready
  spoken.length = 0;
  board = payload(['00063', '00064', '00087'], ['00076'], []);
  win.eval('void 0');
  await wait(7000);   // one poll cycle plus the chime delay and speech settle

  const en = spoken.filter(t => /ready for pickup/i.test(t));
  const ar = spoken.filter(t => /جاهز للاستلام/.test(t));
  check('a newly ready order is announced in English', en.length > 0, en[0] || '(none)');
  check('and in Arabic', ar.length > 0, ar[0] || '(none)');
  check('repeat=2 gives two calls per language',
    en.length === 2 && ar.length === 2, `${en.length} EN / ${ar.length} AR`);
  check('the number is spoken digit by digit, leading zeros dropped',
    /\b8 7\b/.test(en[0] || ''), en[0] || '(none)');
  check('only the new order is called, not the two already on screen',
    !en.some(t => /6 3|6 4/.test(t)), en.join(' | '));

  // --- the newly ready card is highlighted
  const pulsing = q('lane-ready').querySelectorAll('.card.justready');
  check('newly ready card pulses for late-looking guests', pulsing.length === 1,
    pulsing.length + ' pulsing');

  // --- sound off mutes everything
  spoken.length = 0;
  q('soundBtn').dispatchEvent(new win.Event('click'));
  board = payload(['00063', '00064', '00087', '00090'], [], []);
  await wait(7000);
  check('sound off silences announcements', spoken.length === 0, spoken.join(' | '));
  check('sound button reflects the muted state',
    /off|متوقف/i.test(q('soundBtn').textContent), q('soundBtn').textContent);

  // --- a re-fired number announces again after leaving the board
  q('soundBtn').dispatchEvent(new win.Event('click'));   // back on
  spoken.length = 0;
  board = payload([], [], []);
  await wait(4300);
  board = payload(['00087'], [], []);
  await wait(7000);
  check('a number that left the board can be called again',
    spoken.some(t => /8 7/.test(t)), spoken.join(' | ') || '(silent)');

  // --- empty board
  board = payload([], [], []);
  await wait(4300);
  check('empty lanes show the bilingual empty state',
    /No active orders/.test(q('lane-ready').textContent)
    && /لا توجد طلبات نشطة/.test(q('lane-ready').textContent));

  // --- server unreachable: last good board stays, banner flips
  board = null;
  win.fetch = async () => { throw new Error('ECONNREFUSED'); };
  await wait(13000);
  check('connection loss is surfaced after repeated failures',
    /Reconnect|إعادة/.test(q('connText').textContent), q('connText').textContent);

  dom.window.close();
  console.log(failures ? `\n${failures} failure(s)` : '\ncustomer display: all checks pass');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
