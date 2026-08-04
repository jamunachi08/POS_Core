import frappe
from frappe import _
from frappe.model.document import Document


class AlphaXPOSOrderType(Document):
    """Service mode.

    The register is the only consumer, and it reads these flags once at
    boot. Contradictions are caught here rather than at the till, where a
    cashier has a queue in front of them and no way to fix a doctype.
    """

    def validate(self):
        self._reject_contradictions()
        self._normalise()

    def _reject_contradictions(self):
        if self.posts_credit and not self.requires_customer:
            # Credit against "Walk-in" is an unrecoverable receivable.
            self.requires_customer = 1

        if self.requires_delivery_platform and self.table_policy == "Mandatory":
            frappe.throw(
                _("A delivery mode cannot require a table. Set Table to Not Applicable.")
            )

        if self.room_policy == "Mandatory" and self.posts_credit:
            frappe.throw(
                _(
                    "Choose one settlement route: a room charge posts to the folio, "
                    "credit posts to the customer. Both cannot be mandatory."
                )
            )

        if self.service_charge_percent and self.service_charge_percent < 0:
            frappe.throw(_("Service charge cannot be negative."))

    def _normalise(self):
        self.order_type_name = (self.order_type_name or "").strip()
        if self.icon:
            self.icon = self.icon.strip()[:4]

    def on_update(self):
        # The register caches the boot payload; a flag change that does not
        # reach the till is worse than no flag at all.
        try:
            from alphax_pos_suite.alphax_pos_suite.boot.api import invalidate_boot_cache
            invalidate_boot_cache()
        except Exception:
            pass


def resolve_effective(order_type: str, outlet: str | None = None) -> dict:
    """Flags actually in force for a mode at an outlet.

    Resolution order, matching the rest of the suite: an outlet-specific
    row wins over the global row of the same name, and a missing row falls
    back to the legacy hard-coded behaviour so an upgrade never leaves a
    till unable to sell.
    """
    LEGACY = {
        "Dine In": {"table_policy": "Optional", "opens_tab": 1, "prints_kot": 1},
        "Takeaway": {"table_policy": "Not Applicable", "prints_kot": 1},
        "Delivery": {"table_policy": "Not Applicable", "requires_delivery_platform": 1},
        "Staff": {"table_policy": "Not Applicable"},
        "Credit": {"table_policy": "Not Applicable", "requires_customer": 1, "posts_credit": 1},
    }

    if not frappe.db.table_exists("AlphaX POS Order Type"):
        return dict(LEGACY.get(order_type, {}), order_type_name=order_type)

    rows = frappe.get_all(
        "AlphaX POS Order Type",
        filters={"order_type_name": order_type, "enabled": 1},
        fields=["*"],
    )
    if not rows:
        return dict(LEGACY.get(order_type, {}), order_type_name=order_type)

    scoped = [r for r in rows if r.get("outlet") == outlet]
    return scoped[0] if scoped else rows[0]
