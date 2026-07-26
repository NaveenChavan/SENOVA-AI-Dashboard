# testing2 — format compatibility fixtures

Six sales files, six different **business categories**, six different **export
formats**. The point isn't more test data — it's to answer one question honestly:

> How many real-world export shapes can SENOVA's column mapper and validator
> actually handle, without a human fixing the file first?

Everything here is generated from fixed seeds, so the numbers you see in the
dashboard are reproducible.

```bash
py -3 testing2/generate_testing2.py   # (re)create the six files
py -3 testing2/verify_testing2.py     # run all six through the real pipeline
```

---

## The six files

| # | File | Category | Rows | What it deliberately breaks |
|---|------|----------|------|------------------------------|
| 1 | `01_garment_tally_export.csv` | Garment shop | 758 | **Tally headers** (`Voucher Date`, `Particulars`, `Stock Group`, `Qty.`, `Rate/Unit`, `Purchase Rate`), DD-MM-YYYY dates, Sundays closed, a winter-only item that becomes dead stock |
| 2 | `02_grocery_gst_invoice.csv` | Grocery / kirana | 1,050 | **No unit price at all** — `Taxable Value` is a line total, written as `₹ 1,490.00` (currency symbol *and* Indian commas). Plus `Discount`, `GST Amount`, DD/MM/YYYY, an HSN column to ignore |
| 3 | `03_electronics_shopify_orders.csv` | Electronics | 700 | **Marketplace headers** (`Lineitem name`, `Lineitem quantity`, `Ordered On`), **ISO dates**, two competing price columns (`Lineitem price` vs `MRP`), three junk columns (`Currency`, `Order Status`, `Notes`) |
| 4 | `04_pharmacy_marg_stock.xlsx` | Pharmacy | 770 | **Excel**, not CSV — real date cells, and a `Closing Stock` column that unlocks stock-aware inventory. Two `Godown`s and three `Salesman`s |
| 5 | `05_restaurant_pos_semicolon.csv` | Restaurant | 556 | **Semicolon-delimited**, food-service headers (`Section`, `Qty Sold`, `Order Type`), and **13 deliberately broken rows**: `31-02-2026`, quantity `0`, quantity `-2`, a blank category, a price of `"free"` — plus a genuine below-cost clearance line that must survive |
| 6 | `06_footwear_boutique_wide.csv` | Footwear boutique | 576 | **18 columns**, six of them optional dimensions (brand, size, colour, store, payment mode, customer, salesperson), a discount *and* a GST column, `Closing Stock`, a free-text `Remarks` to ignore — and the shop trades on only **45% of days** (the sparse shape) |

---

## What the harness checks per file

`verify_testing2.py` doesn't just import the file — it runs the **automatic**
column guesser (no human confirming a mapping), validates, then computes the same
numbers the dashboard shows and compares each of them against an independent
recomputation straight from the validated frame:

- revenue, profit, units, unique items — must match to the paisa
- the chart engine's total must equal that revenue
- the transaction register's page totals must reconcile with it
- the P&L identity `net − COGS = gross profit` must hold
- no insight card may publish a ₹0 baseline
- inventory must pick the right mode (stock-aware only when stock is mapped)
- the forecast must report which basis its accuracy was scored on

Exit code is non-zero if any file yields no analysable rows or any total
disagrees.

---

## Result (last run)

```
All 6 formats handled, every published total reconciled independently.
```

| File | Auto-mapped | Valid rows | Optional fields unlocked | Inventory mode | Forecast accuracy |
|------|-------------|------------|--------------------------|----------------|-------------------|
| 1 garment (Tally) | 8/8 | 758 (0 rejected) | Invoice No, Payment Mode | demand-only | 90.0% daily |
| 2 grocery (GST) | 10/11 | 1,050 (0 rejected) | Customer, Discount, Invoice No, Line Total, Tax | demand-only | 85.5% daily |
| 3 electronics (Shopify) | 8/12 | 700 (0 rejected) | Invoice No, Payment Mode | demand-only | 90.6% daily |
| 4 pharmacy (Excel) | 10/10 | 770 (0 rejected) | Branch, Invoice No, Salesperson, **Stock On Hand** | **stock-aware** | 87.3% daily |
| 5 restaurant (semicolon, dirty) | 6/7 | **543 of 556** (13 rejected, 13 error notes) | — | demand-only | 85.6% daily |
| 6 footwear (wide, sparse) | 17/18 | 576 (0 rejected) | Branch, Brand, Colour, Customer, Discount, Invoice No, Payment Mode, Salesperson, Size, **Stock On Hand**, Tax | **stock-aware** | 98.1% **total** |

