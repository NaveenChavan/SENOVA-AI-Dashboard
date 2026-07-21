import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# File Settings
NUM_ROWS = 25000
START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 6, 25) # Mahine ke aakhir mein taaki 7 days aur month alag aayein

CATALOG = [
    {"Item": "Formal Shirt", "Category": "Shirts", "Cost": 400, "Price": 899},
    {"Item": "Cotton Polo", "Category": "Shirts", "Cost": 250, "Price": 599},
    {"Item": "Blue Denim Regular", "Category": "Jeans", "Cost": 700, "Price": 1499},
    {"Item": "Ripped Jeans", "Category": "Jeans", "Cost": 800, "Price": 1799},
    {"Item": "Formal Trousers", "Category": "Trousers", "Cost": 600, "Price": 1299},
    {"Item": "Bomber Jacket", "Category": "Jackets", "Cost": 1200, "Price": 2499},
    {"Item": "Leather Belt", "Category": "Accessories", "Cost": 150, "Price": 499},
    # DEAD STOCK CANDIDATE:
    {"Item": "Winter Wool Scarf", "Category": "Accessories", "Cost": 200, "Price": 399}
]

days_diff = (END_DATE - START_DATE).days
random_days = np.random.randint(0, days_diff + 1, NUM_ROWS)
dates = [START_DATE + timedelta(days=int(d)) for d in random_days]

data = []
for date in dates:
    # Scarf sirf January aur February mein bikega
    if date.month > 2:
        available_catalog = CATALOG[:-1] 
    else:
        available_catalog = CATALOG
        
    product = random.choice(available_catalog)
    qty = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
    
    # Slight discount for realistic numbers
    price_variation = random.uniform(0.9, 1.0)
    
    data.append({
        "Date": date.strftime("%Y-%m-%d"),
        "Item": product["Item"],
        "Category": product["Category"],
        "Quantity": qty,
        "Selling Price": round(product["Price"] * price_variation, 2),
        "Cost Price": product["Cost"]
    })

df = pd.DataFrame(data)
df.sort_values(by="Date", inplace=True)
filename = "senova_ultimate_test_25k.csv"
df.to_csv(filename, index=False)

print(f"Done! {filename} generated successfully.")
print(f"Total Rows: {len(df)}")
print(f"Date Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")