from __future__ import annotations

import unittest

from stock_report.analysis import abnormal_volume_price, institution_rank, revenue_growth_filter
from stock_report.models import InstitutionByStock, RevenueRecord, StockQuote


class AnalysisTest(unittest.TestCase):
    def test_abnormal_volume_price_requires_ratio_volume_and_gain(self) -> None:
        today = [
            StockQuote("2330", "台積電", close=100, change_pct=4.0, volume_lots=3001),
            StockQuote("2454", "聯發科", close=100, change_pct=2.0, volume_lots=9000),
        ]
        previous = [
            StockQuote("2330", "台積電", volume_lots=1000),
            StockQuote("2454", "聯發科", volume_lots=1000),
        ]
        result = abnormal_volume_price(today, previous)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].code, "2330")
        self.assertAlmostEqual(result[0][1], 3.001)

    def test_institution_rank_sorts_buy_and_sell(self) -> None:
        rows = [
            InstitutionByStock("1", "A", foreign_lots=10),
            InstitutionByStock("2", "B", foreign_lots=-20),
            InstitutionByStock("3", "C", foreign_lots=30),
        ]
        self.assertEqual([r.code for r in institution_rank(rows, "foreign_lots", 2, True)], ["3", "1"])
        self.assertEqual([r.code for r in institution_rank(rows, "foreign_lots", 2, False)], ["2", "1"])

    def test_revenue_growth_filter(self) -> None:
        rows = [
            RevenueRecord("1", "A", "2026-04", latest_revenue=200_000, yoy_pct=29),
            RevenueRecord("2", "B", "2026-04", latest_revenue=99_999, yoy_pct=30),
            RevenueRecord("3", "C", "2026-04", latest_revenue=100_000, yoy_pct=60),
            RevenueRecord("4", "D", "2026-04", latest_revenue=300_000, yoy_pct=30),
        ]
        self.assertEqual([r.code for r in revenue_growth_filter(rows)], ["3", "4"])


if __name__ == "__main__":
    unittest.main()
