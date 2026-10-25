"""Pure rules for guest ordering — testable without Frappe."""

from __future__ import annotations

import re
from datetime import time

_PHONE = re.compile(r"^\+?\d{8,15}$")


def within_hours(opening: time | None, closing: time | None, now: time) -> bool:
	"""Inside trading hours; handles a closing time past midnight (18:00–02:00)."""
	if not opening or not closing:
		return True
	if opening <= closing:
		return opening <= now <= closing
	return now >= opening or now <= closing


def normalise_phone(raw: str | None) -> str:
	p = re.sub(r"[\s\-().]", "", raw or "")
	if p.startswith("00"):
		p = "+" + p[2:]
	return p


def valid_phone(raw: str | None) -> bool:
	return bool(_PHONE.match(normalise_phone(raw)))
