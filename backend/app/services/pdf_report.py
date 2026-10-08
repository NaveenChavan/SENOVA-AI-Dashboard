"""SENOVA dual financial PDF report generator.

There are deliberately two report products:

1. Visual Financial Report - one landscape A4 page, executive/dashboard style.
2. Detailed Financial Report - multi-page portrait A4, audit-friendly tables.

Both are presentation layers over the same analytics objects. This module does
not invent business numbers or create a second financial calculation engine.
"""

from datetime import datetime
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

from app.models.schemas import AnalyticsResponse, CAReportSummary

# Font setup: Register TTF font for true ₹ unicode glyph support
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

for _p_reg, _p_bold in [
    (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
]:
    if _p_reg.exists() and _p_bold.exists():
        try:
            pdfmetrics.registerFont(TTFont("ReportFont", str(_p_reg)))
            pdfmetrics.registerFont(TTFont("ReportFont-Bold", str(_p_bold)))
            _FONT_REGULAR = "ReportFont"
            _FONT_BOLD = "ReportFont-Bold"
            break
        except Exception:
            pass

_HAS_RUPEE = (_FONT_REGULAR == "ReportFont")
_CURR = "₹" if _HAS_RUPEE else "Rs. "

# Kept for backwards compatibility with callers that import this symbol.
# The PDF report itself now includes the full filtered ledger rather than a
# hidden 500-row cap. Extremely large datasets should still use the paginated
# in-app ledger for browsing; the export remains complete for the selected slice.
MAX_LEDGER_ROWS_IN_PDF = 0

_BRAND_BLUE = colors.HexColor("#0b5ed7")
_NAVY = colors.HexColor("#0b1f3a")
_DARK_TEXT = colors.HexColor("#132238")
_MUTED_TEXT = colors.HexColor("#64748b")
_BORDER = colors.HexColor("#d8e2ee")
_PANEL = colors.HexColor("#f7fbff")
_ROW_ALT = colors.HexColor("#f2f6fb")
_GREEN = colors.HexColor("#079669")
_RED = colors.HexColor("#d92d20")
_AMBER = colors.HexColor("#b7791f")
_WHITE = colors.white


def _fmt_money(amount: float) -> str:
    return f"{_CURR}{amount:,.2f}"


def _fmt_compact_money(amount: float) -> str:
    amount = float(amount)
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    if value >= 10_000_000:
        return f"{sign}{_CURR}{value / 10_000_000:.2f}Cr"
    if value >= 100_000:
        return f"{sign}{_CURR}{value / 100_000:.2f}L"
    if value >= 1_000:
        return f"{sign}{_CURR}{value / 1_000:.1f}K"
    return f"{sign}{_CURR}{value:,.0f}"


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _safe(value, fallback="-"):
    return fallback if value is None else value


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle2", parent=styles["Title"], fontName=_FONT_BOLD, fontSize=22,
        textColor=_BRAND_BLUE, leading=24, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle2", parent=styles["Normal"], fontName=_FONT_REGULAR, fontSize=9.5,
        textColor=_MUTED_TEXT, leading=12, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading2", parent=styles["Heading2"], fontName=_FONT_BOLD, fontSize=12.5,
        textColor=_DARK_TEXT, leading=15, spaceBefore=12, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallNote2", parent=styles["Normal"], fontName=_FONT_REGULAR, fontSize=7.5,
        textColor=_MUTED_TEXT, leading=9.5,
    ))
    return styles


