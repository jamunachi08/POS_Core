// Haptic feedback. Uses navigator.vibrate where supported (Android, some
// Linux tablets, kiosk hardware). Silently no-ops on iOS Safari and
// desktop. Honors a user toggle stored in localStorage.

const KEY = 'alphax_haptics_enabled'

export function isHapticsEnabled() {
  const v = localStorage.getItem(KEY)
  // default: enabled
  return v === null ? true : v === '1'
}

export function setHapticsEnabled(on) {
  localStorage.setItem(KEY, on ? '1' : '0')
}

function vibrate(pattern) {
  if (!isHapticsEnabled()) return
  if (typeof navigator === 'undefined' || !navigator.vibrate) return
  try { navigator.vibrate(pattern) } catch {}
}

export const haptics = {
  // Tap acknowledgment — used on every button-like interaction
  tap()        { vibrate(8) },
  // Successful action
  success()    { vibrate([10, 30, 10]) },
  // Mild warning / unavailable
  warn()       { vibrate(20) },
  // Error / rejected
  error()      { vibrate([40, 60, 40]) },
  // Long-press registered
  longPress()  { vibrate(15) },
}
