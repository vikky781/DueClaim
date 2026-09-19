"""Statutory demand notice PDF.

Pure rendering: takes a Business, an Invoice, a ClaimResult and an optional
prose block, returns PDF bytes. Every figure is taken from the ClaimResult and
formatted with ``dueclaim.money``; nothing is recomputed here. There is no
LLM anywhere in this path — the notice is a deterministic template.

Layout follows the conventions of an Indian legal notice: sender block,
date, addressee, subject line naming the invoice and the statute, numbered
paragraphs of facts / demand / statutory basis, a figures block, the full
month-by-month statement of interest as a bordered table, closing, signature,
and the mandatory disclaimer in the footer of every page.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dueclaim.engine import ClaimResult
from dueclaim.money import to_inr_string

from .models import Business, Invoice

DISCLAIMER = (
    "Estimate only. Not legal advice. Verify Udyam registration status and the date of acceptance "
    "of goods/services before relying on these figures."
)

_FONT_DIR = Path(__file__).parent / "fonts"
SERIF, SERIF_BOLD, MONO = "DejaVuSerif", "DejaVuSerif-Bold", "DejaVuSansMono"
_registered = False


def _register_fonts() -> None:
    """DejaVu carries the rupee glyph (U+20B9); reportlab's built-in Helvetica does not."""
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont(SERIF, str(_FONT_DIR / "DejaVuSerif.ttf")))
    pdfmetrics.registerFont(TTFont(SERIF_BOLD, str(_FONT_DIR / "DejaVuSerif-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(MONO, str(_FONT_DIR / "DejaVuSansMono.ttf")))
    pdfmetrics.registerFontFamily(SERIF, normal=SERIF, bold=SERIF_BOLD, italic=SERIF, boldItalic=SERIF_BOLD)
    _registered = True


def _long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _short_date(d: date) -> str:
    return f"{d.day:02d} {d.strftime('%b %Y')}"


_INK = colors.HexColor("#111111")
_RULE = colors.HexColor("#888888")
_SHADE = colors.HexColor("#F2EFE9")

_BODY = ParagraphStyle("body", fontName=SERIF, fontSize=10.5, leading=15, alignment=TA_JUSTIFY, textColor=_INK)
_SMALL = ParagraphStyle("small", parent=_BODY, fontSize=9, leading=12.5, alignment=0)
_RIGHT = ParagraphStyle("right", parent=_SMALL, alignment=TA_RIGHT)
_H = ParagraphStyle("h", fontName=SERIF_BOLD, fontSize=13, leading=17, textColor=_INK, spaceAfter=2)
_SUBJECT = ParagraphStyle("subject", fontName=SERIF_BOLD, fontSize=10.5, leading=15, textColor=_INK)
_LABEL = ParagraphStyle("label", fontName=SERIF, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
_NUM = ParagraphStyle("num", parent=_BODY, leftIndent=18, firstLineIndent=-18, spaceAfter=6)
_MONO = ParagraphStyle("mono", fontName=MONO, fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=_INK)
_MONO_L = ParagraphStyle("monol", parent=_MONO, alignment=0)
_MONO_BIG = ParagraphStyle("monobig", parent=_MONO, fontSize=11, leading=14)
_MONO_TOTAL = ParagraphStyle("monototal", parent=_MONO, fontSize=12.5, leading=16)
_TH = ParagraphStyle("th", fontName=SERIF_BOLD, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=_INK)
_TH_L = ParagraphStyle("thl", parent=_TH, alignment=0)


def _p(text: str, style: ParagraphStyle = _BODY) -> Paragraph:
    return Paragraph(text, style)


def _money(d: Decimal) -> str:
    return to_inr_string(d)


def render_demand_notice(
    business: Business,
    invoice: Invoice,
    claim: ClaimResult,
    as_of: date,
    prose: str | None = None,
) -> bytes:
    """Return the demand notice as PDF bytes. ``as_of`` is the date the claim figures were computed for."""
    _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=24 * mm,
        title=f"Demand notice — Invoice {invoice.invoice_number}",
        author=business.legal_name,
        subject="Demand for payment with statutory interest under the MSMED Act, 2006",
    )
    e = escape
    story: list = []

    # ---- Sender block --------------------------------------------------------
    story.append(_p(e(business.legal_name), _H))
    story.append(_p(e(business.address), _SMALL))
    story.append(
        _p(
            f"Udyam Registration No. {e(business.udyam_number)} &nbsp;·&nbsp; "
            f"{e(business.enterprise_category.value.capitalize())} enterprise &nbsp;·&nbsp; {e(business.email)}",
            _SMALL,
        )
    )
    story.append(Spacer(1, 6))
    story.append(_hr())
    story.append(Spacer(1, 10))

    # ---- Date, mode, addressee ---------------------------------------------
    story.append(_p(f"Date: {_long_date(as_of)}", _RIGHT))
    story.append(_p("By Registered Post A.D. / Email", _SMALL))
    story.append(Spacer(1, 8))
    story.append(_p("To,", _BODY))
    story.append(_p(f"<b>{e(invoice.buyer_name)}</b>", _BODY))
    if invoice.buyer_gstin:
        story.append(_p(f"GSTIN: {e(invoice.buyer_gstin)}", _SMALL))
    story.append(Spacer(1, 12))

    # ---- Subject -------------------------------------------------------------
    story.append(
        _p(
            f"<u>Subject: Demand for payment of {_money(claim.total_recoverable)} against Invoice No. "
            f"{e(invoice.invoice_number)} dated {_long_date(invoice.invoice_date)}, together with statutory "
            f"interest under Section 16 of the Micro, Small and Medium Enterprises Development Act, 2006</u>",
            _SUBJECT,
        )
    )
    story.append(Spacer(1, 10))
    story.append(_p("Dear Sir / Madam,", _BODY))
    story.append(Spacer(1, 6))

    # ---- Numbered paragraphs -------------------------------------------------
    overdue = claim.days_overdue
    credit = (
        f"an agreed credit period of {invoice.agreed_credit_days} days"
        if invoice.agreed_credit_days
        else "no credit period agreed in writing"
    )
    paras: list[str] = [
        # 1. Facts
        f"We, <b>{e(business.legal_name)}</b>, are a {e(business.enterprise_category.value)} enterprise registered "
        f"under the Micro, Small and Medium Enterprises Development Act, 2006 (“the Act”) bearing Udyam "
        f"Registration No. {e(business.udyam_number)}. We supplied goods/services to you under Invoice No. "
        f"<b>{e(invoice.invoice_number)}</b> dated <b>{_long_date(invoice.invoice_date)}</b> for "
        f"<b>{_money(invoice.amount)}</b>. The goods/services were accepted by you on "
        f"<b>{_long_date(invoice.acceptance_date)}</b>.",
        # 2. Appointed day
        f"Under <b>Section 15</b> of the Act, with {credit}, payment fell due on the appointed day, "
        f"<b>{_long_date(claim.appointed_day)}</b>, being not later than forty-five days from the day of acceptance.",
    ]
    if invoice.amount_paid > 0:
        paras.append(
            f"Against the invoice you have paid <b>{_money(invoice.amount_paid)}</b>, leaving a principal sum of "
            f"<b>{_money(claim.principal_outstanding)}</b> outstanding."
        )
    if overdue > 0:
        paras.append(
            f"As on {_long_date(as_of)} the principal sum of <b>{_money(claim.principal_outstanding)}</b> remains "
            f"unpaid, <b>{overdue} days</b> after the appointed day."
        )
    else:
        paras.append(
            f"As on {_long_date(as_of)} the appointed day has not yet passed and no statutory interest has accrued. "
            f"This notice records the sum falling due."
        )
    if prose:
        paras.append(e(prose))
    paras += [
        # Statutory basis
        f"Under <b>Section 16</b> of the Act, where a buyer fails to make payment as required under Section 15, the "
        f"buyer is liable to pay compound interest with monthly rests, from the appointed day, at <b>three times the "
        f"Bank Rate</b> notified by the Reserve Bank of India. This liability arises notwithstanding anything contained "
        f"in any agreement between us or in any law for the time being in force, and under <b>Section 24</b> the "
        f"provisions of Sections 15 to 23 have effect notwithstanding anything inconsistent in any other law.",
        # Demand
        f"We therefore call upon you to pay the total sum of <b>{_money(claim.total_recoverable)}</b>, comprising the "
        f"principal of {_money(claim.principal_outstanding)} and statutory interest of {_money(claim.total_interest)} "
        f"computed up to {_long_date(as_of)} as set out below, within <b>fifteen (15) days</b> of receipt of this "
        f"notice. Interest continues to accrue under Section 16 until the date of actual payment.",
    ]
    for i, text in enumerate(paras, 1):
        story.append(_p(f"{i}.&nbsp;&nbsp;{text}", _NUM))

    # ---- Figures block -------------------------------------------------------
    story.append(Spacer(1, 8))
    fig = Table(
        [
            [_p("Principal outstanding", _BODY), _p(_money(claim.principal_outstanding), _MONO_BIG)],
            [_p(f"Statutory interest under s.16, to {_short_date(as_of)}", _BODY), _p(_money(claim.total_interest), _MONO_BIG)],
            [_p("<b>Total recoverable</b>", _BODY), _p(_money(claim.total_recoverable), _MONO_TOTAL)],
        ],
        colWidths=[110 * mm, 56 * mm],
        hAlign="LEFT",
    )
    fig.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, _INK),
                ("LINEABOVE", (0, 2), (-1, 2), 0.8, _INK),
                ("BACKGROUND", (0, 2), (-1, 2), _SHADE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(KeepTogether([fig]))
    story.append(Spacer(1, 14))

    # ---- Statement of interest ----------------------------------------------
    story.append(_p("Statement of statutory interest under Section 16", _SUBJECT))
    story.append(
        _p(
            f"Compound interest with monthly rests from the appointed day, {_long_date(claim.appointed_day)}, at three "
            f"times the RBI Bank Rate in force; interest for each period = accrual basis × rate × days ÷ 365; the "
            f"interest of each completed month is capitalised and becomes the accrual basis of the next; the final "
            f"partial period is simple and not capitalised. Computed as of {_long_date(as_of)}.",
            _SMALL,
        )
    )
    story.append(Spacer(1, 6))

    if claim.breakdown:
        head = [
            _p("From", _TH_L), _p("To", _TH_L), _p("Days", _TH), _p("Rate p.a.", _TH),
            _p("Accrual basis", _TH), _p("Interest", _TH), _p("Closing balance", _TH), _p("Cap.", _TH),
        ]  # fmt: skip
        rows = [head]
        for r in claim.breakdown:
            rows.append(
                [
                    _p(_short_date(r.period_start), _MONO_L),
                    _p(_short_date(r.period_end), _MONO_L),
                    _p(str(r.days), _MONO),
                    _p(f"{r.annual_rate_applied}%", _MONO),
                    _p(_money(r.accrual_basis), _MONO),
                    _p(_money(r.interest_for_period), _MONO),
                    _p(_money(r.closing_balance), _MONO),
                    _p("✓" if r.is_capitalised else "–", _MONO),
                ]
            )
        rows.append(
            [
                _p("<b>Total</b>", _TH_L), "", "", "", "",
                _p(f"<b>{_money(claim.total_interest)}</b>", _MONO),
                _p(f"<b>{_money(claim.total_recoverable)}</b>", _MONO),
                "",
            ]
        )  # fmt: skip
        tbl = Table(
            rows,
            colWidths=[24 * mm, 24 * mm, 12 * mm, 15 * mm, 27 * mm, 25 * mm, 28 * mm, 11 * mm],
            repeatRows=1,
            hAlign="LEFT",
        )
        tbl.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, _RULE),
                    ("BOX", (0, 0), (-1, -1), 0.8, _INK),
                    ("BACKGROUND", (0, 0), (-1, 0), _SHADE),
                    ("BACKGROUND", (0, -1), (-1, -1), _SHADE),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.8, _INK),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(tbl)
        story.append(
            _p(
                f'<font name="{MONO}">✓</font> marks a completed rest period whose closing balance is capitalised. '
                "Bank Rate source: Reserve Bank of India.",
                _LABEL,
            )
        )
    else:
        story.append(_p(f"No statutory interest has accrued as of {_long_date(as_of)}: {_money(Decimal(0))}.", _BODY))

    # ---- Closing -------------------------------------------------------------
    story.append(Spacer(1, 14))
    closing = [
        _p(
            "Should the amount not be received within the period stated, we reserve the right, without further "
            "notice, to refer the dispute to the <b>Micro and Small Enterprises Facilitation Council</b> under "
            "Section 18 of the Act through the <b>MSME Samadhaan / ODR portal</b>, and to pursue all other remedies "
            "available in law, at your risk as to costs. You are further advised that under Section 43B(h) of the "
            "Income-tax Act, 1961 the sum payable to us is not deductible in your hands until actually paid.",
            _BODY,
        ),
        Spacer(1, 6),
        _p("This notice is issued without prejudice to our rights and contentions.", _BODY),
        Spacer(1, 26),
        _p(f"For <b>{e(business.legal_name)}</b>", _BODY),
        Spacer(1, 30),
        _p("______________________________", _BODY),
        _p("Authorised Signatory", _BODY),
        _p(f"{e(business.email)}", _SMALL),
    ]
    story.append(KeepTogether(closing))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer, canvasmaker=_NumberedCanvas)
    return buf.getvalue()


