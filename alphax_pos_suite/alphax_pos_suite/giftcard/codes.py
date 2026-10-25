"""Gift card numbers and PINs — pure helpers, testable without Frappe."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def luhn_digit(body: str) -> str:
	total = 0
	for i, ch in enumerate(reversed(body)):
		d = int(ch)
		if i % 2 == 0:
			d *= 2
			if d > 9:
				d -= 9
		total += d
	return str((10 - total % 10) % 10)


def luhn_ok(number: str) -> bool:
	return number.isdigit() and len(number) >= 2 and luhn_digit(number[:-1]) == number[-1]


def new_number(prefix: str = "9") -> str:
	"""16 digits: prefix, 14 random digits, Luhn check digit (catches typos and single misreads)."""
	body = prefix + "".join(secrets.choice("0123456789") for _ in range(15 - len(prefix)))
	return body + luhn_digit(body)


def normalise(code: str | None) -> str:
	return "".join(ch for ch in (code or "") if ch.isdigit())


def pretty(number: str) -> str:
	return " ".join(number[i : i + 4] for i in range(0, len(number), 4))


def masked(number: str) -> str:
	return "•••• " + number[-4:]


def keyed_hash(value: str, key: str) -> str:
	"""HMAC-SHA256 with a site secret: a leaked table does not reveal card numbers."""
	return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def new_pin() -> str:
	return f"{secrets.randbelow(10000):04d}"
