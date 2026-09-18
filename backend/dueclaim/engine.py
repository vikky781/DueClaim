"""Statutory interest engine for MSMED Act 2006, sections 15 and 16.

Pure functions, no I/O, ``decimal.Decimal`` throughout. Nothing here rounds:
callers quantize for presentation only.

Convention implemented (fixed; tests assert it):

* **Appointed day (s.15).** Payment is due on the agreed date, but never later
  than 45 days from the day of acceptance. ``appointed_day`` therefore returns
  ``acceptance_date + min(agreed_credit_days or 45, 45)`` days.
* **Accrual window.** Interest runs from the day *after* the appointed day up to
  and including ``as_of``. ``as_of`` on or before the appointed day -> no
  interest, ``days_overdue == 0``, empty breakdown.
* **Monthly rests.** Rest boundaries are ``appointed_day + n months`` for
  n = 1, 2, ... with end-of-month clamping (31 Jan + 1 month -> 28/29 Feb). The
  anchor is always the appointed day itself, so the day-of-month never drifts
  after a clamp (31 Jan -> 28 Feb -> 31 Mar). Period *n* covers the days
  ``boundary[n-1] + 1 .. boundary[n]`` inclusive.
* **Per-period interest.**
  ``opening_balance * (3 * bank_rate_on(period_start) / 100) * (days / 365)``.
  The denominator is always 365, including leap years.
* **Capitalisation.** At the end of each *completed* rest period the period's
  interest is added to the balance, and the next period opens on that larger
  balance. The final partial period (``boundary[k] + 1 .. as_of`` when
  ``as_of`` is not itself a boundary) accrues simple interest on the current
  balance and is **not** capitalised.
* **Rate change mid-period.** If the RBI Bank Rate changes strictly inside a
  period, that period is split at the change date into segments, each earning
  interest on the *same* opening balance at its own rate for its own day count.
  Each segment is its own ``RestPeriod`` row. Only the last segment of a
  completed period carries ``is_capitalised=True`` and a ``closing_balance``
  that includes the interest of *all* segments of that period; earlier segments
  show ``closing_balance == opening_balance``.
* **Row semantics.** ``closing_balance`` is the balance carried into the next
  row. It equals ``opening_balance`` for every row that does not capitalise.
  ``sum(row.interest_for_period) == total_interest`` and
  ``total_recoverable == principal_outstanding + total_interest`` always hold,
  so every headline figure is traceable to the breakdown.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from . import rates

STATUTORY_CREDIT_LIMIT_DAYS = 45
STATUTORY_MULTIPLIER = Decimal(3)
DAYS_IN_YEAR = Decimal(365)
ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class RestPeriod:
    period_start: date
    period_end: date
    days: int
    annual_rate_applied: Decimal  # percent p.a. after the 3x multiplier
    opening_balance: Decimal
    interest_for_period: Decimal
    closing_balance: Decimal
    is_capitalised: bool


@dataclass(frozen=True)
class ClaimResult:
    principal_outstanding: Decimal
    appointed_day: date
    days_overdue: int
    total_interest: Decimal
    total_recoverable: Decimal
    breakdown: list[RestPeriod] = field(default_factory=list)


def appointed_day(acceptance_date: date, agreed_credit_days: int | None) -> date:
    """Day payment fell due under MSMED Act s.15 (agreed period, capped at 45 days)."""
    credit_days = min(agreed_credit_days or STATUTORY_CREDIT_LIMIT_DAYS, STATUTORY_CREDIT_LIMIT_DAYS)
    return acceptance_date + timedelta(days=credit_days)


def _add_months(anchor: date, months: int) -> date:
    """``anchor + months`` calendar months, clamping the day to the target month's length."""
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _segments(start: date, end: date) -> list[tuple[date, date, Decimal]]:
    """Split ``start..end`` (inclusive) at Bank Rate changes -> [(seg_start, seg_end, annual_rate)]."""
    segments = []
    cursor = start
    for change in rates.rate_changes_within(start, end):
        segments.append((cursor, change - ONE_DAY, STATUTORY_MULTIPLIER * rates.bank_rate_on(cursor)))
        cursor = change
    segments.append((cursor, end, STATUTORY_MULTIPLIER * rates.bank_rate_on(cursor)))
    return segments


def _period_rows(
    start: date, end: date, opening_balance: Decimal, capitalise: bool
) -> tuple[list[RestPeriod], Decimal]:
    """Rows for one rest period (possibly split by rate changes) and the period's total interest."""
    segments = _segments(start, end)
    interests = [
        opening_balance * (rate / 100) * (Decimal((seg_end - seg_start).days + 1) / DAYS_IN_YEAR)
        for seg_start, seg_end, rate in segments
    ]
    period_interest = sum(interests, Decimal(0))
    rows = []
    for index, ((seg_start, seg_end, rate), interest) in enumerate(zip(segments, interests)):
        is_last = index == len(segments) - 1
        capitalised_here = capitalise and is_last
        rows.append(
            RestPeriod(
                period_start=seg_start,
                period_end=seg_end,
                days=(seg_end - seg_start).days + 1,
                annual_rate_applied=rate,
                opening_balance=opening_balance,
                interest_for_period=interest,
                closing_balance=opening_balance + period_interest if capitalised_here else opening_balance,
                is_capitalised=capitalised_here,
            )
        )
    return rows, period_interest


def compute_claim(
    principal: Decimal,
    acceptance_date: date,
    agreed_credit_days: int | None,
    as_of: date,
    amount_paid: Decimal = Decimal("0"),
) -> ClaimResult:
    """Statutory interest under MSMED Act s.16 from the appointed day to ``as_of``.

    See the module docstring for the exact convention.
    """
    principal_outstanding = principal - amount_paid
    if principal_outstanding < 0:
        raise ValueError(f"amount_paid ({amount_paid}) exceeds principal ({principal})")

    due = appointed_day(acceptance_date, agreed_credit_days)
    if as_of <= due:
        return ClaimResult(
            principal_outstanding=principal_outstanding,
            appointed_day=due,
            days_overdue=0,
            total_interest=Decimal(0),
            total_recoverable=principal_outstanding,
            breakdown=[],
        )

    breakdown: list[RestPeriod] = []
    balance = principal_outstanding
    total_interest = Decimal(0)
    previous_boundary = due
    n = 1
    while True:
        boundary = _add_months(due, n)
        if boundary > as_of:
            break
        rows, period_interest = _period_rows(previous_boundary + ONE_DAY, boundary, balance, capitalise=True)
        breakdown.extend(rows)
        balance += period_interest
        total_interest += period_interest
        previous_boundary = boundary
        n += 1

    if previous_boundary < as_of:
        rows, period_interest = _period_rows(previous_boundary + ONE_DAY, as_of, balance, capitalise=False)
        breakdown.extend(rows)
        total_interest += period_interest

    return ClaimResult(
        principal_outstanding=principal_outstanding,
        appointed_day=due,
        days_overdue=(as_of - due).days,
        total_interest=total_interest,
        total_recoverable=principal_outstanding + total_interest,
        breakdown=breakdown,
    )
