// Kiosk mode.
//
// Sets the page into "POS terminal mode":
//   - requests browser fullscreen (where supported)
//   - prevents context-menus that could navigate away
//   - optional 4-digit PIN to exit
//
// We can't fully prevent a determined user with hardware keys, but we can
// remove the obvious foot-guns (swipe-back, F5, browser chrome).

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const PIN_KEY = 'alphax_kiosk_pin'
const ON_KEY  = 'alphax_kiosk_on'

export const useKioskStore = defineStore('kiosk', () => {

  const on = ref(localStorage.getItem(ON_KEY) === '1')
  const pin = ref(localStorage.getItem(PIN_KEY) || '')
  const showExitPrompt = ref(false)

  const hasPin = computed(() => pin.value.length >= 4)

  function setPin(value) {
    pin.value = String(value || '').replace(/\D/g, '')
    if (pin.value) localStorage.setItem(PIN_KEY, pin.value)
    else           localStorage.removeItem(PIN_KEY)
  }

  async function enable() {
    on.value = true
    localStorage.setItem(ON_KEY, '1')
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen()
      }
    } catch {}
    document.body.classList.add('alphax-kiosk-on')
  }

  async function tryDisable(enteredPin) {
    if (hasPin.value && enteredPin !== pin.value) return false
    on.value = false
    localStorage.setItem(ON_KEY, '0')
    try { if (document.fullscreenElement) await document.exitFullscreen() } catch {}
    document.body.classList.remove('alphax-kiosk-on')
    showExitPrompt.value = false
    return true
  }

  function requestExit() { showExitPrompt.value = true }
  function cancelExit()  { showExitPrompt.value = false }

  // Block obvious browser shortcuts in kiosk mode.
  function installGuards() {
    if (typeof window === 'undefined') return
    window.addEventListener('keydown', (e) => {
      if (!on.value) return
      // F5 reload, Ctrl-R, Ctrl-W, Alt-F4, Ctrl+Shift+I devtools
      if (
        e.key === 'F5' ||
        (e.ctrlKey && (e.key === 'r' || e.key === 'R' || e.key === 'w' || e.key === 'W')) ||
        (e.ctrlKey && e.shiftKey && (e.key === 'i' || e.key === 'I'))
      ) {
        e.preventDefault()
      }
    })
    // Disable context-menu in kiosk mode (long-press uses its own handler that
    // already preventDefaults; this just keeps the OS context menu away).
    document.addEventListener('contextmenu', (e) => {
      if (on.value) e.preventDefault()
    })
    // Swallow back gesture / before-unload prompt
    window.addEventListener('beforeunload', (e) => {
      if (on.value) {
        e.preventDefault()
        e.returnValue = ''
      }
    })
    // If the page becomes visible again and kiosk was on, re-enter fullscreen
    document.addEventListener('visibilitychange', () => {
      if (on.value && !document.hidden && !document.fullscreenElement) {
        document.documentElement.requestFullscreen?.().catch(() => {})
      }
    })
  }

  return {
    on, pin, hasPin, showExitPrompt,
    enable, tryDisable, setPin,
    requestExit, cancelExit,
    installGuards,
  }
})
