import re

import pytest

from tests.conftest import USER

API = "/api/v1/uploads"


def _textract(fields: list[tuple[str, str, float]]) -> dict:
    return {
        "ExpenseDocuments": [
            {
                "SummaryFields": [
                    {"Type": {"Text": t}, "ValueDetection": {"Text": v, "Confidence": c}} for t, v, c in fields
                ]
            }
        ]
    }


@pytest.mark.parametrize("ctype, ext", [("image/jpeg", "jpg"), ("image/png", "png"), ("application/pdf", "pdf")])
def test_presign_scopes_key_to_user_and_returns_put_url(client_with_uploads, uploads, ctype, ext):
    r = client_with_uploads.post(f"{API}/presign", json={"content_type": ctype, "filename": "scan.bin"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert re.fullmatch(rf"uploads/{USER}/[0-9a-f]{{32}}\.{ext}", body["key"])
    assert body["url"].startswith("https://")
    assert body["headers"] == {"Content-Type": ctype}
    assert body["expires_in"] == 300
    assert uploads.presigned == [(body["key"], ctype)]


@pytest.mark.parametrize("ctype", ["image/gif", "text/plain", "application/octet-stream", "", "image/jpeg; charset=x"])
def test_presign_rejects_other_content_types(client_with_uploads, ctype):
    r = client_with_uploads.post(f"{API}/presign", json={"content_type": ctype})
    assert r.status_code == 422


def test_extract_maps_textract_output_with_confidence_and_writes_nothing(client_with_uploads, uploads, store):
    key = f"uploads/{USER}/{'a' * 32}.png"
    uploads.responses[key] = _textract(
        [
            ("INVOICE_RECEIPT_ID", "INV-2026-0142", 97.5),
            ("INVOICE_RECEIPT_DATE", "15/01/2026", 92.1),
            ("RECEIVER_NAME", "Acme Industries Pvt Ltd", 88.0),
            ("VENDOR_NAME", "Sharma Precision Tools", 99.0),
            ("TOTAL", "Rs. 5,00,000.00", 96.3),
        ]
    )
    r = client_with_uploads.post(f"{API}/{key}/extract")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == key
    assert body["invoice_number"] == {"value": "INV-2026-0142", "confidence": 97.5, "raw": "INV-2026-0142", "source": "INVOICE_RECEIPT_ID"}
    assert body["invoice_date"]["value"] == "2026-01-15"
    assert body["buyer_name"]["value"] == "Acme Industries Pvt Ltd"
    assert body["amount"] == {"value": "500000.00", "confidence": 96.3, "raw": "Rs. 5,00,000.00", "source": "TOTAL"}
    assert "acceptance_date" not in body
    assert store.list_invoices(USER) == []  # extraction never persists


def test_extract_returns_nulls_for_unparseable_fields(client_with_uploads, uploads):
    key = f"uploads/{USER}/{'b' * 32}.jpg"
    uploads.responses[key] = _textract([("INVOICE_RECEIPT_DATE", "Date", 40.0), ("TOTAL", "1,000 and 2,000", 55.0)])
    body = client_with_uploads.post(f"{API}/{key}/extract").json()
    assert body["invoice_date"] == {"value": None, "confidence": 40.0, "raw": "Date", "source": "INVOICE_RECEIPT_DATE"}
    assert body["amount"]["value"] is None
    assert body["invoice_number"] == {"value": None, "confidence": None, "raw": None, "source": None}


def test_extract_refuses_keys_outside_the_users_prefix(client_with_uploads, uploads):
    other = f"uploads/someone-else/{'c' * 32}.png"
    uploads.responses[other] = _textract([("TOTAL", "1.00", 99.0)])
    assert client_with_uploads.post(f"{API}/{other}/extract").status_code == 404
    assert client_with_uploads.post(f"{API}/uploads/{USER}/../../etc/passwd/extract").status_code == 404
    assert client_with_uploads.post(f"{API}/uploads/{USER}/not-a-uuid.png/extract").status_code == 404


def test_extract_when_object_not_uploaded_yet_is_422(client_with_uploads, uploads):
    key = f"uploads/{USER}/{'d' * 32}.pdf"
    uploads.missing.add(key)
    r = client_with_uploads.post(f"{API}/{key}/extract")
    assert r.status_code == 422
    assert "upload" in r.json()["detail"].lower()


def test_extract_unsupported_document_is_422(client_with_uploads, uploads):
    key = f"uploads/{USER}/{'e' * 32}.pdf"
    uploads.unsupported.add(key)
    r = client_with_uploads.post(f"{API}/{key}/extract")
    assert r.status_code == 422
    assert "read" in r.json()["detail"].lower()


def test_uploads_require_identity(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.delenv("DEV_USER_SUB", raising=False)
    with TestClient(app) as c:
        assert c.post(f"{API}/presign", json={"content_type": "image/png"}).status_code == 401


def test_aws_presign_uses_regional_virtual_hosted_endpoint(monkeypatch):
    """A global-endpoint URL makes S3 answer 307 to the browser's PUT. Pin the regional host."""
    from app.routes.uploads import AwsUploads

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    url = AwsUploads("dueclaim-uploads-dev-123", "ap-south-1").presign_put("uploads/u/k.png", "image/png", 300)
    host = url.split("/")[2]
    assert host == "dueclaim-uploads-dev-123.s3.ap-south-1.amazonaws.com"
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Expires=300" in url
