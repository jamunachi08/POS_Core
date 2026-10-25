# AlphaX POS Suite — v15.20.0

Till-floor ergonomics: PIN sign-in with a lock screen, and the 86 list.

All original AlphaX work. No third-party code, schema, markup or assets.

## New — PIN sign-in and the till lock screen

`/pos_lock` (alias `/pos-lock`). Full-bleed brand panel beside a keypad,
bilingual, RTL, with a password sign-in always one tap away.

A cashier starting a shift should not be typing an email address and a
password on a greasy touchscreen with a queue forming.

**A 4-digit PIN is 10,000 possibilities, so it only ships inside a cage:**

| Control | Behaviour |
|---|---|
| Off by default | Nothing works until `pin_signin_enabled` is ticked on POS Settings |
| Bound terminals only | An unbound browser gets the same answer as a wrong PIN |
| Role-gated | A PIN never grants a role; it proves identity for someone who already holds one |
| Unique per site | Setting a PIN a colleague already uses is refused — a shared PIN signs in the wrong person and the shift report then names them |
| Terminal lockout | 5 failures locks the terminal on an escalating schedule (1, 5, 15, 60 min), counted **per terminal** — a brute force does not know whose PIN it is guessing |
| Audited | Every attempt, success or failure, to the existing authorisation log |
| Indistinguishable failures | Unknown terminal, wrong PIN, disabled user and a user with no POS role all return the same message |

**While a terminal is locked, even the correct PIN is refused.** That is
deliberate: a lockout a correct guess can end is not a lockout. A manager
clears it with `clear_terminal_lockout`.

The lock screen itself returns nothing that identifies anyone — no staff
list, no names, no PIN hints — because it is served to an unauthenticated
browser.

Reuses the existing bcrypt PIN record rather than adding a second one, so
a manager has one PIN, not two.

**Honest limitation:** a PIN proves "the person at this till is on the
rota". It is not a password and is deliberately useless anywhere else.
Leave it off for any terminal that is not physically supervised.

## New — the 86 list

Mid-service the kitchen runs out. Without this the cashier keeps selling
it, the ticket reaches the pass, somebody walks back to the table, and the
guest is told no after they have already decided.

**AlphaX POS Item Availability**, per outlet, with three states because
kitchens do not think in two:

- **Off** — gone. The item **leaves the till payload entirely**, rather
  than being greyed out: a disabled tile still gets tapped.
- **Low** — nearly gone. Still sells, but the reason rides along so a
  party of eight does not order the last two portions.
- **On** — back. Kept as a record rather than deleted, so "how often did
  we 86 the salmon last month" has an answer.

Per outlet, never per company: one branch running out of lamb is not a
reason to stop selling it across the city.

**Driven from the kitchen pass**, which is where the person who knows is
standing. The KDS toolbar carries an **86 List** button that turns red and
shows a count. Taking an item off takes an optional reason and an optional
"back on at" time; the till is told over realtime, not at the next reload.

An expired hold is treated as back on by the till **immediately**, whether
or not the hourly scheduler has run — the till must never be the last to
know.

## Verification

`simulate_availability.py` — 18 assertions across both features, including:

- a hold that expired at 18:00 is already back on at 19:00 without the
  scheduler;
- Off items leave the payload while Low items stay;
- a correct PIN held by someone with no POS role does not sign in;
- an unknown terminal returns the same message as a wrong PIN, so the
  endpoint cannot be used to enumerate terminals;
- the fifth wrong PIN locks the terminal, and the correct PIN is refused
  while it is locked;
- the unauthenticated lock-screen context carries no user list and no PIN
  hint.

## Files

```
security/staff_pin.py                    NEW  sign-in, lockout, uniqueness
www/pos_lock.{py,html}                   NEW  the lock screen
doctype/alphax_pos_item_availability/    NEW  the 86 record
pos/availability.py                      NEW  board, set, auto-restore
catalog/api.py                           Off items leave the menu payload
page/alphax_kds/                         86 List button, board, take-off dialog
doctype/alphax_pos_settings/             pin_signin_enabled, idle lock minutes
hooks.py                                 /pos-lock route, hourly restore
seed/process_flow.py                     86 List + Till Lock Screen nodes (80 total)
simulate_availability.py                 NEW
```

No data migration. New doctype, fields and settings arrive on migrate;
PIN sign-in stays off until switched on.

## Reviewed and not built

- **Waiter assignment and a by-waiter table view** — a real gap: there is
  no server assigned to a table or an order today, so per-server sales,
  tips and section reporting are not possible. Next.
- **Clock in/out at the till** — maps cleanly onto ERPNext Employee
  Checkin rather than a parallel attendance record.
- **No Sale** — open the drawer without a sale, with a reason and an audit
  row. Small and worth having.
- **A terminal menu hub** grouping shift, order and service actions on one
  screen. Mostly a re-arrangement of functions that already exist.

Still queued from v15.19.0: **course firing**, then focus mode and the
complimentary bill.
