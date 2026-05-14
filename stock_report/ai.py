from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .models import NewsDigest, NewsItem, StockNewsSummary, StockQuote


MARKET_KEYWORDS = (
    "台股",
    "大盤",
    "加權",
    "櫃買",
    "三大法人",
    "外資",
    "投信",
    "自營商",
    "美股",
    "費半",
    "Nasdaq",
    "那斯達克",
    "道瓊",
    "標普",
    "S&P",
    "日經",
    "韓股",
    "KOSPI",
    "港股",
    "恆生",
    "陸股",
    "上證",
    "深證",
    "ADR",
)


def summarize_news(items: list[NewsItem], quotes: list[StockQuote], watchlist_codes: list[str] | None = None) -> NewsDigest:
    _match_stock_codes(items, quotes)
    selected_items = _summary_items(items, watchlist_codes or [])
    provider = _provider()
    if provider == "none":
        return _fallback_digest(items, "AI 摘要未啟用；已保留新聞連結與可抓取內文狀態。", watchlist_codes or [])

    prompt = _build_prompt(selected_items, quotes, watchlist_codes or [])
    try:
        if provider == "gemini":
            data = _call_gemini(prompt)
        elif provider == "ollama":
            data = _call_ollama(prompt)
        elif provider == "openrouter":
            data = _call_openrouter(prompt)
        else:
            return _fallback_digest(items, f"未知 AI provider：{provider}", watchlist_codes or [])
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return _fallback_digest(items, f"AI 摘要不可用：{exc}", watchlist_codes or [])

    return _digest_from_payload(data, selected_items, items, watchlist_codes or [])


def _provider() -> str:
    configured = os.getenv("AI_SUMMARY_PROVIDER", "").strip().lower()
    if configured:
        return configured
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "none"


def _match_stock_codes(items: list[NewsItem], quotes: list[StockQuote]) -> None:
    quote_pairs = [(q.code, q.name) for q in quotes if q.code and q.name]
    for item in items:
        text = f"{item.title} {item.description} {item.content}"
        item.matched_codes = [code for code, name in quote_pairs if code in text or name in text]


def _summary_items(items: list[NewsItem], watchlist_codes: list[str]) -> list[NewsItem]:
    watchlist = set(watchlist_codes)
    stock_items = [item for item in items if watchlist and any(code in watchlist for code in item.matched_codes)]
    market_items = [item for item in items if _is_market_news(item)]
    ordered: list[NewsItem] = []
    seen: set[str] = set()
    for item in stock_items + market_items:
        key = item.canonical_url or item.url
        if key in seen:
            continue
        ordered.append(item)
        seen.add(key)
    return ordered


def _is_market_news(item: NewsItem) -> bool:
    text = f"{item.title} {item.description} {item.content}"
    return any(keyword in text for keyword in MARKET_KEYWORDS)


def _build_prompt(items: list[NewsItem], quotes: list[StockQuote], watchlist_codes: list[str]) -> str:
    quote_names = {q.code: q.name for q in quotes}
    watchlist = set(watchlist_codes)
    articles = []
    max_items = _env_int("AI_MAX_NEWS_ITEMS", 30)
    max_chars = _env_int("AI_MAX_CHARS_PER_ARTICLE", 1500)
    for index, item in enumerate(items[:max_items], 1):
        matched_watchlist_codes = [code for code in item.matched_codes if code in watchlist]
        articles.append(
            {
                "id": str(index),
                "title": item.title,
                "source": item.source,
                "published": item.published,
                "url": item.url,
                "category": "watchlist_stock" if matched_watchlist_codes else "market",
                "matched_codes": matched_watchlist_codes,
                "matched_names": [quote_names.get(code, "") for code in matched_watchlist_codes],
                "content_status": item.content_status,
                "content": (item.content or item.description or item.title)[:max_chars],
            }
        )
    return (
        "你是台灣股市盤後報告編輯。請只根據輸入新聞內容整理，不要補充外部知識，不要提供買賣建議。\n"
        "請輸出 JSON，不要 markdown，不要解釋。格式：\n"
        '{"market_bullets":["..."],"stock_summaries":[{"code":"2330","name":"台積電","topic":"...","summary":"...","source_ids":["1","2"]}],"other_ids":["3"]}\n'
        "規則：只有 category=market 且內容明確和台股、大盤、法人、美股或國際股市/指數有關，才能放 market_bullets；一般科技、AI應用、政治、生活或非股市新聞不可放入 market_bullets。\n"
        "只有 category=watchlist_stock 且 matched_codes 非空，才能放 stock_summaries；不得自行加入未在 matched_codes 的股票，也不得摘要非追蹤個股新聞。\n"
        "同一追蹤股票同主題新聞請合併，盡可能涵蓋所有有新聞的追蹤個股。摘要使用繁體中文且每則 35-70 字。\n"
        f"新聞資料：{json.dumps(articles, ensure_ascii=False)}"
    )


def _call_gemini(prompt: str) -> dict[str, Any]:
    key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("AI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    response = _post_json(url, payload)
    text = response["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json_text(text)


def _call_ollama(prompt: str) -> dict[str, Any]:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("AI_MODEL", "qwen3:4b")
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json"}
    response = _post_json(f"{host}/api/chat", payload)
    return _parse_json_text(response["message"]["content"])


def _call_openrouter(prompt: str) -> dict[str, Any]:
    key = os.environ["OPENROUTER_API_KEY"]
    model = os.getenv("AI_MODEL", "openrouter/free")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    response = _post_json("https://openrouter.ai/api/v1/chat/completions", payload, headers={"Authorization": f"Bearer {key}"})
    return _parse_json_text(response["choices"][0]["message"]["content"])


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", "User-Agent": "TaiwanStockReport/1.0"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=_env_int("AI_REQUEST_TIMEOUT", 360)) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_json_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("AI 回傳不是 JSON")
        text = match.group(0)
    return json.loads(text)


def _digest_from_payload(payload: dict[str, Any], prompt_items: list[NewsItem], all_items: list[NewsItem], watchlist_codes: list[str]) -> NewsDigest:
    by_id = {str(index): item for index, item in enumerate(prompt_items, 1)}
    watchlist = set(watchlist_codes)
    stock_summaries: list[StockNewsSummary] = []
    used_urls: set[str] = set()
    for row in payload.get("stock_summaries") or []:
        code = str(row.get("code", "")).strip()
        if watchlist and code not in watchlist:
            continue
        source_ids = [str(value) for value in row.get("source_ids", [])]
        urls = [by_id[source_id].url for source_id in source_ids if source_id in by_id][:3]
        source_items = [by_id[source_id] for source_id in source_ids if source_id in by_id]
        if watchlist and not any(code in item.matched_codes for item in source_items):
            continue
        used_urls.update(urls)
        stock_summaries.append(
            StockNewsSummary(
                code=code,
                name=str(row.get("name", "")).strip(),
                topic=str(row.get("topic", "")).strip(),
                summary=str(row.get("summary", "")).strip(),
                source_urls=urls,
            )
        )
    market_bullets = [str(value).strip() for value in payload.get("market_bullets", []) if str(value).strip()]
    other_news = [item for item in all_items if item.url not in used_urls]
    return NewsDigest(
        market_bullets=market_bullets,
        stock_summaries=[row for row in stock_summaries if row.summary],
        other_news=other_news,
        status="AI 摘要 OK",
    )


def _fallback_digest(items: list[NewsItem], status: str, watchlist_codes: list[str]) -> NewsDigest:
    return NewsDigest(
        market_bullets=[],
        stock_summaries=[],
        other_news=items,
        status=status if items else "",
    )
