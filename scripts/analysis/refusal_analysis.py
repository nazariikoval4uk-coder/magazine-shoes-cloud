"""Причини відмов: злиття замовлень-відмов з ручно внесеними причинами + розподіл."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders, load_refusal_reasons  # noqa: E402

REASON_OPTIONS = [
    "Не підійшов розмір",
    "Передумав",
    "Погана якість",
    "Не прийшов",
    "Інше",
]

REASON_COLORS = {
    "Не підійшов розмір": "#60a5fa",
    "Передумав": "#f472b6",
    "Погана якість": "#ff5c5c",
    "Не прийшов": "#f59e0b",
    "Інше": "#7c7e9a",
    "без причини": "#3a3c54",
}


def refused_orders_with_reasons(orders: pd.DataFrame) -> pd.DataFrame:
    refused = orders[orders["outcome"] == "refused"].copy()
    reasons = load_refusal_reasons()[["order_key", "reason", "comment"]]
    reasons = reasons.rename(columns={"comment": "reason_comment"})
    return refused.merge(reasons, on="order_key", how="left")


def reason_distribution(refused_with_reasons: pd.DataFrame) -> pd.DataFrame:
    total = len(refused_with_reasons)
    dist = (
        refused_with_reasons["reason"]
        .fillna("без причини")
        .value_counts()
        .reset_index()
    )
    dist.columns = ["reason", "count"]
    dist["share_pct"] = (dist["count"] / total * 100).round(1)
    return dist


def main():
    orders = load_orders()
    refused = refused_orders_with_reasons(orders)
    dist = reason_distribution(refused)
    print(f"Всього відмов: {len(refused)}")
    print(dist.to_string(index=False))


if __name__ == "__main__":
    main()
