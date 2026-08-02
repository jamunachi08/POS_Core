"""
AlphaX POS — Floor Plan API

Endpoints used by the visual designer page and the cashier SPA's live floor
view. All updates are fanned out via frappe.publish_realtime so multiple
terminals see the same state.
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_floor_layout(floor):
    """
    Return everything the designer / live view needs to draw one floor.
    """
    if not frappe.db.exists("AlphaX POS Floor", floor):
        frappe.throw(_("Floor not found."))

    f = frappe.get_doc("AlphaX POS Floor", floor)
    tables = frappe.get_all(
        "AlphaX POS Table",
        filters={"floor": floor},
        fields=[
            "name",
            "table_code",
            "seats",
            "shape",
            "status",
            "pos_x",
            "pos_y",
            "width",
            "height",
            "rotation",
            "color",
            "outlet",
            "is_mergeable",
            "min_party_size",
            "max_party_size",
        ],
        order_by="table_code asc",
    )

    return {
        "floor": {
            "name": f.name,
            "floor_name": f.floor_name,
            "outlet": f.outlet,
            "canvas_width": f.canvas_width,
            "canvas_height": f.canvas_height,
            "grid_size": f.grid_size,
            "background_image": f.background_image,
            "background_color": f.background_color,
            "zones_json": f.zones_json,
        },
        "tables": tables,
    }


@frappe.whitelist()
def list_floors(outlet=None):
    """List all floors, optionally filtered by outlet."""
    filters = {"enabled": 1}
    if outlet:
        filters["outlet"] = outlet
    return frappe.get_all(
        "AlphaX POS Floor",
        filters=filters,
        fields=["name", "floor_name", "outlet", "display_order"],
        order_by="display_order asc, floor_name asc",
    )


@frappe.whitelist()
def save_floor_layout(floor, tables, zones_json=None, canvas_width=None,
                      canvas_height=None, background_image=None,
                      background_color=None):
    """
    Persist the designer's drag-drop work in one transaction.
    `tables` is a JSON list of {name, pos_x, pos_y, width, height, rotation, shape, seats}.
    """
    import json

    if isinstance(tables, str):
        tables = json.loads(tables or "[]")

    if not frappe.db.exists("AlphaX POS Floor", floor):
        frappe.throw(_("Floor not found."))

    f = frappe.get_doc("AlphaX POS Floor", floor)
    if zones_json is not None:
        f.zones_json = zones_json
    if canvas_width:
        f.canvas_width = int(canvas_width)
    if canvas_height:
        f.canvas_height = int(canvas_height)
    if background_image is not None:
        f.background_image = background_image
    if background_color is not None:
        f.background_color = background_color
    f.save()

    updated = []
    for t in tables or []:
        if not t.get("name") or not frappe.db.exists("AlphaX POS Table", t["name"]):
            continue
        doc = frappe.get_doc("AlphaX POS Table", t["name"])
        if doc.floor != floor:
            continue
        doc.pos_x = int(t.get("pos_x", doc.pos_x))
        doc.pos_y = int(t.get("pos_y", doc.pos_y))
        doc.width = int(t.get("width", doc.width))
        doc.height = int(t.get("height", doc.height))
        doc.rotation = int(t.get("rotation", doc.rotation or 0))
        if t.get("shape"):
            doc.shape = t["shape"]
        if t.get("seats"):
            doc.seats = int(t["seats"])
        doc.save()
        updated.append(doc.name)

    frappe.publish_realtime(
        event="alphax_pos_floor_updated",
        message={"floor": floor, "tables": updated},
    )
    return {"ok": True, "updated": updated}


@frappe.whitelist()
def add_table(floor, table_code, seats=4, shape="Rectangle", pos_x=50, pos_y=50,
              width=80, height=60, outlet=None):
    """Create a new table on a floor (designer 'add table' button)."""
    if frappe.db.exists("AlphaX POS Table", table_code):
        frappe.throw(_("Table {0} already exists.").format(table_code))
    if not outlet:
        outlet = frappe.db.get_value("AlphaX POS Floor", floor, "outlet")

    t = frappe.new_doc("AlphaX POS Table")
    t.table_code = table_code
    t.floor = floor
    t.outlet = outlet
    t.seats = int(seats)
    t.shape = shape
    t.pos_x = int(pos_x)
    t.pos_y = int(pos_y)
    t.width = int(width)
    t.height = int(height)
    t.status = "Free"
    t.insert()

    frappe.publish_realtime(
        event="alphax_pos_floor_updated",
        message={"floor": floor, "added": t.name},
    )
    return t.as_dict()


@frappe.whitelist()
def update_table_status(table, status, party_size=None):
    """
    Cashier flips a table from Free to Occupied (or any transition).
    Broadcasts to all listening clients so the floor view stays in sync.
    """
    valid = {"Free", "Occupied", "Reserved", "Dirty", "Disabled"}
    if status not in valid:
        frappe.throw(_("Invalid status: {0}").format(status))

    if not frappe.db.exists("AlphaX POS Table", table):
        frappe.throw(_("Table not found."))

    doc = frappe.get_doc("AlphaX POS Table", table)
    old_status = doc.status
    doc.status = status
    doc.save()

    frappe.publish_realtime(
        event="alphax_pos_table_status",
        message={
            "table": table,
            "floor": doc.floor,
            "from_status": old_status,
            "to_status": status,
            "party_size": party_size,
        },
    )
    return {"ok": True, "table": table, "status": status}


@frappe.whitelist()
def get_outlet_floor_summary(outlet):
    """
    Manager dashboard: live counts per floor for an outlet.
    """
    rows = frappe.db.sql(
        """
        select f.name as floor, f.floor_name,
               sum(case when t.status = 'Free' then 1 else 0 end) as free,
               sum(case when t.status = 'Occupied' then 1 else 0 end) as occupied,
               sum(case when t.status = 'Reserved' then 1 else 0 end) as reserved,
               sum(case when t.status = 'Dirty' then 1 else 0 end) as dirty,
               count(t.name) as total
        from `tabAlphaX POS Floor` f
        left join `tabAlphaX POS Table` t on t.floor = f.name
        where f.outlet = %s and f.enabled = 1
        group by f.name, f.floor_name
        order by f.display_order, f.floor_name
        """,
        (outlet,),
        as_dict=True,
    )
    return rows
