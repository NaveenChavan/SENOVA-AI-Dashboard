import pandas as pd

def compute_discount(frame: pd.DataFrame) -> dict:
    """
    Computes overall MRP-based discount metrics and validity breakdowns 
    for a given slice of data.
    
    This is a pure read-only function that does not alter the DataFrame 
    or core metrics like Revenue, Cost, and Profit.
    """
    result = {
        "discount_given": 0.0,
        "discount_pct": 0.0,
        "valid_discount_rows": 0,
        "missing_mrp_rows": 0,
        "price_above_mrp_rows": 0,
    }

    if frame.empty or "MRP" not in frame.columns or "Selling Price" not in frame.columns or "Quantity" not in frame.columns:
        return result

    # Identify breakdown states
    missing_mrp = frame["MRP"].isna() | (frame["MRP"] <= 0)
    result["missing_mrp_rows"] = int(missing_mrp.sum())
    
    # Valid MRPs but selling price is weirdly > MRP
    valid_mrp_mask = ~missing_mrp
    price_above_mrp = valid_mrp_mask & (frame["Selling Price"] > frame["MRP"])
    result["price_above_mrp_rows"] = int(price_above_mrp.sum())

    # Valid discountable rows (Selling Price <= MRP)
    # We only calculate discount where Selling Price <= MRP
    discountable = valid_mrp_mask & (frame["Selling Price"] <= frame["MRP"])
    result["valid_discount_rows"] = int(discountable.sum())

    if result["valid_discount_rows"] > 0:
        disc_rows = frame[discountable]
        # Total discount in Rs
        discount_given = ((disc_rows["MRP"] - disc_rows["Selling Price"]) * disc_rows["Quantity"]).sum()
        result["discount_given"] = float(discount_given)
        
        # Total MRP of the discounted rows
        total_mrp = (disc_rows["MRP"] * disc_rows["Quantity"]).sum()
        if total_mrp > 0:
            result["discount_pct"] = float((discount_given / total_mrp) * 100)

    return result

def compute_discount_vs_margin(frame: pd.DataFrame, top_n: int = 15) -> list[dict]:
    """
    Computes a breakdown of Discount % vs Margin % per Item for the top N items 
    by revenue that have valid MRP discounts.
    """
    if frame.empty or "MRP" not in frame.columns:
        return []
        
    valid_mrp = frame["MRP"].notna() & (frame["MRP"] > 0)
    discountable = valid_mrp & (frame["Selling Price"] <= frame["MRP"])
    
    df = frame[discountable].copy()
    if df.empty:
        return []
        
    df["_revenue"] = df["Quantity"] * df["Selling Price"]
    df["_cost"] = df["Quantity"] * df["Cost Price"]
    df["_mrp_total"] = df["Quantity"] * df["MRP"]
    df["_discount"] = df["_mrp_total"] - df["_revenue"]
    
    grouped = df.groupby("Item", as_index=False).agg({
        "_revenue": "sum",
        "_cost": "sum",
        "_mrp_total": "sum",
        "_discount": "sum"
    })
    
    grouped["_discount_pct"] = (grouped["_discount"] / grouped["_mrp_total"] * 100).fillna(0.0)
    
    # Sort by discount % descending, take top_n
    grouped = grouped.sort_values("_discount_pct", ascending=False).head(top_n)
    
    results = []
    for _, row in grouped.iterrows():
        rev = row["_revenue"]
        cost = row["_cost"]
        mrp = row["_mrp_total"]
        disc = row["_discount"]
        
        margin_pct = ((rev - cost) / rev * 100) if rev > 0 else 0.0
        disc_pct = (disc / mrp * 100) if mrp > 0 else 0.0
        
        results.append({
            "item": row["Item"],
            "discount_pct": round(disc_pct, 2),
            "margin_pct": round(margin_pct, 2),
            "revenue": round(rev, 2)
        })
        
    return results
