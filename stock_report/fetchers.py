from __future__ import annotations

import csv
import html
import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import StringIO
from typing import Any

from .models import (
    GlobalMarket,
    IndexSummary,
    InstitutionByStock,
    InstitutionSummary,
    MarketTurnover,
    NewsItem,
    QuarterlyFinancialRecord,
    RevenueRecord,
    SourceNote,
    StockQuote,
)
from .normalize import lots_from_shares, parse_int, parse_number, pct, tw_date, yyyymmdd


USER_AGENT = "Mozilla/5.0 TaiwanStockReport/1.0"


class DataClient:
    def __init__(self) -> None:
        self.sources: list[SourceNote] = []
        self._ssl_context = ssl.create_default_context()

    def note(self, name: str, url: str, status: str, detail: str = "") -> None:
        self.sources.append(SourceNote(name, url, status, datetime.now(timezone.utc), detail))

    def get_text(self, name: str, url: str, timeout: int = 20, encoding: str | None = None) -> str | None:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=self._ssl_context) as response:
                    body = response.read()
                    charset = encoding or response.headers.get_content_charset() or "utf-8"
                    text = body.decode(charset, errors="replace")
                    detail = f"retried {attempt} time(s)" if attempt else ""
                    self.note(name, url, "OK", detail)
                    return text
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(1.5 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if _is_socket_permission_denied(exc):
                    text = _powershell_get_text(url, timeout=timeout)
                    if text is not None:
                        self.note(name, url, "OK", "fetched via PowerShell Invoke-WebRequest (WinError 10013 fallback)")
                        return text
                break
        self.note(name, url, "資料待確認", str(last_error) if last_error else "")
        return None

    def get_json(self, name: str, url: str) -> dict[str, Any] | None:
        text = self.get_text(name, url)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            self.note(name, url, "資料待確認", f"JSON parse failed: {exc}")
            return None

    def post_text(self, name: str, url: str, data: dict[str, Any], timeout: int = 20, encoding: str | None = None) -> str | None:
        encoded = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=self._ssl_context) as response:
                    body = response.read()
                    charset = encoding or response.headers.get_content_charset() or "utf-8"
                    text = body.decode(charset, errors="replace")
                    detail = f"retried {attempt} time(s)" if attempt else ""
                    self.note(name, url, "OK", detail)
                    return text
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(1.5 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if _is_socket_permission_denied(exc):
                    text = _powershell_post_text(url, data, timeout=timeout)
                    if text is not None:
                        self.note(name, url, "OK", "posted via PowerShell Invoke-WebRequest (WinError 10013 fallback)")
                        return text
                break
        self.note(name, url, "資料待確認", str(last_error) if last_error else "")
        return None


def fetch_twse_quotes(client: DataClient, report_date: date) -> tuple[list[StockQuote], list[IndexSummary], bool]:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={yyyymmdd(report_date)}&type=ALLBUT0999&response=json"
    )
    payload = client.get_json("TWSE 上市盤後行情", url)
    if not payload or payload.get("stat") != "OK":
        return [], [], False

    quotes: list[StockQuote] = []
    indices: list[IndexSummary] = []
    for table in payload.get("tables", []):
        fields = table.get("fields", [])
        if "證券代號" in fields and "成交股數" in fields:
            for row in table.get("data", []):
                record = dict(zip(fields, row, strict=False))
                code = str(record.get("證券代號", "")).strip()
                if not code or not code[0].isdigit():
                    continue
                close = parse_number(record.get("收盤價"))
                change = _signed_change(record.get("漲跌(+/-)"), record.get("漲跌價差"))
                previous = close - change if close is not None and change is not None else None
                volume_shares = parse_int(record.get("成交股數"))
                quotes.append(
                    StockQuote(
                        code=code,
                        name=str(record.get("證券名稱", "")).strip(),
                        close=close,
                        change=change,
                        change_pct=pct(change, previous),
                        volume_shares=volume_shares,
                        volume_lots=lots_from_shares(volume_shares),
                        turnover=parse_number(record.get("成交金額")),
                        market="上市",
                        raw=record,
                    )
                )
        if "指數" in fields and "收盤指數" in fields:
            for row in table.get("data", []):
                record = dict(zip(fields, row, strict=False))
                name = str(record.get("指數", "")).strip()
                if name == "發行量加權股價指數":
                    close = parse_number(record.get("收盤指數"))
                    change = _signed_change(record.get("漲跌(+/-)"), record.get("漲跌點數"))
                    previous = close - change if close is not None and change is not None else None
                    indices.append(IndexSummary("加權指數", close, change, pct(change, previous)))
    return quotes, indices, bool(quotes)


