# AlphaX POS — Administrator Manual

**For:** System administrators, IT staff, business owners doing setup
**Version:** 15.5.13
**Last updated:** May 2026

---

## What's in this manual

1. [Overview: what AlphaX POS includes](#overview-what-alphax-pos-includes)
2. [Architecture: three apps, what runs where](#architecture-three-apps-what-runs-where)
3. [Pre-deployment checklist](#pre-deployment-checklist)
4. [Day 1: install the apps on your bench](#day-1-install-the-apps-on-your-bench)
5. [Day 2: company, branch, outlet, terminal hierarchy](#day-2-company-branch-outlet-terminal-hierarchy)
6. [Day 3: POS Profile and payment methods](#day-3-pos-profile-and-payment-methods)
7. [Day 4: items, taxes, pricing](#day-4-items-taxes-pricing)
8. [Day 5: users, roles, manager PINs](#day-5-users-roles-manager-pins)
9. [Day 6: ZATCA Phase 2 setup](#day-6-zatca-phase-2-setup)
10. [Day 7: hardware bridge — printers, drawers, scanners](#day-7-hardware-bridge--printers-drawers-scanners)
11. [Domain packs: configuring per-vertical features](#domain-packs-configuring-per-vertical-features)
12. [Loyalty, offers, pricing rules](#loyalty-offers-pricing-rules)
13. [Pharmacy domain: drugs, prescriptions, controlled substances](#pharmacy-domain-drugs-prescriptions-controlled-substances)
14. [Routine administration tasks](#routine-administration-tasks)
15. [Backup and disaster recovery](#backup-and-disaster-recovery)
16. [Troubleshooting](#troubleshooting)
17. [Glossary](#glossary)

---

## Overview: what AlphaX POS includes

✅ **Working** unless marked otherwise.

AlphaX POS is a Frappe v15 app suite for retail, restaurants, and
pharmacies. It's designed for the Saudi Arabian market with built-in
ZATCA Phase 2 e-invoicing.

### What's in the box

- **POS register UI** for cashier transactions (`/app/alphax-pos-classic`)
- **52 doctypes** covering outlets, terminals, profiles, orders, shifts,
  cash moves, theme settings, drug master, prescriptions, controlled
  substance log, loyalty, central kitchen, ZATCA processing log, and more
- **Workspace** (`/app/alphax-pos-hub`) with shortcuts to all the major
  setup and operational areas
- **Manager PIN system** (`AlphaX POS Manager PIN`) with bcrypt hashing,
  exponential lockout, full audit log
- **POS Profile integration** with standard ERPNext POS Profile
- **Domain packs** to enable/disable features per vertical
- **Hardware bridge** (separate Python daemon) for thermal printers,
  cash drawers, scales, card terminals — runs on each cashier PC
- **ZATCA Phase 2** integration via the `alphax-zatca` companion app
  (forked from ERPGulf)

### What's optional

- 🔬 **Vue cashier** at `/app/alphax-pos-v2` — a richer single-page-app
  cashier (in Beta; the jQuery `alphax-pos-classic` is the production
  default for v15.5.13)
- 🔬 **Floor Designer**, **KDS** (Kitchen Display System),
  **Profitability Dashboard**, **APOS** (alternative cashier) — beta
  features useful for restaurants

### Status conventions

> ✅ **Working** — production-ready
> 🔬 **Beta** — works, but the API or UI may shift in a near release
> 🚧 **In Development** — listed for completeness; do not deploy yet

---

## Architecture: three apps, what runs where

### The three components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frappe Cloud (your bench)                    │
│                                                                 │
│  ┌──────────────────┐   ┌──────────────────┐                  │
│  │  alphax_pos_     │   │   alphax_zatca   │                  │
│  │     suite        │   │  (companion app) │                  │
│  │                  │   │                  │                  │
│  │  • Cashier UI    │   │  • Phase 2       │                  │
│  │  • Doctypes      │   │    e-invoicing   │                  │
│  │  • Workspace     │   │  • CSID mgmt     │                  │
│  │  • Manager PIN   │   │  • XML signing   │                  │
│  │  • Hooks         │   │                  │                  │
│  └──────────────────┘   └──────────────────┘                  │
│                                                                 │
│              Standard ERPNext + Frappe Framework                │
└─────────────────────────────────────────────────────────────────┘
                          ▲    HTTPS (REST)
                          │
                          ▼
                    ┌─────────────┐
                    │ Cashier PC  │
                    │  (in shop)  │
                    │             │
                    │ ┌─────────┐ │
                    │ │ Browser │ │  ← cashier opens /app/alphax-pos-classic
                    │ └─────────┘ │
                    │ ┌─────────┐ │
                    │ │ Bridge  │ │  ← optional: handles printer/drawer/scale
                    │ │ daemon  │ │     (separate Python program)
                    │ └─────────┘ │
                    │      ▲      │
                    │      │USB   │
                    │   Printer   │
                    │   Drawer    │
                    │   Scanner   │
                    │   Card term.│
                    └─────────────┘
```

### Why three apps and not one

- **`alphax_pos_suite`** — the main app. Lives in the GitHub repo
  `https://github.com/jamunachi08/alphax-pos-core-v15.5.1`. Contains
  the cashier, doctypes, workspace, security module.
- **`alphax_zatca`** — a fork of ERPGulf's `zatca_erpgulf` app. Kept
  separate because (a) it changes independently of the POS, (b) some
  customers use only the POS without ZATCA (non-KSA shops), (c) the
  upstream fork retains GPL-3 licensing.
- **`alphax-pos-bridge`** — a standalone Python daemon, NOT a Frappe
  app. Runs on each cashier PC. Talks to USB hardware. Communicates
  with the browser via WebSocket on `ws://localhost:9876`.

### Data flow at a sale

1. Cashier scans barcode → browser POSTs to Frappe (Sales Invoice)
2. Frappe creates the invoice → triggers `on_submit` hooks
3. `alphax_pos_suite` hooks update inventory, loyalty, audit log
4. `alphax_zatca` hook signs the invoice XML and submits to ZATCA portal
5. Frappe responds to browser
6. Browser tells the bridge daemon to print receipt + open drawer
7. Bridge daemon talks to printer/drawer over USB

---

## Pre-deployment checklist

Before you start, confirm you have:

### Frappe Cloud account

- [ ] A Frappe Cloud account (frappecloud.com)
- [ ] A bench provisioned for this customer (Singapore or AWS-Bahrain
      region recommended for KSA latency)
- [ ] Your bench's URL (e.g., `customername.k.frappe.cloud`)
- [ ] System Administrator credentials for the site

### Apps and source code

- [ ] Access to the GitHub repository:
      `https://github.com/jamunachi08/alphax-pos-core-v15.5.1`
- [ ] Same for the ZATCA fork (separate repo, ask the project owner)
- [ ] If self-hosted, the bench server has SSH access

### Customer information

- [ ] Customer's full legal name (for ZATCA registration)
- [ ] VAT number (15 digits)
- [ ] CR (Commercial Registration) number
- [ ] Branch addresses (each branch needs to be set up)
- [ ] Number of cashier stations per branch
- [ ] Hardware list: printer make/model, scanner brand, card terminal
      provider, cash drawer model

### ZATCA-specific (if KSA customer)

- [ ] Customer is registered on the [Fatoora portal][fatoora]
- [ ] Customer has agreed to provide the OTP from Fatoora when needed
- [ ] You know which production environment ZATCA uses for them
      (Phase 2 generation, post-2024)

[fatoora]: https://fatoora.zatca.gov.sa/

### Hardware (per cashier PC)

- [ ] Windows 10/11 PC, Linux Ubuntu 20+, or macOS 12+
- [ ] Modern browser (Chrome, Edge, Firefox)
- [ ] Stable internet connection
- [ ] USB ports for hardware
- [ ] Optionally: a label-maker for printing PC stickers
      (so manager knows "this PC = Terminal A07")

---

## Day 1: install the apps on your bench

✅ **Working**

### 1.1 Add the GitHub repo to your bench

In Frappe Cloud dashboard:

1. Go to **Bench → Apps → Add App**
2. Source: **From GitHub Repository**
3. URL: `https://github.com/jamunachi08/alphax-pos-core-v15.5.1`
4. Branch: `main` (or whichever your team uses)
5. Click **Add**

Frappe Cloud's deploy pipeline will pull, build, and prepare the app.

### 1.2 Install on your site

After the deploy succeeds:

1. Go to **Site → Apps**
2. Click **Install** next to `alphax_pos_suite`
3. Wait for the green check (~1-2 minutes)

### 1.3 (Optional) Install the ZATCA companion app

If your customer is in KSA and needs Phase 2 e-invoicing:

1. Repeat 1.1 with the ZATCA repo URL
2. Install on the same site

### 1.4 Verify installation

Open `/app/alphax-pos-hub` in a browser. You should see the workspace
with 9 module cards: Operations, Setup & Configuration, Catalog &
Pricing, Sales & Customers, Pharmacy, Compliance & Tax, Reports &
Analysis, Loyalty & Offers, Data Import & Settings.

If you see "Not Found" or the workspace is empty, see the
troubleshooting section.

### 1.5 Verify versions

Click anywhere → **Help → About** in the desk. The Installed Apps list
should show:

- ✅ **alphax_pos_suite: v15.5.13** (or latest)
- ✅ **alphax_zatca: v3.0.x** (if installed)

---

## Day 2: company, branch, outlet, terminal hierarchy

✅ **Working**

This is the core data hierarchy. Get it right before doing anything else.

```
Company
├── Branch (e.g., "Riyadh Mall")
│   ├── Outlet (e.g., "Coffee Shop")
│   │   ├── Terminal A07
│   │   ├── Terminal A08
│   │   └── ...
│   └── Outlet (e.g., "Pharmacy")
│       └── Terminal P01
└── Branch (e.g., "Jeddah Souq")
    └── ...
```

### 2.1 Create the company

If new install, ERPNext will already prompt you. If not:

1. Go to `/app/company/new`
2. Required: Company Name, Abbreviation, Default Currency (SAR for KSA),
   Country (Saudi Arabia)
3. ZATCA-required: Tax ID (15-digit VAT number), Company Registration
   Number, Address (with district, city, postal code, country)
4. Save

> ⚠️ **Don't skip the address.** ZATCA Phase 2 requires the seller's
> address on every invoice. Missing fields cause invoice submission
> to fail.

### 2.2 Create branches

For each physical store location:

1. Go to `/app/branch/new`
2. Branch name: human-readable (e.g., "Riyadh Mall — Branch 02")
3. Save

### 2.3 Create outlets

For each business unit within a branch:

1. Go to `/app/alphax-pos-outlet/new`
2. Outlet Name: human-readable (e.g., "Coffee Shop")
3. Branch: link to the parent branch
4. Domain Pack (optional): pick the vertical (Restaurant, Retail,
   Pharmacy, Electronics, Generic) — affects which features the
   cashier shows
5. Default Warehouse: where stock for this outlet lives (often a
   Branch-level warehouse)
6. Default Cost Center
7. Save

> 💡 **Outlets are the operational unit** — most reports and
> permissions are by outlet, not branch. Create one outlet per
> business unit even if the branch only has one shop.

### 2.4 Create terminals

For each physical cashier station:

1. Go to `/app/alphax-pos-terminal/new`
2. Terminal Name: short code (e.g., "A07", "P01")
3. POS Outlet: link to the parent outlet
4. (Optional) Default POS Profile: a POS Profile to suggest
5. (Optional) Hardware tags: which printer, which scanner, etc.
6. Save

> 💡 **Use a labeling system for terminal names** that makes physical
> sense. "A07" = "Aisle A, station 07". Or "RM-CS-01" = "Riyadh Mall,
> Coffee Shop, station 01". Whatever you pick, label the actual PCs
> with stickers so managers know which terminal to bind during setup.

### 2.5 Verify the hierarchy

Open `/app/alphax-pos-terminal` and look at the list. You should see
each terminal with its outlet visible. Click into one — the breadcrumb
should show you Branch → Outlet → Terminal.

---

## Day 3: POS Profile and payment methods

✅ **Working**

POS Profiles are standard ERPNext doctypes that define a cashier's
operational permissions. AlphaX POS uses these directly.

### 3.1 Create payment methods (Mode of Payment)

Before profiles, make sure you have payment methods:

1. Go to `/app/mode-of-payment`
2. Standard ones: Cash, Mada (KSA debit), Visa, Mastercard, Apple Pay,
   Bank Transfer, Credit Note, Loyalty Points
3. Each has an "Account" field — link to the appropriate cash or
   bank account in your chart of accounts
4. Mark which are "POS"-enabled

### 3.2 Create a POS Profile

For each role/outlet combination:

1. Go to `/app/pos-profile/new`
2. Name: human-readable (e.g., "Coffee Shop Cashier")
3. Company, Customer (default walk-in), Currency
4. **Warehouse**: where stock comes from for this profile's sales
5. **Mode of Payment table**: list all accepted payment methods
6. **Applicable for Users**: list specific cashiers OR leave empty for "all"
7. **Item Groups**: filter what items show up
8. **Taxes and Charges Template**: link to a Sales Tax template
9. **Letter Head, Print Heading**: for receipts
10. **Update Stock** (check — usually yes)
11. **Apply Discount on**: Grand Total or Net Total
12. Save

### 3.3 Link the profile to your AlphaX outlet

After saving, also link the POS Profile to the AlphaX POS Outlet:

1. Open the AlphaX POS Outlet record
2. Set "Default POS Profile" if there's only one for this outlet
3. Or set per-cashier in their User record (if your shop assigns by user)

### 3.4 Test it

The cashier won't fully work until users are assigned and PINs are
set, but you can verify the data setup by going to
`/app/alphax-pos-classic` as System Administrator. The "Station Not
Configured" card should appear (because no terminal is bound to your
admin's PC). Don't bind it yet — that's for cashier PCs, not yours.

---

## Day 4: items, taxes, pricing

✅ **Working**

### 4.1 Item groups

Create item groups that match how your customer thinks about their
products:

```
All Item Groups
├── Beverages
│   ├── Hot Drinks
│   └── Cold Drinks
├── Food
│   ├── Sandwiches
│   └── Desserts
├── Pharmacy (separate vertical)
│   ├── OTC
│   └── Prescription
└── Services
```

### 4.2 Items

Create each sellable product:

1. Go to `/app/item/new`
2. Item Code: short, scannable (e.g., "WAT-001")
3. Item Name: human-readable
4. Item Group
5. Default Unit of Measure
6. **Maintain Stock**: yes for retail/pharmacy, no for services
7. **Is Sales Item**: yes
8. **Standard Selling Rate** in the Item Defaults table
9. Save

> 💡 **For barcode-driven workflows**, the Item Code IS the barcode.
> Or add separate barcodes via the Item's "Barcodes" child table.

### 4.3 Item taxes

For VAT (KSA) and similar:

1. Go to `/app/sales-taxes-and-charges-template`
2. Create "KSA Standard 15% VAT" template
3. Add row: Account Head = "VAT 15% - Output", Rate = 15
4. Mark the "Inclusive" checkbox if your prices include VAT
5. Save

Link this template on POS Profiles → Taxes section.

### 4.4 Inclusive vs exclusive VAT

KSA shops typically display prices INCLUSIVE of VAT (the customer sees
the total they pay). Configure:

- POS Profile → "Apply Discount on" → Net Total
- Sales Tax Template → mark "Included in Print Rate"
- Item rate = price-with-VAT (e.g., 11.50 SAR for a 10-SAR-net coffee)

The system breaks out VAT on the receipt automatically.

### 4.5 Item pricing rules

For "Buy 2 get 1 free", "10% off Tuesdays", loyalty discounts:

1. Go to `/app/pricing-rule/new`
2. Filter: by item, item group, customer group, or all
3. Apply on: Discount Percentage / Discount Amount / Free Item
4. Conditions: Min/Max quantity, Date range, Day of week
5. Save

### 4.6 Test with a dummy item

Open the cashier (you'll need to bind your test PC first). Scan or
type the item code. Confirm the price, taxes, and any discounts are
applied as expected.

---

## Day 5: users, roles, manager PINs

✅ **Working**

### 5.1 Create the AlphaX POS Manager role (if not present)

The role is auto-created on app install, but verify:

1. Go to `/app/role`
2. Search for "AlphaX POS Manager"
3. If missing, create with:
   - Name: AlphaX POS Manager
   - Description: "Authorizes register-side privileged actions
     (returns, discounts, station setup, voids)"
4. Save

### 5.2 Create cashier users

For each cashier:

1. Go to `/app/user/new`
2. First Name, Last Name, Email (will be username)
3. Set a temporary password OR send password reset link
4. **Roles** tab: assign "Sales User" + "POS User" + (optional)
   "Stock User"
5. **Restrict by User Permissions**: optionally restrict by company,
   warehouse
6. Save

### 5.3 Create manager users

For each manager:

Same as cashiers, plus:
1. **Roles** tab: ALSO assign "AlphaX POS Manager"
2. Don't grant System Manager unless they truly need full admin

### 5.4 Set manager PINs

This is currently CLI-only — there's no admin UI for it yet.

In Frappe Cloud:
1. Site → Console (in the bench dashboard)
2. Run:

```python
import frappe
frappe.call(
    'alphax_pos_suite.alphax_pos_suite.security.manager_pin.set_manager_pin',
    user='khalid@example.com',
    pin='8472'
)
```

Replace the email and PIN. The PIN must be 4-6 digits.

The system:
- Verifies the user has a manager role
- Hashes the PIN with bcrypt (12 rounds)
- Saves to `AlphaX POS Manager PIN` doctype
- Resets any prior lockout state
- Logs the action in the Authorization Log

> 💡 **Tell the manager their PIN privately.** Don't email it. Don't
> WhatsApp it. Walk over and tell them, or use a password manager
> share if your team has one.

### 5.5 Test PIN authentication

1. Open `/app/alphax-pos-classic` on a non-bound PC (the test bench
   admin's own browser is fine)
2. Click "Manager Setup"
3. Type the manager's username + PIN
4. Verify the green "Authorized" message appears
5. Pick any terminal to bind (you can reset right after)
6. Confirm the cashier UI loads

### 5.6 Reset a forgotten PIN

If a manager forgets:

```python
import frappe
frappe.call(
    'alphax_pos_suite.alphax_pos_suite.security.manager_pin.set_manager_pin',
    user='khalid@example.com',
    pin='9999'  # NEW pin
)
```

This resets the PIN AND clears any lockout state.

### 5.7 Reset a locked-out manager

If lockout was triggered without resetting the PIN itself:

```python
import frappe
frappe.call(
    'alphax_pos_suite.alphax_pos_suite.security.manager_pin.reset_manager_lockout',
    user='khalid@example.com'
)
```

---

## Day 6: ZATCA Phase 2 setup

✅ **Working** for the integration code
🚧 **In Development** — full guided onboarding UI (manual steps for now)

> ⚠️ **This section is critical for KSA customers.** Mistakes mean
> invoices don't submit, leading to compliance violations.

### 6.1 Confirm ZATCA registration

Before configuring the system, your customer must:

1. Be registered on [Fatoora portal][fatoora]
2. Have a valid VAT certificate
3. Be aware they're moving to Phase 2 (Integration / Generation phase)

If they're not yet registered, that's a tax-consultant task — not
a software task. Don't proceed without it.

### 6.2 Generate device certificates

Each cashier device that submits invoices needs its own CSID
(Cryptographic Stamp Identifier). The flow:

1. Cashier admin opens the AlphaX ZATCA app's onboarding page
2. Enter OTP from the Fatoora portal
3. The app generates a private key + CSR
4. App submits CSR to ZATCA
5. ZATCA returns the device certificate
6. Certificate is stored on the device (or in the bench, depending on
   your deployment model)

> 🚧 **Manual step for v15.5.13:** The full guided UI is in
> development. For now, follow ERPGulf's documentation in the
> `alphax_zatca` repo for the device-onboarding flow. The fork retains
> their tooling.

### 6.3 Production vs sandbox

ZATCA has separate sandbox and production environments. Configure:

1. Go to `/app/alphax-zatca-settings` (or equivalent in the fork)
2. Set "Mode" = Sandbox while testing
3. Switch to Production only after successful sandbox tests

### 6.4 Verify e-invoicing on a test sale

1. Make a test sale on a cashier PC
2. Check `/app/alphax-pos-processing-log` (the workspace shortcut
   "ZATCA Status")
3. The new invoice should appear with status "Submitted" or "Pending"
4. After a few seconds, "Submitted" should become "Cleared"
5. The QR code on the receipt should be a valid Phase 2 ZATCA QR

If status stays "Failed", drill into the row for the error message.
Most common causes:
- Device certificate not provisioned for this terminal
- VAT number missing on customer
- Inclusive VAT misconfigured
- Time desync between bench and ZATCA (rare; ZATCA is strict on
  timestamps)

---

## Day 7: hardware bridge — printers, drawers, scanners

✅ **Working** for browser-only flows (no special hardware needed)
🔬 **Beta** for the bridge daemon

### 7.1 What works without the bridge

Out of the box, with a standard browser and a USB receipt printer
configured at the OS level, you can:

- Print receipts via the browser's print dialog
- Use a USB barcode scanner (acts as a keyboard, no setup needed)
- Capture cash payments (no drawer hardware needed for amount entry)

For many small shops, this is enough. Skip to Day 8.

### 7.2 What requires the bridge

If you need:

- Auto-cut receipts (no print dialog)
- Cash drawer that opens automatically after a sale
- Weight scale integrated with item entry
- Card terminal that exchanges payment data with the POS automatically
- Direct ESC/POS commands to specific printer models

…you need the AlphaX POS Bridge daemon running on each cashier PC.

### 7.3 Installing the bridge

The bridge is a separate Python program in its own GitHub repo.

> 🔬 **Status:** The bridge codebase exists with installer scaffolding
> (PyInstaller, Inno Setup for Windows, .deb for Linux), but the
> end-to-end installer has not been certified for production. For
> v15.5.13 deployments, treat the bridge as Beta.

### 7.4 Bridge → browser communication

The bridge listens on `ws://localhost:9876`. The browser connects to
it for hardware actions:

```
Browser ←─WebSocket─→ Bridge daemon ←─USB─→ Hardware
```

If the bridge is offline, the cashier still works — it just can't
auto-print or open the drawer.

### 7.5 Testing the bridge

After install:

1. Start the bridge daemon (`alphax-bridge` command)
2. In the cashier, click any test buttons (planned for `/app/alphax-pos-hardware-test`)
3. Verify printer prints, drawer opens, scanner reads

> 🚧 **The hardware test page is in development.** For v15.5.13, test
> by completing a real sale and verifying receipt + drawer behavior.

---

## Domain packs: configuring per-vertical features

✅ **Working**

A "domain pack" is a configuration that turns on/off features for a
vertical. You set the domain pack per Outlet.

### Available packs

- **Restaurant** — Floor Plan, KDS, Modifiers, Service Charge, Tips
- **Retail** — Standard cart with stock check
- **Pharmacy** — Drug Master, Prescriptions, Controlled Substance Log,
  Drug Interaction Rules
- **Electronics** — Serial Number capture, Warranty registration
- **Generic** — Bare cart, no extras

### How to switch a domain pack

1. Go to `/app/alphax-pos-outlet`
2. Open the outlet
3. **Domain Pack** field: pick the right one
4. Save

Cashiers at this outlet will see the relevant features enabled on
next page reload.

### Mixing packs across outlets

Each outlet has its own pack, even within a single branch. So a
"Riyadh Mall" branch can have both "Coffee Shop" (Restaurant pack)
and "Pharmacy" (Pharmacy pack) outlets, each with the right features.

---

## Loyalty, offers, pricing rules

✅ **Working**

### Loyalty program setup

1. Go to `/app/loyalty-program/new`
2. Define earn rate (e.g., 1 point per 1 SAR spent)
3. Define redemption value (e.g., 100 points = 10 SAR off)
4. Set expiry policy (typical: 1 year)
5. Save

In POS Profile, link the Loyalty Program. Cashiers can see and apply
loyalty automatically.

### Offers (campaigns)

1. Go to `/app/alphax-pos-offer/new`
2. Code: a coupon code customers can type at checkout
3. Discount: percent or amount
4. Date range
5. Item / Item Group filter
6. Min purchase
7. Save

The cashier's "Offer Code" field accepts these codes.

### Pricing rules

For non-coupon discounts (volume discounts, Tuesday discounts, etc.),
use ERPNext's standard Pricing Rule doctype. See Day 4 above.

---

## Pharmacy domain: drugs, prescriptions, controlled substances

✅ **Working** for the data model
🔬 **Beta** for the cashier UI integration (Vue cashier only)
🚧 **In Development** — full prescription capture in Classic cashier

### 11.1 Drug Master setup

Each medication is an Item AND an AlphaX Drug Master record:

1. Item Code is the same on both
2. AlphaX Drug Master adds:
   - Active ingredient
   - Strength
   - Form (tablet, capsule, syrup, etc.)
   - Route (oral, topical, IV)
   - Schedule (Schedule II, IV, OTC)
   - Max refills, refill cap

### 11.2 Drug Interaction Rules

Define which combinations are dangerous:

1. Go to `/app/alphax-drug-interaction-rule/new`
2. Drug A, Drug B
3. Severity: Major / Moderate / Minor
4. Mechanism (free-text explanation)
5. Save

The cashier will warn at scan time when a customer tries to buy two
interacting drugs in the same transaction.

### 11.3 Controlled Substance Log

Every dispense of a Schedule II/III/IV drug auto-creates an
AlphaX Controlled Substance Log entry. This is a regulatory
requirement in some jurisdictions.

The log has:
- Drug, quantity, batch
- Patient identifier
- Prescribing physician
- Pharmacist who dispensed
- Timestamp

Auditable. Cannot be deleted by users (System Manager too).

### 11.4 Prescription capture

> 🚧 **In Development** — for v15.5.13, prescriptions are entered
> as documents (`/app/alphax-prescription/new`) and the cashier sale
> is linked to them via the customer field. Full inline prescription
> entry from the cashier is on the roadmap.

---

## Routine administration tasks

### 12.1 Daily

- Check ZATCA Status (workspace shortcut) for any failed submissions
- Review Manager Authorization Log for unusual patterns
- Confirm all shifts closed cleanly yesterday

### 12.2 Weekly

- Review Sales Register for variance trends
- Check inventory adjustments
- Backup verification (see "Backup and disaster recovery" below)

### 12.3 Monthly

- Rotate manager PINs (optional but recommended)
- Review Item pricing — anything stale?
- ZATCA certificate expiry check (most renew yearly)
- User access audit — anyone left the company?

### 12.4 Yearly

- ZATCA recertification (per ZATCA's schedule)
- Frappe Cloud bench upgrade (Frappe v15 → v16 when stable)
- Customer's tax-year close

---

## Backup and disaster recovery

✅ **Frappe Cloud handles this** for you.

### What Frappe Cloud does automatically

- Daily SQL dumps of the site database
- Daily file backups (uploaded files, certificates, etc.)
- 14 days of restore points kept

### What you should do additionally

- **Monthly off-site copy**: download a backup to your own storage
  monthly. Frappe Cloud is reliable but a customer-side copy is
  defense in depth.
- **Test a restore**: at least once, verify a backup can actually
  restore. Don't discover backup is broken in an emergency.

### Disaster scenarios

**Site is unreachable**: contact Frappe Cloud support. Usually
resolved in <1 hour.

**Database corruption**: restore from latest backup. You lose any
sales between backup and corruption (typically <24 hours). Use the
offline Sync Queue on cashier PCs if any sales weren't synced
when corruption happened.

**Customer's bench is decommissioned**: download all backups, save
them. Customer can re-deploy on a new bench from these backups.

---

## Troubleshooting

### Cashier shows "Station Not Configured" forever

Manager hasn't bound the PC yet. See Day 5 — "Test PIN authentication".

### Manager PIN dialog says "Incorrect credentials"

Possible causes:
- Manager mistyped → try again
- Manager doesn't have the AlphaX POS Manager role → grant it
- PIN was never set for this manager → set it (Day 5.4)
- Manager is locked out → reset (Day 5.7)

The error is intentionally generic to prevent enumeration of valid
managers. Look at the **AlphaX POS Manager Authorization Log** to
see what actually happened.

### Some assets serve, others 404

If `/assets/alphax_pos_suite/dist/vendor/...` works but
`/assets/alphax_pos_suite/dist/cashier/...` returns 404 — this is
a Frappe Cloud bench issue. Run from the bench shell:

```bash
bench --site <your-site> build --app alphax_pos_suite --hard-link
bench --site <your-site> migrate
bench restart
```

If still failing, contact Frappe Cloud support — the symlink for the
app's public folder may be broken.

### ZATCA invoice failed

Drill into the row in **AlphaX POS Processing Log**. The error
column tells you why. Common fixes:

- "Invalid VAT number" → fix on the Customer record, resubmit
- "Device certificate expired" → reissue via the ZATCA companion app
- "Time skew" → check NTP on bench server (Frappe Cloud does this
  automatically; report to support if persistent)

### Slow cashier on a specific PC

Possible causes:
- Network: check ping to your bench
- Browser: try Chrome instead of older browsers
- Hardware: bridge daemon eating CPU? Restart it
- Cashier UI: hard-refresh (Ctrl+Shift+R) to clear cached JS

### Audit log is empty even after manager actions

Check that `frappe.log_error` isn't suppressing failures. From the
bench console:

```python
import frappe
frappe.get_all("Error Log", fields=["error", "creation"], limit=5)
```

If you see "AlphaX POS: failed to write authorization audit log"
errors, the audit doctype itself may have issues. Run migrate, then
re-test.

---

## Glossary

**Bench** — A Frappe deployment unit. One bench can host multiple
sites. Frappe Cloud customers usually have one bench per Frappe
Cloud account.

**Bcrypt** — A password-hashing algorithm. Used for manager PINs.
Slow by design (12 rounds takes ~50ms) — defends against offline
brute-force.

**Branch** — A standard Frappe doctype for physical store locations.

**Bridge** — The AlphaX POS Bridge daemon, a separate Python program
running on each cashier PC. Handles USB hardware.

**CSID** — Cryptographic Stamp Identifier. The certificate ZATCA
issues per device for Phase 2 e-invoicing.

**Domain Pack** — A bundle of features turned on/off for a vertical
(Restaurant, Retail, Pharmacy, etc.). Set per outlet.

**Fatoora** — ZATCA's portal for VAT registration and e-invoicing
device management.

**Outlet** — An AlphaX-specific doctype for business units within a
branch.

**POS Profile** — Standard ERPNext doctype defining cashier
permissions and settings.

**Sandbox / Production (ZATCA)** — Two ZATCA environments. Sandbox
for testing, Production for live invoices.

**System Manager** — Frappe role with full access. Use sparingly.
Required for: bench-level operations, setting manager PINs,
clearing lockouts, accessing audit logs at scale.

**Terminal** — An AlphaX-specific doctype for individual cashier
stations within an outlet.

---

## Quick reference: cheat sheet

| Task | Where |
|---|---|
| New install | Bench → Apps → Add App from GitHub |
| Create a Branch | `/app/branch/new` |
| Create an Outlet | `/app/alphax-pos-outlet/new` |
| Create a Terminal | `/app/alphax-pos-terminal/new` |
| Create POS Profile | `/app/pos-profile/new` |
| Set Manager PIN | Bench → Console → `frappe.call(...)` |
| ZATCA Status | `/app/alphax-pos-processing-log` |
| Audit Log | `/app/alphax-pos-manager-authorization-log` |
| User management | `/app/user` |
| Today's Sales | `/app/sales-register` (filtered today) |
| Workspace | `/app/alphax-pos-hub` |

---

*Manual version 15.5.13 — May 2026.*
