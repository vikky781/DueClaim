"""Demand notice PDF: pure rendering from Business + Invoice + ClaimResult. Nothing recomputed."""

import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pypdf import PdfReader

from app.models import Business, Invoice
from app.notice import render_demand_notice
from dueclaim.engine import compute_claim
from dueclaim.money import to_inr_string
from tests.conftest import business_payload, invoice_payload

AS_OF = date(2026, 9, 19)


def _invoice(**overrides) -> Invoice:
    data = invoice_payload(**overrides)
    return Invoice(id="inv-0001", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc), **data)


def _text(pdf: bytes) -> tuple[list[str], str]:
    """Per-page text, plus the whole document with whitespace collapsed (line wraps are layout, not content)."""
    reader = PdfReader(io.BytesIO(pdf))
    pages = [p.extract_text() or "" for p in reader.pages]
    return pages, re.sub(r"\s+", " ", " ".join(pages))


@pytest.fixture
def business() -> Business:
    return Business(**business_payload())


def test_renders_a_pdf_with_all_legal_elements(business):
    inv = _invoice()
    claim = compute_claim(inv.amount, inv.acceptance_date, inv.agreed_credit_days, as_of=AS_OF, amount_paid=inv.amount_paid)
    pdf = render_demand_notice(business, inv, claim, as_of=AS_OF)
    assert pdf[:5] == b"%PDF-"
    pages, text = _text(pdf)

    # sender / recipient
    assert "Sharma Precision Tools" in text
    assert "Plot 12, MIDC, Pune 411026" in text
    assert "UDYAM-MH-18-0012345" in text
    assert "Acme Industries Pvt Ltd" in text
    assert "27AAPFU0939F1ZV" in text
    # subject + statute
    assert "INV-001" in text
    assert "Section 15" in text and "Section 16" in text and "Section 24" in text
    assert "Micro, Small and Medium Enterprises Development Act, 2006" in text
    assert "three times" in text and "Bank Rate" in text
    # facts
    assert "10 January 2026" in text  # invoice date
    assert "15 January 2026" in text  # acceptance
    assert "1 March 2026" in text  # appointed day
    assert "201 days" in text or "202 days" in text  # overdue as of AS_OF (19 Sep 2026 -> 202)
    # figures block, Indian grouping
    assert to_inr_string(claim.principal_outstanding) in text  # ₹5,00,000.00
    assert to_inr_string(claim.total_interest) in text
    assert to_inr_string(claim.total_recoverable) in text
    # closing + signature + disclaimer
    assert "Facilitation Council" in text
    assert "MSME" in text and "ODR" in text
    assert "Authorised Signatory" in text
    assert "Estimate only. Not legal advice." in text


def test_breakdown_table_carries_every_row_from_the_claim(business):
    inv = _invoice()
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=AS_OF)
    _, text = _text(render_demand_notice(business, inv, claim, as_of=AS_OF))
    assert len(claim.breakdown) >= 7
    for row in claim.breakdown:
        assert to_inr_string(row.interest_for_period) in text
        assert to_inr_string(row.closing_balance) in text
    assert "16.50%" in text


def test_disclaimer_and_page_numbers_on_every_page_of_a_long_notice(business):
    # ~4 years overdue -> 40+ rows -> multiple pages.
    inv = _invoice(invoice_date="2026-01-10", acceptance_date="2026-01-15")
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=date(2030, 3, 1))
    pages, _ = _text(render_demand_notice(business, inv, claim, as_of=date(2030, 3, 1)))
    assert len(pages) >= 2
    for i, page in enumerate(pages, 1):
        assert "Estimate only. Not legal advice." in page
        assert f"Page {i} of {len(pages)}" in page


def test_omits_gstin_when_absent_and_includes_prose_when_given(business):
    inv = _invoice(buyer_gstin=None, buyer_name="Ravi Traders")
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=AS_OF)
    _, text = _text(render_demand_notice(business, inv, claim, as_of=AS_OF, prose="Despite three reminders by email, no payment has been received."))
    assert "GSTIN" not in text
    assert "Ravi Traders" in text
    assert "Despite three reminders by email" in text


def test_not_yet_overdue_renders_without_a_table(business):
    inv = _invoice(invoice_date="2026-09-01", acceptance_date="2026-09-05")
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=AS_OF)
    assert claim.total_interest == 0
    _, text = _text(render_demand_notice(business, inv, claim, as_of=AS_OF))
    assert "no statutory interest has accrued" in text.lower()
    assert to_inr_string(Decimal("0")) in text


def test_part_payment_is_stated(business):
    inv = _invoice(amount="100000", amount_paid="40000", status="partially_paid")
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=AS_OF, amount_paid=inv.amount_paid)
    _, text = _text(render_demand_notice(business, inv, claim, as_of=AS_OF))
    assert "₹40,000.00" in text
    assert "₹60,000.00" in text


def test_figures_are_the_claims_figures_not_recomputed(business, monkeypatch):
    """If the renderer did arithmetic, a doctored ClaimResult would not round-trip."""
    from dataclasses import replace

    inv = _invoice()
    claim = compute_claim(inv.amount, inv.acceptance_date, None, as_of=AS_OF)
    doctored = replace(claim, total_recoverable=Decimal("999999.99"), total_interest=Decimal("123.45"))
    _, text = _text(render_demand_notice(business, inv, doctored, as_of=AS_OF))
    assert "₹9,99,999.99" in text
    assert "₹123.45" in text
