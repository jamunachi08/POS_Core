# AlphaX POS Suite v15.7.2 — Hotfix

- `rename_workspace_to_match_title` patch crashed migrate:
  `frappe.rename_doc()` has no `ignore_permissions` kwarg in v15.
  Removed (patches run as Administrator; no bypass needed). Failed
  patches are not logged as executed, so this simply re-runs and
  completes on the next migrate — no manual intervention.
- No other `rename_doc` call sites exist in the app (verified).
- Includes everything from v15.7.1 (Shift & Cash Management).
