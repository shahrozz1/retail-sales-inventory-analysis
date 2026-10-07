"""
generate_data.py - builds the simulated store database (data/store.duckdb).

The real POS history isn't available anymore, so this script recreates a
realistic year for a small-town convenience store, modeled on the store I
managed. How it works:

  1. CATALOG   200 products in 12 categories, each with a cost, price,
               shelf space, vendor case size and delivery lead time.
               Popularity follows a long tail: a few items sell dozens
               a day, many sell a few a month.
  2. JAN-JUN   Simulate every day under the store's OLD ordering habits:
               reorder points set by gut feel with no safety stock,
               shelves kept "looking full", vendors ship whole cases.
  3. JULY 1    Run my own analysis queries (sql/01, 04, 05, 06) on the
               first six months and turn the results into decisions:
               cut the weakest items, fix reorder points, reprice.
  4. JUL-DEC   Simulate the rest of the year under the NEW rules.

The before/after results are therefore not typed in by hand. They come
out of the simulation after the SQL-driven decisions are applied.

Run:  python src/generate_data.py
"""

import math
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "store.duckdb"
SQL_DIR = ROOT / "sql"

# Same seed -> same data every run. Results vary somewhat from seed to seed
# (see src/check_seeds.py); seed 13 is the run closest to the median of 20.
SEED = 13
START = date(2025, 1, 1)
WARMUP_DAYS = 730                # run the old habits for 2 years before Jan 1 (not saved)
SIM_ORIGIN = START - timedelta(days=WARMUP_DAYS)
CHANGE_DATE = date(2025, 7, 1)   # the day the new decisions take effect
END = date(2025, 12, 31)

