# AlphaX POS Suite v15.9.4 — Items regression fix + browser repair endpoint

## Empty menu on v15.9.2/.3 (regression, fixed)
listItems requested an item_tax_template COLUMN from tabItem — on Item
that information lives in the "taxes" child table, not a column — so
the item query 1054'd and the register showed "No items in this
category". The item→template mapping now ships in the boot payload
(built server-side from the Item Tax child table); the item query is
back to known-good fields. Tax math (inclusive VAT, tobacco fee,
115 = 50 + 50 + 15) re-verified in the simulator.

## Repair without migrate
Migrate-dependent healing has failed twice in the field, so the heal
is now callable directly. As Administrator (or any System Manager),
open:

/api/method/alphax_pos_suite.alphax_pos_suite.setup_repair.repair_doctypes_now

It creates the missing dependency doctypes (children before parents:
Print Station, KOT Routing Rule, Combo Component, Notify Recipient,
Combo), force-reloads Outlet/Terminal/Shift/KDS Ticket, clears caches,
and returns JSON stating exactly what existed, what was created, and
what was reloaded. Idempotent — safe to run any number of times. Then
hard-refresh the desk and open the Outlet.

The before_migrate self-heal from 15.9.3 remains in place for future
migrates; this endpoint is the independent path that does not wait for
one.
