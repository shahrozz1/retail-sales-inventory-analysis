/* =====================================================================
   Where did the margin improvement come from?
   ---------------------------------------------------------------------
   Store-wide margin rose after July 1, but margin also moves with the
   seasons (cold drinks and ice are high-margin and sell most in summer).
   To separate the two, split products by what happened to them:

     Repriced  - price raised in the July 1 price review
     Cut       - discontinued July 1 and cleared at cost
     Unchanged - everything else (the CONTROL GROUP)

   If the unchanged products' margin is about the same in both halves,
   seasonality isn't driving the store-wide change, and the gain can be
   credited to the actions.
   ===================================================================== */

WITH product_group AS (
    SELECT
        p.sku_id,
        CASE
            WHEN p.discontinued_date IS NOT NULL THEN 'Cut'
            WHEN p.sku_id IN (SELECT sku_id FROM price_changes
                              WHERE reason LIKE 'Price review%') THEN 'Repriced'
            ELSE 'Unchanged'
        END AS action_group
    FROM products AS p
),

group_size AS (
    SELECT action_group, COUNT(*) AS products
    FROM product_group
    GROUP BY action_group
),

by_half AS (
    -- One row per group per half-year.
    SELECT
        g.action_group,
        CASE WHEN s.sale_date < DATE '2025-07-01' THEN 'Before' ELSE 'After' END AS period,
        SUM(s.net_sales)                                   AS revenue,
        SUM(s.net_sales - s.units_sold * p.unit_cost)      AS gross_profit
    FROM daily_sales AS s
    JOIN products      AS p ON p.sku_id = s.sku_id
    JOIN product_group AS g ON g.sku_id = s.sku_id
    GROUP BY 1, 2
),

side_by_side AS (
    -- Turn the Before and After rows into columns ("conditional aggregation"):
    -- each SUM only picks up the rows where its CASE condition is true.
    SELECT
        action_group,
        SUM(CASE WHEN period = 'Before' THEN revenue      END) AS revenue_before,
        SUM(CASE WHEN period = 'Before' THEN gross_profit END) AS profit_before,
        SUM(CASE WHEN period = 'After'  THEN revenue      END) AS revenue_after,
        SUM(CASE WHEN period = 'After'  THEN gross_profit END) AS profit_after
    FROM by_half
    GROUP BY action_group
)

SELECT
    b.action_group,
    z.products,
    ROUND(100.0 * b.profit_before / b.revenue_before, 1) AS margin_before_pct,
    ROUND(100.0 * b.profit_after  / b.revenue_after, 1)  AS margin_after_pct,
    ROUND(b.revenue_before, 2)                           AS revenue_before,
    ROUND(b.revenue_after, 2)                            AS revenue_after
FROM side_by_side AS b
JOIN group_size   AS z ON z.action_group = b.action_group
ORDER BY b.action_group;
