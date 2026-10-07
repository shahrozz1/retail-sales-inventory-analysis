"""
analysis.py - answers the business questions and draws the charts.

Steps:
  1. Connect to the DuckDB database built by generate_data.py.
  2. Run every query in sql/ and save each result as a CSV in outputs/.
  3. Print the headline answers.
  4. Draw three charts into images/:
       turnover_by_category.png   inventory turnover by category, before vs after
       revenue_concentration.png  Pareto curve + revenue share by product group
       before_after.png           monthly gross margin and dead stock

The SQL files are the single source of truth: this script runs them as-is
instead of re-writing the logic in pandas, so the charts always match the
queries.

Run:  python src/analysis.py
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")                      # draw straight to image files, no pop-up windows
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "store.duckdb"
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "outputs"
IMG_DIR = ROOT / "images"

# Query file -> name of the CSV its result is saved as.
QUERIES = {
    "01_slow_movers.sql":          "q1_slow_movers",
    "02_pareto_curve.sql":         "q2_pareto_curve",
    "03_pareto_summary.sql":       "q2_pareto_summary",
    "04_reorder_points.sql":       "q3_reorder_points",
    "05_low_margin_per_shelf.sql": "q4_low_margin_per_shelf",
    "06_price_review.sql":         "price_review",
    "07_turnover_by_category.sql": "turnover_by_category",
    "08_monthly_kpis.sql":         "monthly_kpis",
    "09_margin_by_action.sql":     "margin_by_action",
}

# Colors. "After" is the one highlighted color; "before" is a quiet gray, so
# the eye goes to the result. The rest are neutral inks for text and grid.
AFTER = "#2a78d6"
BEFORE = "#898781"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

SOURCE_NOTE = "Simulated data modeled on a small-town convenience store (200 products, 2025)."


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def run_all_queries(con):
    """Run every SQL file, save each result to outputs/, return them in a dict."""
    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    for filename, name in QUERIES.items():
        df = con.execute((SQL_DIR / filename).read_text()).df()
        df.to_csv(OUT_DIR / f"{name}.csv", index=False)
        results[name] = df
    return results


def before_after_summary(kpis):
    """Collapse the 12 monthly rows into one Before row and one After row.

    Margin is total gross profit / total revenue for each half, NOT the
    average of the six monthly percentages, so busy months count more.
    Dead stock and inventory are month-end snapshots, so we average them.
    """
    halves = kpis.groupby("period").agg(
        revenue=("revenue", "sum"),
        gross_profit=("gross_profit", "sum"),
        dead_stock=("dead_stock_value", "mean"),
        inventory=("inventory_value", "mean"),
        stockout_days=("stockout_days", "sum"),
    )
    halves["gross_margin_pct"] = 100 * halves["gross_profit"] / halves["revenue"]
    return halves.loc[["Before", "After"]]


def pct_change(before, after):
    return 100 * (after / before - 1)


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------
def set_style():
    """One shared look for every chart: light surface, hairline grid, no box."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": AXIS, "ytick.color": AXIS,
        "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "legend.frameon": False,
    })


def add_header_and_note(fig, title, subtitle):
    """Title + one-line takeaway at the top, data-source note at the bottom."""
    height = fig.get_figheight()                 # in inches: keeps spacing equal on every chart
    fig.text(0.015, 1 - 0.18 / height, title, fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.015, 1 - 0.52 / height, subtitle, fontsize=10.5, color=INK_2, va="top")
    fig.text(0.015, 0.015, SOURCE_NOTE, fontsize=8, color=BEFORE, va="bottom")


