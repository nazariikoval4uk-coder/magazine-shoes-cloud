"""
Сезонність: продажі й прибуток по календарних місяцях (січень..грудень),
агреговано по всіх роках разом — щоб бачити, які місяці традиційно сильніші/слабші.

⚠️ Дані охоплюють неповні 2-3 роки (з 2023-11) — чим менше років на календарний
місяць, тим менш надійний висновок. Це орієнтир, не точна статистика.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402
from scripts.analysis.table_format import heat_colors  # noqa: E402

MONTH_NAMES = [
    "січень", "лютий", "березень", "квітень", "травень", "червень",
    "липень", "серпень", "вересень", "жовтень", "листопад", "грудень",
]


def seasonality_summary(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)
    orders["calendar_month"] = orders["date"].dt.month
    orders["year"] = orders["date"].dt.year

    grouped = orders.groupby("calendar_month")
    summary = grouped.agg(
        years_covered=("year", "nunique"),
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
        total_profit=("success_margin", "sum"),
    ).reset_index()

    decided = (summary["orders_success"] + summary["orders_refused"]).astype(float)
    summary["buyout_rate"] = (summary["orders_success"] / decided.replace(0, float("nan")) * 100).round(1)
    summary["avg_profit_per_year"] = (summary["total_profit"] / summary["years_covered"]).round(0)
    summary["month_name"] = summary["calendar_month"].apply(lambda m: MONTH_NAMES[m - 1])
    summary["buyout_rate_bg"] = heat_colors(summary["buyout_rate"])
    summary["avg_profit_bg"] = heat_colors(summary["avg_profit_per_year"])

    return summary.sort_values("calendar_month")


def top_products_by_month(orders: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    orders = orders.copy()
    orders = orders[orders["outcome"] == "success"].copy()
    orders["calendar_month"] = orders["date"].dt.month

    grouped = orders.groupby(["calendar_month", "model"])["margin"].sum().reset_index()
    grouped = grouped.rename(columns={"margin": "total_profit"})
    grouped["month_name"] = grouped["calendar_month"].apply(lambda m: MONTH_NAMES[m - 1])

    top = (
        grouped.sort_values(["calendar_month", "total_profit"], ascending=[True, False])
        .groupby("calendar_month")
        .head(top_n)
    )
    return top


def main():
    orders = load_orders()
    summary = seasonality_summary(orders)
    print("=== Сезонність по календарних місяцях ===")
    cols = ["month_name", "years_covered", "orders_total", "buyout_rate", "avg_profit_per_year"]
    print(summary[cols].to_string(index=False))
    print()
    print("=== Топ-3 товари по місяцях ===")
    top = top_products_by_month(orders)
    print(top[["month_name", "model", "total_profit"]].to_string(index=False))


if __name__ == "__main__":
    main()
