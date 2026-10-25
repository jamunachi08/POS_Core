# AlphaX POS Suite v15.7.14 — ZATCA QR on reprints

get_invoice_receipt now returns the invoice's ZATCA TLV QR (first
non-empty of ksa_einv_qr / zatca_qr_code / qr_code / alphax_zatca_qr,
covering ERPNext KSA regional and the alphax_zatca app). The bridge
renders it as a QR block on thermal reprints; the browser fallback
notes its presence. Verification copies of B2C simplified invoices are
now ZATCA-complete. Payload = tree = stamp verified.

Next (with KOT routing): carry the QR on the ORIGINAL at-sale receipt
for online sales (fetch after submit) and reprint-on-sync for offline
ones.
