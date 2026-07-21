"""
CA-style PDF report generator.

Produces a proper accounting-style PDF using ReportLab's Platypus layout
engine: real text and real tables (selectable, searchable, printable),
NOT a screenshot of the dashboard. This mirrors how a Chartered Accountant
would hand a client a printed sales report — a title page, a Profit & Loss
statement, a category-wise ledger, and a detailed transaction register.

Design notes
------------
- The detailed transaction ledger can legitimately be tens of thousands of
  rows (50k-row files were the real-world scale tested with this app). We
  cap the ledger section at ``MAX_LEDGER_ROWS_IN_PDF`` rows with a clear
  note, rather than silently producing a 500-page PDF or one that browsers
  struggle to render/print. The full ledger is always available in-app via
  the paginated Transaction Ledger table.
- Every number here is computed by the same ``sales_calculations`` module
  the JSON API and charts use — this file is presentation-only, it does
  not duplicate any business logic.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
)

from app.models.schemas import AnalyticsResponse, CAReportSummary

# Cap on how many transaction rows are printed in the PDF. Large uploads
# (tens of thousands of rows) would otherwise produce an impractically
# long document; the in-app paginated ledger remains the source of truth
# for browsing every row.
MAX_LEDGER_ROWS_IN_PDF = 500

_BRAND_BLUE = colors.HexColor("#0ea5e9")
_DARK_TEXT = colors.HexColor("#0f172a")
_MUTED_TEXT = colors.HexColor("#64748b")
_ROW_ALT = colors.HexColor("#f1f5f9")
_POSITIVE = colors.HexColor("#059669")
_NEGATIVE = colors.HexColor("#dc2626")


def _fmt_money(amount: float) -> str:
    """₹ formatted with Indian-style thousands separators, 2 decimals."""
    return f"Rs. {amount:,.2f}"


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontSize=22, textColor=_BRAND_BLUE, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=_MUTED_TEXT, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading", parent=styles["Heading2"], fontSize=13, textColor=_DARK_TEXT,
        spaceBefore=18, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="FootNote", parent=styles["Normal"], fontSize=8, textColor=_MUTED_TEXT,
    ))
    return styles


def _pnl_table(report: CAReportSummary) -> Table:
    """Profit & Loss statement — labelled rows with a ruled-off subtotal."""
    header = ["Particulars", "Amount", "% of Revenue"]
    rows = [header]
    subtotal_rows: list[int] = []

    for i, line in enumerate(report.pnl, start=1):
        pct = f"{line.percentage_of_revenue}%" if line.percentage_of_revenue is not None else "-"
        rows.append([line.label, _fmt_money(line.amount), pct])
        if line.is_subtotal:
            subtotal_rows.append(i)

    table = Table(rows, colWidths=[80 * mm, 50 * mm, 40 * mm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]
    for r in subtotal_rows:
        style.append(("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))
        style.append(("LINEABOVE", (0, r), (-1, r), 1.2, _DARK_TEXT))
        style.append(("TEXTCOLOR", (0, r), (-1, r), _BRAND_BLUE))
    table.setStyle(TableStyle(style))
    return table


def _category_ledger_table(report: CAReportSummary) -> Table:
    """Category-wise revenue/cost/profit/margin schedule."""
    header = ["Category", "Units Sold", "Revenue", "Cost", "Profit", "Margin %"]
    rows = [header]
    for row in report.category_ledger:
        rows.append([
            row.category,
            f"{row.units_sold:,}",
            _fmt_money(row.revenue),
            _fmt_money(row.cost),
            _fmt_money(row.profit),
            f"{row.margin_percentage}%",
        ])

    table = Table(rows, colWidths=[40 * mm, 25 * mm, 32 * mm, 32 * mm, 32 * mm, 22 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _DARK_TEXT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
    ]
    table.setStyle(TableStyle(style))
    return table


def _top_items_table(analytics: AnalyticsResponse) -> Table | None:
    if not analytics.top_items:
        return None
    header = ["Item", "Units Sold", "Revenue"]
    rows = [header] + [[i.name, f"{i.quantity:,}", _fmt_money(i.revenue)] for i in analytics.top_items]
    table = Table(rows, colWidths=[80 * mm, 40 * mm, 40 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _DARK_TEXT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
    ]))
    return table


def _dead_stock_table(analytics: AnalyticsResponse) -> Table | None:
    if not analytics.dead_stock:
        return None
    header = ["Item", "Total Units Sold", "Days Since Last Sale"]
    rows = [header] + [
        [i.name, f"{i.total_quantity:,}", f"{i.days_since_last_sale} days"] for i in analytics.dead_stock
    ]
    table = Table(rows, colWidths=[80 * mm, 40 * mm, 40 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
    ]))
    return table


def _ledger_table(entries, truncated: bool) -> Table:
    """Detailed row-by-row transaction register (day-book style)."""
    header = ["Date", "Category", "Item", "Qty", "Selling Price", "Cost Price", "Revenue", "Profit"]
    rows = [header]
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
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _DARK_TEXT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
    ]
    table.setStyle(TableStyle(style))
    return table


def generate_ca_report_pdf(
    *,
    filename: str,
    analytics: AnalyticsResponse,
    ca_report: CAReportSummary,
    ledger_entries,
    ledger_total_rows: int,
) -> bytes:
    """
    Build the full CA-style PDF report and return it as raw bytes, ready
    to stream in an HTTP response.

    Parameters
    ----------
    filename : the original uploaded filename, shown in the report header.
    analytics : the standard AnalyticsResponse (for top items / dead stock sections).
    ca_report : the CAReportSummary (P&L + category ledger) for the selected period.
    ledger_entries : list[LedgerEntry] to print in the detailed register
        (already capped to ``MAX_LEDGER_ROWS_IN_PDF`` by the caller).
    ledger_total_rows : total transaction count, to note if the printed
        ledger was truncated.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=f"SENOVA Financial Report — {filename}",
    )
    styles = _build_styles()
    story = []

    # ── Header ──────────────────────────────────────────────────────────
    story.append(Paragraph("SENOVA Digital Lab", styles["ReportTitle"]))
    story.append(Paragraph(
        f"Financial Report &middot; {filename} &middot; Period: {ca_report.period_label} "
        f"({ca_report.period_start} to {ca_report.period_end})",
        styles["ReportSubtitle"],
    ))

    # ── Profit & Loss ───────────────────────────────────────────────────
    story.append(Paragraph("Profit &amp; Loss Statement", styles["SectionHeading"]))
    if ca_report.pnl:
        story.append(_pnl_table(ca_report))
    else:
        story.append(Paragraph("No transactions in this period.", styles["Normal"]))

    # ── Category ledger ─────────────────────────────────────────────────
    if ca_report.category_ledger:
        story.append(Paragraph("Category-wise Ledger", styles["SectionHeading"]))
        story.append(_category_ledger_table(ca_report))

    # ── Top items / dead stock ──────────────────────────────────────────
    top_items_tbl = _top_items_table(analytics)
    if top_items_tbl:
        story.append(Paragraph("Top 5 Fast-Moving Items", styles["SectionHeading"]))
        story.append(top_items_tbl)

    dead_stock_tbl = _dead_stock_table(analytics)
    if dead_stock_tbl:
        story.append(Paragraph("Dead Stock / Slow Movers", styles["SectionHeading"]))
        story.append(dead_stock_tbl)

    # ── Detailed transaction ledger ─────────────────────────────────────
    if ledger_entries:
        story.append(PageBreak())
        story.append(Paragraph("Detailed Transaction Ledger", styles["SectionHeading"]))
        if ledger_total_rows > len(ledger_entries):
            story.append(Paragraph(
                f"Showing the first {len(ledger_entries):,} of {ledger_total_rows:,} transactions. "
                "View the full register in-app under the Financial Report tab.",
                styles["FootNote"],
            ))
            story.append(Spacer(1, 6))
        story.append(_ledger_table(ledger_entries, truncated=ledger_total_rows > len(ledger_entries)))

    doc.build(story)
    return buffer.getvalue()
