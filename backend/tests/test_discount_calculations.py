import pandas as pd
import pytest

from app.services.discount_calculations import compute_discount, compute_discount_vs_margin

def test_compute_discount_valid():
    df = pd.DataFrame({
        "MRP": [100, 200, 150],
        "Selling Price": [90, 200, 100],
        "Quantity": [2, 1, 3],
        "Cost Price": [50, 150, 80]
    })
    
    # Rows:
    # 1. MRP 100, SP 90, Qty 2 -> Discountable. Disc = (100-90)*2 = 20. MRP_total = 200
    # 2. MRP 200, SP 200, Qty 1 -> Discountable (SP <= MRP). Disc = 0. MRP_total = 200
    # 3. MRP 150, SP 100, Qty 3 -> Discountable. Disc = (150-100)*3 = 150. MRP_total = 450
    # Total Disc = 20 + 0 + 150 = 170
    # Total MRP = 200 + 200 + 450 = 850
    # Disc % = 170 / 850 = 20.0%
    
    res = compute_discount(df)
    assert res["valid_discount_rows"] == 3
    assert res["missing_mrp_rows"] == 0
    assert res["price_above_mrp_rows"] == 0
    assert res["discount_given"] == 170.0
    assert res["discount_pct"] == 20.0

def test_compute_discount_missing_mrp():
    df = pd.DataFrame({
        "MRP": [100, None, 0, 150],
        "Selling Price": [90, 80, 50, 100],
        "Quantity": [1, 1, 1, 1]
    })
    res = compute_discount(df)
    assert res["missing_mrp_rows"] == 2  # None and 0
    assert res["valid_discount_rows"] == 2

def test_compute_discount_price_above_mrp():
    df = pd.DataFrame({
        "MRP": [100, 200],
        "Selling Price": [150, 180],
        "Quantity": [1, 1]
    })
    res = compute_discount(df)
    assert res["price_above_mrp_rows"] == 1  # 150 > 100
    assert res["valid_discount_rows"] == 1   # 180 <= 200

def test_compute_discount_empty_or_missing_columns():
    # Empty
    assert compute_discount(pd.DataFrame())["discount_given"] == 0.0
    
    # Missing MRP
    assert compute_discount(pd.DataFrame({"Selling Price": [10], "Quantity": [1]}))["discount_given"] == 0.0

def test_compute_discount_vs_margin():
    df = pd.DataFrame({
        "Item": ["A", "B", "C"],
        "MRP": [100, 200, 150],
        "Selling Price": [90, 150, 160],  # C has SP > MRP, will be excluded
        "Cost Price": [50, 100, 80],
        "Quantity": [10, 5, 2]
    })
    
    # Item A:
    # SP=90, CP=50, Q=10. Rev=900, Cost=500. Margin = (900-500)/900 = 44.44%
    # MRP=100. Total MRP=1000. Disc = 1000-900 = 100. Disc% = 10%
    # Item B:
    # SP=150, CP=100, Q=5. Rev=750, Cost=500. Margin = 250/750 = 33.33%
    # MRP=200. Total MRP=1000. Disc = 1000-750 = 250. Disc% = 25%
    # Item C is excluded
    
    res = compute_discount_vs_margin(df)
    assert len(res) == 2
    
    # Sorted by discount_pct descending, so B (25%) then A (10%)
    assert res[0]["item"] == "B"
    assert res[0]["margin_pct"] == 33.33
    assert res[0]["discount_pct"] == 25.0
    assert res[0]["revenue"] == 750.0
    
    assert res[1]["item"] == "A"
    assert res[1]["margin_pct"] == 44.44
    assert res[1]["discount_pct"] == 10.0
    assert res[1]["revenue"] == 900.0
