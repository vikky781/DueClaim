from datetime import date
from decimal import Decimal

from dueclaim.engine import compute_claim
from dueclaim.money import to_paise_string
from tests.conftest import TODAY, USER, business_payload, invoice_payload

API = "/api/v1"


def _setup(client):
    client.post(f"{API}/business", json=business_payload())
    return client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]


def test_generate_notice_writes_pdf_returns_url_and_records_on_invoice(client_with_uploads, uploads, store):
    inv_id = _setup(client_with_uploads)
    r = client_with_uploads.post(f"{API}/invoices/{inv_id}/notice")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://")
    assert body["key"].startswith(f"notices/{USER}/{inv_id}-") and body["key"].endswith(".pdf")
    assert body["expires_in"] == 3600
    expected = compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=TODAY)
    assert body["as_of"] == "2026-09-18"
    assert body["principal_outstanding"] == "500000.00"
    assert body["total_interest"] == to_paise_string(expected.total_interest)
    assert body["total_recoverable"] == to_paise_string(expected.total_recoverable)
    assert body["days_overdue"] == expected.days_overdue
    assert body["notices_generated"] == 1
    # the object really went to storage as a PDF
    stored_key, content_type, data = uploads.objects[-1]
    assert stored_key == body["key"] and content_type == "application/pdf" and data[:5] == b"%PDF-"
    assert uploads.presigned_gets == [(body["key"], 3600)]
    # record on the invoice, visible through the API
    inv = store.get_invoice(USER, inv_id)
    assert len(inv.notices) == 1
    assert inv.notices[0].key == body["key"]
    assert inv.notices[0].total_recoverable == expected.total_recoverable
    detail = client_with_uploads.get(f"{API}/invoices/{inv_id}").json()
    assert len(detail["notices"]) == 1
    assert detail["notices"][0]["total_recoverable"] == to_paise_string(expected.total_recoverable)


def test_second_notice_appends_and_summary_counts_them(client_with_uploads):
    inv_id = _setup(client_with_uploads)
    client_with_uploads.post(f"{API}/invoices/{inv_id}/notice")
    r = client_with_uploads.post(f"{API}/invoices/{inv_id}/notice")
    assert r.json()["notices_generated"] == 2
    assert client_with_uploads.get(f"{API}/portfolio/summary").json()["notices_generated"] == 2


def test_notice_honours_as_of(client_with_uploads):
    inv_id = _setup(client_with_uploads)
    r = client_with_uploads.post(f"{API}/invoices/{inv_id}/notice", params={"as_of": "2026-12-31"})
    expected = compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=date(2026, 12, 31))
    assert r.json()["as_of"] == "2026-12-31"
    assert r.json()["total_recoverable"] == to_paise_string(expected.total_recoverable)


def test_notice_requires_business_profile(client_with_uploads):
    inv_id = client_with_uploads.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    r = client_with_uploads.post(f"{API}/invoices/{inv_id}/notice")
    assert r.status_code == 409
    assert "business" in r.json()["detail"].lower()


def test_notice_for_unknown_invoice_is_404(client_with_uploads):
    client_with_uploads.post(f"{API}/business", json=business_payload())
    assert client_with_uploads.post(f"{API}/invoices/nope/notice").status_code == 404