def _pnl_table(report: CAReportSummary) -> Table:
    rows = [["Particulars", "Amount", "% of Revenue"]]
    subtotal_rows = []
    for i, line in enumerate(report.pnl, start=1):
        pct = _fmt_pct(line.percentage_of_revenue) if line.percentage_of_revenue is not None else "-"
        rows.append([line.label, _fmt_money(line.amount), pct])
        if line.is_subtotal:
            subtotal_rows.append(i)

    table = Table(rows, colWidths=[76 * mm, 52 * mm, 38 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]
    for row in subtotal_rows:
        style += [
            ("FONTNAME", (0, row), (-1, row), _FONT_BOLD),
            ("TEXTCOLOR", (0, row), (-1, row), _BRAND_BLUE),
            ("LINEABOVE", (0, row), (-1, row), 1.1, _DARK_TEXT),
        ]
    table.setStyle(TableStyle(style))
    return table


def _category_ledger_table(report: CAReportSummary) -> Table:
    rows = [["Category", "Units Sold", "Revenue", "Cost", "Profit", "Margin %"]]
    for row in report.category_ledger:
        rows.append([
            row.category,
            f"{row.units_sold:,}",
            _fmt_money(row.revenue),
            _fmt_money(row.cost),
            _fmt_money(row.profit),
            _fmt_pct(row.margin_percentage),
        ])
    table = Table(rows, colWidths=[35 * mm, 24 * mm, 31 * mm, 31 * mm, 31 * mm, 24 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _top_items_table(analytics: AnalyticsResponse) -> Table | None:
    if not analytics.top_items:
        return None
    rows = [["Item", "Units Sold", "Revenue"]]
    for item in analytics.top_items[:5]:
        rows.append([item.name, f"{item.quantity:,}", _fmt_money(item.revenue)])
    table = Table(rows, colWidths=[80 * mm, 34 * mm, 44 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _insights_table(insights) -> Table | None:
    if not insights or not getattr(insights, "insights", None):
        return None
    styles = _build_styles()
    body = ParagraphStyle(name="InsightBody2", parent=styles["Normal"], fontName=_FONT_REGULAR, fontSize=8.2, leading=10.4)
    severity_words = {"critical": "URGENT", "warning": "WATCH", "positive": "GOOD", "neutral": "NOTE"}
    rows = [["Priority", "Finding"]]
    for insight in insights.insights:
        text = f"<b>{insight.title}</b><br/>{insight.message}"
        if insight.action:
            text += f"<br/><i>Suggested action: {insight.action}</i>"
        if not _HAS_RUPEE:
            text = text.replace("₹", "Rs. ")
        rows.append([severity_words.get(insight.severity, "NOTE"), Paragraph(text, body)])
    table = Table(rows, colWidths=[22 * mm, 148 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.35, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _forecast_table(forecast) -> Table | None:
    if not forecast or not getattr(forecast, "available", False):
        return None
    rows = [
        ["Measure", "Value"],
        [f"Expected revenue (next {forecast.horizon_days} days)", _fmt_money(forecast.expected_revenue)],
        [
            "Likely range (80% confidence)",
            f"{_fmt_money(forecast.expected_revenue_lower)} to {_fmt_money(forecast.expected_revenue_upper)}",
        ],
        ["Recent daily average", _fmt_money(forecast.daily_average)],
        ["Trend", f"{forecast.trend_direction.title()} ({_fmt_money(forecast.trend_per_day)} per day)"],
        [
            "Backtest accuracy (last 7 days)",
            f"{forecast.accuracy_pct}%" if forecast.accuracy_pct is not None else "Not enough history to test",
        ],
    ]
    table = Table(rows, colWidths=[90 * mm, 80 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.3),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, _BORDER),
    ]))
    return table


def _reorder_table(inventory) -> Table | None:
    if not inventory or not getattr(inventory, "items", None):
        return None
    stock_aware = bool(getattr(inventory, "stock_aware", False))
    headers = ["Item", "ABC", "Units", "Units/Day", "Idle Days", "Priority"]
    widths = [58 * mm, 12 * mm, 18 * mm, 22 * mm, 20 * mm, 20 * mm]
    if stock_aware:
        headers += ["Stock", "Cover (days)"]
        widths += [18 * mm, 22 * mm]
    rows = [headers]
    for item in inventory.items[:20]:
        row = [
            str(item.item)[:38], str(item.abc_class), f"{item.units_sold:,}",
            f"{item.velocity_per_day:.2f}", str(item.days_since_last_sale), f"{item.reorder_priority:.0f}",
        ]
        if stock_aware:
            row += [
                f"{item.stock_on_hand:,.0f}" if item.stock_on_hand is not None else "-",
                f"{item.days_of_cover:.1f}" if item.days_of_cover is not None else "-",
            ]
        rows.append(row)
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _ledger_table(entries) -> Table:
    headers = ["Date", "Category", "Item", "Qty", "Selling Price", "Cost Price", "Revenue", "Profit"]
    rows = [headers]
    for e in entries:
        rows.append([
            e.date, e.category, e.item, f"{e.quantity:,}",
            _fmt_money(e.selling_price), _fmt_money(e.cost_price),
            _fmt_money(e.revenue), _fmt_money(e.profit),
        ])
    table = Table(
        rows,
        colWidths=[20 * mm, 25 * mm, 35 * mm, 12 * mm, 25 * mm, 25 * mm, 25 * mm, 25 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 7.25),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.3),
        ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _daily_summary_table(daily_summary: list[dict]) -> Table:
    rows = [["Date", "Transactions", "Units Sold", "Revenue", "Cost", "Profit", "Margin %"]]
    for r in daily_summary:
        rows.append([
            r["date"], f"{r['transactions']:,}", f"{r['units_sold']:,}",
            _fmt_money(r["revenue"]), _fmt_money(r["cost"]), _fmt_money(r["profit"]),
            _fmt_pct(r["margin_percentage"]),
        ])
    table = Table(
        rows,
        colWidths=[24 * mm, 28 * mm, 24 * mm, 34 * mm, 34 * mm, 34 * mm, 22 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


def _discount_table(analytics: AnalyticsResponse) -> Table | None:
    metrics = getattr(analytics, "discount_metrics", None)
    items = getattr(analytics, "discount_vs_margin", None) or []
    if not metrics and not items:
        return None
    rows = [["Discount analysis", "Value"]]
    if metrics:
        rows.extend([
            ["Discount given", _fmt_money(metrics.discount_given)],
            ["Average / overall discount", _fmt_pct(metrics.discount_pct)],
            ["Rows with valid MRP", f"{metrics.valid_discount_rows:,}"],
            ["Missing MRP rows", f"{metrics.missing_mrp_rows:,}"],
            ["Price above MRP rows", f"{metrics.price_above_mrp_rows:,}"],
        ])
    if items:
        rows.append(["Top discount/margin signal", f"{items[0].item}: {items[0].discount_pct:.1f}% discount / {items[0].margin_pct:.1f}% margin"])
    table = Table(rows, colWidths=[90 * mm, 80 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _ROW_ALT]),
    ]))
    return table


_DARK_BG = colors.HexColor("#0c192c")
_ACCENT_BLUE = colors.HexColor("#2563eb")
_LIGHT_BLUE = colors.HexColor("#e0f2fe")
_SKY_BAR = colors.HexColor("#38bdf8")
_GREEN_BG = colors.HexColor("#dcfce7")
_GREEN_TEXT = colors.HexColor("#15803d")
_RED_BG = colors.HexColor("#fee2e2")
_RED_TEXT = colors.HexColor("#b91c1c")
_AMBER_BG = colors.HexColor("#fef3c7")
_AMBER_TEXT = colors.HexColor("#b45309")


def _fmt_inr_full(amount: float) -> str:
    """Format full rupee value without decimals, e.g. ₹17,74,788."""
    amt = int(round(float(amount)))
    sign = "-" if amt < 0 else ""
    amt_str = str(abs(amt))
    if len(amt_str) <= 3:
        return f"{sign}{_CURR}{amt_str}"
    last_three = amt_str[-3:]
    remaining = amt_str[:-3]
    chunks = []
    while len(remaining) > 2:
        chunks.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        chunks.insert(0, remaining)
    return f"{sign}{_CURR}{','.join(chunks)},{last_three}"


def _draw_icon(c: canvas.Canvas, x: float, y: float, kind: str):
    """Draw a clean mini vector icon badge."""
    c.setFillColor(_LIGHT_BLUE)
    c.roundRect(x, y, 14, 12, 2.5, stroke=0, fill=1)
    c.setFillColor(_BRAND_BLUE)
    c.setStrokeColor(_BRAND_BLUE)

    if kind == "chart":
        c.rect(x + 2.5, y + 2, 2, 4.5, stroke=0, fill=1)
        c.rect(x + 6, y + 2, 2, 7.5, stroke=0, fill=1)
        c.rect(x + 9.5, y + 2, 2, 6, stroke=0, fill=1)
    elif kind == "trend":
        c.setLineWidth(1.1)
        c.line(x + 2.5, y + 3, x + 6.5, y + 8.5)
        c.line(x + 6.5, y + 8.5, x + 9, y + 5)
        c.line(x + 9, y + 5, x + 11.5, y + 9.5)
        c.setLineWidth(1)
    elif kind == "donut":
        c.circle(x + 7, y + 6, 3.8, stroke=1, fill=0)
    elif kind == "table":
        c.setLineWidth(0.8)
        c.line(x + 2.5, y + 9, x + 11.5, y + 9)
        c.line(x + 2.5, y + 6, x + 11.5, y + 6)
        c.line(x + 2.5, y + 3, x + 11.5, y + 3)
        c.setLineWidth(1)
    elif kind == "badge":
        c.setFont(_FONT_BOLD, 6.5)
        c.drawCentredString(x + 7, y + 3, "#")
    elif kind == "lightning":
        p = c.beginPath()
        p.moveTo(x + 8.5, y + 10)
        p.lineTo(x + 4.5, y + 5.5)
        p.lineTo(x + 7.5, y + 5.5)
        p.lineTo(x + 5.5, y + 2)
        p.lineTo(x + 10.5, y + 6.5)
        p.lineTo(x + 7.5, y + 6.5)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
    elif kind == "target":
        c.circle(x + 7, y + 6, 3.5, stroke=1, fill=0)
        c.circle(x + 7, y + 6, 1.2, stroke=0, fill=1)
    elif kind == "forecast":
        c.setLineWidth(1.1)
        c.line(x + 2.5, y + 4, x + 6.5, y + 5)
        c.line(x + 6.5, y + 5, x + 11.5, y + 8.5)
        c.setLineWidth(1)


def _draw_panel_card(c: canvas.Canvas, x, y, w, h, title: str | None = None, icon_kind: str | None = None):
    c.setFillColor(_PANEL)
    c.setStrokeColor(_BORDER)
    c.roundRect(x, y, w, h, 5, stroke=1, fill=1)
    if title:
        tx = x + 10
        if icon_kind:
            _draw_icon(c, tx, y + h - 17, icon_kind)
            tx += 18
        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_BOLD, 8.8)
        c.drawString(tx, y + h - 14, title)


def _draw_header(c: canvas.Canvas, x, y, w, h, filename: str, ca_report, prepared_date: str):
    c.setFillColor(_DARK_BG)
    c.roundRect(x, y, w, h, 6, stroke=0, fill=1)

    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    logo_path = assets_dir / "logo.png"
    if not logo_path.exists():
        logo_path = assets_dir / "logo.jpeg"
    if not logo_path.exists():
        logo_path = Path(__file__).resolve().parents[3] / "frontend" / "public" / "assets" / "logo.jpeg"

    text_x = x + 12
    if logo_path.exists():
        try:
            c.drawImage(str(logo_path), x + 10, y + 14, 44, 44, mask="auto", preserveAspectRatio=True)
            text_x = x + 62
        except Exception:
            text_x = x + 12

    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 15)
    c.drawString(text_x, y + h - 18, "SENOVA Digital Lab")

    c.setFillColor(colors.HexColor("#93c5fd"))
    c.setFont(_FONT_BOLD, 8.2)
    c.drawString(text_x, y + h - 31, "Business Financial & Performance Report")

    c.setFillColor(colors.HexColor("#cbd5e1"))
    c.setFont(_FONT_REGULAR, 6)
    c.drawString(text_x, y + h - 44, f"Data Source: {filename}")
    c.drawString(text_x, y + h - 55, f"Period: {ca_report.period_label} ({ca_report.period_start} to {ca_report.period_end})")

    c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawString(text_x, y + h - 66, "Currency: INR")

    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont(_FONT_REGULAR, 6)
    c.drawRightString(x + w - 12, y + 21, "Prepared on")
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 7.2)
    c.drawRightString(x + w - 12, y + 10, prepared_date)


