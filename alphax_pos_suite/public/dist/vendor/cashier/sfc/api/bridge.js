// AlphaX POS Bridge client.
//
// Talks to the local bridge daemon (default http://localhost:8420).
// Falls back gracefully if the bridge isn't running — the SPA still
// works, it just can't drive hardware.

const STORAGE = {
  url:   'alphax_bridge_url',
  token: 'alphax_bridge_token',
}

export function getBridgeURL() {
  return localStorage.getItem(STORAGE.url) || 'http://localhost:8420'
}
export function setBridgeURL(v) {
  if (v) localStorage.setItem(STORAGE.url, v)
  else   localStorage.removeItem(STORAGE.url)
}
export function getBridgeToken() {
  return localStorage.getItem(STORAGE.token) || ''
}
export function setBridgeToken(v) {
  if (v) localStorage.setItem(STORAGE.token, v)
  else   localStorage.removeItem(STORAGE.token)
}

async function call(path, { method = 'GET', body = null, timeout = 4000 } = {}) {
  const url = getBridgeURL().replace(/\/+$/, '') + path
  const token = getBridgeToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  try {
    const res = await fetch(url, {
      method, headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
    if (!res.ok) {
      let detail = ''
      try { detail = (await res.json()).error || '' } catch {}
      throw new Error(`bridge ${res.status}: ${detail || res.statusText}`)
    }
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

export const bridge = {
  status:       ()              => call('/'),
  listDevices:  ()              => call('/devices'),
  listProfiles: ()              => call('/profiles'),
  discover:     ()              => call('/discover', { timeout: 8000 }),

  print:    (device, receipt)   => call('/print',   { method: 'POST', body: { device, receipt }, timeout: 12000 }),
  drawer:   (device, pin = 0)   => call('/drawer',  { method: 'POST', body: { device, pin } }),
  display:  (device, payload)   => call('/display', { method: 'POST', body: { device, ...payload } }),
  scale:    (device, timeout=2) => call(`/scale?device=${encodeURIComponent(device)}&timeout=${timeout}`,
                                        { timeout: (timeout + 1) * 1000 }),

  testPrint:   (device) => call('/test', { method: 'POST', body: { device, action: 'print'   } }),
  testKick:    (device) => call('/test', { method: 'POST', body: { device, action: 'kick'    } }),
  testDisplay: (device) => call('/test', { method: 'POST', body: { device, action: 'display' } }),
  testWeight:  (device) => call('/test', { method: 'POST', body: { device, action: 'weight'  } }),

  // Card terminal operations. The bridge waits for the customer to tap /
  // insert / swipe, so the timeout here is long.
  charge: (device, body) => call('/charge', {
    method: 'POST',
    body:   { device, ...body },
    timeout: ((body?.timeout || 90) + 5) * 1000,
  }),
  refund: (device, body) => call('/refund', {
    method: 'POST',
    body:   { device, ...body },
    timeout: 30000,
  }),
  terminalCancel: (device, current_txn_id) => call('/cancel', {
    method: 'POST',
    body:   { device, current_txn_id },
    timeout: 10000,
  }),
}
