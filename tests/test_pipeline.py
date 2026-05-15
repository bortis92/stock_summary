from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_report.models import QuarterlyFinancialRecord, RevenueRecord
from stock_report.pipeline import _season_report_period_for_date, _write_monthly_revenue_report, _write_season_report, rotate_daily_reports, write_report_index


class PipelineOutputTest(unittest.TestCase):
    def test_rotates_daily_reports_and_keeps_three_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for index, content in enumerate(["oldest", "older", "old"]):
                rotate_daily_reports(output_dir)
                (output_dir / "daily_0.html").write_text(content, encoding="utf-8")

            self.assertEqual((output_dir / "daily_0.html").read_text(encoding="utf-8"), "old")
            self.assertEqual((output_dir / "daily_1.html").read_text(encoding="utf-8"), "older")
            self.assertEqual((output_dir / "daily_2.html").read_text(encoding="utf-8"), "oldest")

            rotate_daily_reports(output_dir)
            (output_dir / "daily_0.html").write_text("new", encoding="utf-8")

            self.assertEqual((output_dir / "daily_0.html").read_text(encoding="utf-8"), "new")
            self.assertEqual((output_dir / "daily_1.html").read_text(encoding="utf-8"), "old")
            self.assertEqual((output_dir / "daily_2.html").read_text(encoding="utf-8"), "older")
            self.assertEqual(sorted(path.name for path in output_dir.glob("daily_*.html")), ["daily_0.html", "daily_1.html", "daily_2.html"])

    def test_monthly_report_writes_fixed_month_file(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch("stock_report.pipeline.fetch_revenues", return_value=rows):
                output_path = _write_monthly_revenue_report(date(2026, 5, 8), output_dir, ["2330"])

            self.assertEqual(output_path.name, "month.html")
            self.assertTrue((output_dir / "month.html").exists())
            self.assertFalse(any(output_dir.glob("*-month.html")))
            self.assertIn("月營收追蹤報告 2026-04", output_path.read_text(encoding="utf-8"))

    def test_season_report_writes_fixed_season_file(self) -> None:
        rows = [
            QuarterlyFinancialRecord(
                "2330",
                "台積電",
                "上市",
                2026,
                1,
                operating_revenue=839_254_000,
                operating_income=410_366_000,
                net_income_attributable=361_560_000,
                eps=13.94,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch("stock_report.pipeline.fetch_quarterly_financials", return_value=rows):
                output_path = _write_season_report(2026, 1, output_dir, ["2330"])

            self.assertEqual(output_path.name, "season.html")
            self.assertTrue((output_dir / "season.html").exists())
            self.assertFalse(any(output_dir.glob("*-season.html")))
            self.assertIn("季報追蹤報告 2026 Q1", output_path.read_text(encoding="utf-8"))

    def test_season_report_window_maps_to_latest_reporting_period(self) -> None:
        self.assertEqual(_season_report_period_for_date(date(2026, 3, 20)), (2025, 4))
        self.assertEqual(_season_report_period_for_date(date(2026, 5, 15)), (2026, 1))
        self.assertEqual(_season_report_period_for_date(date(2026, 8, 14)), (2026, 2))
        self.assertEqual(_season_report_period_for_date(date(2026, 11, 14)), (2026, 3))
        self.assertIsNone(_season_report_period_for_date(date(2026, 7, 1)))

    def test_report_index_contains_fixed_entry_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site_root = Path(tmp)
            output_path = write_report_index(site_root / "reports")
            html = output_path.read_text(encoding="utf-8")

        self.assertEqual(output_path, site_root / "index.html")
        for href in ["reports/daily_0.html", "reports/daily_1.html", "reports/daily_2.html", "reports/month.html", "reports/season.html"]:
            self.assertIn(f'href="{href}"', html)
        for label in ["最新日報", "前一份日報", "前二份日報", "最新月營收報告", "最新季報"]:
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
