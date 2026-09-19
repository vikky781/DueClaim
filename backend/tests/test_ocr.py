"""Parsers and Textract mapping for the OCR accelerator. Extraction proposes; it never guesses."""

from decimal import Decimal

import pytest

from app.ocr import map_expense_document, parse_amount, parse_date

# --- amounts -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("5,00,000.00", "500000.00"),
        ("5,00,000", "500000.00"),
        ("Rs. 1,23,456.78", "123456.78"),
        ("Rs 1,23,456.78", "123456.78"),
        ("INR 5,00,000/-", "500000.00"),
        ("₹ 5,00,000.00", "500000.00"),
        ("₹5,00,000", "500000.00"),
        ("Total: 12,345.00", "12345.00"),
        ("12345", "12345.00"),
        ("1234.5", "1234.50"),
        ("  1,85,500.50  ", "185500.50"),
        ("Rs.80,000.00 /-", "80000.00"),
        ("Rs. 80,000.00 Only", "80000.00"),
        ("$ 1,234.00", "1234.00"),  # symbol is ignored; the number is what it is
        ("0.01", "0.01"),
    ],
)
def test_parse_amount_accepts_indian_formats(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "Total",
        "N/A",
        "1,234.567",  # more than paise
        "12,34,567.8.9",
        "1,000 and 2,000",  # two numbers: ambiguous
        "Subtotal 1,000 Tax 180",  # two numbers
        "-500.00",  # negative
        "0",  # not a claimable amount
        "0.00",
        "1.234.567,89",  # European grouping: refuse rather than reinterpret
        "5,00,000.00 5,00,000.00",  # repeated
    ],
)
def test_parse_amount_returns_none_rather_than_guessing(raw):
    assert parse_amount(raw) is None


def test_parse_amount_returns_decimal_never_float():
    assert isinstance(parse_amount("1,23,456.78"), Decimal)


# --- dates -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("15/01/2026", "2026-01-15"),
        ("15-01-2026", "2026-01-15"),
        ("15.01.2026", "2026-01-15"),
        ("2026-01-15", "2026-01-15"),
        ("15 Jan 2026", "2026-01-15"),
        ("15-Jan-2026", "2026-01-15"),
        ("15 January 2026", "2026-01-15"),
        ("January 15, 2026", "2026-01-15"),
        ("Jan 15, 2026", "2026-01-15"),
        ("15th January 2026", "2026-01-15"),
        ("Date: 15/01/2026", "2026-01-15"),
        ("Invoice Date 15/01/2026", "2026-01-15"),
        ("15/01/26", "2026-01-15"),  # two-digit year: 20yy by convention
        ("01/02/2026", "2026-02-01"),  # DD/MM, the Indian convention, never MM/DD
        ("29/02/2028", "2028-02-29"),  # leap day
        ("2 Sept 2026", "2026-09-02"),
        ("2 Sep 2026", "2026-09-02"),
    ],
)
def test_parse_date_accepts_indian_formats(raw, expected):
    assert parse_date(raw).isoformat() == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "Date",
        "03/15/2026",  # month 15 under DD/MM: refuse, do not swap to MM/DD
        "31/02/2026",  # not a real date
        "29/02/2026",  # not a leap year
        "15/01/1026",  # implausible year
        "15/13/2026",
        "2026",
        "15/01",
        "15/01/2026 and 16/01/2026",  # two dates: ambiguous
        "1/2/3",
    ],
)
def test_parse_date_returns_none_rather_than_guessing(raw):
    assert parse_date(raw) is None


# --- Textract mapping --------------------------------------------------------


def _field(type_text: str, value: str, confidence: float, label: str | None = None) -> dict:
    f = {
        "Type": {"Text": type_text, "Confidence": 99.0},
        "ValueDetection": {"Text": value, "Confidence": confidence},
    }
    if label:
        f["LabelDetection"] = {"Text": label, "Confidence": 95.0}
    return f


def _response(summary_fields: list[dict]) -> dict:
    return {"ExpenseDocuments": [{"ExpenseIndex": 1, "SummaryFields": summary_fields, "LineItemGroups": []}]}


