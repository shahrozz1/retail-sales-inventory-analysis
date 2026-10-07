/* =====================================================================
   Bonus. Which products are priced below their category's normal margin?
   ---------------------------------------------------------------------
   Shelf prices that aren't reviewed regularly fall behind rising vendor
   costs, so margin % quietly slips on some items.

   Approach: compare each item's margin % to the MEDIAN margin of its
   category. The median (middle value) is used instead of the average
   so one extreme item can't skew the benchmark. Anything more than
   3 points below its category median is flagged, with a suggested price
   that would bring it back to the median.

   Tobacco is excluded: its pricing is set by manufacturer programs and
   state rules, so a store can't simply reprice it.

   Like Q1-Q4 this is a July 1 diagnosis, so it looks at every product
   carried on that date (items cut later are still included here).

   Suggested price math: if the target margin is m, then
     price = cost / (1 - m)
   then rounded up to the next price ending in 9 (e.g. 3.42 -> 3.49).
   ===================================================================== */

WITH item_margin AS (
    -- Step 1: margin % per item at its current regular price.
    SELECT
        sku_id,
        product_name,
        category,
        unit_cost,
        regular_price,
        (regular_price - unit_cost) / regular_price AS margin
    FROM products
    WHERE category <> 'Tobacco'
),

category_median AS (
    -- Step 2: the middle margin in each category.
    SELECT
        category,
        MEDIAN(margin) AS median_margin
    FROM item_margin
    GROUP BY category
)

SELECT
    i.sku_id,
    i.product_name,
    i.category,
    i.unit_cost,
    i.regular_price,
    ROUND(100 * i.margin, 1)          AS margin_pct,
    ROUND(100 * c.median_margin, 1)   AS category_median_pct,
    -- Round UP to the next 10 cents, then subtract 1 cent -> ends in 9.
    CEIL(i.unit_cost / (1 - c.median_margin) * 10) / 10 - 0.01 AS suggested_price
FROM item_margin AS i
JOIN category_median AS c
    ON c.category = i.category
WHERE i.margin < c.median_margin - 0.03
ORDER BY i.category, i.margin, i.sku_id;
