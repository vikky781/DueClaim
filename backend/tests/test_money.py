from decimal import Decimal

import pytest

from dueclaim.money import quantize_money, to_paise_string


@pytest.mark.parametrize(
    "raw, expected",
    [
        # exact .005 boundary rounds away from zero (HALF_UP), not to even
        ("1.005", "1.01"),
        ("1.015", "1.02"),
        ("1.025", "1.03"),
        ("2.675", "2.68"),
        ("0.005", "0.01"),
        ("-1.005", "-1.01"),
        # just below the boundary rounds down
        ("1.00499999", "1.00"),
        # already at 2dp / integers are padded, not altered
        ("1.10", "1.10"),
        ("100", "100.00"),
        ("0", "0.00"),
        # engine-scale precision
        ("47230.62152948687344696919007", "47230.62"),
        ("543057.2636540088057751899903", "543057.26"),
    ],
)
def test_quantize_money_rounds_half_up_to_two_places(raw, expected):
    assert quantize_money(Decimal(raw)) == Decimal(expected)


@pytest.mark.parametrize("raw, expected", [("1.005", "1.01"), ("100", "100.00"), ("-0.005", "-0.01")])
def test_to_paise_string_is_the_quantized_decimal_as_plain_string(raw, expected):
    out = to_paise_string(Decimal(raw))
    assert isinstance(out, str)
    assert out == expected


def test_to_paise_string_never_uses_scientific_notation():
    assert to_paise_string(Decimal("1E+2")) == "100.00"
    assert to_paise_string(Decimal("5E-3")) == "0.01"
