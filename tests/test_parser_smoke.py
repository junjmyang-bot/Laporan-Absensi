"""Minimal smoke script to validate required JSON schema keys exist."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.absensi_text.parser import parse_attendance_text

REQUIRED_KEYS = {
    "tanggal",
    "mp_name",
    "shift",
    "main_tl",
    "tl_lain",
    "total_kupas_member",
    "total_training",
    "masuk_kupas_member",
    "masuk_training",
    "role_breakdown",
    "jam_masuk",
    "jam_pulang",
    "telat_total",
    "telat_detail",
    "tidak_masuk_total",
    "tidak_masuk_detail",
    "tanpa_keterangan_total",
    "resign_total",
    "warnings",
}


def run_smoke_test() -> None:
    sample = """
Tanggal : 2025-01-01
MP Name : Team A
Shift : 1
Main TL : Jisoo
TL lain : Mina, Dewi
Total : 43 pax + 3 tr
Masuk : 40 pax + 2 tr
-> TL : 5 (Total masuk) / 5 (Total Orang di team)
Telat : 1 orang
1. Telat bangun: Andi (TL) - kesiangan
Tidak Masuk : 1 orang
Sakit: Budi (AST) - demam
""".strip()

    report = parse_attendance_text(sample)
    missing = REQUIRED_KEYS.difference(set(report.keys()))
    assert not missing, f"Missing keys: {sorted(missing)}"


if __name__ == "__main__":
    run_smoke_test()
    print("Smoke test passed.")
