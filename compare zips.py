from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


# ==========================================================
# CONFIG
# ==========================================================
OLD_ZIP = Path(r"I:\Documents\Downloads\Compressed\MGS2-Demastered-Sub_Base_PS2_Resolution_v1.0.1.zip")
NEW_ZIP = Path(r"I:\Documents\Downloads\Compressed\MGS2-Demastered-Sub_Base_PS2_Resolution_v1.0.2.zip")

SEVENZIP_EXE = Path(r"C:\Program Files\7-Zip\7z.exe")
OUTPUT_REPORT = Path("zip_diff_report.txt")

IGNORE_CASE = True

@dataclass(frozen=True)
class ZipEntryInfo:
    path: str
    size: int
    crc: str


# ==========================================================
# HELPERS
# ==========================================================
def normalize_zip_path(path: str) -> str:
    path = path.replace("\\", "/").strip()

    while "//" in path:
        path = path.replace("//", "/")

    if path.startswith("./"):
        path = path[2:]

    return path


def make_key(path: str) -> str:
    normalized = normalize_zip_path(path)

    if IGNORE_CASE:
        return normalized.lower()

    return normalized


def parse_7z_slt_list(zip_path: Path) -> dict[str, ZipEntryInfo]:
    cmd = [
        str(SEVENZIP_EXE),
        "l",
        "-slt",
        str(zip_path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )

    entries: dict[str, ZipEntryInfo] = {}

    current_path: str | None = None
    current_size: int | None = None
    current_crc: str | None = None
    current_is_dir = False

    def flush_current() -> None:
        nonlocal current_path
        nonlocal current_size
        nonlocal current_crc
        nonlocal current_is_dir

        if current_path is None:
            return

        if current_is_dir:
            current_path = None
            current_size = None
            current_crc = None
            current_is_dir = False
            return

        normalized_path = normalize_zip_path(current_path)
        key = make_key(normalized_path)

        entries[key] = ZipEntryInfo(
            path=normalized_path,
            size=current_size if current_size is not None else 0,
            crc=current_crc if current_crc is not None else "",
        )

        current_path = None
        current_size = None
        current_crc = None
        current_is_dir = False

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("Path = "):
            flush_current()
            current_path = line[len("Path = "):]
            continue

        if current_path is None:
            continue

        if line.startswith("Folder = "):
            value = line[len("Folder = "):].strip()
            current_is_dir = (value == "+")
            continue

        if line.startswith("Size = "):
            value = line[len("Size = "):].strip()

            try:
                current_size = int(value)
            except ValueError:
                current_size = 0

            continue

        if line.startswith("CRC = "):
            current_crc = line[len("CRC = "):].strip().upper()
            continue

    flush_current()
    return entries


def write_report(
    output_path: Path,
    removed_files: list[ZipEntryInfo],
    added_files: list[ZipEntryInfo],
    modified_files: list[tuple[ZipEntryInfo, ZipEntryInfo]],
) -> None:
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"OLD ZIP: {OLD_ZIP}\n")
        f.write(f"NEW ZIP: {NEW_ZIP}\n\n")

        f.write(f"Removed files ({len(removed_files)}):\n")
        for entry in removed_files:
            f.write(f"- {entry.path}\n")

        f.write("\n")
        f.write(f"Added files ({len(added_files)}):\n")
        for entry in added_files:
            f.write(f"+ {entry.path}\n")

        f.write("\n")
        f.write(f"Modified files ({len(modified_files)}):\n")
        for old_entry, new_entry in modified_files:
            f.write(f"* {new_entry.path}\n")


# ==========================================================
# MAIN
# ==========================================================
def main() -> None:
    if not OLD_ZIP.is_file():
        raise FileNotFoundError(f"OLD_ZIP not found: {OLD_ZIP}")

    if not NEW_ZIP.is_file():
        raise FileNotFoundError(f"NEW_ZIP not found: {NEW_ZIP}")

    if not SEVENZIP_EXE.is_file():
        raise FileNotFoundError(f"7z executable not found: {SEVENZIP_EXE}")

    print("Listing OLD zip...")
    old_entries = parse_7z_slt_list(OLD_ZIP)

    print("Listing NEW zip...")
    new_entries = parse_7z_slt_list(NEW_ZIP)

    old_keys = set(old_entries.keys())
    new_keys = set(new_entries.keys())

    removed_files = sorted(
        (old_entries[key] for key in (old_keys - new_keys)),
        key=lambda e: e.path.lower(),
    )

    added_files = sorted(
        (new_entries[key] for key in (new_keys - old_keys)),
        key=lambda e: e.path.lower(),
    )

    modified_files: list[tuple[ZipEntryInfo, ZipEntryInfo]] = []

    for key in sorted(old_keys & new_keys):
        old_entry = old_entries[key]
        new_entry = new_entries[key]

        if old_entry.size != new_entry.size or old_entry.crc != new_entry.crc:
            modified_files.append((old_entry, new_entry))

    modified_files.sort(key=lambda pair: pair[1].path.lower())

    write_report(
        OUTPUT_REPORT,
        removed_files,
        added_files,
        modified_files,
    )

    print()
    print(f"Removed:  {len(removed_files)}")
    print(f"Added:    {len(added_files)}")
    print(f"Modified: {len(modified_files)}")
    print(f"Report:   {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()