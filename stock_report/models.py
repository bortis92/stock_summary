from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SourceNote:
    name: str
    url: str
    status: str
    fetched_at: datetime
    detail: str = ""


@dataclass
class StockQuote:
    code: str
    name: str
    close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume_shares: int | None = None
    volume_lots: float | None = None
    turnover: float | None = None
    market: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstitutionByStock:
    code: str
    name: str
    foreign_lots: float | None = None
    investment_trust_lots: float | None = None
    dealer_lots: float | None = None
    total_lots: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstitutionSummary:
    foreign_amount: float | None = None
    investment_trust_amount: float | None = None
    dealer_amount: float | None = None
    total_amount: float | None = None


@dataclass
class MarketTurnover:
    total_amount: float | None = None
    listed_amount: float | None = None
    otc_amount: float | None = None
    previous_total_amount: float | None = None
    total_source: str = ""
    listed_source: str = ""
    otc_source: str = ""


@dataclass
class IndexSummary:
    name: str
    close: float | None = None
    change: float | None = None
    change_pct: float | None = None


@dataclass
class RevenueRecord:
    code: str
    name: str
    month: str
    latest_revenue: float | None = None
    mom_pct: float | None = None
    yoy_pct: float | None = None
    cumulative_yoy_pct: float | None = None
    previous_cumulative_yoy_pct: float | None = None


@dataclass
class GlobalMarket:
    name: str
    close: float | None
    change_pct: float | None
    source_date: str


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published: str = ""
    description: str = ""
    content: str = ""
    content_status: str = ""
    canonical_url: str = ""
    matched_codes: list[str] = field(default_factory=list)
    topic: str = ""
    ai_summary: str = ""


@dataclass
class StockNewsSummary:
    code: str
    name: str
    topic: str
    summary: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class NewsDigest:
    market_bullets: list[str] = field(default_factory=list)
    stock_summaries: list[StockNewsSummary] = field(default_factory=list)
    other_news: list[NewsItem] = field(default_factory=list)
    status: str = ""
