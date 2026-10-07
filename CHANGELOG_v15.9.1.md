# AlphaX POS Suite v15.9.1 — Handover shifts, audit register, v15.9 migrate fix

## Migrate fix (blocks v15.9.0 — deploy this instead)
"DocType AlphaX POS Notify Recipient not found": alphabetical doctype
sync validated AlphaX POS Combo's child-table link before the child
existed, migrate aborted, and later doctypes (incl. Notify Recipient)
were never created. New pre_model_sync patch imports children before
parents — same canonical pattern as v15.8.1.

## Shift handover (the Employee A → Employee C case)
Close-shift gains "Hand over the desk to another cashier": the
outgoing cashier counts the drawer (their accountability closes with
THEIR count), and the incoming cashier's shift opens instantly with
that exact amount as opening float, under their own login — an
unbroken cash chain of custody. Handover closes are flagged
is_handover and NEVER count toward "Auto: After N Shifts", and never
trigger day close: the trading day continues under the incoming
cashier. Chain fields (handed to / continues shift) recorded on both
shift documents.

## Audit: AlphaX POS Shift Register (script report)
The evidence view: one row per shift in a trading-day range — cashier,
open/close timestamps, opening float, counted cash, over/short,
handover chain (who → whom, which shift continues which), auto-closed-
at-store-hours flag, and the Day Close each shift rolled into.
Supervisor/Accounts roles. Day Close documents remain the consolidated
per-day audit record; the register answers "who was at the desk at
that time".

## Sales History dates
From/To default to the shift's TRADING day (business date) — "today"
means the trading day even at 12:40 AM. Clearing either widens the
range.

## Where the old Configuration screen went
Register-level Configuration was removed by design in v15.9.0
(backend-only config). Everything it edited lives in the desk single
doctype **AlphaX POS Settings** (search bar → "AlphaX POS Settings");
outlet-level options (store hours, notify recipients) on the AlphaX
POS Outlet document; terminal-level (day close trigger, business date)
on the AlphaX POS Terminal document.
