from __future__ import annotations

from datetime import date

from .models import (
    GlobalMarket,
    IndexSummary,
    InstitutionByStock,
    InstitutionSummary,
    MarketTurnover,
    NewsDigest,
    NewsItem,
    RevenueRecord,
    SourceNote,
    StockNewsSummary,
    StockQuote,
)
from .normalize import fmt_100m, fmt_lots, fmt_num, fmt_pct, fmt_revenue_100m


def table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "尚未公布或資料待確認。\n"
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    output.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(output) + "\n"


def render_report(
    report_date: date,
    is_trading_day: bool,
    indices: list[IndexSummary],
    quotes: list[StockQuote],
    previous_quotes: list[StockQuote],
    market_turnover: MarketTurnover,
    institution_summary: InstitutionSummary,
    institution_rows: list[InstitutionByStock],
    global_markets: list[GlobalMarket],
    news: list[NewsItem],
    news_digest: NewsDigest,
    turnover_top: list[StockQuote],
    gainers: list[StockQuote],
    losers: list[StockQuote],
    abnormal: list[tuple[StockQuote, float]],
    watchlist_codes: list[str],
    revenue_records: list[RevenueRecord],
    revenue_screen: list[RevenueRecord] | None,
    sources: list[SourceNote],
    warnings: list[str],
) -> str:
    lines: list[str] = [f"# 台股盤後快報 {report_date.isoformat()}", ""]
    if not is_trading_day:
        lines.extend(["> 今日台股休市或官方盤後資料尚未公布。", ""])

    lines.extend(_ai_summary_block(news_digest))

    lines.extend(["## 大盤與法人總覽", ""])
    lines.append(table(["指數", "收盤", "漲跌", "漲跌幅", "上市成交金額"], _index_rows(indices, market_turnover)))
    lines.append(
        table(
            ["法人", "買賣超金額"],
            [
                ["外資及陸資", fmt_100m(institution_summary.foreign_amount)],
                ["投信", fmt_100m(institution_summary.investment_trust_amount)],
                ["自營商", fmt_100m(institution_summary.dealer_amount)],
                ["三大法人合計", fmt_100m(institution_summary.total_amount)],
            ],
        )
    )

    lines.extend(["", "## 國際市場與美股重點", ""])
    lines.append(
        table(
            ["市場", "收盤/最新", "漲跌幅", "資料日期"],
            [[m.name, fmt_num(m.close), fmt_pct(m.change_pct), m.source_date] for m in global_markets],
        )
    )

    lines.extend(["", "## 追蹤個股清單", ""])
    lines.append(_watchlist_table(watchlist_codes, quotes, previous_quotes, institution_rows))

    lines.extend(["", "## 個股新聞摘要表格", ""])
    lines.append(_stock_news_table(news_digest.stock_summaries))

    lines.extend(["", "## 法人買賣超排行", ""])
    lines.extend(_institution_rank_sections(institution_rows))

    lines.extend(["", "## 成交金額排行", ""])
    lines.append(_quote_table(turnover_top, include_turnover=True))
    if len(turnover_top) < 30:
        lines.append(f"> 成交金額排行目前取得 {len(turnover_top)} 檔，少於 30 檔時代表來源資料不足或尚未公布。")

    lines.extend(["", "## 漲跌幅排行", "", "### 漲幅前 30 大", ""])
    lines.append(_quote_table(gainers))
    lines.extend(["", "### 跌幅前 30 大", ""])
    lines.append(_quote_table(losers))

    lines.extend(["", "## 異常量價個股", ""])
    lines.append(
        table(
            ["代號", "名稱", "收盤價", "漲跌幅", "成交量", "量增倍數"],
            [[q.code, q.name, fmt_num(q.close), fmt_pct(q.change_pct), fmt_lots(q.volume_lots), f"{ratio:.2f} 倍"] for q, ratio in abnormal],
        )
    )

    lines.extend(_other_news_block(news_digest.other_news if news_digest.other_news else news))

    lines.extend(["", "## 資料來源與注意事項", ""])
    if news_digest.status:
        lines.append(f"- 新聞 AI 摘要：{news_digest.status}")
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        f"- {source.name}：{source.status}。來源：{source.url}"
        + (f"；說明：{source.detail}" if source.detail else "")
        for source in sources
    )
    return "\n".join(lines).rstrip() + "\n"


def render_monthly_revenue_report(
    revenue_month: date,
    watchlist_codes: list[str],
    revenue_records: list[RevenueRecord],
    revenue_screen: list[RevenueRecord],
    sources: list[SourceNote],
) -> str:
    lines = [
        f"# 月營收追蹤報告 {revenue_month.year}-{revenue_month.month:02d}",
        "",
        "> 單位說明：最新月營收以億元列示；MOPS 原始資料單位為仟元。",
        "",
        "## 追蹤個股月營收",
        "",
    ]
    lines.append(_watchlist_revenue_table(watchlist_codes, revenue_records))
    lines.extend(
        [
            "",
            "## 月營收篩選",
            "",
            "> 篩選條件：單月年增率 >= 30%，且最新月營收 >= 1 億元。",
            "",
        ]
    )
    lines.append(
        table(
            ["代號", "名稱", "資料月份", "最新月營收（億元）", "單月年增率", "累計年增率", "上月累計年增率", "月增率"],
            [
                [
                    r.code,
                    r.name,
                    r.month,
                    fmt_revenue_100m(r.latest_revenue),
                    fmt_pct(r.yoy_pct),
                    fmt_pct(r.cumulative_yoy_pct),
                    fmt_pct(r.previous_cumulative_yoy_pct),
                    fmt_pct(r.mom_pct),
                ]
                for r in revenue_screen
            ],
        )
    )
    lines.extend(["", "## 資料來源與注意事項", ""])
    lines.extend(
        f"- {source.name}：{source.status}。來源：{source.url}"
        + (f"；說明：{source.detail}" if source.detail else "")
        for source in sources
    )
    return "\n".join(lines).rstrip() + "\n"


