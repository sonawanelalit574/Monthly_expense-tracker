from __future__ import annotations

import secrets
from datetime import date, timedelta


def salary_credit_code(credit_on: date, amount: float) -> str:
    stamp = credit_on.strftime("%Y%m%d")
    token = secrets.token_hex(3).upper()
    rupees = int(amount)
    return f"FN-SAL-{stamp}-{rupees}-{token}"


def next_credit_date(credit_day: int, today: date | None = None) -> date:
    today = today or date.today()
    day = max(1, min(int(credit_day or 1), 28))
    candidate = date(today.year, today.month, day)
    if candidate < today:
        month = today.month + 1
        year = today.year + (1 if month == 13 else 0)
        month = 1 if month == 13 else month
        candidate = date(year, month, day)
    return candidate


def days_until(target: date, today: date | None = None) -> int:
    today = today or date.today()
    return (target - today).days
