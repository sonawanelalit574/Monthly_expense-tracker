from __future__ import annotations

from threading import Lock
from time import time

import requests

HTTP_TIMEOUT = 12
CACHE_TTL = 15 * 60

# Country-first catalogue for the converter UI. Live rates come from open.er-api.com.
COUNTRIES = [
    {"country": "India", "code": "INR", "symbol": "₹", "flag": "🇮🇳"},
    {"country": "United States", "code": "USD", "symbol": "$", "flag": "🇺🇸"},
    {"country": "Euro area", "code": "EUR", "symbol": "€", "flag": "🇪🇺"},
    {"country": "United Kingdom", "code": "GBP", "symbol": "£", "flag": "🇬🇧"},
    {"country": "Japan", "code": "JPY", "symbol": "¥", "flag": "🇯🇵"},
    {"country": "China", "code": "CNY", "symbol": "¥", "flag": "🇨🇳"},
    {"country": "United Arab Emirates", "code": "AED", "symbol": "د.إ", "flag": "🇦🇪"},
    {"country": "Saudi Arabia", "code": "SAR", "symbol": "﷼", "flag": "🇸🇦"},
    {"country": "Singapore", "code": "SGD", "symbol": "$", "flag": "🇸🇬"},
    {"country": "Australia", "code": "AUD", "symbol": "$", "flag": "🇦🇺"},
    {"country": "Canada", "code": "CAD", "symbol": "$", "flag": "🇨🇦"},
    {"country": "Switzerland", "code": "CHF", "symbol": "Fr", "flag": "🇨🇭"},
    {"country": "Hong Kong", "code": "HKD", "symbol": "$", "flag": "🇭🇰"},
    {"country": "South Korea", "code": "KRW", "symbol": "₩", "flag": "🇰🇷"},
    {"country": "Thailand", "code": "THB", "symbol": "฿", "flag": "🇹🇭"},
    {"country": "Malaysia", "code": "MYR", "symbol": "RM", "flag": "🇲🇾"},
    {"country": "Indonesia", "code": "IDR", "symbol": "Rp", "flag": "🇮🇩"},
    {"country": "Philippines", "code": "PHP", "symbol": "₱", "flag": "🇵🇭"},
    {"country": "Vietnam", "code": "VND", "symbol": "₫", "flag": "🇻🇳"},
    {"country": "Pakistan", "code": "PKR", "symbol": "₨", "flag": "🇵🇰"},
    {"country": "Bangladesh", "code": "BDT", "symbol": "৳", "flag": "🇧🇩"},
    {"country": "Sri Lanka", "code": "LKR", "symbol": "Rs", "flag": "🇱🇰"},
    {"country": "Nepal", "code": "NPR", "symbol": "Rs", "flag": "🇳🇵"},
    {"country": "Qatar", "code": "QAR", "symbol": "﷼", "flag": "🇶🇦"},
    {"country": "Kuwait", "code": "KWD", "symbol": "د.ك", "flag": "🇰🇼"},
    {"country": "Bahrain", "code": "BHD", "symbol": ".د.ب", "flag": "🇧🇭"},
    {"country": "Oman", "code": "OMR", "symbol": "﷼", "flag": "🇴🇲"},
    {"country": "South Africa", "code": "ZAR", "symbol": "R", "flag": "🇿🇦"},
    {"country": "Nigeria", "code": "NGN", "symbol": "₦", "flag": "🇳🇬"},
    {"country": "Kenya", "code": "KES", "symbol": "KSh", "flag": "🇰🇪"},
    {"country": "Egypt", "code": "EGP", "symbol": "£", "flag": "🇪🇬"},
    {"country": "Turkey", "code": "TRY", "symbol": "₺", "flag": "🇹🇷"},
    {"country": "Russia", "code": "RUB", "symbol": "₽", "flag": "🇷🇺"},
    {"country": "Brazil", "code": "BRL", "symbol": "R$", "flag": "🇧🇷"},
    {"country": "Mexico", "code": "MXN", "symbol": "$", "flag": "🇲🇽"},
    {"country": "Argentina", "code": "ARS", "symbol": "$", "flag": "🇦🇷"},
    {"country": "Chile", "code": "CLP", "symbol": "$", "flag": "🇨🇱"},
    {"country": "Colombia", "code": "COP", "symbol": "$", "flag": "🇨🇴"},
    {"country": "New Zealand", "code": "NZD", "symbol": "$", "flag": "🇳🇿"},
    {"country": "Sweden", "code": "SEK", "symbol": "kr", "flag": "🇸🇪"},
    {"country": "Norway", "code": "NOK", "symbol": "kr", "flag": "🇳🇴"},
    {"country": "Denmark", "code": "DKK", "symbol": "kr", "flag": "🇩🇰"},
    {"country": "Poland", "code": "PLN", "symbol": "zł", "flag": "🇵🇱"},
    {"country": "Czechia", "code": "CZK", "symbol": "Kč", "flag": "🇨🇿"},
    {"country": "Hungary", "code": "HUF", "symbol": "Ft", "flag": "🇭🇺"},
    {"country": "Romania", "code": "RON", "symbol": "lei", "flag": "🇷🇴"},
    {"country": "Israel", "code": "ILS", "symbol": "₪", "flag": "🇮🇱"},
    {"country": "Taiwan", "code": "TWD", "symbol": "NT$", "flag": "🇹🇼"},
    {"country": "Mauritius", "code": "MUR", "symbol": "₨", "flag": "🇲🇺"},
    {"country": "Ghana", "code": "GHS", "symbol": "₵", "flag": "🇬🇭"},
]

