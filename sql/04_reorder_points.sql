/* =====================================================================
   Q3. What reorder points would minimize both stockouts and overstock
       for top-selling items?
   ---------------------------------------------------------------------
   Period: Jan 1 - Jun 30, 2025 (baseline).
   Scope:  the top 20% of products by revenue (same grouping as Q2b).

   The standard reorder-point formula:
     Reorder point = (avg daily demand x lead time) + safety stock
         -> enough stock to cover sales while we wait for the delivery...
     Safety stock  = Z x (std dev of daily demand) x SQRT(lead time)
         -> ...plus a cushion for days busier than average.
     Z = 1.65 means a 95% chance of NOT running out during the wait.
     Max stock     = reorder point + 7 days of average demand
         -> each order brings in about one week of sales, matching the
            weekly delivery cycle. Ordering more just sits on the shelf.

   Two data traps this query handles:
   1. daily_sales has no rows for zero-sale days. We start from
      daily_inventory (one row per item per day) and LEFT JOIN sales, so
      zero days count as 0. Skipping them would overstate demand.
   2. On days the item was out of stock (0 on hand at close), sales were
      capped by what we had, not by what customers wanted ("censored
      demand"). We leave those days out of the average and std dev.

   Output: current vs recommended settings, plus how many stockout days
   each item had, so the case for each change is visible.
   ===================================================================== */

WITH daily AS (
    -- Step 1: one row per product per day, zero-sale days included.
    SELECT
        i.sku_id,
        i.snapshot_date,
        i.on_hand_units,
        COALESCE(s.units_sold, 0) AS units_sold
    FROM daily_inventory AS i
    LEFT JOIN daily_sales AS s
        ON  s.sku_id    = i.sku_id
        AND s.sale_date = i.snapshot_date
    WHERE i.snapshot_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
),

demand AS (
    -- Step 2: demand statistics per product.
    -- CASE WHEN ... THEN units_sold END returns NULL on stockout days,
    -- and AVG / STDDEV skip NULLs, so those days drop out of the math.
    SELECT
        sku_id,
        AVG(CASE WHEN on_hand_units > 0 THEN units_sold END)         AS avg_daily_demand,
        STDDEV_SAMP(CASE WHEN on_hand_units > 0 THEN units_sold END) AS sd_daily_demand,
        SUM(CASE WHEN on_hand_units = 0 THEN 1 ELSE 0 END)           AS stockout_days,
        AVG(on_hand_units)                                           AS avg_on_hand
    FROM daily
    GROUP BY sku_id
),

top_sellers AS (
    -- Step 3: the top 20% of products by revenue (quintile 1).
    -- Window functions run AFTER GROUP BY, so inside OVER (...) the
    -- SUM(net_sales) is already each product's total revenue.
    SELECT sku_id
    FROM (
        SELECT
            sku_id,
            NTILE(5) OVER (ORDER BY SUM(net_sales) DESC, sku_id) AS revenue_quintile
        FROM daily_sales
        WHERE sale_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
        GROUP BY sku_id
    ) AS q
    WHERE revenue_quintile = 1
),

current_settings AS (
    -- Step 4: the reorder rules that were in place during the baseline.
    SELECT sku_id, reorder_point, max_stock
    FROM reorder_settings
    WHERE effective_date = DATE '2025-01-01'
),

recommended AS (
    -- Step 5: apply the formula. CEIL rounds up: a fraction of a can
    -- can't be ordered, and rounding down would add stockout risk.
    SELECT
        p.sku_id,
        p.product_name,
        p.category,
        p.lead_time_days,
        d.avg_daily_demand,
        d.sd_daily_demand,
        d.stockout_days,
        d.avg_on_hand,
        c.reorder_point AS current_reorder_point,
        c.max_stock     AS current_max_stock,
        CEIL(d.avg_daily_demand * p.lead_time_days
             + 1.65 * d.sd_daily_demand * SQRT(p.lead_time_days)) AS recommended_reorder_point
    FROM top_sellers AS t
    JOIN products         AS p ON p.sku_id = t.sku_id
    JOIN demand           AS d ON d.sku_id = t.sku_id
    JOIN current_settings AS c ON c.sku_id = t.sku_id
)

SELECT
    sku_id,
    product_name,
    category,
    lead_time_days,
    ROUND(avg_daily_demand, 1)                                   AS avg_daily_demand,
    ROUND(sd_daily_demand, 1)                                    AS sd_daily_demand,
    stockout_days,
    ROUND(avg_on_hand)                                           AS avg_on_hand,
    current_reorder_point,
    recommended_reorder_point::INTEGER                           AS recommended_reorder_point,
    current_max_stock,
    CEIL(recommended_reorder_point + 7 * avg_daily_demand)::INTEGER AS recommended_max_stock,
    CASE
        WHEN recommended_reorder_point > current_reorder_point THEN 'Raise (stockout risk)'
        WHEN recommended_reorder_point < current_reorder_point THEN 'Lower (overstock)'
        ELSE 'Keep'
    END                                                          AS action
FROM recommended
ORDER BY stockout_days DESC, avg_daily_demand DESC, sku_id;
