from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from stock_report.ai import _is_market_news, _summary_items, summarize_news
from stock_report.models import NewsItem, StockQuote


class AiSummaryTest(unittest.TestCase):
    def test_fallback_without_provider_keeps_news_links(self) -> None:
        with patch.dict(os.environ, {"AI_SUMMARY_PROVIDER": "none"}, clear=False):
            news = [NewsItem("台股下跌 3 大法人賣超", "測試來源", "https://example.com/a")]
            digest = summarize_news(news, [])
        self.assertIn("AI 摘要未啟用", digest.status)
        self.assertEqual(digest.other_news, news)

    def test_matches_stock_code_and_name_before_ai_call(self) -> None:
        with patch.dict(os.environ, {"AI_SUMMARY_PROVIDER": "none"}, clear=False):
            news = [NewsItem("台積電龍科三期供電議題", "測試來源", "https://example.com/a", content="台積電持續評估設廠。")]
            summarize_news(news, [StockQuote("2330", "台積電")])
        self.assertEqual(news[0].matched_codes, ["2330"])

    def test_summary_items_keep_market_and_watchlist_only(self) -> None:
        market = NewsItem("台股下跌 3 大法人賣超", "測試來源", "https://example.com/market")
        watched = NewsItem("台積電龍科三期供電議題", "測試來源", "https://example.com/2330")
        watched.matched_codes = ["2330"]
        not_watched = NewsItem("南寶首季獲利成長", "測試來源", "https://example.com/other")
        not_watched.matched_codes = ["4766"]
        unrelated = NewsItem("AI 助手導入教育場域", "測試來源", "https://example.com/ai")
        self.assertTrue(_is_market_news(market))
        self.assertFalse(_is_market_news(unrelated))
        self.assertEqual(_summary_items([market, watched, not_watched, unrelated], ["2330"]), [watched, market])


if __name__ == "__main__":
    unittest.main()
