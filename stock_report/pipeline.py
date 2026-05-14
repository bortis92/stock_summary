from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from .ai import summarize_news
from .analysis import (
    abnormal_volume_price,
    revenue_growth_filter,
    sort_by_change_pct,
    sort_by_turnover,
)
from .fetchers import (
    DataClient,
    fetch_article_bodies,
    fetch_global_markets,
    fetch_market_turnover,
    fetch_news,
    fetch_revenues,
    fetch_tpex_quotes,
    fetch_twse_institution_by_stock,
    fetch_twse_institution_summary,
    fetch_twse_quotes,
)
from .render import render_monthly_revenue_report, render_report
from .watchlist import load_watchlist


def build_report(report_date: date, output_dir: Path, watchlist_path: Path) -> Path:
    client = DataClient()
    watchlist_codes = load_watchlist(watchlist_path)

    twse_quotes, twse_indices, twse_has_data = fetch_twse_quotes(client, report_date)
    tpex_quotes, tpex_indices = fetch_tpex_quotes(client, report_date)
    quotes = twse_quotes + tpex_quotes
    indices = twse_indices + tpex_indices

    previous_date = _previous_weekday(report_date)
    previous_twse, _, _ = fetch_twse_quotes(client, previous_date)
    previous_tpex, _ = fetch_tpex_quotes(client, previous_date)
    previous_quotes = previous_twse + previous_tpex

    market_turnover = fetch_market_turnover(client, report_date, previous_date)
    institution_summary = fetch_twse_institution_summary(client, report_date)
    institution_rows = fetch_twse_institution_by_stock(client, report_date)
    global_markets = fetch_global_markets(client)

    keywords = _news_keywords(watchlist_codes, quotes)
    news = fetch_news(client, keywords, limit=_env_int("NEWS_RSS_LIMIT", 60))
    if os.getenv("NEWS_FETCH_BODY", "1").strip() not in {"0", "false", "False", "no"}:
        news = fetch_article_bodies(
            client,
            news,
            limit=_env_int("NEWS_MAX_ARTICLES", 30),
            max_chars=_env_int("NEWS_MAX_CHARS_PER_ARTICLE", 1500),
        )
    news_digest = summarize_news(news, quotes, watchlist_codes)

    turnover_top = sort_by_turnover(quotes, 30)
    gainers = sort_by_change_pct(quotes, 30, reverse=True)
    losers = sort_by_change_pct(quotes, 30, reverse=False)
    abnormal = abnormal_volume_price(quotes, previous_quotes)

    warnings = _quality_warnings(
        twse_has_data=twse_has_data,
        quote_count=len(quotes),
        institution_count=len(institution_rows),
        previous_quote_count=len(previous_quotes),
        watchlist_codes=watchlist_codes,
    )
    markdown = render_report(
        report_date=report_date,
        is_trading_day=twse_has_data or bool(quotes),
        indices=indices,
        quotes=quotes,
        previous_quotes=previous_quotes,
        market_turnover=market_turnover,
        institution_summary=institution_summary,
        institution_rows=institution_rows,
        global_markets=global_markets,
        news=news,
        news_digest=news_digest,
        turnover_top=turnover_top,
        gainers=gainers,
        losers=losers,
        abnormal=abnormal,
        watchlist_codes=watchlist_codes,
        revenue_records=[],
        revenue_screen=None,
        sources=client.sources,
        warnings=warnings,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{report_date.isoformat()}.md"
    output_path.write_text(markdown, encoding="utf-8")
    if 5 <= report_date.day <= 12:
        _write_monthly_revenue_report(report_date, output_dir, watchlist_codes)
    return output_path


def _write_monthly_revenue_report(report_date: date, output_dir: Path, watchlist_codes: list[str]) -> Path:
    revenue_month = _latest_revenue_month_date(report_date)
    client = DataClient()
    revenue_records = fetch_revenues(client, revenue_month)
    revenue_screen = revenue_growth_filter(revenue_records, min_latest_revenue=100_000)
    markdown = render_monthly_revenue_report(
        revenue_month=revenue_month,
        watchlist_codes=watchlist_codes,
        revenue_records=revenue_records,
        revenue_screen=revenue_screen,
        sources=client.sources,
    )
    output_path = output_dir / f"{revenue_month.year}-{revenue_month.month:02d}-month.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _previous_weekday(value: date) -> date:
    current = value - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _latest_revenue_month_date(report_date: date) -> date:
    year = report_date.year
    month = report_date.month - 1
    if month == 0:
        year -= 1
        month = 12
    return date(year, month, 1)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _news_keywords(watchlist_codes: list[str], quotes: list) -> list[str]:
    quote_map = {q.code: q for q in quotes}
    keywords = ["台股", "AI", "半導體", "月營收", "法說", "重大訊息"]
    for code in watchlist_codes:
        keywords.append(code)
        quote = quote_map.get(code)
        if quote and quote.name:
            keywords.append(quote.name)
    return keywords


def _quality_warnings(
    twse_has_data: bool,
    quote_count: int,
    institution_count: int,
    previous_quote_count: int,
    watchlist_codes: list[str],
) -> list[str]:
    warnings: list[str] = []
    if not twse_has_data:
        warnings.append("TWSE 當日上市盤後資料未取得；若今日為交易日，可能是資料尚未公布或來源格式變動。")
    if quote_count == 0:
        warnings.append("未取得當日上市櫃個股行情，排行榜與量價分析資料待確認。")
    if institution_count == 0:
        warnings.append("未取得法人個股買賣超資料，法人排行與追蹤股法人欄位資料待確認。")
    if previous_quote_count == 0:
        warnings.append("未取得前一交易日行情，量變化與異常量價倍數資料待確認。")
    if not watchlist_codes:
        warnings.append("尚未設定 watchlist.txt，追蹤個股區塊不列個股。")
    return warnings
