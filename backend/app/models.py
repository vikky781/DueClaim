"""Pydantic v2 models: what the API accepts and what the store persists.

Money fields are ``Decimal`` (rule 5). Interest is never a field on anything
persisted — it is recomputed from the engine on every read.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 2-digit state code, 10-char PAN, entity number, 'Z', checksum.
GSTIN_PATTERN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EnterpriseCategory(str, Enum):
    micro = "micro"
    small = "small"
    medium = "medium"


class InvoiceStatus(str, Enum):
    unpaid = "unpaid"
    partially_paid = "partially_paid"
    paid = "paid"


class Business(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    udyam_number: str = Field(min_length=1, max_length=40)
    legal_name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    enterprise_category: EnterpriseCategory


class InvoiceCreate(BaseModel):
    """Client-supplied invoice fields. ``id`` and ``created_at`` are server-assigned."""

    model_config = ConfigDict(str_strip_whitespace=True)

    invoice_number: str = Field(min_length=1, max_length=100)
    buyer_name: str = Field(min_length=1, max_length=200)
    buyer_gstin: str | None = Field(default=None, pattern=GSTIN_PATTERN)
    buyer_is_corporate: bool = True
    invoice_date: date
    acceptance_date: date
    agreed_credit_days: int | None = Field(default=None, ge=1)
    amount: Decimal = Field(gt=0)
    amount_paid: Decimal = Field(default=Decimal("0"), ge=0)
    status: InvoiceStatus = InvoiceStatus.unpaid

    @model_validator(mode="after")
    def _paid_not_more_than_amount(self) -> InvoiceCreate:
        if self.amount_paid > self.amount:
            raise ValueError("amount_paid must not exceed amount")
        return self


class Invoice(InvoiceCreate):
    id: str
    created_at: datetime


class InvoicePatch(BaseModel):
    amount_paid: Decimal | None = Field(default=None, ge=0)
    status: InvoiceStatus | None = None
