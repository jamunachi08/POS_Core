#!/usr/bin/env python3
"""
Builds the AlphaX POS Hub Workspace fixture.

The Frappe Workspace schema is awkward to hand-author (content is a JSON
string of editorjs blocks, links and shortcuts are siblings, ordering
is implicit). This script takes a clean Python dict describing the
intended layout, expands it into the wire format, and writes
fixtures/workspace.json.

Run this from the repo root after editing LAYOUT below; commit the
result. The fixture is loaded by Frappe on every `bench migrate`, so
edits ship to all sites automatically.
"""
import json
import os

# --- LAYOUT (edit this; everything below is mechanical) ---------------------

WORKSPACE_NAME = "AlphaX POS Hub"
WORKSPACE_TITLE = "AlphaX POS"          # what shows in the sidebar
WORKSPACE_ICON = "retail"                # standard Frappe icon
WORKSPACE_PUBLIC = 1
# Frappe indicator_color is from a fixed set — we pick the closest to mauve.
# The CSS layer overrides the actual rendered color to #714B67.
WORKSPACE_INDICATOR_COLOR = "pink"
WORKSPACE_MODULE = "AlphaX POS Suite"

# Top-row shortcut tiles. Frappe's shortcut color is also a fixed enum
# (Grey, Green, Cyan, Blue, Orange, Yellow, Pink, Red, Purple). We use
# Pink across the board so they're consistent; the CSS retints them mauve.
SHORTCUTS = [
    {"label": "Open Cashier",   "type": "Page",     "link_to": "alphax-pos-classic",   "color": "Pink"},
    {"label": "Outlets",        "type": "DocType",  "link_to": "AlphaX POS Outlet",    "color": "Pink"},
    {"label": "Today's Sales",  "type": "Report",   "link_to": "Sales Register",       "color": "Pink",  "format": "Report Builder"},
    {"label": "ZATCA Status",   "type": "DocType",  "link_to": "AlphaX POS Processing Log", "color": "Pink"},
]

