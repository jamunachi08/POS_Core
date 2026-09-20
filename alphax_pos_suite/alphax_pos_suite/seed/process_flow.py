# -*- coding: utf-8 -*-
"""Seeds the AlphaX POS end-to-end process flow.

Nodes deliberately mix AlphaX POS documents with the stock ERPNext
documents the process depends on. That mix is the point: the board shows
an operator the whole cycle including the parts the suite did not invent,
and it is the plainest available answer to "what does the POS actually
post into?"

Idempotent. Re-running updates labels, sequences and roles in place and
never duplicates a node. Nodes an administrator disabled by hand stay
disabled — the seeder does not re-enable them.
"""

import json

import frappe

FLOW_NAME = "AlphaX POS End-to-End Process"

# --------------------------------------------------------------------------
# Roles. A node with an empty role list falls through to the permission
# check in flow_api, which is the real gate.
# --------------------------------------------------------------------------

ADM = ["System Manager"]
MGR = ["AlphaX POS Manager", "System Manager"]
SUP = ["AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"]
CSH = ["AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager", "System Manager"]
KIT = ["AlphaX POS Kitchen", "AlphaX POS Manager", "System Manager"]
ACC = ["Accounts Manager", "System Manager"]

# --------------------------------------------------------------------------
# (stage_key, label, label_ar, lane, actor, sequence, colour)
# --------------------------------------------------------------------------

STAGES = [
    ("A1", "Company & Outlet", "الشركة والمنفذ", "Setup", "Administrator", 1, "#12303F"),
    ("A2", "Terminals & Hardware", "الأجهزة والطرفيات", "Setup", "Administrator", 2, "#12303F"),
    ("A3", "Catalogue & Pricing", "الأصناف والتسعير", "Setup", "Administrator", 3, "#12303F"),
    ("A4", "Menus, Combos & Offers", "القوائم والعروض", "Setup", "Administrator", 4, "#12303F"),
    ("A5", "People & Access", "المستخدمون والصلاحيات", "Setup", "Administrator", 5, "#12303F"),

    ("B1", "Shift Open", "فتح الوردية", "Open", "Cashier / Supervisor", 6, "#1B7F79"),
    ("B2", "Floor & Order Type", "الصالة ونوع الطلب", "Open", "Cashier", 7, "#1B7F79"),

    ("C1", "Build the Order", "بناء الطلب", "Sell", "Cashier", 8, "#1D5B96"),
    ("C2", "Kitchen Routing", "توجيه المطبخ", "Sell", "System", 9, "#1D5B96"),
    ("C3", "Payment", "الدفع", "Sell", "Cashier", 10, "#1D5B96"),
    ("C4", "Post & Fiscalise", "الترحيل والفوترة", "Sell", "System", 11, "#1D5B96"),

    ("D1", "Kitchen Preparation", "تحضير المطبخ", "Serve", "Kitchen", 12, "#7A4FA3"),
    ("D2", "Guest Ordering", "طلب الضيف", "Serve", "Customer", 13, "#7A4FA3"),

    ("E1", "Authorisation", "التفويض", "Control", "Manager", 14, "#A86A12"),
    ("E2", "Returns & Store Credit", "المرتجعات ورصيد المتجر", "Control", "Manager", 15, "#A86A12"),
    ("E3", "Cash Movement", "حركة النقد", "Control", "Supervisor / Manager", 16, "#A86A12"),

    ("F1", "Shift Close", "إقفال الوردية", "Close", "Cashier / Supervisor", 17, "#1F6F45"),
    ("F2", "Day Close", "إقفال اليوم", "Close", "Supervisor / Manager", 18, "#1F6F45"),
    ("F3", "Reporting & Notification", "التقارير والإشعارات", "Close", "Manager", 19, "#1F6F45"),

    ("G1", "Revenue Posting", "ترحيل الإيراد", "Finance", "Accounts", 20, "#8A5A2B"),
    ("G2", "Liability & Reconciliation", "الالتزامات والمطابقة", "Finance", "Accounts", 21, "#8A5A2B"),

    ("H1", "Audit & Logs", "التدقيق والسجلات", "Governance", "Administrator", 22, "#5A6472"),
    ("H2", "Flow Definition", "تعريف المسار", "Governance", "Administrator", 23, "#5A6472"),
]

