"""
RFM-сегментація клієнтів за телефоном + Heat Score.

Recency/Frequency/Monetary рахуються лише по УСПІШНИХ замовленнях (outcome == success) —
відмови й замовлення в процесі не вважаються покупкою.

Сегменти (лінійка життєвого циклу за давністю останньої покупки):
- без покупок: жодного успішного замовлення (тільки відмови/в процесі)
- новий:       рівно 1 успішна покупка
- активний:    остання покупка <= RECENT_DAYS днів тому
- заснувший:   остання покупка <= FADING_DAYS днів тому
- холодний:    остання покупка <= COLD_DAYS днів тому
- втрачений:   довше за COLD_DAYS

VIP — окремий прапорець (не сегмент): >=VIP_ORDERS успішних покупок, незалежно від давності.
Це навмисно окремо від сегмента, щоб бачити "VIP, але втрачений" — найцінніших клієнтів,
які саме зараз варто реактивувати, а не ховати їх під загальним "втрачений".

Heat Score (0-100, лише автоматичні сигнали з наявних даних; ручні сигнали на кшталt
"відповів на повідомлення"/"клікнув по розсилці" не рахуємо - цих даних просто немає):
+40 остання покупка <= 30 днів, +20 більше 2 покупок, +30 більше 5 покупок,
-20 немає покупок > 90 днів, -40 немає покупок > 180 днів. Клампиться до [0, 100].
0-30 холодний, 31-70 теплий, 71-100 гарячий.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analysis.data_io import load_orders  # noqa: E402

RECENT_DAYS = 30
FADING_DAYS = 90
COLD_DAYS = 180
VIP_ORDERS = 5

# відомі бренди для простого визначення "улюбленого бренду" з назви моделі
KNOWN_BRANDS = [
    "Nike", "Asics", "New Balance", "Salomon", "Adidas", "Puma",
    "Reebok", "Converse", "Vans", "Jordan", "Skechers", "Balenciaga",
]


def extract_brand(model: str) -> str:
    if not isinstance(model, str):
        return "інше"
    model_low = model.lower()
    for brand in KNOWN_BRANDS:
        if brand.lower() in model_low:
            return brand
    return "інше"


def _segment_vectorized(clients: pd.DataFrame) -> pd.Series:
    days = clients["days_since_last_purchase"]
    conditions = [
        clients["orders_success"] == 0,
        clients["orders_success"] == 1,
        days <= RECENT_DAYS,
        days <= FADING_DAYS,
        days <= COLD_DAYS,
    ]
    choices = ["без покупок", "новий", "активний", "заснувший", "холодний"]
    return pd.Series(np.select(conditions, choices, default="втрачений"), index=clients.index)


def _heat_score_vectorized(clients: pd.DataFrame) -> pd.Series:
    days = clients["days_since_last_purchase"]
    score = pd.Series(0, index=clients.index)
    score += np.where(days <= RECENT_DAYS, 40, 0)
    score += np.where(days > FADING_DAYS, -20, 0)
    score += np.where(days > COLD_DAYS, -40, 0)
    score += np.where(clients["orders_success"] > 2, 20, 0)
    score += np.where(clients["orders_success"] > 5, 30, 0)
    return score.clip(0, 100)


def _heat_label_vectorized(heat_score: pd.Series) -> pd.Series:
    conditions = [heat_score <= 30, heat_score <= 70]
    choices = ["холодний", "теплий"]
    return pd.Series(np.select(conditions, choices, default="гарячий"), index=heat_score.index)


def client_segmentation(orders: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    as_of = as_of or pd.Timestamp.now()

    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)
    orders["client_name"] = (
        orders["first_name"].fillna("") + " " + orders["last_name"].fillna("")
    ).str.strip()
    orders["brand"] = orders["model"].apply(extract_brand)
    orders["success_brand"] = orders["brand"].where(orders["outcome"] == "success")
    # булеві колонки замість лямбд у .agg() - вбудовані ("sum") агрегації рахуються
    # у векторизованому Cython-коді pandas, а не Python-функцією на кожну групу.
    orders["is_success"] = orders["outcome"] == "success"
    orders["is_refused"] = orders["outcome"] == "refused"

    grouped = orders.groupby("phone")
    clients = grouped.agg(
        client_name=("client_name", "first"),
        orders_total=("order_key", "count"),
        orders_success=("is_success", "sum"),
        orders_refused=("is_refused", "sum"),
        ltv=("success_margin", "sum"),
        first_order=("date", "min"),
        last_order=("date", "max"),
    ).reset_index()

    # давність/сума рахуємо тільки по успішних покупках
    success_dates = (
        orders[orders["outcome"] == "success"].groupby("phone")["date"].max()
    )
    clients = clients.merge(
        success_dates.rename("last_purchase"), on="phone", how="left",
    )
    clients["days_since_last_purchase"] = (as_of - clients["last_purchase"]).dt.days

    # улюблений бренд: рахуємо частоти (векторизовано), потім idxmax на групу (теж векторизовано)
    brand_counts = (
        orders.dropna(subset=["success_brand"])
        .groupby(["phone", "success_brand"])
        .size()
        .reset_index(name="n")
    )
    if len(brand_counts):
        top_idx = brand_counts.groupby("phone")["n"].idxmax()
        favorite_brand = brand_counts.loc[top_idx].set_index("phone")["success_brand"]
    else:
        favorite_brand = pd.Series(dtype=str)
    clients = clients.merge(
        favorite_brand.rename("favorite_brand"), on="phone", how="left",
    )
    clients["favorite_brand"] = clients["favorite_brand"].fillna("—")

    clients["segment"] = _segment_vectorized(clients)
    clients["is_vip"] = clients["orders_success"] >= VIP_ORDERS
    clients["risk"] = (
        (clients["orders_success"] >= 2)
        & clients["segment"].isin(["заснувший", "холодний", "втрачений"])
    )
    clients["heat_score"] = _heat_score_vectorized(clients)
    clients["heat_label"] = _heat_label_vectorized(clients["heat_score"])

    return clients.sort_values("ltv", ascending=False)


def main():
    orders = load_orders()
    clients = client_segmentation(orders)

    print("Розподіл по сегментах:")
    print(clients["segment"].value_counts().to_string())
    print()
    print(f"VIP клієнтів: {int(clients['is_vip'].sum())}")
    print(f"Клієнтів у ризику відтоку: {int(clients['risk'].sum())}")
    print()
    print("Розподіл по Heat Score:")
    print(clients["heat_label"].value_counts().to_string())
    print()
    print("=== Топ-15 клієнтів за LTV ===")
    cols = ["phone", "client_name", "orders_total", "ltv", "segment", "is_vip", "heat_score", "favorite_brand"]
    print(clients[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
