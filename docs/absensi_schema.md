# Attendance Text Report Schema (Telegram)

This parser converts a mixed Indonesian/Korean attendance text report into structured JSON.

## Input format

- Raw multi-line text from Telegram.
- Labels can vary slightly (`:` or `-` separator).
- Missing sections are allowed.

## JSON output fields

- `tanggal` (str)
- `mp_name` (str)
- `shift` (str)
- `main_tl` (str)
- `tl_lain` (list[str])
- `total_kupas_member` (int)
- `total_training` (int)
- `masuk_kupas_member` (int)
- `masuk_training` (int)
- `role_breakdown` (object)
  - `TL`, `AST`, `AJ`, `BIASA`, `TRAINING`
  - each role has `{masuk, total}`
- `jam_masuk` (str)
- `jam_pulang` (str)
- `telat_total` (int)
- `telat_detail` (list)
  - item: `{category, count, people:[{name, role, reason}]}`
- `tidak_masuk_total` (int)
- `tidak_masuk_detail` (list)
  - item: `{category, name, role, reason}`
- `tanpa_keterangan_total` (int)
- `resign_total` (int)
- `warnings` (list[str])

## Parsing assumptions

1. Missing/blank sections are treated as zero totals.
2. Total lines support forms like:
   - `Total : 43 pax + 3 tr`
   - `Masuk : 40 pax`
3. Role breakdown supports forms like:
   - `-> Biasa : 27 (Total masuk) / 30 (Total Orang di team)`
4. Totals are validated. If inconsistent, a warning is appended to `warnings`.

## CSV outputs

1. **Detail CSV**: one row per person from detail lists (`telat`, `tidak_masuk`, `tanpa_keterangan`, `resign`).
2. **Summary CSV**: one row per report.
