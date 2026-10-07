# AlphaX POS Suite v15.13.0 — assessment of POSNext and hotel_desk, plus store credit

You asked me to read both apps, judge what is worth having, and build it
ourselves. Here is the honest reading, including the parts where the answer
is "we already do this better" and the part you need to know about before
anyone opens POSNext's source again.

---

## Read this first: POSNext is AGPL-3.0

`POSNext-develop/license.txt` is the **GNU Affero General Public License
v3**. That is the most demanding copyleft licence in common use, and the
"Affero" part is what makes it dangerous here: it triggers on *network
use*, not just distribution. A hosted POS your customers reach over a
browser is network use.

If AlphaX POS Suite contained AGPL code, you would be obliged to offer the
complete corresponding source of AlphaX POS Suite to every user who
touches it over a network — including your KSA clients, including
competitors. For a commercial product sold under the AlphaX brand, that is
not a licensing inconvenience; it is the end of the commercial model.

**Your instinct — "we will build everything our own, just take an idea" —
is exactly right, and it is also the only legally safe option.** Copyright
protects expression, not ideas. Reading a doctype list and concluding "we
need customer store credit" is not infringement. Copying a `.py` file, or
transcribing one closely enough that the structure survives, is.

So the discipline I followed, and would recommend as standing policy:

* Read for **what problem it solves**, never for how the code reads.
* Write down the concept in one sentence, close the source, then design
  from the sentence.
* Never copy field names, method names, or file structure — those are the
  fingerprints that make derivation provable.
* Keep the reference apps out of the repo entirely. They are not in this
  zip.

`hotel_desk` is **MIT** — permissive, attribution only. Copying from it
would be legally fine. It is thin enough that there is nothing worth
copying anyway; see below.

---

## What I actually found

### POSNext

| Concept | Verdict |
|---|---|
| **Customer wallet (money)** | **Real gap. Built this release.** |
| Barcode rules | **We are already ahead.** Their rule is a single `barcode_rule` string per row. Ours (`AlphaX POS Scale Barcode Definition`) carries prefix, total length, mapping type, item/qty/rate offsets and lengths, and separate qty and rate dividers. Nothing to take. |
| POS coupons | **Do not rebuild.** ERPNext already ships Coupon Code + Pricing Rule, and we have `AlphaX POS Offer` on top. A third overlapping discount engine would mean three places to look when a discount is wrong. |
| Referral codes | Genuinely absent from ours, but it is a marketing feature, not a POS one. Better as a small app that issues ERPNext coupons than as POS core. |
| Bank deposits | We have `AlphaX POS Cash Movement`. Marginal. |
| Governorate / district | Address hierarchy. ERPNext Address plus two custom fields does this; a doctype pair is overkill. |
| Offline invoice sync | Ours is stronger — v15.11.3 gave us error classification, per-row backoff, and self-healing blocked rows. |

### hotel_desk

Six doctypes: room, room_type, reservation, guest, house_keeping, service.
No folio, no night audit, no rate calendar, no channel management, no
deposit handling. It is a teaching-grade app, and materially less
developed than the hospitality design I sketched for you in v15.10.7.

**But it contains one genuinely good idea**, and it is the kind that is
obvious only after someone else has done it: `Room` carries
**`availability_status` and `cleanliness_status` as two separate fields.**

That is correct, and hotels have modelled it that way for decades, because
one combined field cannot express *vacant but not yet cleaned*. And it
maps straight onto our tables — where we had exactly the flaw their model
avoids. Built this release.

---

## Built: store credit

Concept from POSNext's wallet. Implementation ours, and it differs on the
three points that decide whether it survives a ZATCA audit.

**1. It is a liability, not income.** Money taken now for goods later is
owed, not earned. Booking it to income at issue overstates revenue in the
period it is sold and understates it when it is used. This is a standard
audit finding and it is the default outcome of every store-credit feature
that treats the balance as a number on a customer record rather than a
posting. Ours carries a liability account, defaulting through AlphaX POS
Settings, and **refuses to post rather than guess** at a plausible
account — a wrongly-posted entry is harder to find than one that declined.

**2. VAT attaches on redemption, not on issue.** Issuing credit is not a
supply; nothing has been delivered, so there is nothing to tax yet. The tax
point is when it is spent, at whatever rate the goods carry. Charging VAT
at issue and again at redemption is double taxation; charging it only at
issue is wrong the moment the customer buys zero-rated items. Both are
recoverable only by amending returns. `issue()` posts no tax.

