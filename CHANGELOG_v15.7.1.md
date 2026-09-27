# AlphaX POS Suite v15.7.1 — Phase 1: Shift & Cash Management

First Phase-1 roadmap item shipped: complete drawer discipline at the
till, matching the incumbents' shift workflow.

## New

- **Open shift** — declared opening float; one open shift per
  terminal enforced server-side. Sidebar chip shows live shift state.
- **Cash in / out during shift** — Paid In, Paid Out, Petty Cash
  Expense, Cash Drop To Safe. Movements that take cash OUT of the
  drawer are manager-PIN gated (same policy switch as voids).
- **X report** — mid-shift read: sales/returns/credit counts, totals
  by mode of payment, cash movements, live expected cash. Print any
  time; never resets.
- **Z report (blind close)** — the cashier declares the counted cash
  BEFORE the expected figure is revealed; over/short (variance) is
  computed server-side and stored on the shift. Printable 80mm layout.
- **Day close** — rolls the date's closed shifts into an AlphaX POS
  Day Close with per-shift variances and a day total; emailed close
  reports reuse the existing close_reports pipeline.
- **Credit sales bucket** — credit invoices count as shift revenue but
  never as drawer cash; reported separately on X/Z.
- **Sales Invoice terminal stamp** (`alphax_pos_terminal` custom
  field) — every register sale is now attributable to its terminal,
  making multi-terminal shift math exact (legacy unstamped invoices
  fall back to cashier + time-window matching).
- **Require-shift enforcement** — with `require_shift_open` on, the
  Pay button routes to the open-shift dialog until a shift exists.

## Backend

New `pos/shift_api.py`: `get_shift_state`, `open_shift`,
`record_cash_movement`, `x_report`, `close_shift`, `day_close` —
source-aware (Sales Invoice or AlphaX POS Order pipelines).

## Verification

- Server math unit-tested with stubbed frappe: double-open guard,
  negative-amount guard, expected cash 500+100−30=570, blind variance
  −5, MOP split incl. card.
- Full jsdom lifecycle: open → sale → paid-out → X → blind close →
  day close, all figures exact; all prior regression checks pass.
- Schema audit clean (it caught and removed a SQL literal alias in
  this very feature during development).
