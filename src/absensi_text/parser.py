"""Parser for Indonesian/Korean mixed Telegram attendance text reports."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.absensi_text.schema import add_warning, default_report

ROLE_KEYS = {"TL": "TL", "AST": "AST", "AJ": "AJ", "BIASA": "BIASA", "TRAINING": "TRAINING"}


def _to_int(value: str, default: int = 0) -> int:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else default


def _extract_field(text: str, label_patterns: List[str]) -> str:
    for pattern in label_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def _parse_total_line(text: str, key: str) -> tuple[int, int]:
    """Parse formats like: Total : 43 pax + 3 tr / Masuk : 40 pax."""
    pattern = rf"{key}\s*[:\-]\s*(\d+)\s*pax(?:\s*\+\s*(\d+)\s*tr)?"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return 0, 0
    kupas = int(match.group(1))
    training = int(match.group(2) or 0)
    return kupas, training


def _parse_people_blob(people_blob: str) -> List[Dict[str, str]]:
    """Parse people list from a comma/semicolon-separated blob.

    Supported token examples:
    - Andi (TL) - kesiangan
    - Budi(AST)
    - Citra - izin keluarga
    """
    results: List[Dict[str, str]] = []
    if not people_blob.strip():
        return results

    tokens = [tok.strip() for tok in re.split(r"[;,]", people_blob) if tok.strip()]
    for token in tokens:
        match = re.match(
            r"^(?P<name>[^()\-:]+?)\s*(?:\((?P<role>[^)]+)\))?\s*(?:[-:]\s*(?P<reason>.+))?$",
            token,
        )
        if not match:
            results.append({"name": token, "role": "", "reason": ""})
            continue
        results.append(
            {
                "name": match.group("name").strip(),
                "role": (match.group("role") or "").strip().upper(),
                "reason": (match.group("reason") or "").strip(),
            }
        )
    return results


def _parse_role_breakdown(lines: List[str], report: Dict[str, Any]) -> None:
    # Example: -> Biasa : 27 (Total masuk) / 30 (Total Orang di team)
    pattern = re.compile(r"(?:->\s*)?([A-Za-z]+)\s*:\s*(\d+)\s*.*?/\s*(\d+)", re.IGNORECASE)
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        role_raw = match.group(1).strip().upper()
        role = ROLE_KEYS.get(role_raw)
        if not role:
            continue
        report["role_breakdown"][role] = {
            "masuk": int(match.group(2)),
            "total": int(match.group(3)),
        }


def _split_sections(lines: List[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"telat": [], "tidak_masuk": [], "tanpa_keterangan": [], "resign": []}
    current = ""
    for line in lines:
        low = line.lower()
        if "telat" in low:
            current = "telat"
            continue
        if "tidak masuk" in low or "tdk masuk" in low:
            current = "tidak_masuk"
            continue
        if "tanpa keterangan" in low or "tk" in low:
            current = "tanpa_keterangan"
            continue
        if "resign" in low:
            current = "resign"
            continue
        if current and line.strip():
            sections[current].append(line.strip())
    return sections


def _parse_telat_details(lines: List[str]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for line in lines:
        # category : 2 orang - A(TL)-reason, B(AST)-reason
        match = re.match(
            r"^(?:\d+\.\s*)?(?P<category>[^:]+):\s*(?:(?P<count>\d+)\s*(?:orang|org|pax)?)?\s*(?:[-:]\s*)?(?P<people>.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        category = match.group("category").strip()
        people = _parse_people_blob(match.group("people") or "")
        count = int(match.group("count") or len(people) or 0)
        details.append({"category": category, "count": count, "people": people})
    return details


def _parse_absence_details(lines: List[str], default_category: str) -> List[Dict[str, str]]:
    details: List[Dict[str, str]] = []
    for line in lines:
        # sakit: Andi(TL)-demam; Budi(AST)-flu
        # Andi(TL)-izin keluarga
        category = default_category
        payload = line
        cat_match = re.match(r"^(?:\d+\.\s*)?([^:]+):\s*(.+)$", line)
        if cat_match:
            category = cat_match.group(1).strip()
            payload = cat_match.group(2).strip()

        for person in _parse_people_blob(payload):
            details.append(
                {
                    "category": category,
                    "name": person["name"],
                    "role": person["role"],
                    "reason": person["reason"],
                }
            )
    return details


def _validate_totals(report: Dict[str, Any]) -> None:
    role_masuk_sum = sum(v["masuk"] for v in report["role_breakdown"].values())
    role_total_sum = sum(v["total"] for v in report["role_breakdown"].values())

    expected_masuk = report["masuk_kupas_member"] + report["masuk_training"]
    expected_total = report["total_kupas_member"] + report["total_training"]

    if role_masuk_sum and role_masuk_sum != expected_masuk:
        add_warning(report, f"Role masuk sum mismatch: role={role_masuk_sum}, summary={expected_masuk}")
    if role_total_sum and role_total_sum != expected_total:
        add_warning(report, f"Role total sum mismatch: role={role_total_sum}, summary={expected_total}")

    telat_sum = sum(item["count"] for item in report["telat_detail"])
    if report["telat_total"] and report["telat_total"] != telat_sum:
        add_warning(report, f"Telat total mismatch: total={report['telat_total']}, detail={telat_sum}")

    if report["tidak_masuk_total"] and report["tidak_masuk_total"] != len(report["tidak_masuk_detail"]):
        add_warning(
            report,
            f"Tidak masuk total mismatch: total={report['tidak_masuk_total']}, detail={len(report['tidak_masuk_detail'])}",
        )


def parse_attendance_text(raw_text: str) -> Dict[str, Any]:
    """Parse Telegram attendance text into a structured report dict."""
    report = default_report()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    full_text = "\n".join(lines)

    report["tanggal"] = _extract_field(full_text, [r"tanggal\s*[:\-]\s*(.+)"])
    report["mp_name"] = _extract_field(full_text, [r"mp\s*(?:name)?\s*[:\-]\s*(.+)"])
    report["shift"] = _extract_field(full_text, [r"shift\s*[:\-]\s*(.+)"])
    report["main_tl"] = _extract_field(full_text, [r"main\s*tl\s*[:\-]\s*(.+)"])

    tl_lain_raw = _extract_field(full_text, [r"tl\s*lain\s*[:\-]\s*(.+)"])
    report["tl_lain"] = [v.strip() for v in re.split(r"[,;/]", tl_lain_raw) if v.strip()] if tl_lain_raw else []

    report["total_kupas_member"], report["total_training"] = _parse_total_line(full_text, "total")
    report["masuk_kupas_member"], report["masuk_training"] = _parse_total_line(full_text, "masuk")

    _parse_role_breakdown(lines, report)

    report["jam_masuk"] = _extract_field(full_text, [r"jam\s*masuk\s*[:\-]\s*(.+)"])
    report["jam_pulang"] = _extract_field(full_text, [r"jam\s*pulang\s*[:\-]\s*(.+)"])

    report["telat_total"] = _to_int(_extract_field(full_text, [r"telat\s*(?:total)?\s*[:\-]\s*([^\n]+)"]))
    report["tidak_masuk_total"] = _to_int(
        _extract_field(full_text, [r"tidak\s*masuk\s*(?:total)?\s*[:\-]\s*([^\n]+)", r"tdk\s*masuk\s*[:\-]\s*([^\n]+)"])
    )
    report["tanpa_keterangan_total"] = _to_int(
        _extract_field(full_text, [r"tanpa\s*keterangan\s*(?:total)?\s*[:\-]\s*([^\n]+)", r"tk\s*[:\-]\s*([^\n]+)"])
    )
    report["resign_total"] = _to_int(_extract_field(full_text, [r"resign\s*(?:total)?\s*[:\-]\s*([^\n]+)"]))

    sections = _split_sections(lines)
    report["telat_detail"] = _parse_telat_details(sections["telat"])
    report["tidak_masuk_detail"] = _parse_absence_details(sections["tidak_masuk"], "tidak_masuk")

    # If totals not present, infer from details for convenience.
    if report["telat_total"] == 0 and report["telat_detail"]:
        report["telat_total"] = sum(item["count"] for item in report["telat_detail"])
    if report["tidak_masuk_total"] == 0 and report["tidak_masuk_detail"]:
        report["tidak_masuk_total"] = len(report["tidak_masuk_detail"])

    # Optional detail sections for TK and resign are flattened into tidak_masuk_detail-like rows for export use.
    tk_details = _parse_absence_details(sections["tanpa_keterangan"], "tanpa_keterangan")
    rs_details = _parse_absence_details(sections["resign"], "resign")

    if report["tanpa_keterangan_total"] == 0:
        report["tanpa_keterangan_total"] = len(tk_details)
    if report["resign_total"] == 0:
        report["resign_total"] = len(rs_details)

    # Store internally for exporter convenience.
    report["_tanpa_keterangan_detail"] = tk_details
    report["_resign_detail"] = rs_details

    _validate_totals(report)
    return report