def fetch_tpex_quotes(client: DataClient, report_date: date) -> tuple[list[StockQuote], list[IndexSummary]]:
    candidates = [
        (
            "TPEx 上櫃盤後行情",
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
            f"?date={urllib.parse.quote(tw_date(report_date))}&type=EW&response=json",
        ),
        (
            "TPEx 上櫃盤後行情",
            "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
            f"?l=zh-tw&o=json&d={urllib.parse.quote(tw_date(report_date))}&s=0,asc,0",
        ),
    ]
    for name, url in candidates:
        payload = client.get_json(name, url)
        quotes = _parse_tpex_quotes_payload(payload)
        if quotes:
            return quotes, []
    return [], []


def fetch_market_turnover(client: DataClient, report_date: date, previous_date: date) -> MarketTurnover:
    listed = fetch_twse_listed_turnover(client, report_date)
    otc = fetch_tpex_otc_turnover(client, report_date)
    previous_listed = fetch_twse_listed_turnover(client, previous_date)
    previous_otc = fetch_tpex_otc_turnover(client, previous_date)
    previous_total = None
    if previous_listed is not None and previous_otc is not None:
        previous_total = previous_listed + previous_otc
    return MarketTurnover(
        total_amount=(listed or 0) + (otc or 0) if listed is not None or otc is not None else None,
        listed_amount=listed,
        otc_amount=otc,
        previous_total_amount=previous_total,
        total_source="上市加上櫃成交金額",
        listed_source="TWSE MI_INDEX",
        otc_source="TPEx daily_close_quotes",
    )


def fetch_twse_listed_turnover(client: DataClient, report_date: date) -> float | None:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={yyyymmdd(report_date)}&type=ALLBUT0999&response=json"
    )
    payload = client.get_json("TWSE 上市成交金額彙總", url)
    if not payload or payload.get("stat") != "OK":
        return None
    for table in payload.get("tables", []):
        fields = table.get("fields") or []
        if "成交統計" not in fields or "成交金額(元)" not in fields:
            continue
        for row in table.get("data", []):
            record = dict(zip(fields, row, strict=False))
            if str(record.get("成交統計", "")).startswith("總計"):
                return parse_number(record.get("成交金額(元)"))
    return None


def fetch_tpex_otc_turnover(client: DataClient, report_date: date) -> float | None:
    url = (
        "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
        f"?l=zh-tw&o=json&d={urllib.parse.quote(tw_date(report_date))}&s=0,asc,0"
    )
    payload = client.get_json("TPEx 上櫃成交金額彙總", url)
    if not payload:
        return None
    for table in payload.get("tables", []):
        amount = table.get("totalTradingAmount")
        if amount is not None:
            return parse_number(amount)
    return None


def fetch_twse_institution_summary(client: DataClient, report_date: date) -> InstitutionSummary:
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
        f"?dayDate={yyyymmdd(report_date)}&type=day&response=json"
    )
    payload = client.get_json("TWSE 三大法人買賣金額", url)
    summary = InstitutionSummary()
    if not payload:
        return summary
    if payload.get("stat") != "OK":
        client.note("TWSE 三大法人買賣金額內容", url, "資料待確認", str(payload.get("stat") or "stat not OK"))
        return summary
    if not payload.get("data"):
        client.note("TWSE 三大法人買賣金額內容", url, "尚未公布", "payload data is empty")
        return summary
    for row in payload.get("data", []):
        if len(row) < 4:
            continue
        name = str(row[0])
        amount = parse_number(row[-1])
        if name == "外資及陸資(不含外資自營商)":
            summary.foreign_amount = amount
        elif "投信" in name:
            summary.investment_trust_amount = amount
        elif name in {"自營商(自行買賣)", "自營商(避險)"}:
            summary.dealer_amount = (summary.dealer_amount or 0) + (amount or 0)
        elif "合計" in name:
            summary.total_amount = amount
    if summary.total_amount is None:
        parts = [summary.foreign_amount, summary.investment_trust_amount, summary.dealer_amount]
        summary.total_amount = sum(v for v in parts if v is not None) if any(v is not None for v in parts) else None
    return summary