def _hr():
    t = Table([[""]], colWidths=[166 * mm], rowHeights=[1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, _INK)]))
    return t


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(SERIF, 7.5)
    canvas.setFillColor(colors.HexColor("#555555"))
    width = A4[0] - doc.leftMargin - doc.rightMargin
    # Wrap the disclaimer manually at ~ the text width.
    words, lines, cur = DISCLAIMER.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if pdfmetrics.stringWidth(trial, SERIF, 7.5) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    y = 12 * mm
    for line in reversed(lines):
        canvas.drawString(doc.leftMargin, y, line)
        y += 9.5
    canvas.restoreState()


class _NumberedCanvas:
    """Canvas maker that writes 'Page X of Y' once the total is known."""

    def __init__(self, *args, **kwargs):
        from reportlab.pdfgen import canvas as _c

        self._canvas = _c.Canvas(*args, **kwargs)
        self._saved: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._canvas, name)

    def showPage(self):
        self._saved.append(dict(self._canvas.__dict__))
        self._canvas._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self._canvas.__dict__.update(state)
            self._canvas.setFont(SERIF, 7.5)
            self._canvas.setFillColor(colors.HexColor("#555555"))
            self._canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"Page {self._canvas._pageNumber} of {total}")
            self._canvas.showPage()
        self._canvas.save()
