import pandas as pd

def compute_discount(frame: pd.DataFrame) -> dict:
    """Compute discount totals without treating missing inputs as a real zero.

    A mapped Discount column supplies the amount directly. Otherwise the amount
    can be derived from MRP, Selling Price and Quantity. Discount percentage is
    only meaningful when the MRP basis exists; when it does not, return None so
    reports can render an em dash instead of a fabricated 0%.
    """
    result = {
        "discount_given": 0.0,
        "discount_pct": None,
        "valid_discount_rows": 0,
        "missing_mrp_rows": 0,
        "price_above_mrp_rows": 0,
    }

    if frame.empty:
        return result

    has_direct_discount = "Discount" in frame.columns
    direct_discount = None
    if has_direct_discount:
        direct_discount = pd.to_numeric(frame["Discount"], errors="coerce").fillna(0.0).clip(lower=0.0)
        result["discount_given"] = float(direct_discount.sum())

    required = {"MRP", "Selling Price", "Quantity"}
    if not required.issubset(frame.columns):
        result["missing_mrp_rows"] = len(frame) if "MRP" not in frame.columns else int(
            (frame["MRP"].isna() | (frame["MRP"] <= 0)).sum()
        )
        return result

    mrp = pd.to_numeric(frame["MRP"], errors="coerce")
    selling = pd.to_numeric(frame["Selling Price"], errors="coerce")
    quantity = pd.to_numeric(frame["Quantity"], errors="coerce")
    missing_mrp = mrp.isna() | (mrp <= 0)
    result["missing_mrp_rows"] = int(missing_mrp.sum())

    price_above_mrp = (~missing_mrp) & selling.notna() & (selling > mrp)
    result["price_above_mrp_rows"] = int(price_above_mrp.sum())
    discountable = (~missing_mrp) & selling.notna() & quantity.notna() & (selling <= mrp)
    result["valid_discount_rows"] = int(discountable.sum())

    if result["valid_discount_rows"] > 0:
        if direct_discount is not None:
            discount_amount = float(direct_discount[discountable].sum())
        else:
            discount_amount = float(((mrp[discountable] - selling[discountable]) * quantity[discountable]).sum())
            result["discount_given"] = discount_amount

        total_mrp = float((mrp[discountable] * quantity[discountable]).sum())
        if total_mrp > 0:
            result["discount_pct"] = float((discount_amount / total_mrp) * 100)

    return result

def compute_discount_vs_margin(frame: pd.DataFrame, top_n: int = 15) -> list[dict]:
    """
    Computes a breakdown of Discount % vs Margin % per Item for the top N items 
    by revenue that have valid MRP discounts.
    """
    required_columns = {"Item", "MRP", "Selling Price", "Cost Price", "Quantity"}
    if frame.empty or not required_columns.issubset(frame.columns):
        # This analysis is optional. A valid Date + Line Total upload may not
        # have these fields, so return no rows instead of raising KeyError.
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
