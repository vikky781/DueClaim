from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.routes.invoices import get_today
from dueclaim.engine import compute_claim
from dueclaim.money import to_paise_string
from tests.conftest import TODAY, business_payload, invoice_payload

API = "/api/v1"
DISCLAIMER = (
    "Estimate only. Not legal advice. Verify Udyam registration status and the date of "
    "acceptance of goods/services before relying on these figures."
)


# --- health / auth plumbing --------------------------------------------------


def test_health_is_public_and_needs_no_auth():
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_invoices_without_identity_is_401(monkeypatch):
    monkeypatch.delenv("DEV_USER_SUB", raising=False)
    with TestClient(app) as c:
        assert c.get(f"{API}/invoices").status_code == 401


# --- invoices CRUD -----------------------------------------------------------


def test_create_invoice_returns_claim_computed_as_of_today(client):
    r = client.post(f"{API}/invoices", json=invoice_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"]
    assert body["invoice_number"] == "INV-001"
    assert body["amount"] == "500000.00"
    assert body["amount_paid"] == "0.00"
    assert body["status"] == "unpaid"
    assert body["created_at"]
    claim = body["claim"]
    assert claim["as_of"] == "2026-09-18"
    assert claim["appointed_day"] == "2026-03-01"
    assert claim["days_overdue"] == 201
    assert claim["principal_outstanding"] == "500000.00"
    assert claim["total_interest"] == "47230.62"
    assert claim["total_recoverable"] == "547230.62"
    assert "breakdown" not in body  # list/create views are summaries


def test_create_invoice_rejects_invalid_payloads(client):
    assert client.post(f"{API}/invoices", json=invoice_payload(amount="0")).status_code == 422
    assert client.post(f"{API}/invoices", json=invoice_payload(amount="10", amount_paid="11")).status_code == 422
    assert client.post(f"{API}/invoices", json=invoice_payload(buyer_gstin="BAD")).status_code == 422


def test_create_invoice_before_rate_table_is_422_and_not_persisted(client):
    r = client.post(
        f"{API}/invoices",
        json=invoice_payload(invoice_date="2025-01-01", acceptance_date="2025-01-05"),
    )
    assert r.status_code == 422
    assert "Bank Rate" in r.json()["detail"]
    assert client.get(f"{API}/invoices").json() == []


def test_list_invoices_returns_only_current_users_invoices(client, as_other_user):
    client.post(f"{API}/invoices", json=invoice_payload(invoice_number="A-1"))
    client.post(f"{API}/invoices", json=invoice_payload(invoice_number="A-2"))
    as_other_user.post(f"{API}/invoices", json=invoice_payload(invoice_number="B-1"))
    mine = client.get(f"{API}/invoices").json()
    assert sorted(i["invoice_number"] for i in mine) == ["A-1", "A-2"]
    theirs = as_other_user.get(f"{API}/invoices").json()
    assert [i["invoice_number"] for i in theirs] == ["B-1"]


def test_get_invoice_includes_full_breakdown_that_reconciles(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    r = client.get(f"{API}/invoices/{inv_id}")
    assert r.status_code == 200
    body = r.json()
    rows = body["breakdown"]
    assert len(rows) == 7
    first, last = rows[0], rows[-1]
    assert first["period_start"] == "2026-03-02"
    assert first["period_end"] == "2026-04-01"
    assert first["days"] == 31
    assert first["annual_rate_applied"] == "16.50"
    assert first["accrual_basis"] == "500000.00"
    assert first["interest_for_period"] == "7006.85"
    assert first["closing_balance"] == "507006.85"
    assert first["is_capitalised"] is True
    assert last["is_capitalised"] is False
    assert last["closing_balance"] == body["claim"]["total_recoverable"] == "547230.62"


def test_get_invoice_of_other_user_or_unknown_is_404(client, as_other_user):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    assert as_other_user.get(f"{API}/invoices/{inv_id}").status_code == 404
    assert client.get(f"{API}/invoices/does-not-exist").status_code == 404


def test_interest_is_recomputed_at_read_time_not_stored(client, store):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    today_interest = client.get(f"{API}/invoices/{inv_id}").json()["claim"]["total_interest"]
    app.dependency_overrides[get_today] = lambda: TODAY + timedelta(days=30)
    later = client.get(f"{API}/invoices/{inv_id}").json()["claim"]
    assert later["as_of"] == "2026-10-18"
    assert Decimal(later["total_interest"]) > Decimal(today_interest)
    # Nothing interest-related was persisted on the stored record.
    stored = store.get_invoice("user-sub-aaa", inv_id)
    assert not hasattr(stored, "total_interest")
    assert not hasattr(stored, "claim")


def test_patch_amount_paid_reduces_principal_and_recomputes(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    r = client.patch(f"{API}/invoices/{inv_id}", json={"amount_paid": "200000", "status": "partially_paid"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount_paid"] == "200000.00"
    assert body["status"] == "partially_paid"
    assert body["claim"]["principal_outstanding"] == "300000.00"
    expected = compute_claim(Decimal("300000"), date(2026, 1, 15), None, as_of=TODAY)
    assert body["claim"]["total_interest"] == to_paise_string(expected.total_interest)


def test_patch_rejects_amount_paid_above_amount(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload(amount="1000")).json()["id"]
    r = client.patch(f"{API}/invoices/{inv_id}", json={"amount_paid": "1000.01"})
    assert r.status_code == 422
    assert client.get(f"{API}/invoices/{inv_id}").json()["amount_paid"] == "0.00"


def test_patch_unknown_invoice_is_404(client):
    assert client.patch(f"{API}/invoices/nope", json={"status": "paid"}).status_code == 404


def test_delete_invoice(client, as_other_user):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    assert as_other_user.delete(f"{API}/invoices/{inv_id}").status_code == 404
    assert client.delete(f"{API}/invoices/{inv_id}").status_code == 204
    assert client.get(f"{API}/invoices/{inv_id}").status_code == 404
    assert client.delete(f"{API}/invoices/{inv_id}").status_code == 404


# --- business ----------------------------------------------------------------


def test_business_get_before_set_is_404_then_round_trips(client):
    assert client.get(f"{API}/business").status_code == 404
    r = client.post(f"{API}/business", json=business_payload())
    assert r.status_code == 200, r.text
    assert r.json()["udyam_number"] == "UDYAM-MH-18-0012345"
    assert client.get(f"{API}/business").json() == business_payload()
    # POST again overwrites
    client.post(f"{API}/business", json=business_payload(legal_name="Sharma Tools LLP"))
    assert client.get(f"{API}/business").json()["legal_name"] == "Sharma Tools LLP"


def test_business_rejects_bad_category(client):
    assert client.post(f"{API}/business", json=business_payload(enterprise_category="huge")).status_code == 422


# --- portfolio summary -------------------------------------------------------


def test_portfolio_summary_empty(client):
    r = client.get(f"{API}/portfolio/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["invoice_count"] == 0
    assert body["overdue_count"] == 0
    assert body["total_recoverable"] == "0.00"
    assert body["interest_accruing_per_day"] == "0.00"
    assert body["per_buyer"] == []
    assert body["disclaimer"] == DISCLAIMER


def test_portfolio_summary_aggregates_and_flags_43bh(client):
    # Acme (corporate), two overdue invoices, one partially paid.
    client.post(f"{API}/invoices", json=invoice_payload(invoice_number="A-1", amount="500000"))
    client.post(
        f"{API}/invoices",
        json=invoice_payload(
            invoice_number="A-2", buyer_name="acme industries pvt ltd", amount="100000",
            amount_paid="40000", acceptance_date="2026-05-10", status="partially_paid",
        ),
    )
    # Ravi (individual proprietor, not corporate), overdue -> no 43B(h) flag.
    client.post(
        f"{API}/invoices",
        json=invoice_payload(
            invoice_number="R-1", buyer_name="Ravi Traders", buyer_gstin=None,
            buyer_is_corporate=False, amount="80000", acceptance_date="2026-06-01",
        ),
    )
    # Zed (corporate) but not yet overdue -> counted, zero interest, not exposed.
    client.post(
        f"{API}/invoices",
        json=invoice_payload(
            invoice_number="Z-1", buyer_name="Zed Corp", amount="20000",
            invoice_date="2026-09-01", acceptance_date="2026-09-05",
        ),
    )
    # Fully paid -> excluded from accrual aggregates, still counted.
    client.post(
        f"{API}/invoices",
        json=invoice_payload(
            invoice_number="P-1", buyer_name="Paid Co", amount="5000", amount_paid="5000",
            acceptance_date="2026-02-01", status="paid",
        ),
    )

    body = client.get(f"{API}/portfolio/summary").json()

    a1 = compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=TODAY)
    a2 = compute_claim(Decimal("100000"), date(2026, 5, 10), None, as_of=TODAY, amount_paid=Decimal("40000"))
    r1 = compute_claim(Decimal("80000"), date(2026, 6, 1), None, as_of=TODAY)
    z1 = compute_claim(Decimal("20000"), date(2026, 9, 5), None, as_of=TODAY)
    assert z1.total_interest == 0

    total_principal = Decimal("500000") + Decimal("60000") + Decimal("80000") + Decimal("20000")
    total_interest = a1.total_interest + a2.total_interest + r1.total_interest
    assert body["invoice_count"] == 5
    assert body["overdue_count"] == 3
    assert body["total_principal_outstanding"] == to_paise_string(total_principal)
    assert body["total_statutory_interest"] == to_paise_string(total_interest)
    assert body["total_recoverable"] == to_paise_string(total_principal + total_interest)

    # Per-day accrual is the exact engine delta between today and tomorrow.
    tomorrow = TODAY + timedelta(days=1)
    delta = Decimal(0)
    for principal, acc, paid in [
        (Decimal("500000"), date(2026, 1, 15), Decimal(0)),
        (Decimal("100000"), date(2026, 5, 10), Decimal("40000")),
        (Decimal("80000"), date(2026, 6, 1), Decimal(0)),
        (Decimal("20000"), date(2026, 9, 5), Decimal(0)),
    ]:
        delta += (
            compute_claim(principal, acc, None, as_of=tomorrow, amount_paid=paid).total_recoverable
            - compute_claim(principal, acc, None, as_of=TODAY, amount_paid=paid).total_recoverable
        )
    assert delta > 0
    assert body["interest_accruing_per_day"] == to_paise_string(delta)

    by_name = {b["buyer_name"]: b for b in body["per_buyer"]}
    assert set(by_name) == {"Acme Industries Pvt Ltd", "Ravi Traders", "Zed Corp"}
    acme = by_name["Acme Industries Pvt Ltd"]  # both spellings grouped under first-seen name
    assert acme["principal"] == "560000.00"
    assert acme["interest"] == to_paise_string(a1.total_interest + a2.total_interest)
    assert acme["oldest_days_overdue"] == 201
    assert acme["section_43bh_exposed"] is True
    ravi = by_name["Ravi Traders"]
    assert ravi["oldest_days_overdue"] == r1.days_overdue > 0
    assert ravi["section_43bh_exposed"] is False  # not corporate
    zed = by_name["Zed Corp"]
    assert zed["oldest_days_overdue"] == 0
    assert zed["interest"] == "0.00"
    assert zed["section_43bh_exposed"] is False  # corporate but not overdue
    assert body["disclaimer"] == DISCLAIMER


# --- ?as_of= override --------------------------------------------------------


def test_invoice_detail_as_of_flows_into_engine_unchanged(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    r = client.get(f"{API}/invoices/{inv_id}", params={"as_of": "2026-10-18"})
    assert r.status_code == 200, r.text
    body = r.json()
    expected = compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=date(2026, 10, 18))
    assert body["claim"]["as_of"] == "2026-10-18"
    assert body["claim"]["days_overdue"] == expected.days_overdue == 231
    assert body["claim"]["total_interest"] == to_paise_string(expected.total_interest)
    assert len(body["breakdown"]) == len(expected.breakdown) == 8
    assert body["breakdown"][-1]["period_end"] == "2026-10-18"


def test_invoice_detail_as_of_before_appointed_day_gives_zero(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    body = client.get(f"{API}/invoices/{inv_id}", params={"as_of": "2026-02-01"}).json()
    assert body["claim"]["as_of"] == "2026-02-01"
    assert body["claim"]["days_overdue"] == 0
    assert body["claim"]["total_interest"] == "0.00"
    assert body["breakdown"] == []


def test_invoice_detail_without_as_of_still_uses_today(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    assert client.get(f"{API}/invoices/{inv_id}").json()["claim"]["as_of"] == "2026-09-18"


def test_invalid_as_of_is_422(client):
    inv_id = client.post(f"{API}/invoices", json=invoice_payload()).json()["id"]
    assert client.get(f"{API}/invoices/{inv_id}", params={"as_of": "18/09/2026"}).status_code == 422
    assert client.get(f"{API}/portfolio/summary", params={"as_of": "not-a-date"}).status_code == 422


def test_portfolio_summary_as_of_shifts_every_figure(client):
    client.post(f"{API}/invoices", json=invoice_payload(invoice_number="A-1", amount="500000"))
    client.post(
        f"{API}/invoices",
        json=invoice_payload(invoice_number="R-1", buyer_name="Ravi Traders", amount="80000",
                             acceptance_date="2026-06-01", buyer_is_corporate=False),
    )
    as_of = date(2026, 12, 31)
    body = client.get(f"{API}/portfolio/summary", params={"as_of": as_of.isoformat()}).json()
    assert body["as_of"] == "2026-12-31"

    a = compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=as_of)
    r = compute_claim(Decimal("80000"), date(2026, 6, 1), None, as_of=as_of)
    assert body["total_statutory_interest"] == to_paise_string(a.total_interest + r.total_interest)
    assert body["total_recoverable"] == to_paise_string(a.total_recoverable + r.total_recoverable)
    # Per-day accrual is relative to the requested date, not to today.
    nxt = as_of + timedelta(days=1)
    delta = (
        compute_claim(Decimal("500000"), date(2026, 1, 15), None, as_of=nxt).total_recoverable
        + compute_claim(Decimal("80000"), date(2026, 6, 1), None, as_of=nxt).total_recoverable
        - a.total_recoverable - r.total_recoverable
    )
    assert body["interest_accruing_per_day"] == to_paise_string(delta)
    by_name = {b["buyer_name"]: b for b in body["per_buyer"]}
    assert by_name["Acme Industries Pvt Ltd"]["oldest_days_overdue"] == a.days_overdue == 305
    assert by_name["Ravi Traders"]["oldest_days_overdue"] == r.days_overdue
    # Today's figures are different, proving the override took effect.
    today_body = client.get(f"{API}/portfolio/summary").json()
    assert today_body["as_of"] == "2026-09-18"
    assert Decimal(today_body["total_statutory_interest"]) < Decimal(body["total_statutory_interest"])