# Card-grouped link sections — appear under "Modules"
# Each card is a heading + a list of links.
# `link_type`: "DocType" (most), "Page" (custom pages), "Report" (saved reports).
# `link_to`: the doctype/page/report name (must match exactly what's installed).
CARDS = [
    {
        "label": "Operations",
        "icon":  "retail",
        "links": [
            {"label": "Cashier UI",          "link_type": "Page",    "link_to": "alphax-pos-classic"},
            {"label": "Cashier UI (Vue, Beta)", "link_type": "Page", "link_to": "alphax-pos-v2"},
            {"label": "Held Orders",         "link_type": "DocType", "link_to": "AlphaX POS Order", "filters": {"docstatus": 0}},
            {"label": "Floor Plan",          "link_type": "Page",    "link_to": "alphax_floor_designer"},
            {"label": "Kitchen Display",     "link_type": "Page",    "link_to": "alphax_kds"},
            {"label": "Day Close",           "link_type": "DocType", "link_to": "AlphaX POS Day Close"},
            {"label": "Shifts",              "link_type": "DocType", "link_to": "AlphaX POS Shift"},
        ],
    },
    {
        "label": "Setup & Configuration",
        "icon":  "setting-gear",
        "links": [
            {"label": "POS Outlet",          "link_type": "DocType", "link_to": "AlphaX POS Outlet"},
            {"label": "POS Profile",         "link_type": "DocType", "link_to": "POS Profile"},
            {"label": "AlphaX POS Profile",  "link_type": "DocType", "link_to": "AlphaX POS Profile"},
            {"label": "Domain Pack",         "link_type": "DocType", "link_to": "AlphaX POS Domain Pack"},
            {"label": "POS Theme",           "link_type": "DocType", "link_to": "AlphaX POS Theme"},
            {"label": "Terminals",           "link_type": "DocType", "link_to": "AlphaX POS Terminal"},
            {"label": "POS Settings",        "link_type": "DocType", "link_to": "AlphaX POS Settings"},
            {"label": "Setup Wizard",        "link_type": "Page",    "link_to": "alphax_pos_setup"},
        ],
    },
    {
        "label": "Catalog & Pricing",
        "icon":  "stock",
        "links": [
            {"label": "Items",               "link_type": "DocType", "link_to": "Item"},
            {"label": "Item Groups",         "link_type": "DocType", "link_to": "Item Group"},
            {"label": "Item Prices",         "link_type": "DocType", "link_to": "Item Price"},
            {"label": "Price Lists",         "link_type": "DocType", "link_to": "Price List"},
            {"label": "Recipes / BOM",       "link_type": "DocType", "link_to": "AlphaX POS Recipe"},
            {"label": "Offers / Promotions", "link_type": "DocType", "link_to": "AlphaX POS Offer"},
            {"label": "Scale Barcode Rules", "link_type": "DocType", "link_to": "AlphaX POS Scale Barcode Rule"},
        ],
    },
    {
        "label": "Sales & Customers",
        "icon":  "non-profit",
        "links": [
            {"label": "POS Invoices",        "link_type": "DocType", "link_to": "POS Invoice"},
            {"label": "Sales Invoices",      "link_type": "DocType", "link_to": "Sales Invoice", "filters": {"is_pos": 1}},
            {"label": "POS Orders",          "link_type": "DocType", "link_to": "AlphaX POS Order"},
            {"label": "Customers",           "link_type": "DocType", "link_to": "Customer"},
            {"label": "Loyalty Programs",    "link_type": "DocType", "link_to": "AlphaX POS Loyalty Program"},
            {"label": "Loyalty Wallets",     "link_type": "DocType", "link_to": "AlphaX POS Loyalty Wallet"},
            {"label": "Return Reasons",      "link_type": "DocType", "link_to": "AlphaX POS Return Reason"},
        ],
    },
    {
        "label": "Pharmacy",
        "icon":  "healthcare",
        "links": [
            {"label": "Drug Master",                "link_type": "DocType", "link_to": "AlphaX Drug Master"},
            {"label": "Prescriptions",              "link_type": "DocType", "link_to": "AlphaX Prescription"},
            {"label": "Drug Interaction Rules",     "link_type": "DocType", "link_to": "AlphaX Drug Interaction Rule"},
            {"label": "Controlled Substance Log",   "link_type": "DocType", "link_to": "AlphaX Controlled Substance Log"},
        ],
    },
    {
        "label": "Compliance & Tax",
        "icon":  "files",
        "links": [
            {"label": "Processing Log",       "link_type": "DocType", "link_to": "AlphaX POS Processing Log"},
            {"label": "Tax Templates",        "link_type": "DocType", "link_to": "Sales Taxes and Charges Template"},
            {"label": "Card Transactions",    "link_type": "DocType", "link_to": "AlphaX POS Card Transaction"},
            {"label": "ZATCA App",            "link_type": "DocType", "link_to": "Zatca Settings"},  # falls back to AlphaX ZATCA's settings doctype if installed
        ],
    },
    {
        "label": "Reports & Analytics",
        "icon":  "chart",
        "links": [
            {"label": "Profitability Dashboard",    "link_type": "Page",    "link_to": "alphax_pos_profitability"},
            {"label": "Sales Register",             "link_type": "Report",  "link_to": "Sales Register"},
            {"label": "Item-wise Sales History",    "link_type": "Report",  "link_to": "Item-wise Sales History"},
            {"label": "POS Day Close report",       "link_type": "DocType", "link_to": "AlphaX POS Day Close"},
            {"label": "Email Reports Setup",        "link_type": "DocType", "link_to": "AlphaX POS Report Email Setup"},
        ],
    },
    {
        "label": "Cash Management",
        "icon":  "money",
        "links": [
            {"label": "Day Close",            "link_type": "DocType", "link_to": "AlphaX POS Day Close"},
            {"label": "Cash Movements",       "link_type": "DocType", "link_to": "AlphaX POS Cash Movement"},
            {"label": "Shifts",               "link_type": "DocType", "link_to": "AlphaX POS Shift"},
            {"label": "Payment Terminals",    "link_type": "DocType", "link_to": "AlphaX POS Payment Terminal Settings"},
        ],
    },
    {
        "label": "Hardware & Bridge",
        "icon":  "tool",
        "links": [
            {"label": "Terminals",            "link_type": "DocType", "link_to": "AlphaX POS Terminal"},
            {"label": "Card Terminals",       "link_type": "DocType", "link_to": "AlphaX POS Payment Terminal Settings"},
            {"label": "Kitchen Stations",     "link_type": "DocType", "link_to": "AlphaX POS Kitchen Station"},
            {"label": "Item Stations",        "link_type": "DocType", "link_to": "AlphaX POS Item Station"},
            {"label": "Central Kitchen",      "link_type": "Page",    "link_to": "alphax_pos_central_kitchen_dashboard"},
            {"label": "Central Kitchen Requests", "link_type": "DocType", "link_to": "AlphaX POS Central Kitchen Request"},
        ],
    },
]


# --- builder (mechanical) ---------------------------------------------------