def fetch_twse_institution_by_stock(client: DataClient, report_date: date) -> list[InstitutionByStock]:
    twse_rows = _fetch_twse_institution_by_stock(client, report_date)
    tpex_rows = _fetch_tpex_institution_by_stock(client, report_date)
    merged = {row.code: row for row in twse_rows}
    merged.update({row.code: row for row in tpex_rows})
    return list(merged.values())


def _fetch_twse_institution_by_stock(client: DataClient, report_date: date) -> list[InstitutionByStock]:
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86"
        f"?date={yyyymmdd(report_date)}&selectType=ALLBUT0999&response=json"
    )
    payload = client.get_json("TWSE 外資投信個股買賣超", url)
    if not payload or payload.get("stat") != "OK":
        return []
    fields = payload.get("fields") or []
    rows: list[InstitutionByStock] = []
    for row in payload.get("data", []):
        record = dict(zip(fields, row, strict=False))
        code = str(record.get("證券代號", "")).strip()
        if not code or not code[0].isdigit():
            continue
        item = InstitutionByStock(
            code=code,
            name=str(record.get("證券名稱", "")).strip(),
            foreign_lots=parse_number(record.get("外陸資買賣超股數(不含外資自營商)")),
            investment_trust_lots=parse_number(record.get("投信買賣超股數")),
            dealer_lots=parse_number(record.get("自營商買賣超股數")),
            total_lots=parse_number(record.get("三大法人買賣超股數")),
            raw=record,
        )
        for attr in ("foreign_lots", "investment_trust_lots", "dealer_lots", "total_lots"):
            setattr(item, attr, lots_from_shares(getattr(item, attr)))
        rows.append(item)
    return rows


def _fetch_tpex_institution_by_stock(client: DataClient, report_date: date) -> list[InstitutionByStock]:
    url = (
        "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
        f"?l=zh-tw&o=json&se=EW&t=D&d={urllib.parse.quote(tw_date(report_date))}"
    )
    payload = client.get_json("TPEx 上櫃三大法人個股買賣超", url)
    if not payload:
        return []
    rows: list[InstitutionByStock] = []
    for table in payload.get("tables", []):
        for row in table.get("data", []):
            if len(row) < 24:
                continue
            code = str(row[0]).strip()
            if not code or not code[0].isdigit():
                continue
            item = InstitutionByStock(
                code=code,
                name=str(row[1]).strip(),
                foreign_lots=lots_from_shares(parse_number(row[10])),
                investment_trust_lots=lots_from_shares(parse_number(row[13])),
                dealer_lots=lots_from_shares(parse_number(row[22])),
                total_lots=lots_from_shares(parse_number(row[23])),
                raw={str(i): value for i, value in enumerate(row)},
            )
            rows.append(item)
    return rows


def fetch_global_markets(client: DataClient) -> list[GlobalMarket]:
    symbols = {
        "道瓊": "^DJI",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "費半": "^SOX",
        "日經225": "^N225",
        "韓國KOSPI": "^KS11",
    }
    markets: list[GlobalMarket] = []
    for name, symbol in symbols.items():
        encoded = urllib.parse.quote(symbol, safe="")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=10d&interval=1d"
        payload = client.get_json(f"國際市場 Yahoo Finance {name}", url)
        market = _parse_yahoo_chart_market(name, payload)
        if market:
            markets.append(market)
    return markets


def _parse_yahoo_chart_market(name: str, payload: dict[str, Any] | None) -> GlobalMarket | None:
    if not payload:
        return None
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return None
    item = result[0]
    meta = item.get("meta") or {}
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    points = [(ts, close) for ts, close in zip(timestamps, closes, strict=False) if close is not None]
    latest_time = parse_int(meta.get("regularMarketTime"))
    latest_price = parse_number(meta.get("regularMarketPrice"))
    latest_date = datetime.fromtimestamp(latest_time, timezone.utc).date() if latest_time else None
    point_date = datetime.fromtimestamp(points[-1][0], timezone.utc).date() if points else None
    if latest_time and latest_price is not None and (not points or (latest_date is not None and point_date is not None and latest_date > point_date)):
        previous = parse_number(points[-1][1]) if points else parse_number(meta.get("chartPreviousClose"))
        change_pct = (latest_price - previous) / previous * 100 if previous not in (None, 0) else None
        source_date = datetime.fromtimestamp(latest_time, timezone.utc).date().isoformat()
        return GlobalMarket(name, latest_price, change_pct, source_date)
    if not points:
        return None
    latest_ts, close = points[-1]
    previous = parse_number(points[-2][1]) if len(points) >= 2 else parse_number(meta.get("chartPreviousClose"))
    change_pct = (float(close) - previous) / previous * 100 if previous not in (None, 0) else None
    source_date = datetime.fromtimestamp(latest_ts, timezone.utc).date().isoformat()
    return GlobalMarket(name, float(close), change_pct, source_date)


