from datetime import date
from decimal import Decimal

import pytest

from dueclaim import rates
from dueclaim.engine import appointed_day, compute_claim
from dueclaim.rates import BankRateUnavailableError, bank_rate_on

TWO_DP = Decimal("0.01")


def q(x: Decimal) -> Decimal:
    return x.quantize(TWO_DP)


# Seeded rate: 5.50% from 2025-12-06 -> 16.50% p.a. statutory rate.
ACCEPTED = date(2026, 1, 15)  # +45 days = 2026-03-01
APPOINTED = date(2026, 3, 1)


# --- appointed_day -----------------------------------------------------------


def test_appointed_day_defaults_to_45_days_when_no_agreement():
    assert appointed_day(ACCEPTED, None) == APPOINTED


def test_agreed_credit_days_above_45_is_clamped_to_45():
    assert appointed_day(ACCEPTED, 60) == APPOINTED


def test_agreed_credit_days_below_45_is_honoured():
    assert appointed_day(ACCEPTED, 15) == date(2026, 1, 30)


# --- no interest cases -------------------------------------------------------


def test_not_yet_overdue_yields_zero_interest():
    r = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=date(2026, 2, 1))
    assert r.appointed_day == APPOINTED
    assert r.days_overdue == 0
    assert r.total_interest == Decimal("0")
    assert r.total_recoverable == Decimal("100000")
    assert r.breakdown == []


def test_exactly_on_appointed_day_yields_zero_interest():
    r = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=APPOINTED)
    assert r.days_overdue == 0
    assert r.total_interest == Decimal("0")
    assert r.breakdown == []


# --- compounding -------------------------------------------------------------


def test_one_full_month_overdue_is_one_capitalised_period():
    # Period 2026-03-02 .. 2026-04-01 = 31 days at 16.50% p.a.
    # 100000 * 0.165 * 31 / 365 = 1401.3698... -> 1401.37
    r = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=date(2026, 4, 1))
    assert r.days_overdue == 31
    assert len(r.breakdown) == 1
    p = r.breakdown[0]
    assert p.period_start == date(2026, 3, 2)
    assert p.period_end == date(2026, 4, 1)
    assert p.days == 31
    assert p.annual_rate_applied == Decimal("16.50")
    assert p.opening_balance == Decimal("100000")
    assert p.is_capitalised is True
    assert q(p.interest_for_period) == Decimal("1401.37")
    assert q(p.closing_balance) == Decimal("101401.37")
    assert q(r.total_interest) == Decimal("1401.37")
    assert q(r.total_recoverable) == Decimal("101401.37")


def test_several_full_months_compound_exceeds_simple_interest():
    # 6 completed periods: 2026-03-02 .. 2026-09-01 = 184 days.
    principal = Decimal("100000")
    as_of = date(2026, 9, 1)
    r = compute_claim(principal, ACCEPTED, None, as_of=as_of)
    assert len(r.breakdown) == 6
    assert all(p.is_capitalised for p in r.breakdown)
    assert sum(p.days for p in r.breakdown) == 184
    simple = principal * Decimal("16.50") / 100 * Decimal(184) / 365
    assert r.total_interest > simple
    # Each period opens on the previous period's closing balance.
    for prev, cur in zip(r.breakdown, r.breakdown[1:]):
        assert cur.opening_balance == prev.closing_balance


def test_partial_final_period_is_not_capitalised():
    r = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=date(2026, 4, 15))
    assert len(r.breakdown) == 2
    full, partial = r.breakdown
    assert full.is_capitalised is True
    assert partial.is_capitalised is False
    assert partial.period_start == date(2026, 4, 2)
    assert partial.period_end == date(2026, 4, 15)
    assert partial.days == 14
    # Simple day-count on the capitalised balance; balance does not grow.
    assert partial.opening_balance == full.closing_balance
    assert partial.closing_balance == partial.opening_balance
    expected = full.closing_balance * Decimal("16.50") / 100 * Decimal(14) / 365
    assert q(partial.interest_for_period) == q(expected)
    assert r.total_interest == full.interest_for_period + partial.interest_for_period
    assert r.total_recoverable == Decimal("100000") + r.total_interest


