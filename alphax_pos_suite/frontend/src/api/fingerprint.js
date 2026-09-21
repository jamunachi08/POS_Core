// AlphaX POS — device identity, collected without asking the cashier
// anything.
//
// Three tiers, strongest first:
//
//   1. BRIDGE      — if the local daemon answers, it hands us the real
//                    hostname, machine UUID and MAC. Authoritative.
//   2. LOCAL UUID  — a random v4 we mint once and keep in localStorage.
//                    Survives reboots, dies if site data is cleared.
//   3. WEAK HINTS  — platform / screen / timezone / cores. Only ever used
//                    to help a human disambiguate, never to auto-bind.
//
// The server does the deciding. This file only gathers.

const UUID_KEY = 'alphax_device_uuid'

function uuid4() {
  if (crypto?.randomUUID) return crypto.randomUUID()
  // Fallback for older webviews on cheap Android tills.
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`
}

export function localDeviceUUID() {
  let v = null
  try { v = localStorage.getItem(UUID_KEY) } catch {}
  if (!v) {
    v = uuid4()
    try { localStorage.setItem(UUID_KEY, v) } catch {}
  }
  return v
}

/** Coarse OS string good enough to pick the right installer. */
export function detectOS() {
  const ua = navigator.userAgent || ''
  const plat = navigator.userAgentData?.platform || navigator.platform || ''
  const s = `${ua} ${plat}`.toLowerCase()
  if (/windows|win32|win64/.test(s)) return 'windows'
  if (/macintosh|mac os x/.test(s) && !/iphone|ipad/.test(s)) return 'macos'
  if (/ipad|iphone|ipod/.test(s)) return 'ios'
  if (/android/.test(s)) return 'android'
  if (/ubuntu|debian/.test(s)) return 'debian'
  if (/linux|x11|cros/.test(s)) return 'linux'
  return 'unknown'
}

export function isTablet() {
  const touch = (navigator.maxTouchPoints || 0) > 1
  const small = Math.min(screen.width, screen.height) < 900
  return touch && small
}

/** Everything the browser alone can tell us. */
export function browserHints() {
  let tz = ''
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch {}
  return {
    browser_uuid: localDeviceUUID(),
    platform: navigator.userAgentData?.platform || navigator.platform || '',
    os: detectOS(),
    screen: `${screen.width}x${screen.height}@${window.devicePixelRatio || 1}`,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    timezone: tz,
    language: navigator.language || '',
    cores: navigator.hardwareConcurrency || 0,
    device_memory: navigator.deviceMemory || 0,
    touch: (navigator.maxTouchPoints || 0) > 0,
    tablet: isTablet(),
    user_agent: (navigator.userAgent || '').slice(0, 255),
  }
}

/**
 * Merge browser hints with whatever the bridge reports.
 * `bridgeState` is the object returned by probeBridge() in bridgeInstall.js.
 */
export function collectHints(bridgeState = null) {
  const h = browserHints()
  if (bridgeState?.online) {
    const sys = bridgeState.system || {}
    h.bridge_hostname = sys.hostname || ''
    h.bridge_machine_uuid = sys.machine_uuid || sys.uuid || ''
    h.mac_address = sys.mac_address || sys.mac || ''
    h.bridge_version = bridgeState.version || ''
    h.bridge_os = sys.os || ''
  }
  return h
}
