from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError

from stock_report.fetchers import DataClient, _parse_yahoo_chart_market, extract_article_text, fetch_twse_institution_summary


class FakeHeaders:
    def get_content_charset(self) -> str | None:
        return None


class FakeResponse:
    headers = FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return "ok".encode("utf-8")


class FakeClient:
    sources = []

    def get_json(self, name: str, url: str):
        return {
            "stat": "OK",
            "data": [
                ["外資及陸資(不含外資自營商)", "1", "2", "-12,085,000,000"],
                ["外資自營商", "1", "2", "999,000,000"],
                ["投信", "1", "2", "1,957,000,000"],
                ["自營商(自行買賣)", "1", "2", "-2,619,000,000"],
                ["自營商(避險)", "1", "2", "-7,418,000,000"],
                ["合計", "1", "2", "-20,164,000,000"],
            ],
        }


class FetchersTest(unittest.TestCase):
    def test_foreign_summary_uses_exact_non_dealer_row(self) -> None:
        summary = fetch_twse_institution_summary(FakeClient(), date(2026, 5, 8))
        self.assertEqual(summary.foreign_amount, -12_085_000_000)
        self.assertEqual(summary.investment_trust_amount, 1_957_000_000)
        self.assertEqual(summary.dealer_amount, -10_037_000_000)
        self.assertEqual(summary.total_amount, -20_164_000_000)

    def test_yahoo_market_uses_daily_points_when_regular_time_is_same_date(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 110,
                            "regularMarketTime": 1778654703,
                        },
                        "timestamp": [1778544000, 1778630400],
                        "indicators": {"quote": [{"close": [100, 110]}]},
                    }
                ]
            }
        }
        market = _parse_yahoo_chart_market("TEST", payload)
        self.assertIsNotNone(market)
        self.assertAlmostEqual(market.change_pct, 10.0)

    def test_extract_article_text_removes_scripts_and_keeps_body(self) -> None:
        text = extract_article_text(
            """
            <html><head><script>bad()</script></head>
            <body><article><p>台積電今日說明龍科三期供電議題，台電表示會配合產業需求。</p>
            <p>相關規劃包含評估大潭電廠機組更新或新建機組，供電時程仍待正式計畫確認。</p></article></body></html>
            """
        )
        self.assertIn("台積電今日說明", text)
        self.assertIn("供電時程仍待正式計畫確認", text)
        self.assertNotIn("bad()", text)

    def test_get_text_retries_transient_http_errors(self) -> None:
        transient = HTTPError("https://example.test", 502, "Bad Gateway", {}, None)
        with patch("stock_report.fetchers.urllib.request.urlopen", side_effect=[transient, FakeResponse()]) as urlopen:
            with patch("stock_report.fetchers.time.sleep"):
                client = DataClient()
                text = client.get_text("test source", "https://example.test")

        self.assertEqual(text, "ok")
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(client.sources[-1].status, "OK")
        self.assertEqual(client.sources[-1].detail, "retried 1 time(s)")


if __name__ == "__main__":
    unittest.main()