# --------------------------------------------------------------------------
# (label, label_ar, stage, seq, node_type, target, view, filters, roles, desc)
# target is a DocType name, a Report name, or "" for a Page/Note node
# (which then carries route_override in the desc slot convention below).
# --------------------------------------------------------------------------

NODES = [
    # ---- A1 Company & Outlet
    ("Company", "الشركة", "A1", 1, "DocType", "Company", "List", {}, ADM,
     "The accounting entity every POS document posts against."),
    ("Outlets", "المنافذ", "A1", 2, "DocType", "AlphaX POS Outlet", "List", {}, SUP,
     "Store, trading hours and day-close policy live here."),
    ("Floors", "الطوابق", "A1", 3, "DocType", "AlphaX POS Floor", "List", {}, SUP, ""),
    ("Tables", "الطاولات", "A1", 4, "DocType", "AlphaX POS Table", "List", {}, CSH,
     "Occupancy and readiness are tracked on two separate axes."),
    ("POS Settings", "إعدادات النظام", "A1", 5, "DocType", "AlphaX POS Settings", "Form", {}, ADM,
     "Single doctype. Global switches including the shift gate."),

    # ---- A2 Terminals & Hardware
    ("Terminals", "نقاط البيع", "A2", 1, "DocType", "AlphaX POS Terminal", "List", {}, SUP,
     "One bound PC per terminal. Carries the current business date."),
    ("Bridge Installs", "تثبيتات الجسر", "A2", 2, "DocType", "AlphaX POS Bridge Install", "List", {}, ADM,
     "The Windows agent that reaches local printers and the cash drawer."),
    ("Printer Profiles", "ملفات الطابعات", "A2", 3, "DocType", "AlphaX POS Printer Profile", "List", {}, ADM, ""),
    ("Print Stations", "محطات الطباعة", "A2", 4, "DocType", "AlphaX POS Print Station", "List", {}, SUP, ""),
    ("Kitchen Stations", "محطات المطبخ", "A2", 5, "DocType", "AlphaX POS Kitchen Station", "List", {}, KIT, ""),
    ("Card Readers", "قارئات البطاقات", "A2", 6, "DocType", "AlphaX POS Card Reader", "List", {}, ADM, ""),
    ("Payment Terminal Settings", "إعدادات أجهزة الدفع", "A2", 7, "DocType",
     "AlphaX POS Payment Terminal Settings", "Form", {}, ADM, ""),

    # ---- A3 Catalogue & Pricing
    ("Items", "الأصناف", "A3", 1, "DocType", "Item", "List", {}, ADM, ""),
    ("Item Groups", "مجموعات الأصناف", "A3", 2, "DocType", "Item Group", "List", {}, ADM,
     "Menus are resolved as set algebra over these groups."),
    ("Price Lists", "قوائم الأسعار", "A3", 3, "DocType", "Price List", "List", {}, ADM,
     "One per channel, so an order type can price differently."),
    ("Item Prices", "أسعار الأصناف", "A3", 4, "DocType", "Item Price", "List", {}, ADM, ""),
    ("Item Tax Templates", "قوالب الضريبة", "A3", 5, "DocType", "Item Tax Template", "List", {}, ADM,
     "Inclusive VAT is extracted from the displayed price, line by line."),
    ("Warehouses", "المستودعات", "A3", 6, "DocType", "Warehouse", "List", {}, ADM, ""),
    ("Scale Barcodes", "باركود الموازين", "A3", 7, "DocType",
     "AlphaX POS Scale Barcode Definition", "List", {}, ADM, ""),

    # ---- A4 Menus, Combos & Offers
    ("Menus", "القوائم", "A4", 1, "DocType", "AlphaX POS Menu", "List", {}, SUP,
     "One menu per outlet, expressed as include/exclude rules."),
    ("Combos", "العروض المركبة", "A4", 2, "DocType", "AlphaX POS Combo", "List", {}, SUP,
     "Fixed combos drop in as-is; customisable ones open the picker."),
    ("Offers", "العروض", "A4", 3, "DocType", "AlphaX POS Offer", "List", {}, SUP, ""),
    ("Order Types", "أنواع الطلبات", "A4", 4, "DocType", "AlphaX POS Order Type", "List", {}, SUP,
     "Each carries its own table policy and channel price list."),
    ("Recipes", "الوصفات", "A4", 5, "DocType", "AlphaX POS Recipe", "List", {}, SUP, ""),
    ("Domain Packs", "حزم النشاط", "A4", 6, "DocType", "AlphaX POS Domain Pack", "List", {}, ADM, ""),
    ("Themes", "السمات", "A4", 7, "DocType", "AlphaX POS Theme", "List", {}, ADM, ""),

    # ---- A5 People & Access
    ("Users", "المستخدمون", "A5", 1, "DocType", "User", "List", {}, ADM, ""),
    ("Roles", "الأدوار", "A5", 2, "DocType", "Role", "List",
     {"role_name": ["like", "AlphaX POS%"]}, ADM, ""),
    ("Role Profiles", "ملفات الأدوار", "A5", 3, "DocType", "Role Profile", "List", {}, ADM,
     "Cashier, Supervisor and Manager bundles."),
    ("POS Profiles", "ملفات نقطة البيع", "A5", 4, "DocType", "AlphaX POS Profile", "List", {}, ADM,
     "Terminal accounting configuration, not user identity."),
    ("Manager PINs", "رموز المدراء", "A5", 5, "DocType", "AlphaX POS Manager PIN", "List", {}, MGR,
     "bcrypt hashes. Manager and System Manager only."),

    # ---- B1 Shift Open
    ("Shifts", "الورديات", "B1", 1, "DocType", "AlphaX POS Shift", "List", {}, CSH,
     "No shift, no cart. The gate is enforced on the server."),
    ("Cashier Screen", "شاشة الكاشير", "B1", 2, "Page", "", "List", {}, CSH,
     "/app/alphax-cashier"),

    # ---- B2 Floor & Order Type
    ("Table Sessions", "جلسات الطاولات", "B2", 1, "DocType", "AlphaX POS Table Session", "List", {}, CSH, ""),
    ("Floor Designer", "مصمم الصالة", "B2", 2, "Page", "", "List", {}, SUP,
     "/app/alphax-floor-designer"),

    # ---- C1 Build the Order
    ("POS Orders", "طلبات نقطة البيع", "C1", 1, "DocType", "AlphaX POS Order", "List", {}, CSH,
     "The working document before it becomes an invoice."),
    ("Customers", "العملاء", "C1", 2, "DocType", "Customer", "List", {}, CSH, ""),
    ("Loyalty Wallets", "محافظ الولاء", "C1", 3, "DocType", "AlphaX POS Loyalty Wallet", "List", {}, CSH, ""),
    ("Loyalty Programs", "برامج الولاء", "C1", 4, "DocType", "AlphaX POS Loyalty Program", "List", {}, SUP, ""),

    # ---- C2 Kitchen Routing
    ("KOT Routing Rules", "قواعد توجيه المطبخ", "C2", 1, "DocType",
     "AlphaX POS KOT Routing Rule", "List", {}, SUP,
     "Decides which station prints which line."),
    ("Item Stations", "محطات الأصناف", "C2", 2, "DocType", "AlphaX POS Item Station", "List", {}, SUP, ""),

    # ---- C3 Payment
    ("Modes of Payment", "طرق الدفع", "C3", 1, "DocType", "Mode of Payment", "List", {}, ADM, ""),
    ("Card Transactions", "معاملات البطاقات", "C3", 2, "DocType",
     "AlphaX POS Card Transaction", "List", {}, SUP, ""),
    ("Store Credit", "رصيد المتجر", "C3", 3, "DocType", "AlphaX POS Store Credit", "List", {}, CSH,
     "Redeemable at the till against an auditable liability."),

    # ---- C4 Post & Fiscalise
    ("Sales Invoices", "فواتير المبيعات", "C4", 1, "DocType", "Sales Invoice", "List",
     {"is_return": 0}, CSH,
     "One submit writes the invoice, the GL and the stock movement."),
    ("Processing Log", "سجل المعالجة", "C4", 2, "DocType", "AlphaX POS Processing Log", "List", {}, SUP,
     "Where a failed post leaves its evidence."),

    # ---- D1 Kitchen Preparation
    ("KDS Tickets", "تذاكر المطبخ", "D1", 1, "DocType", "AlphaX POS KDS Ticket", "List", {}, KIT,
     "No prices reach this screen."),
    ("Kitchen Display", "شاشة المطبخ", "D1", 2, "Page", "", "List", {}, KIT, "/app/alphax-kds"),
    ("Central Kitchen Requests", "طلبات المطبخ المركزي", "D1", 3, "DocType",
     "AlphaX POS Central Kitchen Request", "List", {}, KIT, ""),

    # ---- D2 Guest Ordering
    ("QR Table Tokens", "رموز الطاولات", "D2", 1, "DocType",
     "AlphaX POS QR Table Token", "List", {}, SUP,
     "One token per table. Scoped so it cannot reach another table."),
    ("Delivery Platforms", "منصات التوصيل", "D2", 2, "DocType",
     "AlphaX Delivery Platform", "List", {}, SUP, ""),

    # ---- E1 Authorisation
    ("Authorisation Log", "سجل التفويض", "E1", 1, "DocType",
     "AlphaX POS Manager Authorization Log", "List", {}, MGR,
     "Append-only. Who approved what, at which terminal, when."),

    # ---- E2 Returns & Store Credit
    ("Return Reasons", "أسباب المرتجع", "E2", 1, "DocType", "AlphaX POS Return Reason", "List", {}, SUP, ""),
    ("Credit Notes", "الإشعارات الدائنة", "E2", 2, "DocType", "Sales Invoice", "List",
     {"is_return": 1}, SUP, ""),
    ("Store Credit Entries", "قيود رصيد المتجر", "E2", 3, "DocType",
     "AlphaX POS Store Credit Entry", "List", {}, SUP,
     "Issue, adjust and expiry each post a ledger entry."),

    # ---- E3 Cash Movement
    ("Cash Movements", "حركات النقد", "E3", 1, "DocType", "AlphaX POS Cash Movement", "List", {}, SUP,
     "Pay-ins, pay-outs and drops against an open shift."),

    # ---- F1 Shift Close
    ("Shift Close & Variance", "الإقفال والفروقات", "F1", 1, "DocType",
     "AlphaX POS Shift", "Report", {}, SUP,
     "Counted versus expected. The cashier never sees the second column."),
    ("Shift Register", "سجل الورديات", "F1", 2, "Report", "AlphaX POS Shift Register", "Report", {}, SUP, ""),

    # ---- F2 Day Close
    ("Day Close", "إقفال اليوم", "F2", 1, "DocType", "AlphaX POS Day Close", "List", {}, SUP,
     "Manual, after N shifts, or at closing time. Never all three."),

    # ---- F3 Reporting & Notification
    ("Report Email Setup", "إعداد تقارير البريد", "F3", 1, "DocType",
     "AlphaX POS Report Email Setup", "List", {}, MGR, ""),
    ("Email Log", "سجل البريد", "F3", 2, "DocType", "AlphaX POS Email Log", "List", {}, MGR, ""),
    ("Profitability", "الربحية", "F3", 3, "Page", "", "List", {}, MGR,
     "/app/alphax-pos-profitability"),
    ("Delivery Reconciliation", "مطابقة التوصيل", "F3", 4, "Report",
     "AlphaX Delivery Reconciliation", "Report", {}, MGR, ""),

    # ---- G1 Revenue Posting
    ("Posted Invoices", "الفواتير المرحّلة", "G1", 1, "DocType", "Sales Invoice", "List",
     {"docstatus": 1}, ACC, ""),
    ("Payment Entries", "قيود الدفع", "G1", 2, "DocType", "Payment Entry", "List", {}, ACC, ""),
    ("Journal Entries", "قيود اليومية", "G1", 3, "DocType", "Journal Entry", "List", {}, ACC,
     "Where the tobacco fee is moved from income to liability."),

    # ---- G2 Liability & Reconciliation
    ("Store Credit Liability", "التزام رصيد المتجر", "G2", 1, "DocType",
     "AlphaX POS Store Credit", "Report", {}, ACC, ""),
    ("Loyalty Ledger", "دفتر الولاء", "G2", 2, "DocType", "AlphaX POS Loyalty Ledger", "List", {}, ACC, ""),
    ("Period Closing", "إقفال الفترة", "G2", 3, "DocType", "Period Closing Voucher", "List", {}, ACC,
     "Nothing to import: the till posted into this ledger all along."),

    # ---- H1 Audit & Logs
    ("Activity Log", "سجل النشاط", "H1", 1, "DocType", "Activity Log", "List", {}, ADM, ""),
    ("Access Log", "سجل الوصول", "H1", 2, "DocType", "Access Log", "List", {}, ADM, ""),
    ("Knowledge Base", "قاعدة المعرفة", "H1", 3, "DocType", "AlphaX POS KB Article", "List", {}, SUP, ""),

    # ---- H2 Flow Definition
    ("Process Flow", "خريطة العملية", "H2", 1, "DocType",
     "AlphaX POS Process Flow", "List", {}, ADM, ""),
    ("Process Nodes", "عقد العملية", "H2", 2, "DocType",
     "AlphaX POS Process Node", "List", {}, ADM,
     "Every card on this board is one of these records."),
    ("Role Flow (training view)", "مسار الأدوار", "H2", 3, "Page", "", "List", {}, SUP,
     "/pos_role_flow"),
]

