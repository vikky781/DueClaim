"""POST /api/v1/invoices/{id}/notice — generate the statutory demand notice PDF.

Recomputes the claim as of today (or ?as_of), renders the deterministic
template in app.notice, writes the PDF to s3://<bucket>/notices/{sub}/…,
records the generation on the invoice item and returns a one-hour presigned
GET URL together with the figures the notice was generated against.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dueclaim.money import to_paise_string as money

from ..auth import get_current_user_sub
from ..models import NoticeRecord
from ..notice import render_demand_notice
from ..store import Store, get_store
from .invoices import AS_OF_QUERY, _claim_for, _get_or_404, get_today
from .uploads import UploadsBackend, get_uploads_backend

router = APIRouter(prefix="/api/v1/invoices")

NOTICE_URL_TTL_SECONDS = 3600


class NoticeResponse(BaseModel):
    url: str
    key: str
    expires_in: int
    generated_at: datetime
    as_of: date
    appointed_day: date
    days_overdue: int
    principal_outstanding: str
    total_interest: str
    total_recoverable: str
    notices_generated: int


@router.post("/{invoice_id}/notice", response_model=NoticeResponse)
def generate_notice(
    invoice_id: str,
    as_of: date | None = AS_OF_QUERY,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    backend: UploadsBackend = Depends(get_uploads_backend),
    today: date = Depends(get_today),
) -> NoticeResponse:
    inv = _get_or_404(store, sub, invoice_id)
    business = store.get_business(sub)
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set up your business profile before generating a notice; it identifies the sender.",
        )
    as_of = as_of or today
    claim = _claim_for(inv, as_of)
    pdf = render_demand_notice(business, inv, claim, as_of=as_of)

    generated_at = datetime.now(timezone.utc)
    key = f"notices/{sub}/{inv.id}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.pdf"
    backend.put_object(key, pdf, "application/pdf")
    url = backend.presign_get(key, NOTICE_URL_TTL_SECONDS)

    record = NoticeRecord(
        key=key,
        generated_at=generated_at,
        as_of=as_of,
        principal_outstanding=claim.principal_outstanding,
        total_interest=claim.total_interest,
        total_recoverable=claim.total_recoverable,
    )
    updated = inv.model_copy(update={"notices": [*inv.notices, record]})
    store.put_invoice(sub, updated)

    return NoticeResponse(
        url=url,
        key=key,
        expires_in=NOTICE_URL_TTL_SECONDS,
        generated_at=generated_at,
        as_of=as_of,
        appointed_day=claim.appointed_day,
        days_overdue=claim.days_overdue,
        principal_outstanding=money(claim.principal_outstanding),
        total_interest=money(claim.total_interest),
        total_recoverable=money(claim.total_recoverable),
        notices_generated=len(updated.notices),
    )