# ---------------------------------------------------------------------------
# 1. CATALOG
# Each category lists its products from most to least popular. Daily demand
# for the i-th product is roughly  top_rate / (i + 1) ** decay , so it falls
# off quickly down the list: that is what creates the "80/20" pattern.
# An optional third value in a product tuple fixes that item's margin.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "Soft Drinks": dict(
        vendor="Soft drink bottler (DSD)", lead_time=2, case_packs=[24], facings=(2, 4),
        margin=(0.38, 0.48), top_rate=30, decay=0.75, season="beverage",
        items=[("Coca-Cola 20oz", 2.49), ("Mountain Dew 20oz", 2.49), ("Dr Pepper 20oz", 2.49),
               ("Pepsi 20oz", 2.49), ("Diet Coke 20oz", 2.49), ("Coca-Cola 2L", 3.49),
               ("Sprite 20oz", 2.49), ("Big Red 20oz", 2.29), ("Mountain Dew 2L", 3.49),
               ("Dr Pepper 2L", 3.49), ("Coca-Cola 12pk Cans", 8.99), ("Coke Zero 20oz", 2.49),
               ("Pepsi 2L", 3.29), ("Fanta Orange 20oz", 2.29), ("Sunkist 20oz", 2.29),
               ("Pepsi 12pk Cans", 8.49), ("A&W Root Beer 20oz", 2.29), ("Diet Dr Pepper 20oz", 2.49),
               ("7UP 20oz", 2.29), ("Canada Dry Ginger Ale 20oz", 2.29), ("Mug Root Beer 2L", 2.99),
               ("Fresca 12pk Cans", 7.99)]),
    "Energy Drinks": dict(
        vendor="Soft drink bottler (DSD)", lead_time=3, case_packs=[12, 24], facings=(1, 3),
        margin=(0.34, 0.42), top_rate=11, decay=0.75, season="beverage",
        items=[("Monster Energy 16oz", 3.29), ("Red Bull 8.4oz", 3.49), ("Monster Zero Ultra 16oz", 3.29),
               ("Celsius 12oz", 3.29), ("Red Bull 12oz", 4.29), ("Rockstar 16oz", 2.99),
               ("Reign 16oz", 2.99), ("NOS 16oz", 2.99), ("Monster Java 15oz", 3.49),
               ("Red Bull Sugarfree 8.4oz", 3.49), ("Ghost Energy 16oz", 3.49), ("Alani Nu 12oz", 3.29),
               ("5-hour Energy 2oz", 3.99), ("Starbucks Doubleshot 15oz", 3.79)]),
    "Water & Sports Drinks": dict(
        vendor="Soft drink bottler (DSD)", lead_time=2, case_packs=[12, 24], facings=(1, 3),
        margin=(0.40, 0.52), top_rate=9, decay=0.75, season="water",
        items=[("Ozarka Water 16.9oz", 1.49), ("Gatorade Fruit Punch 28oz", 2.79),
               ("Gatorade Cool Blue 28oz", 2.79), ("Powerade Mountain Berry 28oz", 2.49),
               ("Dasani 20oz", 1.99), ("Ozarka Water 24pk", 6.99), ("BodyArmor Strawberry Banana 28oz", 2.99),
               ("Gatorade Zero Glacier Cherry 28oz", 2.79), ("Smartwater 1L", 2.99),
               ("Vitaminwater XXX 20oz", 2.49), ("Propel Berry 24oz", 1.99), ("Gatorade Lemon-Lime 28oz", 2.79)]),
    "Salty Snacks": dict(
        vendor="Snack distributor (DSD)", lead_time=3, case_packs=[6, 8, 12], facings=(1, 3),
        margin=(0.34, 0.42), top_rate=9, decay=0.75, season="flat",
        items=[("Doritos Nacho Cheese 2.75oz", 2.49), ("Cheetos Flamin' Hot 2.5oz", 2.49),
               ("Takis Fuego 4oz", 2.99), ("Lay's Classic 2.6oz", 2.49), ("Funyuns 2.25oz", 2.29),
               ("Doritos Cool Ranch 2.75oz", 2.49), ("Slim Jim Giant", 2.49), ("Fritos Original 3.25oz", 2.29),
               ("David Sunflower Seeds 5.25oz", 2.29), ("Ruffles Cheddar & Sour Cream 2.5oz", 2.49),
               ("Cheetos Crunchy 3.25oz", 2.49), ("Lay's Barbecue 2.6oz", 2.49), ("Chex Mix Traditional 3.75oz", 2.29),
               ("Planters Salted Peanuts 1.75oz", 1.99), ("Pringles Original 5.2oz", 2.99),
               ("Jack Link's Beef Jerky 3.25oz", 8.99), ("Combos Cheddar Cheese 6.3oz", 2.29),
               ("Rold Gold Pretzels 3oz", 2.29), ("Smartfood White Cheddar 2.5oz", 2.49),
               ("Munchies Snack Mix 3oz", 2.49), ("Lay's Classic Party Size 13oz", 5.49),
               ("Mac's Pork Skins 2.5oz", 1.99)]),
    "Candy & Gum": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=6, case_packs=[6, 12, 18], facings=(1, 2),
        margin=(0.38, 0.48), top_rate=7, decay=0.9, season="candy",
        items=[("Snickers 1.86oz", 1.99), ("Reese's Peanut Butter Cups 1.5oz", 1.99), ("M&M's Peanut 1.74oz", 1.99),
               ("Twix 1.79oz", 1.99), ("Skittles Original 2.17oz", 1.99), ("Kit Kat 1.5oz", 1.99),
               ("Extra Spearmint Gum 15ct", 1.79), ("Hershey's Milk Chocolate 1.55oz", 1.99),
               ("Starburst Original 2.07oz", 1.99), ("Sour Patch Kids 2oz", 1.79), ("Reese's King Size 2.8oz", 3.29),
               ("Snickers King Size 3.29oz", 3.29), ("Orbit Peppermint Gum 14ct", 1.79), ("Butterfinger 1.9oz", 1.99),
               ("Airheads Taffy Bar", 0.49), ("Blow Pop", 0.39), ("Payday 1.85oz", 1.99), ("3 Musketeers 1.92oz", 1.99),
               ("Milky Way 1.84oz", 1.99), ("Jolly Rancher Hard Candy 7oz", 3.49), ("Life Savers Wint O Green 6.25oz", 3.69),
               ("Trident Original Gum 14ct", 1.79), ("Hot Tamales 5oz Box", 1.79), ("Mike and Ike Original 5oz Box", 1.79)]),
    "Tobacco": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=5, case_packs=[10], facings=(1, 2),
        margin=(0.11, 0.16), top_rate=17, decay=0.9, season="flat",
        items=[("Marlboro Red Pack", 8.99), ("Newport Menthol Pack", 9.49), ("Marlboro Gold Pack", 8.99),
               ("Camel Blue Pack", 8.79), ("Pall Mall Red Pack", 7.49), ("Grizzly Wintergreen Long Cut", 6.49),
               ("Zyn Cool Mint 6mg", 5.99), ("Winston Red Pack", 7.79), ("Copenhagen Long Cut", 7.99),
               ("Black & Mild Original Cigar", 1.29), ("Swisher Sweets Cigarillo 2pk", 1.49),
               ("L&M Red Pack", 7.29), ("Skoal Wintergreen Long Cut", 7.49), ("Backwoods Honey Cigars 5pk", 9.99)]),
    "Grocery": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=6, case_packs=[6, 12, 24], facings=(1, 2),
        margin=(0.20, 0.32), top_rate=7, decay=1.0, season="flat",
        items=[("Little Debbie Honey Bun", 1.29), ("Nature's Own Butterbread", 3.99), ("Maruchan Ramen Chicken", 0.79),
               ("Vienna Sausage 4.6oz", 1.49), ("Kraft Mac & Cheese 7.25oz", 2.29), ("Campbell's Chicken Noodle Soup", 2.49),
               ("Pop-Tarts Strawberry 2ct", 1.99), ("Chef Boyardee Beef Ravioli", 2.79), ("StarKist Chunk Light Tuna", 1.99),
               ("Hormel Chili with Beans", 3.49), ("Spam Classic 12oz", 5.49), ("Bush's Baked Beans 16oz", 2.99),
               ("Ro-Tel Original 10oz", 1.99), ("Saltine Crackers 16oz", 3.99), ("Jif Creamy Peanut Butter 16oz", 4.99),
               ("Smucker's Grape Jelly 18oz", 4.49), ("Frosted Flakes 13.5oz", 5.99), ("Cheerios 8.9oz", 6.49),
               ("Heinz Ketchup 20oz", 3.99), ("Imperial Sugar 4lb", 4.99), ("Hellmann's Mayonnaise 30oz", 6.99),
               ("Gold Medal Flour 5lb", 4.49), ("Crisco Vegetable Oil 48oz", 6.49), ("Folgers Classic Roast 25oz", 13.99)]),
    "Dairy & Refrigerated": dict(
        vendor="Dairy distributor (DSD)", lead_time=2, case_packs=[4, 6], facings=(1, 3),
        margin=(0.18, 0.30), top_rate=9, decay=0.75, season="flat",
        items=[("Whole Milk Gallon", 4.29), ("2% Milk Gallon", 4.29), ("Large Eggs Dozen", 3.99),
               ("Sweet Tea Gallon", 3.49), ("Chocolate Milk Pint", 1.99), ("Kraft Singles 12ct", 4.49),
               ("Oscar Mayer Bologna 16oz", 3.99), ("Lunchables Turkey & Cheddar", 3.49), ("Butter 1lb", 5.49),
               ("Shredded Cheddar 8oz", 3.99), ("Orange Juice Half Gallon", 4.99), ("Coffee-mate French Vanilla 32oz", 5.49)]),
    "Frozen & Ice": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=5, case_packs=[6, 12], facings=(1, 2),
        margin=(0.30, 0.42), top_rate=10, decay=0.8, season="frozen",
        items=[("Bagged Ice 10lb", 2.99, 0.58), ("Blue Bell Homemade Vanilla Pint", 4.49), ("Hot Pockets Pepperoni 2ct", 3.49),
               ("Totino's Party Pizza", 2.99), ("Nestle Drumstick Cone", 2.49), ("Jimmy Dean Sausage Biscuit", 3.99),
               ("Totino's Pizza Rolls 15ct", 4.49), ("Ice Cream Sandwich", 1.99), ("Banquet Salisbury Steak Meal", 2.49),
               ("El Monterey Beef & Bean Burrito", 1.99), ("Bomb Pop Original", 1.29), ("Blue Bell Homemade Vanilla Half Gallon", 8.99)]),
    "Health & Beauty": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=7, case_packs=[3, 6, 12], facings=(1, 2),
        margin=(0.40, 0.55), top_rate=0.8, decay=1.0, season="hba",
        items=[("Advil Tablets 24ct", 7.99), ("Tylenol Extra Strength 24ct", 8.49), ("Tums Ultra Assorted 72ct", 6.49),
               ("ChapStick Classic", 2.99), ("Band-Aid Assorted 30ct", 5.99), ("Pepto-Bismol 8oz", 7.99),
               ("Alka-Seltzer Plus Cold 20ct", 6.99), ("Benadryl Allergy 24ct", 7.99), ("Travel Toothpaste 0.85oz", 2.49),
               ("Speed Stick Deodorant", 5.49), ("Banana Boat Sunscreen SPF30", 9.99), ("Vicks DayQuil 8oz", 11.99),
               ("Toothbrush Medium", 2.99), ("Zyrtec 24hr 5ct", 8.99), ("Suave Shampoo 12.6oz", 4.49),
               ("Neosporin Ointment 0.5oz", 8.99), ("Rubbing Alcohol 16oz", 3.49), ("Reading Glasses +1.50", 9.99)]),
    "Household & Paper": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=7, case_packs=[6, 12], facings=(1, 3),
        margin=(0.28, 0.40), top_rate=1.6, decay=1.0, season="household",
        items=[("Toilet Paper 4 Roll", 5.49), ("Paper Towels 2 Roll", 4.99), ("Duracell AA Batteries 4pk", 7.99),
               ("Dawn Dish Soap 8oz", 3.49), ("Hefty Trash Bags 13gal 20ct", 7.99), ("Clorox Bleach 43oz", 4.49),
               ("Kingsford Charcoal 8lb", 9.99), ("Duracell AAA Batteries 4pk", 7.99), ("Reynolds Aluminum Foil 30sqft", 4.99),
               ("Paper Plates 50ct", 4.49), ("Tide Pods 16ct", 8.99), ("Kingsford Lighter Fluid 32oz", 5.49),
               ("LED Light Bulbs 2pk", 6.99), ("USB-C Charging Cable 6ft", 12.99)]),
    "Automotive": dict(
        vendor="Grocery wholesaler (weekly truck)", lead_time=7, case_packs=[6, 12], facings=(1, 3),
        margin=(0.30, 0.42), top_rate=1.0, decay=1.1, season="automotive",
        items=[("Little Trees Air Freshener", 1.99), ("Motor Oil 5W-30 1qt", 8.99), ("Windshield Washer Fluid 1gal", 4.49),
               ("Motor Oil 10W-30 1qt", 8.99), ("Antifreeze 50/50 1gal", 15.99), ("Fix-a-Flat 16oz", 11.99),
               ("Octane Booster 15oz", 6.99), ("Fuel Injector Cleaner 12oz", 7.99), ("Tire Pressure Gauge", 4.99),
               ("Brake Fluid 12oz", 6.99), ("Power Steering Fluid 12oz", 7.49), ("Wiper Blade 22in", 14.99)]),
}

