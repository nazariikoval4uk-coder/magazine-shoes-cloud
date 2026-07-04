"""Рейтинг товарів (моделей): популярність, маржинальність, викуп %."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402


def product_ranking(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)

    grouped = orders.groupby("model")
    ranking = grouped.agg(
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
        total_profit=("success_margin", "sum"),
    ).reset_index()

    decided = (ranking["orders_success"] + ranking["orders_refused"]).astype(float)
    ranking["buyout_rate"] = (ranking["orders_success"] / decided.replace(0, float("nan")) * 100).round(1)
    ranking["avg_profit_per_sale"] = (
        ranking["total_profit"] / ranking["orders_success"].astype(float).replace(0, float("nan"))
    ).round(0)

    return ranking.sort_values("total_profit", ascending=False)


def main():
    orders = load_orders()
    ranking = product_ranking(orders)

    print("=== Топ-15 за прибутком ===")
    print(ranking.head(15).to_string(index=False))
    print()
    print("=== Найгірші 15 за прибутком (серед тих, що мали продажі чи відмови) ===")
    decided = ranking[(ranking["orders_success"] + ranking["orders_refused"]) > 0]
    print(decided.sort_values("total_profit").head(15).to_string(index=False))


if __name__ == "__main__":
    main()
