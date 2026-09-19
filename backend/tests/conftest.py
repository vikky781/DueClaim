from __future__ import annotations

from datetime import date

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth import get_current_user_sub
from app.main import app
from app.models import Business, Invoice
from app.routes.invoices import get_today
from app.store import get_store

TODAY = date(2026, 9, 18)
USER = "user-sub-aaa"
OTHER_USER = "user-sub-bbb"


class FakeStore:
    """In-memory stand-in for DynamoStore with the same method surface."""

    def __init__(self) -> None:
        self.businesses: dict[str, Business] = {}
        self.invoices: dict[tuple[str, str], Invoice] = {}

    def put_business(self, sub: str, business: Business) -> None:
        self.businesses[sub] = business

    def get_business(self, sub: str) -> Business | None:
        return self.businesses.get(sub)

    def put_invoice(self, sub: str, invoice: Invoice) -> None:
        self.invoices[(sub, invoice.id)] = invoice

    def get_invoice(self, sub: str, invoice_id: str) -> Invoice | None:
        return self.invoices.get((sub, invoice_id))

    def list_invoices(self, sub: str) -> list[Invoice]:
        return [inv for (s, _), inv in self.invoices.items() if s == sub]

    def delete_invoice(self, sub: str, invoice_id: str) -> bool:
        return self.invoices.pop((sub, invoice_id), None) is not None


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _test_identity(request: Request) -> str:
    """Identity override: the X-Test-User header, defaulting to USER.

    Both clients share one global ``app``, so the override must not bake in
    a single sub.
    """
    return request.headers.get("X-Test-User", USER)


def _install_overrides(store: FakeStore) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user_sub] = _test_identity
    app.dependency_overrides[get_today] = lambda: TODAY


@pytest.fixture
def client(store: FakeStore):
    _install_overrides(store)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def as_other_user(store: FakeStore):
    """Client authenticated as a different Cognito sub, sharing the same store."""
    _install_overrides(store)
    with TestClient(app, headers={"X-Test-User": OTHER_USER}) as c:
        yield c
    app.dependency_overrides.clear()


def invoice_payload(**overrides) -> dict:
    base = {
        "invoice_number": "INV-001",
        "buyer_name": "Acme Industries Pvt Ltd",
        "buyer_gstin": "27AAPFU0939F1ZV",
        "buyer_is_corporate": True,
        "invoice_date": "2026-01-10",
        "acceptance_date": "2026-01-15",
        "agreed_credit_days": None,
        "amount": "500000.00",
        "amount_paid": "0",
    }
    base.update(overrides)
    return base


def business_payload(**overrides) -> dict:
    base = {
        "udyam_number": "UDYAM-MH-18-0012345",
        "legal_name": "Sharma Precision Tools",
        "address": "Plot 12, MIDC, Pune 411026",
        "email": "accounts@sharmatools.in",
        "enterprise_category": "micro",
    }
    base.update(overrides)
    return base


# --- uploads / OCR -------------------------------------------------------------

from app.routes.uploads import get_uploads_backend  # noqa: E402


class FakeUploads:
    """Stands in for S3 presign + Textract. Records calls; serves a canned response per key."""

    def __init__(self) -> None:
        self.presigned: list[tuple[str, str]] = []
        self.responses: dict[str, dict] = {}
        self.missing: set[str] = set()
        self.unsupported: set[str] = set()
        self.objects: list[tuple[str, str, bytes]] = []
        self.presigned_gets: list[tuple[str, int]] = []

    def presign_put(self, key: str, content_type: str, expires_in: int) -> str:
        self.presigned.append((key, content_type))
        return f"https://fake-bucket.s3.ap-south-1.amazonaws.com/{key}?X-Amz-Signature=fake"

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.objects.append((key, content_type, data))

    def presign_get(self, key: str, expires_in: int) -> str:
        self.presigned_gets.append((key, expires_in))
        return f"https://fake-bucket.s3.ap-south-1.amazonaws.com/{key}?X-Amz-Signature=fake-get"

    def analyze_expense(self, key: str) -> dict:
        from app.routes.uploads import ObjectMissing, UnsupportedDocument

        if key in self.missing:
            raise ObjectMissing(key)
        if key in self.unsupported:
            raise UnsupportedDocument(key)
        return self.responses.get(key, {"ExpenseDocuments": []})


@pytest.fixture
def uploads() -> FakeUploads:
    return FakeUploads()


@pytest.fixture
def client_with_uploads(store: FakeStore, uploads: FakeUploads):
    _install_overrides(store)
    app.dependency_overrides[get_uploads_backend] = lambda: uploads
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
