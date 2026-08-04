"""
Pharmacy clinical validator.

Runs over an AlphaX Prescription document and returns a list of
warning strings. Drives:

  - Drug-drug interaction warnings (looks up AlphaX Drug Interaction Rule)
  - Maximum daily dose checks (per AlphaX Drug Master.max_daily_dose)
  - Minimum age checks (per AlphaX Drug Master.min_age_years)
  - Pregnancy category warnings (when patient is_pregnant=1 and a drug is C/D/X)
  - Refill limit checks (controlled substances cap at 2 refills per
    initial prescription per most regulators; non-controlled at 5)

Returns warnings as plain text strings, prefixed with severity:

    "🟥 MAJOR — Warfarin + Aspirin: bleeding risk"
    "🟧 MODERATE — Atorvastatin: dose 80mg/day exceeds max 40mg/day"
    "🟨 MINOR — Ibuprofen: not recommended under 6 months"

The cashier UI shows these on the Rx capture screen so the pharmacist
can decide whether to dispense, override, or call the prescriber.

Validator does NOT block dispensing. The pharmacist is the legal
decision-maker. Warnings are advisory and audit-logged.
"""
from __future__ import annotations

import frappe


SEVERITY_ICONS = {
    "Contraindicated": "🟥 CONTRAINDICATED",
    "Major":           "🟥 MAJOR",
    "Moderate":        "🟧 MODERATE",
    "Minor":           "🟨 MINOR",
}

# Refill caps per regulatory norm. Customizable via AlphaX POS Settings
# in a future iteration; hard-coded here for clarity.
REFILL_CAP_CONTROLLED = 2
REFILL_CAP_OTHER = 5


