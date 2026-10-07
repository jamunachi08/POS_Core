# AlphaX POS Suite v15.7.10 — Queue push endpoint: one call, real diagnostics

## "cannot unpack non-iterable NoneType object"

The 1054 is resolved (columns created by v15.7.9's migrate self-heal) —
the flush now reaches ERPNext core and dies there with a bare TypeError.
The old flush used generic frappe.client.insert + submit, which
discards server tracebacks, so the register can show only that one
useless line.

## Fixes

- New endpoint `pos.queue_api.push_queued_invoice`: insert + submit in
  ONE call. On any failure the FULL traceback is written to Error Log
  (desk → Error Log, title "AlphaX POS: queue push failed") — bare
  core exceptions are now diagnosable.
- **Preflight** translates the classic fresh-site gaps into fix-it
  messages before insert: no Fiscal Year covering the posting date for
  the company (the best-known cause of this exact TypeError on young
  sites — including fiscal years restricted to other companies),
  missing Company default receivable account, nonexistent customer,
  Mode of Payment without an account row for the company.
- Dedupe built in: an invoice already carrying the client UUID is
  returned as {duplicate: true}; a stray DRAFT from the old two-call
  flow (insert ok, submit failed) is submitted and returned — the
  queue self-repairs its own history.
- sync.js flushes through the new endpoint with automatic fallback to
  the legacy pair when the server predates it (version-skew safe).

## After deploying

Reload the register. The two queued sales will either sync, or show a
specific instruction (e.g. create the 2026 Fiscal Year / set the
receivable account). If anything still fails opaquely, desk → Error
Log now has the full traceback — paste it and the next fix is exact.