FALLBACK_USD = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.78,
    "INR": 83.5,
    "JPY": 149.0,
    "CNY": 7.2,
    "AED": 3.67,
    "SAR": 3.75,
    "SGD": 1.34,
    "AUD": 1.52,
    "CAD": 1.36,
    "CHF": 0.88,
    "HKD": 7.82,
    "KRW": 1340.0,
    "THB": 35.5,
    "MYR": 4.7,
    "IDR": 15500.0,
    "PHP": 56.5,
    "VND": 24500.0,
    "PKR": 278.0,
    "BDT": 110.0,
    "LKR": 300.0,
    "NPR": 133.6,
    "QAR": 3.64,
    "KWD": 0.31,
    "BHD": 0.38,
    "OMR": 0.38,
    "ZAR": 18.4,
    "NGN": 1550.0,
    "KES": 129.0,
    "EGP": 48.0,
    "TRY": 32.5,
    "RUB": 92.0,
    "BRL": 5.1,
    "MXN": 17.1,
    "ARS": 890.0,
    "CLP": 930.0,
    "COP": 3950.0,
    "NZD": 1.64,
    "SEK": 10.4,
    "NOK": 10.6,
    "DKK": 6.85,
    "PLN": 3.95,
    "CZK": 23.2,
    "HUF": 360.0,
    "RON": 4.57,
    "ILS": 3.7,
    "TWD": 32.1,
    "MUR": 46.0,
    "GHS": 14.5,
}

_cache: dict[str, tuple[float, object]] = {}
_lock = Lock()


def _cache_get(key: str):
    with _lock:
        hit = _cache.get(key)
        if not hit:
            return None
        stored_at, value = hit
        if time() - stored_at > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value) -> None:
    with _lock:
        _cache[key] = (time(), value)


def fetch_usd_rates() -> tuple[dict[str, float], str, bool]:
    cached = _cache_get("usd")
    if cached is not None:
        return cached
    try:
        response = requests.get("https://open.er-api.com/v6/latest/USD", timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        rates = {str(k).upper(): float(v) for k, v in (payload.get("rates") or {}).items()}
        rates["USD"] = 1.0
        stamp = str(payload.get("time_last_update_utc") or "live")
        result = (rates, stamp, True)
        _cache_set("usd", result)
        return result
    except (requests.RequestException, ValueError, TypeError):
        result = (dict(FALLBACK_USD), "offline fallback", False)
        _cache_set("usd", result)
        return result


def convert(amount: float, source: str, target: str) -> dict:
    source = source.upper().strip()
    target = target.upper().strip()
    rates, stamp, live = fetch_usd_rates()
    if source not in rates or target not in rates:
        raise ValueError(f"No rate for {source} → {target}")
    usd_value = amount / rates[source]
    result = usd_value * rates[target]
    rate = result / amount if amount else rates[target] / rates[source]
    return {
        "amount": amount,
        "from": source,
        "to": target,
        "rate": rate,
        "result": result,
        "as_of": stamp,
        "live": live,
    }
