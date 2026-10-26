"""
Phase 1 Acceptance Suite: Extra Columns Classification, Sidecar Registry,
Two-Field Upload Rule, Honest Degradation, and Dynamic Key Isolation.
"""

import io
import json
import pytest
import pandas as pd
import numpy as np
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.extra_columns import classify_extra_columns, make_safe_slug
from app.services.file_handler import save_extra_registry, load_extra_registry
from app.utils.data_validator import normalize_dataframe, check_required_columns
from app.services.sales_calculations import (
    build_ledger_page, compute_daily_financial_summary, compute_pnl_report, compute_summary_between,
)
from app.services import file_handler
from app.services.forecasting import compute_forecast


@pytest.fixture
def phase1_ten_row_df():
    """
    The 10-row Phase 1 acceptance fixture:
    - Delivery Charge sum: 22,480
    - GST % average: 15.05
    - City: 4 distinct values
    - Sales Rep: 3 distinct values
    - Order ID: ID-like string with leading zeroes ('00101'..'00110')
    - Notes: free text
    - Customer Phone: 10-digit mobile number (PII)
    """
    return pd.DataFrame({
        "Date": [f"2026-03-0{i}" if i < 10 else f"2026-03-{i}" for i in range(1, 11)],
        "Quantity": [2, 3, 1, 4, 2, 5, 1, 2, 3, 4],
        "Selling Price": [500.0, 400.0, 1000.0, 250.0, 600.0, 300.0, 800.0, 450.0, 700.0, 350.0],
        "Delivery Charge": [2000.0, 2000.0, 2500.0, 2500.0, 2480.0, 2000.0, 2000.0, 2500.0, 2000.0, 2500.0],
        "GST %": [18.0, 18.0, 12.0, 12.0, 18.0, 18.0, 12.0, 12.0, 18.0, 12.5],
        "City": ["Mumbai", "Delhi", "Bengaluru", "Mumbai", "Delhi", "Bengaluru", "Chennai", "Mumbai", "Delhi", "Bengaluru"],
        "Sales Rep": ["Alice", "Bob", "Charlie", "Alice", "Bob", "Charlie", "Alice", "Bob", "Charlie", "Alice"],
        "Order ID": ["00101", "00102", "00103", "00104", "00105", "00106", "00107", "00108", "00109", "00110"],
        "Notes": [f"Customer order note special delivery #{i}" for i in range(1, 11)],
        "Customer Phone": [f"987654321{i}" for i in range(10)],
    })


def test_extra_column_classification(phase1_ten_row_df):
    """Verify deterministic classification rules under Section 1.4."""
    extra_df = phase1_ten_row_df[[
        "Delivery Charge", "GST %", "City", "Sales Rep", "Order ID", "Notes", "Customer Phone"
    ]]
    registry, raw_to_safe = classify_extra_columns(extra_df)

    # 1. Delivery Charge: numeric additive -> extra_measure (sum)
    deliv_key = raw_to_safe["Delivery Charge"]
    assert deliv_key == "x_meas:delivery_charge"
    assert registry[deliv_key]["role"] == "extra_measure"
    assert registry[deliv_key]["class_name"] == "numeric"
    assert registry[deliv_key]["aggregation"] == "sum"

    # 2. GST %: numeric percentage -> extra_measure (avg)
    gst_key = raw_to_safe["GST %"]
    assert gst_key == "x_meas:gst_pct"
    assert registry[gst_key]["role"] == "extra_measure"
    assert registry[gst_key]["class_name"] == "numeric"
    assert registry[gst_key]["aggregation"] in ("avg", "average")

    # 3. City: low-cardinality text (4 values) -> extra_dimension
    city_key = raw_to_safe["City"]
    assert city_key == "x_dim:city"
    assert registry[city_key]["role"] == "extra_dimension"
    assert registry[city_key]["class_name"] == "low_cardinality_text"

    # 4. Sales Rep: low-cardinality text (3 values) -> extra_dimension
    rep_key = raw_to_safe["Sales Rep"]
    assert rep_key == "x_dim:sales_rep"
    assert registry[rep_key]["role"] == "extra_dimension"

    # 5. Order ID: ID-like string with leading zeroes -> stored-only
    order_key = raw_to_safe["Order ID"]
    assert order_key == "x_col:order_id"
    assert registry[order_key]["role"] == "stored_only"
    assert registry[order_key]["class_name"] == "id_like"

    # 6. Notes: free text -> stored-only
    notes_key = raw_to_safe["Notes"]
    assert notes_key == "x_col:notes"
    assert registry[notes_key]["role"] == "stored_only"
    assert registry[notes_key]["class_name"] == "other_text"

    # 7. Customer Phone: personal phone number -> personal / stored-only
    phone_key = raw_to_safe["Customer Phone"]
    assert phone_key == "x_col:customer_phone"
    assert registry[phone_key]["role"] == "stored_only"
    assert registry[phone_key]["class_name"] == "personal"


