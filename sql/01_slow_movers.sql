/* =====================================================================
   Q1. Which products have the slowest sell-through and are tying up
       cash in inventory?
   ---------------------------------------------------------------------
   Period: Jan 1 - Jun 30, 2025 (the "baseline" half-year). I only use
   data I would have had on July 1, when the changes were made, so the
   diagnosis is not using hindsight.

   Definitions
   - Sell-through %  = units sold / (units sold + units still on hand)
                       "Of everything we had available, how much sold?"
                       Below 50% means more is sitting on the shelf than
                       we sold in the last six months.
   - Cash tied up    = units on hand at period end x unit cost
                       Money already spent that hasn't come back as a sale.
   - Days of supply  = units on hand / average units sold per day
                       "At this pace, how many days until we run out?"

   Output: the 20 products with the lowest sell-through (the slowest 10%
   of the catalog), sorted by how much cash each one ties up, so the
   biggest problems are at the top. These are the first candidates to
   stop reordering, mark down, or order in smaller quantities.
   ===================================================================== */

WITH baseline_sales AS (
    -- Step 1: total units sold per product during the baseline period.
    SELECT
        sku_id,
        SUM(units_sold) AS units_sold
    FROM daily_sales
    WHERE sale_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
    GROUP BY sku_id
),

ending_stock AS (
    -- Step 2: what was still on the shelf at close of business June 30.
    SELECT
        sku_id,
        on_hand_units
    FROM daily_inventory
    WHERE snapshot_date = DATE '2025-06-30'
),

sku_metrics AS (
    -- Step 3: combine the two and calculate the three metrics.
    -- LEFT JOIN keeps products that sold nothing at all (they have no
    -- rows in daily_sales); COALESCE turns their missing total into 0.
    SELECT
        p.sku_id,
        p.product_name,
        p.category,
        COALESCE(s.units_sold, 0)              AS units_sold,
        e.on_hand_units,
        p.unit_cost,
        -- NULLIF(x, 0) returns NULL instead of 0, which prevents a
        -- divide-by-zero error for products with nothing sold and nothing on hand.
        100.0 * COALESCE(s.units_sold, 0)
            / NULLIF(COALESCE(s.units_sold, 0) + e.on_hand_units, 0)
                                               AS sell_through_pct,
        e.on_hand_units * p.unit_cost          AS cash_tied_up,
        -- 181 = number of days from Jan 1 to Jun 30, 2025.
        e.on_hand_units / NULLIF(COALESCE(s.units_sold, 0) / 181.0, 0)
                                               AS days_of_supply
    FROM products AS p
    JOIN ending_stock AS e
        ON e.sku_id = p.sku_id
    LEFT JOIN baseline_sales AS s
        ON s.sku_id = p.sku_id
),

slowest_20 AS (
    -- Step 4: the 20 products with the lowest sell-through.
    SELECT *
    FROM sku_metrics
    ORDER BY sell_through_pct ASC, sku_id     -- sku_id breaks ties, so the same 20 come back every run
    LIMIT 20
)

-- Step 5: re-sort that shortlist by dollars at stake.
SELECT
    sku_id,
    product_name,
    category,
    units_sold,
    on_hand_units,
    ROUND(sell_through_pct, 1)  AS sell_through_pct,
    ROUND(cash_tied_up, 2)      AS cash_tied_up,
    ROUND(days_of_supply)       AS days_of_supply   -- NULL = sold nothing, so it would never run out
FROM slowest_20
ORDER BY cash_tied_up DESC, sku_id;
