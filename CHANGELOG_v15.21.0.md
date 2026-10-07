# AlphaX POS Suite — v15.21.0

**Maximum shift age** — a hard cut-off for a till left open, independent of
store closing time.

## What already existed, and the hole in it

| Control | Where | Limitation |
|---|---|---|
| `enforce_closing_time` + `closing_time` + grace | Outlet | Only helps an outlet that **configured** a closing time |
| Scheduler auto-close at closing time | every 5 min | Same dependency |
| `require_shift_open` blocks posting | POS Settings | Checks a shift **exists**, never **how old it is** |
| `day_close_trigger` = At Closing Time | Terminal | Same dependency on a closing time |

So on a 24-hour forecourt, or any outlet that never filled in a closing
time, **a shift opened on Monday afternoon was still taking sales on
Thursday.** Nothing checked its age. That is not cosmetic:

- three days of takings land in one cash declaration, so the variance is
  meaningless and nobody can be held to it;
- sales post against a business date that closed days ago, moving revenue
  into the wrong period;
- the day close that should have run never runs, so the shift-wise report
  and the bank deposit never reconcile.

## New — the cut-off

**POS Settings → Maximum Shift Age**

- `max_shift_hours` — 0 is off. **24** means a shift opened 14:00 Monday
  stops taking sales at 14:00 Tuesday.
- `max_shift_action` — *Block new sales*, or *Block new sales and
  auto-close the shift*.
- `max_shift_warn_minutes` — default 60. The till counts down.

**Outlet → Maximum shift length (hours)** overrides the site, because a
24-hour forecourt and a dinner-only restaurant do not share a sensible
number. An outlet left at 0 falls back to the site setting; it does not
become unlimited.

### Blocking is synchronous, not scheduled

The check runs **in the posting path**, so the limit holds the moment it
passes, whether or not the scheduler ever wakes up. A dead background
worker must not quietly re-open a closed control.

The sale in progress is never interrupted. The block refuses the next
submit, which is the only humane place for it: a half-rung sale abandoned
at the payment screen costs a customer.

The message tells the cashier what to do rather than just saying no —
close the shift, count the drawer, run day close, open a new shift.

### Auto-close never invents a figure

Where auto-close is chosen, the scheduler declares **opening float plus
recorded cash movements** and flags the shift `RECOUNT REQUIRED` — the same
rule closing-time enforcement already follows. A counted figure nobody
counted is worse than an obvious gap. Day close follows where the terminal
is set to trigger it.

Kept deliberately separate from closing-time enforcement: the two answer
different questions — "is the shop shut?" and "has this till been open too
long?" — and an outlet can need the second without having the first.

### The countdown reaches the cashier

`get_shift_state` now carries an `age` block (expiry, minutes left, warn,
expired), so the till warns ahead of the limit. A cashier who first meets
the block at a customer's payment has met it too late.

### Surfaced on the flow board

**Setup & Install** gains a **Shift cut-off** check that names any outlet
where a shift can stay open indefinitely — no closing time enforced and no
maximum length set.

## Verification

`simulate_shift_age.py` — 19 assertions, including:

- an outlet's 12h limit overrides the site's 24h; an outlet at 0 falls back
  rather than becoming unlimited;
- a 10h shift sells, a 26h shift is refused, and the refusal names the
  hours and the remedy;
- with no limit configured nothing is blocked — the control is opt-in, not
  imposed on existing sites;
- the scheduler returns unless auto-close was explicitly chosen;
- the auto-closed figure is float plus movements, flagged for recount.

## Files

```
pos/shift_age.py                    NEW  limit resolution, guard, scheduler, status
pos/posting.py                      synchronous block before submit
pos/shift_api.py                    age block on get_shift_state
pos/flow_setup.py                   Shift cut-off readiness check
doctype/alphax_pos_settings/        max_shift_hours, action, warn minutes
doctype/alphax_pos_outlet/          max_shift_hours override
hooks.py                            */5 enforce_max_shift_age
simulate_shift_age.py               NEW
```

**Off by default.** Existing sites behave exactly as before until a limit
is set. Recommended starting point: 24 hours at site level, with
*Block new sales and auto-close the shift*.
