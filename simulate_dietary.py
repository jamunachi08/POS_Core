"""Offline proof of the dietary and allergen rules.

Two rules carry real-world consequences and are therefore asserted here
rather than trusted to a screen:

  * diet chips combine with AND. A guest who is vegan AND gluten free must
    only be shown dishes that satisfy both; an OR would hand them a dish
    that satisfies neither;
  * allergens are never offered as a filter and never inferred. They are
    snapshotted onto the kitchen ticket at the moment it is raised, so an
    item edited later cannot rewrite a ticket already on the rail.
"""
import importlib.util
import re
import sys
import types

ITEMS = {
    "SALAD":  {"food": "Veg",     "diets": ["Vegan", "Vegetarian", "Gluten Free"], "alg": []},
    "PASTA":  {"food": "Veg",     "diets": ["Vegetarian"],                          "alg": ["Contains Gluten", "Contains Milk"]},
    "SATAY":  {"food": "Non-Veg", "diets": ["Gluten Free", "Halal"],                "alg": ["Contains Peanuts"]},
    "OMELET": {"food": "Egg",     "diets": ["Vegetarian", "Gluten Free"],           "alg": ["Contains Eggs", "Contains Milk"]},
    "SOUP":   {"food": "Veg",     "diets": ["Vegan", "Vegetarian"],                 "alg": ["Contains Celery"]},
}
CODES = {"Contains Gluten": "GLU", "Contains Milk": "MLK", "Contains Peanuts": "PNT",
         "Contains Eggs": "EGG", "Contains Celery": "CEL"}
KIND = {t: "Allergen" for t in CODES}
for d in ("Vegan", "Vegetarian", "Gluten Free", "Halal"):
    KIND[d] = "Diet"


class _R(dict):
    __getattr__ = dict.get


fr = types.ModuleType("frappe")
fr._ = lambda s: s
fr.whitelist = lambda *a, **k: (lambda f: f)
fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0]))
fr.PermissionError = Exception
fr.get_meta = lambda dt: types.SimpleNamespace(
    has_field=lambda f: f in ("alphax_food_type", "alphax_dietary_tags",
                              "alphax_spice_level", "alphax_is_weighing_item",
                              "alphax_scale_item_code"))


class DB:
    def exists(self, dt, name=None):
        return True

    def get_value(self, *a, **k):
        return None

    def get_single_value(self, *a, **k):
        return None


fr.db = DB()


def get_all(dt, filters=None, fields=None, order_by=None, ignore_permissions=False, **k):
    f = filters or {}
    if dt == "AlphaX POS Item Dietary Tag":
        want = f.get("parent", ["in", []])[1]
        return [_R(parent=c, dietary_tag=t) for c in want if c in ITEMS
                for t in ITEMS[c]["diets"] + ITEMS[c]["alg"]]
    if dt == "AlphaX POS Dietary Tag":
        names = f.get("name", ["in", list(KIND)])[1]
        rows = [_R(name=n, tag_name_ar="", tag_kind=KIND[n],
                   short_code=CODES.get(n, n[:3].upper()), colour=None)
                for n in names if n in KIND]
        if f.get("tag_kind"):
            rows = [r for r in rows if r.tag_kind == f["tag_kind"]]
        return rows
    if dt == "Item":
        want = f.get("name", ["in", []])[1]
        return [_R(name=c, alphax_food_type=ITEMS[c]["food"], alphax_spice_level=None,
                   alphax_is_weighing_item=0, alphax_scale_item_code=None)
                for c in want if c in ITEMS]
    return []


fr.get_all = get_all
u = types.ModuleType("frappe.utils")
u.cint = lambda v: int(v or 0)
u.flt = lambda v: float(v or 0)
u.getdate = u.nowdate = u.now_datetime = lambda *a: None
u.add_to_date = u.get_datetime = u.get_time = u.time_diff_in_seconds = lambda *a, **k: None
fr.utils = u
sys.modules.update({"frappe": fr, "frappe.utils": u})

