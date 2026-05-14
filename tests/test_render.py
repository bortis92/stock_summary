from __future__ import annotations

import unittest
from datetime import date

from stock_report.models import InstitutionSummary, MarketTurnover, NewsDigest, RevenueRecord
from stock_report.render import markdown_to_html, render_monthly_revenue_report, render_report


class RenderTest(unittest.TestCase):
    def test_renders_no_watchlist_and_non_trading_day(self) -> None:
        markdown = render_report(
            report_date=date(2026, 5, 10),
            is_trading_day=False,
            indices=[],
            quotes=[],
            previous_quotes=[],
            market_turnover=MarketTurnover(),
            institution_summary=InstitutionSummary(),
            institution_rows=[],
            global_markets=[],
            news=[],
            news_digest=NewsDigest(),
            turnover_top=[],
            gainers=[],
            losers=[],
            abnormal=[],
            watchlist_codes=[],
            revenue_records=[],
            revenue_screen=None,
            sources=[],
            warnings=["測試警示"],
        )
        self.assertIn("今日台股休市", markdown)
        self.assertIn("尚未設定追蹤個股", markdown)
        self.assertNotIn("月營收篩選", markdown)

    def test_renders_monthly_revenue_report_in_100m_units(self) -> None:
        rows = [
            RevenueRecord(
                "2330",
                "台積電",
                "2026-04",
                latest_revenue=410_725_118,
                mom_pct=-1.07,
                yoy_pct=17.49,
                cumulative_yoy_pct=29.94,
            )
        ]
        markdown = render_monthly_revenue_report(
            revenue_month=date(2026, 4, 1),
            watchlist_codes=["2330"],
            revenue_records=rows,
            revenue_screen=rows,
            sources=[],
        )
        self.assertIn("最新月營收（億元）", markdown)
        self.assertIn("4,107.25 億元", markdown)

    def test_converts_markdown_report_to_html(self) -> None:
        html = markdown_to_html(
            "\n".join(
                [
                    "# 測試報告",
                    "",
                    "> 摘要",
                    "",
                    "| 代號 | 名稱 |",
                    "| --- | --- |",
                    "| 2330 | 台積電 |",
                    "",
                    "- 來源：https://example.test/report",
                ]
            )
        )

        self.assertIn("<!doctype html>", html)
        self.assertIn("<title>測試報告</title>", html)
        self.assertIn("<table>", html)
        self.assertIn('<a href="https://example.test/report">https://example.test/report</a>', html)


if __name__ == "__main__":
    unittest.main()
