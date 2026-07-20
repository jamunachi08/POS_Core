# AlphaX POS Suite v15.9.0 — Cash Discipline + Combos (Phase 1: Own the Floor)

## Blind shift close
Cashiers count the drawer and close — nothing else. The server strips
net sales, expected cash, by-mode totals, and variance from every
summary for non-supervisors (UI hiding alone would be decoration);
X report is supervisor-only server-side; the Sales History KPI strip
is supervisor-only. Cashiers keep item history and reprint.

## Day close ownership — single choice, mutually exclusive
Terminal → Day Close Trigger:
- Manual (Supervisor) — server-enforced role gate
- Auto: After N Shifts — Nth closed shift of the trading day closes it
- Auto: At Closing Time — follows store-hours enforcement
Manual supervisor close remains available in every mode. The day-close
response carries shift-wise summaries for the printed report, and both
closes notify nominated persons.

## Store hours
On the outlet: opening/closing times, each independently enforceable.
Opening: shifts cannot open earlier. Closing: the scheduler (every 5
min) auto-closes still-open shifts after the grace period using float +
recorded movements as the declared count, flagged "RECOUNT REQUIRED" —
the system never invents a counted figure and never kills a sale in
progress.

## Close notifications
Nominated persons (outlet child table): per-person channel (Email /
WhatsApp / SMS) and event (shift close / day close). Email native;
WhatsApp/SMS through a configurable gateway URL with {phone}/{message}
placeholders — Unifonic, Twilio, or any WhatsApp Business relay plugs
in without code.

## Combos
- AlphaX POS Combo: billing item (carries price + tax), Fixed or
  Customizable, per-component substitution within an Item Group, with
  optional charge-difference (never a discount for cheaper swaps).
- Register: combo cards above the grid; Fixed adds as-is (no editing
  surface); Customizable opens the picker with defaults preselected.
- Billing: ONE priced line on the billing item + components at zero
  rate (stock moves, VAT on the parent) — receipt shows the combo with
  components indented, substitutions marked ⇄.
- KOT: components explode to their OWN stations tagged "COMBO: <name>"
  — burger to the hot kitchen, drink to the juice bar, and the priced
  parent never reaches a kitchen. Verified in the simulator.

## Register cleanup
Configuration button removed from the sales screen — business
configuration lives in the desk. Hardware (device mapping) stays: it is
terminal-local by nature.

All simulators green (17 assertions incl. combo billing + routing).
Payload = tree = stamp verified.