def validate_prescription(prescription) -> list[str]:
    """Run every check over the prescription. Returns a list of
    user-facing warning strings (potentially empty)."""
    warnings: list[str] = []

    # Build the drug list once
    drugs = []
    for line in prescription.lines or []:
        if not line.drug:
            continue
        drug_doc = frappe.get_cached_doc("AlphaX Drug Master", line.drug)
        drugs.append((line, drug_doc))

    # Check 1: drug-drug interactions
    warnings.extend(_check_interactions(drugs))

    # Check 2: max daily dose
    for line, drug in drugs:
        w = _check_max_daily_dose(line, drug)
        if w: warnings.append(w)

    # Check 3: min age
    if prescription.patient_age is not None:
        for line, drug in drugs:
            w = _check_min_age(prescription, line, drug)
            if w: warnings.append(w)

    # Check 4: pregnancy
    if getattr(prescription, "is_pregnant", 0):
        for line, drug in drugs:
            w = _check_pregnancy(line, drug)
            if w: warnings.append(w)

    # Check 5: refill caps
    for line, drug in drugs:
        w = _check_refill_cap(line, drug)
        if w: warnings.append(w)

    # Check 6: requires_prescription compliance — every dispensed drug
    # in a Prescription doc passes this trivially. The check is here
    # as a defense for the unlikely case where a drug's
    # requires_prescription flag changes after the script is written.
    # No-op for now.

    return warnings


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_interactions(drugs) -> list[str]:
    """Pairwise interaction lookup. O(n²) over drugs in the prescription;
    n is typically <= 5 so this is fine."""
    warnings = []
    seen_pairs = set()
    for i, (line_a, drug_a) in enumerate(drugs):
        for line_b, drug_b in drugs[i + 1:]:
            pair = tuple(sorted([drug_a.name, drug_b.name]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            rules = frappe.get_all(
                "AlphaX Drug Interaction Rule",
                filters=[
                    ["active", "=", 1],
                    [
                        "OR",
                        [["drug_a", "=", drug_a.name], ["drug_b", "=", drug_b.name]],
                        [["drug_a", "=", drug_b.name], ["drug_b", "=", drug_a.name]],
                    ],
                ],
                fields=["name", "severity", "message"],
            )
            for rule in rules:
                icon = SEVERITY_ICONS.get(rule["severity"], rule["severity"])
                warnings.append(
                    f"{icon} — {drug_a.drug_name} + {drug_b.drug_name}: {rule['message']}"
                )
    return warnings


def _check_max_daily_dose(line, drug) -> str | None:
    if drug.max_daily_dose is None or drug.max_daily_dose == 0:
        return None
    daily = (line.dose or 0) * (line.frequency_per_day or 0)
    if daily > drug.max_daily_dose:
        unit = drug.max_daily_dose_unit or line.dose_unit or ""
        return (
            f"🟧 MODERATE — {drug.drug_name}: prescribed daily dose "
            f"{daily:g}{unit} exceeds max {drug.max_daily_dose:g}{unit}"
        )
    return None


def _check_min_age(prescription, line, drug) -> str | None:
    if not drug.min_age_years:
        return None
    if (prescription.patient_age or 0) < drug.min_age_years:
        return (
            f"🟨 MINOR — {drug.drug_name}: not recommended under "
            f"{drug.min_age_years} years (patient is {prescription.patient_age})"
        )
    return None


def _check_pregnancy(line, drug) -> str | None:
    cat = drug.pregnancy_category
    if cat in ("C", "D", "X"):
        msg = {
            "C": "🟧 MODERATE",
            "D": "🟥 MAJOR",
            "X": "🟥 CONTRAINDICATED",
        }[cat]
        return (
            f"{msg} — {drug.drug_name}: pregnancy category {cat}. "
            f"Patient is flagged as pregnant."
        )
    return None


def _check_refill_cap(line, drug) -> str | None:
    cap = REFILL_CAP_CONTROLLED if drug.is_controlled else REFILL_CAP_OTHER
    if (line.refills_allowed or 0) > cap:
        kind = "controlled substance" if drug.is_controlled else "drug"
        return (
            f"🟨 MINOR — {drug.drug_name}: {line.refills_allowed} refills "
            f"exceeds the regulatory cap of {cap} for a {kind}."
        )
    return None


# ---------------------------------------------------------------------------
# Cashier-side helper: validate a drug being added to the cart
# ---------------------------------------------------------------------------


def can_dispense_drug(drug_code: str, prescription_name: str | None) -> dict:
    """Return whether an item-being-added-to-cart can be sold without a
    prescription. Used by the cashier SPA when scanning an item that
    happens to be a controlled or prescription-only drug.

    Returns:
        {
            "ok":         True/False,
            "needs_rx":   True/False,
            "is_controlled": True/False,
            "reason":     "..."
        }
    """
    drug = frappe.db.get_value(
        "AlphaX Drug Master",
        {"drug_code": drug_code},
        ["name", "drug_name", "is_controlled", "requires_prescription"],
        as_dict=True,
    )
    if not drug:
        return {"ok": True, "needs_rx": False, "is_controlled": False,
                "reason": "Not a registered drug; treat as regular item."}

    if not drug["requires_prescription"]:
        return {"ok": True, "needs_rx": False,
                "is_controlled": bool(drug["is_controlled"]),
                "reason": "OTC drug; no prescription required."}

    if not prescription_name:
        return {"ok": False, "needs_rx": True,
                "is_controlled": bool(drug["is_controlled"]),
                "reason": f"{drug['drug_name']} requires a valid prescription."}

    # Check the prescription is active and contains this drug.
    rx = frappe.get_doc("AlphaX Prescription", prescription_name)
    if rx.status not in ("Active", "Partially Dispensed"):
        return {"ok": False, "needs_rx": True,
                "is_controlled": bool(drug["is_controlled"]),
                "reason": f"Prescription {rx.name} is {rx.status}, not dispensable."}

    if rx.expiry_date and frappe.utils.getdate(rx.expiry_date) < frappe.utils.getdate(frappe.utils.today()):
        return {"ok": False, "needs_rx": True,
                "is_controlled": bool(drug["is_controlled"]),
                "reason": f"Prescription {rx.name} expired on {rx.expiry_date}."}

    has_drug = any(line.drug == drug["name"] for line in rx.lines)
    if not has_drug:
        return {"ok": False, "needs_rx": True,
                "is_controlled": bool(drug["is_controlled"]),
                "reason": f"{drug['drug_name']} is not on prescription {rx.name}."}

    return {"ok": True, "needs_rx": True,
            "is_controlled": bool(drug["is_controlled"]),
            "reason": "Authorized by prescription."}
