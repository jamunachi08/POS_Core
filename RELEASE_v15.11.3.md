# AlphaX POS Suite v15.11.3 — the queue stops hammering, and heals itself

    sync.pending  SAR 255.00
    Cash · 2 items · Queued at Aug 4, 10:13 AM · 28 attempts
    Last error: Company شركة ألز كباب أمين لتقديم الوجبات has no Default
    Receivable Account. Set it on the Company record (Accounting section),
    then retry.

Twenty-eight attempts, twenty-eight identical failures. The server message
was right and useful; the queue's response to it was neither.

---

## The distinction that was missing

A retry queue that retries everything forever is not resilient — it is
loud. The question it never asked was: **does a human have to do something
before this can possibly succeed?**

* **Transient** — dropped wifi, 502/503/504, timeout, deadlock, "document
  has been modified". Retrying *is* the fix. Retry, with backoff.
* **Blocking** — no receivable account, missing fiscal year, a customer
  that does not exist, a mandatory field, a permission. Retrying changes
  nothing until somebody edits something. Stop, say so, and watch for the
  fix.
* **Duplicate** — the server already has it. Settle the row.

Errors are now classified before anything is decided. Transient wins over
blocking on a tie, because a 503 whose HTML body happens to contain the
word "mandatory" is still a 503.

## What each class now does

**Blocking.** The row stays pending — a sale is never dropped — and is
flagged with the server's own sentence. Attempts stop climbing. The banner
at the top of the queue inspector carries the message verbatim, with an **I
fixed it — retry now** button and the reassurance that nothing is lost.

Crucially, the row is **re-checked every three minutes anyway**. The fix
happens on a different screen, often by a different person, and nobody
comes back to tell the till. The moment the receivable account is set, the
queue clears itself with nobody pressing anything — which is exactly the
behaviour you asked for.

**Transient.** Exponential backoff per row: 5s, 10s, 20s … capped at two
minutes. Rows inside their window are skipped rather than retried, so a
long offline stretch produces a handful of attempts instead of hundreds.
The inspector shows a live countdown — a static "retry in 42s" reads as
stuck; a moving one reads as working.

**Manual retry** ignores every hold: failed status, blocked flag, backoff
window. It means "I have fixed it, try now", so it tries now.

## "Even if it disconnects and connects, it should sync automatically"

The `online` event alone does not deliver that. A closed laptop lid fires
nothing. A background tab has its timers throttled to near zero. Captive
portal wifi reports online while nothing routes. So the queue now wakes on
**everything that means "we might be back"**:

| Trigger | The situation it catches |
|---|---|
| `online` event | Wifi returns while the tab is in front |
| `focus` | Cashier comes back to the till after the router was rebooted |
| `visibilitychange` | Tab brought forward |
| Resume detection | A 15s timer that jumped more than 90s — machine woke from sleep |
| `connection.change` | Tablet moved from wifi to LTE |
| Interval (15s) | Everything else |
| Startup | A till that boots with a queue clears it immediately, not after the first interval |

`drain()` is cheap and idempotent — it returns instantly if one is already
running — so calling it from six places costs nothing.

**One more fix in the same area:** `online` initialised from
`navigator.onLine`, which is `undefined` on any runtime that does not
report it — and `undefined` read as offline, so the queue sat still
forever. It now defaults to online unless the platform explicitly says
otherwise.

## Verification on this tree

| Check | Result |
|---|---|
| `python verify_tree.py` | verified — safe to push |
| `python build_spa_payload.py` | 70 files packed, hash in sync |
| `node simulate.js` | full jsdom boot through the pay dialog |
| `node simulate_sync_queue.js` (new) | 23 checks pass |
| `node simulate_order_modes.js` | 17 checks pass |
| `node simulate_kot_modes.js` | 12 checks pass |
| `node simulate_shift_gate.js` | 7 checks pass |
| `node simulate_customer_display.js` | 17 checks pass |

`simulate_sync_queue.js` replays your exact failure: it queues a SAR 255
cash sale, has the server reject it with the receivable-account message,
and asserts that the sale is kept, flagged as needing a person, and that
**eleven drains later it is still on one attempt, not eleven**. It then
fixes the server behaviour without touching the till and asserts the row
syncs itself. It also covers transient backoff growth (5s → 10s), skipping
rows inside their window, manual retry overriding it, offline queuing
attempting nothing at all, and duplicates settling rather than looping.

That test also caught the `navigator.onLine` defect described above.

## Your immediate fix

The queue is behaving correctly now, but the sale still will not post until
the company is configured. On the desk:

**Company → شركة ألز كباب أمين لتقديم الوجبات → Accounting → Default
Receivable Account** — usually `Debtors - <abbr>`.

Then either press **I fixed it — retry now** in the queue inspector, or do
nothing: within three minutes the till posts it by itself.

## Deploy

    git add -A
    git commit -m "v15.11.3: classify sync errors, back off transients, self-heal blocked rows"
    git push origin HEAD:main --force-with-lease

    bench --site tkakenda.frappe.cloud migrate
    bench --site tkakenda.frappe.cloud clear-cache

Existing queued rows are picked up as they are; the first drain after
reload classifies them and either retries or flags them.
