# AlphaX POS Suite v15.8.2 — Shift/day-close saw zero sales (report source)

Field report: 4 submitted invoices, X report Net sales 0.00. The
terminal's alphax_close_report_source was "AlphaX POS Order", so the
shift (and day close, which consolidates shift summaries) counted POS
Order documents while the register posts Sales Invoices directly.

Fix: config-tolerant fallback — when the configured POS Order source
finds nothing in the shift window, _shift_invoices falls through to
the Sales Invoice scan. A misconfigured terminal now reports the truth
instead of zeros. X report, close shift, and day close all inherit the
fix since they share _shift_summary.

Recommended config: on terminals using the direct-invoice register
flow, set AlphaX POS Terminal → Close Report Source = "Sales Invoice"
(the fallback covers you either way).
