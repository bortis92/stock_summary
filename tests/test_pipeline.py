from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_report.models import RevenueRecord
from stock_report.pipeline import _write_monthly_revenue_report, rotate_daily_reports, write_report_index


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

    def test_report_index_contains_fixed_entry_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = write_report_index(Path(tmp))
            html = output_path.read_text(encoding="utf-8")

        for href in ["daily_0.html", "daily_1.html", "daily_2.html", "month.html", "season.html"]:
            self.assertIn(f'href="{href}"', html)
        for label in ["最新日報", "前一份日報", "前二份日報", "最新月營收報告", "最新季報"]:
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