def fetch_revenues(client: DataClient, report_date: date) -> list[RevenueRecord]:
    records = _fetch_revenue_month(client, report_date)
    previous_month = _previous_month(report_date)
    previous_records = {r.code: r for r in _fetch_revenue_month(client, previous_month)}
    for record in records:
        previous = previous_records.get(record.code)
        if previous:
            record.previous_cumulative_yoy_pct = previous.cumulative_yoy_pct
    return records


def fetch_quarterly_financials(client: DataClient, year: int, quarter: int) -> list[QuarterlyFinancialRecord]:
    records = _fetch_quarterly_financial_period(client, year, quarter)
    previous_year_records = {r.code: r for r in _fetch_quarterly_financial_period(client, year - 1, quarter)}
    previous_year, previous_quarter = _previous_quarter(year, quarter)
    previous_quarter_records = {r.code: r for r in _fetch_quarterly_financial_period(client, previous_year, previous_quarter)}
    for record in records:
        _attach_quarterly_comparisons(record, previous_year_records.get(record.code), previous_quarter_records.get(record.code))
    return records


def fetch_quarterly_financials_for_codes(
    client: DataClient,
    year: int,
    quarter: int,
    codes: list[str],
) -> list[QuarterlyFinancialRecord]:
    records = _fetch_mopsfin_quarterly_financials(client, year, quarter, codes)
    previous_year_records = {r.code: r for r in _fetch_mopsfin_quarterly_financials(client, year - 1, quarter, codes)}
    previous_year, previous_quarter = _previous_quarter(year, quarter)
    previous_quarter_records = {r.code: r for r in _fetch_mopsfin_quarterly_financials(client, previous_year, previous_quarter, codes)}
    for record in records:
        _attach_quarterly_comparisons(record, previous_year_records.get(record.code), previous_quarter_records.get(record.code))
    return records


def _fetch_mopsfin_quarterly_financials(
    client: DataClient,
    year: int,
    quarter: int,
    codes: list[str],
) -> list[QuarterlyFinancialRecord]:
    clean_codes = [code.strip() for code in codes if code.strip()]
    if not clean_codes:
        return []
    url = "https://mopsfin.twse.com.tw/compare/report"
    records: list[QuarterlyFinancialRecord] = []
    for index in range(0, len(clean_codes), 5):
        chunk = clean_codes[index : index + 5]
        payload = {
            "compareItem": "IncomeStatement",
            "quarter": "true",
            "ylabel": "",
            "ys": f"{year}{quarter}",
            "bcodeAvg": "false",
            "companyAvg": "false",
            "qnumber": "",
            "companyId": chunk,
        }
        text = client.post_text(f"mopsfin 季報綜合損益 {year}Q{quarter} 追蹤清單", url, payload)
        if not text:
            continue
        records.extend(_parse_mopsfin_income_statement_html(text, year, quarter))
    return list({record.code: record for record in records}.values())


def _parse_mopsfin_income_statement_html(text: str, year: int, quarter: int) -> list[QuarterlyFinancialRecord]:
    rows = _TableParser.parse(text)
    account_names: list[str] = []
    company_headers: list[str] = []
    value_columns: list[list[str]] = []
    waiting_for_company_headers = False
    for row in rows:
        if len(row) == 1 and row[0] and row[0] not in {"報表類別", "會計科目"}:
            account_names.append(row[0])
            continue
        if len(row) >= 1 and all(_normalize_header(cell) in {"合併", "個別"} for cell in row):
            waiting_for_company_headers = True
            continue
        if waiting_for_company_headers:
            company_headers = row
            value_columns = [[] for _ in company_headers]
            waiting_for_company_headers = False
            continue
        if company_headers and len(row) >= len(company_headers):
            values = row[-len(company_headers) :]
            for column, value in zip(value_columns, values, strict=False):
                column.append(value)
    records: list[QuarterlyFinancialRecord] = []
    for header, values in zip(company_headers, value_columns, strict=False):
        code, name, market = _parse_mopsfin_company_header(header)
        if not code:
            continue
        record = dict(zip([_normalize_header(name) for name in account_names], values, strict=False))
        item = QuarterlyFinancialRecord(
            code=code,
            name=name,
            market=market,
            year=year,
            quarter=quarter,
            operating_revenue=_number_field(record, "營業收入合計", "營業收入"),
            gross_profit=_number_field(record, "營業毛利毛損淨額", "營業毛利毛損", "營業毛利"),
            operating_income=_number_field(record, "營業利益損失", "營業利益"),
            profit_before_tax=_number_field(record, "稅前淨利淨損", "稅前淨利"),
            net_income=_number_field(record, "本期淨利淨損", "繼續營業單位本期淨利淨損"),
            net_income_attributable=_number_field(record, "本期淨利淨損歸屬於母公司業主", "淨利淨損歸屬於母公司業主"),
            eps=_number_field(record, "基本每股盈餘", "繼續營業單位淨利淨損基本每股盈餘"),
            raw=record,
        )
        _attach_margins(item)
        records.append(item)
    return records


