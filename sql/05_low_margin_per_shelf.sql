/* =====================================================================
   Q4. Which products have the lowest margin relative to shelf space
       and could be cut?
   ---------------------------------------------------------------------
   Period: Jan 1 - Jun 30, 2025 (baseline = 26 weeks).

   In a convenience store, shelf space is the scarcest resource. So the
   real question isn't "which item has the lowest margin %" but "which
   item earns the least for the space it takes up?"

     Gross profit          = revenue - (units sold x unit cost)
     GP per facing per wk  = gross profit / shelf facings / 26 weeks
       A "facing" is one product-width slot at the front of the shelf.

   Business rule: top-20% revenue items are EXCLUDED even if their margin
   is thin. Items like milk and cigarettes are traffic drivers: people
   come in for them and buy other things while they're there, so cutting
   them would cost far more than their own margin.

   Output: the 15 weakest items, with their category's average for
   comparison. These became the cut list.
   ===================================================================== */

WITH sku_perf AS (
    -- Step 1: revenue and cost of goods per product.
    -- Date filter is in the ON clause so items with no sales stay in.
    SELECT
        p.sku_id,
        p.product_name,
        p.category,
        p.shelf_facings,
        COALESCE(SUM(s.net_sales), 0)                AS revenue,
        COALESCE(SUM(s.units_sold), 0) * p.unit_cost AS cost_of_goods
    FROM products AS p
    LEFT JOIN daily_sales AS s
        ON  s.sku_id = p.sku_id
        AND s.sale_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
    GROUP BY p.sku_id, p.product_name, p.category, p.shelf_facings, p.unit_cost
),

scored AS (
    -- Step 2: profit per facing, the revenue group, and a category benchmark.
    SELECT
        *,
        revenue - cost_of_goods                                  AS gross_profit,
        (revenue - cost_of_goods) / shelf_facings / 26.0         AS gp_per_facing_per_week,
        NTILE(5) OVER (ORDER BY revenue DESC, sku_id)            AS revenue_quintile,
        -- PARTITION BY = "calculate separately for each category".
        -- Computed here, before the WHERE below, so the benchmark
        -- includes every product in the category.
        AVG((revenue - cost_of_goods) / shelf_facings / 26.0)
            OVER (PARTITION BY category)                         AS category_avg_gp_per_facing
    FROM sku_perf
)

SELECT
    sku_id,
    product_name,
    category,
    shelf_facings,
    ROUND(revenue, 2)                                    AS revenue,
    ROUND(gross_profit, 2)                               AS gross_profit,
    ROUND(100.0 * gross_profit / NULLIF(revenue, 0), 1)  AS margin_pct,
    ROUND(gp_per_facing_per_week, 2)                     AS gp_per_facing_per_week,
    ROUND(category_avg_gp_per_facing, 2)                 AS category_avg_gp_per_facing
FROM scored
WHERE revenue_quintile > 1                               -- protect the top-20% traffic drivers
ORDER BY gp_per_facing_per_week ASC, sku_id      -- sku_id breaks ties, so the list is the same every run
LIMIT 15;
