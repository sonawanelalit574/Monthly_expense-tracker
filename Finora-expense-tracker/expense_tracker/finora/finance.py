from __future__ import annotations

from calendar import monthrange
from datetime import date


def month_key(value: date | None = None) -> str:
    value = value or date.today()
    return value.strftime("%Y-%m")


def in_month(occurred_on: date, key: str) -> bool:
    return occurred_on.strftime("%Y-%m") == key


def emi_amount(principal: float, annual_rate: float, tenure_months: int) -> float:
    if tenure_months <= 0:
        return 0.0
    r = (annual_rate / 12.0) / 100.0
    if r == 0:
        return principal / tenure_months
    factor = (1 + r) ** tenure_months
    return principal * r * factor / (factor - 1)


def sip_future_value(monthly: float, annual_rate: float, months: int) -> float:
    if months <= 0:
        return 0.0
    r = (annual_rate / 12.0) / 100.0
    if r == 0:
        return monthly * months
    return monthly * (((1 + r) ** months - 1) / r) * (1 + r)


def months_elapsed(start_month: str, current_month: str) -> int:
    try:
        sy, sm = [int(x) for x in start_month.split("-")]
        cy, cm = [int(x) for x in current_month.split("-")]
    except ValueError:
        return 0
    return max(0, (cy - sy) * 12 + (cm - sm) + 1)


def remaining_days_in_month(today: date | None = None) -> int:
    today = today or date.today()
    last = monthrange(today.year, today.month)[1]
    return last - today.day


def suggested_daily_spend(available: float, today: date | None = None) -> float:
    days = remaining_days_in_month(today)
    if days <= 0:
        return max(0.0, available)
    return max(0.0, available / days)
