# AlphaX POS Suite v15.7.9 — Column split-brain guard

Supersedes v15.7.8 (same fix set, one hardening added). Deploy this one.

v15.7.8's migrate hook created missing Custom Field *records*, but a
site where an earlier aborted migrate left the record without the DB
*column* would pass the exists-check and keep failing with 1054 —
Customize Form looks correct while the table disagrees.

`ensure_custom_fields_silently` now verifies every seeded field has a
real column via `frappe.db.has_column` and runs `frappe.db.updatedb`
on any doctype that's short, on every migrate. Whichever of the two
states testneo is in (field record missing, or record present but
column missing), one deploy + migrate heals it.
