"""Зведена по постачальниках товару (поле "Постачальник"): маржа, викуп %, обсяг."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402


def supplier_summary(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)
    orders["supplier"] = orders["supplier"].fillna("Невідомо")

    grouped = orders.groupby("supplier")
    summary = grouped.agg(
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
        total_profit=("success_margin", "sum"),
    ).reset_index()

    decided = (summary["orders_success"] + summary["orders_refused"]).astype(float)
    summary["buyout_rate"] = (summary["orders_success"] / decided.replace(0, float("nan")) * 100).round(1)
    summary["avg_profit_per_sale"] = (
        summary["total_profit"] / summary["orders_success"].astype(float).replace(0, float("nan"))
    ).round(0)

    return summary.sort_values("total_profit", ascending=False)


def main():
    orders = load_orders()
    summary = supplier_summary(orders)

    print("=== Топ-15 постачальників за прибутком ===")
    print(summary.head(15).to_string(index=False))
    print()
    print("=== Найгірший викуп % (мінімум 10 замовлень) ===")
    reliable = summary[summary["orders_total"] >= 10].sort_values("buyout_rate")
    print(reliable.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