def _fetch_quarterly_financial_period(client: DataClient, year: int, quarter: int) -> list[QuarterlyFinancialRecord]:
    url = "https://mops.twse.com.tw/mops/web/ajax_t163sb04"
    records: list[QuarterlyFinancialRecord] = []
    for market_code, market_name in (("sii", "上市"), ("otc", "上櫃")):
        payload = {
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "off": "1",
            "isQuery": "Y",
            "TYPEK": market_code,
            "year": str(year - 1911),
            "season": f"{quarter:02d}",
        }
        text = client.post_text(f"MOPS 季報綜合損益 {market_name} {year}Q{quarter}", url, payload)
        if not text:
            continue
        records.extend(_parse_quarterly_financial_html(text, year, quarter, market_name))
    return list({record.code: record for record in records}.values())


def _parse_quarterly_financial_html(text: str, year: int, quarter: int, market: str) -> list[QuarterlyFinancialRecord]:
    rows = _TableParser.parse(text)
    records: list[QuarterlyFinancialRecord] = []
    headers: list[str] = []
    for row in rows:
        normalized = [_normalize_header(cell) for cell in row]
        if any(cell == "公司代號" for cell in normalized) and any(cell == "公司名稱" for cell in normalized):
            headers = normalized
            continue
        if not headers or len(row) < 3:
            continue
        code = row[0].strip()
        if not code or not code[0].isdigit():
            continue
        record = dict(zip(headers, row, strict=False))
        item = QuarterlyFinancialRecord(
            code=code,
            name=_field(record, "公司名稱") or row[1].strip(),
            market=market,
            year=year,
            quarter=quarter,
            operating_revenue=_number_field(record, "營業收入", "營業收入合計", "收益", "淨收益"),
            gross_profit=_number_field(record, "營業毛利", "營業毛利毛損", "營業毛利毛損淨額"),
            operating_income=_number_field(record, "營業利益", "營業利益損失", "營業淨利", "營業淨利淨損"),
            profit_before_tax=_number_field(record, "稅前淨利", "稅前淨利淨損", "繼續營業單位稅前淨利淨損"),
            net_income=_number_field(record, "稅後淨利", "本期淨利", "本期淨利淨損", "繼續營業單位本期淨利淨損"),
            net_income_attributable=_number_field(
                record,
                "歸屬母公司業主淨利",
                "淨利歸屬於母公司業主",
                "淨利淨損歸屬於母公司業主",
                "本期淨利淨損歸屬於母公司業主",
            ),
            eps=_number_field(record, "每股盈餘", "基本每股盈餘", "基本每股盈餘元"),
            raw=record,
        )
        _attach_margins(item)
        records.append(item)
    return records


def _fetch_revenue_month(client: DataClient, report_date: date) -> list[RevenueRecord]:
    roc_year = report_date.year - 1911
    month = report_date.month
    records: list[RevenueRecord] = []
    for market in ("sii", "otc"):
        for category in (0, 1):
            url = f"https://mopsc.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{month}_{category}.html"
            text = client.get_text(f"MOPS 月營收 {market} 類別{category}", url, encoding="big5")
            if not text:
                continue
            records.extend(_parse_revenue_html(text, report_date))
    return list({record.code: record for record in records}.values())


