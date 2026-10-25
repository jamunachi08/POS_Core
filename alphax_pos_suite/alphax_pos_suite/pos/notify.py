"""Close notifications: shift close and day close, to nominated persons.

Recipients live on the outlet (AlphaX POS Notify Recipient child table),
each with a channel. Email sends natively. WhatsApp and SMS post to a
configurable gateway webhook (AlphaX POS Settings → notify_gateway_url,
with {phone} and {message} placeholders) so any provider — Unifonic,
Twilio, a WhatsApp Business API relay — plugs in without code changes.
Notification failures are logged, never raised: closing a shift must
not depend on a webhook being up.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt


def _recipients(outlet: str | None, event: str):
    if not outlet:
        return []
    doc = frappe.get_cached_doc("AlphaX POS Outlet", outlet)
    flag = "on_shift_close" if event == "shift" else "on_day_close"
    return [r for r in (doc.get("notify_recipients") or []) if r.get(flag)]


def _fmt_money(v):
    return f"SAR {flt(v):,.2f}"


def _send(recipient, subject: str, body: str):
    try:
        if recipient.channel == "Email":
            frappe.sendmail(recipients=[recipient.address], subject=subject, message=body.replace("\n", "<br>"))
            return
        gateway = None
        try:
            gateway = frappe.db.get_single_value("AlphaX POS Settings", "notify_gateway_url")
        except Exception:
            pass
        if not gateway:
            frappe.logger().info(
                f"AlphaX POS notify: no gateway configured; skipped {recipient.channel} to {recipient.address}"
            )
            return
        url = gateway.replace("{phone}", recipient.address).replace(
            "{message}", frappe.utils.quote(f"{subject}\n{body}")
        )
        frappe.enqueue(
            "frappe.integrations.utils.make_get_request",
            queue="short", url=url, enqueue_after_commit=True,
        )
    except Exception:
        frappe.log_error(title="AlphaX POS: notification failed", message=frappe.get_traceback())


def notify_shift_close(summary: dict, outlet: str | None):
    try:
        subject = _("Shift closed — {0}").format(summary.get("shift"))
        body = _(
            "Terminal: {0}\nCashier: {1}\nTrading day: {2}\n"
            "Net sales: {3}\nReturns: {4}\nVAT: {5}\n"
            "Counted cash: {6}\nOver/Short: {7}"
        ).format(
            summary.get("terminal") or "", summary.get("user") or "",
            summary.get("business_date") or "",
            _fmt_money(summary.get("net_sales")), _fmt_money(summary.get("returns")),
            _fmt_money(summary.get("vat")), _fmt_money(summary.get("counted_cash")),
            _fmt_money(summary.get("variance")),
        )
        for r in _recipients(outlet, "shift"):
            _send(r, subject, body)
    except Exception:
        frappe.log_error(title="AlphaX POS: shift-close notify failed", message=frappe.get_traceback())


def notify_day_close(dc, shift_summaries: list[dict], outlet: str | None):
    try:
        subject = _("Day close — {0} ({1})").format(dc.pos_terminal, dc.posting_date)
        lines = [
            _("Sales: {0} · Returns: {1} · Net: {2} · VAT: {3}").format(
                _fmt_money(dc.sales_value), _fmt_money(dc.return_value),
                _fmt_money(dc.net_sales), _fmt_money(dc.get("vat_amount")),
            ),
            "",
            _("Shift-wise:"),
        ]
        for s in shift_summaries:
            lines.append(
                f"  {s.get('shift')}: {s.get('user')} — net {_fmt_money(s.get('net_sales'))}, "
                f"over/short {_fmt_money(s.get('variance'))}"
            )
        body = "\n".join(lines)
        for r in _recipients(outlet, "day"):
            _send(r, subject, body)
    except Exception:
        frappe.log_error(title="AlphaX POS: day-close notify failed", message=frappe.get_traceback())
