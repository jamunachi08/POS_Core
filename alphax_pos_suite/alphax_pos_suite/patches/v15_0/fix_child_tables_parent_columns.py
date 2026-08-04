import frappe

CHILD_DT = [
    "AlphaX POS Profile Payment Method",
    "AlphaX POS Scale Barcode Rule",
]

REQUIRED_COLS = [
    ("parent", "varchar(140)"),
    ("parenttype", "varchar(140)"),
    ("parentfield", "varchar(140)"),
    ("idx", "int(11)"),
]

def execute():
    for dt in CHILD_DT:
        table = "tab" + dt
        if not frappe.db.table_exists(table):
            continue
        existing = {c[0] for c in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}
        for col, coltype in REQUIRED_COLS:
            if col not in existing:
                frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {coltype}")
    frappe.db.commit()
