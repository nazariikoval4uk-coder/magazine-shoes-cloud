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


def _segment(row: pd.Series) -> str:
    if row["orders_success"] == 0:
        return "без покупок"
    if row["orders_success"] == 1:
        return "новий"
    days = row["days_since_last_purchase"]
    if days <= RECENT_DAYS:
        return "активний"
    if days <= FADING_DAYS:
        return "заснувший"
    if days <= COLD_DAYS:
        return "холодний"
    return "втрачений"


def _heat_score(row: pd.Series) -> int:
    score = 0
    days = row["days_since_last_purchase"]
    if pd.notna(days):
        if days <= RECENT_DAYS:
            score += 40
        if days > FADING_DAYS:
            score -= 20
        if days > COLD_DAYS:
            score -= 40
    if row["orders_success"] > 2:
        score += 20
    if row["orders_success"] > 5:
        score += 30
    return max(0, min(100, score))


def _heat_label(score: int) -> str:
    if score <= 30:
        return "холодний"
    if score <= 70:
        return "теплий"
    return "гарячий"


def client_segmentation(orders: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    as_of = as_of or pd.Timestamp.now()

    orders = orders.copy()
    orders["success_margin"] = orders["margin"].where(orders["outcome"] == "success", 0)
    orders["client_name"] = (
        orders["first_name"].fillna("") + " " + orders["last_name"].fillna("")
    ).str.strip()
    orders["brand"] = orders["model"].apply(extract_brand)
    orders["success_brand"] = orders["brand"].where(orders["outcome"] == "success")

    grouped = orders.groupby("phone")
    clients = grouped.agg(
        client_name=("client_name", "first"),
        orders_total=("order_key", "count"),
        orders_success=("outcome", lambda s: (s == "success").sum()),
        orders_refused=("outcome", lambda s: (s == "refused").sum()),
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

    favorite_brand = (
        orders.dropna(subset=["success_brand"])
        .groupby("phone")["success_brand"]
        .agg(lambda s: s.value_counts().idxmax() if len(s) else "—")
    )
    clients = clients.merge(
        favorite_brand.rename("favorite_brand"), on="phone", how="left",
    )
    clients["favorite_brand"] = clients["favorite_brand"].fillna("—")

    clients["segment"] = clients.apply(_segment, axis=1)
    clients["is_vip"] = clients["orders_success"] >= VIP_ORDERS
    clients["risk"] = (
        (clients["orders_success"] >= 2)
        & clients["segment"].isin(["заснувший", "холодний", "втрачений"])
    )
    clients["heat_score"] = clients.apply(_heat_score, axis=1)
    clients["heat_label"] = clients["heat_score"].apply(_heat_label)

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