def _draw_kpi_row(c: canvas.Canvas, x, y, w, h, analytics, ca_report):
    summary = analytics.summary
    card_w = (w - 3 * 6) / 4
    margin_pct = (float(summary.profit.value) / float(summary.revenue.value) * 100) if summary.revenue.value else 0.0

    kpis = [
        ("Total Revenue", _fmt_inr_full(summary.revenue.value), summary.revenue.trend_percentage, "trend"),
        ("Gross Profit", _fmt_inr_full(summary.profit.value), summary.profit.trend_percentage, "table"),
        ("Profit Margin", f"{margin_pct:.2f}%", summary.profit.trend_percentage, "donut"),
        ("Units Sold", f"{int(summary.units_sold.value):,}", summary.units_sold.trend_percentage, "chart"),
    ]

    for idx, (label, val_str, trend, icon) in enumerate(kpis):
        cx = x + idx * (card_w + 6)
        c.setFillColor(_WHITE)
        c.setStrokeColor(_BORDER)
        c.roundRect(cx, y, card_w, h, 4.5, stroke=1, fill=1)

        _draw_icon(c, cx + 8, y + h - 18, icon)

        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 6.4)
        c.drawString(cx + 26, y + h - 14, label)

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_BOLD, 10.5)
        c.drawString(cx + 8, y + h - 33, val_str)

        if trend is not None:
            sign = "↑" if trend >= 0 else "↓"
            color = _GREEN_TEXT if trend >= 0 else _RED_TEXT
            c.setFillColor(color)
            c.setFont(_FONT_BOLD, 5.8)
            trend_text = f"{sign} {abs(trend):.1f}%"
            c.drawString(cx + 8, y + 9, trend_text)
            c.setFillColor(_MUTED_TEXT)
            c.setFont(_FONT_REGULAR, 5.5)
            tw = stringWidth(trend_text, _FONT_BOLD, 5.8)
            c.drawString(cx + 12 + tw, y + 9, "vs prior period")


def _draw_findings(c: canvas.Canvas, x, y, w, h, insights):
    _draw_panel_card(c, x, y, w, h, "What Changed — Key Findings", "target")
    if not insights or not getattr(insights, "insights", None):
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 7.5)
        c.drawString(x + 12, y + h / 2, "No automated findings available for this period.")
        return

    items = insights.insights[:5]
    row_h = 24.5
    top_y = y + h - 22

    severity_styles = {
        "critical": (_RED_BG, _RED_TEXT, "URGENT"),
        "warning": (_AMBER_BG, _AMBER_TEXT, "WATCH"),
        "positive": (_GREEN_BG, _GREEN_TEXT, "GOOD"),
        "neutral": (colors.HexColor("#f1f5f9"), colors.HexColor("#475569"), "NOTE"),
    }

    for idx, ins in enumerate(items):
        ry = top_y - idx * row_h
        bg_col, txt_col, badge_text = severity_styles.get(ins.severity, severity_styles["neutral"])

        c.setFillColor(bg_col)
        c.roundRect(x + 9, ry - 14, 38, 13, 2.5, stroke=0, fill=1)
        c.setFillColor(txt_col)
        c.setFont(_FONT_BOLD, 6.2)
        c.drawCentredString(x + 28, ry - 9.5, badge_text)

        tag_text = None
        tag_color = txt_col
        tag_bg = bg_col

        title_text = str(ins.title)
        msg_text = str(ins.message)

        if "dropped" in title_text.lower() or "below" in msg_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"-{word.strip('(),')} vs typical"
                    break
        elif "spiked" in title_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"+{word.strip('(),')} vs typical"
                    break
        elif "growing" in title_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"+{word.strip('(),')} growth"
                    break
        elif "losing" in title_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"-{word.strip('(),')} vs previous"
                    break
        elif "discount" in title_text.lower() or "discount" in msg_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"{word.strip('(),')} discount"
                    break
        elif "margin" in title_text.lower() or "margin" in msg_text.lower():
            for word in msg_text.split():
                if "%" in word:
                    tag_text = f"{word.strip('(),')} margin"
                    break

        right_margin = 12
        if tag_text:
            tag_w = max(52, stringWidth(tag_text, _FONT_BOLD, 5.4) + 8)
            bx = x + w - tag_w - 9
            c.setFillColor(tag_bg)
            c.roundRect(bx, ry - 14, tag_w, 13, 2.5, stroke=0, fill=1)
            c.setFillColor(tag_color)
            c.setFont(_FONT_BOLD, 5.4)
            c.drawCentredString(bx + tag_w / 2, ry - 9.5, tag_text)
            right_margin = tag_w + 16

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_BOLD, 7)
        title_max_w = w - 52 - right_margin
        clean_title = title_text
        while stringWidth(clean_title, _FONT_BOLD, 7) > title_max_w and len(clean_title) > 10:
            clean_title = clean_title[:-4] + "…"
        c.drawString(x + 52, ry - 6, clean_title)

        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 5.6)
        clean_msg = msg_text
        while stringWidth(clean_msg, _FONT_REGULAR, 5.6) > title_max_w and len(clean_msg) > 15:
            clean_msg = clean_msg[:-4] + "…"
        c.drawString(x + 52, ry - 14, clean_msg)

        if idx < len(items) - 1:
            c.setStrokeColor(colors.HexColor("#f1f5f9"))
            c.line(x + 9, ry - 17, x + w - 9, ry - 17)