#: Stock Frappe/ERPNext documents. Used only to tag a node so the board can
#: show how much of the cycle the suite did not have to reinvent.
STD = {
    "Company", "Item", "Item Group", "Item Price", "Price List", "Item Tax Template",
    "Warehouse", "Customer", "Mode of Payment", "Sales Invoice", "Payment Entry",
    "Journal Entry", "Period Closing Voucher", "User", "Role", "Role Profile",
    "Activity Log", "Access Log",
}


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


def seed_process_flow():
    """Idempotent. Safe on install and on every migrate."""
    if not frappe.db.exists("DocType", "AlphaX POS Process Flow"):
        return
    flow = _ensure_flow()
    _ensure_nodes(flow)
    frappe.db.commit()


def _ensure_flow() -> str:
    if frappe.db.exists("AlphaX POS Process Flow", FLOW_NAME):
        doc = frappe.get_doc("AlphaX POS Process Flow", FLOW_NAME)
    else:
        doc = frappe.new_doc("AlphaX POS Process Flow")
        doc.flow_name = FLOW_NAME

    doc.flow_name_ar = "دورة عمل نقاط البيع من البداية إلى النهاية"
    doc.is_default = 1
    doc.description = (
        "From an empty site to a reconciled trading day. Every card opens the "
        "document behind it, and only the cards your roles can actually reach "
        "are drawn."
    )

    doc.set("stages", [])
    for key, label, label_ar, lane, actor, seq, colour in STAGES:
        doc.append("stages", {
            "stage_key": key, "stage_label": label, "stage_label_ar": label_ar,
            "lane": lane, "actor": actor, "sequence": seq, "colour": colour,
        })

    doc.flags.ignore_permissions = True
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
    return doc.name


