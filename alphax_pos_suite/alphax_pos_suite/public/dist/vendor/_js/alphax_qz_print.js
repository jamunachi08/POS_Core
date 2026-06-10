/*
 * AlphaX POS — qz-tray client wrapper (v15.5.16).
 *
 * Provides a single window.AlphaXPrint API that hides qz-tray's setup
 * complexity. The Classic cashier calls AlphaXPrint.printReceipt(...)
 * and this module decides:
 *
 *   - If qz-tray daemon is reachable: send ESC/POS directly to thermal
 *     printer over WebSocket. No browser dialog, instant print.
 *   - If qz-tray is unavailable: fall back to the browser's print dialog
 *     using window.print() on an iframe with the rendered HTML.
 *
 * qz-tray (https://qz.io) is a free-for-personal-use cross-platform daemon
 * that ships an installer (.msi, .pkg, .deb). The merchant installs it once
 * per cashier PC. After that, this wrapper handles everything.
 *
 * Loading model: qz.js is fetched from cdnjs on first call (lazy). If the
 * CDN is unreachable AND no daemon is installed, we silently degrade to
 * browser print — never block the cashier.
 *
 * Public API (attached to window.AlphaXPrint):
 *
 *   await AlphaXPrint.ensureLoaded()
 *       Lazy-loads the qz.js library if not present.
 *
 *   await AlphaXPrint.isAvailable()
 *       Returns true if the local qz-tray daemon answered. Use this to
 *       decide whether to show 'qz-tray status: connected' in your UI.
 *
 *   await AlphaXPrint.listPrinters()
 *       Returns an array of printer names the daemon can see.
 *
 *   await AlphaXPrint.printReceipt(opts)
 *       opts = {
 *         html: string,           // full HTML to render (for browser dialog)
 *         escposLines: string[],  // raw ESC/POS text lines for qz-tray
 *         printerName: string,    // OS printer name (for qz-tray)
 *         autoCut: boolean,
 *         openDrawer: boolean,
 *         encoding: 'UTF-8' | 'CP437' | 'Windows-1256' | ...,
 *         charsPerLine: number,
 *       }
 *       Resolves when printing is dispatched (not necessarily complete).
 *       Throws on hard error (config missing); falls back silently to
 *       browser dialog if qz-tray is down.
 *
 *   AlphaXPrint.escposHelpers
 *       Small toolkit for building ESC/POS sequences:
 *         .text(s)
 *         .bold(s)
 *         .center(s)
 *         .line() — fills a divider line
 *         .feed(n)
 *         .cut()
 *         .kickDrawer()
 */
