# AlphaX POS Suite — v16.4.0

**Receipt Designer with a ZATCA QR block, and AlphaX Wallet gift cards.**

## Receipt Designer (Process flow board → L1)

- **Desk page "Receipt Designer"**: arrange blocks top to bottom, set align,
  size, bold, English and Arabic text, hide or reorder, and see a live preview
  at true paper width (80, 76 or 58 mm) against any submitted POS invoice.
- Blocks: Logo, Title, Company & VAT, Outlet & Address, Invoice Details,
  Customer, Items, Totals, VAT Breakdown, Payments, **ZATCA QR**, Loyalty &
  Gift Balance, Text, Divider, Spacer. Language: Arabic, English or both.
- **ZATCA check built in.** The designer and the template form list anything
  a simplified tax invoice must show and the layout omits: the title
  "Simplified Tax Invoice / فاتورة ضريبية مبسطة", seller name and VAT number,
  invoice number and date/time, items with quantity and price, VAT amount,
  total including VAT, and the QR.
- Per outlet: **Receipt template** on AlphaX POS Outlet; one template can be
  the default. New print format **AlphaX Receipt** renders whichever applies.
  Templates are data, not Jinja, and every value is escaped.

### ZATCA QR

- If the ZATCA app has stamped the invoice (Phase 2: tags 1–9 including hash
  and signature), that QR is printed as-is.
- Otherwise the Phase-1 QR (seller, VAT number, UTC timestamp, total with VAT,
  VAT) is built here. Its encoding matches the worked example in ZATCA's QR
  guidance byte for byte, including Arabic seller names (lengths in UTF-8
  bytes).
- The image is drawn **on this server** (PyQRCode, already part of Frappe).

**Fixed:** the existing *AlphaX Thermal 80mm* receipt fetched its QR image
from a public QR web service, sending every invoice's VAT number and totals
to a third party abroad and printing no QR whenever the till was offline. It
now uses the local QR.

## AlphaX Wallet — gift cards

### What it does

- **Sell** a card at the desk page *Gift Cards* (or activate a pre-printed
  card by scanning it). The full number — and a PIN for cards at or above the
  PIN threshold — is shown **once**.
- **Spend** at the till: Payment → **🎁 Gift card** → scan or type the number
  (PIN if required) → the balance shows → apply up to the remaining due.
  Several cards on one sale are fine. The gift card tender can only be used
  through a checked card.
- **Reload**, **statement**, **refund and void** (manager), **batches** for
  pre-printed or corporate cards (generate → CSV of numbers and PINs as a
  private file → activate when paid), and a public **balance check page** at
  `/giftcard`.
- **Receipts** show the remaining balance of each card used (Loyalty & Gift
  Balance block).

### Accounting and VAT

- A card sale posts **Dr tender account / Cr gift card liability**. No Sales
  Invoice, because nothing has been supplied yet.
- Treated as a **multi-purpose voucher**: no VAT at sale; VAT arises on the
  invoice where the card is spent, at the goods' own rates. Confirm with your
  tax adviser for single-purpose use (for example, a card valid for one
  specific product).
- Spending: the invoice's gift card payment line uses the gift card Mode of
  Payment, whose account **is** the liability account, so the invoice
  releases the liability; the ledger entry references the invoice and posts
  no second journal. Cancelling the invoice restores the balance.
- Expiry (daily) moves remaining balances to the **breakage** account, if one
  is set; otherwise the balance stays a liability and the entry says so.
- **Setup** (Gift Cards page → menu → *Set up gift cards for a company*):
  creates *Gift Cards Payable* under Current Liabilities and a *Gift Card*
  Mode of Payment linked to it, or tells you what to fix.

### Security

- Only an **HMAC of the card number** (keyed with the site's encryption key)
  and the last four digits are stored; a leaked table does not reveal usable
  numbers. Numbers are 16 digits with a **Luhn** check digit.
- **PIN** from the configured value up; five wrong PINs lock the card for 30
  minutes.
- The till gets a **short-lived authorisation token** after a check; the
  invoice carries the token, and on validation it is replaced by the card
  hash — no card number on any invoice.
- Every balance change **locks the card row** and re-checks the balance in
  the same transaction, so two tills cannot spend the same money.
- The ledger (*AlphaX Gift Card Entry*) cannot be edited or deleted.
- Public balance check: 10 per hour per IP; shows masked number, balance and
  expiry only.

### Limits in this release

- **Refunds onto a gift card** are refused at the till; refund to store
  credit or cash. (Reload is available from the desk page.)
- Gift card tender needs the till to be **online** for the check; an offline
  till cannot accept gift cards.

## Other changes

- Store credit module docstring no longer names a third-party product.
- Till: PaymentDialog and the POS store updated (gift card tender, token
  handling, Arabic/English strings); SPA payload rebuilt.

## Tests

- `simulate_receipts_giftcards.py`: ZATCA example byte-for-byte, Arabic TLV,
  local QR rendering, no external QR service, default layout passes the
  compliance rule, 2000 unique Luhn-valid numbers, keyed hashing, PIN, row
  locking, hooks wired, till sends tokens not numbers.
- The edited Vue component compiles with the Vue SFC compiler; store syntax
  checks.
- All 20 simulations, `verify_tree.py` and the v16 health check pass.

Not yet run on a live site. On staging: run gift card setup for the company,
sell a card, spend part of it at the till, cancel that invoice, and print the
receipt with the designer template; scan the QR with ZATCA's validation app.
