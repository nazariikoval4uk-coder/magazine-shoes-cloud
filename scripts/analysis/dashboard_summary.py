"""
Розрахунки для головної сторінки дашборду: період/фільтр по магазинах, KPI,
дані для графіка Chart.js, розбивка по магазинах, прості інсайти-підказки.
"""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ALL_SHOPS = ["Best", "Bunnix", "ОЛХ", "Пром", "Невідомо"]

SHOP_COLORS = {
    "Best": "#60a5fa",
    "Bunnix": "#f472b6",
    "ОЛХ": "#f59e0b",
    "Пром": "#34d399",
    "Невідомо": "#7c7e9a",
}

CHART_MAX_HEIGHT = 160  # px, як у референсі власника

KPI_COLORS = {
    "total": "#6c63ff", "success": "#22d3a0", "refused": "#ff5c5c",
    "pending": "#fbbf24", "margin": "#22d3a0", "avg_margin": "#6c63ff", "lost": "#ff5c5c",
}

MIN_DECIDED_FOR_INSIGHT = 10  # не робити висновки про викуп на малій вибірці
LOW_BUYOUT_THRESHOLD = 65.0


def resolve_period(period: str, date_from: str, date_to: str, orders: pd.DataFrame):
    today = pd.Timestamp.now().normalize()
    min_date = orders["date"].min()
    max_date = orders["date"].max()

    if period == "custom" and date_from and date_to:
        return pd.Timestamp(date_from), pd.Timestamp(date_to)
    if period == "month":
        return today.replace(day=1), today
    if period == "3m":
        return today - timedelta(days=90), today
    if period == "6m":
        return today - timedelta(days=180), today
    if period == "year":
        return today.replace(month=1, day=1), today
    # "all" або невідомо
    return min_date, max_date


def filter_orders(orders: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, shops: list[str]) -> pd.DataFrame:
    filtered = orders[(orders["date"] >= start) & (orders["date"] <= end)]
    if shops:
        filtered = filtered[filtered["shop"].isin(shops)]
    return filtered


def kpi_summary(filtered: pd.DataFrame) -> dict:
    total = len(filtered)
    success = int((filtered["outcome"] == "success").sum())
    refused = int((filtered["outcome"] == "refused").sum())
    pending = int((filtered["outcome"] == "pending").sum())

    total_margin = float(filtered.loc[filtered["outcome"] == "success", "margin"].sum())
    lost_margin_refused = float(filtered.loc[filtered["outcome"] == "refused", "margin"].sum())
    avg_margin = total_margin / success if success else 0.0
    decided = success + refused
    buyout_rate = round(success / decided * 100, 1) if decided else None
    refusal_remainder_total = float(
        filtered.loc[filtered["outcome"] == "refused", "refusal_remainder"].sum()
    )
    # реально сплачено за відмови (ціна повернення посилки, |Дохід| для refused) - справжні кошти,
    # на відміну від lost_margin_refused, яка гіпотетична (упущений прибуток)
    refusal_cost_total = float(
        filtered.loc[filtered["outcome"] == "refused", "income_raw"].abs().sum()
    )

    return {
        "total": total, "success": success, "refused": refused, "pending": pending,
        "total_margin": total_margin, "avg_margin": avg_margin,
        "lost_margin_refused": lost_margin_refused, "buyout_rate": buyout_rate,
        "refusal_remainder_total": refusal_remainder_total,
        "refusal_cost_total": refusal_cost_total,
    }


def shop_breakdown(filtered: pd.DataFrame) -> pd.DataFrame:
    grouped = filtered.groupby("shop")
    rows = grouped.apply(lambda g: pd.Series(kpi_summary(g))).reset_index()
    return rows.sort_values("total_margin", ascending=False)


def _fmt_short(value: float) -> str:
    if abs(value) >= 1000:
        return f"{round(value / 1000)}k"
    return f"{value:.0f}" if value else "0"


def monthly_chart_data(filtered: pd.DataFrame, shops: list[str]) -> dict:
    """Дані для CSS-бар-чарту (стек по магазинах на місяць), в пікселях висоти + шкала."""
    success = filtered[filtered["outcome"] == "success"]
    grouped = success.groupby(["month", "shop"])["margin"].sum().reset_index()
    months = sorted(filtered["month"].dropna().unique())

    totals_by_month = {
        m: sum(float(grouped.loc[(grouped["month"] == m) & (grouped["shop"] == s), "margin"].sum()) for s in shops)
        for m in months
    }
    max_total = max(totals_by_month.values()) if totals_by_month else 0

    columns = []
    for m in months:
        segments = []
        for shop in shops:
            value = float(grouped.loc[(grouped["month"] == m) & (grouped["shop"] == shop), "margin"].sum())
            if value <= 0:
                continue
            height_px = max(2, round(value / max_total * CHART_MAX_HEIGHT)) if max_total else 2
            segments.append({"shop": shop, "value": value, "color": SHOP_COLORS.get(shop, "#7c7e9a"), "height_px": height_px})

        total = totals_by_month[m]
        total_height_px = max(2, round(total / max_total * CHART_MAX_HEIGHT)) if max_total else 2
        columns.append({
            "month": m, "month_short": m[5:], "total": total,
            "total_label": _fmt_short(total) if total else "", "total_height_px": total_height_px, "segments": segments,
        })

    # шкала зліва: 0, 25%, 50%, 75%, 100% від максимуму місяця
    y_ticks = [_fmt_short(max_total * frac) for frac in (1, 0.75, 0.5, 0.25, 0)]

    return {"columns": columns, "y_ticks": y_ticks, "max_total": max_total}


def generate_insights(breakdown: pd.DataFrame) -> list[dict]:
    insights = []
    reliable = breakdown[breakdown["success"] + breakdown["refused"] >= MIN_DECIDED_FOR_INSIGHT]

    if len(reliable):
        worst = reliable.sort_values("buyout_rate").iloc[0]
        if worst["buyout_rate"] is not None and worst["buyout_rate"] < LOW_BUYOUT_THRESHOLD:
            insights.append({
                "type": "warn",
                "text": f"{worst['shop']} — викуп {worst['buyout_rate']:.0f}% за цей період. Перевір трафік.",
            })

    if len(breakdown):
        best = breakdown.sort_values("total_margin", ascending=False).iloc[0]
        if best["total_margin"] > 0:
            insights.append({
                "type": "success",
                "text": f"{best['shop']} — лідер періоду ({best['total_margin']:.0f} ₴). Масштабуй.",
            })

    total_lost = breakdown["lost_margin_refused"].sum()
    if total_lost:
        insights.append({
            "type": "info",
            "text": f"Упущена маржа через відмови за період: {total_lost:.0f} ₴ (гіпотетично, не реальні кошти)",
        })

    return insights
