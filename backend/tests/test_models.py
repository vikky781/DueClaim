from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Business, InvoiceCreate
from tests.conftest import business_payload, invoice_payload


def test_invoice_create_parses_money_as_decimal():
    inv = InvoiceCreate(**invoice_payload(amount="123456.78", amount_paid="0.01"))
    assert inv.amount == Decimal("123456.78")
    assert isinstance(inv.amount, Decimal)
    assert inv.amount_paid == Decimal("0.01")
    assert inv.buyer_is_corporate is True
    assert inv.status.value == "unpaid"


@pytest.mark.parametrize("amount", ["0", "-1", "-0.01"])
def test_invoice_rejects_non_positive_amount(amount):
    with pytest.raises(ValidationError):
        InvoiceCreate(**invoice_payload(amount=amount))


def test_invoice_rejects_amount_paid_greater_than_amount():
    with pytest.raises(ValidationError) as exc:
        InvoiceCreate(**invoice_payload(amount="100", amount_paid="100.01"))
    assert "amount_paid" in str(exc.value)


def test_invoice_allows_amount_paid_equal_to_amount():
    inv = InvoiceCreate(**invoice_payload(amount="100", amount_paid="100"))
    assert inv.amount_paid == inv.amount


def test_invoice_rejects_negative_amount_paid():
    with pytest.raises(ValidationError):
        InvoiceCreate(**invoice_payload(amount_paid="-5"))


@pytest.mark.parametrize("gstin", ["27AAPFU0939F1ZV", "07AABCU9603R1ZM"])
def test_valid_gstin_accepted(gstin):
    assert InvoiceCreate(**invoice_payload(buyer_gstin=gstin)).buyer_gstin == gstin


@pytest.mark.parametrize("gstin", ["27AAPFU0939F1Z", "27aapfu0939f1zv", "XXAAPFU0939F1ZV", "27AAPFU0939F1AV"])
def test_invalid_gstin_rejected(gstin):
    with pytest.raises(ValidationError):
        InvoiceCreate(**invoice_payload(buyer_gstin=gstin))


def test_gstin_is_optional():
    assert InvoiceCreate(**invoice_payload(buyer_gstin=None)).buyer_gstin is None


def test_business_requires_valid_category():
    assert Business(**business_payload()).enterprise_category.value == "micro"
    with pytest.raises(ValidationError):
        Business(**business_payload(enterprise_category="large"))
