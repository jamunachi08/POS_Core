"""Process flow board API.

The board is a navigation surface, not a picture. Every node points at a
real document type, so a user reads the sequence and opens the document
from the same card.

Two filters run, in this order, and both matter:

1. **Role** — a node may name the roles allowed to see it. A node with no
   roles listed falls through to step 2.
2. **Permission** — ``frappe.has_permission(doctype, "read")`` decides
   whether the node survives at all, and ``"create"`` decides whether the
   card offers a New button.

Step 2 is the one that cannot be got wrong by editing data: even if
somebody lists every role on every node, a cashier still cannot see a
Journal Entry card, because the permission check is the same one the desk
itself uses. Role rows narrow the board; they never widen it.
"""

from __future__ import annotations

import json

import frappe


def _parse_filters(raw):
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except ValueError:
        return {}


def _default_flow() -> str | None:
    return (
        frappe.db.get_value("AlphaX POS Process Flow", {"is_default": 1, "disabled": 0}, "name")
        or frappe.db.get_value("AlphaX POS Process Flow", {"disabled": 0}, "name")
    )


@frappe.whitelist()
def get_flow(flow: str | None = None, with_counts: int | str = 1) -> dict:
    """Stages and the nodes this user may actually reach."""
    flow = flow or _default_flow()
    if not flow:
        return {}

    doc = frappe.get_doc("AlphaX POS Process Flow", flow)

    nodes = frappe.get_all(
        "AlphaX POS Process Node",
        filters={"process_flow": flow, "disabled": 0},
        fields=[
            "name", "node_label", "node_label_ar", "stage_key", "sequence", "node_type",
            "document_type", "report_name", "route_override", "default_view",
            "filters_json", "is_erpnext_standard", "show_count", "icon", "description",
        ],
        order_by="sequence asc, node_label asc",
        ignore_permissions=True,
    )

    user_roles = set(frappe.get_roles())
    want_counts = int(with_counts or 0)
    visible = []

    for n in nodes:
        allowed = [
            r.role for r in frappe.get_all(
                "AlphaX POS Node Role", filters={"parent": n.name}, fields=["role"],
                ignore_permissions=True,
            )
        ]
        if allowed and not (user_roles & set(allowed)):
            continue

        n["can_create"] = False
        n["is_single"] = False
        if n.node_type == "DocType" and n.document_type:
            if not frappe.db.exists("DocType", n.document_type):
                # A node pointing at a doctype from an app that is not
                # installed here: drop it rather than render a dead card.
                continue
            if not frappe.has_permission(n.document_type, "read"):
                continue
            # A Single has no table. Routing it to a List view raises
            # TableMissingError; counting it raises too. It opens as a form,
            # has exactly one record, and can never be "created".
            n["is_single"] = bool(frappe.get_meta(n.document_type).issingle)
            if not n["is_single"]:
                n["can_create"] = bool(frappe.has_permission(n.document_type, "create"))
        elif n.node_type == "Report" and n.report_name:
            if not frappe.db.exists("Report", n.report_name):
                continue

        n["filters"] = _parse_filters(n.get("filters_json"))
        n["route"] = _route_for(n)

        n["count"] = None
        if (want_counts and n.show_count and n.node_type == "DocType" and n.document_type
                and not n["is_single"]):
            try:
                n["count"] = frappe.db.count(n.document_type, n["filters"])
            except Exception:
                n["count"] = None

        visible.append(n)

    stages = []
    for st in sorted(doc.stages, key=lambda s: s.sequence or 0):
        stage_nodes = [n for n in visible if n.stage_key == st.stage_key]
        if not stage_nodes:
            # An empty stage on a cashier's board is noise. Drop it.
            continue
        stages.append({
            "stage_key": st.stage_key,
            "stage_label": st.stage_label,
            "stage_label_ar": st.stage_label_ar,
            "lane": st.lane,
            "actor": st.get("actor"),
            "sequence": st.sequence,
            "colour": st.colour,
            "nodes": stage_nodes,
        })

    return {
        "flow": doc.name,
        "flow_name": doc.flow_name,
        "flow_name_ar": doc.flow_name_ar,
        "description": doc.description,
        "stages": stages,
        "user": frappe.session.user,
        "user_roles": sorted(user_roles & _known_roles()),
        "visible_nodes": len(visible),
        "total_nodes": len(nodes),
    }


def _known_roles() -> set:
    return {
        "AlphaX POS Cashier", "AlphaX POS Supervisor", "AlphaX POS Manager",
        "AlphaX POS Kitchen", "AlphaX POS User", "Accounts Manager",
        "Accounts User", "Stock Manager", "System Manager",
    }


def _route_for(n) -> str:
    if n.get("route_override"):
        return n["route_override"]
    if n.node_type == "Report" and n.report_name:
        return f"/app/query-report/{n.report_name}"
    if n.node_type == "DocType" and n.document_type:
        slug = n.document_type.lower().replace(" ", "-")
        # Singles and "Form" nodes open the document itself. Only List and
        # Report are real list-view modes; "/view/form" is not a Frappe route
        # and fell through to the List view, which is what broke Singles.
        if n.get("is_single") or (n.default_view or "List") == "Form":
            return f"/app/{slug}"
        view = (n.default_view or "List").lower()
        return f"/app/{slug}" if view == "list" else f"/app/{slug}/view/{view}"
    return ""


@frappe.whitelist()
def node_summary(flow: str | None = None) -> dict:
    """How much of the flow is AlphaX and how much is stock ERPNext.

    Useful in a demo: the answer is the argument for the suite sitting on
    a real ERP rather than beside one.
    """
    filters = {"disabled": 0}
    if flow:
        filters["process_flow"] = flow
    rows = frappe.get_all(
        "AlphaX POS Process Node", filters=filters,
        fields=["is_erpnext_standard", "count(name) as total"],
        group_by="is_erpnext_standard", ignore_permissions=True,
    )
    out = {"erpnext_standard": 0, "alphax_pos": 0}
    for r in rows:
        if r.is_erpnext_standard:
            out["erpnext_standard"] = r.total
        else:
            out["alphax_pos"] = r.total
    out["total"] = out["erpnext_standard"] + out["alphax_pos"]
    return out