# Scales every product's demand so the store does roughly $2,000 a day.
DEMAND_SCALE = 1.15

# Month-by-month demand multipliers (Jan..Dec). 1.0 = an average month.
SEASONALITY = {
    "flat":       [0.95, 0.94, 0.98, 1.00, 1.02, 1.03, 1.03, 1.02, 1.00, 1.00, 0.99, 1.04],
    "beverage":   [0.86, 0.88, 0.95, 1.00, 1.08, 1.17, 1.20, 1.18, 1.07, 0.98, 0.88, 0.86],
    "water":      [0.70, 0.74, 0.88, 1.00, 1.16, 1.34, 1.40, 1.36, 1.14, 0.94, 0.72, 0.68],
    "frozen":     [0.68, 0.72, 0.86, 1.00, 1.18, 1.38, 1.45, 1.40, 1.15, 0.92, 0.70, 0.66],
    "candy":      [0.94, 1.08, 0.96, 1.00, 0.96, 0.95, 0.95, 0.96, 0.98, 1.24, 1.00, 1.10],
    "hba":        [1.20, 1.18, 1.05, 0.98, 0.95, 0.92, 0.90, 0.92, 0.95, 1.00, 1.10, 1.20],
    "household":  [1.00, 0.96, 0.98, 1.00, 1.04, 1.06, 1.06, 1.04, 1.00, 0.96, 0.96, 1.00],
    "automotive": [1.25, 1.15, 1.00, 0.92, 0.88, 0.88, 0.88, 0.90, 0.95, 1.05, 1.15, 1.25],
}

