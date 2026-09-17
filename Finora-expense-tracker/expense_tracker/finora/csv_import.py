from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

CHANNEL_WORDS = {
    "upi": "phone",
    "phone": "phone",
    "gpay": "phone",
    "paytm": "phone",
    "neft": "bank",
    "imps": "bank",
    "rtgs": "bank",
    "bank": "bank",
    "cash": "cash",
    "atm": "cash",
    "card": "card",
    "visa": "card",
    "master": "card",
}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _pick(row: dict, *names: str) -> str:
    keys = {_norm(k): v for k, v in row.items()}
    for name in names:
        value = keys.get(_norm(name))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def parse_amount(raw: str) -> float:
    text = (raw or "").replace(",", "").replace("₹", "").replace("INR", "").strip()
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in {".", "-"}:
        return 0.0
    return abs(float(text))


def parse_day(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = text.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def guess_channel(title: str, explicit: str = "") -> str:
    blob = f"{explicit} {title}".lower()
    for word, channel in CHANNEL_WORDS.items():
        if word in blob:
            return channel
    return "bank"


def convert_row(raw: dict, fallback_category: str = "Other") -> dict | None:
    title = _pick(raw, "title", "description", "narration", "particulars", "details", "remark", "name") or "Imported"
    day = parse_day(_pick(raw, "date", "txn date", "transaction date", "value date", "posted", "occurred_on"))
    debit = parse_amount(_pick(raw, "debit", "withdrawal", "dr", "spent"))
    credit = parse_amount(_pick(raw, "credit", "deposit", "cr", "income"))
    amount = parse_amount(_pick(raw, "amount", "inr", "value"))
    direction = (_pick(raw, "direction", "type") or "").lower()
    if debit and not credit:
        amount, direction = debit, "out"
    elif credit and not debit:
        amount, direction = credit, "in"
    elif not amount:
        return None
    if direction not in {"in", "out"}:
        direction = "out"
    if not day:
        day = date.today()
    category = _pick(raw, "category", "label") or fallback_category
    channel = guess_channel(title, _pick(raw, "channel", "mode", "method"))
    merchant = _pick(raw, "merchant", "payee", "beneficiary")
    return {
        "title": title[:160],
        "category": category[:80] or "Other",
        "channel": channel,
        "direction": direction,
        "amount": round(amount, 2),
        "occurred_on": day.isoformat(),
        "merchant": merchant[:160],
        "notes": "csv import",
    }


def parse_csv_bytes(payload: bytes) -> list[dict]:
    text = payload.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    converted = []
    for raw in reader:
        item = convert_row({(k or ""): (v or "") for k, v in raw.items()})
        if item:
            converted.append(item)
    return converted
