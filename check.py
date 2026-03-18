from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


INPUT_CSV = Path(r"C:\Development\Git\MGS-Tri-Dumper\mgs2_texture_map.csv")

OUT_STR_TO_FILE_TXT = Path("texture_strcode_multiple_filenames.txt")
OUT_STR_TO_FILE_CSV = Path("texture_strcode_multiple_filenames.csv")

OUT_FILE_TO_STR_TXT = Path("texture_filename_multiple_strcodes.txt")
OUT_FILE_TO_STR_CSV = Path("texture_filename_multiple_strcodes.csv")


def normalize(s: str) -> str:
    return (s or "").strip()


def is_comment_or_blank(line: str) -> bool:
    t = (line or "").strip()
    return (not t) or t.startswith(";")


def numeric_sort_key(s: str):
    if s.isdigit():
        return (0, int(s))
    return (1, s)


def main() -> int:
    if not INPUT_CSV.exists():
        raise SystemExit(f"Input CSV not found: {INPUT_CSV}")

    # Maps
    strcode_to_filenames: dict[str, set[str]] = defaultdict(set)
    filename_to_strcodes: dict[str, set[str]] = defaultdict(set)

    total_lines = 0
    parsed_rows = 0
    skipped_comment_blank = 0
    skipped_bad = 0

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        for raw_line in f:
            total_lines += 1

            if is_comment_or_blank(raw_line):
                skipped_comment_blank += 1
                continue

            try:
                row = next(csv.reader([raw_line], skipinitialspace=True))
            except Exception:
                skipped_bad += 1
                continue

            if len(row) < 4:
                skipped_bad += 1
                continue

            texture_filename = normalize(row[0])
            texture_strcode = normalize(row[3])

            if not texture_filename or not texture_strcode:
                skipped_bad += 1
                continue

            strcode_to_filenames[texture_strcode].add(texture_filename)
            filename_to_strcodes[texture_filename].add(texture_strcode)
            parsed_rows += 1

    # Build conflict lists
    strcode_conflicts = [
        (s, sorted(filenames))
        for s, filenames in strcode_to_filenames.items()
        if len(filenames) > 1
    ]
    strcode_conflicts.sort(key=lambda x: numeric_sort_key(x[0]))

    filename_conflicts = [
        (f, sorted(strcodes))
        for f, strcodes in filename_to_strcodes.items()
        if len(strcodes) > 1
    ]
    filename_conflicts.sort(key=lambda x: numeric_sort_key(x[0]))

    # ---------- Write STRCODE -> FILENAMES ----------
    lines = []
    lines.append(f"Input: {INPUT_CSV}")
    lines.append(f"Total lines read: {total_lines}")
    lines.append(f"Parsed rows: {parsed_rows}")
    lines.append(f"Skipped comment/blank: {skipped_comment_blank}")
    lines.append(f"Skipped bad rows: {skipped_bad}")
    lines.append(f"Conflicting texture_strcode count: {len(strcode_conflicts)}")
    lines.append("")
    lines.append("texture_strcode -> texture_filename(s)")
    lines.append("------------------------------------------------------------")

    for strcode, filenames in strcode_conflicts:
        lines.append(f"{strcode} -> {', '.join(filenames)}")

    OUT_STR_TO_FILE_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with OUT_STR_TO_FILE_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["texture_strcode", "texture_filename_count", "texture_filenames"])
        for strcode, filenames in strcode_conflicts:
            w.writerow([strcode, len(filenames), "|".join(filenames)])

    # ---------- Write FILENAME -> STRCODES ----------
    lines = []
    lines.append(f"Input: {INPUT_CSV}")
    lines.append(f"Total lines read: {total_lines}")
    lines.append(f"Parsed rows: {parsed_rows}")
    lines.append(f"Skipped comment/blank: {skipped_comment_blank}")
    lines.append(f"Skipped bad rows: {skipped_bad}")
    lines.append(f"Conflicting texture_filename count: {len(filename_conflicts)}")
    lines.append("")
    lines.append("texture_filename -> texture_strcode(s)")
    lines.append("------------------------------------------------------------")

    for filename, strcodes in filename_conflicts:
        lines.append(f"{filename} -> {', '.join(strcodes)}")

    OUT_FILE_TO_STR_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with OUT_FILE_TO_STR_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["texture_filename", "texture_strcode_count", "texture_strcodes"])
        for filename, strcodes in filename_conflicts:
            w.writerow([filename, len(strcodes), "|".join(strcodes)])

    print(f"Wrote: {OUT_STR_TO_FILE_TXT.resolve()}")
    print(f"Wrote: {OUT_STR_TO_FILE_CSV.resolve()}")
    print(f"Wrote: {OUT_FILE_TO_STR_TXT.resolve()}")
    print(f"Wrote: {OUT_FILE_TO_STR_CSV.resolve()}")
    print()
    print(f"Strcode conflicts: {len(strcode_conflicts)}")
    print(f"Filename conflicts: {len(filename_conflicts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())