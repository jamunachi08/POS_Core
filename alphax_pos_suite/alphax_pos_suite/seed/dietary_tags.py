# -*- coding: utf-8 -*-
"""Standard diets and allergens.

Two kinds, and the difference is the whole point:

  Diet      what a guest chooses to eat. Missing one costs a sale.
  Allergen  what a dish contains. Missing one puts a guest in hospital,
            so allergens are never inferred, never defaulted, and never
            hidden behind a filter toggle — they travel to the kitchen
            ticket whether or not anybody asked.

The fourteen allergens below are the EU/UK declarable set, which KSA and
GCC food-service practice follows closely. Seeded disabled-free and
idempotent: re-running updates labels and leaves an administrator's own
tags alone.
"""

import frappe

#: (tag, arabic, kind, short code, colour, show as a till filter)
TAGS = [
    # ---- diets: what a guest asks for --------------------------------------
    ("Vegetarian",   "نباتي",              "Diet", "VEG",  "#16A34A", 1),
    ("Vegan",        "نباتي صرف",          "Diet", "VGN",  "#15803D", 1),
    ("Halal",        "حلال",               "Diet", "HAL",  "#0F766E", 1),
    ("Gluten Free",  "خالٍ من الغلوتين",   "Diet", "GF",   "#CA8A04", 1),
    ("Dairy Free",   "خالٍ من الألبان",    "Diet", "DF",   "#0891B2", 1),
    ("Nut Free",     "خالٍ من المكسرات",   "Diet", "NF",   "#7C3AED", 1),
    ("Sugar Free",   "خالٍ من السكر",      "Diet", "SF",   "#DB2777", 1),
    ("Keto",         "كيتو",               "Diet", "KETO", "#475569", 0),
    ("Low Calorie",  "سعرات منخفضة",       "Diet", "LOW",  "#65A30D", 0),

    # ---- allergens: what the dish contains ---------------------------------
    ("Contains Gluten",    "يحتوي غلوتين",       "Allergen", "GLU", "#B45309", 0),
    ("Contains Crustaceans", "يحتوي قشريات",     "Allergen", "CRU", "#B45309", 0),
    ("Contains Eggs",      "يحتوي بيض",          "Allergen", "EGG", "#B45309", 0),
    ("Contains Fish",      "يحتوي أسماك",        "Allergen", "FSH", "#B45309", 0),
    ("Contains Peanuts",   "يحتوي فول سوداني",   "Allergen", "PNT", "#B91C1C", 0),
    ("Contains Soy",       "يحتوي صويا",         "Allergen", "SOY", "#B45309", 0),
    ("Contains Milk",      "يحتوي حليب",         "Allergen", "MLK", "#B45309", 0),
    ("Contains Tree Nuts", "يحتوي مكسرات",       "Allergen", "NUT", "#B91C1C", 0),
    ("Contains Celery",    "يحتوي كرفس",         "Allergen", "CEL", "#B45309", 0),
    ("Contains Mustard",   "يحتوي خردل",         "Allergen", "MUS", "#B45309", 0),
    ("Contains Sesame",    "يحتوي سمسم",         "Allergen", "SES", "#B45309", 0),
    ("Contains Sulphites", "يحتوي كبريتيت",      "Allergen", "SUL", "#B45309", 0),
    ("Contains Lupin",     "يحتوي ترمس",         "Allergen", "LUP", "#B45309", 0),
    ("Contains Molluscs",  "يحتوي رخويات",       "Allergen", "MOL", "#B45309", 0),
]


def seed_dietary_tags():
    """Idempotent. Safe on install and on every migrate."""
    if not frappe.db.exists("DocType", "AlphaX POS Dietary Tag"):
        return

    for name, name_ar, kind, code, colour, as_filter in TAGS:
        if frappe.db.exists("AlphaX POS Dietary Tag", name):
            doc = frappe.get_doc("AlphaX POS Dietary Tag", name)
        else:
            doc = frappe.new_doc("AlphaX POS Dietary Tag")
            doc.tag_name = name
            # Only on creation: an administrator who hides a filter chip
            # should not have it reappear on the next migrate.
            doc.show_as_filter = as_filter

        doc.tag_name_ar = name_ar
        doc.tag_kind = kind
        doc.short_code = code
        doc.colour = colour
        doc.flags.ignore_permissions = True
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)

    frappe.db.commit()