def test_thirty_column_cap_and_collision_handling():
    """Verify 30-column cap and deterministic slug collision handling."""
    # Create 35 unmapped columns
    cols = {f"Extra Col {i}": [1, 2, 3] for i in range(35)}
    df = pd.DataFrame(cols)
    registry, raw_to_safe = classify_extra_columns(df)
    assert len(registry) == 30
    assert len(raw_to_safe) == 30

    # Collision test: City, city, CITY!
    coll_df = pd.DataFrame({
        "City": ["A", "B"],
        "city": ["C", "D"],
        "CITY!": ["E", "F"],
    })
    coll_reg, coll_map = classify_extra_columns(coll_df)
    keys = list(coll_reg.keys())
    assert len(keys) == 3
    assert len(set(keys)) == 3
    assert "x_dim:city" in keys
    assert "x_dim:city_2" in keys
    assert "x_dim:city_3" in keys


def test_two_field_upload_path_a_date_and_line_total():
    """Verify Path A: Date + Line Total only (Category, Item, Cost Price omitted)."""
    df = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02"],
        "Line Total": [1500.0, 2500.0],
        "Delivery Fee": [100.0, 150.0],
    })
    is_valid, missing = check_required_columns(df.columns)
    assert is_valid, missing

    valid_df, errors = normalize_dataframe(df)
    assert len(errors) == 0
    assert len(valid_df) == 2
    assert "Line Total" in valid_df.columns
    assert "Date" in valid_df.columns
    assert "x_meas:delivery_fee" in valid_df.columns

    # Honest degradation check: profit, cost, units sold are not fabricated
    empty_prev = valid_df.iloc[0:0]
    summary = compute_summary_between(valid_df, empty_prev)
    assert summary.revenue.available is True
    assert summary.revenue.value == 4000.0
    assert summary.profit.available is False
    assert "needs Cost Price" in summary.profit.reason
    assert summary.cost.available is False
    assert "needs Cost Price" in summary.cost.reason
    assert summary.units_sold.available is False
    assert "needs Quantity" in summary.units_sold.reason


def test_two_field_upload_path_b_date_qty_selling_price():
    """Verify Path B: Date + Quantity + Selling Price only (Cost, Category, Item omitted)."""
    df = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02"],
        "Quantity": [2, 3],
        "Selling Price": [500.0, 400.0],
    })
    is_valid, missing = check_required_columns(df.columns)
    assert is_valid, missing

    valid_df, errors = normalize_dataframe(df)
    assert len(errors) == 0
    assert len(valid_df) == 2
    assert "Quantity" in valid_df.columns
    assert "Selling Price" in valid_df.columns

    empty_prev = valid_df.iloc[0:0]
    summary = compute_summary_between(valid_df, empty_prev)
    assert summary.revenue.available is True
    assert summary.revenue.value == 2200.0  # (2*500) + (3*400)
    assert summary.units_sold.available is True
    assert summary.units_sold.value == 5
    assert summary.profit.available is False
    assert "needs Cost Price" in summary.profit.reason
    assert summary.cost.available is False
    assert "needs Cost Price" in summary.cost.reason


