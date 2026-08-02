from __future__ import annotations

import frappe

no_cache = 1


def _card_for_token(tok: str):
    d = frappe.db.get_value(
        "AlphaX POS QR Table Token",
        {"token": tok, "is_active": 1},
        ["table", "outlet", "token"],
        as_dict=True,
    )
    if not d:
        return None
    outlet_name = ""
    if d.outlet:
        outlet_name = frappe.db.get_value("AlphaX POS Outlet", d.outlet, "outlet_name") or d.outlet
    return {
        "table": d.table,
        "outlet": outlet_name,
        "token": d.token,
        "url": frappe.utils.get_url() + "/bonanza_order?token=" + d.token,
    }


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/table_qr"
        raise frappe.Redirect

    token = frappe.form_dict.get("token")
    table = frappe.form_dict.get("table")
    outlet = frappe.form_dict.get("outlet")
    cards = []

    if token:
        c = _card_for_token(token)
        if c:
            cards.append(c)
    elif table:
        tok = frappe.db.get_value(
            "AlphaX POS QR Table Token", {"table": table, "is_active": 1}, "token"
        )
        if tok:
            c = _card_for_token(tok)
            if c:
                cards.append(c)
    elif outlet:
        tables = frappe.get_all(
            "AlphaX POS Table",
            filters={"outlet": outlet},
            pluck="name",
            order_by="table_code asc",
        )
        for t in tables:
            tok = frappe.db.get_value(
                "AlphaX POS QR Table Token", {"table": t, "is_active": 1}, "token"
            )
            if tok:
                c = _card_for_token(tok)
                if c:
                    cards.append(c)

    context.cards_json = frappe.as_json(cards)
    context.card_count = len(cards)
    context.no_cache = 1
    context.show_sidebar = False
    return context
