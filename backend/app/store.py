"""Single-table DynamoDB access.

Key layout
----------
Business : PK=USER#{sub}  SK=BUSINESS
Invoice  : PK=USER#{sub}  SK=INV#{invoice_id}
GSI1     : GSI1PK=USER#{sub}#BUYER#{normalized_buyer_name}
           GSI1SK=INV#{invoice_date}#{invoice_id}

Money is written and read as ``Decimal``. boto3's DynamoDB serializer accepts
Decimal natively and rejects float, so a value like 123456.78 round-trips with
no precision loss (see tests/test_store.py). Dates and datetimes are stored as
ISO-8601 strings. No interest figure is ever stored.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any, Protocol

import boto3
from boto3.dynamodb.conditions import Key

from .models import Business, Invoice

_WS = re.compile(r"\s+")


def normalize_buyer_name(name: str) -> str:
    return _WS.sub(" ", name.strip()).lower()


class Store(Protocol):
    def put_business(self, sub: str, business: Business) -> None: ...
    def get_business(self, sub: str) -> Business | None: ...
    def put_invoice(self, sub: str, invoice: Invoice) -> None: ...
    def get_invoice(self, sub: str, invoice_id: str) -> Invoice | None: ...
    def list_invoices(self, sub: str) -> list[Invoice]: ...
    def delete_invoice(self, sub: str, invoice_id: str) -> bool: ...


def _user_pk(sub: str) -> str:
    return f"USER#{sub}"


def _invoice_sk(invoice_id: str) -> str:
    return f"INV#{invoice_id}"


def _to_item(model: Any) -> dict[str, Any]:
    """Model -> DynamoDB attribute dict. Decimal stays Decimal; dates become ISO strings."""
    out: dict[str, Any] = {}
    for key, value in model.__dict__.items():
        if value is None:
            continue  # DynamoDB has no useful null semantics for optional fields
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            pass
        out[key] = value
    return out


_INVOICE_FIELDS = set(Invoice.model_fields)
_BUSINESS_FIELDS = set(Business.model_fields)


class DynamoStore:
    def __init__(self, table_name: str, resource: Any | None = None) -> None:
        self._table = (resource or boto3.resource("dynamodb")).Table(table_name)

    # -- business -----------------------------------------------------------

    def put_business(self, sub: str, business: Business) -> None:
        item = {"PK": _user_pk(sub), "SK": "BUSINESS", "entity": "BUSINESS", **_to_item(business)}
        self._table.put_item(Item=item)

    def get_business(self, sub: str) -> Business | None:
        resp = self._table.get_item(Key={"PK": _user_pk(sub), "SK": "BUSINESS"})
        item = resp.get("Item")
        if not item:
            return None
        return Business.model_validate({k: v for k, v in item.items() if k in _BUSINESS_FIELDS})

    # -- invoices -----------------------------------------------------------

    def put_invoice(self, sub: str, invoice: Invoice) -> None:
        item = {
            "PK": _user_pk(sub),
            "SK": _invoice_sk(invoice.id),
            "entity": "INVOICE",
            "GSI1PK": f"{_user_pk(sub)}#BUYER#{normalize_buyer_name(invoice.buyer_name)}",
            "GSI1SK": f"INV#{invoice.invoice_date.isoformat()}#{invoice.id}",
            **_to_item(invoice),
        }
        self._table.put_item(Item=item)

    def get_invoice(self, sub: str, invoice_id: str) -> Invoice | None:
        resp = self._table.get_item(Key={"PK": _user_pk(sub), "SK": _invoice_sk(invoice_id)})
        item = resp.get("Item")
        return self._invoice_from_item(item) if item else None

    def list_invoices(self, sub: str) -> list[Invoice]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(_user_pk(sub)) & Key("SK").begins_with("INV#")
        }
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return [self._invoice_from_item(i) for i in items]

    def delete_invoice(self, sub: str, invoice_id: str) -> bool:
        resp = self._table.delete_item(
            Key={"PK": _user_pk(sub), "SK": _invoice_sk(invoice_id)}, ReturnValues="ALL_OLD"
        )
        return "Attributes" in resp and bool(resp["Attributes"])

    @staticmethod
    def _invoice_from_item(item: dict[str, Any]) -> Invoice:
        return Invoice.model_validate({k: v for k, v in item.items() if k in _INVOICE_FIELDS})


@lru_cache(maxsize=1)
def _default_store() -> DynamoStore:
    table_name = os.environ.get("TABLE_NAME")
    if not table_name:
        raise RuntimeError("TABLE_NAME environment variable is not set")
    return DynamoStore(table_name)


def get_store() -> Store:
    """FastAPI dependency. Tests override this with an in-memory fake."""
    return _default_store()
