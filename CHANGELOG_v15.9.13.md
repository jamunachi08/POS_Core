# AlphaX POS Suite v15.9.13 — Day close totals + print; bundled thermal print format

- Day close header totals fixed: the return contract now carries
  net_sales / vat_amount / counted_cash / variance explicitly (dialog
  read keys the API never sent → 0.00 while shift-wise showed 230).
  VAT is aggregated across shifts; the Day Close document also stores
  vat_amount, cash_total, and variance now.
- "Print report" button on the day-close result: 80mm report — doc no,
  date, terminal, totals, and the shift-wise table (cashier, net,
  counted, over/short).
- Bundled Print Format "AlphaX Thermal 80mm" (Sales Invoice, Jinja):
  80mm receipt layout with per-account tax rows (VAT and Tobacco fee
  print as separate lines automatically) and ZATCA QR when present.
  Select it in Print Settings or per-print; customizable in desk
  without development.