# Mon..Sun multipliers: Friday/Saturday are the busiest days.
DAY_OF_WEEK = np.array([0.95, 0.92, 0.95, 1.00, 1.15, 1.15, 0.88])

# Units that fit behind each facing: the old habit was to keep every slot full.
SHELF_DEPTH = 8

# Share of products that used to sell much better than they do now. Their
# reorder settings were set back then and never revisited, which is the most
# common way dead stock builds up. FADE_RANGE = how many times faster they used to sell.
# Tobacco is excluded: the manager counts it every day, so it can't drift unnoticed.
FADED_SHARE = 0.15
FADE_RANGE = (2, 4)

# Items keep fading DURING the year too (tastes change). Each one's sales
# slide down to 1/3 over about 3 months while its reorder settings stay put,
# so new dead stock keeps forming unless someone keeps checking.
FADING_IN_YEAR_SHARE = 0.08
FADE_FLOOR = 1 / 3
FADE_DAYS = 90

# How often the OLD habits re-ordered (days of stock per order) by vendor type.
OLD_REVIEW_DAYS = {"DSD": 14, "wholesaler": 21}

# Share of products whose vendor cost went up without the shelf price following.
COST_CREEP_SHARE = 0.50
COST_CREEP_RANGE = (1.10, 1.20)     # cost rose 10-20%

