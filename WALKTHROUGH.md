# Walkthrough: how this project works

A plain-English explanation of every query and every part of the Python code, and the reasoning behind each choice. Open each SQL file next to its section below; the queries are also commented step by step.

To run a query on its own, use the [DuckDB CLI](https://duckdb.org/docs/installation/): `duckdb data/store.duckdb < sql/01_slow_movers.sql`

---

## Contents

1. [SQL ideas used in this project](#1-sql-ideas-used-in-this-project)
2. [Query-by-query walkthrough](#2-query-by-query-walkthrough)
3. [Python walkthrough](#3-python-walkthrough)

---

## 1. SQL ideas used in this project

These come up in almost every query.

| Idea | Plain-English meaning | Where it's used |
|---|---|---|
| **CTE** (`WITH name AS (...)`) | A named, temporary result you build in steps, like helper tabs in a spreadsheet. Makes long queries readable top to bottom. | Every query |
| **INNER JOIN** (`JOIN`) | Keep only rows that match in both tables. | Joining sales to products |
| **LEFT JOIN** | Keep *every* row from the left table, even with no match; the missing side becomes NULL. | Keeping products that sold nothing |
| **Filter in `ON` vs `WHERE`** | With a LEFT JOIN, a date filter in `ON` keeps unmatched products (as zeros); the same filter in `WHERE` silently drops them. | 02, 03, 05 |
| **`COALESCE(x, 0)`** | "Use x, but if it's NULL use 0." | Turning "no sales" into 0 |
| **`NULLIF(x, 0)`** | "Return NULL if x is 0." Dividing by NULL gives NULL instead of crashing with divide-by-zero. | Sell-through, days of supply |
| **`GROUP BY`** | Collapse many rows into one per group (per product, per month...). | Everywhere |
| **Window function** (`... OVER (...)`) | Calculate across rows *without* collapsing them. Every row keeps its identity but can see its neighbors. | Running totals, rankings |
| **`ORDER BY` inside `OVER`** | Makes it a running calculation: "from the first row up to this one." | Pareto running total |
| **`PARTITION BY`** | Restart the calculation for each group, like a separate window per category. | Category averages in 05 |
| **`ROW_NUMBER()`** | 1, 2, 3, ... in the given order. | Revenue rank |
| **`NTILE(5)`** | Deal rows into 5 equal-sized groups in order. Group 1 = top 20%. | Top sellers, Pareto groups |
| **Conditional aggregation** (`SUM(CASE WHEN ... END)`) | Count or add up only the rows that meet a condition. Also used to turn rows into columns. | Stockout days, 09 |
| **`CEIL`** | Round up. You can't order 18.3 cans, and rounding down adds stockout risk. | Reorder points |
| **Tie-breaker in `ORDER BY`** | Adding `sku_id` at the end makes the order identical every run when values tie. | Every `LIMIT` query |

---

## 2. Query-by-query walkthrough

### `00_schema.sql`: the tables

Five tables, and why each is shaped the way it is:

- **`daily_sales` has no zero rows.** A real POS export only records sales that happened. That creates a trap later (see Q3): if you average this table directly, you only average the days something sold, which overstates demand.
- **`daily_inventory` has a row for every product, every day.** It's the complete calendar, so it's the right table to start from when zero-sale days need to count.
- **Cost of goods isn't stored; it's calculated as `units_sold × unit_cost`.** One source of truth means numbers can't disagree.
- **`reorder_settings` keeps history** (an `effective_date` per rule), so you can see exactly what changed on July 1.
- **Money is `DECIMAL`, not floating point,** so cents never round oddly.

### `01_slow_movers.sql`: Q1, slow sellers tying up cash

**Business question:** Where is cash stuck on the shelf?

**Steps:**
1. `baseline_sales`: total units sold per product, Jan 1 to Jun 30.
2. `ending_stock`: units on hand at close on June 30.
3. `sku_metrics`: three numbers per product:
   - *Sell-through %* = sold ÷ (sold + still on hand). "Of everything we had, how much sold?"
   - *Cash tied up* = on hand × unit cost.
   - *Days of supply* = on hand ÷ (units sold ÷ 181 days). "How long until we'd run out?"
4. `slowest_20`: the 20 lowest sell-through products.
5. Final: re-sort those 20 by cash tied up, so the biggest dollar problem is on top.

**Why `LEFT JOIN` to sales?** A product that sold *nothing* has no rows in `daily_sales`. An inner join would drop it, and those are exactly the worst offenders.

**Why only Jan–Jun?** On July 1, that's all the data I would have had. Using later data would be hindsight.

**Why "lowest 20, then sort by dollars"** instead of just sorting by dollars? A fast seller with lots of stock also has lots of dollars on the shelf, but it isn't a problem. First filter to slow sellers, then prioritize by money.

**Result:** 20 products, $3,541 at cost. Celsius 12oz was the worst: 409 units, 136 days of supply.

### `02_pareto_curve.sql`: Q2, the cumulative curve

**Business question:** Do a few products drive most of the revenue?

**Steps:**
1. `sku_revenue`: revenue per product (LEFT JOIN, so zero-sale products show as $0).
2. Final: three window functions on every row:
   - `ROW_NUMBER() OVER (ORDER BY revenue DESC, sku_id)` = rank.
   - rank ÷ `COUNT(*) OVER ()` = "what % of products are at or above this rank." An empty `OVER ()` means "all rows."
   - `SUM(revenue) OVER (ORDER BY revenue DESC ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` ÷ total = running % of revenue.

**How to read it:** find the row where cumulative revenue first passes 80%. Its "% of products" is the answer: 31% of products = 80% of revenue.

### `03_pareto_summary.sql`: Q2, the five-group summary

Same revenue per product, then `NTILE(5)` splits the 200 products into 5 groups of 40 by revenue. Group totals ÷ store total gives each group's share.

**The scalar subquery** `(SELECT SUM(revenue) FROM sku_revenue)` returns one number, the store total, which every group's revenue is divided by.

**Result:** top 20% = 67.8% of revenue; bottom 20% = 1.3%.

**Why it matters:** it decides where to focus. Protect the top 40 from stockouts (Q3); look for cuts in the bottom (Q1, Q4).

### `04_reorder_points.sql`: Q3, reorder points for top sellers

**Business question:** When should we reorder each top seller, and how much?

**The formula:**
- **Reorder point** = (average daily demand × lead time) + safety stock
  *Enough to cover sales while we wait for the truck...*
- **Safety stock** = 1.65 × standard deviation of daily demand × √(lead time)
  *...plus a cushion for busier-than-average days.*
  - **1.65** is the Z-score for a 95% service level: a 95% chance of not running out while waiting.
  - **Standard deviation** measures how much daily sales bounce around. Steady sellers need less cushion.
  - **√lead time:** busy and slow days partly cancel out over several days, so uncertainty grows with the square root of time, not in a straight line.
- **Max stock** = reorder point + 7 days of demand (one week's delivery).

**Steps:**
1. `daily`: start from `daily_inventory` (every product, every day) and LEFT JOIN sales. Zero-sale days now count as 0. **This is the trap from the schema section.** If you start from `daily_sales`, an item that sells 10 units on 3 days out of 10 looks like it sells 10 a day instead of 3.
2. `demand`: average and standard deviation of daily sales, **leaving out days the item was out of stock**. `CASE WHEN on_hand_units > 0 THEN units_sold END` returns NULL on stockout days, and AVG/STDDEV skip NULLs. Why? On a day you're out of stock, zero sales doesn't mean nobody wanted it; it means there was nothing to sell. That's called *censored demand*.
3. `top_sellers`: NTILE(5) = 1, the top 40 by revenue.
4. `current_settings`: the rules in effect since January 1.
5. `recommended`: apply the formula, using `CEIL` to round up.
6. Final: current vs recommended side by side, with an action label.

**Result:** 29 of 40 needed a higher reorder point (179 out-of-stock days in six months). 10 had settings that were too high.

**The key result:** after the change, out-of-stock days fell from 179 to 40 **and** inventory on these items fell from $12.3K to $6.4K. The old rules ordered too late (no safety stock) *and* too much at once (2–3 weeks of padding). Fixing both moves stock in smaller, better-timed deliveries.

### `05_low_margin_per_shelf.sql`: Q4, the cut list

**Business question:** Which products earn the least for the space they take up?

**Why per facing, not margin %?** A 50%-margin item that sells twice a month earns almost nothing for its shelf space. In a store where space is the constraint, *profit per unit of space* is the right measure. Grocery stores call this "space productivity."

**Steps:**
1. `sku_perf`: revenue and cost per product (LEFT JOIN, date filter in `ON`).
2. `scored`:
   - gross profit ÷ facings ÷ 26 weeks = GP per facing per week.
   - `NTILE(5)` revenue group.
   - `AVG(...) OVER (PARTITION BY category)` = the category's average, as a benchmark. It's computed *before* the `WHERE` filter so the benchmark includes every product in the category.
3. Final: exclude the top 20% (`revenue_quintile > 1`), sort lowest first, take 15.

**Why exclude the top 20%?** Traffic drivers. Milk and cigarettes can have thin margins, but people come in for them and buy a drink and a snack too. Cutting them loses far more than their own margin. This is a *business rule*, not math.

**Result:** 15 items at $0.20–$0.81 per facing per week vs category averages of $1.63–$5.20. Cutting them freed 28 facings.

### `06_price_review.sql`: bonus, under-priced items

**Business question:** Have vendor costs gone up without shelf prices following?

**Steps:**
1. `item_margin`: margin % for every non-tobacco product at its regular price.
2. `category_median`: the **median** margin per category. Why median, not average? One extreme item can drag an average; the median is the middle value and ignores outliers.
3. Final: flag items more than 3 points below their category median and suggest a price: `cost ÷ (1 − target margin)`, rounded up to end in 9.

**The price math:** if margin = (price − cost) ÷ price, then solving for price gives price = cost ÷ (1 − margin). Example: cost $1.41, target 40.8% → $1.41 ÷ 0.592 = $2.38 → $2.39.

**Why exclude tobacco?** Manufacturer programs and state rules set its pricing; a store can't just reprice it.

### `07_turnover_by_category.sql`: turnover chart data

**Inventory turnover** = cost of goods sold ÷ average inventory value. "How many times a year does the money on the shelf turn back into sales?" 25 turns ≈ stock sells through every two weeks.

Two CTEs, one for what was sold (`cogs`) and one for what was held (`inventory`), each grouped by category and half-year. They're joined at the end. Each half is multiplied by 365 ÷ days in the half (*annualized*), so the numbers compare to a normal yearly figure.

### `08_monthly_kpis.sql`: before/after chart data

One row per month with gross margin %, dead stock, inventory value and stockout days.

**Dead stock definition:** at each month-end, any stock beyond **60 days of supply** at that month's sales pace, valued at cost. If an item sold nothing that month, everything on hand counts.

**`LAST_DAY(date)`** returns the last day of that date's month, so `WHERE snapshot_date = LAST_DAY(snapshot_date)` keeps only month-end stock counts.

**`GREATEST(x, 0)`** stops fast sellers from counting as "negative" dead stock.

Discontinued items are left out of the stockout count, since running them down to zero was the goal.

### `09_margin_by_action.sql`: the control group

**Business question:** Did margin go up because of what I did, or because of the season?

Split products into three groups by what happened to them on July 1: **Repriced**, **Cut**, and **Unchanged**. The unchanged group is the *control group*. If its margin is the same before and after, seasonality isn't what moved the store total.

**Result:** Unchanged 28.8% → 28.9% (flat). Repriced 27.7% → 34.5%. So the gain came from the price review.

**Conditional aggregation** turns rows into columns: `SUM(CASE WHEN period = 'Before' THEN revenue END)` adds up only the Before rows. It's the SQL version of a pivot table.

---

## 3. Python walkthrough

### `analysis.py`: runs the SQL and draws the charts

**The design idea:** Python doesn't redo any analysis. It reads each `.sql` file and runs it unchanged, so the SQL is the single source of truth and the charts can never disagree with the queries.

| Part | What it does |
|---|---|
| `QUERIES` dict | Maps each SQL file to the CSV name its result is saved as. |
| `run_all_queries()` | Loops over the files: read text → `con.execute(sql).df()` returns a pandas DataFrame → save it as CSV. |
| `before_after_summary()` | `groupby("period")` collapses 12 monthly rows into Before and After. **Margin is total profit ÷ total revenue**, not the average of six monthly percentages, so busier months count more. Dead stock is averaged because it's a snapshot, not a flow. |
| `set_style()` | One shared look via `plt.rcParams`: light background, thin gridlines, no box around the plot. |
| `add_header_and_note()` | Title, one-sentence takeaway, and a "Simulated data" note on every image, so a chart shared on its own can't be mistaken for real data. |
| `chart_turnover()` | `sns.barplot` with `hue="period"` draws the before/after pairs. Categories are sorted by the After value. Only the After bars get number labels, because the result is what matters. |
| `chart_pareto()` | Left: `ax.plot` of the cumulative curve plus a diagonal "if every product sold equally" line for comparison; `annotate` calls out the 20% and 80% points. Right: a 5-bar summary. |
| `chart_before_after()` | Two side-by-side panels (margin, dead stock). Gray before July, blue after, a vertical line at the change, and thin lines at each half's average. |

**Color choice:** "Before" is gray and "after" is blue on *every* chart. One highlight color pulls the eye to the result, and keeping it consistent means a reader learns it once. This is also deliberately **not** a dual-axis chart: margin % and dollars are separate panels because two different y-scales on one chart can suggest relationships that aren't there.

### `generate_data.py`: the simulated store

The key ideas:

1. **The catalog.** Each category lists products from most to least popular. Daily demand for the i-th product ≈ `top_rate ÷ (i+1)^decay`, so sales fall off quickly down the list. That's what creates the 80/20 pattern.
2. **Random daily demand.** Each day, customer demand for each product is a **Poisson** draw around its average, which is the standard way to model "how many customers show up." The average is adjusted for season and day of the week. The store can only sell what's on the shelf: `sold = min(wanted, on_hand)`.
3. **The reorder loop.** Every evening, for each product: if stock + units already on order ≤ reorder point, order up to max stock, rounded up to a full case (or single units). The order arrives after the lead time.
4. **The old habits** (Jan–Jun) that cause the problems:
   - reorder point = lead-time demand with **no safety stock** → stockouts
   - orders padded to 2–3 weeks and "full-looking shelves" → overstock
   - some items' settings date from when they **sold 2–4× more** → dead stock
   - **vendor cost increases** not passed on to prices → margin squeeze
5. **A two-year warm-up** that isn't saved, so January 1 looks like a store that has been running this way for years, not one that just opened with perfect shelves.
6. **July 1: the script runs the SQL files** (`01`, `04`, `05`, `06`) and applies their output. The decisions come from the analysis, not from hand-picked numbers.
7. **Items keep fading during the year,** so dead stock keeps forming unless someone keeps checking. This is why one of the recommendations is a monthly review.

### `check_seeds.py`: is the result luck?

Reruns the whole year with 20 different random seeds and records the before/after changes. The seed used in the project is the run closest to the **median**, so the README shows a typical outcome. **Every run improves margin (+4.1% to +7.6%); dead stock varies more (−8% to −56%).** The README reports the range, not just the single run.
