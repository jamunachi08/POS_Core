# AlphaX POS Suite — v16.1.0

**Demand & Prep Planner** — forecasts what each outlet will sell, item by
item, for the week ahead, and turns it into a station prep list and a
shortfall request. All computation runs on this site's own workers; an
optional local model writes the morning briefing and never sees customer data.

Open it from the process flow board (new stage **I1 Forecast & Prep**) or at
`/app/alphax-pos-forecast`.

## How it forecasts

Statistical, explainable and dependency-free (`forecast/engine.py`):

- Learns weekday shape (the Fri/Sat weekend included) from the last 8 weeks,
  shrunk toward flat so a thin history cannot produce wild swings.
- Learns the effect of each calendar event it has seen in your own sales:
  **Ramadan, the last ten nights, Eid al-Fitr, Eid al-Adha, Founding Day,
  National Day, payday (27th–2nd)**, plus any event you add.
- Exponential smoothing on the de-seasonalised level; **Croston-SBA** for
  items that sell on fewer than half the days (catering trays, specials).
- **Back-tests itself** on the last 14 days against a seasonal-naive forecast
  and keeps whichever was more accurate, item by item.
- Gives a P10–P90 range from its own back-test errors. Prep is planned to
  P50, P80 (default) or P90.
- Every line says **why**: "Thursday ×1.21; Ramadan ×1.69".

**Hijri calendar** (`forecast/calendar_ksa.py`) is computed in code and
matches Umm al-Qura on the tested dates (Ramadan 1446/1447, Eid al-Fitr 1447,
Eid al-Adha 1447 exact; Eid al-Adha 1446 one day early). Where sighting
differs, record the confirmed dates as **AlphaX POS Calendar Event** — they
replace the computed dates for that event.

**Measured on synthetic two-year outlet data** (`simulate_forecast.py`, 180
rolling one-day-ahead forecasts across Ramadan and Eid 1447):

| | Daily item-level error (WAPE) |
|---|---|
| Seasonal naive (same weekday, last 4 weeks) | 28.6% |
| AlphaX engine | **18.6%** |

P10–P90 band coverage 83% against a nominal 80%. The data carries 18% random
noise, so roughly 14% WAPE is the floor any method can reach on it. Real
outlets will differ; the planner tracks its own live error (below).

## Prep plan

From a day's forecast, **Build prep plan**:

- Explodes each item through its **AlphaX POS Recipe** (UOM conversions
  applied), routes it to the item's station (**AlphaX POS Item Station**),
  and splits it into **Morning / Lunch / Evening** using that item's own
  hourly sales curve (outlet curve when an item has little history).
- Checks outlet stock in slot order, so the sheet says *when* you run short:
  "Lunch — chicken thigh, short 3.2 kg".
- Lists sold items that have no recipe, so the gap is visible.
- **Request shortfall** raises a draft Material Request (transfer from the
  central kitchen, or purchase).
- Kitchen staff tick lines off on the page; **Print prep sheet** prints the list.

## Accuracy, every morning

The nightly run (02:30) fills **actuals** on the last three days' forecasts
(late postings included) and records WAPE and bias. The planner shows the
14-day error and whether it runs high or low.

## Local AI briefing (optional, off by default)

Planner settings → *Briefing writer*. Point it at any OpenAI-compatible
server you run — Ollama, vLLM or a NeotecAI gateway.

- **Residency guard:** the endpoint must resolve only to private, loopback or
  link-local addresses, or be named in *Allowed hosts* (a server you control
  in the Kingdom). Anything else is refused before a request is made.
- **Minimal context:** item names, quantities, slots and calendar tags. No
  customer, cashier, invoice or payment data.
- **No invented numbers:** a reply containing a quantity the engine did not
  produce is discarded and the template briefing is used instead.
- Off, unreachable or rejected → a deterministic English/Arabic template.
- *Test local AI connection* (page menu) reports exactly what was checked.

## New DocTypes

AlphaX POS Forecast Settings (single), AlphaX POS Calendar Event, AlphaX POS
Demand Forecast (+ Line), AlphaX POS Prep Plan (+ Line). Managers plan;
kitchen staff view and tick prep; supervisors view.

## Fixed — two hooks silently dropped by duplicate keys

`hooks.py` declared the same key twice in two dicts. Python keeps only the
last, so:

- **Sales Invoice `on_cancel`**: `pos.tobacco.cancel_tobacco_fee` never ran.
  Cancelling an invoice did not reverse the KSA tobacco fee posting.
- **Scheduler `daily`**: `credit.api.expire_stale_credit` never ran. Store
  credit past its expiry date was never retired.

Both keys are merged. `scripts/health_check.py` now fails the build on any
duplicate key in a dict literal anywhere in the app.

**After upgrading:** review invoices with a tobacco fee cancelled since the
tobacco hook shipped, and expect the first daily run to expire a backlog of
store credit (it writes Expiry entries, it does not zero balances).

## Correction to v16.0.0

The v16.0.0 notes called the invoice-order link a live accounting bug. It was
dormant: AlphaX POS Order is not submittable, so its submit/cancel hooks never
fire. The fix stays, harmlessly; the v16.0.0 changelog now says so.

## Data residency — what this does and does not guarantee

The planner keeps sales data inside the ERP site and the model inside your
network. Whether that means **inside the Kingdom** depends on where the site
itself is hosted. A site on infrastructure outside KSA keeps its data outside
KSA, planner or not. For the residency claim to hold, host the site (and any
model server) in a KSA region or on-prem.

## Not verified without a live bench

`simulate_forecast.py` exercises the engine and calendar; the Frappe side
(SQL against posted invoices, recipe explosion, Material Request) was checked
statically against v16 field definitions but has not run on a site. Before
release to a customer: enable the planner on a staging site with real sales
history, run it from the page, build a prep plan, and raise a shortfall
request.
