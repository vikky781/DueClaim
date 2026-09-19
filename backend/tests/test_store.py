"""DynamoStore against moto's in-process DynamoDB: key layout and Decimal round-trip."""

from datetime import date, datetime, timezone
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from app.models import Business, Invoice
from app.store import DynamoStore, normalize_buyer_name
from tests.conftest import business_payload, invoice_payload

TABLE = "dueclaim-test"


@pytest.fixture
def table_and_store(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-south-1")
        table = ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        yield table, DynamoStore(TABLE)


def make_invoice(**overrides) -> Invoice:
    data = invoice_payload(**overrides)
    return Invoice(
        id=overrides.get("id", "inv-0001"),
        created_at=datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc),
        **{k: v for k, v in data.items() if k != "id"},
    )


def test_money_round_trips_through_dynamodb_as_exact_decimal(table_and_store):
    _, store = table_and_store
    store.put_invoice("sub-1", make_invoice(amount="123456.78", amount_paid="1000.05"))
    got = store.get_invoice("sub-1", "inv-0001")
    assert got is not None
    assert isinstance(got.amount, Decimal)
    assert got.amount == Decimal("123456.78")
    assert str(got.amount) == "123456.78"  # no float drift, no exponent
    assert got.amount_paid == Decimal("1000.05")


def test_invoice_round_trips_all_fields(table_and_store):
    _, store = table_and_store
    original = make_invoice(agreed_credit_days=30, buyer_gstin=None, status="partially_paid", amount_paid="10")
    store.put_invoice("sub-1", original)
    assert store.get_invoice("sub-1", "inv-0001") == original


def test_invoice_item_key_layout(table_and_store):
    table, store = table_and_store
    store.put_invoice("sub-1", make_invoice(buyer_name="  Acme   INDUSTRIES Pvt Ltd "))
    item = table.get_item(Key={"PK": "USER#sub-1", "SK": "INV#inv-0001"})["Item"]
    assert item["GSI1PK"] == "USER#sub-1#BUYER#acme industries pvt ltd"
    assert item["GSI1SK"] == "INV#2026-01-10#inv-0001"
    assert isinstance(item["amount"], Decimal)


def test_normalize_buyer_name_collapses_case_and_whitespace():
    assert normalize_buyer_name("  Acme   INDUSTRIES Pvt Ltd ") == "acme industries pvt ltd"


def test_list_and_delete_are_scoped_to_user(table_and_store):
    _, store = table_and_store
    store.put_invoice("sub-1", make_invoice(id="a"))
    store.put_invoice("sub-1", make_invoice(id="b"))
    store.put_invoice("sub-2", make_invoice(id="c"))
    assert sorted(i.id for i in store.list_invoices("sub-1")) == ["a", "b"]
    assert store.get_invoice("sub-2", "a") is None
    assert store.delete_invoice("sub-2", "a") is False
    assert store.delete_invoice("sub-1", "a") is True
    assert [i.id for i in store.list_invoices("sub-1")] == ["b"]


def test_business_round_trip_and_key_layout(table_and_store):
    table, store = table_and_store
    biz = Business(**business_payload())
    assert store.get_business("sub-1") is None
    store.put_business("sub-1", biz)
    assert store.get_business("sub-1") == biz
    item = table.get_item(Key={"PK": "USER#sub-1", "SK": "BUSINESS"})["Item"]
    assert item["udyam_number"] == "UDYAM-MH-18-0012345"


def test_invoice_with_notice_records_round_trips(table_and_store):
    from app.models import NoticeRecord

    _, store = table_and_store
    rec = NoticeRecord(
        key="notices/sub-1/inv-0001-20260919T101500Z.pdf",
        generated_at=datetime(2026, 9, 19, 10, 15, tzinfo=timezone.utc),
        as_of=date(2026, 9, 19),
        principal_outstanding=Decimal("500000.00"),
        total_interest=Decimal("47476.11"),
        total_recoverable=Decimal("547476.11"),
    )
    original = make_invoice().model_copy(update={"notices": [rec]})
    store.put_invoice("sub-1", original)
    got = store.get_invoice("sub-1", "inv-0001")
    assert got == original
    assert isinstance(got.notices[0].total_recoverable, Decimal)
    assert got.notices[0].total_recoverable == Decimal("547476.11")
