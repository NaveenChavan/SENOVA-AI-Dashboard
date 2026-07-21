import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# Configuration
NUM_ROWS = 50000
FILENAME = "senova_stress_test_50k.csv"

# Garment Store Master Data
CATEGORIES = {
    "Shirts": ["Formal Shirt", "Casual Checked Shirt", "Linen Solid Shirt", "Cotton Polo"],
    "Trousers": ["Formal Chinos", "Slim Fit Trouser", "Cotton Joggers"],
    "Jeans": ["Blue Denim Regular", "Black Slim Fit Jeans", "Ripped Denim"],
    "Accessories": ["Leather Belt", "Cotton Socks (Pack of 3)", "Silk Tie"],
    "Jackets": ["Denim Jacket", "Bomber Jacket", "Fleece Hoodie"]
}

# Pricing Logic (Cost, Selling)
PRICE_MAP = {
    "Formal Shirt": (400, 899), "Casual Checked Shirt": (350, 799), "Linen Solid Shirt": (500, 1199), "Cotton Polo": (250, 599),
    "Formal Chinos": (600, 1299), "Slim Fit Trouser": (550, 1199), "Cotton Joggers": (450, 999),
    "Blue Denim Regular": (700, 1499), "Black Slim Fit Jeans": (750, 1599), "Ripped Denim": (800, 1699),
    "Leather Belt": (150, 499), "Cotton Socks (Pack of 3)": (80, 199), "Silk Tie": (120, 349),
    "Denim Jacket": (1000, 2499), "Bomber Jacket": (1200, 2999), "Fleece Hoodie": (800, 1899)
}

print(f"Generating {NUM_ROWS} rows of test data...")

data = []
start_date = datetime.now() - timedelta(days=180) # 6 months of data

for _ in range(NUM_ROWS):
    category = random.choice(list(CATEGORIES.keys()))
    item = random.choice(CATEGORIES[category])
    cost_price, base_selling_price = PRICE_MAP[item]
    
    # Introduce random discounts/fluctuations
    selling_price = base_selling_price * random.uniform(0.85, 1.0)
    
    # Heavier sales volume on weekends
    random_days = random.randint(0, 180)
    date_val = start_date + timedelta(days=random_days)
    qty = random.randint(1, 3) if date_val.weekday() < 5 else random.randint(2, 6)

    data.append({
        "Date": date_val.strftime("%Y-%m-%d"),
        "Item": item,
        "Category": category,
        "Quantity": qty,
        "Selling Price": round(selling_price, 2),
        "Cost Price": cost_price
    })

df = pd.DataFrame(data)
df = df.sort_values(by="Date")
df.to_csv(FILENAME, index=False)
print(f"Done! File saved as {FILENAME}. File size: ~{df.memory_usage(deep=True).sum() / (1024*1024):.2f} MB")