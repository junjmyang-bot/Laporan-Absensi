"""Export helpers for parsed attendance text reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def export_report_json(report: Dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output


def _build_detail_rows(report: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    common = {
        "tanggal": report.get("tanggal", ""),
        "mp_name": report.get("mp_name", ""),
        "shift": report.get("shift", ""),
    }

    for item in report.get("telat_detail", []):
        for person in item.get("people", []):
            rows.append(
                {
                    **common,
                    "event_type": "telat",
                    "category": item.get("category", ""),
                    "name": person.get("name", ""),
                    "role": person.get("role", ""),
                    "reason": person.get("reason", ""),
                }
            )

    for item in report.get("tidak_masuk_detail", []):
        rows.append(
            {
                **common,
                "event_type": "tidak_masuk",
                "category": item.get("category", ""),
                "name": item.get("name", ""),
                "role": item.get("role", ""),
                "reason": item.get("reason", ""),
            }
        )

    for item in report.get("_tanpa_keterangan_detail", []):
        rows.append(
            {
                **common,
                "event_type": "tanpa_keterangan",
                "category": item.get("category", ""),
                "name": item.get("name", ""),
                "role": item.get("role", ""),
                "reason": item.get("reason", ""),
            }
        )

    for item in report.get("_resign_detail", []):
        rows.append(
            {
                **common,
                "event_type": "resign",
                "category": item.get("category", ""),
                "name": item.get("name", ""),
                "role": item.get("role", ""),
                "reason": item.get("reason", ""),
            }
        )

    return rows


def export_details_csv(report: Dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = _build_detail_rows(report)
    fieldnames = ["tanggal", "mp_name", "shift", "event_type", "category", "name", "role", "reason"]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output


def export_summary_csv(report: Dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "tanggal": report.get("tanggal", ""),
        "mp_name": report.get("mp_name", ""),
        "shift": report.get("shift", ""),
        "main_tl": report.get("main_tl", ""),
        "tl_lain": "|".join(report.get("tl_lain", [])),
        "total_kupas_member": report.get("total_kupas_member", 0),
        "total_training": report.get("total_training", 0),
        "masuk_kupas_member": report.get("masuk_kupas_member", 0),
        "masuk_training": report.get("masuk_training", 0),
        "jam_masuk": report.get("jam_masuk", ""),
        "jam_pulang": report.get("jam_pulang", ""),
        "telat_total": report.get("telat_total", 0),
        "tidak_masuk_total": report.get("tidak_masuk_total", 0),
        "tanpa_keterangan_total": report.get("tanpa_keterangan_total", 0),
        "resign_total": report.get("resign_total", 0),
        "warnings": " | ".join(report.get("warnings", [])),
    }

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)

    return output
