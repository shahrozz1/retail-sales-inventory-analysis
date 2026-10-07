/* =====================================================================
   Q2a. Pareto curve: how concentrated is revenue across products?
   ---------------------------------------------------------------------
   Period: Jan 1 - Jun 30, 2025 (baseline).

   One row per product, sorted from best seller to worst, with a running
   total. Reading down the list answers questions like "how many products
   does it take to reach 80% of revenue?" This feeds the Pareto chart.

   New idea: WINDOW FUNCTIONS (the OVER (...) clause)
   A normal SUM() collapses many rows into one. A window function
   calculates across rows but keeps every row. That is how we get a
   running total next to each product, like an Excel running-sum column.
   ===================================================================== */

WITH sku_revenue AS (
    -- Step 1: revenue per product. The date filter sits in the JOIN's ON
    -- clause (not in WHERE) so products with zero sales still appear,
    -- with revenue 0. Filtering in WHERE would silently drop them.
    SELECT
        p.sku_id,
        p.product_name,
        p.category,
        COALESCE(SUM(s.net_sales), 0) AS revenue
    FROM products AS p
    LEFT JOIN daily_sales AS s
        ON  s.sku_id = p.sku_id
        AND s.sale_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
    GROUP BY p.sku_id, p.product_name, p.category
)

SELECT
    sku_id,
    product_name,
    category,
    revenue,

    -- Position in the ranking: 1 = best seller. sku_id breaks ties so
    -- the order is the same every time the query runs.
    ROW_NUMBER() OVER (ORDER BY revenue DESC, sku_id) AS revenue_rank,

    -- What % of all products are at or above this rank?
    -- COUNT(*) OVER () = total number of products (an empty OVER() means "all rows").
    ROUND(100.0 * ROW_NUMBER() OVER (ORDER BY revenue DESC, sku_id)
          / COUNT(*) OVER (), 2)                     AS cumulative_pct_of_skus,

    -- Running total of revenue down the ranking, as a % of all revenue.
    -- "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" = from the top
    -- of the list down to this row.
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC, sku_id
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(revenue) OVER (), 2)                 AS cumulative_pct_of_revenue
FROM sku_revenue
ORDER BY revenue_rank;
