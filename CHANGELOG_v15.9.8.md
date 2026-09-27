# AlphaX POS Suite v15.9.8 — Controller class names (ImportError on save)

Frappe imports each doctype's controller class by the doctype name
with spaces/hyphens stripped: "AlphaX POS Notify Recipient" →
class AlphaXPOSNotifyRecipient. The doctype generator had written
naive capitalization (AlphaxPosNotifyRecipient), so the record could
be created and listed but never INSTANTIATED — saving a Print Station
or an Outlet with a notify recipient row raised
ImportError: <doctype>.

Audited EVERY doctype in the app against Frappe's exact rule: 7
mismatches fixed — the five v15.8/v15.9 doctypes (Print Station, KOT
Routing Rule, Combo + Component, Notify Recipient) and two latent
pre-existing ones (Central Kitchen Request + Item) that would have
failed on first use.

Pure code fix — deploy is enough, no migrate dependency. After deploy:
Print Station saves, Outlet saves with nominated persons, combos
save, and day close runs (its notify step instantiates the recipient
rows that were failing).
