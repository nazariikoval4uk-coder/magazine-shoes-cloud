"""Спільні хелпери форматування таблиць: назви місяців та теплова розмальовка колонок."""
import pandas as pd

MONTH_NAMES_UK = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]


def format_month_label(month_str: str) -> str:
    """'2026-07' -> 'Липень 2026'."""
    try:
        year, month = month_str.split("-")
        return f"{MONTH_NAMES_UK[int(month) - 1]} {year}"
    except (ValueError, AttributeError, IndexError):
        return month_str


def heat_colors(series: pd.Series, alpha: float = 0.22) -> list:
    """Колір фону за позицією значення в діапазоні колонки: червоний (мін) -> зелений (макс)."""
    low_rgb = (255, 92, 92)
    high_rgb = (34, 211, 160)
    values = pd.to_numeric(series, errors="coerce")
    vmin, vmax = values.min(), values.max()

    colors = []
    for v in values:
        if pd.isna(v) or pd.isna(vmin) or pd.isna(vmax) or vmax == vmin:
            colors.append("transparent")
            continue
        t = (v - vmin) / (vmax - vmin)
        r = round(low_rgb[0] + (high_rgb[0] - low_rgb[0]) * t)
        g = round(low_rgb[1] + (high_rgb[1] - low_rgb[1]) * t)
        b = round(low_rgb[2] + (high_rgb[2] - low_rgb[2]) * t)
        colors.append(f"rgba({r},{g},{b},{alpha})")
    return colors