**3. The balance is the ledger.** POSNext stores `current_balance` on the
wallet. We store it too — but only as a cache, recomputed from the entries
on every movement and on every read that matters. A stored balance that
drifts from its entries cannot be reconciled afterwards, because nobody
can say which of the two was right.

Three more decisions worth stating:

* **Separate from loyalty points, deliberately.** We already have
  `AlphaX POS Loyalty Wallet`. Points are a marketing accrual the business
  may devalue or expire at will; store credit is the customer's money.
  Merging them into one "wallet" is convenient until someone asks which
  part of the balance is a liability.
* **`redeem()` does not post to the GL by default, and `issue()` does.**
  The asymmetry is intentional: the normal redemption path is a Sales
  Invoice with a payment line against the store-credit account, and that
  invoice already relieves the liability. Posting a journal as well would
  relieve it twice and leave the account permanently short. The flag
  exists for redemptions with no invoice behind them.
* **`client_uuid` is uniquely indexed.** An offline till retrying a
  redemption must not spend the same credit twice, and the unique index is
  what actually guarantees that — not the retry logic, which is exactly
  the thing that failed.

Also: append-only entries (a mistake is corrected by a Reversal, never an
edit), balance-check against the live ledger rather than the cache so two
tills cannot both overdraw, expiry as a daily job that writes an Expiry
entry rather than zeroing a balance, and a `statement()` endpoint for the
question customers actually ask at the counter.

The settings field notes that several jurisdictions forbid expiring credit
that originated as a cash refund. Worth checking before anyone sets a
default expiry.

## Built: two-axis table state

Concept from hotel_desk's room model.

`AlphaX POS Table` had one `status`: Free / Occupied / Reserved / Dirty /
Disabled. Free and Dirty are mutually exclusive in that list — but not in a
restaurant. A party leaves and the table is simultaneously *free of guests*
and *not ready for the next ones*.

Now two independent axes:

| Occupancy | Readiness |
|---|---|
| Free · Occupied · Reserved · Disabled | Ready · Needs Cleaning · Out of Service |

`Dirty` stays in the occupancy list so historical rows remain readable, but
is superseded.

**A party leaving always sets Needs Cleaning.** Somebody has to say a table
is clean; nothing should assume it. `set_table_readiness()` is a separate
endpoint from `update_table_status()` because bussing is a different action
by a different person at a different moment, and permission to seat should
not imply permission to declare clean. Marking Ready is refused while the
table is still occupied.

`readiness_changed_on`, `last_seated_on` and `last_cleared_on` are stamped
as a side effect, which gives you turn-time reporting for free — and how
long tables sit dirty is usually the real constraint on covers, not how
many tables there are.

---

## What I did not build, and why

* **Referral codes** — marketing, not POS. Belongs in a separate app that
  issues native ERPNext coupons.
* **A third discount engine** — ERPNext Pricing Rule + Coupon Code plus our
  Offers already means two places to look. Three would be worse.
* **A hotel module from hotel_desk** — it has no folio, which is the part
  that matters. The design in the v15.10.7 note is further along than what
  is in that zip.
* **Store credit UI on the till.** The engine, the accounting and the
  endpoints are complete and callable. The tender button is not wired yet.
  I would rather hand you a correct ledger with one screen outstanding than
  a screen posting to the wrong account.

## Verification on this tree

| Check | Result |
|---|---|
| `python verify_tree.py` | verified — seven guards clean |
| `node simulate.js` | boot simulation: no page errors |
| `node simulate_onboarding_steps.js` | 11 checks pass |
| `node simulate_sync_queue.js` | 23 checks pass |
| `node simulate_order_modes.js` | 17 checks pass |
| `node simulate_kot_modes.js` | 12 checks pass |
| `node simulate_shift_gate.js` | 7 checks pass |

## Deploy

    git add -A
    git commit -m "v15.13.0: store credit ledger, two-axis table state"
    git push origin HEAD:main --force-with-lease

    bench --site tkakenda.frappe.cloud migrate
    bench --site tkakenda.frappe.cloud clear-cache

Then, before issuing any credit: **AlphaX POS Settings → Store Credit →
Store Credit Liability Account.** Create it as a current liability under
the company if it does not exist. The engine will refuse to post without
one, which is deliberate.

Existing tables default to Readiness = Ready on migrate, so nothing changes
until a party is seated and leaves.
