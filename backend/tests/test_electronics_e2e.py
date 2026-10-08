import pandas as pd
import pytest
from app.utils.data_validator import normalize_dataframe
from app.services.tier1_classifier import classify_columns
from app.services.discount_calculations import compute_discount, compute_discount_vs_margin

import os

def test_electronics_csv_discount_logic():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    csv_path = os.path.join(base_dir, "testing2", "03_electronics_shopify_orders.csv")
    df = pd.read_csv(csv_path)
    
    # Simulate user mapping columns based on classify_columns
    mapping = {}
    guesses = classify_columns(df)
    for guess in guesses:
        if guess.canonical:
            mapping[guess.raw_column] = guess.canonical
            
    # "MRP" should be mapped to "MRP"
    assert mapping["MRP"] == "MRP"
    # "Lineitem price" mapped to "Selling Price"
    assert mapping["Lineitem price"] == "Selling Price"
    # "Unit Cost" to "Cost Price"
    assert mapping["Unit Cost"] == "Cost Price"
    # "Lineitem quantity" to "Quantity"
    assert mapping["Lineitem quantity"] == "Quantity"
    
    valid, errors = normalize_dataframe(df, mapping)
    assert not errors
    
    res = compute_discount(valid)
    assert res["valid_discount_rows"] > 0
    assert res["missing_mrp_rows"] == 0
    assert res["price_above_mrp_rows"] == 0
    assert res["discount_given"] > 0
    assert res["discount_pct"] > 0
    
    chart = compute_discount_vs_margin(valid)
    assert len(chart) > 0
    assert "item" in chart[0]
    assert "discount_pct" in chart[0]
    assert "margin_pct" in chart[0]

def test_electronics_query_engine_discount():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    csv_path = os.path.join(base_dir, "testing2", "03_electronics_shopify_orders.csv")
    df = pd.read_csv(csv_path)
    
    mapping = {}
    guesses = classify_columns(df)
    for guess in guesses:
        if guess.canonical:
            mapping[guess.raw_column] = guess.canonical
            
    valid, errors = normalize_dataframe(df, mapping)
    
    from app.services.query_engine import aggregate
    res = aggregate(valid, dimension="category", measure="discount")

def test_electronics_new_insights():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    csv_path = os.path.join(base_dir, "testing2", "03_electronics_shopify_orders.csv")
    df = pd.read_csv(csv_path)
    
    mapping = {}
    guesses = classify_columns(df)
    for guess in guesses:
        if guess.canonical:
            mapping[guess.raw_column] = guess.canonical
            
    valid, errors = normalize_dataframe(df, mapping)
    
    from app.services.insights_engine import compute_insights
    from app.services.sales_calculations import _prepare
    prepped = _prepare(valid)
    # create empty df for previous period
    prev_prepped = prepped.iloc[0:0]
    insights = compute_insights(prepped, prev_prepped, period_label="all")
    
    insight_kinds = [i.kind for i in insights.insights]
    
    assert "discount_leader" in insight_kinds
    assert "margin_gap" in insight_kinds
    assert "payment_mix" in insight_kinds
    
    dl = next(i for i in insights.insights if i.kind == "discount_leader")
    assert dl.metrics["discount_pct"] > 0
    
    mg = [i for i in insights.insights if i.kind == "margin_gap"]
    assert len(mg) > 0
    
    pm = next(i for i in insights.insights if i.kind == "payment_mix")
    assert pm.metrics["share_pct"] >= 50

def test_electronics_tier2_zero_calls():
    import asyncio
    from app.services.column_understanding import analyse
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    csv_path = os.path.join(base_dir, "testing2", "03_electronics_shopify_orders.csv")
    df = pd.read_csv(csv_path)

    async def run_analyse():
        return await analyse(df, ai_consent=True)

    # FastEmbed is generally not available in CI, so this natively tests the fallback.
    reports, timings, notice, reason_code = asyncio.run(run_analyse())
    
    # Verify no time was spent in Tier 2
    assert timings.tier2_ms == 0.0

    # Verify Currency, Notes, Order Status are all recognised and marked unused
    for col in ["Currency", "Order Status", "Notes"]:
        report = next(r for r in reports if r["raw_column"] == col)
        assert report["recognised_unused"] is True
        assert report["needs_review"] is False
        assert report["source"] == "local"
