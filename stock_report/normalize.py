from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def tw_date(value: date, sep: str = "/") -> str:
    return f"{value.year - 1911:03d}{sep}{value.month:02d}{sep}{value.day:02d}"


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "--", "-", "X", "除權息", "不比"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace("+", "")
    try:
        number = float(Decimal(text))
        return -number if negative else number
    except (InvalidOperation, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def pct(change: float | None, previous_close: float | None) -> float | None:
    if change is None or previous_close in (None, 0):
        return None
    return change / previous_close * 100


def lots_from_shares(shares: int | float | None) -> float | None:
    return shares / 1000 if shares is not None else None


def fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "尚未公布"
    return f"{value:,.{digits}f}"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "尚未公布"
    return f"{value:,}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "尚未公布"
    return f"{value:+.2f}%"


def fmt_lots(value: float | None) -> str:
    if value is None:
        return "尚未公布"
    return f"{value:,.0f} 張"


def fmt_100m(value: float | None) -> str:
    if value is None:
        return "尚未公布"
    return f"{value / 100_000_000:,.2f} 億元"


def fmt_revenue_100m(value: float | None) -> str:
    if value is None:
        return "尚未公布"
    return f"{value / 100_000:,.2f} 億元"


def clean_stock_code(value: str) -> str:
    return value.strip().split()[0]
