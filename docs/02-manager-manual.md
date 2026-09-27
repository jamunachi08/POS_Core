# AlphaX POS — Manager Manual

**For:** Branch managers, shift supervisors, and anyone with the
AlphaX POS Manager role
**Version:** 15.5.13
**Last updated:** May 2026

---

## What's in this manual

1. [Your role and what you can authorize](#your-role-and-what-you-can-authorize)
2. [Your manager PIN: setup and care](#your-manager-pin-setup-and-care)
3. [Setting up a new cashier PC (station binding)](#setting-up-a-new-cashier-pc-station-binding)
4. [Daily opening procedures](#daily-opening-procedures)
5. [During the day: approvals you'll be asked for](#during-the-day-approvals-youll-be-asked-for)
6. [Shift management: opens, closes, cash counts](#shift-management-opens-closes-cash-counts)
7. [Reading the day's sales](#reading-the-days-sales)
8. [Handling returns and refunds](#handling-returns-and-refunds)
9. [Held order cleanup](#held-order-cleanup)
10. [Day-end procedures](#day-end-procedures)
11. [Audit log: who did what, when](#audit-log-who-did-what-when)
12. [Troubleshooting from a manager's view](#troubleshooting-from-a-managers-view)
13. [Glossary](#glossary)

---

## Your role and what you can authorize

✅ **Working**

As a **manager**, you have authority that cashiers don't. Specifically:

| Action | Who can do it |
|---|---|
| Ring up a sale | Cashier or Manager |
| Process a routine return | Cashier or Manager |
| Override the price of an item | Manager (with PIN) |
| Approve a return older than X days | Manager (with PIN) |
| Approve a discount above the threshold | Manager (with PIN) |
| Bind a PC to a terminal | Manager (with PIN) |
| Reset a PC's terminal binding | Manager (with PIN) |
| Cancel a held order older than today | Manager (or Cashier with permission) |
| Edit credit note amount | Manager only |
| Open/close a register shift with cash variance | Manager (must approve variance) |

When a cashier triggers an action that needs your authorization, the
register shows a manager-PIN dialog. You walk over, type your username
and PIN, and the action proceeds. The system records who authorized
it, when, and on which terminal.

### Status of features in this manual

> ✅ **Working** = ready to use today
> 🔬 **Beta** = available but might change soon
> 🚧 **In Development** = coming in a future update

---

## Your manager PIN: setup and care

✅ **Working**

### Why PINs instead of passwords

Your full Frappe password is long and hard to type at a busy register.
PINs are a 4-to-6 digit shortcut for the small set of register-floor
authorizations you do many times a day.

A PIN is **not** a replacement for your password. You still log in
with your username and password. The PIN is only for these
register-side approvals.

### Getting your PIN set

You don't set your own PIN. The **System Administrator** sets it for
you — usually during your onboarding. They:

1. Go to your User profile
2. Open "AlphaX POS Manager PIN" → New
3. Enter a 4-6 digit PIN
4. Save

You'll be told the PIN privately. **Memorize it.** Don't write it down
where customers or other staff can see.

### Changing your PIN

If you suspect your PIN was seen by someone, ask the System
Administrator to change it. They can also rotate PINs on a schedule
(some shops do this every 90 days).

### When you forget your PIN

This is normal. Tell the System Administrator. They reset it. You get
a new one. Don't panic and don't try to guess — see the next section.

### Lockout policy

If 5 wrong PIN attempts happen in a row on your account, you're locked
out for 5 minutes. After that, the next 5 wrong attempts lock you out
for 30 minutes. Then 4 hours. Then 24 hours plus an alert email to
the System Administrator. After that, only the admin can unlock you.

This is to protect your authority — if someone tries to guess your
PIN, the system stops them long before they succeed.

**If you trigger a lockout by accident:**
1. Wait the listed time
2. Try again with the correct PIN
3. If you genuinely forgot, contact the System Administrator
   to reset and unlock

> ⚠️ **Important:** If you find yourself locked out and you didn't
> mistype your PIN, that means **someone else tried to use it**.
> Tell the System Administrator immediately.

### PIN security rules

- ✅ Use a PIN that's not your birthday or a common pattern
  (1234, 0000, 1111)
- ✅ Memorize it; don't write it on a sticky note
- ✅ Type it where customers can't see (cover the keypad with your hand)
- ❌ Never give your PIN to a cashier "just this once"
- ❌ Never share it via WhatsApp / SMS / email
- ❌ Never type your PIN on a device that's not yours

---

## Setting up a new cashier PC (station binding)

✅ **Working**

A new PC arrives at the branch. Or an old one was reset. Either way,
when a cashier logs in, they see:

> 🔒 **Station Not Configured**
> This computer hasn't been bound to a POS terminal yet.
> A manager must complete a one-time setup before this station can take orders.

Here's what you do.

### Step 1: Make sure the terminal exists in the system

Each cashier station has to correspond to a **Terminal** record in
AlphaX POS. Before binding, confirm with your System Administrator
that:

- Your branch has its terminals defined (e.g., "Terminal A07")
- Each terminal is linked to the correct **Outlet**
- Each outlet is linked to the correct **Branch**

If the terminals haven't been created yet, ask the System Administrator
to create them — give them the list of physical PC locations.

### Step 2: Open the cashier on the new PC

The cashier is at the new PC, sees the "Station Not Configured" card.

### Step 3: Click "Manager Setup"

A dialog opens with two fields: **Manager Username** and **Manager PIN**.

### Step 4: Type your credentials and verify

Type:
- Your username (work email)
- Your 4-6 digit PIN

Click **Verify**.

If correct: a green confirmation appears: **✓ Authorized as [your name]**.

If wrong: a red error appears. Try again. After 5 wrong attempts you're
locked out — see the lockout policy above.

### Step 5: Bind the PC to a terminal

After successful verification, two buttons appear:

- **Bind This PC to a Terminal** — opens a dropdown of all terminals
- **Done** — close without binding

Click **Bind This PC to a Terminal**.

A new dialog opens with a dropdown showing all terminals in the
breadcrumb format:

```
Riyadh Mall  ›  Coffee Shop  ›  Terminal A07
Riyadh Mall  ›  Coffee Shop  ›  Terminal A08
Jeddah Branch  ›  Pharmacy  ›  Terminal P01
...
```

Pick the one that matches the **physical location of the PC you're
sitting at**. Double-check by reading the label on the PC if there is
one.

Click **Bind This PC**.

### Step 6: Verify the binding

The cashier UI loads automatically. The station banner at the top
shows:

```
STATION   Riyadh Mall  ›  Coffee Shop  ›  Terminal A07
```

If this is correct, you're done. The PC is bound. Every future shift
on this PC, the cashier loads straight to this terminal.

### Step 7: Hand off to the cashier

The cashier can start their shift. Your work here is done.

---

## Changing a PC's terminal

A PC has been bound to one terminal but you need to change it (e.g.,
the PC is being moved to another counter, or you set the wrong
terminal originally).

### Steps

1. At the PC in question, click the **⚙ gear icon** in the top-right
   of the cashier toolbar
2. Type your username + PIN in the Manager Setup dialog
3. After verification, click **Change Terminal**
4. Pick the new terminal from the dropdown
5. Click **Bind This PC**

The PC is now bound to the new terminal. Anything from the old
terminal stays in the system — you haven't deleted any sales, just
changed which terminal future sales go to.

---

## Resetting a PC

Use this when:
- The PC is being decommissioned
- You're handing it to another branch
- Something is genuinely wrong and you want a fresh start

### Steps

1. Click **⚙** → type credentials → **Verify**
2. Click **Reset Station (Clear Binding)**
3. Confirm the prompt

The PC is now unconfigured. The cashier sees the "Station Not
Configured" card on next refresh. The next manager (or you) needs to
re-bind it before sales can happen.

---

## Daily opening procedures

🔬 **Some parts in development** — adapt these to your shop's habits;
the platform is flexible.

### 1. Walk the floor

Before opening:
- Visit each cashier station
- Confirm the station banner shows the right terminal/branch
- Check that printers, scanners, cash drawers all look connected
- Open one test scan if you want to be sure

### 2. Open the day's shifts

Each cashier opens their own shift via **Shifts → Open Shift**, but
you should know:
- Their starting cash float (you give it to them)
- The shift opens "open"
- They can take sales

### 3. Check the Sync Queue

Look at any cashier's Sync Queue counter. It should be 0 at start of
day. If it shows pending items from yesterday, that's a sign yesterday
didn't close cleanly. Investigate before letting the day proceed.

### 4. Check the workspace for alerts

Visit `/app/alphax-pos-hub`. You'll see:
- Today's Sales (will start at 0, increases as sales happen)
- ZATCA Status (any pending or failed e-invoicing submissions)
- Open Cashier shortcut

If ZATCA Status shows a red number, click into it. There may be
yesterday's invoices that didn't submit. Get the System Administrator
involved if you're not sure how to clear it.

---

## During the day: approvals you'll be asked for

✅ **Working**

### Discount approval

A cashier tries to apply a discount above your shop's threshold. The
register shows a dialog asking for manager PIN.

**You should:**
1. Look at the discount on screen — is it justified?
   (Loyalty member, manager-approved promo, customer complaint
   resolution, etc.)
2. If yes, type your username + PIN
3. If no, decline — the cashier closes the dialog and the regular
   price applies

### Price override approval

A cashier needs to change an item's price to something other than the
default. Same flow.

### Return approval (older than X days)

Returns within X days don't need approval (X is set in your shop's
settings). Older returns ask for your PIN.

### Cash drawer open without sale

A cashier needs to open the cash drawer without ringing up a sale
(e.g., to make change for a customer who only has a 500 SAR note).

> 🔬 **Beta** — this varies by shop and printer. Some shops let
> cashiers do this; others require manager approval.

### Voiding a submitted invoice

If a sale was completed by mistake, voiding it is a manager-only
action. Generally:
1. Find the invoice in **Sales Invoices** list
2. Click **Cancel** (not Delete — never delete)
3. Reason: choose from the standard set, or type a free-form reason
4. The system records who voided, when, why

> ⚠️ **Voiding affects:**
> - Inventory (items return to stock)
> - Accounts (revenue reduced)
> - ZATCA (a credit note will be generated automatically)
>
> Don't void casually. Use Returns instead for the customer-walked-back
> case.

---

## Shift management: opens, closes, cash counts

✅ **Working** for basic flow
🔬 **Beta** for variance approvals

### Opening a shift

Each cashier should open their own shift at start of day:
1. Cashier clicks **Shifts** in the cashier toolbar
2. Picks the cash they're starting with (their float)
3. Confirms

The shift is now "Open" in the system. All their sales today flow
into this shift.

### Mid-shift cash drops

When a cashier's drawer gets full of cash, they (or you) can do a
**Cash Move** to the safe:

1. Click **Cash Moves** at the top
2. Pick **Safe Drop**
3. Enter the amount
4. Confirm

The system records the move. The drawer's expected balance reduces.
The amount is credited to the safe account.

### Closing a shift

At end of shift, the cashier:
1. Clicks **Shifts** → **Close Shift**
2. Counts the actual cash in the drawer
3. Types the count
4. Sees "Variance: 0.00" (perfect) or "Variance: ±X.XX" (mismatch)

If variance is 0 or within tolerance: shift closes automatically.

If variance is over tolerance: a manager-approval dialog appears.
You walk over, look at the count, type your PIN, choose:
- **Approve and Close** (variance is recorded but the shift closes)
- **Recount** (cashier counts again)

> 💡 **Variances over tolerance trigger an audit log entry** even when
> approved. Pattern of variances on one cashier should be investigated.

---

## Reading the day's sales

✅ **Working**

### Live sales counter

The workspace's "Today's Sales" shortcut takes you to a live report:
- Total sales count
- Total revenue
- Breakdown by mode of payment
- Per-cashier breakdown

### Drilling into one cashier's sales

Click a cashier's row. You see all their invoices for the day:
- Invoice number, time, customer, total, payment method
- Each invoice's items, taxes, etc.

### Looking at one specific invoice

Click any invoice. The full receipt details appear. You can:
- Print a duplicate receipt
- Email it to the customer
- See the ZATCA status for that invoice (Submitted / Pending / Failed)

### End-of-day summary

> 🚧 **In Development** — a one-click "End of Day" button is coming.
> For now, you read the Today's Sales report at end of day, then close
> shifts manually.

---

## Handling returns and refunds

✅ **Working** for routine cases
🔬 **Beta** for cross-branch returns

### Routine returns (same branch, same day)

The cashier handles these without your involvement. They:
1. Click **Return** → find the invoice → adjust quantities → submit
2. Choose Cash Refund or Credit Note
3. The customer leaves with cash or a credit note

### Returns needing your approval

When the system asks for manager PIN on a return:

1. Look at the original sale (the cashier should show you on screen)
2. Look at the return reason (cashier should ask)
3. Decide:
   - Within shop policy: type your PIN, return proceeds
   - Outside policy: decline, explain to customer

**Common reasons returns ask for approval:**
- Older than X days from original sale
- Refund amount exceeds threshold
- Customer doesn't have the receipt
- Item is on a no-return list (e.g., underwear, perishables)

### Cross-branch returns

> 🔬 **Beta** — supported but flow is being polished.

If a customer bought at Riyadh Mall and is returning at Jeddah Branch:
1. The cashier searches for the original invoice (should appear if
   both branches use the same Frappe instance)
2. The return goes through, but the credit note / cash refund is
   recorded against the Jeddah Branch's books
3. End-of-month reconciliation between branches handles the inter-
   branch transfer

If the system can't find the invoice across branches, the cashier
can't process the return. Direct the customer back to the branch
where they bought it, or take their info and arrange a manual
refund through accounts.

---

## Held order cleanup

✅ **Working**

Held orders are sales that were paused. Sometimes they linger
forever (customer never came back). Cleaning them up keeps the
held-orders list manageable for cashiers.

### Reviewing held orders

Go to `/app/alphax-pos-order` (or click "Held Orders" from the
workspace). You see a list with:
- Order number
- Customer
- Time held
- Cashier who held it
- Items in the order

### When to cancel a held order

- Customer didn't come back within a few hours
- Items are being held for an inventory recount and need to be released
- Cashier accidentally held an order they meant to submit

### How to cancel

1. Click into the held order
2. Click **Cancel** (top-right)
3. Reason: pick from list or type your own
4. Confirm

The held order is voided. Inventory and accounting are unaffected
(it was never a real sale).

---

## Day-end procedures

🔬 **Beta** — process is being formalized into a single button.

### Before closing the branch

1. **All cashiers close their shifts** (cash counted, variances
   approved by you, shifts closed)
2. **Sync Queue is 0** on all cashier PCs
3. **Held Orders list is empty** (or only contains genuinely-pending
   orders like layaways)
4. **ZATCA Status** shows no failures (workspace shortcut)

### Run the day-close report

> 🚧 **In Development** — a single "Day Close" report is coming.

For now, run:
- Today's Sales (workspace shortcut) → print or save PDF
- Cash Moves report → all cash drops/lifts for the day
- Sales Register → if accountant wants details

### Reconcile cash to bank

Take cash drops to bank/safe per your shop's policy. Update the
Cash Move records or use the standard ERPNext deposit flow if
configured.

### Logout and lock up

Each cashier logs out. You log out last. The PCs go to sleep / shut
down per your shop's policy.

---

## Audit log: who did what, when

✅ **Working**

### What gets logged

Every privileged action — anything that needed a manager PIN — is
recorded in the **AlphaX POS Manager Authorization Log**. This includes:

- Manager PIN attempts (success and failure)
- Terminal bindings, changes, resets
- (When implemented:) discount overrides, return approvals,
  void approvals

### Why this matters

- Patterns of failures may indicate someone is trying to guess your PIN
- Patterns of approvals tell you which cashiers ask for them most
  (training opportunity)
- Audits, disputes with customers, or staff disagreements can be
  reviewed factually

### Reading the log

Go to `/app/alphax-pos-manager-authorization-log`. Filter by:
- Date range
- Specific manager
- Specific terminal
- Result (Success / Wrong PIN / Locked Out / etc.)

Click any entry for details: who, when, what, IP address, browser used.

### What you can't do

The log is **append-only**. You cannot delete entries, even as a System
Manager. This is a security feature — a compromised admin account
cannot scrub their own tracks.

If you genuinely need to remove an entry (e.g., it contains an entry
mistakenly tied to the wrong user), contact the System Administrator
who has the database tools to handle it.

---

## Troubleshooting from a manager's view

### A cashier is locked out of their PIN

You need their full username (work email). Tell the System
Administrator: "Khalid (khalid@example.com) is locked out, please reset."
The Admin runs a one-line command, the lockout clears, Khalid types
his PIN again.

### A whole branch's PCs went offline at the same time

This is usually internet trouble, not POS trouble. Each PC's
Sync Queue accumulates pending sales. When internet returns:
1. Each cashier clicks **Sync Queue** at the top
2. Pending sales push to the server
3. Counter goes back to 0

If sync fails after multiple tries, that's a deeper issue. Get the
System Administrator on the line.

### Receipt printing fails on every PC

Printer issue (network printer, paper jam, ink) or driver issue.
Check the physical printer first. If multiple PCs print to the same
network printer and that one is offline, all PCs lose printing.

### A cashier can't sign in

Ask:
- Are they sure of the username (often it's their email, full domain)?
- Did they get their password reset email?
- Is the system reachable from any PC? (Can YOU log in?)

If you can log in and they can't: their account issue → Admin help.
If you also can't log in: bigger system issue → Admin help urgently.

### "ZATCA Status" workspace shortcut shows red errors

Click into it. You'll see invoices that didn't submit to ZATCA. Each
has a reason in the error column. Common causes:
- ZATCA portal had downtime → just resubmit
- Customer's VAT number was malformed → fix on the invoice, resubmit
- Device certificate expired → System Admin needs to rotate it

If you can't tell what's wrong, get System Admin help — ZATCA
non-compliance has financial consequences.

### A customer is upset about a return rejection

You're authorized to override your own shop's return policy in
exceptional cases. You can:
1. Override the manager-PIN check (you ARE the manager)
2. Process the return with a manager-required-approved discount
3. Document the reason in the invoice's notes field

But: every override is in the audit log. If your shop's policy says
"no returns after 30 days" and you approve one, your owner sees that
in the audit report. Have a reason ready.

---

## Glossary

**AlphaX POS Manager** — A Frappe role. Anyone with this role can
perform manager actions and have a manager PIN.

**Audit Log** — The append-only record of all privileged actions
taken in the POS system. See "Audit log: who did what, when" above.

**Branch** — A physical store location. One business owns one or
more branches.

**Cash Move** — A non-sale movement of cash (drop to safe, lift to
fund float, between drawers, etc.). Tracked separately from sales.

**Lockout** — A state where a manager's PIN is temporarily disabled
because of too many wrong attempts. Lockout durations escalate:
5 min → 30 min → 4 hours → 24 hours → admin reset only.

**Outlet** — A business unit within a branch. A branch can have
multiple outlets (e.g., "Coffee Shop" and "Pharmacy" at the same
mall location).

**POS Profile** — A Frappe doctype that defines a cashier's
permissions, default warehouse, payment methods, etc.

**Shift** — A cashier's time on the clock with a specific cash float.
Opens at start of work, closes at end of work, with a cash count
both times. Variances are reconciled at close.

**Sync Queue** — Pending offline sales waiting to be sent to the
server. Should be 0 at end of every shift.

**Terminal** — A specific cashier station within an outlet. Each PC
running the cashier is bound to exactly one terminal.

**Variance** — Difference between expected cash (calculated) and
actual cash (counted) at shift close. Small variances within
tolerance are auto-accepted; larger ones need manager approval.

**ZATCA** — The Saudi tax authority. The POS reports each sale to
ZATCA automatically; failures are visible in the workspace.

---

## Quick reference card for managers

> 📋 **Print and keep at your desk.**

| Situation | What you do |
|---|---|
| New cashier PC needs setup | ⚙ icon → Verify PIN → Bind terminal |
| Cashier asks for discount approval | Walk over, type PIN at their station |
| Return is too old / too large | Walk over, type PIN, approve with reason |
| Shift close shows variance | Recount with cashier, then approve+close |
| Sync Queue won't clear | Get System Admin (network or auth issue) |
| Cashier can't login | Check user account; Admin if needed |
| ZATCA showed errors yesterday | Click ZATCA Status → resubmit failures |
| Audit a specific employee | Filter Authorization Log by their user |

---

*Manual version 15.5.13 — May 2026. For the latest version, check the
docs/ folder in your AlphaX POS installation.*