def build_content_blocks():
    """Return the editorjs-style blocks list that becomes the workspace
    `content` JSON string. We use header + spacer + shortcut + spacer +
    one card per group. Frappe's workspace renderer reads this to lay
    out the page."""
    blocks = []

    # Top header
    blocks.append({"type": "header", "data": {"text": "<span class=\"h4\"><b>AlphaX POS</b></span>", "col": 12}})
    blocks.append({"type": "spacer", "data": {"col": 12}})

    # Shortcut tiles row
    blocks.append({"type": "shortcut", "data": {"shortcut_name": s["label"], "col": 3}}
                  for s in SHORTCUTS) if False else None
    # The "shortcut" block in editorjs takes one entry; we add one block per shortcut.
    for s in SHORTCUTS:
        blocks.append({"type": "shortcut", "data": {"shortcut_name": s["label"], "col": 3}})

    blocks.append({"type": "spacer", "data": {"col": 12}})

    # "Modules" header
    blocks.append({"type": "header", "data": {"text": "<span class=\"h6\">Modules</span>", "col": 12}})

    # One card per group, 4 columns wide each (Frappe lays them out 3 per row)
    for c in CARDS:
        blocks.append({"type": "card", "data": {"card_name": c["label"], "col": 4}})

    return blocks


def build_shortcuts():
    """Return the `shortcuts` array."""
    out = []
    for idx, s in enumerate(SHORTCUTS, start=1):
        entry = {
            "color":     s.get("color", "Grey"),
            "doctype":   "Workspace Shortcut",
            "format":    s.get("format", ""),
            "icon":      "",
            "label":     s["label"],
            "link_to":   s["link_to"],
            "parent":    WORKSPACE_NAME,
            "parentfield": "shortcuts",
            "parenttype":  "Workspace",
            "type":      s["type"],
            "url":       "",
            "stats_filter": "",
            "idx":       idx,
            "docstatus": 0,
        }
        out.append(entry)
    return out


def build_links():
    """Return the `links` array. Each card becomes a Card Break followed
    by the link entries. Order matters — Frappe renders them in array order."""
    out = []
    seq = 0
    for c in CARDS:
        seq += 1
        out.append({
            "doctype":      "Workspace Link",
            "type":         "Card Break",
            "label":        c["label"],
            "icon":         c.get("icon", ""),
            "hidden":       0,
            "is_query_report": 0,
            "link_count":   len(c["links"]),
            "onboard":      0,
            "parent":       WORKSPACE_NAME,
            "parentfield":  "links",
            "parenttype":   "Workspace",
            "idx":          seq,
            "docstatus":    0,
            "link_to":      "",
            "link_type":    "",
            "url":          "",
            "format":       "",
            "description":  "",
            "report_ref_doctype": "",
            "dependencies": "",
            "only_for_country": "",
            "restrict_to_domain": "",
        })
        for l in c["links"]:
            seq += 1
            entry = {
                "doctype":      "Workspace Link",
                "type":         "Link",
                "label":        l["label"],
                "link_to":      l["link_to"],
                "link_type":    l["link_type"],
                "hidden":       0,
                "is_query_report": 1 if l["link_type"] == "Report" else 0,
                "onboard":      0,
                "parent":       WORKSPACE_NAME,
                "parentfield":  "links",
                "parenttype":   "Workspace",
                "idx":          seq,
                "docstatus":    0,
                "link_count":   0,
                "url":          "",
                "format":       "",
                "description":  "",
                "report_ref_doctype": "",
                "dependencies": "",
                "only_for_country": "",
                "restrict_to_domain": "",
                "icon":         "",
            }
            if l.get("filters"):
                # Frappe Workspace Link doesn't have a native filters column,
                # but DocType links honor query strings via `link_to`. We
                # leave this for now — filters would need a Report or a
                # separate List View entry.
                pass
            out.append(entry)
    return out


def build_workspace_doc():
    return {
        "charts":      [],
        "content":     json.dumps(build_content_blocks(), separators=(",", ":")),
        "creation":    "2026-01-01 00:00:00",
        "custom_blocks":[],
        "docstatus":   0,
        "doctype":     "Workspace",
        "for_user":    "",
        "hide_custom": 0,
        "icon":        WORKSPACE_ICON,
        "indicator_color": WORKSPACE_INDICATOR_COLOR,
        "is_hidden":   0,
        "label":       WORKSPACE_NAME,
        "links":       build_links(),
        "modified":    "2026-01-01 00:00:00",
        "modified_by": "Administrator",
        "module":      WORKSPACE_MODULE,
        "name":        WORKSPACE_NAME,
        "number_cards":[],
        "owner":       "Administrator",
        "parent_page": "",
        "public":      WORKSPACE_PUBLIC,
        "quick_lists": [],
        "roles":       [],
        "sequence_id": 50.0,
        "shortcuts":   build_shortcuts(),
        "title":       WORKSPACE_TITLE,
    }


def main():
    out_dir = os.path.join(
        os.path.dirname(__file__),
        "alphax_pos_suite",
        "fixtures",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "workspace.json")
    workspace = build_workspace_doc()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([workspace], f, indent=1, ensure_ascii=False)
    print(f"Wrote {out_path}")
    print(f"  {len(workspace['shortcuts'])} shortcuts, "
          f"{len(workspace['links'])} link entries "
          f"({sum(1 for l in workspace['links'] if l['type'] == 'Card Break')} cards)")


if __name__ == "__main__":
    main()
