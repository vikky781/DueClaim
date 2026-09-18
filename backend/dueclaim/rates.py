"""Dated RBI Bank Rate table.

Section 16 of the MSMED Act 2006 pegs statutory interest at three times the
Bank Rate notified by the Reserve Bank of India. The engine multiplies; this
module only answers "what was the Bank Rate on date X?".

All lookups read ``BANK_RATES`` at call time so tests can substitute a table
with ``monkeypatch.setattr(rates, "BANK_RATES", [...])`` without touching this
file.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal


class BankRateUnavailableError(LookupError):
    """Raised when asked for a Bank Rate on a date before the table begins."""


# (effective_from, rate_percent), sorted ascending by effective_from.
# TODO: historical entries to be supplied from rbi.org.in (verified). Only the
# current rate is seeded; any date before the first entry raises.
BANK_RATES: list[tuple[date, Decimal]] = [
    (date(2025, 12, 6), Decimal("5.50")),
]


def bank_rate_on(d: date) -> Decimal:
    """Return the RBI Bank Rate (percent p.a.) in force on ``d``."""
    earliest = BANK_RATES[0][0]
    if d < earliest:
        raise BankRateUnavailableError(
            f"No RBI Bank Rate known for {d.isoformat()}: the rate table starts "
            f"on {earliest.isoformat()}. Add earlier entries to dueclaim.rates.BANK_RATES."
        )
    rate = BANK_RATES[0][1]
    for effective_from, rate_percent in BANK_RATES:
        if effective_from > d:
            break
        rate = rate_percent
    return rate


def rate_changes_within(start: date, end: date) -> list[date]:
    """Dates on which a new Bank Rate takes effect, with ``start < date <= end``.

    Used by the engine to split an interest period at a rate change. A change
    effective exactly on ``start`` is not a split: ``bank_rate_on(start)``
    already returns the new rate.
    """
    return [eff for eff, _ in BANK_RATES if start < eff <= end]