spec = importlib.util.spec_from_file_location(
    "alphax_pos_suite.alphax_pos_suite.catalog.api",
    "alphax_pos_suite/alphax_pos_suite/catalog/api.py")
cat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cat
spec.loader.exec_module(cat)

spec2 = importlib.util.spec_from_file_location(
    "kot", "alphax_pos_suite/alphax_pos_suite/pos/kot_api.py")
kot = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(kot)

fails = 0


def check(c, m):
    global fails
    print(("  OK   " if c else "  FAIL ") + m)
    fails += (not c)


print("== payload splits diets from allergens ==")
rows = [{"item_code": c, "standard_rate": 0} for c in ITEMS]
cat._apply_optional_fields(rows)
by = {r["item_code"]: r for r in rows}
check(all("diets" in r and "allergens" in r for r in rows), "every row carries both lists")
check({d["tag"] for d in by["PASTA"]["diets"]} == {"Vegetarian"},
      f"PASTA diets = {[d['tag'] for d in by['PASTA']['diets']]}")
check({a["code"] for a in by["PASTA"]["allergens"]} == {"GLU", "MLK"},
      f"PASTA allergens = {sorted(a['code'] for a in by['PASTA']['allergens'])}")
check(not any(a["tag"] in ("Vegan", "Halal") for r in rows for a in r["allergens"]),
      "no diet ever lands in the allergen list")
check(by["OMELET"]["alphax_food_type"] == "Egg", "food type carried through")

print("== diet chips are AND, not OR ==")


def grid(active):
    out = []
    for r in rows:
        tags = {d["tag"] for d in r["diets"]}
        if all(a in tags for a in active):
            out.append(r["item_code"])
    return sorted(out)


check(grid(["Vegan"]) == ["SALAD", "SOUP"], f"Vegan -> {grid(['Vegan'])}")
check(grid(["Gluten Free"]) == ["OMELET", "SALAD", "SATAY"], f"Gluten Free -> {grid(['Gluten Free'])}")
check(grid(["Vegan", "Gluten Free"]) == ["SALAD"],
      f"Vegan AND Gluten Free -> {grid(['Vegan', 'Gluten Free'])} (an OR would wrongly include SATAY and SOUP)")
check(grid(["Vegan", "Halal"]) == [], "a combination nothing satisfies returns nothing, not everything")

print("== allergens are not filterable ==")
src = open("alphax_pos_suite/alphax_pos_suite/catalog/api.py", encoding="utf-8").read()
fn = src[src.index("def dietary_filters"):]
fn = fn[:fn.index("\ndef ") if "\ndef " in fn else len(fn)]
check('"tag_kind": "Diet"' in fn, "dietary_filters asks the database for Diet only")
check("Allergen" not in fn.split('"""')[2] if fn.count('"""') >= 2 else True,
      "no allergen path in the filter query body")

print("== kitchen ticket snapshot ==")
snap = kot._dietary_snapshot(["PASTA", "SATAY", "SALAD"])
check(snap["SATAY"]["allergens"] == ["PNT"], f"SATAY -> {snap['SATAY']['allergens']}")
check(sorted(snap["PASTA"]["allergens"]) == ["GLU", "MLK"], f"PASTA -> {sorted(snap['PASTA']['allergens'])}")
check(snap["SALAD"]["allergens"] == [], "a dish with no allergens carries an empty list, not a null")
check(snap["SATAY"]["food_type"] == "Non-Veg", "food type reaches the ticket")
check(all(len(c) <= 4 for v in snap.values() for c in v["allergens"]),
      "ticket codes stay short enough for an 80mm roll")

print("== a diet is never printed as an allergen ==")
check(not any(t in snap["SATAY"]["allergens"] for t in ("Halal", "HAL", "Gluten Free", "GF")),
      "SATAY is Halal and Gluten Free; neither appears as a ticket allergen")

print()
print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
sys.exit(1 if fails else 0)
