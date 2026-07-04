"""
Інкрементальний імпорт вивантаження замовлень з CRM (.xls, повний список щоразу)
у майстер-таблицю data/processed/orders_master.csv.

Нові замовлення (за композитним ключем дата+телефон+модель+артикул) додаються,
вже наявні — оновлюються (статус ТТН, маржа тощо можуть змінитись з часом).

Використання:
    python scripts/etl/import_orders.py data/raw/2026-07-02_clients_report.xls
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW_COLUMNS = {
    "Дата": "date",
    "Клієнт": "client_nickname",
    "Прізвище": "last_name",
    "Ім'я": "first_name",
    "Телефон": "phone",
    "Постачальник": "supplier",
    "Часткова передплата": "prepayment",
    "Дроп ціна": "cost_price",
    "Дохід": "income_raw",
    "ТТН": "ttn",
    "Статус ТТН": "ttn_status",
    "Маржа": "margin",
    "Модель": "model",
    "Артикул": "sku",
    "Джерело трафіку": "traffic_source",
    "Менеджер який прийняв замовлення": "manager",
}

# manager -> shop. traffic_source використовується як запасний варіант,
# якщо менеджер порожній або невідомий.
MANAGER_TO_SHOP = {
    "Юля": "Best",
    "Настя": "Bunnix",
    "PROM": "Пром",
    "OLX": "ОЛХ",
}
TRAFFIC_SOURCE_TO_SHOP = {
    "інстаграм реклама": "Best",
    "nst": "Bunnix",
    "PROM": "Пром",
    "ОЛХ": "ОЛХ",
    "Назар": "Best",
    "ПАРК": "Best",
}
# дефолт, якщо і Менеджер, і Джерело трафіку порожні/невідомі (рішення власника)
UNMAPPED_SHOP = "Best"

SUCCESS_STATUSES = {"Отримано"}
REFUSED_STATUSES = {"Відмова"}
# все інше (На пошті, Чекає на надходження, Відправлення слідує, ...) = "в процесі"

# поля, які можуть змінитись між вивантаженнями для того самого замовлення
MUTABLE_FIELDS = [
    "ttn",
    "ttn_status",
    "margin",
    "income_raw",
    "prepayment",
    "outcome",
]

MASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "orders_master.csv"


def assign_shop(row: pd.Series) -> str:
    manager = row["manager"]
    if pd.notna(manager) and manager in MANAGER_TO_SHOP:
        return MANAGER_TO_SHOP[manager]
    traffic_source = row["traffic_source"]
    if pd.notna(traffic_source) and traffic_source in TRAFFIC_SOURCE_TO_SHOP:
        return TRAFFIC_SOURCE_TO_SHOP[traffic_source]
    return UNMAPPED_SHOP


def assign_outcome(ttn_status: str) -> str:
    if ttn_status in SUCCESS_STATUSES:
        return "success"
    if ttn_status in REFUSED_STATUSES:
        return "refused"
    return "pending"


def make_order_key(row: pd.Series) -> str:
    date_str = "" if pd.isna(row["date"]) else str(row["date"])
    phone_str = "" if pd.isna(row["phone"]) else str(row["phone"])
    model_str = "" if pd.isna(row["model"]) else str(row["model"]).strip()
    sku_str = "" if pd.isna(row["sku"]) else str(row["sku"]).strip()
    return "|".join([date_str, phone_str, model_str, sku_str])


def normalize(path: Path, source_file: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = df.rename(columns=RAW_COLUMNS)

    df["shop"] = df.apply(assign_shop, axis=1)
    df["outcome"] = df["ttn_status"].apply(assign_outcome)
    df["order_key"] = df.apply(make_order_key, axis=1)
    df["imported_at"] = datetime.now(timezone.utc).isoformat()
    df["source_file"] = source_file

    return df


def merge(master: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    if master.empty:
        return new, len(new), 0

    master = master.set_index("order_key")
    new = new.set_index("order_key")

    added = new.index.difference(master.index)
    existing = new.index.intersection(master.index)

    updated_count = 0
    for key in existing:
        if not master.loc[key, MUTABLE_FIELDS].equals(new.loc[key, MUTABLE_FIELDS]):
            master.loc[key, MUTABLE_FIELDS + ["imported_at", "source_file"]] = (
                new.loc[key, MUTABLE_FIELDS + ["imported_at", "source_file"]]
            )
            updated_count += 1

    merged = pd.concat([master, new.loc[added]])
    return merged.reset_index(), len(added), updated_count


def import_file(raw_path: Path, source_file: str | None = None) -> dict:
    """Імпортує один .xls у майстер-таблицю. Повертає короткий підсумок для UI/CLI."""
    raw_path = Path(raw_path)
    new_df = normalize(raw_path, source_file or raw_path.name)

    if MASTER_PATH.exists():
        master_df = pd.read_csv(MASTER_PATH, dtype={"order_key": str})
    else:
        master_df = pd.DataFrame()

    merged_df, added_count, updated_count = merge(master_df, new_df)

    MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")

    return {
        "file_name": raw_path.name,
        "added": added_count,
        "updated": updated_count,
        "unchanged": len(new_df) - added_count - updated_count,
        "total": len(merged_df),
        "shop_counts": merged_df["shop"].value_counts().to_dict(),
        "outcome_counts": merged_df["outcome"].value_counts().to_dict(),
    }


def main():
    if len(sys.argv) != 2:
        print("Використання: python scripts/etl/import_orders.py <шлях до .xls>")
        sys.exit(1)

    result = import_file(Path(sys.argv[1]))

    print(f"Файл: {result['file_name']}")
    print(f"Нових замовлень:     {result['added']}")
    print(f"Оновлених замовлень: {result['updated']}")
    print(f"Без змін:            {result['unchanged']}")
    print(f"Всього в майстер-таблиці: {result['total']}")
    print(f"Збережено: {MASTER_PATH}")
    print()
    print("Розподіл по магазинах (весь масив):")
    for shop, count in result["shop_counts"].items():
        print(f"{shop}: {count}")
    print()
    print("Розподіл по результату замовлення (весь масив):")
    for outcome, count in result["outcome_counts"].items():
        print(f"{outcome}: {count}")


if __name__ == "__main__":
    main()
