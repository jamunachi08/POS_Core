# AlphaX POS Suite — v16.3.0

**Table (QR) ordering through to the kitchen, online pickup ordering, and one
Order Queue for both.**

## What was broken in QR ordering — read this first

Reviewing the existing QR flow found that it **had never worked end to end**:

1. **Every QR order failed.** `submit_qr_order` inserted an AlphaX POS Order
   without its required **terminal** and **customer**. Validation rejected
   it, the error was swallowed, and the guest saw "Order rejected".
2. **Even a successful order would have gone nowhere.** It set fields the
   order DocType does not have (`order_source`, `status`, `customer_name`),
   which Frappe silently drops, and nothing created kitchen tickets for it.
3. **Register sales never reached the KDS either.** The kitchen fan-out wrote
   item status **"New"** on KDS ticket rows, whose options are
   Queued / Preparing / Ready / Served / Cancelled. Frappe rejected every
   ticket, and the failure was caught and logged as "KOT fan-out failed".
   Any outlet with print stations enabled has had **no kitchen tickets from
   the till**. Check Error Log for that title to see how long.
4. Guests could order items switched off on the availability board.

All four are fixed. `scripts/health_check.py` gained a check that validates
every Select value in documents built in code (including child rows); run
against v16.2.0 it reports the KDS bug, so it cannot come back silently.

## Order Queue (desk page, process flow board → D2)

One board for table and online orders, in four columns — **New**, **In the
kitchen**, **Ready**, **Done / to pay** — with a sound and alert on arrival.

- **Send to kitchen** (with a ready-in time) creates kitchen tickets through
  the same station routing as till sales, carrying the order's short number
  (Q-017 for tables, W-017 for web) so the lobby screen and KDS can call it.
- When **every ticket** for an order is marked Ready on the KDS, the order
  turns Ready by itself. Outlets without KDS stations mark it ready here.
- **Served / Collected**, **Take payment** (posts a POS Sales Invoice for the
  outlet, tied to an open shift's terminal, with the order linked — the
  kitchen is **not** sent the order a second time), **Reject** and **Cancel**
  (cancels the order's open kitchen tickets) with a reason the guest sees.
- Late orders (past their ready-by time) turn red.

### Confirmation before cooking

Per outlet, **Send table (QR) orders straight to the kitchen** and **Send
online orders straight to the kitchen**. Both default to **off**: staff
confirm each order first, which stops prank and mistaken orders from reaching
the line.

## Table (QR) ordering

The existing QR page and table tokens keep working. Orders now book under the
outlet's till (one with an open shift if there is one), use the outlet price
list, refuse unavailable items, and the confirmation screen links to a live
tracking page.

## Online pickup ordering

Per outlet (AlphaX POS Outlet → *Online & QR ordering*):

- **Store link** `/shop/<name>`: mobile-first, Arabic/English, light and dark,
  menu by group, cart, name and mobile number, **pickup ASAP or a 15-minute
  slot**, note for the kitchen. Pay on collection.
- **Controls:** on/off, **pause now** (for a rush), earliest pickup lead time,
  **cap on open online orders** (new orders are refused at capacity), opening
  and closing time (windows past midnight handled), page message in both
  languages.
- **Abuse limits:** 5 orders per phone and 20 per IP per hour; server prices
  only; 50 lines and 99 per line at most.

## Guest tracking — `/track/<ref>`

Big order number, status steps (received → in the kitchen → ready → done),
ready-by time, items and total, refreshed every 10 seconds; vibrates on a
phone when the order turns ready. The reference is a 16-character random
value; the page shows no name or phone number.

## Changes to existing code

- `pos/kot_api.py`: the fan-out is now a shared `fan_out()` used by register
  invoices and queued orders. Fixed the item status, and a variable that
  shadowed the dine-in table with the routing table.
- `api.submit_qr_order` delegates to the queue (same response keys plus
  number, reference and tracking URL). `api.get_qr_menu` hides switched-off
  items.
- AlphaX POS Order: Source, Queue status, Number, Fulfilment, Guest name,
  Ready by, Guest reference, Guest note, Reject reason.
- AlphaX POS Outlet: online and QR ordering settings.

## Not in this release

- **Online payment.** Orders are paid on collection. A payment gateway
  (mada / Apple Pay via a KSA acquirer) is the natural next step and plugs
  into `ordering.public.place`.
- **SMS / WhatsApp** "your order is ready" — the tracking page covers it for
  now.

## Tests

`simulate_ordering.py` (trading hours including past midnight, phone
numbers, required fields set, statuses present, KDS fixes in place, every
guest endpoint bounded). All 19 simulations, `verify_tree.py` and the v16
health check pass. The Frappe side has not run on a live site: on staging,
place one QR order and one online order, send both to the kitchen, bump the
tickets on the KDS, and take payment.
