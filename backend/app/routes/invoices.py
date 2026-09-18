"""/api/v1 — invoices, business profile, portfolio summary.

Interest is ALWAYS recomputed by ``dueclaim.engine`` as of today at read time.
Nothing here reads a stored interest figure, because none is stored. Money
leaves this module as 2dp strings via ``dueclaim.money`` — the single
quantization point.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from dueclaim.engine import ClaimResult, RestPeriod, compute_claim
from dueclaim.money import to_paise_string as money

from ..auth import get_current_user_sub
from ..models import Business, Invoice, InvoiceCreate, InvoicePatch, InvoiceStatus
from ..store import Store, get_store, normalize_buyer_name

DISCLAIMER = (
    "Estimate only. Not legal advice. Verify Udyam registration status and the date of "
    "acceptance of goods/services before relying on these figures."
)

router = APIRouter(prefix="/api/v1")


def get_today() -> date:
    """Dependency so tests can pin the as-of date."""
    return datetime.now(timezone.utc).date()


# --- response schemas (money as strings, quantized once) ---------------------


class ClaimSummary(BaseModel):
    as_of: date
    appointed_day: date
    days_overdue: int
    principal_outstanding: str
    total_interest: str
    total_recoverable: str


class RestPeriodRead(BaseModel):
    period_start: date
    period_end: date
    days: int
    annual_rate_applied: str
    accrual_basis: str
    interest_for_period: str
    closing_balance: str
    is_capitalised: bool


class InvoiceRead(BaseModel):
    id: str
    invoice_number: str
    buyer_name: str
    buyer_gstin: str | None
    buyer_is_corporate: bool
    invoice_date: date
    acceptance_date: date
    agreed_credit_days: int | None
    amount: str
    amount_paid: str
    status: InvoiceStatus
    created_at: datetime
    claim: ClaimSummary


class InvoiceDetail(InvoiceRead):
    breakdown: list[RestPeriodRead]


class BuyerSummary(BaseModel):
    buyer_name: str
    principal: str
    interest: str
    oldest_days_overdue: int
    section_43bh_exposed: bool


class PortfolioSummary(BaseModel):
    as_of: date
    total_principal_outstanding: str
    total_statutory_interest: str
    total_recoverable: str
    interest_accruing_per_day: str
    invoice_count: int
    overdue_count: int
    per_buyer: list[BuyerSummary]
    disclaimer: str


# --- helpers -----------------------------------------------------------------


def _claim_for(inv: Invoice, as_of: date) -> ClaimResult:
    return compute_claim(
        principal=inv.amount,
        acceptance_date=inv.acceptance_date,
        agreed_credit_days=inv.agreed_credit_days,
        as_of=as_of,
        amount_paid=inv.amount_paid,
    )


def _claim_summary(claim: ClaimResult, as_of: date) -> ClaimSummary:
    return ClaimSummary(
        as_of=as_of,
        appointed_day=claim.appointed_day,
        days_overdue=claim.days_overdue,
        principal_outstanding=money(claim.principal_outstanding),
        total_interest=money(claim.total_interest),
        total_recoverable=money(claim.total_recoverable),
    )


def _row(p: RestPeriod) -> RestPeriodRead:
    return RestPeriodRead(
        period_start=p.period_start,
        period_end=p.period_end,
        days=p.days,
        annual_rate_applied=money(p.annual_rate_applied),
        accrual_basis=money(p.accrual_basis),
        interest_for_period=money(p.interest_for_period),
        closing_balance=money(p.closing_balance),
        is_capitalised=p.is_capitalised,
    )


def _invoice_fields(inv: Invoice) -> dict:
    return {
        **inv.model_dump(exclude={"amount", "amount_paid"}),
        "amount": money(inv.amount),
        "amount_paid": money(inv.amount_paid),
    }


def _read(inv: Invoice, as_of: date) -> InvoiceRead:
    claim = _claim_for(inv, as_of)
    return InvoiceRead(**_invoice_fields(inv), claim=_claim_summary(claim, as_of))


def _detail(inv: Invoice, as_of: date) -> InvoiceDetail:
    claim = _claim_for(inv, as_of)
    return InvoiceDetail(
        **_invoice_fields(inv),
        claim=_claim_summary(claim, as_of),
        breakdown=[_row(p) for p in claim.breakdown],
    )


def _get_or_404(store: Store, sub: str, invoice_id: str) -> Invoice:
    inv = store.get_invoice(sub, invoice_id)
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return inv


# --- invoices ----------------------------------------------------------------


@router.post("/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> InvoiceRead:
    inv = Invoice(id=uuid4().hex, created_at=datetime.now(timezone.utc), **payload.model_dump())
    # Compute first: if the rate table cannot cover this invoice we refuse it
    # (422 via the BankRateUnavailableError handler) rather than persist it.
    read = _read(inv, today)
    store.put_invoice(sub, inv)
    return read


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> list[InvoiceRead]:
    invoices = sorted(store.list_invoices(sub), key=lambda i: (i.invoice_date, i.created_at))
    return [_read(inv, today) for inv in invoices]


AS_OF_QUERY = Query(
    default=None,
    description="Compute the claim as of this date (YYYY-MM-DD) instead of today. "
    "Passed to the engine unchanged; nothing else differs.",
)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(
    invoice_id: str,
    as_of: date | None = AS_OF_QUERY,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> InvoiceDetail:
    return _detail(_get_or_404(store, sub, invoice_id), as_of or today)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
def patch_invoice(
    invoice_id: str,
    patch: InvoicePatch,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> InvoiceRead:
    inv = _get_or_404(store, sub, invoice_id)
    changes = patch.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Nothing to update")
    try:
        updated = inv.model_copy(update=changes)
        Invoice.model_validate(updated.model_dump())  # re-run amount_paid <= amount check
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    store.put_invoice(sub, updated)
    return _read(updated, today)


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: str,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
) -> Response:
    if not store.delete_invoice(sub, invoice_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- business ----------------------------------------------------------------


@router.post("/business", response_model=Business)
def upsert_business(
    payload: Business,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
) -> Business:
    store.put_business(sub, payload)
    return payload


@router.get("/business", response_model=Business)
def get_business(
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
) -> Business:
    biz = store.get_business(sub)
    if biz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not set")
    return biz


# --- portfolio ---------------------------------------------------------------


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(
    as_of: date | None = AS_OF_QUERY,
    sub: str = Depends(get_current_user_sub),
    store: Store = Depends(get_store),
    today: date = Depends(get_today),
) -> PortfolioSummary:
    """Aggregate claim position across all open invoices, as of ``as_of`` (default today).

    Invoices with ``status == paid`` count toward ``invoice_count`` but are
    excluded from every accrual figure and from ``per_buyer``.
    ``interest_accruing_per_day`` is the exact engine delta between
    total_recoverable as of today and as of tomorrow — not a rate x balance
    approximation, so it is correct across rest boundaries and rate changes.
    """
    today = as_of or today
    invoices = store.list_invoices(sub)
    open_invoices = [i for i in invoices if i.status != InvoiceStatus.paid]
    tomorrow = today + timedelta(days=1)

    total_principal = Decimal(0)
    total_interest = Decimal(0)
    recoverable_today = Decimal(0)
    recoverable_tomorrow = Decimal(0)
    overdue = 0
    buyers: dict[str, dict] = {}

    for inv in open_invoices:
        claim = _claim_for(inv, today)
        total_principal += claim.principal_outstanding
        total_interest += claim.total_interest
        recoverable_today += claim.total_recoverable
        recoverable_tomorrow += _claim_for(inv, tomorrow).total_recoverable
        if claim.days_overdue > 0:
            overdue += 1

        key = normalize_buyer_name(inv.buyer_name)
        b = buyers.setdefault(
            key,
            {
                "buyer_name": inv.buyer_name,
                "principal": Decimal(0),
                "interest": Decimal(0),
                "oldest_days_overdue": 0,
                "section_43bh_exposed": False,
            },
        )
        b["principal"] += claim.principal_outstanding
        b["interest"] += claim.total_interest
        b["oldest_days_overdue"] = max(b["oldest_days_overdue"], claim.days_overdue)
        b["section_43bh_exposed"] = b["section_43bh_exposed"] or (
            inv.buyer_is_corporate and claim.days_overdue > 0
        )

    per_buyer = sorted(buyers.values(), key=lambda b: b["principal"] + b["interest"], reverse=True)
    return PortfolioSummary(
        as_of=today,
        total_principal_outstanding=money(total_principal),
        total_statutory_interest=money(total_interest),
        total_recoverable=money(recoverable_today),
        interest_accruing_per_day=money(recoverable_tomorrow - recoverable_today),
        invoice_count=len(invoices),
        overdue_count=overdue,
        per_buyer=[
            BuyerSummary(
                buyer_name=b["buyer_name"],
                principal=money(b["principal"]),
                interest=money(b["interest"]),
                oldest_days_overdue=b["oldest_days_overdue"],
                section_43bh_exposed=b["section_43bh_exposed"],
            )
            for b in per_buyer
        ],
        disclaimer=DISCLAIMER,
    )
