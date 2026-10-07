# AlphaX POS Suite v15.9.3 — Migrate self-heal (before_migrate)

Field state: "DocType AlphaX POS Notify Recipient not found" persisting
ON v15.9.1, whose pre_model_sync patch should have fixed it. Root
cause: patches execute once — if a migrate ever failed and Frappe
Cloud's "Skip failing patches" was used, the patch is marked executed
WITHOUT running, the child doctypes never exist, and every subsequent
migrate aborts at the alphabetical model sync (parent Link/Table
validated against a missing child).

Fix: ensure_dependency_doctypes() on the **before_migrate hook** — no
execution history, runs at the START of every migrate, creates any of
the five dependency doctypes that are missing (children before
parents: Print Station, KOT Routing Rule, Combo Component, Notify
Recipient, Combo), no-ops on healthy sites, and logs anything it
creates. This failure class is now permanently retired: even a
half-synced site heals itself on the next deploy.

Includes everything from v15.9.2 (inclusive VAT engine + KSA tobacco
fee). Deploy this; migrate completes; Outlet form opens with Store
Hours and Nominated Persons sections.
