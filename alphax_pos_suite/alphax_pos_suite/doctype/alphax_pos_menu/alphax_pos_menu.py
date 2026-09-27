import frappe
from frappe import _
from frappe.model.document import Document


class AlphaXPOSMenu(Document):
    """A sellable range.

    The single most important rule in this design: an Item Group says what
    a product *is*; a Menu says where it is *sold*. Overloading the item
    tree with branch or channel meaning is the mistake that cannot be
    undone later, because the tree is also what every historical report
    groups by. Reorganise it to open a branch and you rewrite history.
    """

    def validate(self):
        self.menu_name = (self.menu_name or "").strip()
        self._validate_rules()
        self._validate_window()
        # Cheap enough to do on save, and a menu that silently resolves to
        # nothing is the failure people lose an afternoon to.
        from alphax_pos_suite.alphax_pos_suite.catalog.api import resolve_menu_items
        try:
            self.resolved_count = len(resolve_menu_items([self.name])) if not self.is_new() else 0
        except Exception:
            self.resolved_count = 0

    def _validate_rules(self):
        if not self.rules:
            frappe.throw(_("A menu with no rules sells nothing. Add at least one Include row."))
        if not any(r.rule_type == "Include" for r in self.rules):
            frappe.throw(_("A menu needs at least one Include rule. Excludes only subtract."))
        for r in self.rules:
            field = {"Item Group": "item_group", "Item": "item",
                     "Brand": "brand", "Item Attribute": "attribute"}[r.match_on]
            if not r.get(field):
                frappe.throw(_("Row {0}: choose a {1}.").format(r.idx, r.match_on))

    def _validate_window(self):
        if self.days_of_week:
            valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
            given = [d.strip().lower()[:3] for d in str(self.days_of_week).split(",") if d.strip()]
            bad = [d for d in given if d not in valid]
            if bad:
                frappe.throw(_("Unknown day(s): {0}. Use Mon,Tue,Wed,Thu,Fri,Sat,Sun.")
                             .format(", ".join(bad)))
            self.days_of_week = ",".join(d.capitalize() for d in given)
        if self.valid_from and self.valid_upto and self.valid_from > self.valid_upto:
            frappe.throw(_("Valid From is after Valid Until."))

    def on_update(self):
        try:
            from alphax_pos_suite.alphax_pos_suite.boot.api import invalidate_boot_cache
            invalidate_boot_cache()
        except Exception:
            pass
        frappe.cache().delete_keys("alphax_pos_menu")
