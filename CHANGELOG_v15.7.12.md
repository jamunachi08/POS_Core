# AlphaX POS Suite v15.7.12 — ROOT CAUSE: the '__Walk-in' customer

## Diagnosed from ERPNext v15 source

`set_pos_fields` (runs on every is_pos invoice insert) does:

    customer_price_list, customer_group = frappe.get_value(
        "Customer", self.customer, ["default_price_list", "customer_group"])

frappe.get_value on a NONEXISTENT customer returns None → "cannot
unpack non-iterable NoneType object". The register's queue rows showed
the customer verbatim: "__Walk-in" — the SPA's fabricated fallback
string, a customer that exists on no site.

Why the fallback fired: settings.default_customer in the boot payload
reads AlphaX POS **Settings** (empty on the fresh site) — the
**Terminal's** properly configured default customer was never
consulted. Every sale therefore posted as '__Walk-in', the online
insert crashed, the client (correctly) treated the failure as
"couldn't post" and queued the sale — which is why online sales kept
landing in the offline queue.

## Fixes — all three layers

1. **Boot** resolves an *effective* default customer:
   Terminal.default_customer → Settings.default_customer, validated to
   EXIST; otherwise null. The SPA is never handed a customer the
   server would reject.
2. **SPA**: the '__Walk-in' fabrication is gone. With no selected and
   no default customer, the sale is blocked at Pay with a bilingual
   message naming the exact setting to fix — instead of poisoning the
   queue with unpostable payloads.
3. **Queue healer** (server): payloads already frozen in registers'
   IndexedDB still carry '__Walk-in'. push_queued_invoice now
   substitutes the terminal's (then settings') validated default
   customer for any nonexistent one, records the substitution in the
   invoice remarks for the audit trail, and only then posts. Your
   stuck sales flush on the next retry with no manual surgery.

## After deploying

Deploy → reload the register. All queued sales should post (check
their remarks for the substitution note), and from then on new sales
post directly to Sales Invoice — and onward to ZATCA on submit — with
the queue reserved for genuine offline periods, as designed.
