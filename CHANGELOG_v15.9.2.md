# AlphaX POS Suite v15.9.2 — Inclusive VAT + KSA Tobacco Fee

## Inclusive pricing done right
The register previously summed template rates and ADDED tax on top —
wrong for KSA retail, where menu prices are VAT-inclusive. The new
line-level engine honors included_in_print_rate: the net base is
EXTRACTED from the shown price, the cart total equals the menu price,
and the invoice carries the same template rows so ERPNext's
authoritative recomputation matches the till to the halala. Exclusive
templates keep the old add-on behavior — the flag on the template rows
decides, per row.

## Tobacco (sheesha) fee — separate account head, compound VAT
Implemented through ERPNext-native Item Tax Templates, so the fee
posts to ITS OWN liability account and only for tobacco items:

Setup (one time, in desk):
1. Chart of Accounts: create "Tobacco Fee" (liability, like your VAT
   account).
2. Sales Taxes and Charges Template — two rows IN THIS ORDER:
   Row 1: On Net Total, account "Tobacco Fee", rate 0,
          included_in_print_rate as per your pricing.
   Row 2: On Previous Row Total, account "VAT 15%", rate 15 —
          "previous row" makes VAT compute on the fee-INCLUSIVE amount,
          per KSA rules.
3. Item Tax Template "KSA Tobacco 100 + VAT 15":
          Tobacco Fee → 100, VAT 15% → 15.
4. Assign that Item Tax Template on each sheesha/tobacco Item.

Result at the till: a sheesha at SAR 115 inclusive shows
Net 50.00 · Tobacco fee 50.00 · VAT 15.00 — verified in the simulator
to the exact halala. Non-tobacco items see the fee row at rate 0 and
are untouched. The cart, receipt tax breakdown, and GL rows all name
the separate account.

## Plumbing
Boot ships Item Tax Template definitions; menu items carry their
template; invoice items pass item_tax_template so ERPNext applies
per-item rates server-side; cart totals area now renders one row per
tax account (VAT and Tobacco fee separately) instead of a single
aggregate percentage.

Both simulators green (18 assertions incl. the 115 = 50+50+15 check).
Payload = tree = stamp verified.