@pytest.mark.asyncio
async def test_end_to_end_phase1_acceptance(phase1_ten_row_df):
    """
    Full end-to-end acceptance run:
    1. Upload 10-row CSV with unmapped extra columns
    2. Confirm mapping
    3. Query chart data for Delivery Charge -> verify sum == 22,480
    4. Query chart data for GST % -> verify avg == 15.05
    5. Query dimensions -> verify City (4 distinct) & Sales Rep (3 distinct) present
    6. Verify PII & Order ID are NOT exposed in dimensions
    7. Query with unknown dynamic key or cross-file key -> verify HTTP 422
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Convert df to CSV bytes
        csv_buffer = io.StringIO()
        phase1_ten_row_df.to_csv(csv_buffer, index=False)
        csv_bytes = csv_buffer.getvalue().encode("utf-8")

        # 1. Upload to /upload/
        upload_resp = await client.post(
            "/upload/",
            files={"file": ("ten_rows.csv", csv_bytes, "text/csv")},
            data={"ai_consent": "false"},
        )
        assert upload_resp.status_code == 201
        preview = upload_resp.json()
        file_id = preview["file_id"]

        # 2. Confirm mapping at /upload/{file_id}/confirm-mapping
        mapping = {
            "Date": "Date",
            "Quantity": "Quantity",
            "Selling Price": "Selling Price",
        }
        confirm_resp = await client.post(
            f"/upload/{file_id}/confirm-mapping",
            json={"mapping": mapping},
        )
        assert confirm_resp.status_code == 200

        # Verify sidecar persistence
        registry = load_extra_registry(file_id)
        assert registry is not None
        assert "x_meas:delivery_charge" in registry
        assert "x_meas:gst_pct" in registry
        assert "x_dim:city" in registry
        assert "x_col:order_id" in registry

        # 3. Query chart data for Delivery Charge (sum)
        deliv_resp = await client.post(
            f"/analytics/{file_id}/chart-data",
            json={
                "measure": "x_meas:delivery_charge",
                "dimension": "day",
                "chart_type": "bar",
                "time_filter": "all",
                "filters": {},
            },
        )
        assert deliv_resp.status_code == 200
        deliv_data = deliv_resp.json()
        total_delivery = sum(p["value"] for p in deliv_data["points"])
        assert round(total_delivery, 2) == 22480.0

        # 4. Query chart data for GST % (avg)
        gst_resp = await client.post(
            f"/analytics/{file_id}/chart-data",
            json={
                "measure": "x_meas:gst_pct",
                "dimension": "day",
                "chart_type": "bar",
                "time_filter": "all",
                "filters": {},
            },
        )
        assert gst_resp.status_code == 200
        gst_data = gst_resp.json()
        assert round(gst_data["total"], 2) == 15.05

        # 5. Query dimensions
        dim_resp = await client.get(f"/analytics/{file_id}/dimensions")
        assert dim_resp.status_code == 200
        dim_data = dim_resp.json()
        dim_keys = [d["key"] for d in dim_data["dimensions"]]

        assert "x_dim:city" in dim_keys
        assert "x_dim:sales_rep" in dim_keys

        # Check distinct counts
        city_dim = next(d for d in dim_data["dimensions"] if d["key"] == "x_dim:city")
        assert len(city_dim["values"]) == 4
        assert city_dim["total"] == 4

        rep_dim = next(d for d in dim_data["dimensions"] if d["key"] == "x_dim:sales_rep")
        assert len(rep_dim["values"]) == 3
        assert rep_dim["total"] == 3

        # 6. Verify PII & stored-only are NOT in dimensions
        assert "x_col:order_id" not in dim_keys
        assert "x_col:notes" not in dim_keys
        assert "x_col:customer_phone" not in dim_keys
        assert "Order ID" not in [d["label"] for d in dim_data["dimensions"]]
        assert "Customer Phone" not in [d["label"] for d in dim_data["dimensions"]]

        # Extra measures returned in dimension response
        meas_keys = [m["key"] for m in dim_data["extra_measures"]]
        assert "x_meas:delivery_charge" in meas_keys
        assert "x_meas:gst_pct" in meas_keys

        # 7. Dynamic key isolation: querying unknown dynamic key -> HTTP 422
        bad_req = await client.post(
            f"/analytics/{file_id}/chart-data",
            json={
                "measure": "x_meas:nonexistent",
                "dimension": "category",
                "chart_type": "bar",
                "time_filter": "all",
                "filters": {},
            },
        )
        assert bad_req.status_code == 422

        # Stored-only or PII key requested as measure or dimension -> HTTP 422
        bad_dim = await client.post(
            f"/analytics/{file_id}/chart-data",
            json={
                "measure": "revenue",
                "dimension": "x_col:customer_phone",
                "chart_type": "bar",
                "time_filter": "all",
                "filters": {},
            },
        )
        assert bad_dim.status_code == 422

        # 8. Schema endpoint check for coverage report
        schema_resp = await client.post(f"/analytics/{file_id}/schema")
        assert schema_resp.status_code == 200
        schema_data = schema_resp.json()
        assert "coverage" in schema_data
        cov = schema_data["coverage"]
        assert cov["mapped_columns"] == 3
        assert cov["extra_dimensions"] == 2
        assert cov["extra_measures"] == 2
        assert cov["stored_only_columns"] == 3



def test_optional_blank_category_and_item_do_not_drop_sales_rows():
    df = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02", "2026-03-03"],
        "Quantity": [1, 2, 3],
        "Selling Price": [100, 200, 300],
        "Category": ["Tops", "", None],
        "Item": ["Shirt", None, ""],
    })
    clean, errors = normalize_dataframe(
        df,
        column_mapping={
            "Date": "Date",
            "Quantity": "Quantity",
            "Selling Price": "Selling Price",
            "Category": "Category",
            "Item": "Item",
        },
    )
    assert len(clean) == 3
    assert clean["Category"].tolist() == ["Tops", "Unspecified", "Unspecified"]
    assert clean["Item"].tolist() == ["Shirt", "Unspecified", "Unspecified"]


def test_date_line_total_report_and_daily_summary_degrade_honestly():
    raw = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02"],
        "Amount": [1500, 2500],
    })
    clean, errors = normalize_dataframe(raw, column_mapping={"Date": "Date", "Amount": "Line Total"})
    assert len(errors) == 0
    assert len(clean) == 2
    daily = compute_daily_financial_summary(clean, "2026-03-01", "2026-03-02")
    assert [row["revenue"] for row in daily] == [1500.0, 2500.0]
    assert all(row["units_sold"] is None for row in daily)
    assert all(row["cost"] is None and row["profit"] is None for row in daily)

    report = compute_pnl_report(clean, "All Time")
    assert report.total_transactions == 2
    assert report.category_ledger == []
    assert sum(line.amount or 0 for line in report.pnl) == 4000.0
    ledger = build_ledger_page(clean, page=1, page_size=10)
    assert len(ledger.entries) == 2
    assert ledger.entries[0].revenue == 1500.0
    assert ledger.entries[0].quantity is None
    assert ledger.entries[0].profit is None


def test_partial_quantity_uses_line_total_fallback_without_cast_crash():
    raw = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02"],
        "Quantity": [2, None],
        "Selling Price": [100, None],
        "Line Total": [200, 750],
    })
    clean, errors = normalize_dataframe(
        raw,
        column_mapping={
            "Date": "Date",
            "Quantity": "Quantity",
            "Selling Price": "Selling Price",
            "Line Total": "Line Total",
        },
    )
    assert len(errors) == 0
    assert len(clean) == 2
    assert pd.isna(clean.iloc[1]["Quantity"])
    summary = compute_summary_between(clean, clean.iloc[0:0])
    assert summary.revenue.value == 950.0
    assert summary.units_sold.available is False


def test_csv_read_preserves_leading_zeroes_and_cleanup_removes_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(file_handler, "UPLOAD_DIR", str(tmp_path))
    raw_csv = b"Date,Order ID,Line Total\n2026-03-01,00101,500\n2026-03-02,00102,700\n"
    file_id = file_handler.save_upload(raw_csv, "orders.csv", "owner@test")
    frame = file_handler.read_to_dataframe(file_id)
    assert frame["Order ID"].tolist() == ["00101", "00102"]

    file_handler.save_extra_registry(file_id, {"x_col:order_id": {"role": "stored_only"}})
    registry_path = tmp_path / f"{file_id}.registry.json"
    assert registry_path.exists()
    file_handler.cleanup(file_id)
    assert not registry_path.exists()
    assert not (tmp_path / f"{file_id}.meta.json").exists()


def test_date_line_total_long_history_forecast_and_pnl_degrade_honestly():
    """Path A must still work when inventory/item forecast fields are absent."""
    raw = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d"),
        "Line Total": [1000 + 25 * i for i in range(30)],
    })
    clean, errors = normalize_dataframe(raw, column_mapping={"Date": "Date", "Line Total": "Line Total"})
    assert not errors
    assert len(clean) == 30

    forecast = compute_forecast(clean, horizon_days=7)
    assert forecast.available is True
    assert len(forecast.item_forecasts) == 0

    report = compute_pnl_report(clean, "All Time")
    cost = next(line for line in report.pnl if line.label == "Cost of Goods Sold (COGS)")
    profit = next(line for line in report.pnl if line.label == "Gross Profit")
    assert cost.amount is None and "needs Quantity and Cost Price" in cost.availability_reason
    assert profit.amount is None and "needs Quantity and Cost Price" in profit.availability_reason


@pytest.mark.asyncio
async def test_path_a_confirmed_upload_supports_report_and_pdf_endpoints():
    """Exercise the full report builder with no optional inventory columns."""
    raw = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d"),
        "Line Total": [1000 + 25 * i for i in range(30)],
    })
    csv_buffer = io.StringIO()
    raw.to_csv(csv_buffer, index=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        upload = await client.post(
            "/upload/",
            files={"file": ("path_a.csv", csv_buffer.getvalue().encode("utf-8"), "text/csv")},
            data={"ai_consent": "false"},
        )
        assert upload.status_code == 201, upload.text
        file_id = upload.json()["file_id"]
        confirmed = await client.post(
            f"/upload/{file_id}/confirm-mapping",
            json={"mapping": {"Date": "Date", "Line Total": "Line Total"}},
        )
        assert confirmed.status_code == 200, confirmed.text

        report = await client.get(f"/analytics/{file_id}/report", params={"time_filter": "all"})
        assert report.status_code == 200, report.text
        lines = report.json()["pnl"]
        cogs = next(line for line in lines if line["label"] == "Cost of Goods Sold (COGS)")
        assert cogs["amount"] is None
        assert "needs Quantity and Cost Price" in cogs["availability_reason"]

        forecast = await client.post(
            f"/analytics/{file_id}/forecast",
            json={"time_filter": "all", "horizon": 7},
        )
        assert forecast.status_code == 200, forecast.text
        assert forecast.json()["available"] is True
        assert forecast.json()["item_forecasts"] == []

        pdf = await client.get(f"/analytics/{file_id}/report.pdf", params={"time_filter": "all"})
        assert pdf.status_code == 200, pdf.text[:500]
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")


def test_pii_date_column_is_classified_personal_and_redacted():
    raw = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02"],
        "Line Total": [100, 200],
        "Customer DOB": ["1992-05-04", "1988-11-13"],
    })
    clean, errors = normalize_dataframe(
        raw,
        column_mapping={"Date": "Date", "Line Total": "Line Total"},
    )
    assert not errors
    key = "x_col:customer_dob"
    assert clean.attrs["extra_registry"][key]["class_name"] == "personal"
    assert clean.attrs["extra_registry"][key]["role"] == "stored_only"
    assert clean[key].tolist() == ["[redacted]", "[redacted]"]


def test_extra_measure_missing_cells_are_not_silently_zero_filled():
    raw = pd.DataFrame({
        "Date": ["2026-03-01", "2026-03-02", "2026-03-03"],
        "Line Total": [100, 200, 300],
        "GST %": [5.0, None, 18.0],
    })
    clean, errors = normalize_dataframe(
        raw,
        column_mapping={"Date": "Date", "Line Total": "Line Total"},
    )
    key = "x_meas:gst_pct"
    assert pd.isna(clean.loc[1, key])
    clean.attrs["extra_registry"] = clean.attrs["extra_registry"]
    from app.services.query_engine import aggregate, heatmap, QueryError
    with pytest.raises(QueryError, match="blank or non-numeric"):
        aggregate(clean, dimension="day", measure=key)
    with pytest.raises(QueryError, match="blank or non-numeric"):
        heatmap(clean, measure=key)


def test_average_extra_measure_other_bucket_uses_weighted_average():
    """Folded 'Other' must average underlying rows, never sum group averages."""
    from app.services.query_engine import aggregate

    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-03-01"] * 12),
        "Line Total": [100.0] * 12,
        "x_dim:store": [f"Store {i}" for i in range(1, 13)],
        "x_meas:gst_pct": [float(i) for i in range(1, 13)],
    })
    frame.attrs["extra_registry"] = {
        "x_dim:store": {
            "display_label": "Store", "role": "extra_dimension", "class_name": "low_cardinality_text"
        },
        "x_meas:gst_pct": {
            "display_label": "GST %", "role": "extra_measure", "class_name": "numeric", "aggregation": "avg"
        },
    }
    result = aggregate(frame, dimension="x_dim:store", measure="x_meas:gst_pct", top_n=10)
    assert result.total == pytest.approx(6.5)
    other = next(point for point in result.points if point.label.startswith("Other"))
    assert other.value == pytest.approx(1.5)
