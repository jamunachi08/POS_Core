# AlphaX POS Documentation

Welcome. Pick the manual that matches your role.

---

## 📚 Four manuals

### 👤 [Cashier Manual](01-cashier-manual.md)
**For cashiers and front-line staff using the POS register.**

How to log in, scan items, take payments, handle returns, work
offline, and end your shift. Plain language, no technical knowledge
needed. ~12 pages.

### 👔 [Manager Manual](02-manager-manual.md)
**For branch managers and shift supervisors.**

Manager PIN setup, station binding, approvals, shift cash counts,
day-end procedures, audit log review, and troubleshooting from a
manager's view. ~14 pages.

### ⚙ [Administrator Manual](03-administrator-manual.md)
**For system administrators, IT staff, and business owners doing setup.**

Full installation, company hierarchy, POS Profile setup, items and
taxes, ZATCA Phase 2, hardware bridge, domain packs, loyalty,
pharmacy, routine admin tasks, and backup/disaster recovery. ~20 pages.

### 🔧 [Implementer Manual](04-implementer-manual.md)
**For Frappe developers, partners, and technical implementers.**

Architecture, three-app structure, Frappe Cloud deploy specifics, the
SFC loader for Vue, doctype reference, hooks, boot API, manager PIN
security module, soft adapter pattern, custom field strategy,
extending the system, customer onboarding playbook, known gotchas.
~22 pages.

---

## 📦 Available formats

Each manual is available in:

- **Markdown (.md)** — source format, in this folder. Easy to read in
  GitHub, easy to grep.
- **Word (.docx)** — in [`exports/`](exports/). Polished for sharing
  with customers.
- **PDF** — in [`exports/`](exports/). Final, professional, can't be
  edited.
- **HTML site** — open `exports/site/index.html` in any browser for a
  searchable, navigable version of all four manuals.

---

## Status legend

Throughout the manuals you'll see badges:

- ✅ **Working** — production-ready
- 🔬 **Beta** — works but may change
- 🚧 **In Development** — listed for completeness, not yet ready

We mark each section/feature so you can tell what's stable vs aspirational.

---

## Versioning

Documentation version matches the AlphaX POS Suite version. The
current set is for **v15.5.13** (May 2026).

When a new release ships, the docs are updated in the same git commit.
If a doc seems out of date, check the file's "Last updated" line in
its header.

---

## Contributing

Found a typo, error, or omission? The Markdown source is the canonical
version. Send a pull request to the GitHub repository, or message the
maintainer.

For technical corrections to the Implementer Manual, please cite the
relevant code path or doctype.

---

*Generated alongside AlphaX POS Suite v15.5.13.*
