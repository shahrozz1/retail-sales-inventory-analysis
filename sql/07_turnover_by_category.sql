/* =====================================================================
   Inventory turnover by category, before vs after the July 1 changes
   ---------------------------------------------------------------------
   Inventory turnover = cost of goods sold / average inventory value (at cost)
     "How many times a year does the money sitting on the shelf turn
      back into sales?" Higher is better: 12 turns = stock sells through
      about once a month.

   Each half-year is annualized (x 365 / days in the half) so the two
   periods are comparable to a normal yearly turnover figure.

   Two separate summaries are joined at the end:
     cogs       - what we sold, at cost (from daily_sales)
     inventory  - what we held, at cost (from daily_inventory)
   ===================================================================== */

WITH cogs AS (
    SELECT
        p.category,
        CASE WHEN s.sale_date < DATE '2025-07-01' THEN 'Before (Jan-Jun)'
             ELSE 'After (Jul-Dec)' END                AS period,
        SUM(s.units_sold * p.unit_cost)                AS cost_of_goods_sold
    FROM daily_sales AS s
    JOIN products AS p ON p.sku_id = s.sku_id
    GROUP BY 1, 2                                      -- 1, 2 = the first two columns in SELECT
),

inventory AS (
    -- Average inventory value = total of every day's stock value / number of days.
    SELECT
        p.category,
        CASE WHEN i.snapshot_date < DATE '2025-07-01' THEN 'Before (Jan-Jun)'
             ELSE 'After (Jul-Dec)' END                AS period,
        SUM(i.on_hand_units * p.unit_cost)
            / COUNT(DISTINCT i.snapshot_date)          AS avg_inventory_value,
        COUNT(DISTINCT i.snapshot_date)                AS days_in_period
    FROM daily_inventory AS i
    JOIN products AS p ON p.sku_id = i.sku_id
    GROUP BY 1, 2
)

SELECT
    c.category,
    c.period,
    ROUND(c.cost_of_goods_sold, 2)                     AS cost_of_goods_sold,
    ROUND(i.avg_inventory_value, 2)                    AS avg_inventory_value,
    ROUND(c.cost_of_goods_sold / i.avg_inventory_value
          * 365.0 / i.days_in_period, 1)               AS annual_turnover
FROM cogs AS c
JOIN inventory AS i
    ON  i.category = c.category
    AND i.period   = c.period
ORDER BY c.category, c.period DESC;
