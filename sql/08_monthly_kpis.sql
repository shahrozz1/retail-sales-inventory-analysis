/* =====================================================================
   Monthly KPIs: did the July 1 changes work?
   ---------------------------------------------------------------------
   One row per month with the three numbers the project set out to move:

   1. Gross margin %  = (revenue - cost of goods) / revenue

   2. Dead stock value (month-end, at cost)
      Stock on the shelf beyond 60 days of supply at that month's sales
      pace: cash that won't turn back into sales for at least two months.
        excess units = on hand at month-end - (units sold that month x 60 / days in month)
      If an item sold nothing that month, everything on hand counts.

   3. Stockout days for continuing items (an item at 0 units at close).
      Discontinued items are left out: running them down to zero was
      the goal, not a failure.

   The Python script splits these rows into Before (Jan-Jun) and
   After (Jul-Dec) and compares the two halves.
   ===================================================================== */

WITH sales_by_month AS (
    -- Revenue, cost and units per product per month.
    SELECT
        DATE_TRUNC('month', s.sale_date) AS month,
        s.sku_id,
        SUM(s.units_sold)                AS units_sold,
        SUM(s.net_sales)                 AS revenue,
        SUM(s.units_sold * p.unit_cost)  AS cost_of_goods
    FROM daily_sales AS s
    JOIN products AS p ON p.sku_id = s.sku_id
    GROUP BY 1, 2
),

month_end_stock AS (
    -- LAST_DAY(date) returns the last day of that date's month, so this
    -- keeps only the month-end stock counts (Jan 31, Feb 28, ...).
    SELECT
        DATE_TRUNC('month', i.snapshot_date) AS month,
        i.sku_id,
        i.on_hand_units,
        DAY(i.snapshot_date)                 AS days_in_month
    FROM daily_inventory AS i
    WHERE i.snapshot_date = LAST_DAY(i.snapshot_date)
),

dead_stock AS (
    -- Excess units per product at month-end, valued at cost.
    -- GREATEST(x, 0) stops fast sellers from counting as negative excess.
    SELECT
        m.month,
        SUM(GREATEST(m.on_hand_units
                     - COALESCE(s.units_sold, 0) * 60.0 / m.days_in_month, 0)
            * p.unit_cost)                               AS dead_stock_value,
        SUM(m.on_hand_units * p.unit_cost)               AS inventory_value
    FROM month_end_stock AS m
    JOIN products AS p ON p.sku_id = m.sku_id
    LEFT JOIN sales_by_month AS s
        ON  s.sku_id = m.sku_id
        AND s.month  = m.month
    GROUP BY m.month
),

stockouts AS (
    SELECT
        DATE_TRUNC('month', i.snapshot_date) AS month,
        COUNT(*)                             AS stockout_days
    FROM daily_inventory AS i
    JOIN products AS p ON p.sku_id = i.sku_id
    WHERE i.on_hand_units = 0
      AND p.discontinued_date IS NULL
    GROUP BY 1
),

store_sales AS (
    -- Roll the per-product sales up to one row per month for the whole store.
    SELECT
        month,
        SUM(revenue)       AS revenue,
        SUM(cost_of_goods) AS cost_of_goods
    FROM sales_by_month
    GROUP BY month
)

-- Every CTE above now has exactly one row per month, so they join 1-to-1.
SELECT
    s.month,
    CASE WHEN s.month < DATE '2025-07-01' THEN 'Before' ELSE 'After' END  AS period,
    ROUND(s.revenue, 2)                                                  AS revenue,
    ROUND(s.revenue - s.cost_of_goods, 2)                                AS gross_profit,
    ROUND(100.0 * (s.revenue - s.cost_of_goods) / s.revenue, 2)          AS gross_margin_pct,
    ROUND(d.dead_stock_value, 2)                                         AS dead_stock_value,
    ROUND(d.inventory_value, 2)                                          AS inventory_value,
    COALESCE(o.stockout_days, 0)                                         AS stockout_days
FROM store_sales AS s
JOIN dead_stock AS d ON d.month = s.month
LEFT JOIN stockouts AS o ON o.month = s.month
ORDER BY s.month;
