/* =====================================================================
   Q2b. Pareto summary: what % of products drive what % of revenue?
   ---------------------------------------------------------------------
   Period: Jan 1 - Jun 30, 2025 (baseline).

   NTILE(5) deals products into 5 equal-sized groups by revenue, best
   sellers first. With 200 products each group has 40, so group 1 is
   "the top 20% of products". Then we total each group's revenue.

   Why it matters: if a small group of products drives most of the
   revenue, those items must NEVER be out of stock (see
   04_reorder_points.sql), and the long tail at the bottom is where cash
   gets stuck (see 01_slow_movers.sql).
   ===================================================================== */

WITH sku_revenue AS (
    -- Same first step as 02_pareto_curve.sql: revenue per product,
    -- keeping products that sold nothing.
    SELECT
        p.sku_id,
        COALESCE(SUM(s.net_sales), 0) AS revenue
    FROM products AS p
    LEFT JOIN daily_sales AS s
        ON  s.sku_id = p.sku_id
        AND s.sale_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
    GROUP BY p.sku_id
),

ranked AS (
    -- Step 2: tag every product with its group (1 = top 20%).
    SELECT
        sku_id,
        revenue,
        NTILE(5) OVER (ORDER BY revenue DESC, sku_id) AS revenue_quintile
    FROM sku_revenue
)

-- Step 3: one row per group. The scalar subquery in the denominator
-- returns a single number (total revenue) to divide each group by.
SELECT
    revenue_quintile,
    CASE revenue_quintile
        WHEN 1 THEN 'Top 20%'
        WHEN 2 THEN 'Next 20% (21-40%)'
        WHEN 3 THEN 'Middle 20% (41-60%)'
        WHEN 4 THEN 'Next 20% (61-80%)'
        ELSE        'Bottom 20%'
    END                                                        AS product_group,
    COUNT(*)                                                   AS products,
    ROUND(SUM(revenue), 2)                                     AS revenue,
    ROUND(100.0 * SUM(revenue) / (SELECT SUM(revenue) FROM sku_revenue), 1)
                                                               AS pct_of_revenue
FROM ranked
GROUP BY revenue_quintile
ORDER BY revenue_quintile;
