"""
ZATCA soft-adapter.

Wires the AlphaX POS Core to the AlphaX ZATCA app — but only when both
are installed AND the outlet has opted in. This file always loads
cleanly: the import of `alphax_zatca` is guarded so that POS Core works
fine on installs that don't have ZATCA, and ZATCA works fine on installs
that don't have POS Core.

How it fires:

  1. POS Core's hooks.py registers `on_pos_invoice_submit` as part of
     the Sales Invoice on_submit chain.
  2. When a Sales Invoice from a POS Outlet is submitted, this function
     runs.
  3. It checks: is alphax_zatca importable? If no, return (no-op).
  4. It checks: does the Outlet have `zatca_enabled` = 1? If no, return.
  5. It calls into alphax_zatca's submit pipeline. Whatever ZATCA does
     after that — sign, submit, attach QR, log — is upstream's concern.

The Outlet's `zatca_enabled` field is added by the POS Core patch
(see patches/v15_0/upgrade_to_vertical_platform.py).
"""
from __future__ import annotations

import frappe


def is_zatca_app_available() -> bool:
    """Return True only if the alphax_zatca Frappe app is installed and
    importable in this Python environment."""
    try:
        import alphax_zatca  # noqa: F401
        return True
    except ImportError:
        return False


def is_zatca_enabled_for_outlet(outlet_name: str) -> bool:
    """Returns True only when the named Outlet has zatca_enabled = 1.
    Safe to call even when the alphax_zatca app is not installed —
    we read a custom field on AlphaX POS Outlet, which exists in POS
    Core regardless."""
    if not outlet_name:
        return False
    return bool(frappe.db.get_value(
        "AlphaX POS Outlet", outlet_name, "zatca_enabled"
    ))


def on_pos_invoice_submit(doc, method=None):
    """Sales Invoice on_submit hook — fired by POS Core's hooks.py.

    Routes the doc to alphax_zatca for signing + submission only when
    the soft-adapter conditions are met. Failures are caught and logged
    but never break the POS flow — the cashier sale is already done.
    """
    outlet = getattr(doc, "alphax_outlet", None)
    if not outlet:
        return  # not a POS sale

    if not is_zatca_enabled_for_outlet(outlet):
        return  # outlet hasn't opted in

    if not is_zatca_app_available():
        # ZATCA toggle is on but the app isn't installed.
        # Log a warning so the operator notices in misconfiguration.
        frappe.log_error(
            title="AlphaX ZATCA: app not installed",
            message=(f"Outlet {outlet} has zatca_enabled=1 but the "
                     f"alphax_zatca app is not installed. Sales Invoice "
                     f"{doc.name} will not be submitted to ZATCA. "
                     f"Either install alphax_zatca or disable the outlet's "
                     f"ZATCA toggle."),
        )
        return

    # Both apps present and outlet is opted in.
    # Defer the import so a missing alphax_zatca never breaks module load.
    try:
        from alphax_zatca.alphax_zatca.pos_sign import zatca_background_on_submit
        zatca_background_on_submit(doc, method, bypass_background_check=False)
    except Exception as e:
        # Never propagate. The sale is committed; ZATCA submission can be
        # retried via the upstream "Resubmit Failed Invoices" workflow.
        frappe.log_error(
            title=f"AlphaX ZATCA: submission failed for {doc.name}",
            message=str(e),
        )


def get_zatca_status_for_invoice(invoice_name: str) -> dict:
    """Returns a small dict the cashier SPA can poll to show ZATCA status
    on the receipt: {installed, enabled, submitted, error_msg}.

    Cashier UI uses this to render "ZATCA QR pending" / "ZATCA submitted"
    badges next to the invoice number."""
    if not is_zatca_app_available():
        return {"installed": False, "enabled": False,
                "submitted": False, "error_msg": ""}

    outlet = frappe.db.get_value("Sales Invoice", invoice_name, "alphax_outlet")
    enabled = is_zatca_enabled_for_outlet(outlet) if outlet else False

    # Read upstream's status fields (added by upstream's custom-fields seed)
    fields = frappe.db.get_value(
        "Sales Invoice", invoice_name,
        ["custom_zatca_status", "custom_zatca_full_response"],
        as_dict=True,
    ) or {}

    return {
        "installed": True,
        "enabled":   enabled,
        "submitted": fields.get("custom_zatca_status") in ("REPORTED", "CLEARED"),
        "status":    fields.get("custom_zatca_status") or "",
        "error_msg": (fields.get("custom_zatca_full_response") or "")[:500],
    }
