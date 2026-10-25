// useBarcodeScanner — global keyboard-wedge listener.
//
// Virtually every USB / Bluetooth retail barcode scanner behaves as a HID
// keyboard: it "types" the barcode digits very fast and finishes with Enter.
// We exploit that — no driver, no serial port, no permissions needed.
//
// Heuristic: characters arriving faster than `maxIntervalMs` apart are
// treated as scanner input (humans can't type that fast). A terminating
// Enter (or a timeout) flushes the buffer to `onScan(code)`. We ignore the
// stream entirely when the user is typing into a normal text input, so the
// search box and dialogs keep working.
//
// Usage (in App.vue / CashierView.vue setup):
//   import { useBarcodeScanner } from '../composables/useBarcodeScanner'
//   useBarcodeScanner((code) => pos.scan(code))

import { onMounted, onBeforeUnmount } from 'vue'

export function useBarcodeScanner(onScan, opts = {}) {
  const minLength = opts.minLength ?? 3
  const maxIntervalMs = opts.maxIntervalMs ?? 35   // gap between keystrokes
  const flushMs = opts.flushMs ?? 120              // idle before auto-flush

  let buffer = ''
  let lastTime = 0
  let flushTimer = null

  function isTypingTarget(el) {
    if (!el) return false
    const tag = (el.tagName || '').toUpperCase()
    return (
      tag === 'INPUT' ||
      tag === 'TEXTAREA' ||
      tag === 'SELECT' ||
      el.isContentEditable === true
    )
  }

  function reset() {
    buffer = ''
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
  }

  function flush() {
    const code = buffer.trim()
    reset()
    if (code.length >= minLength && typeof onScan === 'function') {
      onScan(code)
    }
  }

  function onKeydown(e) {
    // Let the cashier type normally into fields; scanners aimed at a focused
    // input will still deliver there, which is fine.
    if (isTypingTarget(e.target)) return

    const now = Date.now()
    const gap = now - lastTime
    lastTime = now

    if (e.key === 'Enter') {
      if (buffer.length >= minLength) {
        e.preventDefault()
        flush()
      } else {
        reset()
      }
      return
    }

    // Only printable single chars are part of a barcode.
    if (e.key.length !== 1) return

    // A slow keystroke means a human, not a scanner — restart the buffer.
    if (buffer && gap > maxIntervalMs) buffer = ''

    buffer += e.key

    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = setTimeout(flush, flushMs)
  }

  onMounted(() => window.addEventListener('keydown', onKeydown, true))
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKeydown, true)
    reset()
  })
}