def save(fig, filename):
    IMG_DIR.mkdir(exist_ok=True)
    fig.savefig(IMG_DIR / filename, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 1: inventory turnover by category
# ---------------------------------------------------------------------------
def chart_turnover(turnover):
    # Sort categories by their After turnover so the chart reads top-down.
    after_rows = turnover[turnover["period"].str.startswith("After")]
    order = after_rows.sort_values("annual_turnover", ascending=False)["category"]

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.subplots_adjust(left=0.20, right=0.95, top=0.84, bottom=0.10)
    sns.barplot(
        data=turnover, y="category", x="annual_turnover", order=order,
        hue="period", hue_order=["Before (Jan-Jun)", "After (Jul-Dec)"],
        palette=[BEFORE, AFTER], width=0.75, gap=0.1, ax=ax,
    )
    # Label only the After bars: the result is the number that matters.
    ax.bar_label(ax.containers[1], fmt="%.0f", padding=3, fontsize=9, color=INK_2)
    ax.set_xlabel("Inventory turns per year (annualized)")
    ax.set_ylabel("")
    ax.grid(axis="y", visible=False)
    ax.legend(title="", loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)

    total = turnover.groupby("period")[["cost_of_goods_sold", "avg_inventory_value"]].sum()
    turns = (total["cost_of_goods_sold"] / total["avg_inventory_value"] * 2).round(0)
    add_header_and_note(
        fig, "Inventory turnover by category",
        f"How many times a year shelf stock sells through. Store-wide: "
        f"{turns['Before (Jan-Jun)']:.0f} turns before, {turns['After (Jul-Dec)']:.0f} after.",
    )
    save(fig, "turnover_by_category.png")


# ---------------------------------------------------------------------------
# Chart 2: revenue concentration (Pareto)
# ---------------------------------------------------------------------------
def chart_pareto(curve, summary):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw={"width_ratios": [1.35, 1]})
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.14, wspace=0.28)

    # Left: the cumulative curve. Start at (0, 0) so the line begins at the origin.
    x = [0] + curve["cumulative_pct_of_skus"].tolist()
    y = [0] + curve["cumulative_pct_of_revenue"].tolist()
    ax1.plot(x, y, color=AFTER, linewidth=2)
    ax1.fill_between(x, y, color=AFTER, alpha=0.08)
    ax1.plot([0, 100], [0, 100], color=AXIS, linewidth=1)
    ax1.text(62, 55, "If every product sold equally", color=BEFORE, fontsize=8.5, rotation=33)

    top20 = curve.loc[curve["cumulative_pct_of_skus"] == 20, "cumulative_pct_of_revenue"].iloc[0]
    hit80 = curve[curve["cumulative_pct_of_revenue"] >= 80].iloc[0]
    for px, py, text, offset in [
        (20, top20, f"Top 20% of products\n= {top20:.0f}% of revenue", (30, 50)),
        (hit80["cumulative_pct_of_skus"], hit80["cumulative_pct_of_revenue"],
         f"{hit80['cumulative_pct_of_skus']:.0f}% of products\n= 80% of revenue", (48, 72)),
    ]:
        ax1.scatter([px], [py], s=45, color=AFTER, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax1.annotate(text, xy=(px, py), xytext=offset, fontsize=9.5, color=INK,
                     arrowprops=dict(arrowstyle="-", color=BEFORE, linewidth=0.8))
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 102)
    ax1.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax1.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax1.set_xlabel("Share of products, best sellers first")
    ax1.set_ylabel("Cumulative share of revenue")
    ax1.set_title("Cumulative revenue curve")

    # Right: the same story in five bars.
    labels = ["Top 20%", "21-40%", "41-60%", "61-80%", "Bottom 20%"]
    bars = ax2.bar(labels, summary["pct_of_revenue"], color=AFTER, width=0.6)
    ax2.bar_label(bars, fmt="%.0f%%", padding=3, fontsize=9.5, color=INK_2)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax2.set_ylim(0, summary["pct_of_revenue"].max() * 1.15)
    ax2.grid(axis="x", visible=False)
    ax2.set_xlabel("Product group (by revenue rank)")
    ax2.set_title("Share of revenue by product group")

    add_header_and_note(
        fig, "Revenue is concentrated in a few products",
        f"Jan-Jun 2025. The top 40 of 200 products bring in {top20:.0f}% of revenue; "
        f"the bottom 40 bring in {summary['pct_of_revenue'].iloc[-1]:.0f}%.",
    )
    save(fig, "revenue_concentration.png")


