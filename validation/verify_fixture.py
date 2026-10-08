"""Independent C2 fixture validation; does not import the incomplete app bundle."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "testing2" / "03_electronics_shopify_orders.csv"

df = pd.read_csv(CSV)
df["Date"] = pd.to_datetime(df["Ordered On"])
df["Revenue"] = df["Lineitem quantity"] * df["Lineitem price"]
df["Cost"] = df["Lineitem quantity"] * df["Unit Cost"]
df["Profit"] = df["Revenue"] - df["Cost"]

max_day = df["Date"].dt.normalize().max()
latest = df[df["Date"].dt.normalize() == max_day]
assert len(latest) == 7
assert latest["Revenue"].sum() == 49180
assert latest["Profit"].sum() == 19750

latest_power = latest[latest["Product type"] == "Power"]
assert len(latest_power) == 2
assert latest_power["Revenue"].sum() == 13893

start = pd.Timestamp("2026-03-19")
end = pd.Timestamp("2026-04-17")
custom_power = df[
    (df["Date"].dt.normalize() >= start)
    & (df["Date"].dt.normalize() <= end)
    & (df["Product type"] == "Power")
]
assert len(custom_power) == 60
assert custom_power["Revenue"].sum() == 510327
assert custom_power["Cost"].sum() == 301950
assert custom_power["Profit"].sum() == 208377
assert custom_power["Lineitem quantity"].sum() == 273

print("C2 fixture validation: PASS")
print("Latest day: 2026-06-17 | rows=7 | revenue=49180 | profit=19750")
print("Latest day + Power: rows=2 | revenue=13893")
print("2026-03-19..2026-04-17 + Power: rows=60 | revenue=510327 | cost=301950 | profit=208377 | units=273")
