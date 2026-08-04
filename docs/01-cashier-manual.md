# AlphaX POS — Cashier Manual

**For:** Cashiers and front-line staff using the POS register
**Version:** 15.5.13
**Last updated:** May 2026

---

## What's in this manual

1. [Before your first shift](#before-your-first-shift)
2. [Logging in and starting your day](#logging-in-and-starting-your-day)
3. [Selling: from scan to receipt](#selling-from-scan-to-receipt)
4. [Cart actions: adjust, void, hold](#cart-actions-adjust-void-hold)
5. [Taking payments](#taking-payments)
6. [Refunds and returns](#refunds-and-returns)
7. [Held orders: pause and resume sales](#held-orders-pause-and-resume-sales)
8. [Credit notes and customer credit](#credit-notes-and-customer-credit)
9. [Offline mode: keeping the register working](#offline-mode-keeping-the-register-working)
10. [End of your shift](#end-of-your-shift)
11. [Common problems and quick fixes](#common-problems-and-quick-fixes)
12. [Glossary](#glossary)

---

## Before your first shift

Welcome to AlphaX POS. This manual teaches you how to use the cashier
register. You don't need to know anything about Frappe, ERPNext, or
software development to follow it.

### What you need from your manager before your first day

- ✅ A **user account** (your username is usually your work email)
- ✅ Your **password** for that account
- ✅ The **branch and terminal** you'll be working at
- ✅ **One quick walkthrough** of your branch's specific procedures
  (every shop has small differences in cash counting, returns policy,
  etc.)

### What you don't need

- ❌ Any technical knowledge
- ❌ Your own device — the cashier PC at your station is set up by
  the manager
- ❌ A "manager PIN" — that's for managers only

### Status of features in this manual

> ✅ **Working** = ready to use today
> 🔬 **Beta** = available but might change soon
> 🚧 **In Development** = coming in a future update; ignore for now

---

## Logging in and starting your day

✅ **Working**

### Step 1: Open the browser at your cashier station

Your cashier PC's browser usually opens to the AlphaX POS login page
automatically. If not, the address looks like:

```
https://your-company.k.frappe.cloud
```

You'll see a login screen.

### Step 2: Enter your username and password

Type your work email as the username, then your password. Click
**Login**.

> 💡 **Tip:** If you forgot your password, use the "Forgot Password"
> link on the login page. The system will email you a reset link.
> If you don't have email access, ask your manager to reset it.

### Step 3: Open the cashier page

After login, you land on the AlphaX POS Hub workspace. Click
**"Open Cashier"** at the top, or navigate to:

```
https://your-company.k.frappe.cloud/app/alphax-pos-classic
```

### Step 4: First-time setup of your station (if you see this screen)

Most days, the cashier opens straight to the register. But on a brand-new
PC, or if a manager has reset the station, you'll see a card that says:

> 🔒 **Station Not Configured**
> This computer hasn't been bound to a POS terminal yet.
> A manager must complete a one-time setup before this station can take orders.

**You cannot fix this yourself.** Walk over to your manager, who will:

1. Click **Manager Setup**
2. Type their username and PIN
3. Pick the right terminal for this PC

After they're done, the cashier register will load and stay loaded for
every future shift on this PC.

### Step 5: Confirm the station banner

Once the cashier loads, look at the top of the page. You should see
a banner like:

```
STATION   Riyadh ›  Coffee Shop  ›  Terminal A07
```

Make sure this matches where you're physically standing. If it's wrong,
**don't ring up any sales** — get your manager to re-bind the PC.

---

## Selling: from scan to receipt

✅ **Working**

The basic flow is: scan items → take payment → submit. Let's break that
down.

### Adding items to the cart

You have two ways to add items:

**Method 1: Barcode scan (fastest)**
1. Click into the **Scan / Item Code** field (it should be focused
   automatically when the page loads)
2. Pull the trigger on your barcode scanner aimed at the product's
   barcode
3. The item appears in the cart with quantity 1

**Method 2: Type the item code manually**
1. Click into the **Scan / Item Code** field
2. Type the item's code (your manager has a list, or print one)
3. Press **Enter**
4. The item appears in the cart

### Adjusting quantity before adding

If you need 3 of something:
1. Type the quantity in the **Qty** field (it stays at 1 by default)
2. Then scan or type the item code
3. The item is added with the quantity you set

After scanning, the **Qty** field resets to 1 for the next item.

### What you'll see in the cart

Each line in the cart shows:

- The item code (e.g., **WAT-001**)
- Rate (price per unit)
- Quantity
- Subtotal (rate × quantity)
- Three buttons on the right: **−** (decrease), **+** (increase),
  **×** (remove)

The cart total updates automatically at the bottom.

### Adding multiple items quickly

Just keep scanning. Each scan adds another line (or increments the
quantity if the item is already in the cart — depends on your branch's
settings).

---

## Cart actions: adjust, void, hold

✅ **Working**

### Increase or decrease quantity

For an existing line:
- Click **+** to add one more
- Click **−** to remove one (if it goes to 0, the line is removed)

### Remove an item entirely

Click the red **×** button on the right of the line.

> 💡 **Tip:** If you misclick or remove the wrong item, just scan it
> again to add it back. Nothing is permanent until you click
> **Pay & Submit**.

### Void / cancel the entire sale

If the customer changes their mind and walks away with no items:

1. Click **×** on each cart line until the cart is empty
2. The cart is now ready for the next customer

> 🚧 **In Development:** A "Void Whole Sale" button is coming. For
> now, removing items one at a time is the way.

### Hold the order (customer is taking too long)

If a customer needs to step away (forgot their wallet, going to grab
another item):

1. Click **Hold**
2. The current cart is saved as a "held order"
3. The cart clears, ready for the next customer
4. When they come back, find their order in the **Held Invoices**
   panel on the right and click **Open**

---

## Taking payments

✅ **Working**

### Single payment method

Most sales:

1. After all items are in the cart, click **Pay & Submit**
2. The system asks for a **Mode of Payment** (Cash, Card, etc.)
3. Type the **Amount** the customer is paying
4. Click **Add Payment**
5. If the amount equals or exceeds the total, the sale completes and
   the receipt prints

### Split payments (cash + card, etc.)

Some customers want to pay part in cash and part on card:

1. After items are in the cart, click in the **Payments** section
2. Pick the first payment method (e.g., **Cash**)
3. Type the cash amount
4. Click **Add Payment** — the line appears in the payment list
5. Pick the second method (e.g., **Card**)
6. Type the remaining amount
7. Click **Add Payment**
8. When total payment ≥ cart total, click **Pay & Submit**

### Removing a payment line

If you typed the wrong amount, click the red **×** next to the
payment line and re-enter it.

### Receiving change

The system shows the change due based on payments minus total. Hand
the difference to the customer and the receipt will print.

### Receipt printing

After **Pay & Submit** succeeds:
- The receipt prints automatically (if a printer is connected)
- The cart clears for the next customer
- A confirmation message appears briefly at the top

If the receipt didn't print, see [Common problems](#common-problems-and-quick-fixes).

---

## Refunds and returns

✅ **Working** for cash returns
🔬 **Beta** for credit-note returns

### Step 1: Click "Return"

The big red **Return** button starts a return. The cashier asks you
to find the original sale.

### Step 2: Find the original invoice

You can search by:
- Invoice number
- Customer name
- Date range

Click on the right invoice. The cart loads with the original items as
**negative quantities** (e.g., qty = -1 means "give 1 back").

### Step 3: Adjust if it's a partial return

If the customer is only returning some items:

1. Use the **−** button to bring negative quantities closer to 0
   (e.g., if they bought 3 and are returning 1, change qty from -3
   to -1)
2. Click **×** to remove items they're keeping

### Step 4: Process the refund

Click **Pay & Submit**. The system asks how to settle:

- **Cash refund:** Hand the customer cash. Mode of payment = Cash,
  Amount = (negative total).
- **Credit note:** No cash leaves the till. The customer gets a
  credit note they can use on a future visit.

> ⚠️ **Manager approval may be required.** If your store's settings
> require manager approval for returns over a certain age or amount,
> the system asks for a manager PIN before completing.

---

## Held orders: pause and resume sales

✅ **Working**

### When to hold an order

- Customer forgot something and is going to fetch it
- Customer wants to add items but the line is getting long
- You need to help another customer briefly

### How to hold

Click **Hold** on the order entry card. The cart clears.

### How to resume

Look at the **Held Invoices** panel on the right side of the cashier
screen. You'll see a list of held orders by their reference number
and customer name.

Click **Open** next to the right one. The cart fills with their items.
You can:
- Add more items
- Adjust quantities
- Take payment as normal

> 💡 **Tip:** If a held order has been sitting for too long (customer
> never came back), ask your manager. They can clean up old held
> orders so the list stays manageable.

---

## Credit notes and customer credit

✅ **Working**

### What is a credit note?

When a customer returns an item but doesn't want cash back (or your
shop policy doesn't allow it), they get a credit note instead. It's
a record of credit they have at your store, redeemable on a future
purchase.

### Redeeming a credit note

1. Customer arrives with their credit note (paper printout, email,
   or just the number)
2. Build their cart as normal
3. In the **Payments** section, click **Redeem Credit Note**
4. Type or paste the credit note number
5. The system shows the available balance
6. Type how much to apply
7. Click **Add Payment**

The credit note balance reduces by the amount used. If they spent
less than their credit, the balance stays for next time.

### What if the credit note is expired?

The system tells you. Most shops have a 1-year expiry on credit notes.
If expired, point the customer to your manager for an exception.

---

## Offline mode: keeping the register working

✅ **Working**

### What "offline" means

Internet connections drop. When yours does, the cashier doesn't stop
working — it queues sales locally and submits them when the connection
comes back.

### How you'll notice you're offline

- The **Sync Queue** counter at top-right shows a number > 0
- Submitting a sale shows a brief yellow notice: "Saved offline"
- The receipt still prints

### What still works offline

- ✅ Scanning items
- ✅ Adding to cart
- ✅ Taking payments (cash always; card only if card terminal is
  also connected directly to the PC)
- ✅ Printing receipts
- ✅ Holding orders (saved locally, will sync)

### What doesn't work offline

- ❌ Looking up customer balance from old invoices
- ❌ Checking if a credit note exists
- ❌ Loading new items added by your manager today
- ❌ Real-time stock check ("how many of this do we have?")

### When connection returns

Click **Sync Queue** at the top. The system pushes all your pending
sales to the server. The counter goes back to 0.

> ⚠️ **Important:** At end of shift, make sure Sync Queue = 0 before
> you leave. Otherwise your sales aren't reflected in the day's
> totals. If it won't go to 0, get your manager.

---

## End of your shift

🚧 **Some parts in development** — this section reflects the intended
flow; specific buttons may move slightly.

### Step 1: Make sure all sales are synced

Look at the **Sync Queue** count. It should say "Queue empty" or
show 0 pending sales. If not:

- Click **Show** to see what's queued
- Click **Sync Queue** at the top to push them
- If sync fails repeatedly, get your manager — don't leave with
  unsynced sales

### Step 2: Close any held orders

The **Held Invoices** panel should be empty (or only have orders
that genuinely span shifts, like layaways). Resume and complete any
that are yours, or get a manager to dispose of them.

### Step 3: Click "Shifts" → close your shift

> 🔬 **Beta** — the shift management UI is being polished.

The **Shifts** button opens a panel where you:

1. Confirm your start cash (what you started the day with)
2. The system shows expected cash (based on cash sales − refunds)
3. You count the actual cash in the drawer
4. Type the actual amount
5. The system shows the difference (over / short)
6. Click **Close Shift**

The system records the shift with all this info. Your manager will
review it.

### Step 4: Cash drop / safe drop

If your branch uses cash drops:

1. Click **Cash Moves**
2. Pick **Safe Drop**
3. Type the amount being moved to the safe
4. The amount leaves your drawer for accounting purposes
5. Hand the cash to the manager / put in safe

### Step 5: Log out

Click your name (top-right) → **Logout**. Done.

---

## Common problems and quick fixes

### "Something went wrong loading the register"

You see this card after the page loads. The cashier UI hasn't started.

**What to do:**
1. Hard-refresh the page (Ctrl+Shift+R on Windows, Cmd+Shift+R on Mac)
2. If that doesn't fix it, get your manager
3. Don't try to take sales until it loads — they'd just fail

### Barcode scanner isn't working

**What to check:**
1. Is the Scan field focused? (Click into it.)
2. Is the scanner turned on? (Some have a power button.)
3. Does scanning anywhere else (like Notepad) produce text?
   - If yes: scanner is fine, the field is the problem (refresh page)
   - If no: scanner hardware issue, get your manager

### Receipt didn't print

**What to check:**
1. Is the printer turned on?
2. Is there paper?
3. Click the **Sync Queue** count — was the sale saved offline?
   (If yes, it'll print when sync completes)

### "Manager approval required" when I try to give a discount

This is normal. Walk to your manager, they'll come over and:
1. Look at your screen
2. Type their username + PIN in the dialog that appears
3. The discount applies, you continue

### Cart total doesn't match what I expect

The system applies pricing rules, taxes, and offers automatically.
Some common reasons the total isn't what you expected:

- **Inclusive VAT:** Many KSA prices include VAT. The line shows the
  inclusive price, but the receipt breaks it out.
- **Discount applied:** A pricing rule may have given the customer a
  discount. Check the line for a strikethrough price or a discount
  pill.
- **Volume offer:** Buying 3 of the same item triggered a "buy 3 get
  X off" rule.

If you genuinely think the total is wrong, hold the order, get a
manager.

### I scanned the wrong customer for a return

Don't process the return. Click **×** on each line to clear, then
start over with **Return** and pick the right invoice.

### The page is frozen

1. Wait 5 seconds — sometimes it's a slow network call
2. Hard-refresh (Ctrl+Shift+R)
3. If that doesn't work, close the browser tab and reopen
4. If still frozen, restart the browser

> ⚠️ **Don't restart the PC during a sale.** If you have items in the
> cart and the cart isn't synced, restarting could lose them. Hold
> the order first, then restart.

---

## Glossary

**Branch** — A physical store location (e.g., "Riyadh Mall"). One
business can have many branches.

**Outlet** — A specific business unit within a branch (e.g., "Coffee
Shop" at Riyadh Mall). Larger stores can have multiple outlets per
branch.

**Terminal** — A specific cashier station within an outlet (e.g.,
"Terminal A07"). Each PC running the cashier is bound to exactly one
terminal.

**POS Profile** — Your cashier's permission set: which payment methods
you can accept, which warehouse stock comes from, which printer to use.
Set by your manager.

**Held Invoice** — An order that was paused mid-sale and saved for
later. Lives in the Held Invoices panel until resumed or canceled.

**Sync Queue** — Pending sales that happened offline and haven't been
sent to the server yet. Should be empty at end of shift.

**Credit Note** — A record of credit a customer has at your store,
issued when they return items without taking cash back. Redeemable on
future purchases.

**ZATCA** — The Saudi tax authority. Every sale must be reported to
them via the e-invoicing system. The cashier handles this
automatically — you don't need to do anything special.

**Manager PIN** — A 4-6 digit number a manager types to authorize
privileged actions (return approvals, discount overrides, station
setup). You as a cashier never type a manager PIN.

**Hold** — Pause an order so you can serve another customer first.
Different from canceling: held orders can be resumed.

---

## Quick reference card

> 📋 **Print this and keep it at your station.**

| What I want to do | What I click |
|---|---|
| Add an item | Scan it, or type code + Enter |
| Increase quantity | **+** on the cart line |
| Decrease quantity | **−** on the cart line |
| Remove item | **×** on the cart line |
| Add a coupon | Type code in **Offer Code** field |
| Take payment | Pick mode → Amount → **Add Payment** |
| Complete sale | **Pay & Submit** |
| Pause order | **Hold** |
| Resume order | **Open** in Held Invoices |
| Process return | **Return** → find invoice → **Pay & Submit** |
| Use credit note | **Redeem Credit Note** |
| Sync offline sales | **Sync Queue** at top |
| End of shift | **Shifts** → Close Shift |

---

*Manual version 15.5.13 — May 2026. For the latest version, check the
docs/ folder in your AlphaX POS installation.*
