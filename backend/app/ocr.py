"""OCR accelerator: Textract AnalyzeExpense -> proposed invoice fields.

Everything here is pure and defensive. Extraction PROPOSES values for the
manual form; it never writes to the store and never guesses: a field that
cannot be parsed unambiguously comes back as ``None`` with the raw text and
Textract's confidence attached, so the user can decide.

Conventions for Indian invoices:
* Dates are DD/MM/YYYY (or DD-MM-YYYY, DD.MM.YYYY). A date that only makes
  sense as MM/DD is rejected rather than reinterpreted. Two-digit years are
  read as 20yy.
* Amounts use lakh/crore grouping (5,00,000.00) with optional "Rs.", "Rs",
  "INR", "₹" prefixes and "/-" or "Only" suffixes. Grouping commas are
  stripped; a European decimal comma is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dueclaim.money import quantize_money

# --- amounts -----------------------------------------------------------------

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")  # no bare ".50": totals start with a digit


def parse_amount(raw: str | None) -> Decimal | None:
    """'Rs. 1,23,456.78' -> Decimal('123456.78'); None when not exactly one positive paise-precision number."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if re.search(r"(?<![\d,])-\s*\d", text):
        return None  # negative
    candidates = _NUMBER.findall(text)
    if len(candidates) != 1:
        return None  # zero or several numbers: ambiguous
    token = candidates[0]
    if token.count(".") > 1:
        return None
    # A comma used as a decimal separator (European) shows up as a group of
    # exactly 1 or 2 digits after the last comma with no dot: refuse.
    if "," in token:
        head, _, tail = token.rpartition(",")
        if not re.fullmatch(r"\d{3}(\.\d+)?", tail):
            return None  # last comma is not a thousands separator
        if "." in head:
            return None  # dots before commas: '1.234.567,89' style
    digits = token.replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    if value.as_tuple().exponent < -2:
        return None  # finer than paise: not a real invoice total
    return quantize_money(value)


# --- dates -------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}  # fmt: skip

_NUMERIC = re.compile(r"(?<!\d)(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})(?!\d)")
_DMY_TEXT = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})[\s\-,]+(\d{4})(?!\d)")
_MDY_TEXT = re.compile(r"(?<![A-Za-z])([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)")


def _mk(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    if not (1990 <= y <= 2100):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(raw: str | None) -> date | None:
    """Indian-convention date text -> date; None unless exactly one unambiguous date is present."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    found: list[date | None] = []

    for m in _NUMERIC.finditer(text):
        a, b, c = m.groups()
        if len(a) == 4:  # ISO: YYYY-MM-DD
            found.append(_mk(int(a), int(b), int(c)) if len(c) <= 2 else None)
        else:  # DD/MM/YY(YY)
            found.append(_mk(int(c), int(b), int(a)) if len(c) in (2, 4) else None)
    for m in _DMY_TEXT.finditer(text):
        d, mon, y = m.groups()
        month = _MONTHS.get(mon.lower())
        found.append(_mk(int(y), month, int(d)) if month else None)
    for m in _MDY_TEXT.finditer(text):
        mon, d, y = m.groups()
        month = _MONTHS.get(mon.lower())
        if month:
            found.append(_mk(int(y), month, int(d)))

    if len(found) != 1:
        return None  # nothing, or more than one date-shaped thing
    return found[0]


# --- Textract mapping --------------------------------------------------------


@dataclass(frozen=True)
class ExtractedField:
    value: str | None  # normalised: ISO date, 2dp amount, or trimmed text
    confidence: float | None  # Textract ValueDetection confidence, 0-100
    raw: str | None  # exactly what Textract read
    source: str | None  # Textract summary field type used


@dataclass(frozen=True)
class ExtractedInvoice:
    invoice_number: ExtractedField
    invoice_date: ExtractedField
    buyer_name: ExtractedField
    amount: ExtractedField
    fields_seen: list[str] = field(default_factory=list)


_EMPTY = ExtractedField(None, None, None, None)


def _best(fields: dict[str, list[tuple[str, float]]], normalise, *types: str) -> ExtractedField:
    """First type (in preference order) with any reading, then within it the
    highest-confidence reading that PARSES. Textract often tags several lines
    with the same type (e.g. the amount-in-words line as TOTAL); a reading that
    normalises to a value beats a higher-confidence one that does not. If none
    parse, the top raw reading is returned with ``value=None`` so the user can
    still see what was read."""
    for t in types:
        readings = fields.get(t)
        if not readings:
            continue
        ranked = sorted(readings, key=lambda rc: rc[1], reverse=True)
        for raw, conf in ranked:
            value = normalise(raw)
            if value is not None:
                return ExtractedField(value=value, confidence=conf, raw=raw, source=t)
        raw, conf = ranked[0]
        return ExtractedField(value=None, confidence=conf, raw=raw, source=t)
    return _EMPTY


def map_expense_document(response: dict[str, Any]) -> ExtractedInvoice:
    fields: dict[str, list[tuple[str, float]]] = {}
    for doc in response.get("ExpenseDocuments", []) or []:
        for f in doc.get("SummaryFields", []) or []:
            type_text = (f.get("Type") or {}).get("Text")
            value = (f.get("ValueDetection") or {}).get("Text")
            conf = (f.get("ValueDetection") or {}).get("Confidence")
            if not type_text or value is None:
                continue
            fields.setdefault(type_text, []).append((value.strip(), float(conf or 0.0)))

    return ExtractedInvoice(
        invoice_number=_best(fields, lambda s: s or None, "INVOICE_RECEIPT_ID"),
        invoice_date=_best(fields, lambda s: (d.isoformat() if (d := parse_date(s)) else None), "INVOICE_RECEIPT_DATE"),
        buyer_name=_best(fields, lambda s: s or None, "RECEIVER_NAME", "VENDOR_NAME"),
        amount=_best(fields, lambda s: (str(a) if (a := parse_amount(s)) is not None else None), "TOTAL"),
        fields_seen=sorted(fields),
    )