def _ensure_nodes(flow: str):
    existing = {
        (r.stage_key, r.node_label): r.name
        for r in frappe.get_all(
            "AlphaX POS Process Node", filters={"process_flow": flow},
            fields=["name", "stage_key", "node_label"], ignore_permissions=True,
        )
    }

    for label, label_ar, stage, seq, ntype, target, view, filters, roles, desc in NODES:
        key = (stage, label)
        if key in existing:
            doc = frappe.get_doc("AlphaX POS Process Node", existing[key])
        else:
            doc = frappe.new_doc("AlphaX POS Process Node")
            doc.process_flow = flow

        doc.stage_key = stage
        doc.sequence = seq
        doc.node_label = label
        doc.node_label_ar = label_ar
        doc.node_type = ntype
        doc.default_view = view
        doc.filters_json = json.dumps(filters, ensure_ascii=False) if filters else ""
        doc.show_count = 1 if ntype == "DocType" else 0

        if ntype == "DocType":
            doc.document_type = target
            doc.is_erpnext_standard = 1 if target in STD else 0
            doc.description = desc
            doc.route_override = ""
        elif ntype == "Report":
            doc.report_name = target
            doc.is_erpnext_standard = 0
            doc.description = desc
            doc.route_override = ""
        else:
            # Page and Note nodes carry the route in the description slot.
            doc.route_override = desc
            doc.is_erpnext_standard = 0
            doc.description = ""

        doc.set("roles", [])
        for r in roles:
            doc.append("roles", {"role": r})

        doc.flags.ignore_permissions = True
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)