def _draw_pnl_statement(c: canvas.Canvas, x, y, w, h, ca_report):
    _draw_panel_card(c, x, y, w, h, "Profit & Loss Statement", "table")
    tx = x + 9
    ty = y + h - 23
    tw = w - 18

    col_widths = [tw * 0.48, tw * 0.28, tw * 0.24]

    c.setFillColor(_NAVY)
    c.roundRect(tx, ty - 13, tw, 14, 2, stroke=0, fill=1)
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 6.5)
    c.drawString(tx + 6, ty - 9, "Particulars")
    c.drawRightString(tx + col_widths[0] + col_widths[1] - 6, ty - 9, f"Amount ({_CURR})")
    c.drawRightString(tx + tw - 6, ty - 9, "% of Revenue")

    rows = []
    for line in ca_report.pnl:
        if line.label in {"Gross Revenue", "Cost of Goods Sold (COGS)", "Gross Profit"}:
            rows.append(line)

    row_y = ty - 17
    for line in rows:
        is_profit = "Gross Profit" in line.label
        row_h = 13.5
        if is_profit:
            c.setFillColor(_LIGHT_BLUE)
            c.roundRect(tx, row_y - row_h + 3, tw, row_h, 2, stroke=0, fill=1)
            c.setFillColor(_BRAND_BLUE)
            c.setFont(_FONT_BOLD, 6.8)
        else:
            c.setFillColor(_DARK_TEXT)
            c.setFont(_FONT_REGULAR, 6.5)

        c.drawString(tx + 6, row_y - 6, line.label)
        c.drawRightString(tx + col_widths[0] + col_widths[1] - 6, row_y - 6, f"{line.amount:,.2f}")
        pct_str = f"{line.percentage_of_revenue:.2f}%" if line.percentage_of_revenue is not None else "-"
        c.drawRightString(tx + tw - 6, row_y - 6, pct_str)

        row_y -= row_h


def _draw_revenue_profit_trend(c: canvas.Canvas, x, y, w, h, analytics):
    _draw_panel_card(c, x, y, w, h, "Revenue vs Profit", "trend")
    daily = analytics.daily_trend or []
    if not daily:
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 7)
        c.drawString(x + 12, y + h / 2, "No daily trend data available.")
        return

    c.setFillColor(_BRAND_BLUE)
    c.rect(x + w - 68, y + h - 13.5, 7, 2, stroke=0, fill=1)
    c.setFillColor(_DARK_TEXT)
    c.setFont(_FONT_REGULAR, 5.5)
    c.drawString(x + w - 58, y + h - 14.5, "Rev")

    c.setFillColor(_GREEN)
    c.rect(x + w - 36, y + h - 13.5, 7, 2, stroke=0, fill=1)
    c.drawString(x + w - 26, y + h - 14.5, "Profit")

    px = x + 28
    py = y + 18
    pw = w - 36
    ph = h - 42

    rev_vals = [max(0, float(d.revenue)) for d in daily]
    prof_vals = [max(0, float(d.profit)) for d in daily]
    max_val = max(max(rev_vals or [1]), max(prof_vals or [1])) or 1

    c.setStrokeColor(colors.HexColor("#f1f5f9"))
    c.setFont(_FONT_REGULAR, 5.2)
    c.setFillColor(_MUTED_TEXT)
    for i in range(3):
        frac = i / 2
        y_pos = py + ph * frac
        c.line(px, y_pos, px + pw, y_pos)
        tick_val = max_val * frac
        c.drawRightString(px - 3, y_pos - 1.5, _fmt_compact_money(tick_val))

    n = len(daily)
    c.setStrokeColor(_BRAND_BLUE)
    c.setLineWidth(1.4)
    prev = None
    for i, val in enumerate(rev_vals):
        x_pt = px + (pw * i / max(1, n - 1))
        y_pt = py + (ph * val / max_val)
        if prev:
            c.line(prev[0], prev[1], x_pt, y_pt)
        prev = (x_pt, y_pt)

    c.setStrokeColor(_GREEN)
    c.setLineWidth(1.4)
    prev = None
    for i, val in enumerate(prof_vals):
        x_pt = px + (pw * i / max(1, n - 1))
        y_pt = py + (ph * val / max_val)
        if prev:
            c.line(prev[0], prev[1], x_pt, y_pt)
        prev = (x_pt, y_pt)

    c.setLineWidth(1)

    if n > 0:
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 5.2)
        c.drawString(px, py - 9, daily[0].date[5:])
        c.drawCentredString(px + pw / 2, py - 9, daily[n // 2].date[5:])
        c.drawRightString(px + pw, py - 9, daily[-1].date[5:])


def _draw_revenue_mix_donut(c: canvas.Canvas, x, y, w, h, categories):
    _draw_panel_card(c, x, y, w, h, "Revenue Mix by Category", "donut")
    if not categories:
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 7)
        c.drawString(x + 12, y + h / 2, "No category data.")
        return

    cx = x + 50
    cy = y + (h - 20) / 2 + 2
    radius = min(36, (h - 40) / 2)
    hole = radius * 0.55
    total = sum(max(0, float(c.revenue)) for c in categories) or 1.0

    palette = [
        colors.HexColor("#0284c7"),
        colors.HexColor("#10b981"),
        colors.HexColor("#f59e0b"),
        colors.HexColor("#ef4444"),
        colors.HexColor("#8b5cf6"),
        colors.HexColor("#06b6d4"),
    ]

    start = 90
    for i, cat in enumerate(categories[:6]):
        extent = 360 * max(0, float(cat.revenue)) / total
        c.setFillColor(palette[i % len(palette)])
        c.wedge(cx - radius, cy - radius, cx + radius, cy + radius, start, extent, stroke=0, fill=1)
        start -= extent

    c.setFillColor(_WHITE)
    c.circle(cx, cy, hole, stroke=0, fill=1)
    c.setFillColor(_DARK_TEXT)
    c.setFont(_FONT_BOLD, 7)
    c.drawCentredString(cx, cy + 1, _fmt_compact_money(total))
    c.setFillColor(_MUTED_TEXT)
    c.setFont(_FONT_REGULAR, 4.6)
    c.drawCentredString(cx, cy - 6, "Total revenue")

    lx = x + 98
    ly = y + h - 28
    for i, cat in enumerate(categories[:5]):
        row_y = ly - i * 14
        pct = (float(cat.revenue) / total * 100) if total else 0.0
        c.setFillColor(palette[i % len(palette)])
        c.roundRect(lx, row_y - 2, 6, 6, 1.5, stroke=0, fill=1)
        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_BOLD, 6)
        c.drawString(lx + 10, row_y - 1, f"{str(cat.category)[:11]}")
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 5.4)
        c.drawRightString(x + w - 8, row_y - 1, f"{pct:.1f}% · {_fmt_compact_money(cat.revenue)}")


