# AlphaX POS Bridge 15.6.0 — source patch

These five files are the complete change from bridge **v15.5.3** to
**v15.6.0**. The rebuilt wheel and kit are already vendored in
`alphax_pos_suite/public/bridge/`, so this POS build ships 15.6.0 today.

**Commit these to the `alphax-pos-bridge` repo and tag `v15.6.0` before
the next run of `scripts/sync_bridge_kit.ps1`.** That script rebuilds the
kit from the bridge repo; run it against an unpatched repo and it silently
puts 15.5.3 back, taking network discovery with it.

| File | Change |
|---|---|
| `alphax_bridge/netscan.py` | NEW. LAN scan: single IP, CIDR up to /24, or this PC's /24. TCP connect probes on 9100/515/631/8420/80/443, SNMP v1 GET (sysDescr, sysName, hrDeviceDescr) hand-encoded, HTTP title, reverse DNS, MAC from the ARP table. |
| `alphax_bridge/netdevices.py` | NEW. Adds a discovered network printer to the live registry and persists it to `~/.alphax-bridge/network-devices.json`. |
| `alphax_bridge/server.py` | `GET /hello` (public, name/version/hostname only), `GET /discover/network`, `POST /devices/network`, `Access-Control-Allow-Private-Network` CORS header. |
| `alphax_bridge/__main__.py` | Loads `network-devices.json` at startup, after the main config. |
| `alphax_bridge/__init__.py` | Version 15.6.0. |

No new dependencies. Stdlib only.

## Safety properties, all tested

- Private, link-local and loopback addresses only; public ranges refused.
- At most 256 addresses per scan.
- Port 9100 is connect-and-close; zero bytes are ever written to a printer.
- SNMP is a read-only GET.
- `/discover/network` and `/devices/network` require the bridge token.
- `/hello` is the only unauthenticated route and returns three fields.
