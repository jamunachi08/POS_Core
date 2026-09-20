# AlphaX POS Suite v15.9.14 — Tobacco fee, the ERPGulf-compatible way

Field constraint: ERPGulf's ZATCA app does not accept item-wise tax
templates with VAT-inclusive pricing — and ZATCA's XML has no category
for a non-VAT levy anyway (the tobacco fee is part of the
CONSIDERATION per ZATCA guidance, not a tax subtotal).

New design (replaces the Item Tax Template approach entirely):
- The invoice stays a textbook inclusive S-15% document. Sheesha at
  SAR 115 → taxable 100, VAT 15. Nothing tobacco-shaped in the XML;
  ERPGulf submits it as an ordinary invoice.
- On submit, a hook computes the fee INSIDE each tobacco line's net
  (fee = net × rate ÷ (100 + rate); at 100%: net 100 → 50 sales +
  50 fee) and moves it from the line's income account to the fee
  liability account with one auto-submitted Journal Entry
  (cheque_no = TOBACCO::<invoice> for traceability; idempotent).
  Cancelling the invoice cancels the JE.
- Configuration on AlphaX POS Settings → "Tobacco Fee (KSA)": enable
  toggle, fee Account, fee Rate % (default 100 — regulation changes
  are a FORM EDIT), and the tobacco Item Group (descendants included;
  no Item Tax Template anywhere).

## Setup on testneo (undo + redo)
1. REVERT the Sales Taxes template: remove the Tobacco Fee row —
   keep only the plain VAT 15% inclusive row. Remove any Item Tax
   Template assignments from sheesha items.
2. Put sheesha items under a "Tobacco" Item Group (or any group you
   pick), priced fee-inclusive (e.g. 115 gross).
3. AlphaX POS Settings → Tobacco Fee (KSA): enable, pick the Tobacco
   Fee account, rate 100, item group Tobacco.
4. Sell one sheesha; check: invoice shows net 100 / VAT 15 / total
   115; a Journal Entry TOBACCO::<inv> moves 50 income → Tobacco Fee;
   ERPGulf sandbox accepts the invoice.
