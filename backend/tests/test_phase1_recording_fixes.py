"""
Regression tests for Phase 1 test recording issues:
Issue A — Missing Discount must not appear as zero (Path A and Path B).
Issue B — PII mapping must override AI suggestions (Customer Email / Buyer Contact No).
Issue C — Incorrect or stale dashboard weekday insights and number guard verification.
"""

from __future__ import annotations

import io
import pandas as pd
import pytest

from app.api.routes.analytics import _discount_metrics_if_supported
from app.api.routes.upload import _SAMPLE_ROW_COUNT
from app.models.schemas import AnalyticsResponse, SalesSummary, MetricValue
from app.services import column_understanding, dynamic_schema, number_guard, tier1_classifier, tier2_gemini
from app.services.extra_columns import classify_extra_columns, is_personal_pii
from app.services.insights_engine import _weekday_insight, compute_insights
from app.services.pdf_report import _discount_table
from app.services.pii_mask import mask_text
from app.utils.data_validator import (
    detect_column_mapping,
    guess_canonical_column,
    normalize_dataframe,
)


@pytest.fixture
def path_a_raw_df() -> pd.DataFrame:
    """Path A CSV structure: Date + Line Total + extra metadata, no Discount or MRP."""
    dates = pd.date_range("2026-09-01", periods=28, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({
        "Date": dates,
        "Line Total": [500.0 + (i % 7) * 150.0 for i in range(28)],
        "Transaction Ref": [f"008100{i:02d}" for i in range(28)],
        "Buyer Contact No": [f"90000010{i:02d}" for i in range(28)],
        "Store Zone": ["North Hub" if i % 2 == 0 else "South Hub" for i in range(28)],
        "Packing Fee Amount": [15.0 + i for i in range(28)],
        "Margin Rate pct": [8.0 + (i % 5) for i in range(28)],
        "Dispatch Date": dates,
        "Staff Note": [f"Pack note {i}" for i in range(28)],
    })


@pytest.fixture
def path_b_raw_df() -> pd.DataFrame:
    """Path B CSV structure: Date + Quantity + Selling Price + Customer Email, no Discount or MRP."""
    dates = pd.date_range("2026-09-01", periods=28, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({
        "Date": dates,
        "Quantity": [2 + (i % 4) for i in range(28)],
        "Selling Price": [150.0 + (i % 5) * 50.0 for i in range(28)],
        "SKU Ref Code": [f"004200{i:02d}" for i in range(28)],
        "Region Group": ["Raichur Urban" if i % 2 == 0 else "Manvi Route" for i in range(28)],
        "Delivery Fee Amount": [20.0 + i for i in range(28)],
        "GST Rate pct": [5.0 for _ in range(28)],
        "Customer Email": [f"customer{i:03d}@example.com" for i in range(28)],
        "Supplier ETA": dates,
        "Internal Comment": [f"Check package {i}" for i in range(28)],
    })


# ═══════════════════════════════════════════════════════════════════════════
# Issue A Tests: Missing Discount must not appear as zero
# ═══════════════════════════════════════════════════════════════════════════


class TestIssueAMissingDiscount:
    def test_path_a_discount_unavailable_and_no_zero_fabrication(self, path_a_raw_df):
        norm_df, _ = normalize_dataframe(
            path_a_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Line Total": "Line Total"},
        )
        schema = dynamic_schema.build(norm_df, mapping={"Date": "Date", "Line Total": "Line Total"})

        discount_kpi = next(c for c in schema["kpi_cards"] if c["key"] == "discount")
        assert discount_kpi["available"] is False, "Discount KPI must be marked unavailable when absent"
        assert discount_kpi["reason"] == "Map Discount, or map MRP + Selling Price + Quantity, to calculate this metric."

        discount_measure = next(m for m in schema["measures"] if m["key"] == "discount")
        assert discount_measure["available"] is False
        assert "Map Discount, or map MRP + Selling Price + Quantity" in discount_measure["reason"]

        assert _discount_metrics_if_supported(norm_df) is None

        # PDF table returns None when discount metrics are None
        dummy_analytics = AnalyticsResponse(
            summary=SalesSummary(
                revenue=MetricValue(value=1000.0, available=True),
                profit=MetricValue(value=None, available=False),
                cost=MetricValue(value=None, available=False),
                units_sold=MetricValue(value=None, available=False),
                unique_items_sold=MetricValue(value=None, available=False),
            ),
            row_count=len(norm_df),
            top_items=[],
            daily_trend=[],
            dead_stock=[],
            categories=[],
            errors=[],
            discount_metrics=None,
            discount_vs_margin=[],
        )
        assert _discount_table(dummy_analytics) is None

    def test_path_b_discount_unavailable_and_no_zero_fabrication(self, path_b_raw_df):
        norm_df, _ = normalize_dataframe(
            path_b_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Quantity": "Quantity", "Selling Price": "Selling Price"},
        )
        schema = dynamic_schema.build(
            norm_df,
            mapping={"Date": "Date", "Quantity": "Quantity", "Selling Price": "Selling Price"},
        )

        discount_kpi = next(c for c in schema["kpi_cards"] if c["key"] == "discount")
        assert discount_kpi["available"] is False
        assert discount_kpi["reason"] == "Map Discount, or map MRP + Selling Price + Quantity, to calculate this metric."

        discount_measure = next(m for m in schema["measures"] if m["key"] == "discount")
        assert discount_measure["available"] is False
        assert _discount_metrics_if_supported(norm_df) is None

    def test_genuine_zero_discount_is_preserved(self):
        """When a valid Discount column is present with genuine 0.0, it remains available as 0.0."""
        dates = pd.date_range("2026-09-01", periods=5, freq="D").strftime("%Y-%m-%d")
        df_zero = pd.DataFrame({
            "Date": dates,
            "Line Total": [100.0, 200.0, 300.0, 400.0, 500.0],
            "Discount": [0.0, 0.0, 0.0, 0.0, 0.0],
        })
        norm_df, _ = normalize_dataframe(
            df_zero,
            soft_fail=True,
            column_mapping={"Date": "Date", "Line Total": "Line Total", "Discount": "Discount"},
        )
        schema = dynamic_schema.build(
            norm_df,
            mapping={"Date": "Date", "Line Total": "Line Total", "Discount": "Discount"},
        )

        discount_kpi = next(c for c in schema["kpi_cards"] if c["key"] == "discount")
        assert discount_kpi["available"] is True
        assert discount_kpi["reason"] is None

        metrics = _discount_metrics_if_supported(norm_df)
        assert metrics is not None
        assert metrics["discount_given"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Issue B Tests: PII mapping must override AI suggestions
# ═══════════════════════════════════════════════════════════════════════════


class TestIssueBPIIOverrides:
    def test_guess_canonical_column_rejects_pii_headers(self):
        assert guess_canonical_column("Customer Email")[0] is None
        assert guess_canonical_column("Customer Phone")[0] is None
        assert guess_canonical_column("Buyer Contact No")[0] is None
        assert guess_canonical_column("Client Email Address")[0] is None
        assert guess_canonical_column("Contact Mobile")[0] is None
        assert guess_canonical_column("Customer DOB")[0] is None

        # Clean customer headers without PII tokens still match Customer
        assert guess_canonical_column("Customer Name")[0] == "Customer"
        assert guess_canonical_column("Party Name")[0] == "Customer"

    def test_tier1_classifies_pii_as_stored_only(self, path_b_raw_df):
        guesses = tier1_classifier.classify_columns(path_b_raw_df, ai_available=True)
        email_guess = next(g for g in guesses if g.raw_column == "Customer Email")
        assert email_guess.label == "personal"
        assert email_guess.canonical is None
        assert email_guess.route == tier1_classifier.ROUTE_LOCAL

    @pytest.mark.asyncio
    async def test_ai_suggestion_cannot_override_pii_privacy_rule(self, path_b_raw_df):
        """Even if Tier 2 Gemini returned 'Customer' for Customer Email, privacy rule overrides it."""
        mock_result = tier2_gemini.Tier2Result(
            source=tier2_gemini.SOURCE_GEMINI,
            verdicts={
                "Customer Email": {
                    "label": "customer",
                    "confidence": 0.98,
                    "reason": "Looks like customer identifier",
                }
            },
            elapsed_ms=10.0,
            notice=None,
            reason_code=None,
        )

        reports = [
            {
                "raw_column": "Customer Email",
                "suggested_field": "Customer",
                "confidence": "fuzzy",
                "confidence_score": 0.98,
                "confidence_band": "high",
                "semantic_label": "customer",
                "route": tier1_classifier.ROUTE_GEMINI,
                "source": "pending",
                "reason": "AI read this as customer",
                "needs_review": False,
                "recognised_unused": False,
            }
        ]

        column_understanding._apply_tier2_reports(reports, mock_result, path_b_raw_df)

        assert reports[0]["suggested_field"] is None
        assert reports[0]["semantic_label"] == "personal"
        assert reports[0]["confidence_band"] == "low"
        assert reports[0]["confidence_score"] == 0.0
        assert "Personal / contact data (PII) preserved as stored-only" in reports[0]["reason"]

    def test_sample_rows_masks_pii_values(self, path_b_raw_df):
        pii_cols = {col for col in path_b_raw_df.columns if is_personal_pii(str(col), path_b_raw_df[col])}
        assert "Customer Email" in pii_cols

        sample_rows = [
            {
                str(col): (
                    None
                    if pd.isna(value)
                    else ("[redacted]" if col in pii_cols else mask_text(value)[:120])
                )
                for col, value in row.items()
            }
            for row in path_b_raw_df.head(_SAMPLE_ROW_COUNT).to_dict(orient="records")
        ]

        for row in sample_rows:
            assert row["Customer Email"] == "[redacted]"
            assert "@example.com" not in str(row["Customer Email"])

    def test_normalized_dataframe_masks_and_excludes_pii(self, path_b_raw_df):
        norm_df, _ = normalize_dataframe(
            path_b_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Quantity": "Quantity", "Selling Price": "Selling Price"},
        )
        registry = norm_df.attrs.get("extra_registry", {})
        email_entry = next((v for v in registry.values() if v["display_label"] == "Customer Email"), None)
        assert email_entry is not None
        assert email_entry["role"] == "stored_only"
        assert email_entry["class_name"] == "personal"

        # Values in stored-only personal columns are redacted
        email_col = email_entry["key"]
        for val in norm_df[email_col]:
            assert val == "[redacted]"


# ═══════════════════════════════════════════════════════════════════════════
# Issue C Tests: Weekday Insights Consistency & Number Guard Verification
# ═══════════════════════════════════════════════════════════════════════════


class TestIssueCWeekdayInsights:
    def test_weekday_insight_generates_consistent_heading_and_body(self, path_a_raw_df):
        norm_df, _ = normalize_dataframe(
            path_a_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Line Total": "Line Total"},
        )
        norm_df["_row_revenue"] = norm_df["Line Total"]
        insight = _weekday_insight(norm_df)
        assert insight is not None
        assert insight.id == "weekday-timing"

        best_day = insight.evidence[2]
        worst_day = insight.evidence[3]

        assert best_day in insight.title
        assert worst_day in insight.title
        assert f"{best_day} is your strongest day, {worst_day} the weakest" == insight.title
        assert best_day in insight.message
        assert worst_day in insight.message
        assert f"{best_day} averages" in insight.message
        assert f"on {worst_day}" in insight.message

    def test_number_guard_rejects_inverted_weekday_ai_narrative(self, path_a_raw_df):
        norm_df, _ = normalize_dataframe(
            path_a_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Line Total": "Line Total"},
        )
        norm_df["_row_revenue"] = norm_df["Line Total"]
        insight = _weekday_insight(norm_df)
        assert insight is not None

        best_day = insight.evidence[2]
        worst_day = insight.evidence[3]

        # 1. Authentic rewrite preserving calculation succeeds
        good_rewrite = f"Your highest takings occur on {best_day}, while {worst_day} sees your lowest takings."
        verified, offenders = number_guard.verify(good_rewrite, metrics=insight.metrics, evidence=insight.evidence)
        assert verified is True
        assert offenders == []

        # 2. Inverted rewrite claiming worst_day as strongest/busiest fails
        bad_rewrite = f"{worst_day} is your strongest day for sales, while {best_day} was slowest."
        verified, offenders = number_guard.verify(bad_rewrite, metrics=insight.metrics, evidence=insight.evidence)
        assert verified is False
        assert any("Inverted weekday" in o for o in offenders)

    def test_cross_file_insight_isolation(self, path_a_raw_df, path_b_raw_df):
        norm_a, _ = normalize_dataframe(
            path_a_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Line Total": "Line Total"},
        )
        norm_b, _ = normalize_dataframe(
            path_b_raw_df,
            soft_fail=True,
            column_mapping={"Date": "Date", "Quantity": "Quantity", "Selling Price": "Selling Price"},
        )

        insights_a = compute_insights(norm_a, None, period_label="all")
        insights_b = compute_insights(norm_b, None, period_label="all")

        # Both compute their own independent insights
        assert insights_a.analysed_days > 0
        assert insights_b.analysed_days > 0
        assert insights_a != insights_b
