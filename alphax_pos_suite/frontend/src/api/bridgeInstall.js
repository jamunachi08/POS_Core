// AlphaX POS — "is the bridge on this machine, and if not, get it here."
//
// The existing api/bridge.js talks to a bridge we already know about.
// This module answers the earlier question: is there one at all?
//
// Detection strategy: race a HEAD-ish GET against every candidate port
// on both 127.0.0.1 and localhost, short timeout, first success wins.
// Both hostnames matter — some Windows builds resolve `localhost` to ::1
// only, and some corporate proxies swallow `localhost` but not the
// literal loopback address.

import { setBridgeURL, setBridgeToken, getBridgeURL } from './bridge'

const DEFAULT_PORTS = [8420, 8421, 8080]
const PROBE_TIMEOUT = 1200

async function probeOne(url, token = '') {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT)
  try {
    const headers = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(url, { signal: ctrl.signal, headers, mode: 'cors' })
    // 401 still proves a bridge is listening — it just wants a token.
    if (res.status === 401) {
      return { online: true, needs_token: true, url, status: 401 }
    }
    if (!res.ok) return null
    const body = await res.json()
    if (body?.name !== 'alphax-pos-bridge') return null
    return {
      online: true,
      needs_token: false,
      url,
      version: body.version || '',
      device_count: body.devices ?? 0,
      profile_count: body.profiles ?? 0,
      system: body.system || {},
      raw: body,
    }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Find a bridge. Returns:
 *   { online: true,  url, version, needs_token, system, devices[] }
 *   { online: false, probed: [urls] }
 */
export async function probeBridge({ ports = DEFAULT_PORTS, token = '' } = {}) {
  const candidates = []

  // Anything the cashier configured by hand wins the first look.
  const saved = getBridgeURL()
  if (saved) candidates.push(saved.replace(/\/+$/, '') + '/')

  for (const p of ports) {
    candidates.push(`http://127.0.0.1:${p}/`)
    candidates.push(`http://localhost:${p}/`)
  }

  const seen = new Set()
  const unique = candidates.filter(u => !seen.has(u) && seen.add(u))

  // Race them — a dead port fails fast, so this settles in ~1.2s worst case.
  const results = await Promise.all(unique.map(u => probeOne(u, token)))
  const hit = results.find(Boolean)

  if (!hit) return { online: false, probed: unique }

  setBridgeURL(hit.url.replace(/\/$/, ''))
  if (!hit.needs_token) {
    const devices = await listDevices(hit.url, token)
    return { ...hit, devices }
  }
  return { ...hit, devices: [] }
}

async function listDevices(baseUrl, token = '') {
  try {
    const headers = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(baseUrl.replace(/\/$/, '') + '/devices', { headers })
    if (!res.ok) return []
    const body = await res.json()
    return body.devices || []
  } catch {
    return []
  }
}

/** Verify a token the cashier just pasted (or that pairing handed us). */
export async function applyToken(token) {
  setBridgeToken(token)
  const r = await probeBridge({ token })
  return r
}

/**
 * Kick off a native installer download. We deliberately do NOT try to
 * execute anything — browsers can't, and pretending otherwise produces
 * a worse experience than an honest "download, double-click".
 *
 * The custom protocol attempt is the one shortcut that IS legitimate:
 * if a previous bridge version registered `alphaxbridge://`, the OS can
 * hand the install request straight to it (upgrade path, no download).
 */
export function launchInstaller(method, { onFallback } = {}) {
  if (method.id !== 'installer') return false

  // Try the protocol handler first — silent upgrade when one exists.
  let handled = false
  try {
    const t = setTimeout(() => { if (!handled) fallback() }, 1200)
    const onBlur = () => { handled = true; clearTimeout(t); window.removeEventListener('blur', onBlur) }
    window.addEventListener('blur', onBlur)
    window.location.href =
      `alphaxbridge://install?args=${encodeURIComponent(method.silent_args || '')}`
  } catch {
    fallback()
  }

  function fallback() {
    const a = document.createElement('a')
    a.href = method.download_url
    a.download = method.filename || ''
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    onFallback?.()
  }
  return true
}

/**
 * Poll for the bridge coming online while the cashier runs the installer.
 * Resolves the moment it answers, or after `maxMs`.
 */
export async function waitForBridge({ ports = DEFAULT_PORTS, intervalMs = 2500,
                                      maxMs = 10 * 60 * 1000, onTick } = {}) {
  const started = Date.now()
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const r = await probeBridge({ ports })
    if (r.online) return r
    const elapsed = Date.now() - started
    onTick?.(elapsed)
    if (elapsed > maxMs) return { online: false, timedOut: true }
    await new Promise(res => setTimeout(res, intervalMs))
  }
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Non-secure context (plain http on a shop LAN) — fall back.
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch {}
    ta.remove()
    return ok
  }
}