def _parse_revenue_html(text: str, report_date: date) -> list[RevenueRecord]:
    rows = _TableParser.parse(text)
    records: list[RevenueRecord] = []
    for row in rows:
        if len(row) < 10 or not row[0].strip().isdigit():
            continue
        records.append(
            RevenueRecord(
                code=row[0].strip(),
                name=row[1].strip(),
                month=f"{report_date.year}-{report_date.month:02d}",
                latest_revenue=parse_number(row[2]),
                mom_pct=parse_number(row[5]),
                yoy_pct=parse_number(row[6]),
                cumulative_yoy_pct=parse_number(row[9]),
                previous_cumulative_yoy_pct=None,
            )
        )
    return records


def fetch_news(client: DataClient, keywords: list[str], limit: int = 24) -> list[NewsItem]:
    feeds = [
        ("Yahoo股市台股動態", "https://tw.stock.yahoo.com/rss?category=tw-market"),
        ("Yahoo股市最新新聞", "https://tw.stock.yahoo.com/rss?category=news"),
        ("Yahoo股市國際市場", "https://tw.stock.yahoo.com/rss?category=international"),
        ("Yahoo股市ETF", "https://tw.stock.yahoo.com/rss?category=ETF"),
        ("中央社財經", "https://feeds.feedburner.com/cnaMoney"),
    ]
    matched: list[NewsItem] = []
    fallback: list[NewsItem] = []
    keyword_set = {k for k in keywords if k}
    seen: set[str] = set()
    per_feed_limit = max(6, limit // 2)
    for source, url in feeds:
        text = client.get_text(f"新聞 RSS {source}", url)
        if not text:
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            client.note(f"新聞 RSS {source}", url, "資料待確認", str(exc))
            continue
        feed_count = 0
        for node in root.findall(".//item"):
            if feed_count >= per_feed_limit:
                break
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            pub_date = (node.findtext("pubDate") or "").strip()
            description = _clean_text(_rss_text(node, "description"))
            if not title or link in seen:
                continue
            seen.add(link)
            item = NewsItem(title=title, source=source, url=link, published=pub_date, description=description)
            if keyword_set and any(keyword in title for keyword in keyword_set):
                matched.append(item)
            else:
                fallback.append(item)
            feed_count += 1
    return (matched + fallback)[:limit]


def fetch_article_bodies(client: DataClient, items: list[NewsItem], limit: int = 24, max_chars: int = 3500) -> list[NewsItem]:
    for item in items[:limit]:
        text = client.get_text(f"新聞內文 {item.source}", item.url, timeout=15)
        if not text:
            fallback = item.description or item.title
            item.content = fallback[:max_chars]
            item.content_status = "使用 RSS 摘要" if item.description else "僅標題"
            continue
        body = extract_article_text(text)
        canonical = _extract_canonical_url(text)
        if body:
            item.content = body[:max_chars]
            item.content_status = "正文 OK"
        elif item.description:
            item.content = item.description[:max_chars]
            item.content_status = "使用 RSS 摘要"
        else:
            item.content = item.title[:max_chars]
            item.content_status = "僅標題"
        if canonical:
            item.canonical_url = canonical
    for item in items[limit:]:
        item.content = (item.description or item.title)[:max_chars]
        item.content_status = "未抓取內文"
    return items


def extract_article_text(html_text: str) -> str:
    candidates: list[str] = []
    candidates.extend(_meta_contents(html_text, ["article:body", "description", "og:description"]))
    for pattern in (
        r"<article\b[^>]*>(.*?)</article>",
        r"<main\b[^>]*>(.*?)</main>",
        r"<div\b[^>]+(?:caas-body|article-body|story_body|article-content|news-content)[^>]*>(.*?)</div>",
    ):
        for match in re.finditer(pattern, html_text, flags=re.IGNORECASE | re.DOTALL):
            candidates.append(_html_to_text(match.group(1)))
    if not candidates:
        candidates.append(_html_to_text(html_text))
    cleaned = [_clean_text(value) for value in candidates if _clean_text(value)]
    cleaned = [value for value in cleaned if len(value) >= 30]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


def _rss_text(node: ET.Element, local_name: str) -> str:
    for child in list(node):
        if child.tag.split("}")[-1] == local_name and child.text:
            return child.text.strip()
    return ""


def _meta_contents(html_text: str, names: list[str]) -> list[str]:
    values: list[str] = []
    wanted = {name.lower() for name in names}
    for match in re.finditer(r"<meta\b[^>]*>", html_text, flags=re.IGNORECASE):
        tag = match.group(0)
        attrs = dict(
            (name.lower(), html.unescape(value))
            for name, value in re.findall(r"""([a-zA-Z_:.-]+)\s*=\s*["']([^"']*)["']""", tag)
        )
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        if key in wanted and attrs.get("content"):
            values.append(attrs["content"])
    return values


def _extract_canonical_url(html_text: str) -> str:
    for match in re.finditer(r"<link\b[^>]*>", html_text, flags=re.IGNORECASE):
        tag = match.group(0)
        attrs = dict(
            (name.lower(), html.unescape(value))
            for name, value in re.findall(r"""([a-zA-Z_:.-]+)\s*=\s*["']([^"']*)["']""", tag)
        )
        if attrs.get("rel", "").lower() == "canonical" and attrs.get("href"):
            return attrs["href"]
    return ""


def _html_to_text(html_text: str) -> str:
    text = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(text)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"\s+", " ", value)
    noise = ("將 Yahoo 加入 Google 優先推薦來源", "將 Yahoo 設為首選來源", "Image:", "Button:")
    for token in noise:
        value = value.replace(token, " ")
    return re.sub(r"\s+", " ", value).strip()


