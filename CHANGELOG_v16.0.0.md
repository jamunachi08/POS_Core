# AlphaX POS Suite — v16.0.0

**Runs on Frappe/ERPNext v15 and v16.** First release built against the v16
source tree (Frappe 16.53, ERPNext 16.52) as well as v15.

## Health check — what was examined

A new static checker, `scripts/health_check.py`, resolves the app against
Frappe/ERPNext v16 source without a bench:

| Check | Result |
|---|---|
| Dependency pins | **Was blocking**: `<16.0.0` on frappe and erpnext. Fixed. |
| Python 3.14 (v16 runtime): removed stdlib modules, syntax | Clean |
| 221 `frappe.*` / `erpnext.*` imported names | All resolve on v16 |
| 38 dotted paths in `hooks.py` | All resolve |
| `patches.txt` entries and `execute()` | All resolve |
| 79 DocTypes: modules, duplicate fields, Link/Table targets | Clean |
| DocType names and core fields read/written in Python | All exist on v16 or in app custom fields, except one real gap (below) |
| Custom-field targets and `insert_after` anchors on v16 | Two stale anchors (below) |
| 80 browser → server method calls | All reach whitelisted functions |
| 7 guest-callable endpoints | Reviewed; one hardened (below) |
| Existing gates: `verify_tree.py`, 14 boot/flow simulations | All green (one stale kit and four broken simulation paths fixed) |

Run it before every push:

```bash
python3 verify_tree.py
python3 scripts/health_check.py --ref /path/to/apps   # folder holding frappe/ and erpnext/
```

## Fixed — order cancellation did not reverse the invoice

> **Correction (v16.1.0):** AlphaX POS Order is not a submittable DocType, so
> its `on_submit`/`on_cancel` hooks never fire and this path was dormant: no
> live invoices were left unreversed through it, and the SQL check below will
> return nothing. The field and the stricter cancel stay in place so the path
> is correct if orders are ever made submittable. See CHANGELOG_v16.1.0.md.


Posting assigned `Sales Invoice.alphax_pos_order`, but that custom field was
never created, so the value was silently dropped. `on_order_cancel` required
it to match, so the condition was always false: **cancelling a POS Order left
its Sales Invoice submitted** — revenue, VAT and stock unreversed — and the
failure path only wrote an error log.

- New custom field `Sales Invoice.alphax_pos_order` (read-only, indexed).
- Patch `v16_0.link_invoices_to_pos_orders` creates it and backfills every
  existing invoice from the order's own `sales_invoice` pointer.
- Cancel now trusts the order's pointer, refuses an invoice owned by a
  different order, and **raises on failure** so an order can no longer show
  Cancelled while its invoice stays live.

**After upgrading**, list orders cancelled before v16.0.0 whose invoice is still
submitted and cancel or return those invoices:

```sql
select o.name, o.sales_invoice from `tabAlphaX POS Order` o
join `tabSales Invoice` si on si.name = o.sales_invoice
where o.docstatus = 2 and si.docstatus = 1;
```

## Hardened — card-payment callback

`card_payment_callback` is guest-callable (readers cannot log in) and relied
only on an unguessable UUID. Anyone holding a UUID could post "Approved", an
outcome could be overwritten after the fact, and every unknown UUID created a
database record.

- Per-IP rate limit, 120 per minute.
- New **Callback Signing Secret** on AlphaX POS Card Reader. When set, the
  body must carry `X-AlphaX-Signature: sha256=<HMAC-SHA256>`; mismatches are
  rejected and logged. Set it on every reader that posts back over HTTP.
- Results are accepted only while the transaction is **Pending**.
- Unknown UUIDs are logged once per UUID and no longer create records.

## v16 readiness

- Pins widened to `>=15.0.0,<17.0.0` for frappe and erpnext.
- `frappe.cache()` → `frappe.cache` at 20 call sites (the call form survives
  in v16 only as a back-compat shim).
- Custom-field anchors corrected for fresh installs: `Item.alphax_is_weighing_item`
  now sits after `barcodes` (v16 Item has no `barcode` field);
  `AlphaX POS Profile.alphax_outlet` after `pos_type`.

## Housekeeping

- Removed stale `AlphaX-POS-Bridge-Setup-15.5.3.zip` (verify_tree failure).
- Four JS simulations used an absolute path from an old build machine; they now
  resolve relative to the repo. The availability simulation's cache mock
  matches the property-style API.

## Not verifiable without a live v16 bench

Static checks cannot prove these; test them on a v16 staging site before
moving customers:

1. Desk pages (cashier, KDS, floor designer, setup wizard) under v16's desk
   chrome and sidebar.
2. Workspace rendering — v16 reworked the workspace sidebar.
3. A full sale → Sales Invoice → ZATCA submission with the alphax-zatca fork,
   which must itself be v16-ready.
4. `bench migrate` from a v15.21.0 site, including the new patch.
