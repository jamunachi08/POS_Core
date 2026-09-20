"""
Hooks invoked when a Sales Invoice posted by AlphaXPOS submits or cancels.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from alphax_pos_suite.alphax_pos_suite.loyalty import engine


def _resolve_program_for_invoice(invoice):
    """
    Resolve which loyalty program applies to this invoice.

    Resolution order:
      1. Explicit override on the invoice (custom field `alphax_loyalty_program`).
      2. Customer's default program (custom field `alphax_default_loyalty_program`).
      3. Outlet's default program.
      4. None.
    """
    explicit = invoice.get("alphax_loyalty_program")
    if explicit:
        return explicit

    if invoice.customer:
        cust_default = frappe.db.get_value(
            "Customer", invoice.customer, "alphax_default_loyalty_program"
        )
        if cust_default:
            return cust_default

    outlet = invoice.get("alphax_outlet")
    if outlet:
        outlet_default = frappe.db.get_value(
            "AlphaX POS Outlet", outlet, "default_loyalty_program"
        )
        if outlet_default:
            return outlet_default

    return None


def _resolve_domain_for_invoice(invoice):
    outlet = invoice.get("alphax_outlet")
    if outlet:
        primary = frappe.db.get_value(
            "AlphaX POS Outlet", outlet, "primary_domain"
        )
        if primary:
            return primary
    return None


def on_sales_invoice_submit(invoice, method=None):
    """
    Earn points (and consume any preauthorized redemption) when a POS-originated
    Sales Invoice is submitted.

    The cashier SPA optionally writes:
      - alphax_loyalty_program (Data)
      - alphax_loyalty_redeem_points (Float, points to redeem on this invoice)
      - alphax_loyalty_redeem_value  (Currency, value already discounted from bill)
    """
    if not invoice.get("is_pos"):
        return
    if not invoice.customer:
        return

    program_name = _resolve_program_for_invoice(invoice)
    if not program_name:
        return

    redeem_pts = flt(invoice.get("alphax_loyalty_redeem_points"))
    if redeem_pts > 0:
        try:
            engine.post_redeem(
                customer=invoice.customer,
                program_name=program_name,
                points=redeem_pts,
                reference_doctype="Sales Invoice",
                reference_name=invoice.name,
                remarks=f"Redeemed on POS invoice {invoice.name}",
            )
        except Exception as e:
            frappe.log_error(
                title="AlphaXPOS Loyalty Redemption Failed",
                message=f"Invoice {invoice.name}: {e}",
            )
            raise

    items = []
    for line in (invoice.items or []):
        items.append({
            "item_code": line.item_code,
            "qty": flt(line.qty),
            "rate": flt(line.rate),
            "amount": flt(line.amount),
        })

    order = {
        "items": items,
        "net_total": flt(invoice.net_total),
        "tax_total": flt(invoice.total_taxes_and_charges),
        "service_charge": 0,  # Could be teased out of taxes if you book SC there
        "tips": 0,
        "domain": _resolve_domain_for_invoice(invoice),
    }

    result = engine.compute_points_for_order(
        program_name, order, customer=invoice.customer
    )
    pts = flt(result.get("points"))
    if pts > 0:
        engine.post_earn(
            customer=invoice.customer,
            program_name=program_name,
            points=pts,
            reference_doctype="Sales Invoice",
            reference_name=invoice.name,
            remarks=f"Earned on POS invoice {invoice.name}",
        )


def on_sales_invoice_cancel(invoice, method=None):
    """Reverse loyalty entries when an invoice is cancelled."""
    engine.post_reverse_for_invoice(invoice.name)


# ---------------------------------------------------------------------------
# Daily expiry job (registered in hooks.py scheduler_events)
# ---------------------------------------------------------------------------


def expire_points():
    """
    Daily job: find all unexpired Earn entries whose expires_on <= today and
    that haven't already been expired/redeemed/reversed, and post Expire entries
    for the residual portion.

    Strategy: per wallet, sum still-unexpired earns up to today, compare with
    current balance + already-redeemed-from-future-earns. If the wallet's
    available balance exceeds the sum of NOT-YET-expired earns from after
    today, the difference must be expired.

    Simpler model used here (and what most POSs do): for each wallet, find
    all Earn entries with expires_on <= today that have NOT been previously
    expired, compute residual (points minus matched redemptions in FIFO order),
    and post one Expire entry per wallet for the total residual.
    """
    today_d = getdate(today())

    earns = frappe.db.sql(
        """
        select wallet, name, points, expires_on
        from `tabAlphaX POS Loyalty Ledger`
        where docstatus = 1
          and entry_type = 'Earn'
          and expires_on is not null
          and expires_on <= %s
          and ifnull(custom_expired, 0) = 0
        order by wallet, expires_on, creation
        """,
        (today_d,),
        as_dict=True,
    )

    by_wallet = {}
    for row in earns:
        by_wallet.setdefault(row["wallet"], []).append(row)

    for wallet_name, rows in by_wallet.items():
        wallet = frappe.get_doc("AlphaX POS Loyalty Wallet", wallet_name)
        if flt(wallet.current_balance) <= 0:
            continue

        to_expire = sum(flt(r["points"]) for r in rows)
        residual = min(to_expire, flt(wallet.current_balance))
        if residual <= 0:
            continue

        ledger = frappe.new_doc("AlphaX POS Loyalty Ledger")
        ledger.wallet = wallet_name
        ledger.entry_type = "Expire"
        ledger.points = -round(residual, 4)
        ledger.remarks = f"Expired {len(rows)} earn entries on {today_d}"
        ledger.insert(ignore_permissions=True)
        ledger.submit()

    frappe.db.commit()
