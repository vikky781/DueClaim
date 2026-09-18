"""Presentation-layer money quantization.

Rule: engine internals carry full ``Decimal`` precision end to end. Quantization
to two decimal places (rupees.paise) happens exactly once, at the serialization
boundary (API response, PDF, table render). Nothing inside ``dueclaim.engine``
imports or calls this module.

Rounding mode is ``ROUND_HALF_UP`` — the commercial convention (0.005 -> 0.01),
not Python's default banker's rounding.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def quantize_money(d: Decimal) -> Decimal:
    """``d`` rounded to 2dp with ROUND_HALF_UP, as a Decimal."""
    return d.quantize(PAISE, rounding=ROUND_HALF_UP)


def to_paise_string(d: Decimal) -> str:
    """``d`` rounded to 2dp with ROUND_HALF_UP, as a plain string (never scientific notation)."""
    return f"{quantize_money(d):f}"
