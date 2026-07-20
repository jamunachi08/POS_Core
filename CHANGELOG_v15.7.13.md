# AlphaX POS Suite v15.7.13 — Sales History (view-only) with reprint

## What it is

A read-only Invoice Management view inside the register, opened from a
new "Sales history" sidebar button: tabs for History / Unpaid / Drafts /
Returns with live counts, KPI strip (invoices, gross, tendered, change
returned, outstanding), search by invoice no. or customer, date-range
filter, and a "Print copy" button on every invoice for verification
reprints. Fully localized EN/AR.

## Permission model — view-only by construction

- Two new server endpoints (pos/history_api.py), both READ-ONLY —
  there is deliberately no mutation surface: cashiers verify and
  reprint, nothing else. Even a modified client cannot edit, void, or
  return through this API.
- Listing requires read permission on Sales Invoice and throws a
  fix-it message when missing (same pattern as the terminal picker).
- Scope is the TERMINAL, not the user — after a shift handover the
  next cashier must be able to verify the previous cashier's sales on
  the same till.

## Reprint

- Receipt data is rebuilt SERVER-SIDE from the document (items, tax
  breakdown, payments), so reprints are correct even for invoices
  created before the register was last reloaded.
- Prints via the hardware bridge when connected; falls back to an
  80mm-styled browser print when the bridge is offline.
- Every copy is marked "REPRINT — duplicate copy" in the footer: a
  duplicate must be distinguishable from the original for audit (and
  ZATCA hygiene).

Both simulators green, including a new click-through of the history
modal (open → tabs/counts → KPI strip → cards → reprint button).
Payload = tree = stamp verified.