PRICE_ELASTICITY = -0.8     # a 10% price increase loses about 8% of units
CLEARANCE_LIFT = 1.6        # clearance pricing sells discontinued items 60% faster


def build_catalog(rng):
    """Create the 200-product item master plus each product's true demand rate."""
    rows = []
    for category, cfg in CATEGORIES.items():
        for i, item in enumerate(cfg["items"]):
            name, price = item[0], item[1]
            margin = item[2] if len(item) > 2 else rng.uniform(*cfg["margin"])
            # Popularity: falls off down the list, with some randomness so
            # the order isn't perfectly smooth.
            base_rate = DEMAND_SCALE * cfg["top_rate"] / (i + 1) ** cfg["decay"] * rng.lognormal(0, 0.45)
            low, high = cfg["facings"]
            facings = int(rng.integers(low, high + 1)) + (1 if i < 3 else 0)
            cost = price * (1 - margin)
            can_fade = i >= 3 and category != "Tobacco"     # best sellers and tobacco don't fade
            # Vendor price increases that were never passed on to the shelf
            # price: this quietly squeezes margin (tobacco is set by the
            # manufacturer, so it's excluded).
            if category != "Tobacco" and rng.random() < COST_CREEP_SHARE:
                cost = min(cost * rng.uniform(*COST_CREEP_RANGE), price * 0.88)
            rows.append(dict(
                product_name=name,
                category=category,
                vendor=cfg["vendor"],
                unit_cost=round(cost, 2),
                regular_price=price,
                shelf_facings=facings,
                case_pack=int(rng.choice(cfg["case_packs"])),
                lead_time_days=cfg["lead_time"],
                base_rate=base_rate,
                season=cfg["season"],
                faded=can_fade and rng.random() < FADED_SHARE,
                # Day of the year (0-364) this item starts fading, or None.
                fade_start=(int(rng.integers(0, 365))
                            if can_fade and rng.random() < FADING_IN_YEAR_SHARE else None),
            ))
    catalog = pd.DataFrame(rows)
    catalog.insert(0, "sku_id", [f"SKU-{n:03d}" for n in range(1, len(catalog) + 1)])
    return catalog


def old_reorder_settings(catalog, rng):
    """The 'gut feel' rules in place before the project.

    Reorder points cover only the lead time (no safety stock) and are based
    on a rough guess of demand, so fast sellers run out. Max stock is padded
    to keep shelves looking full, and faded items are still ordered as if
    they sold like they used to, so slow sellers pile up.
    """
    guess = catalog["base_rate"] * rng.lognormal(0, 0.4, len(catalog))   # demand as the manager perceived it
    fade = np.where(catalog["faded"], rng.uniform(*FADE_RANGE, len(catalog)), 1.0)
    guess = guess * fade
    review = np.where(catalog["vendor"].str.contains("DSD"), OLD_REVIEW_DAYS["DSD"], OLD_REVIEW_DAYS["wholesaler"])
    rop = np.maximum(1, np.round(guess * catalog["lead_time_days"])).astype(int)
    max_stock = np.maximum.reduce([
        rop + catalog["case_pack"],
        rop + np.round(guess * review).astype(int),
        catalog["shelf_facings"] * SHELF_DEPTH,   # "a full-looking shelf"
    ])
    return pd.DataFrame({"sku_id": catalog["sku_id"], "effective_date": START,
                         "reorder_point": rop, "max_stock": max_stock,
                         "order_multiple": catalog["case_pack"]})     # always full cases


