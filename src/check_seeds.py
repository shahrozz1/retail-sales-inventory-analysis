"""
check_seeds.py - how much do the results depend on luck?

The simulation is random, so one run could be unusually good or bad by
chance. This script regenerates the store 20 times with different random
seeds, measures the before/after change each time, and prints the range
and median. The seed used in generate_data.py is the run closest to the
median, so the case study shows a typical result, not a lucky one.

Run:  python src/check_seeds.py      (takes about a minute)
"""

import contextlib
import io
from pathlib import Path

import duckdb
import pandas as pd

import generate_data

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "sql" / "08_monthly_kpis.sql").read_text()
TEMP_DB = ROOT / "data" / "_seed_check.duckdb"


def before_after(db_path):
    """Percent change from Before (Jan-Jun) to After (Jul-Dec) for the headline KPIs."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        kpis = con.execute(SQL).df()
    halves = kpis.groupby("period").agg(
        revenue=("revenue", "sum"),
        gross_profit=("gross_profit", "sum"),
        dead_stock=("dead_stock_value", "mean"),
        stockout_days=("stockout_days", "sum"),
    )
    halves["margin"] = halves["gross_profit"] / halves["revenue"]
    change = (halves.loc["After"] / halves.loc["Before"] - 1) * 100
    return {
        "gross_margin_before_pct": round(100 * halves.loc["Before", "margin"], 1),
        "gross_margin_after_pct": round(100 * halves.loc["After", "margin"], 1),
        "margin_change_pct": round(change["margin"], 1),
        "dead_stock_change_pct": round(change["dead_stock"], 1),
        "stockout_change_pct": round(change["stockout_days"], 1),
    }


def main():
    generate_data.DB_PATH = TEMP_DB
    rows = []
    for seed in range(1, 21):
        generate_data.SEED = seed
        with contextlib.redirect_stdout(io.StringIO()):     # silence the generator's printout
            generate_data.main()
        rows.append({"seed": seed, **before_after(TEMP_DB)})
    TEMP_DB.unlink()

    runs = pd.DataFrame(rows)
    print(runs.to_string(index=False))
    print("\nMedian across 20 runs:")
    print(runs.drop(columns="seed").median().round(1).to_string())
    out = ROOT / "outputs" / "seed_check.csv"
    out.parent.mkdir(exist_ok=True)
    runs.to_csv(out, index=False)
    print(f"\nSaved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
