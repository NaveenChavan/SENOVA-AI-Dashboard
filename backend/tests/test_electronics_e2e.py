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
    assert sum(p.value for p in res.points) == 1211000
