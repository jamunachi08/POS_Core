"""ZATCA QR for simplified tax invoices — built and drawn on this server.

Phase 1 (generation): the QR carries a base64 TLV of five fields — seller
name, VAT registration number, invoice timestamp, invoice total including
VAT, VAT total. Phase 2 (integration) adds the invoice hash, the ECDSA
signature, the public key and, for simplified invoices, the certificate
signature (tags 6–9). Those come from the cryptographic stamp, so when the
ZATCA app has produced a QR for the invoice, that QR is used as-is; this
module only builds the Phase-1 form when nothing else exists.

The image is rendered locally (PyQRCode, shipped with Frappe). Receipts
used to fetch the image from a public QR web service, which sent each
invoice's VAT number and totals to a third party abroad and failed
whenever the till was offline.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime

PHASE2_FIELDS = ("ksa_einv_qr", "zatca_qr_code", "qr_code", "custom_zatca_qr", "zatca_qr")


def _tlv(tag: int, value: str) -> bytes:
	b = (value or "").encode("utf-8")
	if len(b) > 255:
		raise ValueError(f"TLV value for tag {tag} longer than 255 bytes")
	return bytes([tag, len(b)]) + b


def phase1_tlv(seller: str, vat_no: str, timestamp: datetime | str, total: float, vat: float) -> str:
	ts = timestamp if isinstance(timestamp, str) else timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
	raw = _tlv(1, seller) + _tlv(2, vat_no) + _tlv(3, ts) + _tlv(4, f"{total:.2f}") + _tlv(5, f"{vat:.2f}")
	return base64.b64encode(raw).decode()


def decode_tlv(b64: str) -> dict[int, bytes]:
	raw = base64.b64decode(b64)
	out, i = {}, 0
	while i + 2 <= len(raw):
		tag, ln = raw[i], raw[i + 1]
		out[tag] = raw[i + 2 : i + 2 + ln]
		i += 2 + ln
	return out


def is_tlv(text: str) -> bool:
	try:
		d = decode_tlv(text)
	except Exception:
		return False
	return all(t in d for t in (1, 2, 3, 4, 5))


def png_data_uri(text: str, scale: int = 4) -> str:
	import pyqrcode

	q = pyqrcode.create(text, error="M")
	try:
		return "data:image/png;base64," + q.png_as_base64_str(scale=scale, quiet_zone=2)
	except Exception:
		buf = io.BytesIO()
		q.svg(buf, scale=scale, quiet_zone=2, omithw=True, xmldecl=False, svgns=True)
		return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
