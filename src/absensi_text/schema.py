"""Schema helpers for attendance text parsing output.

The schema is intentionally plain-dict based so it is easy to serialize as JSON
and easy to tweak without introducing heavy dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List


def default_report() -> Dict[str, Any]:
    """Return a report object populated with safe defaults."""
    return {
        "tanggal": "",
        "mp_name": "",
        "shift": "",
        "main_tl": "",
        "tl_lain": [],
        "total_kupas_member": 0,
        "total_training": 0,
        "masuk_kupas_member": 0,
        "masuk_training": 0,
        "role_breakdown": {
            "TL": {"masuk": 0, "total": 0},
            "AST": {"masuk": 0, "total": 0},
            "AJ": {"masuk": 0, "total": 0},
            "BIASA": {"masuk": 0, "total": 0},
            "TRAINING": {"masuk": 0, "total": 0},
        },
        "jam_masuk": "",
        "jam_pulang": "",
        "telat_total": 0,
        "telat_detail": [],
        "tidak_masuk_total": 0,
        "tidak_masuk_detail": [],
        "tanpa_keterangan_total": 0,
        "resign_total": 0,
        "warnings": [],
    }


def add_warning(report: Dict[str, Any], message: str) -> None:
    """Append a warning message once."""
    warnings: List[str] = report["warnings"]
    if message not in warnings:
        warnings.append(message)