def _index_rows(indices: list[IndexSummary], market_turnover: MarketTurnover) -> list[list[str]]:
    return [
        [
            i.name,
            fmt_num(i.close),
            fmt_num(i.change),
            fmt_pct(i.change_pct),
            fmt_100m(market_turnover.listed_amount) if i.name == "加權指數" else "",
        ]
        for i in indices
    ]


def _quote_table(quotes: list[StockQuote], include_turnover: bool = False) -> str:
    headers = ["代號", "名稱", "收盤價", "漲跌幅", "成交量"]
    if include_turnover:
        headers.insert(4, "成交金額")
    rows: list[list[str]] = []
    for q in quotes:
        row = [q.code, q.name, fmt_num(q.close), fmt_pct(q.change_pct)]
        if include_turnover:
            row.append(fmt_100m(q.turnover))
        row.append(fmt_lots(q.volume_lots))
        rows.append(row)
    return table(headers, rows)


def _institution_rank_sections(rows: list[InstitutionByStock]) -> list[str]:
    from .analysis import institution_rank

    sections: list[str] = []
    specs = [
        ("外資買超前 20 大", "foreign_lots", True),
        ("外資賣超前 20 大", "foreign_lots", False),
        ("投信買超前 20 大", "investment_trust_lots", True),
        ("投信賣超前 20 大", "investment_trust_lots", False),
    ]
    for title, field, reverse in specs:
        ranked = institution_rank(rows, field, 20, reverse)
        sections.extend(["", f"### {title}", ""])
        sections.append(table(["代號", "名稱", "買賣超張數"], [[r.code, r.name, fmt_lots(getattr(r, field))] for r in ranked]))
        if len(ranked) < 20:
            sections.append(f"> {title} 目前取得 {len(ranked)} 檔，少於 20 檔時代表來源資料不足或尚未公布。")
    return sections


def _watchlist_table(
    codes: list[str],
    quotes: list[StockQuote],
    previous_quotes: list[StockQuote],
    institution_rows: list[InstitutionByStock],
) -> str:
    if not codes:
        return "尚未設定追蹤個股。\n"
    quote_map = {q.code: q for q in quotes}
    previous_map = {q.code: q for q in previous_quotes}
    institution_map = {r.code: r for r in institution_rows}
    rows: list[list[str]] = []
    for code in codes:
        quote = quote_map.get(code)
        previous = previous_map.get(code)
        inst = institution_map.get(code)
        volume_change = None
        if quote and previous and quote.volume_lots is not None and previous.volume_lots not in (None, 0):
            volume_change = (quote.volume_lots - previous.volume_lots) / previous.volume_lots * 100
        rows.append(
            [
                code,
                quote.name if quote else (inst.name if inst else "資料待確認"),
                fmt_num(quote.close if quote else None),
                fmt_num(quote.change if quote else None),
                fmt_pct(quote.change_pct if quote else None),
                fmt_lots(quote.volume_lots if quote else None),
                fmt_pct(volume_change),
                fmt_lots(inst.foreign_lots if inst else None),
                fmt_lots(inst.investment_trust_lots if inst else None),
                fmt_lots(inst.dealer_lots if inst else None),
            ]
        )
    return table(["代號", "名稱", "收盤價", "漲跌", "漲跌幅", "成交量", "量變化", "外資", "投信", "自營商"], rows)


def _watchlist_revenue_table(codes: list[str], revenues: list[RevenueRecord]) -> str:
    if not codes:
        return "尚未設定追蹤個股。\n"
    revenue_map = {r.code: r for r in revenues}
    rows: list[list[str]] = []
    for code in codes:
        revenue = revenue_map.get(code)
        rows.append(
            [
                code,
                revenue.name if revenue else "資料待確認",
                revenue.month if revenue else "尚未公布",
                fmt_revenue_100m(revenue.latest_revenue if revenue else None),
                fmt_pct(revenue.yoy_pct if revenue else None),
                fmt_pct(revenue.mom_pct if revenue else None),
                fmt_pct(revenue.cumulative_yoy_pct if revenue else None),
            ]
        )
    return table(["代號", "名稱", "資料月份", "最新月營收（億元）", "單月年增率", "月增率", "累計年增率"], rows)


def _ai_summary_block(digest: NewsDigest) -> list[str]:
    lines = ["## AI 快速重點整理", ""]
    if digest.market_bullets:
        lines.extend(f"- {bullet}" for bullet in digest.market_bullets)
    elif digest.status:
        lines.append(f"- {digest.status}")
    else:
        lines.append("- 尚未取得可整理的新聞重點。")
    lines.append("")
    return lines


def _stock_news_table(rows: list[StockNewsSummary]) -> str:
    return table(
        ["代號", "名稱", "新聞主題", "AI 摘要", "來源"],
        [
            [
                row.code or "市場",
                row.name or "資料待確認",
                row.topic or "新聞摘要",
                row.summary,
                "、".join(f"[來源{i + 1}]({url})" for i, url in enumerate(row.source_urls)) or "資料待確認",
            ]
            for row in rows
        ],
    )


def _other_news_block(news: list[NewsItem]) -> list[str]:
    if not news:
        return ["", "## 其他新聞連結", "", "尚未取得其他新聞連結。"]
    lines = ["", "## 其他新聞連結", ""]
    for item in news:
        status = f"，{item.content_status}" if item.content_status else ""
        lines.append(f"- [{item.title}]({item.url})（{item.source} {item.published}{status}）")
    return lines
