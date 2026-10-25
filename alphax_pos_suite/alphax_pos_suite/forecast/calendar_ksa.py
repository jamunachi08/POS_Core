"""Saudi trading calendar for demand forecasting — no external dependencies.

What moves a Saudi outlet's demand, and how each is derived:

* Weekend (Friday, Saturday) — learned from history through weekday seasonality.
* Ramadan, Eid al-Fitr, Eid al-Adha — Hijri dates from the tabular Islamic
  calendar. Umm al-Qura sightings can differ by a day, so any outlet that
  needs exact dates records them as AlphaX POS Calendar Events, which always
  win over the computed ones.
* Founding Day (22 Feb) and National Day (23 Sep) — fixed Gregorian dates.
* Payday — government salaries land on the 27th; spending lifts from the
  27th through the 2nd of the next month.

Pure functions only, so the forecasting engine stays testable outside Frappe.
"""

from __future__ import annotations

from datetime import date, timedelta

# ------------------------------------------------------------------ Hijri


def _jdn_from_gregorian(d: date) -> int:
	a = (14 - d.month) // 12
	y = d.year + 4800 - a
	m = d.month + 12 * a - 3
	return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _gregorian_from_jdn(jdn: int) -> date:
	a = jdn + 32044
	b = (4 * a + 3) // 146097
	c = a - 146097 * b // 4
	d = (4 * c + 3) // 1461
	e = c - 1461 * d // 4
	m = (5 * e + 2) // 153
	day = e - (153 * m + 2) // 5 + 1
	month = m + 3 - 12 * (m // 10)
	year = 100 * b + d - 4800 + m // 10
	return date(year, month, day)


_ISLAMIC_EPOCH = 1948440  # JDN of 1 Muharram 1 AH (civil epoch)


def _jdn_from_hijri(y: int, m: int, d: int) -> int:
	return d + int(29.5 * (m - 1) + 0.5) + (y - 1) * 354 + (3 + 11 * y) // 30 + _ISLAMIC_EPOCH - 1


def to_hijri(d: date) -> tuple[int, int, int]:
	jdn = _jdn_from_gregorian(d)
	y = (30 * (jdn - _ISLAMIC_EPOCH) + 10646) // 10631
	m = min(12, int((jdn - (29 + _jdn_from_hijri(y, 1, 1))) / 29.5 + 0.99999) + 1)
	m = max(1, m)
	day = jdn - _jdn_from_hijri(y, m, 1) + 1
	return y, m, day


def from_hijri(y: int, m: int, d: int) -> date:
	return _gregorian_from_jdn(_jdn_from_hijri(y, m, d))


# ------------------------------------------------------------------ events

EVENT_TYPES = (
	"Ramadan",
	"Last 10 Nights",
	"Eid al-Fitr",
	"Eid al-Adha",
	"Founding Day",
	"National Day",
	"Payday",
	"School Holiday",
	"Promotion",
	"Local Event",
	"Closure",
)


def builtin_events(d: date) -> set[str]:
	"""Event tags the calendar itself knows for a date."""
	tags: set[str] = set()
	hy, hm, hd = to_hijri(d)
	if hm == 9:
		tags.add("Ramadan")
		if hd >= 20:
			tags.add("Last 10 Nights")
	if (hm == 10 and hd <= 3) or (hm == 9 and hd >= 30):
		tags.add("Eid al-Fitr")
	if hm == 12 and 10 <= hd <= 13:
		tags.add("Eid al-Adha")
	if (d.month, d.day) == (2, 22):
		tags.add("Founding Day")
	if (d.month, d.day) == (9, 23):
		tags.add("National Day")
	if d.day >= 27 or d.day <= 2:
		tags.add("Payday")
	return tags


def daterange(start: date, end: date):
	cur = start
	while cur <= end:
		yield cur
		cur += timedelta(days=1)
