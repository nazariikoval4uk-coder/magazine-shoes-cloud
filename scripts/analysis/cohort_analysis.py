"""
Когортний аналіз утримання: клієнти групуються за місяцем ПЕРШОЇ успішної покупки
(когорта), і для кожного зсуву в місяцях (0, 1, 2, ...) рахується % клієнтів
когорти, які зробили ще одну успішну покупку саме в цьому місяці.

Показує, чи "молодші" когорти (напр. з нової реклами) повертаються краще/гірше
за старіші - тобто чи варті вони грошей у довгостроці, а не тільки з першого продажу.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402

MAX_OFFSET = 12


def cohort_analysis(orders: pd.DataFrame, max_offset: int = MAX_OFFSET) -> pd.DataFrame:
    success = orders[orders["outcome"] == "success"][["phone", "date"]].copy()
    success["month"] = success["date"].dt.to_period("M")

    first_purchase = success.groupby("phone")["month"].min().rename("cohort_month")
    success = success.merge(first_purchase, on="phone")
    success["offset"] = (success["month"] - success["cohort_month"]).apply(lambda o: o.n)

    cohort_sizes = first_purchase.value_counts().rename("cohort_size")

    retention = (
        success[success["offset"].between(0, max_offset)]
        .groupby(["cohort_month", "offset"])["phone"]
        .nunique()
        .reset_index(name="returning_clients")
    )
    retention = retention.merge(cohort_sizes, left_on="cohort_month", right_index=True)
    retention["retention_pct"] = (
        retention["returning_clients"] / retention["cohort_size"] * 100
    ).round(1)

    pivot = retention.pivot(index="cohort_month", columns="offset", values="retention_pct")
    pivot.columns = [f"m{c}" for c in pivot.columns]
    pivot.insert(0, "cohort_size", cohort_sizes)
    pivot = pivot.reset_index()
    pivot["cohort_month"] = pivot["cohort_month"].astype(str)

    return pivot.sort_values("cohort_month")


def main():
    orders = load_orders()
    cohorts = cohort_analysis(orders)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(cohorts.to_string(index=False))


if __name__ == "__main__":
    main()
