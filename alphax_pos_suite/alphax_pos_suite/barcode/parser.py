"""
Embedded / variable-measure barcode parser.

Supermarket scales and butcher/deli/produce scales print EAN-13 barcodes
that pack a PLU (item code) plus either a weight or a price into the digits.
A typical in-store scheme looks like:

    2 PPPPP VVVVV C
    │ │     │     └ check digit (ignored — the scanner already verified it)
    │ │     └ embedded value: weight in grams (/1000) OR price in cents (/100)
    │ └ 5-digit item / PLU code
    └ prefix '2' (GS1 in-store / variable-measure range)

This module is deliberately free of any Frappe imports so it can be unit
tested in isolation and reused anywhere. The caller supplies a plain dict
matching the 'AlphaX POS Scale Barcode Definition' doctype fields.

All segment positions are 1-based (matching how a human reads the barcode
and how the doctype fields are labelled).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmbeddedResult:
    """Parsed embedded barcode. `qty` and `rate` are None when not encoded."""
    item_code: str
    qty: Optional[float]
    rate: Optional[float]
    definition_name: Optional[str] = None


def _slice_1based(code: str, start: int, length: int) -> str:
    """Extract a 1-based [start, start+length) slice, safely."""
    if not start or not length:
        return ""
    return code[start - 1: start - 1 + length]


def _to_number(segment: str, divider: float) -> Optional[float]:
    if not segment or not segment.isdigit():
        return None
    try:
        divider = float(divider) if divider else 1.0
        if divider == 0:
            divider = 1.0
        return int(segment) / divider
    except (ValueError, ZeroDivisionError):
        return None


def matches_definition(code: str, definition: dict) -> bool:
    """Cheap pre-check: does this code look like it belongs to `definition`?"""
    if not code or not code.isdigit():
        return False
    if not definition.get("enabled", 1):
        return False
    total_length = int(definition.get("total_length") or 0)
    if total_length and len(code) != total_length:
        return False
    prefix = (definition.get("prefix") or "").strip()
    if prefix and not code.startswith(prefix):
        return False
    return True


def parse(code: str, definition: dict) -> Optional[EmbeddedResult]:
    """Parse `code` against one definition dict. Returns None on no match.

    `definition` keys (all optional except positions actually used):
        prefix, total_length, item_start, item_length,
        qty_start, qty_length, qty_divider, use_qty_from_barcode,
        rate_start, rate_length, rate_divider, use_rate_from_barcode,
        definition_name
    """
    if not matches_definition(code, definition):
        return None

    item_code = _slice_1based(
        code,
        int(definition.get("item_start") or 0),
        int(definition.get("item_length") or 0),
    )
    if not item_code:
        return None
    # Strip leading zeros for matching convenience, but keep a non-empty code.
    item_code_stripped = item_code.lstrip("0") or item_code

    qty = rate = None
    if definition.get("use_qty_from_barcode"):
        qty = _to_number(
            _slice_1based(
                code,
                int(definition.get("qty_start") or 0),
                int(definition.get("qty_length") or 0),
            ),
            definition.get("qty_divider") or 1,
        )
    if definition.get("use_rate_from_barcode"):
        rate = _to_number(
            _slice_1based(
                code,
                int(definition.get("rate_start") or 0),
                int(definition.get("rate_length") or 0),
            ),
            definition.get("rate_divider") or 1,
        )

    return EmbeddedResult(
        item_code=item_code_stripped,
        qty=qty,
        rate=rate,
        definition_name=definition.get("definition_name"),
    )


def parse_first(code: str, definitions: list[dict]) -> Optional[EmbeddedResult]:
    """Try a list of definitions in order; return the first match."""
    for d in definitions or []:
        result = parse(code, d)
        if result is not None:
            return result
    return None
