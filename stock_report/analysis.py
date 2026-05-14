from __future__ import annotations

from datetime import date, timedelta

from .models import InstitutionByStock, RevenueRecord, StockQuote


def previous_calendar_day(report_date: date) -> date:
    return report_date - timedelta(days=1)


def sort_by_turnover(quotes: list[StockQuote], limit: int = 30) -> list[StockQuote]:
    return sorted(
        [q for q in quotes if q.turnover is not None],
        key=lambda q: q.turnover or 0,
        reverse=True,
    )[:limit]


def sort_by_change_pct(quotes: list[StockQuote], limit: int = 30, reverse: bool = True) -> list[StockQuote]:
    return sorted(
        [q for q in quotes if q.change_pct is not None],
        key=lambda q: q.change_pct or 0,
        reverse=reverse,
    )[:limit]


def institution_rank(
    rows: list[InstitutionByStock],
    field: str,
    limit: int = 20,
    reverse: bool = True,
) -> list[InstitutionByStock]:
    return sorted(
        [r for r in rows if getattr(r, field) is not None],
        key=lambda r: getattr(r, field) or 0,
        reverse=reverse,
    )[:limit]


def abnormal_volume_price(
    today_quotes: list[StockQuote],
    previous_quotes: list[StockQuote],
) -> list[tuple[StockQuote, float]]:
    previous_by_code = {q.code: q for q in previous_quotes if q.volume_lots not in (None, 0)}
    matches: list[tuple[StockQuote, float]] = []
    for quote in today_quotes:
        previous = previous_by_code.get(quote.code)
        if not previous or quote.volume_lots is None or quote.change_pct is None:
            continue
        ratio = quote.volume_lots / previous.volume_lots
        if ratio >= 3 and quote.volume_lots > 1000 and quote.change_pct > 3:
            matches.append((quote, ratio))
    return sorted(matches, key=lambda item: item[1], reverse=True)


def revenue_growth_filter(
    records: list[RevenueRecord],
    min_yoy: float = 30,
    min_latest_revenue: float | None = 100_000,
) -> list[RevenueRecord]:
    return sorted(
        [
            r
            for r in records
            if r.yoy_pct is not None
            and r.yoy_pct >= min_yoy
            and (min_latest_revenue is None or (r.latest_revenue is not None and r.latest_revenue >= min_latest_revenue))
        ],
        key=lambda r: r.yoy_pct or 0,
        reverse=True,
    )


def quote_by_code(quotes: list[StockQuote]) -> dict[str, StockQuote]:
    return {q.code: q for q in quotes}


def institution_by_code(rows: list[InstitutionByStock]) -> dict[str, InstitutionByStock]:
    return {r.code: r for r in rows}


def revenues_by_code(rows: list[RevenueRecord]) -> dict[str, RevenueRecord]:
    return {r.code: r for r in rows}