def test_maps_summary_fields_with_confidence():
    resp = _response(
        [
            _field("INVOICE_RECEIPT_ID", "INV-2026-0142", 97.5),
            _field("INVOICE_RECEIPT_DATE", "15/01/2026", 92.1),
            _field("RECEIVER_NAME", "Acme Industries Pvt Ltd", 88.0),
            _field("VENDOR_NAME", "Sharma Precision Tools", 99.0),
            _field("TOTAL", "Rs. 5,00,000.00", 96.3),
        ]
    )
    out = map_expense_document(resp)
    assert out.invoice_number.value == "INV-2026-0142"
    assert out.invoice_number.confidence == 97.5
    assert out.invoice_date.value == "2026-01-15"
    assert out.invoice_date.raw == "15/01/2026"
    assert out.invoice_date.confidence == 92.1
    assert out.buyer_name.value == "Acme Industries Pvt Ltd"  # RECEIVER preferred over VENDOR
    assert out.buyer_name.confidence == 88.0
    assert out.amount.value == "500000.00"
    assert out.amount.raw == "Rs. 5,00,000.00"
    assert out.amount.confidence == 96.3


def test_buyer_falls_back_to_vendor_name_when_no_receiver():
    out = map_expense_document(_response([_field("VENDOR_NAME", "Ravi Traders", 90.0)]))
    assert out.buyer_name.value == "Ravi Traders"
    assert out.buyer_name.source == "VENDOR_NAME"


def test_unparseable_values_come_back_null_but_keep_raw_and_confidence():
    out = map_expense_document(
        _response([_field("INVOICE_RECEIPT_DATE", "Date", 40.0), _field("TOTAL", "Subtotal 1,000 Tax 180", 70.0)])
    )
    assert out.invoice_date.value is None
    assert out.invoice_date.raw == "Date"
    assert out.invoice_date.confidence == 40.0
    assert out.amount.value is None
    assert out.amount.raw == "Subtotal 1,000 Tax 180"


def test_missing_fields_are_null_and_empty_documents_do_not_crash():
    out = map_expense_document({"ExpenseDocuments": []})
    assert out.invoice_number.value is None
    assert out.invoice_number.confidence is None
    assert out.amount.value is None
    out2 = map_expense_document(_response([]))
    assert out2.buyer_name.value is None


def test_highest_confidence_wins_when_textract_repeats_a_field():
    out = map_expense_document(
        _response([_field("TOTAL", "1,000.00", 60.0), _field("TOTAL", "5,00,000.00", 91.0), _field("TOTAL", "999", 30.0)])
    )
    assert out.amount.value == "500000.00"
    assert out.amount.confidence == 91.0


def test_mapping_never_invents_acceptance_date():
    out = map_expense_document(_response([_field("INVOICE_RECEIPT_DATE", "15/01/2026", 99.0)]))
    assert not hasattr(out, "acceptance_date")


def test_prefers_highest_confidence_reading_that_parses():
    # Seen on a real invoice: Textract tags the amount-in-words line as TOTAL too,
    # at a higher confidence than the numeric total.
    out = map_expense_document(
        _response([_field("TOTAL", "Rupees Five Lakh Only", 99.95), _field("TOTAL", "Rs. 5,00,000.00", 99.1)])
    )
    assert out.amount.value == "500000.00"
    assert out.amount.raw == "Rs. 5,00,000.00"
    assert out.amount.confidence == 99.1


def test_when_no_reading_parses_keep_the_top_raw_for_the_user():
    out = map_expense_document(_response([_field("TOTAL", "Rupees Five Lakh Only", 99.95), _field("TOTAL", "Total", 40.0)]))
    assert out.amount.value is None
    assert out.amount.raw == "Rupees Five Lakh Only"
    assert out.amount.confidence == 99.95


def test_preference_order_between_types_still_applies_before_parseability():
    # RECEIVER_NAME present -> used even though VENDOR_NAME has higher confidence.
    out = map_expense_document(_response([_field("VENDOR_NAME", "Sharma Precision Tools", 99.9), _field("RECEIVER_NAME", "Acme", 70.0)]))
    assert out.buyer_name.value == "Acme"
