"""Offline proof that a tapped item and a scanned item cost the same.

Before v15.17.0 the grid priced menu -> outlet -> standard rate, and the
scanner priced ERPNext POS Profile -> outlet -> Selling Settings. With a
POS Profile on "Standard Selling" and an outlet on "Retail KSA", one item
had two prices. This builds exactly that site and asserts one price.
"""
import importlib.util
import sys
import types

ITEM_PRICE = {  # (price_list, item) -> rate
    ("Menu Promo", "LATTE"): 12.0,
    ("Retail KSA", "LATTE"): 15.0, ("Retail KSA", "MUFFIN"): 9.0,
    ("Standard Selling", "LATTE"): 18.0, ("Standard Selling", "MUFFIN"): 11.0,
    ("Standard Selling", "WATER"): 2.0,
}
VALUES = {
    ("AlphaX POS Outlet", "OUT-1", "default_price_list"): "Retail KSA",
    ("AlphaX POS Terminal", "T-1", "pos_profile"): "Main POS",
    ("POS Profile", "Main POS", "selling_price_list"): "Standard Selling",
    ("AlphaX POS Terminal", "T-1", "pos_outlet"): "OUT-1",
}
MENUS = []


class _R(dict):
    __getattr__ = dict.get


fr = types.ModuleType("frappe")
fr._ = lambda s: s
fr.whitelist = lambda *a, **k: (lambda f: f)
fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0]))
fr.PermissionError = Exception
fr.has_permission = lambda *a, **k: True


class DB:
    def get_value(self, dt, name, field=None, as_dict=False):
        return VALUES.get((dt, name, field))

    def exists(self, dt, name=None):
        return True

    def get_single_value(self, dt, f):
        return "Standard Selling"

    def table_exists(self, dt):
        return True


fr.db = DB()


def get_all(dt, filters=None, fields=None, **k):
    if dt == "Item Price":
        pl, codes = filters["price_list"], filters["item_code"][1]
        return [_R(item_code=c, price_list_rate=ITEM_PRICE[(pl, c)])
                for c in codes if (pl, c) in ITEM_PRICE]
    if dt == "AlphaX POS Menu Link":
        return []
    if dt == "AlphaX POS Menu":
        return MENUS
    return []


fr.get_all = get_all
utils = types.ModuleType("frappe.utils")
utils.cint = lambda v: int(v or 0)
utils.flt = lambda v: float(v or 0)
utils.getdate = utils.now_datetime = utils.nowdate = lambda *a: None
fr.utils = utils
sys.modules["frappe"] = fr
sys.modules["frappe.utils"] = utils

APP = "alphax_pos_suite/alphax_pos_suite"
pkg = types.ModuleType("alphax_pos_suite.alphax_pos_suite.catalog")
spec = importlib.util.spec_from_file_location("alphax_pos_suite.alphax_pos_suite.catalog.api",
                                              f"{APP}/catalog/api.py")
cat = importlib.util.module_from_spec(spec)
sys.modules["alphax_pos_suite.alphax_pos_suite.catalog.api"] = cat
spec.loader.exec_module(cat)

fails = 0


def check(c, m):
    global fails
    print(("  OK   " if c else "  FAIL ") + m)
    fails += (not c)


print("== chain order ==")
chain = cat.price_list_chain(outlet="OUT-1", terminal="T-1")
print("  ", " -> ".join(f"{pl} ({s})" for pl, s in chain))
check([s for _, s in chain] == ["outlet", "pos_profile"], "outlet before POS Profile; Selling Settings deduped")

MENUS[:] = [{"name": "M1", "menu_name": "Promo", "price_list": "Menu Promo", "priority": 5}]
chain_m = cat.price_list_chain(outlet="OUT-1", terminal="T-1", menus=MENUS)
check(chain_m[0] == ("Menu Promo", "menu:Promo"), "menu price list outranks outlet")

print("== grid vs scanner agree ==")
for code, std in [("LATTE", 0), ("MUFFIN", 0), ("WATER", 0), ("GHOST", 0), ("GHOST2", 7.5)]:
    rows = [{"item_code": code, "standard_rate": std}]
    cat._apply_prices(rows, cat.price_list_chain(outlet="OUT-1", terminal="T-1"))
    MENUS[:] = []
    scan_rate, pl, src = cat.rate_for(code, outlet="OUT-1", terminal="T-1", standard_rate=std)
    same = rows[0]["rate"] == scan_rate
    print(f"   {code:7s} grid={rows[0]['rate']:6.2f} ({rows[0]['price_source']:16s}) scan={scan_rate:6.2f}")
    check(same, f"{code}: tapped and scanned price identical")

rows = [{"item_code": "WATER", "standard_rate": 0}]
cat._apply_prices(rows, cat.price_list_chain(outlet="OUT-1", terminal="T-1"))
check(rows[0]["rate"] == 2.0 and rows[0]["price_source"] == "pos_profile",
      "item priced only on POS Profile list no longer shows 0.00")
rows = [{"item_code": "GHOST", "standard_rate": 0}]
cat._apply_prices(rows, cat.price_list_chain(outlet="OUT-1", terminal="T-1"))
check(rows[0]["price_source"] == "unpriced", "truly unpriced item is flagged, not silently 0")

print()
print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
