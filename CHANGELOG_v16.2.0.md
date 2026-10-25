# AlphaX POS Suite — v16.2.0

**Delivery platforms (HungerStation, Jahez, Keeta) and recipe costing.**

## Delivery platforms

Orders from the platforms arrive in one **Delivery Inbox**, get answered from
the till, and post as ordinary POS sales — so kitchen tickets, ZATCA, the
tobacco fee, loyalty, the shift register and the existing **Delivery
Reconciliation** report all apply without a second code path.

### Status by platform — read before selling this

| Platform | Built against | Status |
|---|---|---|
| HungerStation | Delivery Hero's published POS plugin contract (HungerStation is listed on it for KSA) | Implemented end to end. Must pass Delivery Hero's sandbox certification before go-live. |
| Jahez | No public spec — Jahez issues it to partners (integration@jahez.net) | Framework and an editable template. **Paths and field names must be set from the spec Jahez sends.** |
| Keeta | No public spec — issued at onboarding | Same as Jahez. |

### Setup (Process flow board → J1 Delivery Platforms)

1. **AlphaX Delivery Platform** — one per platform, with its settlement Mode
   of Payment and commission % (both already existed).
2. **AlphaX Aggregator Connection** — credentials, protocol, the invoice
   customer, and a **Stores** table mapping each platform store id to an
   outlet. Saving shows the **webhook URL** to give the platform. New
   connections start in **Sandbox**: orders are accepted for the platform's
   test flow and nothing is cooked or posted.
3. **AlphaX Aggregator Item Map** — every product and topping code the
   platform sends appears here automatically, unmapped, the first time an
   order brings it. Map each to an Item (or mark a free topping *Ignore*).
4. Turn **Enabled** on; turn **Sandbox** off after certification.

### How an order flows

- **Arrival.** The platform calls `/aggregator/<connection>/…`. The request
  is authenticated before anything is written — Delivery Hero's HS512 JWT
  (`service: middleware`), or a shared secret / HMAC / Basic for the others —
  and every request is logged, including rejected ones. Retries return the
  same order (idempotent on the platform's order token); Delivery Hero gets
  back its required `remoteOrderId`.
- **Routing.** By the platform store id; if unknown, by the platform's
  restaurant id inside the order, with a review note asking you to add the
  store id.
- **Answering.** From the inbox (countdown to the platform's deadline, red
  under two minutes) or automatically when **Accept automatically** is on.
  Auto-accept only fires if the outlet has an **open shift** and **every
  item is mapped**; otherwise the order waits for a person.
- **The platform is answered first, then the kitchen.** The order turns
  Accepted only after the platform confirms. The Sales Invoice is posted after
  that; if posting fails, the order is flagged with the reason and a manager
  can post it from the inbox. Delivery Hero's acceptance time uses the rider
  pickup time when given, never under three minutes.
- **Test orders never reach a kitchen.** The platform's `test` flag, a store
  marked *Test store*, or a connection in Sandbox each block posting.
- **Rejecting** requires one of the platform's reject reasons.
- **Ready / handed over.** Platform-delivered orders send *ready*; vendor
  delivery and pickup orders send *picked up*, which is final on the platform
  and is refused until the order is ready unless a manager forces it.
- **Cancellations** from the platform close the order. If it was already
  invoiced, the invoice is **not** reversed automatically — the order is
  flagged for a manager, because the food may already have left.
- **Expiry.** Unanswered orders past the deadline are marked Expired every
  two minutes.
- **Posting.** POS Sales Invoice for the outlet, order type Delivery, the
  delivery platform set, the platform's prices, paid by the platform's Mode of
  Payment (settled later through Delivery Reconciliation), tied to an open
  shift's terminal. If the invoice total and what the platform says the
  customer paid differ by more than 1, the order is flagged.

### Why `/aggregator/` is handled in `before_request`

Delivery Hero calls fixed paths (`/order/{remoteId}`), cancels with **PUT**,
and authenticates with its own **Bearer JWT**. Frappe's router serves website
paths for GET/HEAD/POST only, and Frappe's auth treats any unknown Bearer
token as a failed OAuth login (401). The hook answers paths under
`/aggregator/` before either runs and leaves every other request untouched.
Verified against the Frappe v16 request lifecycle (`app.py`, `auth.py`).

### Certification checklist (HungerStation)

1. Request Delivery Hero POS integration credentials (they are PGP-encrypted
   to a key you provide); set username, password and plugin secret on the
   connection, API base URL to the middleware host they give you.
2. Give them the webhook URL from the connection.
3. Run their test orders with Sandbox on. Check the Request Log: dispatch 200,
   accept 2xx, cancel received.
4. Compare one real payload in the log with the field mapping in
   `protocol.normalize_dh` (prices, toppings, delivery fees). Field names were
   built from the public contract and an independent implementation, not
   from a live sandbox.

## Recipe costing and menu engineering

**Report → AlphaX Recipe Costing** (Process flow board → K1).

- **Plate cost** through the recipe, including **sub-recipes** (a sauce or
  dough with its own recipe), **batch yield** (new *Portions this recipe
  makes* on the recipe) and **trim/cooking waste** (new *Waste %* on each
  line), with UOM conversion. Recipe loops are detected and reported.
- **Cost source** per material, in order: outlet warehouse valuation →
  company-wide stock value → last purchase rate → item master. Materials with
  no cost are listed as costing gaps instead of silently counting as zero.
- **Menu price** from the outlet's price list, **net of VAT** when the
  outlet's tax template is price-inclusive; falls back to the average sold
  price.
- **Food cost %**, **margin in store**, and **margin on each delivery
  platform after its commission** — one column per platform. An item at a
  healthy 30% food cost can lose money on a 25% commission; those show red.
- **Menu engineering** (Kasavana–Smith) on the period's sales mix: Star,
  Plowhorse, Puzzle, Dog.
- Summary: theoretical food cost, items with costing gaps, items losing money
  on any platform.

`api.compute_recipe_cost` now uses the same engine (same response keys plus
`warnings`; optional `outlet` for outlet valuation), so the existing
profitability page and tests keep working.

Commission is applied to the menu price. If a platform's menu prices differ
from the outlet price list, read the platform columns as an approximation.

## Tests

- `simulate_aggregators.py` — 27 checks: JWT (wrong secret, wrong claim,
  expired, `alg=none`, unconfigured secret all rejected), Delivery Hero order
  normalisation, acceptance-time floor, Jahez/Keeta templates, HMAC tamper.
- `simulate_costing.py` — waste, UOM, sub-recipe with batch yield, cycle
  detection, VAT, channel margin, menu classes.
- All 18 simulations, `verify_tree.py` and `scripts/health_check.py` against
  Frappe/ERPNext v16 source pass.

## Not verified without a live bench and platform sandbox

The protocol layer and costing maths are tested; the Frappe side (inbound
hook on a running site, posting a delivery invoice, the inbox page) was
checked statically against v16 and has not run on a site. Do one full
sandbox order per platform on staging before any customer goes live.