(function() {
  'use strict';

  // qz.js CDN — using jsdelivr because Frappe Cloud allows that origin
  const QZ_CDN = 'https://cdn.jsdelivr.net/npm/qz-tray@2.2.5/qz-tray.js';

  // ESC/POS control bytes (constants)
  const ESC = '\x1B';
  const GS = '\x1D';
  const ESCPOS = {
    INIT:      ESC + '@',
    BOLD_ON:   ESC + 'E\x01',
    BOLD_OFF:  ESC + 'E\x00',
    ALIGN_LEFT:    ESC + 'a\x00',
    ALIGN_CENTER:  ESC + 'a\x01',
    ALIGN_RIGHT:   ESC + 'a\x02',
    CUT_FULL:  GS  + 'V\x00',
    CUT_PART:  GS  + 'V\x01',
    DRAWER_KICK: ESC + 'p\x00\x32\xFA',  // pin 2, 50ms on, 250ms off
  };

  // State
  let qzLoaded = false;
  let qzLoadPromise = null;
  let qzConnected = false;

  // --- Load qz.js from CDN (lazy, idempotent) ---
  function loadQzScript() {
    if (qzLoaded) return Promise.resolve();
    if (qzLoadPromise) return qzLoadPromise;
    qzLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = QZ_CDN;
      script.async = true;
      script.onload = () => { qzLoaded = true; resolve(); };
      script.onerror = () => {
        qzLoadPromise = null;  // allow retry
        reject(new Error('Failed to load qz-tray library from CDN.'));
      };
      document.head.appendChild(script);
    });
    return qzLoadPromise;
  }

  // --- Connect to local qz-tray daemon ---
  async function ensureConnected() {
    if (typeof window.qz === 'undefined') {
      await loadQzScript();
    }
    if (qzConnected && window.qz.websocket.isActive()) return true;

    // qz-tray uses a self-signed certificate by default. For production,
    // merchants must install a real cert. For Beta, we accept the
    // self-signed cert (qz-tray's UI explains this to the merchant on first run).
    try {
      window.qz.api.setPromiseType(promise => promise);  // we use native Promises
      window.qz.api.setSha256Type(data => {
        // Use a no-op signature (qz-tray Community edition: this means
        // it pops a permission dialog on first connect, which is fine).
        return '';
      });
      await window.qz.websocket.connect({
        retries: 1,
        delay: 1,
      });
      qzConnected = true;
      return true;
    } catch (e) {
      qzConnected = false;
      // Don't throw - this is "qz-tray unavailable" not "fatal error"
      return false;
    }
  }

  // --- List printers ---
  async function listPrinters() {
    const ok = await ensureConnected();
    if (!ok) return [];
    try {
      const printers = await window.qz.printers.find();
      return Array.isArray(printers) ? printers : [printers];
    } catch (e) {
      return [];
    }
  }

  // --- Print via qz-tray ---
  async function printViaQz(opts) {
    const ok = await ensureConnected();
    if (!ok) throw new Error('qz-tray daemon not reachable');
    if (!opts.printerName) throw new Error('printerName is required for qz-tray');

    const config = window.qz.configs.create(opts.printerName, {
      encoding: opts.encoding || 'UTF-8',
    });

    // Build the ESC/POS data
    let body = ESCPOS.INIT;
    if (opts.escposLines && opts.escposLines.length){
      body += opts.escposLines.join('\n') + '\n';
    } else if (opts.html){
      // qz-tray supports HTML rendering for thermal printers too
      // but ESC/POS direct is cleaner — fall back to HTML print if escpos not provided
      body = opts.html;
    }
    if (opts.autoCut) body += ESCPOS.CUT_PART;
    if (opts.openDrawer) body += ESCPOS.DRAWER_KICK;

    const data = [
      { type: 'raw', format: 'plain', data: body }
    ];
    await window.qz.print(config, data);
  }

  // --- Print via browser dialog (fallback) ---
  function printViaBrowser(opts) {
    return new Promise((resolve) => {
      const html = opts.html || (opts.escposLines || []).join('<br>');
      const iframe = document.createElement('iframe');
      iframe.style.position = 'fixed';
      iframe.style.left = '-10000px';
      iframe.style.top = '-10000px';
      iframe.style.width = '0';
      iframe.style.height = '0';
      iframe.style.border = '0';
      document.body.appendChild(iframe);

      iframe.contentDocument.open();
      iframe.contentDocument.write(`
        <!DOCTYPE html>
        <html><head><title>Receipt</title>
        <style>
          body { font-family: 'Courier New', monospace; font-size: 11px; margin: 8px; }
          pre { white-space: pre-wrap; }
        </style>
        </head><body>${html}</body></html>
      `);
      iframe.contentDocument.close();

      // Trigger print, then clean up
      setTimeout(() => {
        try {
          iframe.contentWindow.focus();
          iframe.contentWindow.print();
        } catch(e){ console.error('Print dialog failed', e); }
        setTimeout(() => {
          document.body.removeChild(iframe);
          resolve();
        }, 1000);
      }, 200);
    });
  }

  // --- Public API ---
  window.AlphaXPrint = {
    async ensureLoaded() {
      try {
        await loadQzScript();
        return true;
      } catch(e){
        return false;
      }
    },

    async isAvailable() {
      try {
        return await ensureConnected();
      } catch(e){
        return false;
      }
    },

    async listPrinters() {
      return await listPrinters();
    },

    async printReceipt(opts) {
      opts = opts || {};
      // Decide: qz-tray if available + printerName provided, else browser
      if (opts.printerName){
        try {
          await printViaQz(opts);
          return { ok: true, transport: 'qz-tray' };
        } catch (e) {
          // qz-tray failed — fall back to browser
          console.warn('AlphaXPrint: qz-tray failed, falling back to browser dialog:', e);
        }
      }
      // Browser fallback
      await printViaBrowser(opts);
      return { ok: true, transport: 'browser' };
    },

    escposHelpers: {
      text: (s) => s,
      bold: (s) => ESCPOS.BOLD_ON + s + ESCPOS.BOLD_OFF,
      center: (s) => ESCPOS.ALIGN_CENTER + s + ESCPOS.ALIGN_LEFT,
      right: (s) => ESCPOS.ALIGN_RIGHT + s + ESCPOS.ALIGN_LEFT,
      line: (char, n) => (char || '-').repeat(n || 42),
      feed: (n) => '\n'.repeat(n || 1),
      cut: () => ESCPOS.CUT_PART,
      kickDrawer: () => ESCPOS.DRAWER_KICK,
      init: () => ESCPOS.INIT,
    },
  };

  // Log on load
  if (window.console && console.info) {
    console.info('AlphaXPrint loaded. Call AlphaXPrint.isAvailable() to check qz-tray status.');
  }
})();
