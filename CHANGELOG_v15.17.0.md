# AlphaX POS Suite — v15.17.0

Answers two questions: **where does the cashier's item list come from**,
and **can the system fetch hardware on its own or from an IP**. Fixes a
pricing split found while answering the first, and builds the network
discovery the second needs.

---

## 1. Where the item list comes from

Neither POS Profile decides what the till sells.

```
Terminal ─► Outlet ─► Menus  (terminal menus REPLACE outlet menus)
                        │
                        ├─ menus assigned  → items = menu include rules − exclude rules
                        └─ no menu         → items = everything under the outlet's
                                             Domain Pack "default item group"
                                             └─ no group either → EVERY sellable,
                                                enabled, non-variant Item on the site
```

Source: `catalog/api.list_menu_items`.

**The two profiles do different jobs:**

| Document | Linked from | Decides |
|---|---|---|
| ERPNext **POS Profile** | Terminal → `pos_profile` | accounting defaults; now also the 3rd price-list fallback |
| **AlphaX POS Profile** | Terminal → Allowed POS Profiles | theme, payment methods, scale barcode rules |

Neither decides items. The ERPNext POS Profile's own *Item Groups* table
is not read by the AlphaX till.

**What the screenshot shows** is the last fallback: no menu on the outlet
and no domain item group, so the till lists every sellable item on the
site. Backpack, Camera, Laptop and T-shirt are ERPNext demo data; the two
Oral Examination lines come from `neo_dentiq`. To fix: create an
**AlphaX POS Menu**, add include rules for the item groups this outlet
sells, and link it on the outlet.

## 2. Why every price shows SAR 0.00

None of the price lists the till consulted had an Item Price for those
items, and their standard rate is 0.

### Fixed — tapped and scanned prices could differ

Three code paths priced items three different ways:

| Path | Before |
|---|---|
| Tapped on the grid | menu → outlet → standard rate |
| Scanned barcode | **ERPNext POS Profile** → outlet → Selling Settings |
| Invoice header | outlet |

On a site where the POS Profile says *Standard Selling* and the outlet
says *Retail KSA*, one item carried two prices depending on whether the
cashier tapped it or scanned it.

Now there is one chain, `catalog.api.price_list_chain`, used by the grid
and the scanner alike:

1. menu price lists, highest priority first
2. outlet default price list
3. ERPNext POS Profile selling price list
4. Selling Settings default
5. then standard rate, then 0 flagged `unpriced`

Step 3 is new for the grid: an item priced only on the POS Profile's list
no longer shows 0.00. `simulate_pricing.py` builds exactly the split site
above and asserts one price per item across both paths.

The scanner now reads the outlet **before** the POS Profile. On a site
where they differ, scanned items change price to match tapped ones. That
is the fix, but it is a visible change at the till.

`scan_barcode` accepts an optional `terminal` so terminal menu price
lists apply to scans too. The cashier SPA does not send it yet; until it
does, scans use the outlet's menus, which is correct for every till
without a terminal-level menu override.

### Visible on the board

**Setup & Install** gains two checks, run through the same
`catalog_diagnose` the register uses:

- **What the till sells** — flags the unscoped fallback with the reason.
- **Selling prices** — shows the price chain in force and how many items
  in scope would sell at 0.00.

---

## 3. Hardware: what can be fetched, from where

| Want | Possible? | How |
|---|---|---|
| This PC's hostname, UUID, MAC | Yes | Bridge on this PC, every heartbeat — already built |
| Printers on the shop LAN | **Yes, new** | Bridge on any PC in that LAN scans it |
| Another PC's hardware by its IP | Partly | Scan finds its bridge; that PC's full detail arrives through its own heartbeat |
| Server fetches from an IP | **No** | Frappe Cloud cannot route to 192.168.x.x |
| Browser fetches from an IP | **No** | No raw sockets; an HTTPS page may not call plain-HTTP LAN addresses |

The PC Identity and Hardware Bridge sections were blank because the bridge
has not been installed on that PC. Nothing needed building for them — the
**Download bridge** button from v15.16.0 is the fix.

### New — network discovery (AlphaX Bridge 15.6.0)

Bridge 15.5.3's `/discover` returned `"network": []`. It had no network
discovery at all. 15.6.0 adds it.

**Setup & Install → Scan network from this PC.** Enter a printer's IP, a
range like `192.168.1.0/24`, or leave blank for this PC's subnet.

The bridge probes each address and reports:

- **Printers** — anything on 9100 (raw), 515 (LPD) or 631 (IPP). Model
  from SNMP where the printer allows it, else its web page title. A
  matching bridge profile is suggested (TM-m30 → `epson-tm-m30`, unknown
  → `generic-network-escpos`).
- **Other AlphaX bridges** — matched to their terminal by hostname.
- **Other devices** — anything else that answered.
- MAC addresses from the ARP table, reverse DNS names.

Results are stored on the terminal (new collapsible **Network Discovery**
section) and each printer has **Use this printer**: the bridge registers
it as a network device, persisted across restarts, and the server creates
the matching **Print Station** with `bridge_target` set to that device —
which is what KOT routing reads.

**Must be run on a PC with the bridge installed**, usually the till itself.
The dialog says so plainly if the bridge does not answer, needs pairing,
or is older than 15.6.0.

### Safety, all tested

- Private, link-local and loopback addresses only. `8.8.8.8` and
  `1.1.1.0/24` are refused.
- At most 256 addresses per scan; `/23` and larger are refused.
- Port 9100 is connect-and-close. A live test with a fake printer on 9100
  confirms **zero bytes** are written to it — anything written there prints.
- SNMP is a read-only GET, hand-encoded, no new dependency.
- Scan and add routes require the bridge token.
- `GET /hello` is the only public route and returns exactly
  `{name, version, hostname}` — no UUID, MAC or device list.
- Adds `Access-Control-Allow-Private-Network: true`, which Chromium
  requires before an HTTPS page may call localhost.

---

## ⚠ Before the next bridge sync

The 15.6.0 kit vendored here was built from 15.5.3 plus the patch in
`bridge_patch/`. **Commit that patch to the `alphax-pos-bridge` repo and
tag v15.6.0 before running `scripts/sync_bridge_kit.ps1` again** — it
rebuilds from the bridge repo and would silently restore 15.5.3.

## verify_tree.py

New section 10, **bridge kit integrity**: kit present, SHA-256 and size
match the manifest, exactly one wheel at the manifest version, no stale
kits. The personalised installer checks the same hash at download time, so
a mismatch would fail every install on every till with "Download is
corrupt". Mutation-tested.

Section 9 now resolves six flow-page server calls, up from four.

## Files

```
catalog/api.py                               price_list_chain, rate_for, diagnose: chain + unpriced + scope
barcode/api.py                               scans use the shared chain; optional terminal
pos/flow_setup.py                            catalogue + pricing readiness; report_network_scan;
                                             create_print_station_from_scan
page/alphax_pos_flow/alphax_pos_flow.js      Scan network from this PC; results; Use this printer
onboarding/setup.py                          terminal Network Discovery fields; target version 15.6.0
public/bridge/AlphaX-POS-Bridge-Setup-15.6.0.zip   replaces 15.5.3
public/bridge/manifest.json                  15.6.0, new SHA-256
bridge_patch/                                bridge source change, for the bridge repo
simulate_pricing.py                          NEW
verify_tree.py                               section 10
alphax_pos_suite/__init__.py                 15.17.0
```

New custom fields on AlphaX POS Terminal arrive on migrate through the
existing `ensure_onboarding_fields` hook.
