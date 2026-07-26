"""
Generate the six format-torture test files in ``testing2/``.

Each file is a different **business category** *and* a different **export
format**, so uploading all six answers one question: how many real-world shapes
can SENOVA's column mapper and validator actually handle?

Run from the repository root or from this folder::

    py -3 testing2/generate_testing2.py

Everything is generated from fixed seeds, so the files (and therefore the numbers
you see in the dashboard) are reproducible.

    file                                    category        format torture-test
    ─────────────────────────────────────── ─────────────── ──────────────────────────────
    01_garment_tally_export.csv             Garment shop    Tally headers, DD-MM-YYYY
    02_grocery_gst_invoice.csv              Grocery/kirana  Line total only (no unit price),
                                                            discount + GST, ₹ with commas
    03_electronics_shopify_orders.csv       Electronics     Marketplace headers, ISO dates,
                                                            unmapped junk columns
    04_pharmacy_marg_stock.xlsx             Pharmacy        Excel, stock on hand, branches,
                                                            salespeople
    05_restaurant_pos_semicolon.csv         Restaurant      Semicolon-delimited + dirty rows
                                                            (bad dates, zero qty, blanks)
    06_footwear_boutique_wide.csv           Footwear        18 columns: brand/size/colour/
                                                            payment/customer, sparse trading
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent


def _write_csv(name: str, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    """Write one file and report its size, so the caller can print a summary."""
    path = OUT_DIR / name
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _inr(value: float) -> str:
    """``1234567.5`` → ``"12,34,567.50"`` — Indian grouping, as real exports print it."""
    negative = value < 0
    whole, fraction = divmod(round(abs(value) * 100), 100)
    text = f"{whole:d}"
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        text = f"{','.join(groups)},{tail}"
    return f"{'-' if negative else ''}{text}.{fraction:02d}"


# ── 1. Garment shop — a Tally sales register ────────────────────────────────
# Torture test: Tally's own header names, DD-MM-YYYY dates, a unit rate and a
# purchase rate, and nothing else. This is the baseline "clean but foreign
# headers" case, and it must land in demand-only inventory mode (no stock column).
def build_garment_tally() -> tuple[str, int]:
    rng = np.random.default_rng(101)
    start = date(2026, 1, 1)
    catalogue = [
        ("Cotton Kurta - M", "Kurta", 320.0, 799.0, 7),
        ("Cotton Kurta - L", "Kurta", 320.0, 799.0, 6),
        ("Silk Saree", "Saree", 1850.0, 3499.0, 2),
        ("Chiffon Saree", "Saree", 900.0, 1999.0, 3),
        ("Formal Shirt", "Shirt", 430.0, 949.0, 5),
        ("Denim Jeans", "Jeans", 720.0, 1599.0, 4),
        ("Woollen Shawl", "Shawl", 950.0, 1799.0, 2),
        ("Party Gown", "Gown", 2100.0, 4299.0, 1),
    ]

    rows = []
    for offset in range(120):
        day = start + timedelta(days=offset)
        # Sundays closed; Saturdays busy — gives the weekday insight real signal.
        if day.weekday() == 6:
            continue
        uplift = 1.7 if day.weekday() == 5 else 1.0
        for item, group, cost, rate, base in catalogue:
            # The shawl only sells in the first six weeks (winter) → dead stock.
            if group == "Shawl" and offset > 42:
                continue
            units = int(round(base * uplift * rng.uniform(0.5, 1.5)))
            if units <= 0:
                continue
            rows.append(
                [
                    day.strftime("%d-%m-%Y"),
                    f"SL/{offset + 1:04d}",
                    item,
                    group,
                    units,
                    f"{rate:.2f}",
                    f"{cost:.2f}",
                    "Cash" if units % 2 else "UPI",
                ]
            )

    header = [
        "Voucher Date",
        "Voucher No",
        "Particulars",
        "Stock Group",
        "Qty.",
        "Rate/Unit",
        "Purchase Rate",
        "Payment Mode",
    ]
    _write_csv("01_garment_tally_export.csv", header, rows)
    return "01_garment_tally_export.csv", len(rows)


# ── 2. Grocery / kirana — a GST invoice register ────────────────────────────
# Torture test: there is **no unit price column at all**. "Taxable Value" is a
# line total, so the unit price has to be derived as total ÷ quantity — mapping it
# to Selling Price would multiply revenue by the quantity a second time. Also:
# ₹ amounts written with commas, a discount column, GST, and a bill number.
def build_grocery_gst() -> tuple[str, int]:
    rng = np.random.default_rng(202)
    start = date(2026, 2, 1)
    catalogue = [
        ("Toor Dal 1kg", "Pulses", 118.0, 149.0, 12),
        ("Basmati Rice 5kg", "Grains", 460.0, 599.0, 4),
        ("Sunflower Oil 1L", "Edible Oil", 128.0, 165.0, 9),
        ("Amul Butter 500g", "Dairy", 245.0, 285.0, 5),
        ("Tata Salt 1kg", "Staples", 22.0, 28.0, 15),
        ("Detergent 1kg", "Household", 96.0, 139.0, 6),
        ("Biscuits Pack", "Snacks", 75.0, 110.0, 11),
    ]

    rows = []
    bill_no = 4001
    for offset in range(150):
        day = start + timedelta(days=offset)
        for item, category, cost, price, base in catalogue:
            units = int(round(base * rng.uniform(0.4, 1.6)))
            if units <= 0:
                continue
            gross = units * price
            # Kirana shops round the bill down; that becomes the discount line.
            discount = round(gross * rng.choice([0.0, 0.0, 0.02, 0.05]), 2)
            taxable = gross - discount
            gst = round(taxable * (0.05 if category in {"Pulses", "Grains", "Dairy"} else 0.18), 2)
            rows.append(
                [
                    f"INV-{bill_no}",
                    day.strftime("%d/%m/%Y"),
                    item,
                    category,
                    "HSN" + str(1000 + (bill_no % 90)),
                    units,
                    f"₹ {_inr(taxable)}",   # LINE TOTAL, not a unit price
                    f"₹ {_inr(discount)}",
                    f"₹ {_inr(gst)}",
                    f"{cost:.2f}",
                    "Counter Sale",
                ]
            )
            bill_no += 1

    header = [
        "Bill No",
        "Bill Date",
        "Item Name",
        "Item Group",
        "HSN Code",
        "Billed Qty",
        "Taxable Value",
        "Discount",
        "GST Amount",
        "Purchase Rate",
        "Customer",
    ]
    _write_csv("02_grocery_gst_invoice.csv", header, rows)
    return "02_grocery_gst_invoice.csv", len(rows)


# ── 3. Electronics — a marketplace order export ─────────────────────────────
# Torture test: Shopify/Amazon-style headers, ISO YYYY-MM-DD dates, a currency
# code column and three columns that must be *ignored* (Order Status, Fulfilment,
# Notes). Also two candidate price columns (Lineitem price and MRP) so the mapping
# screen has to make the user choose.
def build_electronics_marketplace() -> tuple[str, int]:
    rng = np.random.default_rng(303)
    start = date(2026, 3, 10)
    catalogue = [
        ("Wireless Mouse", "Accessories", 780.0, 1299.0, 1499.0, 6),
        ("USB-C Hub 7-in-1", "Accessories", 1240.0, 1899.0, 2299.0, 4),
        ("Bluetooth Speaker", "Audio", 1450.0, 2499.0, 2999.0, 3),
        ("ANC Headphones", "Audio", 3200.0, 5499.0, 6999.0, 2),
        ("65W GaN Charger", "Power", 980.0, 1699.0, 1999.0, 5),
        ("Power Bank 20000mAh", "Power", 1350.0, 2199.0, 2699.0, 3),
        ("1080p Webcam", "Video", 1750.0, 2899.0, 3499.0, 2),
    ]

    rows = []
    order = 90001
    for offset in range(100):
        day = start + timedelta(days=offset)
        for item, product_type, cost, price, mrp, base in catalogue:
            units = int(round(base * rng.uniform(0.3, 1.8)))
            if units <= 0:
                continue
            rows.append(
                [
                    f"#{order}",
                    day.isoformat(),
                    item,
                    product_type,
                    units,
                    f"{price:.2f}",
                    f"{mrp:.2f}",
                    f"{cost:.2f}",
                    "INR",
                    rng.choice(["Prepaid", "COD"]),
                    "fulfilled",
                    "shipped from Mumbai warehouse",
                ]
            )
            order += 1

    header = [
        "Order ID",
        "Ordered On",
        "Lineitem name",
        "Product type",
        "Lineitem quantity",
        "Lineitem price",
        "MRP",
        "Unit Cost",
        "Currency",
        "Payment Method",
        "Order Status",
        "Notes",
    ]
    _write_csv("03_electronics_shopify_orders.csv", header, rows)
    return "03_electronics_shopify_orders.csv", len(rows)


# ── 4. Pharmacy — a Marg-style Excel stock register ─────────────────────────
# Torture test: an .xlsx file (not CSV), real datetime cells rather than strings,
# and a **Closing Stock** column — the one thing that unlocks stock-aware
# inventory (days of cover, reorder alerts, capital locked). Two branches and
# three salespeople give the filter panel something to slice by.
def build_pharmacy_excel() -> tuple[str, int]:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - openpyxl ships with the backend
        raise SystemExit("openpyxl is required for the Excel file: pip install openpyxl") from exc

    rng = np.random.default_rng(404)
    start = date(2026, 1, 15)
    catalogue = [
        ("Paracetamol 500mg", "Tablets", 14.0, 22.0, 40, 26),
        ("Amoxicillin 250mg", "Antibiotics", 68.0, 96.0, 18, 12),
        ("Cough Syrup 100ml", "Syrups", 78.0, 112.0, 12, 9),
        ("Insulin Pen", "Injectables", 620.0, 845.0, 3, 4),
        ("Vitamin D3 Sachet", "Supplements", 32.0, 55.0, 22, 15),
        ("Digital Thermometer", "Devices", 210.0, 349.0, 2, 6),
        ("Glucometer Strips", "Devices", 480.0, 699.0, 4, 3),
    ]
    branches = ["Main Store", "Hospital Road"]
    staff = ["Ravi", "Sneha", "Imran"]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sales Register"
    header = [
        "Invoice Date",
        "Bill No",
        "Item Name",
        "Category",
        "Qty",
        "MRP",
        "Purchase Rate",
        "Closing Stock",
        "Godown",
        "Salesman",
    ]
    sheet.append(header)

    count = 0
    bill = 7001
    for offset in range(110):
        day = start + timedelta(days=offset)
        for item, category, cost, mrp, stock, base in catalogue:
            units = int(round(base * rng.uniform(0.3, 1.7)))
            if units <= 0:
                continue
            sheet.append(
                [
                    day,  # a real date cell, not a string
                    f"B{bill}",
                    item,
                    category,
                    units,
                    mrp,
                    cost,
                    int(max(stock + rng.integers(-3, 4), 0)),
                    str(rng.choice(branches)),
                    str(rng.choice(staff)),
                ]
            )
            bill += 1
            count += 1

    for column, width in zip("ABCDEFGHIJ", (13, 10, 22, 14, 7, 9, 14, 14, 15, 12)):
        sheet.column_dimensions[column].width = width

    workbook.save(OUT_DIR / "04_pharmacy_marg_stock.xlsx")
    return "04_pharmacy_marg_stock.xlsx", count


# ── 5. Restaurant — a POS export with dirty rows ────────────────────────────
# Torture test: **semicolon-delimited** (the delimiter sniffer has to spot it) and
# deliberately dirty — unparseable dates, zero and negative quantities, blank
# categories, a text price, and one row selling below cost (legitimate, must be
# kept). Exercises row-level validation and the "partial success" banner.
def build_restaurant_dirty() -> tuple[str, int, int]:
    rng = np.random.default_rng(505)
    start = date(2026, 4, 1)
    catalogue = [
        ("Veg Thali", "Main Course", 95.0, 199.0, 14),
        ("Paneer Butter Masala", "Main Course", 130.0, 289.0, 8),
        ("Masala Dosa", "South Indian", 45.0, 129.0, 16),
        ("Cold Coffee", "Beverages", 38.0, 119.0, 12),
        ("Gulab Jamun (2 pc)", "Desserts", 30.0, 89.0, 9),
        ("Chicken Biryani", "Main Course", 165.0, 329.0, 11),
    ]

    rows: list[list] = []
    bad_rows = 0
    for offset in range(90):
        day = start + timedelta(days=offset)
        for item, section, cost, price, base in catalogue:
            units = int(round(base * rng.uniform(0.4, 1.6)))
            rows.append([day.strftime("%d-%m-%Y"), item, section, units, f"{price:.2f}", f"{cost:.2f}", "Dine-in"])

        # One deliberately broken row per week, cycling through failure modes.
        if offset % 7 == 0:
            mode = (offset // 7) % 5
            if mode == 0:
                rows.append(["31-02-2026", "Veg Thali", "Main Course", 4, "199.00", "95.00", "Dine-in"])
            elif mode == 1:
                rows.append([day.strftime("%d-%m-%Y"), "Cold Coffee", "Beverages", 0, "119.00", "38.00", "Takeaway"])
            elif mode == 2:
                rows.append([day.strftime("%d-%m-%Y"), "Masala Dosa", "", 3, "129.00", "45.00", "Dine-in"])
            elif mode == 3:
                rows.append([day.strftime("%d-%m-%Y"), "Cold Coffee", "Beverages", 2, "free", "38.00", "Takeaway"])
            else:
                rows.append([day.strftime("%d-%m-%Y"), "Gulab Jamun (2 pc)", "Desserts", -2, "89.00", "30.00", "Dine-in"])
            bad_rows += 1

        # A genuine loss-making clearance line — must survive validation.
        if offset % 30 == 0:
            rows.append([day.strftime("%d-%m-%Y"), "Chicken Biryani", "Main Course", 5, "149.00", "165.00", "Zomato"])

    header = ["Sale Date", "Item", "Section", "Qty Sold", "Rate", "Cost", "Order Type"]
    _write_csv("05_restaurant_pos_semicolon.csv", header, rows, delimiter=";")
    return "05_restaurant_pos_semicolon.csv", len(rows), bad_rows


# ── 6. Footwear boutique — a wide, sparse export ────────────────────────────
# Torture test: eighteen columns, six of them optional dimensions (brand, size,
# colour, branch, payment mode, customer), a discount *and* a tax column, and the
# shop trades on only ~45% of days — the sparse shape that broke the anomaly
# baseline and the forecast accuracy basis.
def build_footwear_wide() -> tuple[str, int]:
    rng = np.random.default_rng(606)
    start = date(2026, 1, 6)
    catalogue = [
        ("Running Shoe", "Sports", "Nike", 2400.0, 4299.0, 3),
        ("Canvas Sneaker", "Casual", "Converse", 1100.0, 2199.0, 4),
        ("Leather Formal", "Formal", "Bata", 1450.0, 2799.0, 2),
        ("Kolhapuri Chappal", "Ethnic", "Local", 380.0, 899.0, 5),
        ("Flip Flop", "Casual", "Paragon", 120.0, 299.0, 8),
        ("Heeled Sandal", "Party", "Metro", 980.0, 1999.0, 2),
        ("Trekking Boot", "Outdoor", "Woodland", 3100.0, 5499.0, 1),
    ]
    sizes = ["6", "7", "8", "9", "10"]
    colours = ["Black", "Brown", "White", "Navy", "Tan"]
    branches = ["MG Road", "Phoenix Mall", "Station Road"]
    payments = ["UPI", "Card", "Cash", "EMI", "Wallet"]
    customers = ["Walk-in", "Anita S", "Rahul M", "Priya K", "Corporate"]

    rows = []
    invoice = 20001
    for offset in range(200):
        day = start + timedelta(days=offset)
        if rng.random() > 0.45:  # shop shut / nothing recorded
            continue
        for item, category, brand, cost, price, base in catalogue:
            units = int(round(base * rng.uniform(0.3, 1.8)))
            if units <= 0:
                continue
            gross = units * price
            discount = round(gross * rng.choice([0.0, 0.05, 0.1, 0.15]), 2)
            tax = round((gross - discount) * 0.12, 2)
            rows.append(
                [
                    day.strftime("%d-%m-%Y"),
                    f"FB/{invoice}",
                    item,
                    category,
                    brand,
                    str(rng.choice(sizes)),
                    str(rng.choice(colours)),
                    units,
                    f"{price:.2f}",
                    f"{cost:.2f}",
                    f"{discount:.2f}",
                    f"{tax:.2f}",
                    str(rng.choice(branches)),
                    str(rng.choice(payments)),
                    str(rng.choice(customers)),
                    str(rng.choice(["Ayesha", "Vikram", "Neha"])),
                    int(max(rng.integers(0, 25), 0)),
                    "exchange allowed within 7 days",
                ]
            )
            invoice += 1

    header = [
        "Bill Date",
        "Invoice No",
        "Style Name",
        "Category",
        "Brand",
        "Size",
        "Colour",
        "Qty",
        "Rate/Unit",
        "Purchase Rate",
        "Discount",
        "GST Amount",
        "Store",
        "Payment Mode",
        "Customer Name",
        "Salesperson",
        "Closing Stock",
        "Remarks",
    ]
    _write_csv("06_footwear_boutique_wide.csv", header, rows)
    return "06_footwear_boutique_wide.csv", len(rows)


def main() -> None:
    print("Generating testing2 fixtures…\n")
    results = [build_garment_tally(), build_grocery_gst(), build_electronics_marketplace()]
    results.append(build_pharmacy_excel())
    restaurant = build_restaurant_dirty()
    results.append((restaurant[0], restaurant[1]))
    results.append(build_footwear_wide())

    for name, rows in results:
        size_kb = (OUT_DIR / name).stat().st_size / 1024
        print(f"  {name:<38} {rows:>6,} rows   {size_kb:>7.1f} KB")

    print(f"\n  (of which {restaurant[2]} rows in the restaurant file are deliberately invalid)")
    print(f"\nWritten to {OUT_DIR}")


if __name__ == "__main__":
    main()
