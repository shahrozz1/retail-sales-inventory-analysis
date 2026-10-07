/* =====================================================================
   SCHEMA: Retail Sales & Inventory database (DuckDB)
   ---------------------------------------------------------------------
   Five tables, modeled on what a convenience store's systems export:

     products          one row per item the store carries (the "item master")
     daily_sales       one row per item per day it SOLD (POS export; no zero rows)
     daily_inventory   one row per item per day: deliveries + end-of-day stock count
     reorder_settings  the reorder rules in effect, with the date each took effect
     price_changes     a log of every shelf-price change and why it was made

   A few design choices worth knowing:
   - Money columns use DECIMAL, not floating point, so cents never drift.
   - daily_sales only has rows for days an item actually sold, just like a
     real POS export. Days with zero sales must be filled in as 0 by the
     query (see 04_reorder_points.sql) or averages come out too high.
   - Cost of goods sold is not stored; it is calculated as
     units_sold * products.unit_cost, so it can never disagree with the
     item master.
   ===================================================================== */

CREATE TABLE products (
    sku_id            VARCHAR PRIMARY KEY,      -- store item number, e.g. 'SKU-001'
    product_name      VARCHAR      NOT NULL,
    category          VARCHAR      NOT NULL,
    vendor            VARCHAR      NOT NULL,
    unit_cost         DECIMAL(8,2) NOT NULL,    -- what the store pays per unit
    regular_price     DECIMAL(8,2) NOT NULL,    -- shelf price on Jan 1, 2025
    shelf_facings     INTEGER      NOT NULL,    -- shelf space: how many units sit side-by-side at the front of the shelf
    case_pack         INTEGER      NOT NULL,    -- the vendor ships in multiples of this many units
    lead_time_days    INTEGER      NOT NULL,    -- days between placing an order and receiving it
    is_active         BOOLEAN      NOT NULL,    -- FALSE once an item is discontinued
    discontinued_date DATE                      -- NULL if the item is still carried
);

CREATE TABLE daily_sales (
    sale_date   DATE          NOT NULL,
    sku_id      VARCHAR       NOT NULL REFERENCES products (sku_id),
    units_sold  INTEGER       NOT NULL,
    net_sales   DECIMAL(10,2) NOT NULL,         -- dollars collected (units x the price that day)
    PRIMARY KEY (sale_date, sku_id)
);

CREATE TABLE daily_inventory (
    snapshot_date   DATE    NOT NULL,
    sku_id          VARCHAR NOT NULL REFERENCES products (sku_id),
    units_received  INTEGER NOT NULL,           -- delivered that morning (0 on most days)
    on_hand_units   INTEGER NOT NULL,           -- stock left at close of business
    PRIMARY KEY (snapshot_date, sku_id)
);

CREATE TABLE reorder_settings (
    sku_id          VARCHAR NOT NULL REFERENCES products (sku_id),
    effective_date  DATE    NOT NULL,
    reorder_point   INTEGER NOT NULL,           -- when stock falls to this level, place an order
    max_stock       INTEGER NOT NULL,           -- order enough to bring stock back up to this level
    order_multiple  INTEGER NOT NULL,           -- order in multiples of this: the case pack, or 1 = single units
    PRIMARY KEY (sku_id, effective_date)
);

CREATE TABLE price_changes (
    sku_id          VARCHAR      NOT NULL REFERENCES products (sku_id),
    effective_date  DATE         NOT NULL,
    old_price       DECIMAL(8,2) NOT NULL,
    new_price       DECIMAL(8,2) NOT NULL,
    reason          VARCHAR      NOT NULL,
    PRIMARY KEY (sku_id, effective_date)
);
