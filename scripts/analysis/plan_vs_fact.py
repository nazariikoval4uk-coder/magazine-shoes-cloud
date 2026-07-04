"""Порівняння місячного факту прибутку (з orders_master) з планом (data/manual/plan.csv)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders, load_plan  # noqa: E402
from scripts.analysis.shop_summary import shop_monthly_summary  # noqa: E402


def plan_vs_fact(orders: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    fact = shop_monthly_summary(orders)[["shop", "month", "profit"]]
    fact = fact.rename(columns={"profit": "fact_profit"})

    merged = pd.merge(plan, fact, on=["shop", "month"], how="outer")
    merged["fact_profit"] = merged["fact_profit"].fillna(0)
    merged["planned_profit"] = merged["planned_profit"].fillna(0)

    merged["variance"] = merged["fact_profit"] - merged["planned_profit"]
    merged["completion_pct"] = (
        merged["fact_profit"] / merged["planned_profit"].replace(0, float("nan")) * 100
    ).round(1)

    return merged.sort_values(["month", "shop"])


def monthly_totals(merged: pd.DataFrame) -> pd.DataFrame:
    totals = merged.groupby("month").agg(
        planned_profit=("planned_profit", "sum"),
        fact_profit=("fact_profit", "sum"),
    ).reset_index()
    totals["variance"] = totals["fact_profit"] - totals["planned_profit"]
    totals["completion_pct"] = (
        totals["fact_profit"] / totals["planned_profit"].replace(0, float("nan")) * 100
    ).round(1)
    return totals.sort_values("month", ascending=False)


def main():
    orders = load_orders()
    plan = load_plan()
    result = plan_vs_fact(orders, plan)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