def simulate(first_day, last_day, catalog, state, price, rop, max_stock,
             order_multiple, demand_mult, can_order, rng):
    """Simulate the store one day at a time between two dates (inclusive).

    Each day, for every product:
      morning  - deliveries that were ordered lead_time days ago arrive
      daytime  - customers want a random number of units (Poisson draw around
                 the product's average for that month and weekday); we can only
                 sell what is on the shelf
      evening  - if stock + units already on order <= reorder point, order
                 enough to get back to max stock, rounded up to the order
                 multiple (a full case, or single units)
    """
    season = np.array([SEASONALITY[s] for s in catalog["season"]])        # products x 12 months
    lead = catalog["lead_time_days"].to_numpy()
    base = catalog["base_rate"].to_numpy()
    # Day index (counted from SIM_ORIGIN) each product starts fading; never = far future.
    fade_t = catalog["fade_start"].fillna(10_000).to_numpy() + WARMUP_DAYS
    skus = catalog["sku_id"].to_numpy()
    on_hand, pipeline = state["on_hand"], state["pipeline"]
    sales, inventory = [], []

    day = first_day
    while day <= last_day:
        t = (day - SIM_ORIGIN).days
        received = pipeline[t].copy()
        on_hand += received

        fading = np.clip((t - fade_t) / FADE_DAYS, 0, 1)                 # 0 = not yet, 1 = fully faded
        fade_mult = 1 - fading * (1 - FADE_FLOOR)
        expected = base * season[:, day.month - 1] * DAY_OF_WEEK[day.weekday()] * demand_mult * fade_mult
        wanted = rng.poisson(expected)
        sold = np.minimum(wanted, on_hand)
        on_hand -= sold

        on_order = pipeline[t + 1:].sum(axis=0)
        position = on_hand + on_order
        qty = np.ceil(np.maximum(max_stock - position, 0) / order_multiple) * order_multiple
        order = can_order & (position <= rop) & (qty > 0)
        for j in np.flatnonzero(order):
            pipeline[t + lead[j], j] += qty[j]

        for j in np.flatnonzero(sold):
            sales.append((day, skus[j], int(sold[j]), round(sold[j] * price[j], 2)))
        inventory.extend(zip([day] * len(skus), skus, received.astype(int).tolist(), on_hand.astype(int).tolist()))
        day += timedelta(days=1)

    return (pd.DataFrame(sales, columns=["sale_date", "sku_id", "units_sold", "net_sales"]),
            pd.DataFrame(inventory, columns=["snapshot_date", "sku_id", "units_received", "on_hand_units"]))


def run_sql_file(con, filename):
    return con.execute((SQL_DIR / filename).read_text()).df()


def insert(con, table, df):
    con.register("staging_df", df)
    con.execute(f"INSERT INTO {table} SELECT * FROM staging_df")
    con.unregister("staging_df")


