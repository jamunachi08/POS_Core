#!/usr/bin/env python3
"""v16.2.0 — delivery platform protocol checks (no Frappe needed)."""

import hashlib
import hmac
import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent / "alphax_pos_suite" / "alphax_pos_suite"
spec = importlib.util.spec_from_file_location("protocol", BASE / "integrations" / "aggregators" / "protocol.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
FAILS = []


def check(c, m):
	print(("  OK   " if c else "  FAIL ") + m)
	if not c:
		FAILS.append(m)


print("== Delivery Hero plugin auth (JWT HS512, service=middleware) ==")
sec = "plugin-secret-xyz"
good = P.sign_jwt_hs512({"service": "middleware", "exp": time.time() + 60}, sec)
check(P.verify_dh_jwt("Bearer " + good, sec)[0], "valid token accepted")
check(not P.verify_dh_jwt("Bearer " + good, "other")[0], "wrong secret rejected")
check(not P.verify_dh_jwt("Bearer " + P.sign_jwt_hs512({"service": "someone"}, sec), sec)[0], "wrong service claim rejected")
check(not P.verify_dh_jwt("Bearer " + P.sign_jwt_hs512({"service": "middleware", "exp": time.time() - 3600}, sec), sec)[0], "expired token rejected")
check(not P.verify_dh_jwt(None, sec)[0], "missing header rejected")
check(not P.verify_dh_jwt("Bearer " + good, None)[0], "unconfigured secret fails closed")
hs256 = good.split(".")
hs256[0] = P._b64url(json.dumps({"alg": "none"}).encode())
check(not P.verify_dh_jwt("Bearer " + ".".join(hs256), sec)[0], "alg=none rejected")

print("== Delivery Hero order normalisation ==")
order = {
	"token": "tok-123", "code": "HS-998877", "shortCode": "579", "test": False,
	"expiryDate": "2026-10-25T18:10:00Z", "expeditionType": "delivery",
	"platformRestaurant": {"id": "224235"},
	"customer": {"firstName": "Noura", "lastName": "A."},
	"comments": {"customerComment": "No onions"},
	"delivery": {"riderPickupTime": "2026-10-25T18:25:00Z"},
	"price": {"grandTotal": "64.40", "vatTotal": "8.40", "deliveryFees": [{"name": "delivery", "value": 7}]},
	"products": [
		{"remoteCode": "SHAW-L", "name": "Shawarma Large", "quantity": 2, "unitPrice": "19.00", "comment": "",
		 "selectedToppings": [{"remoteCode": "GARLIC", "name": "Extra garlic", "quantity": 1, "price": "2.00", "children": []},
		                      {"remoteCode": "NOPICK", "name": "No pickles", "quantity": 1, "price": "0"}]},
		{"remoteCode": "PEPSI", "name": "Pepsi", "quantity": 1, "unitPrice": "6.00"},
	],
	"callbackUrls": {"orderAcceptedUrl": "https://mw/x/accept", "orderRejectedUrl": "https://mw/x/reject",
	                 "orderPickedUpUrl": "https://mw/x/picked", "orderPreparedUrl": "https://mw/x/prepared"},
}
n = P.normalize_dh(order, "vendor-001")
check(n["order_token"] == "tok-123" and n["short_code"] == "579", "token and short code")
check(n["remote_store_id"] == "vendor-001" and n["platform_store_ref"] == "224235", "both store ids captured (remote id + platform restaurant id)")
check(len(n["lines"]) == 2 and n["lines"][0]["qty"] == 2 and n["lines"][0]["rate"] == 19.0, "product lines")
check([t["external_code"] for t in n["lines"][0]["toppings"]] == ["GARLIC", "NOPICK"], "toppings kept under their product")
check(n["gross_total"] == 64.4 and n["delivery_fee"] == 7 and n["vat_total"] == 8.4, "money fields")
check(n["expiry"] == datetime(2026, 10, 25, 18, 10, tzinfo=timezone.utc), "expiry parsed as UTC")
check(n["callbacks"]["orderAcceptedUrl"].endswith("/accept"), "callback URLs kept for answering")
check(P.normalize_dh({**order, "expeditionType": "pickup"}, "v")["expedition"] == "Pickup", "pickup expedition")

print("== acceptance time ==")
now = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)
check(P.dh_acceptance_time(now, 1, None) == "2026-10-25T18:03:00Z", "never under the 3-minute floor")
check(P.dh_acceptance_time(now, 15, None) == "2026-10-25T18:15:00Z", "prep minutes used when no rider time")
check(P.dh_acceptance_time(now, 15, now + timedelta(minutes=25)) == "2026-10-25T18:25:00Z", "rider pickup time wins")

print("== generic webhooks (Jahez / Keeta templates) ==")
j = P.template_for("Jahez")
payload = {"event": "order_created", "order": {"id": 5521, "order_number": "J-88", "branch_id": "BR-7", "total": 41.5,
           "items": [{"product_id": "P1", "name": "Kabsa", "quantity": 1, "price": 35, "modifiers": [{"id": "M1", "name": "Extra rice", "price": 6.5}]}]}}
gn = P.normalize_generic(payload, j)
check(P.generic_event(payload, j) == "new", "Jahez new-order event recognised")
check(gn["external_order_id"] == "5521" and gn["short_code"] == "J-88" and gn["remote_store_id"] == "BR-7", "Jahez ids mapped")
check(gn["lines"][0]["toppings"][0]["external_code"] == "M1", "Jahez modifiers mapped")
check(P.generic_event({"event": "order_cancelled"}, j) == "cancelled", "Jahez cancel event recognised")
k = P.template_for("Keeta")
raw = json.dumps({"event_type": "ORDER_CREATED", "data": {"order_id": "K1"}}).encode()
sig = hmac.new(b"kk", raw, hashlib.sha256).hexdigest()
check(P.verify_shared({"X-Keeta-Signature": sig}, raw, "kk", k["auth"])[0], "Keeta HMAC signature accepted")
check(not P.verify_shared({"X-Keeta-Signature": "00" + sig[2:]}, raw, "kk", k["auth"])[0], "tampered body rejected")
check(not P.verify_shared({}, raw, None, k["auth"])[0], "missing secret fails closed")
check(P.verify_shared({"X-Jahez-Secret": "abc"}, b"", "abc", j["auth"])[0], "Jahez shared secret accepted")
check(P.fill({"path": "/orders/{order_id}/accept"}, {"order_id": 9}) == {"path": "/orders/9/accept"}, "action path placeholders")

print()
print("RESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
sys.exit(1 if FAILS else 0)
