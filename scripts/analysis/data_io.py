"""Спільне завантаження даних для всіх модулів аналітики та дашборду."""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_MANUAL = PROJECT_ROOT / "data" / "manual"


_orders_cache = {"mtime": None, "df": None}


def load_orders() -> pd.DataFrame:
    path = DATA_PROCESSED / "orders_master.csv"
    mtime = path.stat().st_mtime
    if _orders_cache["mtime"] == mtime:
        return _orders_cache["df"].copy()

    df = pd.read_csv(path, dtype={"order_key": str, "phone": str, "sku": str})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    for col in ("margin", "income_raw", "prepayment", "cost_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Колонка "Маржа" з CRM не враховує часткову передплату (вона стягується
    # окремо від накладеного платежу при отриманні). Реальний прибуток =
    # маржа з CRM + передплата. Підтверджено звіркою власника: 96/100 замовлень
    # збіглись з ручним підрахунком тільки після додавання передплати.
    df["margin_raw"] = df["margin"]
    df["margin"] = df["margin_raw"] + df["prepayment"].fillna(0)

    # При відмові "income_raw" зберігає ціну відмови зі знаком мінус.
    # Залишок = передплата (0, якщо її не було) - ціна відмови.
    is_refused = df["outcome"] == "refused"
    refusal_cost = df["income_raw"].abs()
    df["refusal_remainder"] = pd.NA
    df.loc[is_refused, "refusal_remainder"] = (
        df.loc[is_refused, "prepayment"].fillna(0) - refusal_cost[is_refused]
    )
    df["refusal_remainder"] = pd.to_numeric(df["refusal_remainder"], errors="coerce")

    _orders_cache["mtime"] = mtime
    _orders_cache["df"] = df
    return df.copy()


def load_expenses() -> pd.DataFrame:
    path = DATA_MANUAL / "expenses.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df.reset_index().rename(columns={"index": "row_id"})


def delete_expense(row_id: int) -> None:
    path = DATA_MANUAL / "expenses.csv"
    df = pd.read_csv(path)
    df = df.drop(index=row_id).reset_index(drop=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_salaries() -> pd.DataFrame:
    path = DATA_MANUAL / "salaries.csv"
    df = pd.read_csv(path, dtype={"month": str})
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def load_plan() -> pd.DataFrame:
    path = DATA_MANUAL / "plan.csv"
    df = pd.read_csv(path, dtype={"month": str})
    df["planned_profit"] = pd.to_numeric(df["planned_profit"], errors="coerce")
    return df


def set_plan(month: str, shop: str, planned_profit: float) -> None:
    path = DATA_MANUAL / "plan.csv"
    df = pd.read_csv(path, dtype={"month": str})
    match = (df["month"] == month) & (df["shop"] == shop)
    if match.any():
        df.loc[match, "planned_profit"] = planned_profit
    else:
        new_row = pd.DataFrame([{"month": month, "shop": shop, "planned_profit": planned_profit}])
        df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def append_expense(date: str, shop: str, category: str, amount: float, comment: str) -> None:
    path = DATA_MANUAL / "expenses.csv"
    df = pd.read_csv(path)
    new_row = pd.DataFrame([{
        "date": date, "shop": shop, "category": category,
        "amount": amount, "comment": comment,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_wishlist() -> pd.DataFrame:
    path = DATA_MANUAL / "wishlist.csv"
    df = pd.read_csv(path, dtype={"phone": str})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.reset_index().rename(columns={"index": "row_id"})


def append_wishlist(date: str, phone: str, client_name: str, item: str, comment: str) -> None:
    path = DATA_MANUAL / "wishlist.csv"
    df = pd.read_csv(path, dtype={"phone": str})
    new_row = pd.DataFrame([{
        "date": date, "phone": phone, "client_name": client_name,
        "item": item, "status": "очікує", "comment": comment,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def mark_wishlist_fulfilled(row_id: int) -> None:
    path = DATA_MANUAL / "wishlist.csv"
    df = pd.read_csv(path, dtype={"phone": str})
    df.loc[row_id, "status"] = "виконано"
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_client_notes() -> pd.DataFrame:
    path = DATA_MANUAL / "client_notes.csv"
    df = pd.read_csv(path, dtype={"phone": str})
    if "contact_status" not in df.columns:
        df["contact_status"] = "не писали"
    df["updated_date"] = pd.to_datetime(df["updated_date"], errors="coerce")
    return df


def set_client_note(phone: str, next_action: str, comment: str, contact_status: str) -> None:
    path = DATA_MANUAL / "client_notes.csv"
    df = pd.read_csv(path, dtype={"phone": str})
    if "contact_status" not in df.columns:
        df["contact_status"] = "не писали"
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    if phone in df["phone"].values:
        df.loc[df["phone"] == phone, ["next_action", "comment", "contact_status", "updated_date"]] = (
            next_action, comment, contact_status, today
        )
    else:
        new_row = pd.DataFrame([{
            "phone": phone, "next_action": next_action,
            "comment": comment, "contact_status": contact_status, "updated_date": today,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_refusal_reasons() -> pd.DataFrame:
    path = DATA_MANUAL / "refusal_reasons.csv"
    df = pd.read_csv(path, dtype={"order_key": str})
    df["updated_date"] = pd.to_datetime(df["updated_date"], errors="coerce")
    return df


def set_refusal_reason(order_key: str, reason: str, comment: str) -> None:
    path = DATA_MANUAL / "refusal_reasons.csv"
    df = pd.read_csv(path, dtype={"order_key": str})
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    if order_key in df["order_key"].values:
        df.loc[df["order_key"] == order_key, ["reason", "comment", "updated_date"]] = (
            reason, comment, today
        )
    else:
        new_row = pd.DataFrame([{
            "order_key": order_key, "reason": reason,
            "comment": comment, "updated_date": today,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
