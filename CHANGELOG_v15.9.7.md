# AlphaX POS Suite v15.9.7 — Day close as a first-class action + full-schema repair

## Day close moved to the sidebar (owner decision — the right call)
Day close is a TERMINAL-day operation, not a property of any one
shift's Z panel (which goes read-only after Done, stranding the
button). New sidebar action "Day close" (🌙), visible to supervisors
only (boot.is_manager; server enforces the role independently):
confirm dialog showing the trading day and an open-shift warning →
runs the close → displays day totals + shift-wise lines (cashier, net,
over/short) → notifies nominated persons. The Z-panel button is gone.

## Day close 1054 ('parent' in WHERE)
Static schema audit of every query in the close path found no code
mismatch — the failure is site-side schema drift from the failed
migrates (same root as the Notify Recipient saga). The repair endpoint
is upgraded from "five doctypes" to FULL-SCHEMA: it now force-reloads
EVERY doctype in the app, children before parents — the browser-
callable equivalent of a successful migrate. Run as Administrator:

/api/method/alphax_pos_suite.alphax_pos_suite.setup_repair.repair_doctypes_now

then hard-refresh the desk. It returns JSON listing created, reloaded,
and reload_failed. After it runs clean, day close will post.
