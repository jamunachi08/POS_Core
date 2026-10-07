# AlphaX POS Suite v15.8.0 — KOT Station Routing + KDS v2 (Phase 1: Own the Floor)

Roadmap position: Phase 1 of the Top-5 strategy (AlphaX_POS_Top5_
Strategy.docx). With shift/cash management, business-date control, and
sales history already shipped in the v15.7.x run, this release closes
the kitchen leg.

## KOT Station Routing

- **AlphaX POS Print Station**: Juice Bar, Sandwich, Shawarma, Hot
  Kitchen… type Printer (prints via the local bridge) or Kitchen
  Display (appears on the KDS board). Per-outlet or global; one
  default station catches unmatched items so nothing silently drops.
- **AlphaX POS KOT Routing Rule**: Item Group → Station. Nearest
  ancestor wins (a rule on Hot Beverages beats one on Beverages for a
  cappuccino); outlet-specific rules beat global.
- **Fan-out**: one order splits into one ticket per station, each
  carrying only that station's lines.
- **Two transports by design**:
  - PAPER routes and prints CLIENT-SIDE at sale time from rules
    shipped in the boot payload — the shawarma station gets its ticket
    even with the internet down. Each Print Station names its bridge
    device; the shop's single bridge relays ESC/POS to each printer's
    LAN IP (the fan-out you asked about at the start of this session).
  - SCREEN tickets are created server-side on invoice submit (KDS +
    audit trail; business-date stamped) and pushed over realtime.
    Ticket creation can never block the sale.

## KDS v2

The 249-line v1 flat list becomes a station-bound board: each screen
binds to one Kitchen Display station and shows only its lines in three
lanes — New / Preparing / Ready — with tap-to-bump (Start → Ready →
Serve), realtime pushes, elapsed-time urgency colors (8m warn / 15m
late), lane counts, fullscreen mode, and optional new-ticket sound.
Runs on any tablet or wall screen logged into the desk.

## Setup (per shop)

1. Create Print Stations (type + bridge device name for printers).
2. Map Item Groups → Stations in KOT Routing Rules; mark one station
   default.
3. Register the printers in the local bridge under those device names.
4. For displays: open the Kitchen Display page on the station's
   screen, bind it once — it remembers.

Verified: client routing exercised in the simulator (ancestor-chain
resolution Coffee→Beverages→Juice Bar); both simulators fully green;
payload = tree = stamp.
