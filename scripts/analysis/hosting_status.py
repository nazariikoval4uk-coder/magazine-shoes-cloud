"""Відлік до дати, коли треба вручну продовжити безкоштовний хостинг (PythonAnywhere)."""
import json
from datetime import date, timedelta
from pathlib import Path

STATUS_PATH = Path(__file__).resolve().parents[2] / "dashboard" / "instance" / "hosting_status.json"
RENEW_PERIOD_DAYS = 30


def load_status() -> dict | None:
    if not STATUS_PATH.exists():
        return None
    with open(STATUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    expires_at = date.fromisoformat(data["expires_at"])
    days_left = (expires_at - date.today()).days
    if days_left <= 3:
        level = "critical"
    elif days_left <= 10:
        level = "warning"
    else:
        level = "ok"
    return {"expires_at": expires_at.isoformat(), "days_left": days_left, "level": level}


def set_expiry(expires_at: str) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"expires_at": expires_at}, f, indent=2)


def renew() -> None:
    set_expiry((date.today() + timedelta(days=RENEW_PERIOD_DAYS)).isoformat())
