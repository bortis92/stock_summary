from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError

from stock_report.fetchers import (
    DataClient,
    _parse_mopsfin_income_statement_html,
    _parse_quarterly_financial_html,
    _parse_yahoo_chart_market,
    extract_article_text,
    fetch_quarterly_financials,
    fetch_twse_institution_summary,
)


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


class FakePostClient:
    sources = []

    def post_text(self, name: str, url: str, data: dict[str, str]):
        if data["TYPEK"] != "sii":
            return ""
        values = {
            ("115", "01"): (200_000, 80_000, 40_000, 20_000),
            ("114", "01"): (100_000, 30_000, 10_000, 5_000),
            ("114", "04"): (160_000, 48_000, 20_000, 10_000),
        }
        row = values.get((data["year"], data["season"]))
        if not row:
            return ""
        revenue, gross, operating, net_income = row
        return f"""
        <table>
          <tr><th>公司代號</th><th>公司名稱</th><th>營業收入</th><th>營業毛利（毛損）</th><th>營業利益（損失）</th><th>本期淨利（淨損）</th><th>基本每股盈餘（元）</th></tr>
          <tr><td>2330</td><td>台積電</td><td>{revenue}</td><td>{gross}</td><td>{operating}</td><td>{net_income}</td><td>1.00</td></tr>
        </table>
        """


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

    def test_parse_quarterly_financial_html_extracts_core_income_statement_fields(self) -> None:
        html = """
        <table>
          <tr>
            <th>公司代號</th><th>公司名稱</th><th>營業收入</th><th>營業毛利（毛損）</th>
            <th>營業利益（損失）</th><th>稅前淨利（淨損）</th>
            <th>本期淨利（淨損）</th><th>淨利（淨損）歸屬於母公司業主</th><th>基本每股盈餘（元）</th>
          </tr>
          <tr>
            <td>2330</td><td>台積電</td><td>839,254,000</td><td>496,157,000</td>
            <td>410,366,000</td><td>422,301,000</td><td>361,560,000</td><td>361,560,000</td><td>13.94</td>
          </tr>
          <tr>
            <td>9999</td><td>缺欄公司</td><td>100,000</td><td></td><td></td><td></td><td></td><td></td><td></td>
          </tr>
        </table>
        """
        rows = _parse_quarterly_financial_html(html, 2026, 1, "上市")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].code, "2330")
        self.assertEqual(rows[0].name, "台積電")
        self.assertEqual(rows[0].operating_revenue, 839_254_000)
        self.assertEqual(rows[0].gross_profit, 496_157_000)
        self.assertEqual(rows[0].operating_income, 410_366_000)
        self.assertEqual(rows[0].profit_before_tax, 422_301_000)
        self.assertEqual(rows[0].net_income_attributable, 361_560_000)
        self.assertEqual(rows[0].eps, 13.94)
        self.assertAlmostEqual(rows[0].gross_margin_pct or 0, 59.1188, places=3)
        self.assertIsNone(rows[1].eps)

    def test_fetch_quarterly_financials_adds_yoy_and_qoq_comparisons(self) -> None:
        rows = fetch_quarterly_financials(FakePostClient(), 2026, 1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].revenue_yoy_pct, 100)
        self.assertEqual(rows[0].operating_income_yoy_pct, 300)
        self.assertEqual(rows[0].net_income_yoy_pct, 300)
        self.assertEqual(rows[0].revenue_qoq_pct, 25)
        self.assertEqual(rows[0].operating_income_qoq_pct, 100)
        self.assertEqual(rows[0].net_income_qoq_pct, 100)
        self.assertEqual(rows[0].gross_margin_yoy_diff, 10)
        self.assertEqual(rows[0].gross_margin_qoq_diff, 10)

    def test_parse_mopsfin_income_statement_html_extracts_company_columns(self) -> None:
        html = """
        <table><tbody>
          <tr><td>營業收入合計</td></tr>
          <tr><td>營業毛利（毛損）淨額</td></tr>
          <tr><td>營業利益（損失）</td></tr>
          <tr><td>稅前淨利（淨損）</td></tr>
          <tr><td>本期淨利（淨損）</td></tr>
          <tr><td>基本每股盈餘</td></tr>
        </tbody></table>
        <table>
          <tr><th>合併</th><th>合併</th></tr>
          <tr><th>2330&nbsp;台積電<br/>(上市半導體業)</th><th>2454&nbsp;聯發科<br/>(上市半導體業)</th></tr>
          <tr><td>621,295,550</td><td>142,000,000</td></tr>
          <tr><td>325,400,299</td><td>66,000,000</td></tr>
          <tr><td>268,545,816</td><td>45,000,000</td></tr>
          <tr><td>237,955,407</td><td>40,000,000</td></tr>
          <tr><td>237,955,407</td><td>40,000,000</td></tr>
          <tr><td>9.17</td><td>12.50</td></tr>
        </table>
        """
        rows = _parse_mopsfin_income_statement_html(html, 2026, 1)

        self.assertEqual([r.code for r in rows], ["2330", "2454"])
        self.assertEqual(rows[0].name, "台積電")
        self.assertEqual(rows[0].market, "上市")
        self.assertEqual(rows[0].operating_revenue, 621_295_550)
        self.assertEqual(rows[0].gross_profit, 325_400_299)
        self.assertEqual(rows[0].operating_income, 268_545_816)
        self.assertEqual(rows[0].net_income, 237_955_407)
        self.assertEqual(rows[0].eps, 9.17)


if __name__ == "__main__":
    unittest.main()
