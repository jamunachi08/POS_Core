"""post_model_sync: fold the v1 station model into Print Stations.

v1 shipped AlphaX POS Kitchen Station (name + outlet, display-oriented)
and AlphaX POS Item Station (per-item mapping). v15.8.0 introduced the
richer AlphaX POS Print Station (types, bridge fan-out target, default
fallback) + item-group routing rules. Consolidation:

- every enabled Kitchen Station becomes a Print Station of type
  "Kitchen Display" with the SAME NAME — so existing Item Station rows
  and KDS ticket lines keep pointing at valid records after their Link
  options flip to Print Station;
- Item Station survives as the per-item OVERRIDE (exact item beats
  group rules), which v1 users already rely on;
- Kitchen Station is retired from new configuration but not deleted —
  removing doctypes breaks sites.
"""

import frappe


def execute():
    if not frappe.db.table_exists("AlphaX POS Kitchen Station"):
        return
    for ks in frappe.get_all(
        "AlphaX POS Kitchen Station",
        fields=["name", "station_name", "outlet", "enabled"],
    ):
        target_name = ks.station_name or ks.name
        if frappe.db.exists("AlphaX POS Print Station", target_name):
            continue
        frappe.get_doc({
            "doctype": "AlphaX POS Print Station",
            "station_name": target_name,
            "outlet": ks.outlet,
            "station_type": "Kitchen Display",
            "enabled": ks.enabled,
        }).insert(ignore_permissions=True)
    frappe.db.commit()