def _draw_daily_revenue_trend(c: canvas.Canvas, x, y, w, h, analytics, ca_report):
    _draw_panel_card(c, x, y, w, h, "Daily Revenue Trend", "chart")
    daily = analytics.daily_trend or []
    if not daily:
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 7.5)
        c.drawString(x + 12, y + h / 2, "No daily revenue data.")
        return

    rev_vals = [max(0, float(d.revenue)) for d in daily]
    avg_rev = (sum(rev_vals) / len(rev_vals)) if rev_vals else 0
    max_val = max(rev_vals or [1]) or 1

    lx = x + w - 162
    c.setFillColor(_SKY_BAR)
    c.roundRect(lx, y + h - 15, 7, 7, 1.5, stroke=0, fill=1)
    c.setFillColor(_MUTED_TEXT)
    c.setFont(_FONT_REGULAR, 5.8)
    c.drawString(lx + 10, y + h - 14, "Daily Revenue")

    c.setStrokeColor(_RED)
    c.setDash([2, 2])
    c.line(lx + 68, y + h - 11, lx + 78, y + h - 11)
    c.setDash()
    c.setFillColor(_RED_TEXT)
    c.drawString(lx + 82, y + h - 14, f"Average ({_fmt_compact_money(avg_rev)})")

    px = x + 38
    py = y + 18
    pw = w - 54
    ph = h - 40

    c.setStrokeColor(colors.HexColor("#f1f5f9"))
    c.setFont(_FONT_REGULAR, 5.2)
    c.setFillColor(_MUTED_TEXT)
    for i in range(4):
        frac = i / 3
        y_pos = py + ph * frac
        c.line(px, y_pos, px + pw, y_pos)
        tick_val = max_val * frac
        c.drawRightString(px - 3, y_pos - 1.5, _fmt_compact_money(tick_val))

    n = len(daily)
    gap = 2.5
    bar_w = max(2.5, (pw - gap * (n - 1)) / n)

    min_idx = 0
    min_val = rev_vals[0] if rev_vals else 0
    for idx, v in enumerate(rev_vals):
        if v < min_val:
            min_val = v
            min_idx = idx

    for i, (d, v) in enumerate(zip(daily, rev_vals)):
        bx = px + i * (bar_w + gap)
        bh = ph * (v / max_val)
        c.setFillColor(_SKY_BAR)
        c.roundRect(bx, py, bar_w, max(1.5, bh), 1, stroke=0, fill=1)

    date_step = max(4, n // 6)
    shown_indices = set(range(0, n, date_step)) | {n - 1}
    if (n - 1) in shown_indices and (n - 2) in shown_indices:
        shown_indices.remove(n - 2)

    for i in sorted(shown_indices):
        bx = px + i * (bar_w + gap)
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 5.2)
        try:
            d_dt = datetime.strptime(daily[i].date, "%Y-%m-%d")
            d_lbl = d_dt.strftime("%d %b")
        except Exception:
            d_lbl = daily[i].date[5:]
        center_x = min(bx + bar_w / 2, x + w - 16)
        c.drawCentredString(center_x, py - 8, d_lbl)

    avg_y = py + ph * (avg_rev / max_val)
    c.setStrokeColor(_RED)
    c.setDash([2, 2])
    c.line(px, avg_y, px + pw, avg_y)
    c.setDash()

    if min_val < avg_rev * 0.7 and n > 5:
        callout_x = px + min_idx * (bar_w + gap) - 15
        callout_x = max(px, min(px + pw - 52, callout_x))
        callout_y = py + ph * (min_val / max_val) + 12
        callout_y = min(py + ph - 22, callout_y)
        callout_w = 50
        callout_h = 20

        c.setFillColor(_RED_BG)
        c.setStrokeColor(colors.HexColor("#fca5a5"))
        c.roundRect(callout_x, callout_y, callout_w, callout_h, 2.5, stroke=1, fill=1)

        try:
            min_dt = datetime.strptime(daily[min_idx].date, "%Y-%m-%d")
            min_d_lbl = min_dt.strftime("%d %b")
        except Exception:
            min_d_lbl = daily[min_idx].date[5:]

        drop_pct = ((min_val - avg_rev) / avg_rev * 100) if avg_rev else 0
        c.setFillColor(_RED_TEXT)
        c.setFont(_FONT_BOLD, 5.2)
        c.drawCentredString(callout_x + callout_w / 2, callout_y + 13.5, min_d_lbl)
        c.setFont(_FONT_BOLD, 5.4)
        c.drawCentredString(callout_x + callout_w / 2, callout_y + 7.5, _fmt_compact_money(min_val))
        c.setFont(_FONT_REGULAR, 4.8)
        c.drawCentredString(callout_x + callout_w / 2, callout_y + 2, f"({drop_pct:.1f}% vs typical)")


def _draw_category_ledger_table(c: canvas.Canvas, x, y, w, h, ca_report):
    _draw_panel_card(c, x, y, w, h, "Category-wise Ledger", "table")
    tx = x + 9
    ty = y + h - 21
    tw = w - 18

    cols = [
        ("Category", tw * 0.28, "left"),
        ("Units Sold", tw * 0.14, "right"),
        (f"Revenue ({_CURR})", tw * 0.17, "right"),
        (f"Cost ({_CURR})", tw * 0.15, "right"),
        (f"Profit ({_CURR})", tw * 0.14, "right"),
        ("Margin %", tw * 0.12, "right"),
    ]

    c.setFillColor(_NAVY)
    c.roundRect(tx, ty - 12, tw, 13, 2, stroke=0, fill=1)
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 6.2)

    cx_cursor = tx
    for name, cw, align in cols:
        if align == "left":
            c.drawString(cx_cursor + 4, ty - 8.5, name)
        else:
            c.drawRightString(cx_cursor + cw - 4, ty - 8.5, name)
        cx_cursor += cw

    rows = ca_report.category_ledger[:4]
    tot_units = sum(r.units_sold for r in ca_report.category_ledger)
    tot_rev = sum(r.revenue for r in ca_report.category_ledger)
    tot_cost = sum(r.cost for r in ca_report.category_ledger)
    tot_prof = sum(r.profit for r in ca_report.category_ledger)
    tot_margin = (tot_prof / tot_rev * 100) if tot_rev else 0.0

    row_y = ty - 14
    row_h = 12
    for idx, r in enumerate(rows):
        if idx % 2 == 1:
            c.setFillColor(_ROW_ALT)
            c.rect(tx, row_y - row_h + 3, tw, row_h, stroke=0, fill=1)

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_REGULAR, 6.2)

        cx_cursor = tx
        c.drawString(cx_cursor + 4, row_y - 5.5, str(r.category)[:16])
        cx_cursor += cols[0][1]

        c.drawRightString(cx_cursor + cols[1][1] - 4, row_y - 5.5, f"{r.units_sold:,}")
        cx_cursor += cols[1][1]

        c.drawRightString(cx_cursor + cols[2][1] - 4, row_y - 5.5, f"{r.revenue:,.2f}")
        cx_cursor += cols[2][1]

        c.drawRightString(cx_cursor + cols[3][1] - 4, row_y - 5.5, f"{r.cost:,.2f}")
        cx_cursor += cols[3][1]

        c.drawRightString(cx_cursor + cols[4][1] - 4, row_y - 5.5, f"{r.profit:,.2f}")
        cx_cursor += cols[4][1]

        c.drawRightString(cx_cursor + cols[5][1] - 4, row_y - 5.5, f"{r.margin_percentage:.2f}%")

        row_y -= row_h

    c.setFillColor(_LIGHT_BLUE)
    c.roundRect(tx, row_y - row_h + 2.5, tw, row_h, 2, stroke=0, fill=1)
    c.setFillColor(_BRAND_BLUE)
    c.setFont(_FONT_BOLD, 6.5)

    cx_cursor = tx
    c.drawString(cx_cursor + 4, row_y - 5.5, "Total")
    cx_cursor += cols[0][1]

    c.drawRightString(cx_cursor + cols[1][1] - 4, row_y - 5.5, f"{tot_units:,}")
    cx_cursor += cols[1][1]

    c.drawRightString(cx_cursor + cols[2][1] - 4, row_y - 5.5, f"{tot_rev:,.2f}")
    cx_cursor += cols[2][1]

    c.drawRightString(cx_cursor + cols[3][1] - 4, row_y - 5.5, f"{tot_cost:,.2f}")
    cx_cursor += cols[3][1]

    c.drawRightString(cx_cursor + cols[4][1] - 4, row_y - 5.5, f"{tot_prof:,.2f}")
    cx_cursor += cols[4][1]

    c.drawRightString(cx_cursor + cols[5][1] - 4, row_y - 5.5, f"{tot_margin:.2f}%")


