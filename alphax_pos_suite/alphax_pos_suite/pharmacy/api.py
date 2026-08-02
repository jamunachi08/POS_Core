"""
Pharmacy HTTP API — endpoints the cashier SPA calls when adding a
prescription drug to a sale.

All endpoints are @frappe.whitelist()'d so the SPA can call them via
frappe.call().
"""
import frappe

from .validator import can_dispense_drug


@frappe.whitelist()
def lookup_drug(item_code: str | None = None, drug_code: str | None = None) -> dict:
    """Given an Item.item_code OR a Drug.drug_code, return the drug's
    dispensing metadata for the cashier UI."""
    if not (item_code or drug_code):
        frappe.throw("Provide item_code or drug_code.")

    filters = {}
    if drug_code:
        filters["drug_code"] = drug_code
    elif item_code:
        filters["linked_item"] = item_code

    drug = frappe.db.get_value(
        "AlphaX Drug Master", filters,
        [
            "name", "drug_code", "drug_name", "form",
            "strength", "strength_unit",
            "is_controlled", "requires_prescription",
            "max_daily_dose", "max_daily_dose_unit",
            "min_age_years", "pregnancy_category",
            "drug_class", "atc_code",
        ],
        as_dict=True,
    )
    if not drug:
        return {"found": False}
    drug["found"] = True
    return drug


@frappe.whitelist()
def authorize_dispense(drug_code: str, prescription_name: str | None = None) -> dict:
    """Cashier scans an item, the SPA asks: can I add this to the cart?
    For OTC items the answer is always yes. For prescription items,
    the SPA must supply prescription_name; the helper checks that the
    Rx is active, not expired, and contains the drug."""
    return can_dispense_drug(drug_code, prescription_name)


@frappe.whitelist()
def search_active_prescriptions(query: str = "", outlet: str | None = None,
                                limit: int = 20) -> list[dict]:
    """Search active/partially-dispensed prescriptions by patient name,
    patient ID, or phone. Used by the Rx capture dialog when the
    cashier looks up an existing prescription."""
    filters = [["status", "in", ["Active", "Partially Dispensed"]]]
    if outlet:
        filters.append(["outlet", "=", outlet])
    if query:
        ors = [
            ["patient_name", "like", f"%{query}%"],
            ["patient_id", "like", f"%{query}%"],
            ["patient_phone", "like", f"%{query}%"],
            ["name", "like", f"%{query}%"],
        ]
        filters.append(["OR"] + ors)
    rows = frappe.get_all(
        "AlphaX Prescription",
        filters=filters,
        fields=[
            "name", "patient_name", "patient_id", "patient_phone",
            "prescriber_name", "prescription_date", "expiry_date",
            "status", "fully_dispensed",
        ],
        order_by="modified desc",
        limit=limit,
    )
    return rows


@frappe.whitelist()
def get_prescription_lines(prescription_name: str) -> list[dict]:
    """Return the line items of a prescription with dispensable
    quantities and refill state."""
    rx = frappe.get_doc("AlphaX Prescription", prescription_name)
    out = []
    for line in rx.lines:
        drug = frappe.get_cached_doc("AlphaX Drug Master", line.drug)
        out.append({
            "line_name":          line.name,
            "drug":               line.drug,
            "drug_code":          drug.drug_code,
            "drug_name":          drug.drug_name,
            "form":               drug.form,
            "strength":           drug.strength,
            "strength_unit":      drug.strength_unit,
            "dose":               line.dose,
            "dose_unit":          line.dose_unit,
            "frequency_per_day":  line.frequency_per_day,
            "duration_days":      line.duration_days,
            "quantity_dispensed": line.quantity_dispensed,
            "refills_allowed":    line.refills_allowed,
            "refills_used":       line.refills_used,
            "refills_remaining":  (line.refills_allowed or 0) - (line.refills_used or 0),
            "is_controlled":      drug.is_controlled,
            "linked_item":        drug.linked_item,
            "already_dispensed":  bool(line.dispensed_at),
        })
    return out


@frappe.whitelist()
def record_dispensing(prescription_name: str, line_name: str,
                      qty: float, sales_invoice: str) -> dict:
    """Mark a prescription line as dispensed via the given sales invoice.
    Increments refills_used. If the drug is controlled, writes a
    Controlled Substance Log entry. Returns the updated dispense state."""
    rx = frappe.get_doc("AlphaX Prescription", prescription_name)
    rx.record_dispense(line_name, float(qty), sales_invoice)
    return {
        "ok":               True,
        "fully_dispensed":  rx.fully_dispensed,
        "status":           rx.status,
        "fills_count":      rx.fills_count,
        "last_fill_date":   str(rx.last_fill_date) if rx.last_fill_date else None,
    }
