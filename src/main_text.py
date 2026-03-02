import argparse
from pathlib import Path

from src.absensi_text.parser import parse_attendance_text
from src.absensi_text.export import save_json, save_csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_text_file", required=True)
    ap.add_argument("--output_dir", default="data/processed")
    args = ap.parse_args()

    input_path = Path(args.input_text_file)
    out_dir = Path(args.output_dir)

    text = input_path.read_text(encoding="utf-8")
    result = parse_attendance_text(text)

    base = input_path.stem
    save_json(result, out_dir / f"{base}.json")
    save_csv(result, out_dir / f"{base}.csv")

    print("OK. Saved:")
    print(out_dir / f"{base}.json")
    print(out_dir / f"{base}.csv")


if __name__ == "__main__":
    main()