def _draw_top_items_table(c: canvas.Canvas, x, y, w, h, analytics):
    _draw_panel_card(c, x, y, w, h, "Top 5 Fast-Moving Items", "badge")
    tx = x + 9
    ty = y + h - 21
    tw = w - 18

    cols = [
        ("#", tw * 0.07, "center"),
        ("Item", tw * 0.44, "left"),
        ("Units Sold", tw * 0.27, "left"),
        (f"Revenue ({_CURR})", tw * 0.22, "right"),
    ]

    c.setFillColor(_NAVY)
    c.roundRect(tx, ty - 12, tw, 13, 2, stroke=0, fill=1)
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 6.2)

    cx_cursor = tx
    for name, cw, align in cols:
        if align == "center":
            c.drawCentredString(cx_cursor + cw / 2, ty - 8.5, name)
        elif align == "left":
            c.drawString(cx_cursor + 4, ty - 8.5, name)
        else:
            c.drawRightString(cx_cursor + cw - 4, ty - 8.5, name)
        cx_cursor += cw

    items = (analytics.top_items or [])[:5]
    max_qty = max([float(i.quantity) for i in items] or [1]) or 1

    row_y = ty - 14
    row_h = 12
    for idx, it in enumerate(items, start=1):
        if idx % 2 == 0:
            c.setFillColor(_ROW_ALT)
            c.rect(tx, row_y - row_h + 3, tw, row_h, stroke=0, fill=1)

        cx_cursor = tx
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_BOLD, 6.2)
        c.drawCentredString(cx_cursor + cols[0][1] / 2, row_y - 5.5, str(idx))
        cx_cursor += cols[0][1]

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_REGULAR, 6.2)
        c.drawString(cx_cursor + 4, row_y - 5.5, str(it.name)[:28])
        cx_cursor += cols[1][1]

        bar_col_w = cols[2][1]
        track_w = 42
        c.setFillColor(_LIGHT_BLUE)
        c.roundRect(cx_cursor + 4, row_y - 6.5, track_w, 5.5, 1.5, stroke=0, fill=1)
        fill_w = track_w * (float(it.quantity) / max_qty)
        c.setFillColor(_BRAND_BLUE)
        c.roundRect(cx_cursor + 4, row_y - 6.5, max(2, fill_w), 5.5, 1.5, stroke=0, fill=1)

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_BOLD, 6.2)
        c.drawRightString(cx_cursor + bar_col_w - 6, row_y - 5.5, f"{it.quantity:,}")
        cx_cursor += bar_col_w

        c.drawRightString(cx_cursor + cols[3][1] - 4, row_y - 5.5, f"{it.revenue:,.2f}")

        row_y -= row_h


def _draw_sales_speed_table(c: canvas.Canvas, x, y, w, h, inventory, analytics):
    _draw_panel_card(c, x, y, w, h, "Sales-Speed Ranking (Top 5 by Demand)", "lightning")
    tx = x + 9
    ty = y + h - 21
    tw = w - 18

    cols = [
        ("Item", tw * 0.38, "left"),
        ("ABC", tw * 0.10, "center"),
        ("Units", tw * 0.12, "right"),
        ("Units/Day", tw * 0.14, "right"),
        ("Idle Days", tw * 0.12, "right"),
        ("Priority", tw * 0.14, "center"),
    ]

    c.setFillColor(_NAVY)
    c.roundRect(tx, ty - 12, tw, 13, 2, stroke=0, fill=1)
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 6.2)

    cx_cursor = tx
    for name, cw, align in cols:
        if align == "center":
            c.drawCentredString(cx_cursor + cw / 2, ty - 8.5, name)
        elif align == "left":
            c.drawString(cx_cursor + 4, ty - 8.5, name)
        else:
            c.drawRightString(cx_cursor + cw - 4, ty - 8.5, name)
        cx_cursor += cw

    items = getattr(inventory, "items", [])[:5] if inventory else []
    row_y = ty - 14
    row_h = 12
    for idx, it in enumerate(items):
        if idx % 2 == 1:
            c.setFillColor(_ROW_ALT)
            c.rect(tx, row_y - row_h + 3, tw, row_h, stroke=0, fill=1)

        cx_cursor = tx
        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_REGULAR, 6.2)
        c.drawString(cx_cursor + 4, row_y - 5.5, str(it.item)[:24])
        cx_cursor += cols[0][1]

        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_BOLD, 6.2)
        c.drawCentredString(cx_cursor + cols[1][1] / 2, row_y - 5.5, str(it.abc_class))
        cx_cursor += cols[1][1]

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_REGULAR, 6.2)
        c.drawRightString(cx_cursor + cols[2][1] - 4, row_y - 5.5, f"{it.units_sold:,}")
        cx_cursor += cols[2][1]

        c.drawRightString(cx_cursor + cols[3][1] - 4, row_y - 5.5, f"{it.velocity_per_day:.2f}")
        cx_cursor += cols[3][1]

        c.drawRightString(cx_cursor + cols[4][1] - 4, row_y - 5.5, str(it.days_since_last_sale))
        cx_cursor += cols[4][1]

        prio = float(it.reorder_priority)
        prio_col = cols[5][1]
        pw, ph = 24, 9.5
        px_pos = cx_cursor + (prio_col - pw) / 2
        py_pos = row_y - 6.5

        if prio >= 70:
            c.setFillColor(_GREEN_BG)
            txt_c = _GREEN_TEXT
        elif prio >= 50:
            c.setFillColor(_AMBER_BG)
            txt_c = _AMBER_TEXT
        else:
            c.setFillColor(colors.HexColor("#f1f5f9"))
            txt_c = colors.HexColor("#475569")

        c.roundRect(px_pos, py_pos, pw, ph, 2, stroke=0, fill=1)
        c.setFillColor(txt_c)
        c.setFont(_FONT_BOLD, 5.8)
        c.drawCentredString(px_pos + pw / 2, py_pos + 2.2, f"{prio:.0f}")

        row_y -= row_h


