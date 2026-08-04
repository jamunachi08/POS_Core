import frappe
from frappe import _
from frappe.model.document import Document


class AlphaXPOSOrder(Document):
    def before_insert(self):
        """
        Idempotency guard: if the cashier SPA retries an offline-queued order,
        the same client_uuid will arrive twice. Refuse duplicates.

        Generate a uuid if the client didn't send one, so legacy flows still work.
        """
        if not getattr(self, "client_uuid", None):
            self.client_uuid = frappe.generate_hash(length=20)
            return

        existing = frappe.db.get_value(
            "AlphaX POS Order",
            {"client_uuid": self.client_uuid},
            "name",
        )
        if existing:
            frappe.throw(
                _("Order with client_uuid {0} already exists as {1}.").format(
                    self.client_uuid, existing
                ),
                frappe.DuplicateEntryError,
            )


@frappe.whitelist()
def find_by_client_uuid(client_uuid):
    """
    Lookup endpoint for the offline sync queue. The cashier sends an order,
    network blips, retries: instead of duplicating, the SPA calls this with
    the same client_uuid and either gets back the existing record or proceeds
    with a fresh insert.
    """
    if not client_uuid:
        return None
    name = frappe.db.get_value(
        "AlphaX POS Order", {"client_uuid": client_uuid}, "name"
    )
    if not name:
        return None
    return frappe.get_doc("AlphaX POS Order", name).as_dict()