def _signed_change(sign: Any, value: Any) -> float | None:
    number = parse_number(value)
    if number is None:
        return None
    sign_text = str(sign)
    if "-" in sign_text or "跌" in sign_text:
        return -abs(number)
    return number


def _is_socket_permission_denied(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError) and getattr(exc, "winerror", None) == 10013:
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, PermissionError) and getattr(reason, "winerror", None) == 10013:
            return True
        if isinstance(reason, OSError) and getattr(reason, "winerror", None) == 10013:
            return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10013:
        return True
    return False


def _powershell_get_text(url: str, timeout: int = 20) -> str | None:
    # Some environments block outbound sockets for python.exe (WinError 10013),
    # while allowing PowerShell. Use Invoke-WebRequest as a narrow fallback.
    safe_url = url.replace("'", "''")
    safe_ua = USER_AGENT.replace("'", "''")
    ps_script = (
        "$ProgressPreference='SilentlyContinue'\n"
        f"$u = '{safe_url}'\n"
        f"$ua = '{safe_ua}'\n"
        f"$t = {int(timeout)}\n"
        "$r = Invoke-WebRequest -Uri $u -Headers @{ 'User-Agent'=$ua } -UseBasicParsing -TimeoutSec $t\n"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "$r.Content\n"
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 5,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return completed.stdout


def _powershell_post_text(url: str, data: dict[str, Any], timeout: int = 20) -> str | None:
    safe_url = url.replace("'", "''")
    body_parts: list[str] = []
    for key, value in data.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            body_parts.append(f"{urllib.parse.quote_plus(str(key))}={urllib.parse.quote_plus(str(item))}")
    safe_body = "&".join(body_parts).replace("'", "''")
    safe_ua = USER_AGENT.replace("'", "''")
    ps_script = (
        "$ProgressPreference='SilentlyContinue'\n"
        f"$u = '{safe_url}'\n"
        f"$body = '{safe_body}'\n"
        f"$ua = '{safe_ua}'\n"
        f"$t = {int(timeout)}\n"
        "$headers = @{ 'User-Agent'=$ua; 'Content-Type'='application/x-www-form-urlencoded' }\n"
        "$r = Invoke-WebRequest -Uri $u -Method Post -Body $body -Headers $headers -UseBasicParsing -TimeoutSec $t\n"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "$r.Content\n"
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 5,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return completed.stdout


def _parse_tpex_quotes_payload(payload: dict[str, Any] | None) -> list[StockQuote]:
    if not payload:
        return []
    if "tables" in payload:
        rows = payload.get("tables", [{}])[0].get("data") or []
        fields = payload.get("tables", [{}])[0].get("fields") or []
    else:
        rows = payload.get("aaData") or payload.get("data") or []
        fields = payload.get("fields") or []
    quotes: list[StockQuote] = []
    for row in rows:
        if isinstance(row, dict):
            record = row
            values = []
        else:
            values = list(row)
            record = dict(zip(fields, values, strict=False)) if fields else {}
        code = _first_text(record, ["代號", "證券代號"]) or (str(values[0]).strip() if len(values) > 0 else "")
        name = _first_text(record, ["名稱", "證券名稱"]) or (str(values[1]).strip() if len(values) > 1 else "")
        if not code or not code[0].isdigit():
            continue
        close = parse_number(_first_text(record, ["收盤", "收盤價"]) or (values[2] if len(values) > 2 else None))
        change = parse_number(_first_text(record, ["漲跌", "漲跌價差"]) or (values[3] if len(values) > 3 else None))
        previous = close - change if close is not None and change is not None else None
        volume_shares = parse_number(_first_text(record, ["成交股數", "成交股數  "]) or (values[7] if len(values) > 7 else None))
        turnover = parse_number(_first_text(record, ["成交金額(元)", " 成交金額(元)", "成交金額"]) or (values[8] if len(values) > 8 else None))
        quotes.append(
            StockQuote(
                code=code,
                name=name,
                close=close,
                change=change,
                change_pct=pct(change, previous),
                volume_shares=int(volume_shares) if volume_shares is not None else None,
                volume_lots=lots_from_shares(volume_shares),
                turnover=turnover,
                market="上櫃",
                raw=record or {str(i): value for i, value in enumerate(values)},
            )
        )
    return quotes


def _first_text(record: dict[str, Any], keys: list[str]) -> str | None:
    normalized = {key.strip(): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(key.strip())
        if value is not None:
            return str(value).strip()
    return None


def _normalize_header(value: str) -> str:
    text = re.sub(r"\s+", "", value)
    text = text.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    text = text.replace("%", "").replace("％", "").replace("元", "")
    text = text.replace("－", "-").replace("、", "")
    return text


def _field(record: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = record.get(_normalize_header(name))
        if value not in (None, ""):
            return str(value).strip()
    return None


def _number_field(record: dict[str, str], *names: str) -> float | None:
    value = _field(record, *names)
    return parse_number(value)


def _parse_mopsfin_company_header(header: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", header.replace("\xa0", " ")).strip()
    match = re.match(r"(?P<code>\d{4,6})\s+(?P<name>[^()]+)(?:\((?P<detail>[^)]+)\))?", text)
    if not match:
        return "", text, ""
    detail = match.group("detail") or ""
    market = "上市" if "上市" in detail else ("上櫃" if "上櫃" in detail else "")
    return match.group("code"), match.group("name").strip(), market


def _attach_margins(record: QuarterlyFinancialRecord) -> None:
    revenue = record.operating_revenue
    if revenue in (None, 0):
        return
    if record.gross_profit is not None:
        record.gross_margin_pct = record.gross_profit / revenue * 100
    if record.operating_income is not None:
        record.operating_margin_pct = record.operating_income / revenue * 100
    net_income = record.net_income_attributable if record.net_income_attributable is not None else record.net_income
    if net_income is not None:
        record.net_margin_pct = net_income / revenue * 100


def _attach_quarterly_comparisons(
    record: QuarterlyFinancialRecord,
    previous_year: QuarterlyFinancialRecord | None,
    previous_quarter: QuarterlyFinancialRecord | None,
) -> None:
    if previous_year:
        record.revenue_yoy_pct = _growth_pct(record.operating_revenue, previous_year.operating_revenue)
        record.operating_income_yoy_pct = _growth_pct(record.operating_income, previous_year.operating_income)
        record.net_income_yoy_pct = _growth_pct(_net_income_for_growth(record), _net_income_for_growth(previous_year))
        if record.gross_margin_pct is not None and previous_year.gross_margin_pct is not None:
            record.gross_margin_yoy_diff = record.gross_margin_pct - previous_year.gross_margin_pct
    if previous_quarter:
        record.revenue_qoq_pct = _growth_pct(record.operating_revenue, previous_quarter.operating_revenue)
        record.operating_income_qoq_pct = _growth_pct(record.operating_income, previous_quarter.operating_income)
        record.net_income_qoq_pct = _growth_pct(_net_income_for_growth(record), _net_income_for_growth(previous_quarter))
        if record.gross_margin_pct is not None and previous_quarter.gross_margin_pct is not None:
            record.gross_margin_qoq_diff = record.gross_margin_pct - previous_quarter.gross_margin_pct


def _net_income_for_growth(record: QuarterlyFinancialRecord) -> float | None:
    return record.net_income_attributable if record.net_income_attributable is not None else record.net_income


def _growth_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def _previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    if quarter <= 1:
        return year - 1, 4
    return year, quarter - 1


def _previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    @classmethod
    def parse(cls, text: str) -> list[list[str]]:
        parser = cls()
        parser.feed(text)
        return parser.rows

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._current_row = []
        elif tag.lower() in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            value = html.unescape("".join(self._current_cell))
            value = re.sub(r"\s+", " ", value).strip()
            self._current_row.append(value)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None