def test_agreed_credit_days_affect_accrual_start():
    clamped = compute_claim(Decimal("100000"), ACCEPTED, 60, as_of=date(2026, 4, 1))
    honoured = compute_claim(Decimal("100000"), ACCEPTED, 15, as_of=date(2026, 4, 1))
    assert clamped.appointed_day == APPOINTED
    assert honoured.appointed_day == date(2026, 1, 30)
    assert honoured.days_overdue == 61
    assert honoured.total_interest > clamped.total_interest


def test_mid_period_rate_change_splits_period_at_change_date(monkeypatch):
    monkeypatch.setattr(
        rates,
        "BANK_RATES",
        [
            (date(2025, 12, 6), Decimal("5.50")),
            (date(2026, 3, 17), Decimal("6.00")),
        ],
    )
    r = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=date(2026, 4, 1))
    assert len(r.breakdown) == 2
    a, b = r.breakdown
    # Segment 1: 2026-03-02 .. 2026-03-16 = 15 days at 16.50%
    assert (a.period_start, a.period_end, a.days) == (date(2026, 3, 2), date(2026, 3, 16), 15)
    assert a.annual_rate_applied == Decimal("16.50")
    assert a.is_capitalised is False
    assert a.opening_balance == Decimal("100000")
    assert a.closing_balance == Decimal("100000")  # no capitalisation mid-period
    # Segment 2: 2026-03-17 .. 2026-04-01 = 16 days at 18.00%
    assert (b.period_start, b.period_end, b.days) == (date(2026, 3, 17), date(2026, 4, 1), 16)
    assert b.annual_rate_applied == Decimal("18.00")
    assert b.is_capitalised is True
    assert b.opening_balance == Decimal("100000")  # same opening balance, not compounded
    # 100000*0.165*15/365 = 678.0822 ; 100000*0.18*16/365 = 789.0411 ; sum = 1467.12
    assert q(a.interest_for_period) == Decimal("678.08")
    assert q(b.interest_for_period) == Decimal("789.04")
    assert q(r.total_interest) == Decimal("1467.12")
    assert q(b.closing_balance) == Decimal("101467.12")


def test_leap_year_february_period_has_29_days_and_anchor_day_is_kept():
    # 2027-12-17 + 45 days = 2028-01-31. Rests: 2028-02-29 (clamped), 2028-03-31 (anchor day 31).
    accepted = date(2027, 12, 17)
    r = compute_claim(Decimal("100000"), accepted, None, as_of=date(2028, 3, 31))
    assert r.appointed_day == date(2028, 1, 31)
    assert len(r.breakdown) == 2
    feb, mar = r.breakdown
    assert (feb.period_start, feb.period_end, feb.days) == (date(2028, 2, 1), date(2028, 2, 29), 29)
    assert (mar.period_start, mar.period_end, mar.days) == (date(2028, 3, 1), date(2028, 3, 31), 31)
    assert feb.is_capitalised and mar.is_capitalised
    # 100000 * 0.165 * 29 / 365 = 1310.9589... -> 1310.96
    assert q(feb.interest_for_period) == Decimal("1310.96")


def test_amount_paid_reduces_principal_before_interest_accrues():
    unpaid = compute_claim(Decimal("100000"), ACCEPTED, None, as_of=date(2026, 4, 1))
    part = compute_claim(
        Decimal("100000"), ACCEPTED, None, as_of=date(2026, 4, 1), amount_paid=Decimal("40000")
    )
    assert part.principal_outstanding == Decimal("60000")
    assert part.breakdown[0].opening_balance == Decimal("60000")
    assert q(part.total_interest) == q(unpaid.total_interest * Decimal("0.6"))
    assert part.total_recoverable == Decimal("60000") + part.total_interest


# --- rates -------------------------------------------------------------------


def test_bank_rate_on_returns_rate_in_force():
    assert bank_rate_on(date(2025, 12, 6)) == Decimal("5.50")
    assert bank_rate_on(date(2030, 1, 1)) == Decimal("5.50")


def test_bank_rate_before_earliest_entry_raises_specific_exception():
    with pytest.raises(BankRateUnavailableError) as exc:
        bank_rate_on(date(2025, 12, 5))
    assert "2025-12-05" in str(exc.value)
    assert "2025-12-06" in str(exc.value)


def test_compute_claim_before_earliest_rate_raises_specific_exception():
    with pytest.raises(BankRateUnavailableError):
        compute_claim(Decimal("100000"), date(2025, 9, 1), None, as_of=date(2025, 12, 1))