# ---------------------------------------------------------------------------
# Chart 3: before vs after
# ---------------------------------------------------------------------------
def chart_before_after(kpis, halves):
    kpis = kpis.assign(month=pd.to_datetime(kpis["month"]))
    before = kpis[kpis["period"] == "Before"]
    after = kpis[kpis["period"] == "After"]
    change_line = pd.Timestamp("2025-06-16")       # halfway between the Jun and Jul points

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.72, bottom=0.12, wspace=0.25)

    panels = [
        (ax1, "gross_margin_pct", "gross_margin_pct", "Gross margin %",
         lambda v: f"{v:.1f}%", mtick.FuncFormatter(lambda v, _: f"{v:.0f}%")),
        (ax2, "dead_stock_value", "dead_stock", "Dead stock (month-end, at cost)",
         # "\\$" = a literal dollar sign; matplotlib treats a bare $...$ pair as a math formula
         lambda v: f"\\${v:,.0f}", mtick.FuncFormatter(lambda v, _: f"${v:,.0f}")),
    ]
    for ax, column, summary_col, name, fmt, axis_fmt in panels:
        # Monthly line: gray for the old habits, blue for the new rules.
        ax.plot(before["month"], before[column], color=BEFORE, linewidth=2, marker="o", markersize=5)
        ax.plot(after["month"], after[column], color=AFTER, linewidth=2, marker="o", markersize=5)
        ax.plot([before["month"].iloc[-1], after["month"].iloc[0]],
                [before[column].iloc[-1], after[column].iloc[0]], color=AXIS, linewidth=1.5)

        # Thin horizontal line at each half's overall level (the numbers go in the title).
        b, a = halves.loc["Before", summary_col], halves.loc["After", summary_col]
        ax.hlines(b, before["month"].iloc[0], before["month"].iloc[-1], color=BEFORE, linewidth=1, alpha=0.6)
        ax.hlines(a, after["month"].iloc[0], after["month"].iloc[-1], color=AFTER, linewidth=1, alpha=0.6)

        ax.axvline(change_line, color=AXIS, linewidth=1)
        ax.text(change_line, 1.0, " changes made Jul 1", transform=ax.get_xaxis_transform(),
                color=INK_2, fontsize=8.5, va="bottom")
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.yaxis.set_major_formatter(axis_fmt)
        ax.grid(axis="x", visible=False)
        ax.set_title(f"{name}\nJan-Jun avg {fmt(b)}  \u2192  Jul-Dec avg {fmt(a)}  ({pct_change(b, a):+.0f}%)",
                     pad=18, fontsize=10.5, linespacing=1.6)

    ax1.set_ylim(kpis["gross_margin_pct"].min() - 1, kpis["gross_margin_pct"].max() + 1)
    ax2.set_ylim(0, kpis["dead_stock_value"].max() * 1.2)

    add_header_and_note(
        fig, "Before vs after the July 1 changes",
        "Gray = old ordering habits (Jan-Jun). Blue = rules built from the SQL analysis (Jul-Dec). "
        "Thin lines = each half's average.",
    )
    save(fig, "before_after.png")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def print_summary(r, halves):
    def show(title, df, columns, rows=5):
        print(f"\n{title}")
        print(df[columns].head(rows).to_string(index=False))

    show("Q1. Slowest sellers tying up the most cash (Jan-Jun):", r["q1_slow_movers"],
         ["product_name", "sell_through_pct", "cash_tied_up", "days_of_supply"])
    print(f"   -> {len(r['q1_slow_movers'])} items, ${r['q1_slow_movers']['cash_tied_up'].sum():,.0f} tied up in total")

    show("Q2. Revenue by product group (Jan-Jun):", r["q2_pareto_summary"],
         ["product_group", "products", "pct_of_revenue"])

    q3 = r["q3_reorder_points"]
    show("Q3. Reorder points for top sellers (most stockouts first):", q3,
         ["product_name", "stockout_days", "current_reorder_point", "recommended_reorder_point", "action"])
    print(f"   -> {(q3['action'].str.startswith('Raise')).sum()} of {len(q3)} top sellers needed a higher "
          f"reorder point; they were out of stock {q3['stockout_days'].sum():.0f} item-days in six months")

    show("Q4. Lowest gross profit per shelf facing (cut candidates):", r["q4_low_margin_per_shelf"],
         ["product_name", "shelf_facings", "gp_per_facing_per_week", "category_avg_gp_per_facing"])

    print(f"\nPrice review: {len(r['price_review'])} items priced 3+ points below their category's median margin")

    show("Margin by what happened to each product (Unchanged = control group):", r["margin_by_action"],
         ["action_group", "products", "margin_before_pct", "margin_after_pct"])

    print("\nBefore vs after (Jan-Jun vs Jul-Dec):")
    for label, col, fmt in [("Gross margin", "gross_margin_pct", "{:.1f}%"),
                            ("Avg dead stock", "dead_stock", "${:,.0f}"),
                            ("Avg inventory value", "inventory", "${:,.0f}"),
                            ("Stockout days", "stockout_days", "{:,.0f}")]:
        b, a = halves.loc["Before", col], halves.loc["After", col]
        print(f"  {label:<20} {fmt.format(b):>9} -> {fmt.format(a):>9}   ({pct_change(b, a):+.1f}%)")


def main():
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        results = run_all_queries(con)

    halves = before_after_summary(results["monthly_kpis"])
    print_summary(results, halves)

    set_style()
    chart_turnover(results["turnover_by_category"])
    chart_pareto(results["q2_pareto_curve"], results["q2_pareto_summary"])
    chart_before_after(results["monthly_kpis"], halves)
    print(f"\nCSVs saved to {OUT_DIR.relative_to(ROOT)}/, charts saved to {IMG_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
