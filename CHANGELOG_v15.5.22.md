# CHANGELOG — v15.5.22

Makes the Setup Wizard friendly for **existing sites** (sites that already
have a Company and ERPNext Branches), instead of always creating new ones.

## Why
- Step 1 took a free-text Company name and **created a new Company** unless
  the name matched an existing one exactly — a duplicate-company risk when
  installing onto a site that already has one.
- Step 2's branch is the standard ERPNext **Branch** master, but the wizard
  only offered a free-text box rather than letting you pick what exists.

## Changed
- **Step 1 (Company):** if the site already has companies, you now get a
  dropdown to **select your existing company**, plus a "➕ Create a new
  company…" option that reveals the name/VAT/currency/country fields. A
  single existing company is pre-selected. On a brand-new site, you simply
  get the create form as before.
- **Step 2 (Branch):** now lists existing ERPNext **Branch** records to
  pick from, with the same "➕ Create a new branch…" escape hatch. Pre-
  selects the first existing branch on an existing site.
- When an existing company is selected, the POS Profile and outlet now use
  **that company's own currency** rather than the wizard default.
- New endpoint `get_setup_wizard_context()` returns existing companies and
  branches to drive the pickers.

## Behaviour
- Selecting an existing Company/Branch **reuses** it — nothing is duplicated.
- Creating new still works exactly as before for fresh installs.

## Known limitation (unchanged, noted for later)
- The Branch "Address" field is collected but ERPNext's Branch doctype has
  no address field, so it isn't stored yet. Proper ZATCA address handling
  (an Address record linked to the Company/outlet) is a separate follow-up.