def main():
    rng = np.random.default_rng(SEED)
    DB_PATH.parent.mkdir(exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute((SQL_DIR / "00_schema.sql").read_text())

    # --- 1. Catalog and the old ordering rules -----------------------------
    catalog = build_catalog(rng)
    old_settings = old_reorder_settings(catalog, rng)
    products = catalog.drop(columns=["base_rate", "season", "faded", "fade_start"]).assign(is_active=True, discontinued_date=pd.NaT)
    insert(con, "products", products)
    insert(con, "reorder_settings", old_settings)

    n = len(catalog)
    total_days = (END - SIM_ORIGIN).days + 1
    state = {"on_hand": old_settings["max_stock"].to_numpy(dtype=float).copy(),
             "pipeline": np.zeros((total_days + 30, n))}
    price = catalog["regular_price"].to_numpy(dtype=float).copy()
    rop = old_settings["reorder_point"].to_numpy(dtype=float).copy()
    max_stock = old_settings["max_stock"].to_numpy(dtype=float).copy()
    order_multiple = old_settings["order_multiple"].to_numpy(dtype=float).copy()
    demand_mult = np.ones(n)
    can_order = np.ones(n, dtype=bool)

    # --- 2. Jan-Jun under the old habits ------------------------------------
    # Warm-up: run the old habits for two years first and throw the results
    # away, so Jan 1 looks like a store that has been run this way for years.
    # Any dead stock on Jan 1 was created by the old habits themselves.
    simulate(SIM_ORIGIN, START - timedelta(days=1), catalog, state,
             price, rop, max_stock, order_multiple, demand_mult, can_order, rng)

    sales, inventory = simulate(START, CHANGE_DATE - timedelta(days=1), catalog, state,
                                price, rop, max_stock, order_multiple, demand_mult, can_order, rng)
    insert(con, "daily_sales", sales)
    insert(con, "daily_inventory", inventory)

    # --- 3. July 1: run the analysis queries and act on them ---------------
    idx = {sku: j for j, sku in enumerate(catalog["sku_id"])}
    slow_movers = run_sql_file(con, "01_slow_movers.sql")
    reorder = run_sql_file(con, "04_reorder_points.sql")
    cut_list = run_sql_file(con, "05_low_margin_per_shelf.sql")
    price_review = run_sql_file(con, "06_price_review.sql")
    new_settings, price_log = [], []

    # a) Cut list (Q4): stop reordering, clear remaining stock at cost.
    cut_ids = set(cut_list["sku_id"])
    for sku in cut_ids:
        j = idx[sku]
        can_order[j] = False
        new_price = float(catalog.at[j, "unit_cost"])
        price_log.append((sku, CHANGE_DATE, price[j], new_price, "Clearance - discontinued"))
        price[j] = new_price
        demand_mult[j] *= CLEARANCE_LIFT
        new_settings.append((sku, CHANGE_DATE, 0, 0, int(order_multiple[j])))

    # b) Top sellers (Q3): switch to the formula-based reorder points.
    for row in reorder.itertuples():
        j = idx[row.sku_id]
        rop[j], max_stock[j] = row.recommended_reorder_point, row.recommended_max_stock
        new_settings.append((row.sku_id, CHANGE_DATE, int(rop[j]), int(max_stock[j]), int(order_multiple[j])))

    # c) Slow movers (Q1) not already handled above: order only when nearly
    #    out, and only about a month of supply. The wholesaler sells "broken
    #    cases" (single units) of slow items; DSD route reps only deliver full
    #    cases, so for DSD items we can only lower the par level.
    handled = cut_ids | set(reorder["sku_id"])
    for row in slow_movers.itertuples():
        if row.sku_id in handled:
            continue
        j = idx[row.sku_id]
        daily = row.units_sold / 181
        rop[j] = max(1, math.ceil(daily * catalog.at[j, "lead_time_days"]))
        max_stock[j] = max(rop[j] + 1, math.ceil(daily * 30))
        if "DSD" not in catalog.at[j, "vendor"]:
            order_multiple[j] = 1
        new_settings.append((row.sku_id, CHANGE_DATE, int(rop[j]), int(max_stock[j]), int(order_multiple[j])))

    # d) Price review (bonus query): move under-priced items up to their
    #    category's typical margin. Customers buy a little less at the higher price.
    for row in price_review.itertuples():
        if row.sku_id in cut_ids:
            continue
        j = idx[row.sku_id]
        new_price = round(float(row.suggested_price), 2)
        price_log.append((row.sku_id, CHANGE_DATE, price[j], new_price, "Price review - below category margin"))
        demand_mult[j] *= (new_price / price[j]) ** PRICE_ELASTICITY
        price[j] = new_price

    insert(con, "reorder_settings", pd.DataFrame(new_settings, columns=["sku_id", "effective_date", "reorder_point", "max_stock", "order_multiple"]))
    insert(con, "price_changes", pd.DataFrame(price_log, columns=["sku_id", "effective_date", "old_price", "new_price", "reason"]))

    # --- 4. Jul-Dec under the new rules -------------------------------------
    sales, inventory = simulate(CHANGE_DATE, END, catalog, state,
                                price, rop, max_stock, order_multiple, demand_mult, can_order, rng)
    insert(con, "daily_sales", sales)
    insert(con, "daily_inventory", inventory)

    cut_sql = ", ".join(f"'{s}'" for s in sorted(cut_ids))
    con.execute(f"""UPDATE products
                    SET is_active = FALSE, discontinued_date = DATE '{CHANGE_DATE}'
                    WHERE sku_id IN ({cut_sql})""")

    # --- Summary -------------------------------------------------------------
    for table in ["products", "daily_sales", "daily_inventory", "reorder_settings", "price_changes"]:
        print(f"{table:<18} {con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:>7,} rows")
    print(f"\nJuly 1 decisions: {len(cut_ids)} items cut, {len(reorder)} reorder points reset, "
          f"{len(set(slow_movers['sku_id']) - handled)} slow movers right-sized, "
          f"{len([p for p in price_log if p[4].startswith('Price')])} prices raised")
    con.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