def _draw_revenue_forecast_card(c: canvas.Canvas, x, y, w, h, forecast):
    _draw_panel_card(c, x, y, w, h, "Revenue Forecast (Next 14 Days)", "forecast")
    if not forecast or not getattr(forecast, "available", False):
        c.setFillColor(_MUTED_TEXT)
        c.setFont(_FONT_REGULAR, 7.5)
        c.drawString(x + 12, y + h / 2, "Forecast model unavailable for this data slice.")
        return

    chart_w = 154
    table_w = w - chart_w - 26
    cx = x + 10
    cy = y + 10
    ch = h - 38

    leg_y = y + h - 24
    c.setFillColor(_ACCENT_BLUE)
    c.rect(cx + 8, leg_y, 6, 2, stroke=0, fill=1)
    c.setFillColor(_MUTED_TEXT)
    c.setFont(_FONT_REGULAR, 5.2)
    c.drawString(cx + 16, leg_y - 1, "Historical")

    c.setStrokeColor(_GREEN)
    c.setDash([2, 2])
    c.line(cx + 56, leg_y + 1, cx + 64, leg_y + 1)
    c.setDash()
    c.drawString(cx + 67, leg_y - 1, "Forecast")

    c.setFillColor(_GREEN_BG)
    c.rect(cx + 104, leg_y - 1, 7, 5, stroke=0, fill=1)
    c.drawString(cx + 114, leg_y - 1, "Range (80%)")

    points = getattr(forecast, "points", [])
    if points:
        all_vals = []
        for p in points:
            if getattr(p, "actual", None) is not None:
                all_vals.append(float(p.actual))
            if getattr(p, "forecast", None) is not None:
                all_vals.append(float(p.forecast))
            if getattr(p, "upper", None) is not None:
                all_vals.append(float(p.upper))

        max_v = max(all_vals or [1]) or 1
        n = len(points)
        plot_left = cx + 24
        plot_w = chart_w - 28
        plot_h = ch - 8
        plot_bot = cy + 6

        c.setStrokeColor(colors.HexColor("#f1f5f9"))
        c.setFont(_FONT_REGULAR, 4.8)
        c.setFillColor(_MUTED_TEXT)
        for i in range(3):
            frac = i / 2
            y_pos = plot_bot + plot_h * frac
            c.line(plot_left, y_pos, plot_left + plot_w, y_pos)
            c.drawRightString(plot_left - 2, y_pos - 1.5, _fmt_compact_money(max_v * frac))

        band_pts = [(i, p.lower, p.upper) for i, p in enumerate(points) if getattr(p, "forecast", None) is not None and getattr(p, "lower", None) is not None and getattr(p, "upper", None) is not None]
        if band_pts:
            c.setFillColor(_GREEN_BG)
            poly = c.beginPath()
            first = True
            for i, low, up in band_pts:
                px_pos = plot_left + plot_w * i / max(1, n - 1)
                py_pos = plot_bot + plot_h * (float(up) / max_v)
                if first:
                    poly.moveTo(px_pos, py_pos)
                    first = False
                else:
                    poly.lineTo(px_pos, py_pos)
            for i, low, up in reversed(band_pts):
                px_pos = plot_left + plot_w * i / max(1, n - 1)
                py_pos = plot_bot + plot_h * (float(low) / max_v)
                poly.lineTo(px_pos, py_pos)
            poly.close()
            c.drawPath(poly, stroke=0, fill=1)

        hist_pts = [(i, p.actual) for i, p in enumerate(points) if getattr(p, "actual", None) is not None]
        if hist_pts:
            c.setStrokeColor(_ACCENT_BLUE)
            c.setLineWidth(1.2)
            prev = None
            for i, val in hist_pts:
                px_pos = plot_left + plot_w * i / max(1, n - 1)
                py_pos = plot_bot + plot_h * (float(val) / max_v)
                if prev:
                    c.line(prev[0], prev[1], px_pos, py_pos)
                prev = (px_pos, py_pos)

        fore_pts = [(i, p.forecast) for i, p in enumerate(points) if getattr(p, "forecast", None) is not None]
        if fore_pts:
            c.setStrokeColor(_GREEN)
            c.setLineWidth(1.2)
            c.setDash([2, 2])
            prev = None
            for i, val in fore_pts:
                px_pos = plot_left + plot_w * i / max(1, n - 1)
                py_pos = plot_bot + plot_h * (float(val) / max_v)
                if prev:
                    c.line(prev[0], prev[1], px_pos, py_pos)
                prev = (px_pos, py_pos)
            c.setDash()

        c.setLineWidth(1)

    tx = cx + chart_w + 10
    ty = y + h - 21
    rows = [
        ("Expected revenue (next 14 days)", _fmt_inr_full(forecast.expected_revenue)),
        ("Likely range (80% confidence)", f"{_fmt_compact_money(forecast.expected_revenue_lower)} to {_fmt_compact_money(forecast.expected_revenue_upper)}"),
        ("Recent daily average", _fmt_inr_full(forecast.daily_average)),
        ("Trend", f"{forecast.trend_direction.title()} ({_fmt_compact_money(forecast.trend_per_day)}/day)"),
        ("Backtest accuracy (last 7 days)", f"{forecast.accuracy_pct:.1f}%" if forecast.accuracy_pct is not None else "-"),
    ]

    c.setFillColor(_NAVY)
    c.roundRect(tx, ty - 12, table_w, 13, 1.5, stroke=0, fill=1)
    c.setFillColor(_WHITE)
    c.setFont(_FONT_BOLD, 5.8)
    c.drawString(tx + 4, ty - 8.5, "Measure")
    c.drawRightString(tx + table_w - 4, ty - 8.5, "Value")

    row_y = ty - 14
    row_h = 12.5
    for idx, (m, v) in enumerate(rows):
        if idx % 2 == 1:
            c.setFillColor(_ROW_ALT)
            c.rect(tx, row_y - row_h + 3, table_w, row_h, stroke=0, fill=1)

        c.setFillColor(_DARK_TEXT)
        c.setFont(_FONT_REGULAR, 5.8)
        c.drawString(tx + 4, row_y - 5.5, m)
        c.setFont(_FONT_BOLD if idx == 0 else _FONT_REGULAR, 5.8)
        if idx == 0:
            c.setFillColor(_BRAND_BLUE)
        c.drawRightString(tx + table_w - 4, row_y - 5.5, v)

        row_y -= row_h


def generate_visual_financial_pdf(
    *,
    filename: str,
    analytics: AnalyticsResponse,
    ca_report: CAReportSummary,
    daily_summary: list[dict],
    insights=None,
    inventory=None,
    forecast=None,
) -> bytes:
    """Build the single-page, dashboard-grade visual financial report."""
    page_w, page_h = landscape(A4)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    c.setTitle(f"SENOVA Visual Financial Report - {filename}")

    col_w_left = 398
    col_w_right = 406
    gap_x = 10
    x_left = 14
    x_right = x_left + col_w_left + gap_x  # 422

    try:
        dt = datetime.strptime(str(ca_report.period_end)[:10], "%Y-%m-%d")
        prepared_date = dt.strftime("%d %b %Y")
    except Exception:
        prepared_date = datetime.now().strftime("%d %b %Y")

    # LEFT COLUMN:
    _draw_header(c, x_left, 514, col_w_left, 71, filename, ca_report, prepared_date)
    _draw_kpi_row(c, x_left, 442, col_w_left, 66, analytics, ca_report)
    _draw_findings(c, x_left, 284, col_w_left, 152, insights)
    _draw_pnl_statement(c, x_left, 196, col_w_left, 82, ca_report)

    bottom_half_w = (col_w_left - 8) / 2
    _draw_revenue_profit_trend(c, x_left, 12, bottom_half_w, 178, analytics)
    _draw_revenue_mix_donut(c, x_left + bottom_half_w + 8, 12, bottom_half_w, 178, analytics.categories)

    # RIGHT COLUMN:
    _draw_daily_revenue_trend(c, x_right, 459, col_w_right, 126, analytics, ca_report)
    _draw_category_ledger_table(c, x_right, 349, col_w_right, 104, ca_report)
    _draw_top_items_table(c, x_right, 239, col_w_right, 104, analytics)
    _draw_sales_speed_table(c, x_right, 129, col_w_right, 104, inventory, analytics)
    _draw_revenue_forecast_card(c, x_right, 12, col_w_right, 111, forecast)

    c.showPage()
    c.save()
    return buffer.getvalue()


