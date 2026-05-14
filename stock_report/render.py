from __future__ import annotations

import html as html_lib
import re
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


URL_RE = re.compile(r"(https?://[^\s<]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def markdown_to_html(markdown: str, title: str | None = None) -> str:
    lines = markdown.splitlines()
    page_title = title or next((line.lstrip("#").strip() for line in lines if line.startswith("# ")), "台股報告")
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(level, 1), 6)
            content = stripped[level:].strip()
            body.append(f"<h{level}>{_inline_html(content)}</h{level}>")
            i += 1
            continue
        if stripped.startswith(">"):
            parts: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                parts.append(lines[i].strip()[1:].strip())
                i += 1
            body.append("<blockquote>" + "<br>".join(_inline_html(part) for part in parts) + "</blockquote>")
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            headers = _split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i]))
                i += 1
            table_html = ['<div class="table-wrap"><table><thead><tr>']
            table_html.extend(f"<th>{_inline_html(cell)}</th>" for cell in headers)
            table_html.append("</tr></thead><tbody>")
            for row in rows:
                table_html.append("<tr>")
                table_html.extend(f"<td>{_inline_html(cell)}</td>" for cell in row)
                table_html.append("</tr>")
            table_html.append("</tbody></table></div>")
            body.append("".join(table_html))
            continue
        if stripped.startswith("- "):
            body.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                body.append(f"<li>{_inline_html(lines[i].strip()[2:].strip())}</li>")
                i += 1
            body.append("</ul>")
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", ">", "|", "- ")):
            paragraph.append(lines[i].strip())
            i += 1
        body.append("<p>" + _inline_html(" ".join(paragraph)) + "</p>")
    css = """
    :root { color-scheme: light; --text:#172033; --muted:#5f6b7a; --line:#d9e0ea; --bg:#f6f8fb; --card:#ffffff; --accent:#0f766e; --accent-soft:#e8f4f2; }
    * { box-sizing: border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","Microsoft JhengHei",Arial,sans-serif; background:var(--bg); color:var(--text); line-height:1.65; }
    main { max-width:1180px; margin:0 auto; padding:32px 20px 56px; }
    h1 { margin:0 0 24px; padding-bottom:16px; border-bottom:3px solid var(--accent); font-size:clamp(28px,4vw,42px); letter-spacing:0; }
    h2 { margin:34px 0 14px; font-size:24px; letter-spacing:0; }
    h3 { margin:26px 0 10px; font-size:19px; color:#26364d; letter-spacing:0; }
    p, blockquote { margin:10px 0; }
    blockquote { padding:10px 14px; border-left:4px solid var(--accent); background:var(--accent-soft); color:#23413e; }
    a { color:#0f5f9e; text-decoration:none; }
    a:hover { text-decoration:underline; }
    ul { padding-left:24px; }
    li { margin:4px 0; overflow-wrap:anywhere; }
    .table-wrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; margin:14px 0 22px; box-shadow:0 1px 3px rgba(20,32,50,.05); }
    table { width:max-content; min-width:100%; border-collapse:collapse; table-layout:auto; }
    th, td { padding:9px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    th { position:sticky; top:0; background:#eef3f8; font-weight:700; color:#24324a; white-space:nowrap; }
    td { white-space:nowrap; max-width:220px; }
    td:has(a) { max-width:280px; white-space:normal; }
    tbody tr:nth-child(even) { background:#fafbfd; }
    @media (max-width: 720px) { main { padding:24px 12px 44px; } th, td { padding:8px 9px; font-size:14px; } }
    """.strip()
    return (
        "<!doctype html>\n"
        '<html lang="zh-Hant">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html_lib.escape(page_title)}</title>\n"
        "  <style>\n"
        f"{css}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        + "\n".join("    " + item for item in body)
        + "\n  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _inline_html(value: str) -> str:
    pieces: list[str] = []
    pos = 0
    for match in MD_LINK_RE.finditer(value):
        pieces.append(_escape_and_link_urls(value[pos:match.start()]))
        label = html_lib.escape(match.group(1), quote=False)
        href = html_lib.escape(match.group(2), quote=True)
        pieces.append(f'<a href="{href}">{label}</a>')
        pos = match.end()
    pieces.append(_escape_and_link_urls(value[pos:]))
    return "".join(pieces)


def _escape_and_link_urls(value: str) -> str:
    escaped = html_lib.escape(value, quote=False)
    return URL_RE.sub(lambda match: f'<a href="{html_lib.escape(match.group(1), quote=True)}">{match.group(1)}</a>', escaped)


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


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
