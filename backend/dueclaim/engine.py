"""Statutory interest engine for MSMED Act 2006, sections 15 and 16.

Pure functions, no I/O, ``decimal.Decimal`` throughout. Nothing in this module
rounds or quantizes; every figure is carried at full Decimal context precision.
Quantization to paise happens once, at the serialization boundary, via
``dueclaim.money`` — which this module must never import.

REST CONVENTION (fixed; the test suite asserts each clause)
===========================================================

1. Appointed day (s.15).
   Payment falls due on the day agreed in writing between supplier and buyer,
   but in no case later than 45 days from the day of acceptance (or deemed
   acceptance) of the goods or services. ``appointed_day`` therefore returns
   ``acceptance_date + min(agreed_credit_days or 45, 45)`` days. An agreed
   period longer than 45 days is clamped to 45; a shorter one is honoured; no
   agreement means 45.

2. Accrual window.
   Interest accrues from the day AFTER the appointed day, up to and including
   ``as_of``. If ``as_of`` is on or before the appointed day there is no
   interest: ``days_overdue == 0``, ``total_interest == 0``, empty breakdown.
   ``days_overdue = (as_of - appointed_day).days``.

3. Monthly rests, anchored to the appointed day.
   Rest boundaries are ``appointed_day + n calendar months`` for n = 1, 2, ...
   The anchor is ALWAYS the appointed day itself, never the previous boundary,
   so the day-of-month does not drift after a clamp. End-of-month clamping:
   if the anchor day does not exist in the target month, the boundary is the
   last day of that month (31 Jan -> 28 Feb, or 29 Feb in a leap year ->
   31 Mar). Rest period n covers the days ``boundary[n-1] + 1`` through
   ``boundary[n]`` inclusive, where ``boundary[0]`` is the appointed day.

4. Interest for a period (or segment).
   ``interest = opening_balance * (3 * bank_rate / 100) * (days / 365)``
   where ``bank_rate`` is the RBI Bank Rate (percent p.a.) in force on the
   first day of the period or segment, ``3 *`` is the s.16 multiplier, and
   ``days`` is the inclusive day count of the period or segment. The
   denominator is always 365, including in leap years. No rounding.

5. Capitalisation at completed rest boundaries only.
   At the end of each COMPLETED rest period the period's interest is added to
   the balance, and the next period opens on that enlarged balance. That is
   what "compound interest with monthly rests" means here.

6. Final partial period.
   If ``as_of`` is not itself a rest boundary, the days from the last boundary
   + 1 through ``as_of`` form a final partial period. It accrues SIMPLE
   interest on the balance as it stood at the last boundary and is NOT
   capitalised (``is_capitalised == False``). If ``as_of`` falls exactly on a
   boundary, the last period is a completed one and is capitalised.

7. Mid-period Bank Rate change.
   If the RBI Bank Rate changes on a date strictly inside a rest period, the
   period is split at the change date into consecutive day segments
   (``start .. change-1`` and ``change .. end``). Each segment earns interest
   on the SAME opening balance — the balance at the start of the rest period —
   at its own rate for its own day count. There is no capitalisation at the
   change date. The balance rolled forward at the boundary is the opening
   balance plus the interest of ALL segments in that period. Each segment is
   emitted as its own ``RestPeriod`` row; only the last segment of a completed
   period carries ``is_capitalised == True``.

ROW SEMANTICS (``RestPeriod``)
==============================

* ``opening_balance`` is the base on which ``interest_for_period`` was
  computed, i.e. clause 4 can be re-derived from the row's own columns.
* ``closing_balance == opening_balance + interest_for_period`` for EVERY row,
  capitalised or not.
* ``is_capitalised`` says whether that closing balance rolls forward as the
  next row's opening balance. Within a rate-split period the segments share
  one opening balance, so the next period opens on
  ``opening_balance + sum(segment interests)`` rather than on the last
  segment's ``closing_balance`` alone.

RESULT INVARIANTS (``ClaimResult``)
===================================

* ``sum(row.interest_for_period) == total_interest``
* ``total_recoverable == principal_outstanding + total_interest``
* ``breakdown[-1].closing_balance == total_recoverable`` whenever the final
  period is a single unsplit row (always true unless a Bank Rate change falls
  inside the final period).

Every headline figure is therefore traceable to specific rows.
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
                closing_balance=opening_balance + interest,
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
