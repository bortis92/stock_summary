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
from .render import markdown_to_html, render_monthly_revenue_report, render_report
from .watchlist import load_watchlist


DAILY_REPORTS = ("daily_0.html", "daily_1.html", "daily_2.html")
MONTHLY_REPORT = "month.html"
SEASON_REPORT = "season.html"
INDEX_REPORT = "index.html"


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
    rotate_daily_reports(output_dir)
    output_path = output_dir / DAILY_REPORTS[0]
    write_html_report(output_path, markdown_to_html(markdown))
    if 5 <= report_date.day <= 12:
        _write_monthly_revenue_report(report_date, output_dir, watchlist_codes)
    write_report_index(output_dir)
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
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / MONTHLY_REPORT
    write_html_report(output_path, markdown_to_html(markdown))
    write_report_index(output_dir)
    return output_path


def rotate_daily_reports(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    oldest = output_dir / DAILY_REPORTS[2]
    if oldest.exists():
        oldest.unlink()
    for current_name, next_name in zip(reversed(DAILY_REPORTS[:2]), reversed(DAILY_REPORTS[1:]), strict=True):
        current = output_dir / current_name
        if current.exists():
            current.replace(output_dir / next_name)


def write_html_report(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def write_report_index(output_dir: Path, site_root: Path | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    site_root = site_root or output_dir.parent
    site_root.mkdir(parents=True, exist_ok=True)
    report_prefix = output_dir.name
    cards = [
        ("最新日報", f"{report_prefix}/daily_0.html", "今日或最近一次產生的台股盤後快報"),
        ("前一份日報", f"{report_prefix}/daily_1.html", "上一份保留的台股盤後快報"),
        ("前二份日報", f"{report_prefix}/daily_2.html", "再前一份保留的台股盤後快報"),
        ("最新月營收報告", f"{report_prefix}/month.html", "最新覆寫的月營收追蹤報告"),
        ("最新季報", f"{report_prefix}/season.html", "最新覆寫的季報整理"),
    ]
    card_html = "\n".join(
        f'      <a class="card" href="{href}"><span>{title}</span><small>{description}</small></a>'
        for title, href, description in cards
    )
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>台股報告入口</title>
  <style>
    :root {{ color-scheme: light; --text:#172033; --muted:#5f6b7a; --line:#d9e0ea; --bg:#f6f8fb; --card:#ffffff; --accent:#0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","Microsoft JhengHei",Arial,sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:980px; margin:0 auto; padding:40px 20px 56px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px,4vw,44px); letter-spacing:0; }}
    p {{ margin:0 0 28px; color:var(--muted); line-height:1.7; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }}
    .card {{ display:block; min-height:120px; padding:20px; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--text); text-decoration:none; box-shadow:0 1px 3px rgba(20,32,50,.05); }}
    .card:hover {{ border-color:var(--accent); }}
    .card span {{ display:block; margin-bottom:10px; font-size:20px; font-weight:700; }}
    .card small {{ color:var(--muted); line-height:1.6; }}
  </style>
</head>
<body>
  <main>
    <h1>台股報告入口</h1>
    <p>選擇要查看的固定報告頁。日報保留最新三份，月營收報告與季報只保留最新版本。</p>
    <section class="grid">
{card_html}
    </section>
  </main>
</body>
</html>
"""
    output_path = site_root / INDEX_REPORT
    write_html_report(output_path, html)
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
