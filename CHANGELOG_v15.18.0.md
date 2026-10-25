# AlphaX POS Suite — v15.18.0

Front-of-house planning for F&B: reservations, a table timeline, and a
branded bilingual till login. Design rationale in
**AlphaX-FOH-Enhancement-Plan-v1.0**.

All original AlphaX work, written against AlphaX doctypes. No third-party
code, schema, markup or assets are used anywhere in this release.

## New — Table Timeline

`/app/alphax-table-timeline`, with a workspace shortcut and a flow-board
node in stage B2.

Tables down the side, the service day across the top in hours, every
reservation and every live walk-in session drawn as a bar. The axis is
hours rather than days because a restaurant turns the same table three or
four times in one service, and the scarce resource is covers per hour, not
the table itself.

On the board:

- **Covers line** — per half hour, covers held against seats available.
  Turns red when the service is oversold. The yield line for a dining room.
- **Turnaround conflicts** — two parties on one table with less than the
  outlet's reset time between them, flagged with the gap and both names.
- **Suggest tables** — deterministic and explainable: the smallest table
  that still seats the party, so eight-tops stay free for parties of eight.
  No model, no surprises.
- **VIP star and allergy marker** drawn on the bar, so the floor sees the
  two things that change service before walking over.
- Tables grouped by floor, readiness as a dot, unassigned bookings in a
  strip above the grid, click for seat / completed / no-show / cancel /
  move. Bilingual EN-AR with RTL.

## New — AlphaX POS Table Reservation

The document the timeline draws. The table model already carried occupancy
and readiness; what was missing was a table **held for later**, which is
what a restaurant sells on the phone all afternoon.

Carries party, covers, source, VIP, duration, allergy notes, and links to
the table session once seated — so a seated reservation becomes an ordinary
running table rather than a second concept the till has to learn.

**Two rules are enforced in the controller, not the board**, because the
desk form, an import and a future online booking all land in the same
place:

- a table may not hold two live bookings whose windows overlap, **including
  the turnaround minutes** the outlet needs to clear and reset it;
- a party may not be seated at a table that cannot hold it (`max_party_size`
  where set, otherwise the seat count; `min_party_size` keeps large tables
  free for large bookings).

Cancelled and No Show bookings are invisible to both checks, so releasing a
table is a status change and the history survives.

`simulate_reservations.py` asserts fourteen cases, including the two edges
that matter: a booking ending **exactly** when the next begins is refused,
and one starting exactly one turnaround later is allowed.

Also adds `closed_on`, `covers` and `reservation` to **AlphaX POS Table
Session**, so a bar has a real end and turn time becomes measurable.

## New — bilingual till login

`/pos_login` (alias `/pos-login`). Guest-accessible, branded from Website
Settings and the outlet's company.

The language picker sits **directly under the logo and above the form**: a
cashier who cannot read the field labels will not find a picker at the
bottom of the page.

- The choice is written to the key the cashier SPA already reads, so the
  language chosen at the door is the language the till opens in. One
  decision, not two.
- **Caps Lock warning** on the password field — the most common cause of a
  failed login on a shop-floor keyboard.
- Show/hide password, because cashiers type on keyboards they did not pick.
- One failure message for every failure, so a wrong username cannot be told
  apart from a wrong password.
- The `redirect-to` target is validated to a same-site path. An unvalidated
  redirect on a login page is a phishing gift.

## Changed

- `verify_tree.py` section 9 now resolves **every desk page's** server
  calls, not just the flow board's, including a module name held in a
  const. Mutation-tested against a typo in `suggest_tables`. Eleven calls
  resolved.
- Workspace: `Table Timeline` shortcut and an Operations card link; the
  content row is rebuilt from the shortcut list so every tile draws.
- Process flow: 77 nodes, up from 75.
- Version 15.17.0 → 15.18.0.

## Next — v15.19.0

In build order:

1. **Course firing** — fire starters, hold mains. The largest remaining gap
   between the KDS and a restaurant pass. Needs a course on the order line,
   a fire action per course, and fired timestamps for hold-time reporting.
2. **Allergy and dietary flags on the ticket** — groundwork shipped here:
   reservations carry allergy notes. Remaining work is to copy them onto the
   ticket when the party is seated and show them where the pass cannot miss
   them, plus a veg / non-veg marker per line.
3. **Focus mode** — full-screen till that hides the desk navigation, with a
   visible Esc affordance. Browser full screen offered separately; staff
   conflate the two.
4. **Complimentary bill** — settled at zero against a reason and a manager
   authorisation, reported apart from discounts.

## Files

```
doctype/alphax_pos_table_reservation/     NEW  doctype + controller
pos/timeline_api.py                       NEW  timeline, suggestions, seat
page/alphax_table_timeline/               NEW  the board
www/pos_login.{py,html}                   NEW  bilingual login
doctype/alphax_pos_table_session/         closed_on, covers, reservation
seed/process_flow.py                      Reservations + Table Timeline nodes
fixtures/workspace.json                   shortcut + Operations link
hooks.py                                  /pos-login alias
simulate_reservations.py                  NEW  14 assertions
verify_tree.py                            section 9 generalised
```

New doctype and fields arrive on migrate. No data migration.
