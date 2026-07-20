# AlphaX POS Suite v15.9.9 — Child-table registration defects (day close 1054)

Error Log evidence: "Option AlphaX POS Day Close Payment for field
payments is not a child table". Audit of every Table field in the app
found FIVE doctypes used as child tables but registered standalone
(istable=0) — so their DB tables were created WITHOUT parent/
parenttype/parentfield columns, and any load/query WHERE parent=…
raised 1054:

- AlphaX POS Day Close Payment    (Day Close.payments)      ← the 1054
- AlphaX POS Denomination Line    (Day Close.denominations) ← the 1054
- AlphaX POS Profile Payment Method (POS Profile.payment_methods)
- AlphaX POS Scale Barcode Rule     (POS Profile.scale_rules)
- AlphaX POS Email Recipient        (Report Email Setup.recipients)

All five flipped to istable=1 (child permissions cleared). These are
long-standing repo defects — the last three were unexploded bombs for
POS Profile saves and report email setup.

## Applying on the site
Deploy, then run the repair endpoint once more as Administrator:
/api/method/alphax_pos_suite.alphax_pos_suite.setup_repair.repair_doctypes_now
The full-schema reload flips istable on the site and the schema sync
adds the missing parent columns to the existing tables. Then run day
close.
