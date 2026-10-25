#!/usr/bin/env python3
"""v16.4.0 — ZATCA QR, receipt compliance rules and gift card numbers (no Frappe needed)."""

import ast
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "alphax_pos_suite" / "alphax_pos_suite"
FAILS = []


def load(name, path):
	spec = importlib.util.spec_from_file_location(name, path)
	m = importlib.util.module_from_spec(spec)
	sys.modules[name] = m
	spec.loader.exec_module(m)
	return m


def check(c, msg):
	print(("  OK   " if c else "  FAIL ") + msg)
	if not c:
		FAILS.append(msg)


Z = load("zatca_qr", APP / "receipts" / "zatca_qr.py")
C = load("codes", APP / "giftcard" / "codes.py")

print("== ZATCA Phase-1 QR (TLV) ==")
official = "AQxCb2JzIFJlY29yZHMCDzMxMDEyMjM5MzUwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoEBzEwMDAuMDAFBjE1MC4wMA=="
mine = Z.phase1_tlv("Bobs Records", "310122393500003", "2022-04-25T15:30:00Z", 1000, 150)
check(mine == official, "matches the worked example in ZATCA's QR guidance byte for byte")
ar = Z.phase1_tlv("شركة الاختبار", "300000000000003", "2026-10-26T09:00:00Z", 115, 15)
d = Z.decode_tlv(ar)
check(d[1].decode() == "شركة الاختبار" and d[4] == b"115.00", "Arabic seller name: length counted in UTF-8 bytes")
check(Z.is_tlv(ar) and not Z.is_tlv("not-base64") and not Z.is_tlv(base64.b64encode(b"\x01\x01A").decode()), "TLV detection")
try:
	import pyqrcode  # noqa: F401
	uri = Z.png_data_uri(official)
	check(uri.startswith("data:image/"), "QR image rendered locally as a data URI")
except ImportError:
	print("  SKIP pyqrcode not installed here (ships with Frappe)")

print("== no third-party QR service ==")
pf = json.loads((APP / "print_format/alphax_thermal_80mm/alphax_thermal_80mm.json").read_text())["html"]
check("qrserver" not in pf and "alphax_zatca_qr(doc)" in pf, "thermal receipt no longer sends invoice data to an external QR site")
hooks = (ROOT / "alphax_pos_suite/hooks.py").read_text()
for fn in ("alphax_receipt", "alphax_zatca_qr"):
	check(f"receipts.render.{fn}\"" in hooks and f"def {fn}(" in (APP / "receipts/render.py").read_text(),
	      f"jinja method {fn} registered by function name")

print("== receipt compliance rule ==")
src = (APP / "receipts/render.py").read_text()
tree = ast.parse(src)
consts = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
          and isinstance(n.value, ast.Constant)}
default = next(eval(ast.unparse(n.value), {}, consts) for n in tree.body  # noqa: S307 — our own source
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "DEFAULT_BLOCKS")
required = [m.group(1) for m in re.finditer(r'\("([A-Za-z &]+)", _\(', src)]
shown = {b["block_type"] for b in default}
check(all(r in shown for r in required), f"default layout carries every required block ({', '.join(required)})")
title = next(b for b in default if b["block_type"] == "Title")
check("Simplified Tax Invoice" in title["text_en"] and "فاتورة ضريبية مبسطة" in title["text_ar"], "default title is the ZATCA title in both languages")

print("== gift card numbers ==")
nums = {C.new_number() for _ in range(2000)}
check(len(nums) == 2000 and all(len(n) == 16 and C.luhn_ok(n) for n in nums), "2000 numbers: unique, 16 digits, Luhn-valid")
n = next(iter(nums))
check(not C.luhn_ok(n[:-1] + str((int(n[-1]) + 1) % 10)), "a mistyped check digit is caught")
check(C.normalise("9123 4567-8901 2345") == "9123456789012345" and C.masked(n) == "•••• " + n[-4:], "normalise and mask")
check(C.keyed_hash("card:1", "k1") != C.keyed_hash("card:1", "k2"), "hash is keyed: same number, different site, different hash")
check(len(C.new_pin()) == 4, "4-digit PIN")

print("== gift card wiring ==")
svc = (APP / "giftcard/service.py").read_text()
check("for update" in svc and "_card_for_update" in svc, "balance changes lock the card row")
check("alphax_gift_cards = json.dumps(resolved)" in svc, "invoice keeps card hashes, never tokens or numbers")
for h in ("giftcard.service.invoice_validate", "giftcard.service.invoice_on_submit", "giftcard.service.invoice_on_cancel", "giftcard.service.expire_cards"):
	check(h in hooks, f"hook {h.split('.')[-1]} wired")
pos = (APP.parent / "public/dist/vendor/cashier/sfc/stores/pos.js").read_text()
check("alphax_gift_cards:" in pos and "token: g.token" in pos and "code" not in pos[pos.index("alphax_gift_cards:"):pos.index("alphax_gift_cards:") + 200],
      "till sends authorisation tokens, not card numbers")

print()
print("RESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
sys.exit(1 if FAILS else 0)
