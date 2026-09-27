# AlphaX POS Suite v15.7.11 — Business Date (trading day) control

## The problem

Restaurants trade past midnight; 24h sites run three shifts against one
day. Until now every sale posted on the server clock's calendar date,
so a 12:30 AM sale landed on the "next" day, day close matched shifts
by a midnight-to-midnight window (splitting an overnight shift across
two days), and nobody could say with certainty which date a document
would post on.

## The model

**The trading day rolls at Day Close, not at midnight.**

- `AlphaX POS Terminal.current_business_date` — the trading day
  currently open on the terminal. Set when the first shift opens,
  carried across midnight and across any number of shifts, cleared by
  Day Close. Managers can correct it on the Terminal doc if a close
  was missed.
- `AlphaX POS Shift.business_date` — stamped at shift open from the
  terminal (in list view + standard filter).
- **Every sale posts on the shift's trading day**: the SPA stamps
  `posting_date` + `set_posting_time` on the invoice payload AT SALE
  TIME — so an offline sale queued at 12:30 AM keeps yesterday's
  trading day even if it syncs after day close. Server-side, the
  before_insert hook forces `set_posting_time` for all register
  invoices and back-fills the date from the terminal for older SPAs.
  GL, stock, VAT, and ZATCA all follow posting_date, so the whole
  paper trail lands on the right day.
- **Day Close** now selects shifts by `business_date` (legacy shifts
  without one fall back to the old calendar window so historic days
  remain closable), defaults its posting date to the terminal's open
  trading day, and clears the terminal's date on success — the next
  shift open starts a fresh day. Naturally correct for: close at 1 AM
  (previous day's trade), 24h × 3 shifts (all one date), closed-Friday
  gaps (next open simply starts Saturday).

## UI

- Sidebar: a trading-day chip under the shift status — visible even in
  rail mode via tooltip, in the accent color, because after midnight it
  *intentionally* differs from the wall calendar and the cashier should
  see that, not be surprised by it.
- Shift-open dialog: "This shift opens under trading day 2026-07-12 ·
  carried over until day close" — the cashier knows the date before
  committing the float.
- EN/AR localized.

## Plumbing

- Boot payload carries `terminal.business_date`; shift summaries carry
  `business_date`; the boot cache is invalidated on shift open and day
  close so registers never reload into a stale trading day.

Payload = tree = stamp verified. Both simulators green.