Notes worth reading off that table:

- File 2 proves the `Line Total ÷ Quantity` derivation: revenue comes out as
  ₹13,60,225 — the sum of the line totals — not quantity × line total.
- File 5 is the partial-success path: exactly the 13 planted bad rows are
  rejected, each with a row-level error note, and the other 543 are analysed.
  The below-cost clearance line is kept, because selling at a loss is legal.
- File 6 is the only one whose accuracy is scored on the **7-day total** rather
  than per day, because it trades 84 of 198 days — per-day error there would
  measure "did we guess which days it opened".
- Files 4 and 6 are the only ones with days-of-cover, reorder alerts and capital
  locked, because they're the only ones carrying stock.

---

## Two bugs these fixtures found

Both were fixed, and both now have regression tests in
`backend/tests/test_data_validator.py`.

### 1. Currency symbols broke the unit-price derivation → **0 valid rows**

File 2 initially produced *no analysable rows at all*. The ₹-and-comma cleaning
lived inside the main numeric coercion loop, but `Line Total ÷ Quantity` runs
*before* that loop — so `"₹ 1,490.00"` came out as `NaN`, every row lost its
`Selling Price`, and all 1,050 rows were dropped.

Fix: one shared `_coerce_numeric()` helper, used by both the loop and the
derivation.

### 2. `dayfirst=True` scrambled ISO dates → a 100-day file spanning 337 days

File 3 uses `2026-04-05`. Parsing with `dayfirst=True` first reads that as
5 April *or* 4 May depending on the value, so a 100-day export was spread over
337 days. Consequences were visible downstream: the shop looked like it traded
100 of 337 days (sparse), the anomaly check switched to trading-day mode
unnecessarily, and forecast accuracy read **4%**.

Fix: anything matching `YYYY-MM-DD` is parsed as ISO first; only the remainder is
retried with `dayfirst=True`, so Indian and ISO dates can coexist in one column.
Same file now: 100 of 100 trading days, accuracy **90.6%**.

A third, smaller gap: file 5's `Section` column wasn't recognised as a category.
Food-service aliases (`Section`, `Menu Group`, `Menu Category`, `Course`,
`Kitchen Group`, `Food Type`) were added to the alias map.

---

## Using them in the app

1. Start both servers (`uvicorn app.main:app --reload` and `npm run dev`).
2. Upload a file, look at the mapping screen — the confidence badges show what
   was matched exactly, guessed, or not recognised.
3. For file 3, the mapping screen deliberately offers a choice: `Lineitem price`
   or `MRP`. Pick `Lineitem price` as Selling Price and leave `MRP` ignored.
4. Confirm, and check the dashboard against the table above.

Things worth clicking through per file:

- **1 garment** — weekday insight (Sundays closed, Saturdays 1.7×), dead stock
  (the woollen shawl stops in mid-February).
- **2 grocery** — the P&L should show *Gross Sales → Less: Discounts → Net
  Revenue*, plus a GST memo line beneath gross profit.
- **3 electronics** — the trend chart should span ~100 days, not ~340.
- **4 pharmacy** — Inventory tab: days of cover, reorder alerts, capital locked;
  filter by `Godown` and by `Salesman`.
- **5 restaurant** — the amber "13 rows skipped" banner, expandable by column.
- **6 footwear** — six filter dimensions, the sparse trend line with its 7-day
  average, and a forecast labelled "on the last 7-day total".