class _DetailedReportHeaderFlowable(Flowable):
    """Executive branded header banner for the Detailed Financial Report."""

    def __init__(self, width: float, height: float, filename: str, ca_report, prepared_date: str):
        super().__init__()
        self.width = width
        self.height = height
        self.filename = filename
        self.ca_report = ca_report
        self.prepared_date = prepared_date

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w = self.width
        h = self.height

        # Rounded dark navy background container
        c.setFillColor(_DARK_BG)
        c.roundRect(0, 0, w, h, 6, stroke=0, fill=1)

        # Subtle bottom accent highlight
        c.setFillColor(_BRAND_BLUE)
        c.roundRect(0, 0, w, 2.5, 1, stroke=0, fill=1)

        # SENOVA Logo
        assets_dir = Path(__file__).resolve().parent.parent / "assets"
        logo_path = assets_dir / "logo.png"
        if not logo_path.exists():
            logo_path = assets_dir / "logo.jpeg"
        if not logo_path.exists():
            logo_path = Path(__file__).resolve().parents[3] / "frontend" / "public" / "assets" / "logo.jpeg"

        text_x = 12
        if logo_path.exists():
            try:
                c.drawImage(str(logo_path), 12, (h - 46) / 2, 46, 46, mask="auto", preserveAspectRatio=True)
                text_x = 68
            except Exception:
                text_x = 12

        # Title
        c.setFillColor(_WHITE)
        c.setFont(_FONT_BOLD, 15)
        c.drawString(text_x, h - 20, "SENOVA Digital Lab")

        # Subtitle
        c.setFillColor(colors.HexColor("#93c5fd"))
        c.setFont(_FONT_BOLD, 8.5)
        c.drawString(text_x, h - 33, "Detailed Financial & Performance Report")

        # Metadata
        c.setFillColor(colors.HexColor("#cbd5e1"))
        c.setFont(_FONT_REGULAR, 6.5)
        c.drawString(text_x, h - 46, f"Data Source: {self.filename}")
        c.drawString(text_x, h - 57, f"Period: {self.ca_report.period_label} ({self.ca_report.period_start} to {self.ca_report.period_end})")

        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(text_x, h - 67, "Currency: INR")

        # Right side: Prepared On & Badge
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.setFont(_FONT_REGULAR, 6.5)
        c.drawRightString(w - 14, h - 20, "Prepared on")
        c.setFillColor(_WHITE)
        c.setFont(_FONT_BOLD, 8.5)
        c.drawRightString(w - 14, h - 32, self.prepared_date)

        # Audit tag pill
        pill_w = 98
        pill_h = 15
        px = w - pill_w - 14
        py = 12
        c.setFillColor(colors.HexColor("#1e293b"))
        c.roundRect(px, py, pill_w, pill_h, 3, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#38bdf8"))
        c.setFont(_FONT_BOLD, 6)
        c.drawCentredString(px + pill_w / 2, py + 4.5, "AUDIT & LEDGER REPORT")


def _on_first_page_ca(c: canvas.Canvas, doc):
    c.saveState()
    c.setStrokeColor(_BORDER)
    c.setLineWidth(0.5)
    c.line(14 * mm, 11 * mm, A4[0] - 14 * mm, 11 * mm)
    c.setFillColor(_MUTED_TEXT)
    c.setFont(_FONT_REGULAR, 6.5)
    c.drawString(14 * mm, 8 * mm, "Confidential — SENOVA Digital Financial Management")
    c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
    c.restoreState()


def _on_later_pages_ca(c: canvas.Canvas, doc):
    c.saveState()
    c.setStrokeColor(_BORDER)
    c.setLineWidth(0.5)
    c.line(14 * mm, A4[1] - 11 * mm, A4[0] - 14 * mm, A4[1] - 11 * mm)
    c.setFillColor(_MUTED_TEXT)
    c.setFont(_FONT_REGULAR, 7)
    c.drawString(14 * mm, A4[1] - 9 * mm, "SENOVA Digital Lab · Detailed Financial Report")
    c.drawRightString(A4[0] - 14 * mm, A4[1] - 9 * mm, f"Page {doc.page}")

    c.line(14 * mm, 11 * mm, A4[0] - 14 * mm, 11 * mm)
    c.setFont(_FONT_REGULAR, 6.5)
    c.drawString(14 * mm, 8 * mm, "Confidential — SENOVA Digital Financial Management")
    c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
    c.restoreState()


def generate_ca_report_pdf(
    *,
    filename: str,
    analytics: AnalyticsResponse,
    ca_report: CAReportSummary,
    ledger_entries,
    ledger_total_rows: int,
    insights=None,
    inventory=None,
    forecast=None,
    daily_summary: list[dict] | None = None,
) -> bytes:
    """Build the detailed accounting-style PDF with every selected transaction row."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"SENOVA Detailed Financial Report - {filename}",
    )
    styles = _build_styles()
    story = []

    try:
        dt = datetime.strptime(str(ca_report.period_end)[:10], "%Y-%m-%d")
        prepared_date = dt.strftime("%d %b %Y")
    except Exception:
        prepared_date = datetime.now().strftime("%d %b %Y")

    header_w = A4[0] - 28 * mm
    story.append(_DetailedReportHeaderFlowable(
        width=header_w,
        height=74,
        filename=filename,
        ca_report=ca_report,
        prepared_date=prepared_date,
    ))
    story.append(Spacer(1, 10))

    insights_tbl = _insights_table(insights)
    if insights_tbl:
        story.append(Paragraph("What Changed - Automated Findings", styles["SectionHeading2"]))
        story.append(insights_tbl)

    story.append(Paragraph("Profit &amp; Loss Statement", styles["SectionHeading2"]))
    if ca_report.pnl:
        story.append(_pnl_table(ca_report))
    else:
        story.append(Paragraph("No transactions in this period.", styles["Normal"]))

    if daily_summary:
        story.append(Paragraph("Daily Financial Summary", styles["SectionHeading2"]))
        story.append(_daily_summary_table(daily_summary))

    if ca_report.category_ledger:
        story.append(Paragraph("Category-wise Ledger", styles["SectionHeading2"]))
        story.append(_category_ledger_table(ca_report))

    discount_tbl = _discount_table(analytics)
    if discount_tbl:
        story.append(Paragraph("Discount / Margin Analysis", styles["SectionHeading2"]))
        story.append(discount_tbl)

    forecast_tbl = _forecast_table(forecast)
    if forecast_tbl:
        story.append(Paragraph("Revenue Forecast", styles["SectionHeading2"]))
        story.append(forecast_tbl)
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            "Projection from the dashboard forecasting pipeline. Treat the range, not the single figure, as the expectation.",
            styles["SmallNote2"],
        ))
    elif forecast is not None:
        story.append(Paragraph("Revenue Forecast", styles["SectionHeading2"]))
        story.append(Paragraph(str(getattr(forecast, "reason", "Not available in uploaded data")), styles["SmallNote2"]))

    top_items_tbl = _top_items_table(analytics)
    if top_items_tbl:
        story.append(Paragraph("Top 5 Fast-Moving Items", styles["SectionHeading2"]))
        story.append(top_items_tbl)

    reorder_tbl = _reorder_table(inventory)
    if reorder_tbl:
        story.append(PageBreak())
        title = "Reorder Priority (Top 20 by Demand)" if getattr(inventory, "stock_aware", False) else "Sales-speed Ranking (Top 20 by Demand)"
        story.append(Paragraph(title, styles["SectionHeading2"]))
        story.append(reorder_tbl)
        if getattr(inventory, "note", None):
            story.append(Spacer(1, 3))
            story.append(Paragraph(str(inventory.note), styles["SmallNote2"]))

    if ledger_entries:
        story.append(PageBreak())
        story.append(Paragraph("Detailed Transaction Ledger", styles["SectionHeading2"]))
        story.append(Paragraph(
            f"Complete selected transaction register: {ledger_total_rows:,} row(s). Values use the same dashboard calculation pipeline.",
            styles["SmallNote2"],
        ))
        story.append(Spacer(1, 4))
        story.append(_ledger_table(ledger_entries))

    doc.build(story, onFirstPage=_on_first_page_ca, onLaterPages=_on_later_pages_ca)
    return buffer.getvalue()
