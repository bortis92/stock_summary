from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from stock_report.pipeline import build_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Taiwan stock after-market report.")
    parser.add_argument(
        "--date", help="Report date in YYYY-MM-DD. Defaults to today in local timezone.")
    parser.add_argument("--output-dir", default="reports",
                        help="Directory for Markdown reports.")
    parser.add_argument("--watchlist", default="./watchlist/watchlist.txt",
                        help="Path to watchlist text file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_date = date.fromisoformat(args.date) if args.date else date.today()
    output = build_report(
        report_date=report_date,
        output_dir=Path(args.output_dir),
        watchlist_path=Path(args.watchlist),
    )
    print(output)


if __name__ == "__main__":
    main()
