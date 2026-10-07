"""
AlphaX POS — Loyalty Engine

Pure-ish functions that:
  1. Resolve which rule applies to a given line (item / item group / brand / domain).
  2. Compute earn points per line, with tier multipliers and program-level filters.
  3. Post earn / redeem / expire ledger entries atomically.

Design intent
-------------
* All state lives in the ledger. The wallet's balance is a cached projection,
  rebuilt from the ledger on every submit/cancel. There is no way for the
  wallet to drift from the ledger.
* Earn rules are evaluated client-side AND server-side. The cashier SPA shows
  the user "you'll earn 24 points" as items are added; the server recomputes
  on Sales Invoice submit. The two should agree, but the server is the source
  of truth.
* Multiple programs are first-class. A customer can have wallets in several
  programs (one per business / domain). The cashier picks the right one based
  on outlet's primary domain and item's domain scope.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days, now_datetime


# ---------------------------------------------------------------------------
# Rule resolution
# ---------------------------------------------------------------------------

# Default priority by scope (lower = wins). Tie-broken by explicit `priority`
# field on the rule, then by row order.
_SCOPE_PRIORITY = {
    "Item": 10,
    "Item Group": 20,
    "Brand": 30,
    "Domain": 40,
    "No Earn": 5,  # No Earn always wins if it matches
}


def _item_meta_cache(item_code):
    """Single Item read with item_group and brand. Cached per request."""
    if not item_code:
        return {"item_group": None, "brand": None}
    cache = frappe.local.cache.setdefault("_alphax_loyalty_item_meta", {})
    if item_code not in cache:
        row = frappe.db.get_value(
            "Item",
            item_code,
            ["item_group", "brand"],
            as_dict=True,
        ) or {"item_group": None, "brand": None}
        cache[item_code] = row
    return cache[item_code]


def _item_group_ancestors(item_group):
    """Return [item_group, parent, grandparent, ...] using nested-set lft/rgt."""
    if not item_group:
        return []
    cache = frappe.local.cache.setdefault("_alphax_ig_ancestors", {})
    if item_group in cache:
        return cache[item_group]

    target = frappe.db.get_value(
        "Item Group", item_group, ["lft", "rgt"], as_dict=True
    )
    if not target:
        cache[item_group] = [item_group]
        return [item_group]

    rows = frappe.db.sql(
        """
        select name
        from `tabItem Group`
        where lft <= %s and rgt >= %s
        order by lft desc
        """,
        (target["lft"], target["rgt"]),
        as_dict=True,
    )
    chain = [r["name"] for r in rows]
    cache[item_group] = chain
    return chain


def _rule_matches(rule, item_code, item_meta, domain):
    """True iff this rule applies to this line."""
    today = getdate()
    if rule.valid_from and getdate(rule.valid_from) > today:
        return False
    if rule.valid_to and getdate(rule.valid_to) < today:
        return False

    if rule.scope == "Item":
        return rule.item_code and rule.item_code == item_code
    if rule.scope == "Item Group":
        if not rule.item_group or not item_meta.get("item_group"):
            return False
        return rule.item_group in _item_group_ancestors(item_meta["item_group"])
    if rule.scope == "Brand":
        return rule.brand and rule.brand == item_meta.get("brand")
    if rule.scope == "Domain":
        return rule.domain and rule.domain == domain
    if rule.scope == "No Earn":
        # "No Earn" rule needs an item or item_group to be useful
        if rule.item_code:
            return rule.item_code == item_code
        if rule.item_group and item_meta.get("item_group"):
            return rule.item_group in _item_group_ancestors(item_meta["item_group"])
        return False
    return False


def find_rule_for_item(program, item_code, domain=None):
    """
    Return the highest-priority rule that matches this item, or None if no
    rule matches (caller should then use program defaults).
    """
    if not program or not getattr(program, "rules", None):
        return None

    item_meta = _item_meta_cache(item_code)
    matches = []
    for idx, rule in enumerate(program.rules):
        if _rule_matches(rule, item_code, item_meta, domain):
            scope_pri = _SCOPE_PRIORITY.get(rule.scope, 99)
            explicit_pri = flt(rule.priority) if rule.priority is not None else 10
            matches.append((scope_pri, explicit_pri, idx, rule))

    if not matches:
        return None
    matches.sort(key=lambda t: (t[0], t[1], t[2]))
    return matches[0][3]


# ---------------------------------------------------------------------------
# Point computation
# ---------------------------------------------------------------------------


def _earn_for_line(program, rule, line, tier_multiplier=1.0):
    """
    Compute points earned on a single order line.

    line: dict with keys item_code, qty, amount (line total before tax),
          rate (unit price). 'amount' is the source of truth for currency-based earn.
    """
    if rule and rule.scope == "No Earn":
        return 0.0

    if rule:
        basis = rule.earn_basis or "Use Program Default"
        if basis == "Use Program Default":
            basis = program.earn_basis or "Per Currency Spent"
        points_per_unit = flt(rule.points) or 0.0
        per_amount = flt(rule.per_amount) or 1.0
        rule_mult = flt(rule.multiplier) if rule.multiplier else 1.0
    else:
        basis = program.earn_basis or "Per Currency Spent"
        points_per_unit = flt(program.default_earn_points) or 0.0
        per_amount = flt(program.default_earn_per_amount) or 1.0
        rule_mult = 1.0

    qty = flt(line.get("qty"))
    amount = flt(line.get("amount"))

    if basis == "Per Currency Spent":
        if per_amount <= 0:
            per_amount = 1.0
        raw = (amount / per_amount) * points_per_unit
    elif basis == "Per Item Quantity":
        raw = qty * points_per_unit
    elif basis == "Fixed Per Line":
        raw = points_per_unit
    elif basis == "Per Visit":
        # Per Visit is handled at the order level, not per line
        raw = 0.0
    else:
        raw = 0.0

    return raw * rule_mult * (tier_multiplier or 1.0)


def compute_points_for_order(program_name, order, customer=None):
    """
    Compute total points to be earned on this order.

    program_name: AlphaX POS Loyalty Program name
    order: dict {
        items: [ {item_code, qty, rate, amount}, ... ],
        net_total, tax_total, service_charge, tips,
        domain  (optional, for domain-scoped rules)
    }
    customer: optional Customer name (used to resolve current tier)

    Returns dict { points, breakdown: [{item_code, points, rule_used}], ... }
    """
    program = frappe.get_cached_doc("AlphaX POS Loyalty Program", program_name)
    if not program.enabled:
        return {"points": 0.0, "breakdown": [], "reason": "program_disabled"}

    domain = order.get("domain")
    if (
        program.domain_scope
        and program.domain_scope != "All Domains"
        and domain
        and program.domain_scope != domain
    ):
        return {"points": 0.0, "breakdown": [], "reason": "domain_out_of_scope"}

    if (
        program.min_purchase_to_earn
        and flt(order.get("net_total")) < flt(program.min_purchase_to_earn)
    ):
        return {"points": 0.0, "breakdown": [], "reason": "below_min_purchase"}

    tier_multiplier = 1.0
    tier_name = None
    if customer:
        wallet = frappe.db.get_value(
            "AlphaX POS Loyalty Wallet",
            {"customer": customer, "program": program_name},
            ["name", "current_tier", "lifetime_earned"],
            as_dict=True,
        )
        if wallet and wallet.current_tier:
            for t in (program.tiers or []):
                if t.tier_name == wallet.current_tier:
                    tier_multiplier = flt(t.earn_multiplier) or 1.0
                    tier_name = t.tier_name
                    break

    breakdown = []
    total = 0.0

    if (program.earn_basis or "Per Currency Spent") == "Per Visit":
        pts = flt(program.default_earn_points) * tier_multiplier
        total += pts
        breakdown.append(
            {"item_code": None, "points": pts, "rule_used": "per_visit"}
        )
    else:
        for line in order.get("items") or []:
            rule = find_rule_for_item(program, line.get("item_code"), domain=domain)
            pts = _earn_for_line(program, rule, line, tier_multiplier=tier_multiplier)
            if pts:
                total += pts
                breakdown.append(
                    {
                        "item_code": line.get("item_code"),
                        "points": round(pts, 4),
                        "rule_used": rule.scope if rule else "program_default",
                    }
                )

    if program.earn_on_service_charge and order.get("service_charge"):
        sc = flt(order["service_charge"])
        per_amt = flt(program.default_earn_per_amount) or 1.0
        pts = (sc / per_amt) * flt(program.default_earn_points) * tier_multiplier
        total += pts
        breakdown.append(
            {"item_code": None, "points": round(pts, 4), "rule_used": "service_charge"}
        )

    if program.earn_on_tips and order.get("tips"):
        t = flt(order["tips"])
        per_amt = flt(program.default_earn_per_amount) or 1.0
        pts = (t / per_amt) * flt(program.default_earn_points) * tier_multiplier
        total += pts
        breakdown.append(
            {"item_code": None, "points": round(pts, 4), "rule_used": "tips"}
        )

    if program.earn_on_tax and order.get("tax_total"):
        tx = flt(order["tax_total"])
        per_amt = flt(program.default_earn_per_amount) or 1.0
        pts = (tx / per_amt) * flt(program.default_earn_points) * tier_multiplier
        total += pts
        breakdown.append(
            {"item_code": None, "points": round(pts, 4), "rule_used": "tax"}
        )

    return {
        "points": round(total, 4),
        "breakdown": breakdown,
        "tier": tier_name,
        "tier_multiplier": tier_multiplier,
    }


# ---------------------------------------------------------------------------
# Redemption preview
# ---------------------------------------------------------------------------


def preview_redemption(program_name, customer, points_to_redeem, bill_total):
    """
    Validate a redemption attempt and return the cash equivalent.
    Does NOT mutate state. Use post_redeem() to actually deduct.
    """
    program = frappe.get_cached_doc("AlphaX POS Loyalty Program", program_name)
    if not program.enabled:
        frappe.throw(_("Loyalty program is disabled."))

    pts = flt(points_to_redeem)
    if pts <= 0:
        return {"points": 0, "value": 0}

    if pts < flt(program.min_points_to_redeem or 0):
        frappe.throw(
            _("Minimum {0} points required to redeem.").format(
                int(program.min_points_to_redeem or 0)
            )
        )

    wallet = frappe.db.get_value(
        "AlphaX POS Loyalty Wallet",
        {"customer": customer, "program": program_name},
        ["name", "current_balance", "current_tier"],
        as_dict=True,
    )
    if not wallet:
        frappe.throw(_("Customer is not enrolled in this program."))
    if pts > flt(wallet.current_balance):
        frappe.throw(
            _("Insufficient points. Available: {0}, requested: {1}.").format(
                wallet.current_balance, pts
            )
        )

    redeem_value_mult = 1.0
    if wallet.current_tier:
        for t in (program.tiers or []):
            if t.tier_name == wallet.current_tier:
                redeem_value_mult = flt(t.redeem_value_multiplier) or 1.0
                break

    value = pts * flt(program.redemption_value or 0) * redeem_value_mult
    cap_pct = flt(program.max_redeem_percent or 100) / 100.0
    cap = flt(bill_total) * cap_pct
    if value > cap:
        max_points = (cap / (flt(program.redemption_value or 0) * redeem_value_mult)) if program.redemption_value else 0
        frappe.throw(
            _("Redemption capped at {0}% of bill ({1}). Max points usable: {2}.").format(
                program.max_redeem_percent, cap, int(max_points)
            )
        )

    return {
        "wallet": wallet.name,
        "points": pts,
        "value": round(value, 2),
        "redeem_value_multiplier": redeem_value_mult,
    }


# ---------------------------------------------------------------------------
# Ledger posting (state-mutating)
# ---------------------------------------------------------------------------


def _ensure_wallet(customer, program_name, card_number=None):
    """Get or create a wallet for this (customer, program). Idempotent."""
    name = frappe.db.exists(
        "AlphaX POS Loyalty Wallet",
        {"customer": customer, "program": program_name},
    )
    if name:
        return frappe.get_doc("AlphaX POS Loyalty Wallet", name)

    wallet = frappe.new_doc("AlphaX POS Loyalty Wallet")
    wallet.customer = customer
    wallet.program = program_name
    if card_number:
        wallet.card_number = card_number
    wallet.insert(ignore_permissions=True)
    return wallet


def post_earn(
    customer,
    program_name,
    points,
    reference_doctype=None,
    reference_name=None,
    remarks=None,
):
    """Submit an Earn ledger entry. Returns the ledger doc."""
    if flt(points) <= 0:
        return None

    wallet = _ensure_wallet(customer, program_name)
    program = frappe.get_cached_doc("AlphaX POS Loyalty Program", program_name)

    expires_on = None
    if program.expiry_days and int(program.expiry_days) > 0:
        expires_on = add_days(now_datetime().date(), int(program.expiry_days))

    ledger = frappe.new_doc("AlphaX POS Loyalty Ledger")
    ledger.wallet = wallet.name
    ledger.entry_type = "Earn"
    ledger.points = round(flt(points), 4)
    ledger.reference_doctype = reference_doctype
    ledger.reference_name = reference_name
    ledger.expires_on = expires_on
    ledger.remarks = remarks
    ledger.insert(ignore_permissions=True)
    ledger.submit()
    return ledger


def post_redeem(
    customer,
    program_name,
    points,
    reference_doctype=None,
    reference_name=None,
    remarks=None,
):
    """Submit a Redeem ledger entry. Throws on insufficient balance."""
    if flt(points) <= 0:
        return None

    wallet_name = frappe.db.exists(
        "AlphaX POS Loyalty Wallet",
        {"customer": customer, "program": program_name},
    )
    if not wallet_name:
        frappe.throw(_("Customer is not enrolled in {0}.").format(program_name))

    ledger = frappe.new_doc("AlphaX POS Loyalty Ledger")
    ledger.wallet = wallet_name
    ledger.entry_type = "Redeem"
    ledger.points = -round(flt(points), 4)
    ledger.reference_doctype = reference_doctype
    ledger.reference_name = reference_name
    ledger.remarks = remarks
    ledger.insert(ignore_permissions=True)
    ledger.submit()
    return ledger


def post_reverse_for_invoice(invoice_name):
    """
    Reverse all loyalty entries linked to a specific Sales Invoice.
    Called when an invoice is cancelled or fully credited.
    """
    entries = frappe.get_all(
        "AlphaX POS Loyalty Ledger",
        filters={
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice_name,
            "docstatus": 1,
        },
        fields=["name", "points", "wallet", "entry_type"],
    )
    for e in entries:
        rev = frappe.new_doc("AlphaX POS Loyalty Ledger")
        rev.wallet = e["wallet"]
        rev.entry_type = "Reverse"
        rev.points = -flt(e["points"])
        rev.reference_doctype = "Sales Invoice"
        rev.reference_name = invoice_name
        rev.remarks = f"Reverse of {e['name']} (invoice cancelled)"
        rev.insert(ignore_permissions=True)
        rev.submit()


# ---------------------------------------------------------------------------
# Whitelisted endpoints (called by the cashier SPA)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def quote_points(program, items, net_total=0, tax_total=0, service_charge=0, tips=0,
                 domain=None, customer=None):
    """Live preview from the cashier SPA. Read-only."""
    import json
    if isinstance(items, str):
        items = json.loads(items)
    order = {
        "items": items or [],
        "net_total": flt(net_total),
        "tax_total": flt(tax_total),
        "service_charge": flt(service_charge),
        "tips": flt(tips),
        "domain": domain,
    }
    return compute_points_for_order(program, order, customer=customer)


@frappe.whitelist()
def lookup_wallet(card_number=None, customer=None, program=None):
    """Cashier scans a loyalty card or types customer name."""
    filters = {}
    if card_number:
        filters["card_number"] = card_number
    if customer:
        filters["customer"] = customer
    if program:
        filters["program"] = program
    if not filters:
        frappe.throw(_("Provide card_number or customer."))

    wallets = frappe.get_all(
        "AlphaX POS Loyalty Wallet",
        filters=filters,
        fields=[
            "name",
            "customer",
            "program",
            "card_number",
            "current_balance",
            "lifetime_earned",
            "current_tier",
        ],
    )
    return wallets


@frappe.whitelist()
def quote_redemption(program, customer, points, bill_total):
    """Live preview before the cashier locks in a redemption."""
    return preview_redemption(program, customer, flt(points), flt(bill_total))
