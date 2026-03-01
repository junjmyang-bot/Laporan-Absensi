# Attendance Telegram Text Parser

텔레그램 ABSENSI 보고서 텍스트(예: `A. Laporan Absensi Team` 형식)를 파싱해 JSON/CSV로 저장하는 간단한 프로젝트입니다.

## Repository structure

- `src/absensi_text/parser.py` — 텍스트 파싱 로직
- `src/absensi_text/export.py` — JSON/CSV 저장
- `src/main_text.py` — 메인 CLI (요청한 진입점)
- `src/main.py` — 호환용 래퍼 (`main_text` 호출)
- `docs/absensi_schema.md` — 스키마/가정 문서
- `tests/test_parser_smoke.py` — 최소 스모크 테스트

## Dependencies

- `pandas` 의존성 없음
- 표준 라이브러리(`csv`, `json`)만 사용

## Run

```bash
python -m src.main_text --input_text_file data/raw/sample_report.txt
```

옵션:

```bash
python -m src.main_text --input_text_file data/raw/sample_report.txt --output_dir data/processed
```

## Output

입력 파일명이 `sample_report.txt` 이면 기본적으로 `data/processed/` 아래에 생성됩니다.

- `sample_report.json`
- `sample_report_details.csv`
- `sample_report_summary.csv`

## Notes

- 섹션이 비어있거나 누락되면 숫자 항목은 `0`으로 처리됩니다.
- 합계가 맞지 않으면 `warnings` 필드에 mismatch 메시지가 추가됩니다.
- 규칙 변경은 `src/absensi_text/parser.py`에서 쉽게 수정할 수 있습니다.
