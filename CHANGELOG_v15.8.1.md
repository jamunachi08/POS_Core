# AlphaX POS Suite v15.8.1 — Migrate fix: doctype sync order + v1 station consolidation

## "Field station is referring to non-existing doctype AlphaX POS Print Station"

Frappe syncs an app's doctypes in alphabetical folder order, so
alphax_pos_kds_ticket validated its station Link before
alphax_pos_print_station existed. The v1 KDS Ticket Item child had
carried a Link to a never-created station doctype since before v15.8 —
a latent bug that only detonated when v15.8.0 re-triggered the sync.

Fixes:
- **[pre_model_sync] patch** imports Print Station and Routing Rule
  BEFORE the general model sync, so every dependent Link validates
  against an existing doctype. Idempotent (force re-import) — also
  self-heals a site where the doctype was deleted by hand.
- **[post_model_sync] consolidation**: legacy AlphaX POS Kitchen
  Stations become same-named Print Stations (type Kitchen Display), so
  existing KDS ticket lines and Item Station rows keep pointing at
  valid records. Kitchen Station is retired from new configuration but
  not deleted. Fresh sites no-op.
- **Item Station overrides honored end-to-end**: exact-item → station
  mappings (v1 heritage) now beat group rules in BOTH the server
  fan-out and the register's offline client routing, and ship in the
  boot payload. Verified in the simulator: item override wins over the
  matching group rule.

Deploy over v15.8.0; migrate completes cleanly on both upgraded and
fresh sites. Payload = tree = stamp verified.
