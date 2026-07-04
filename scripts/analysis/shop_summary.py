"""Місячна зведена по магазинах: кількість замовлень, викуп %, прибуток."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402


def shop_monthly_summary(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)

    grouped = orders.groupby(["shop", "month"])
    summary = grouped.agg(
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
        orders_pending=("outcome", lambda s: (s == "pending").sum()),
        profit=("success_margin", "sum"),
    ).reset_index()

    decided = (summary["orders_success"] + summary["orders_refused"]).astype(float)
    summary["buyout_rate"] = (summary["orders_success"] / decided.replace(0, float("nan")) * 100).round(1)

    return summary.sort_values(["month", "shop"])


def overall_monthly_trend(orders: pd.DataFrame) -> pd.DataFrame:
    """Загальний тренд (всі магазини разом) по місяцях, з дельтою до попереднього місяця."""
    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)

    grouped = orders.groupby("month")
    trend = grouped.agg(
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
        orders_pending=("outcome", lambda s: (s == "pending").sum()),
        profit=("success_margin", "sum"),
    ).reset_index().sort_values("month")

    decided = (trend["orders_success"] + trend["orders_refused"]).astype(float)
    trend["buyout_rate"] = (trend["orders_success"] / decided.replace(0, float("nan")) * 100).round(1)

    trend["buyout_rate_delta"] = trend["buyout_rate"].diff().round(1)
    trend["profit_delta"] = trend["profit"].diff().round(0)

    return trend.sort_values("month", ascending=False)


def main():
    orders = load_orders()
    summary = shop_monthly_summary(orders)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
