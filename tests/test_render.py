from __future__ import annotations

import unittest
from datetime import date

from stock_report.models import InstitutionSummary, MarketTurnover, NewsDigest, QuarterlyFinancialRecord, RevenueRecord
from stock_report.render import markdown_to_html, render_monthly_revenue_report, render_report, render_season_report


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

    def test_renders_season_report_with_watchlist_and_financial_units(self) -> None:
        rows = [
            QuarterlyFinancialRecord(
                "2330",
                "台積電",
                "上市",
                2026,
                1,
                operating_revenue=839_254_000,
                gross_profit=496_157_000,
                operating_income=410_366_000,
                net_income_attributable=361_560_000,
                eps=13.94,
                gross_margin_pct=59.12,
                revenue_yoy_pct=41.6,
                net_income_yoy_pct=60.3,
                gross_margin_yoy_diff=5.1,
            )
        ]
        markdown = render_season_report(
            year=2026,
            quarter=1,
            watchlist_codes=["2330", "2454"],
            records=rows,
            featured=rows,
            eps_rank=rows,
            net_income_growth_rank=rows,
            gross_margin_improvement_rank=rows,
            revenue_growth_rank=rows,
            sources=[],
        )

        self.assertIn("季報追蹤報告 2026 Q1", markdown)
        self.assertIn("金額以億元列示", markdown)
        self.assertIn("8,392.54 億元", markdown)
        self.assertIn("13.94", markdown)
        self.assertIn("2454", markdown)
        self.assertIn("資料待確認", markdown)

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

    def test_table_cells_allow_long_text_to_wrap(self) -> None:
        html = markdown_to_html(
            "\n".join(
                [
                    "# Report",
                    "",
                    "| Code | Name | Topic | AI Summary | Source |",
                    "| --- | --- | --- | --- | --- |",
                    "| 2330 | TSMC | Topic | Long summary text | [Source](https://example.test/a-very-long-url) |",
                ]
            )
        )

        self.assertIn("overflow-wrap:anywhere", html)
        self.assertIn("td:first-child, td:nth-child(2), td:nth-child(3)", html)

    def test_table_cells_mark_directional_numbers(self) -> None:
        html = markdown_to_html(
            "\n".join(
                [
                    "# Report",
                    "",
                    "| Code | Change | Flow | Volume | Source |",
                    "| --- | --- | --- | --- | --- |",
                    "| 2330 | 4.00 | -100 張 | 1,000 張 | [Source](https://example.test) |",
                    "| 2454 | -1.23% | +50 張 | 2,000 張 | Plain text |",
                ]
            )
        )

        self.assertIn('<td>2330</td>', html)
        self.assertIn('<td class="num-up">4.00</td>', html)
        self.assertIn('<td class="num-down">-100 張</td>', html)
        self.assertIn('<td class="num-down">-1.23%</td>', html)
        self.assertIn('<td class="num-up">+50 張</td>', html)
        self.assertIn('<td>1,000 張</td>', html)
        self.assertIn('<a href="https://example.test">Source</a>', html)


if __name__ == "__main__":
    unittest.main()
