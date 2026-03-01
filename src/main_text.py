"""CLI entry for Telegram ABSENSI text parsing."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.absensi_text.export import export_details_csv, export_report_json, export_summary_csv
from src.absensi_text.parser import parse_attendance_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Telegram ABSENSI text and export JSON/CSV")
    parser.add_argument("--input_text_file", required=True, help="Path to raw text report file")
    parser.add_argument(
        "--output_dir",
        default="data/processed",
        help="Directory for generated JSON/CSV files (default: data/processed)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_path = Path(args.input_text_file)
    output_dir = Path(args.output_dir)
    raw_text = input_path.read_text(encoding="utf-8")

    report = parse_attendance_text(raw_text)
    base_name = input_path.stem

    json_path = export_report_json(report, output_dir / f"{base_name}.json")
    detail_csv = export_details_csv(report, output_dir / f"{base_name}_details.csv")
    summary_csv = export_summary_csv(report, output_dir / f"{base_name}_summary.csv")

    print("Parsed report exported:")
    print(f"- JSON    : {json_path}")
    print(f"- Details : {detail_csv}")
    print(f"- Summary : {summary_csv}")
    print(f"- Warnings: {len(report.get('warnings', []))}")


if __name__ == "__main__":
    main()
