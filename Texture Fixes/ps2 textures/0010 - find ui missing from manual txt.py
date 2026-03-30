from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable, Set

SCRIPT_DIR = Path(__file__).resolve().parent
MANUAL_UI_TXT = SCRIPT_DIR / "manual_ui_textures.txt"
OUTPUT_TXT = SCRIPT_DIR / "manual_ui_texture_location_issues.log"

VALID_EXTENSIONS = {".png", ".tga"}


def pause_and_exit(code: int = 1) -> None:
    try:
        input("Press ENTER to exit...")
    except EOFError:
        pass
    raise SystemExit(code)


def normalize_stem(value: str) -> str:
    return value.strip().lower()


def load_manual_ui_stems(path: Path) -> Set[str]:
    if not path.is_file():
        print(f"ERROR: Missing file: {path}")
        pause_and_exit(1)

    stems: Set[str] = set()

    with path.open("r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#") or line.startswith(";") or line.startswith("//"):
                continue

            stem = normalize_stem(line)

            if not stem:
                print(f"WARNING: Ignoring empty entry on line {line_number}")
                continue

            stems.add(stem)

    return stems


def is_under_no_mip_ui(path: Path, root: Path) -> bool:
    relative_parts = [part.lower() for part in path.relative_to(root).parts]

    for i in range(len(relative_parts) - 1):
        if relative_parts[i] == "no_mip_fixes" and relative_parts[i + 1] == "ui":
            return True

    return False


def iter_texture_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in VALID_EXTENSIONS:
            continue

        yield path


def write_issues_txt(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        if path.exists():
            path.unlink()
        return

    stems = sorted({row["stem"] for row in rows})

    with path.open("w", encoding="utf-8", newline="\n") as f:
        for stem in stems:
            f.write(stem + "\n")


def main() -> None:
    manual_stems = load_manual_ui_stems(MANUAL_UI_TXT)

    print(f"Loaded manual UI stems: {len(manual_stems)}")
    print(f"Scanning: {SCRIPT_DIR}")

    issues: list[dict[str, str]] = []
    scanned_files = 0
    ui_files = 0
    wrong_location_count = 0
    unexpected_in_ui_count = 0

    for file_path in iter_texture_files(SCRIPT_DIR):
        scanned_files += 1

        if file_path == MANUAL_UI_TXT or file_path == OUTPUT_TXT:
            continue

        stem = normalize_stem(file_path.stem)
        relative_path = file_path.relative_to(SCRIPT_DIR).as_posix()
        in_expected_ui_folder = is_under_no_mip_ui(file_path, SCRIPT_DIR)
        in_manual_list = stem in manual_stems

        if in_expected_ui_folder:
            ui_files += 1

            if not in_manual_list:
                unexpected_in_ui_count += 1
                issues.append(
                    {
                        "issue": "in_ui_missing_from_manual_txt",
                        "stem": stem,
                        "extension": file_path.suffix.lower(),
                        "relative_path": relative_path,
                        "details": "File is under no_mip_fixes/ui but its stem is not listed in manual_ui_textures.txt",
                    }
                )
        else:
            if in_manual_list:
                wrong_location_count += 1
                issues.append(
                    {
                        "issue": "manual_ui_texture_in_wrong_location",
                        "stem": stem,
                        "extension": file_path.suffix.lower(),
                        "relative_path": relative_path,
                        "details": "Stem is listed in manual_ui_textures.txt but file is not under no_mip_fixes/ui",
                    }
                )

    issues.sort(
        key=lambda row: (
            row["issue"],
            row["stem"],
            row["relative_path"],
        )
    )

    write_issues_txt(OUTPUT_TXT, issues)

    print()
    print(f"Scanned texture files: {scanned_files}")
    print(f"Files under no_mip_fixes/ui: {ui_files}")
    print(f"Unexpected files in UI folders: {unexpected_in_ui_count}")
    print(f"Manual UI files in wrong location: {wrong_location_count}")

    if issues:
        print(f"Issues written to: {OUTPUT_TXT}")
    else:
        print("No issues found.")
        print("No log file was written.")
    
    return 0


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        pause_and_exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}")
        pause_and_exit(1)