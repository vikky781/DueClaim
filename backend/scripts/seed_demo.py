"""Seed a realistic demo portfolio for one Cognito user, straight into DynamoDB.

Standalone (not a route). Uses the same models and store as the API, so what
it writes is exactly what the API would have written. Dates are relative to
today so the portfolio stays fresh whenever the demo is recorded.

    cd backend
    venv/Scripts/python scripts/seed_demo.py --sub <cognito-sub> [--table dueclaim-dev] [--replace]

--replace deletes the user's existing invoices first (the business profile is
always upserted). Credentials/region come from the usual AWS environment.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")  # the rupee sign on a Windows console

import boto3  # noqa: E402

from app.models import Business, Invoice, InvoiceStatus  # noqa: E402
from app.store import DynamoStore  # noqa: E402
from dueclaim.engine import compute_claim  # noqa: E402
from dueclaim.money import to_inr_string  # noqa: E402

BUSINESS = Business(
    udyam_number="UDYAM-MH-18-0012345",
    legal_name="Sharma Precision Tools",
    address="Plot 12, MIDC Bhosari, Pune 411026, Maharashtra",
    email="accounts@sharmatools.in",
    enterprise_category="micro",
)


def _plan(today: date) -> list[dict]:
    """Six invoices, four buyers. Acceptance dates are days-ago offsets from ``today``."""
    d = lambda days_ago: today - timedelta(days=days_ago)  # noqa: E731
    return [
        # Acme: the big one, ~9.5 months overdue, corporate -> 43B(h) exposed.
        # NOTE: the RBI rate table currently starts 2025-12-06, so accrual cannot
        # begin before that; 330 days ago is the oldest the engine will accept
        # today. Push this out once historical rates are in dueclaim/rates.py.
        dict(
            invoice_number="SPT/25-26/0142", buyer_name="Acme Industries Pvt Ltd", buyer_gstin="27AAPFU0939F1ZV",
            buyer_is_corporate=True, invoice_date=d(335), acceptance_date=d(330), agreed_credit_days=None,
            amount="850000.00", amount_paid="0", status=InvoiceStatus.unpaid,
        ),
        # Acme again: partially paid.
        dict(
            invoice_number="SPT/25-26/0287", buyer_name="Acme Industries Pvt Ltd", buyer_gstin="27AAPFU0939F1ZV",
            buyer_is_corporate=True, invoice_date=d(154), acceptance_date=d(150), agreed_credit_days=30,
            amount="240000.00", amount_paid="90000.00", status=InvoiceStatus.partially_paid,
        ),
        # Ravi Traders: sole proprietor, no 43B(h) leverage, no GSTIN on file.
        dict(
            invoice_number="SPT/25-26/0201", buyer_name="Ravi Traders", buyer_gstin=None,
            buyer_is_corporate=False, invoice_date=d(203), acceptance_date=d(200), agreed_credit_days=None,
            amount="80000.00", amount_paid="0", status=InvoiceStatus.unpaid,
        ),
        # Meridian Textiles: recently overdue, corporate.
        dict(
            invoice_number="SPT/26-27/0031", buyer_name="Meridian Textiles Ltd", buyer_gstin="24AADCM7392Q1ZK",
            buyer_is_corporate=True, invoice_date=d(64), acceptance_date=d(60), agreed_credit_days=None,
            amount="420000.00", amount_paid="0", status=InvoiceStatus.unpaid,
        ),
        # Meridian again: not yet overdue (inside the 45-day window).
        dict(
            invoice_number="SPT/26-27/0058", buyer_name="Meridian Textiles Ltd", buyer_gstin="24AADCM7392Q1ZK",
            buyer_is_corporate=True, invoice_date=d(33), acceptance_date=d(30), agreed_credit_days=None,
            amount="160000.00", amount_paid="0", status=InvoiceStatus.unpaid,
        ),
        # Kohinoor: small, settled in full -> counted, excluded from accruals.
        dict(
            invoice_number="SPT/25-26/0176", buyer_name="Kohinoor Auto Components LLP", buyer_gstin="27AAEFK4410B1ZC",
            buyer_is_corporate=True, invoice_date=d(253), acceptance_date=d(250), agreed_credit_days=None,
            amount="45000.00", amount_paid="45000.00", status=InvoiceStatus.paid,
        ),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sub", required=True, help="Cognito user sub to seed for")
    ap.add_argument("--table", default="dueclaim-dev")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--replace", action="store_true", help="delete the user's existing invoices first")
    args = ap.parse_args()

    store = DynamoStore(args.table, resource=boto3.resource("dynamodb", region_name=args.region))
    today = datetime.now(timezone.utc).date()

    if args.replace:
        existing = store.list_invoices(args.sub)
        for inv in existing:
            store.delete_invoice(args.sub, inv.id)
        print(f"removed {len(existing)} existing invoice(s)")

    store.put_business(args.sub, BUSINESS)
    print(f"business: {BUSINESS.legal_name} ({BUSINESS.udyam_number})")

    now = datetime.now(timezone.utc)
    total_principal = total_interest = Decimal(0)
    for i, spec in enumerate(_plan(today)):
        inv = Invoice(id=uuid4().hex, created_at=now - timedelta(minutes=len(_plan(today)) - i), **spec)
        # Compute first, exactly as POST /invoices does: an invoice the engine
        # cannot price (rate table too short) must never reach the table.
        claim = compute_claim(inv.amount, inv.acceptance_date, inv.agreed_credit_days, as_of=today, amount_paid=inv.amount_paid)
        store.put_invoice(args.sub, inv)
        if inv.status != InvoiceStatus.paid:
            total_principal += claim.principal_outstanding
            total_interest += claim.total_interest
        exposed = inv.status != InvoiceStatus.paid and inv.buyer_is_corporate and claim.days_overdue > 0
        flag = "43B(h)" if exposed else "      "
        print(
            f"  {inv.invoice_number:<16} {inv.buyer_name:<30} {inv.status.value:<14} "
            f"{claim.days_overdue:>4}d  {flag}  {to_inr_string(claim.total_recoverable):>16}"
        )
    print(f"\nopen principal {to_inr_string(total_principal)}  +  interest {to_inr_string(total_interest)}"
          f"  =  recoverable {to_inr_string(total_principal + total_interest)}  (as of {today})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
