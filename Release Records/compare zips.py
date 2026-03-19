from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================================
# CONFIG
# ==========================================================
OLD_ZIP = Path(r"C:\Users\cmkoo\OneDrive\Desktop\bugfix comp\MGS2-Community-Bugfix-Compilation_2x_Upscaled_Addon_v2.0.2.zip")
NEW_ZIP = Path(r"C:\Users\cmkoo\OneDrive\Desktop\bugfix comp\MGS2-Community-Bugfix-Compilation_2x_Upscaled_Addon_v2.1.2.zip")

SEVENZIP_EXE = Path(r"C:\Program Files\7-Zip\7z.exe")

HASH_MAX_WORKERS = min(8, max(1, os.cpu_count() or 4))

IGNORE_CASE = True
SHA1_BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ZipEntryInfo:
    path: str
    size: int
    crc: str
 

@dataclass(frozen=True)
class RemovedFileWithSha1:
    entry: ZipEntryInfo
    sha1: str


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


def sanitize_filename_component(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.rstrip(". ")
    return value or "unnamed"


def make_output_report_path(old_zip: Path, new_zip: Path) -> Path:
    old_name = sanitize_filename_component(old_zip.stem)
    new_name = sanitize_filename_component(new_zip.stem)
    filename = f"zip_diff_report__{old_name}__to__{new_name}.txt"
    return Path(__file__).resolve().with_name(filename)


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


def compute_entry_sha1(zip_path: Path, entry_path: str) -> str:
    cmd = [
        str(SEVENZIP_EXE),
        "x",
        "-so",
        str(zip_path),
        entry_path,
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    sha1 = hashlib.sha1()

    assert process.stdout is not None

    while True:
        chunk = process.stdout.read(SHA1_BUFFER_SIZE)
        if not chunk:
            break
        sha1.update(chunk)

    stderr_data = b""
    if process.stderr is not None:
        stderr_data = process.stderr.read()

    return_code = process.wait()

    if return_code != 0:
        stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"7z failed while hashing '{entry_path}' from '{zip_path}'. Exit code: {return_code}. "
            f"stderr: {stderr_text}"
        )

    return sha1.hexdigest().lower()


def build_removed_files_with_sha1(old_zip: Path, removed_files: list[ZipEntryInfo]) -> list[RemovedFileWithSha1]:
    if not removed_files:
        return []

    results: list[RemovedFileWithSha1 | None] = [None] * len(removed_files)

    def worker(index: int, entry: ZipEntryInfo) -> tuple[int, RemovedFileWithSha1]:
        sha1 = compute_entry_sha1(old_zip, entry.path)
        return index, RemovedFileWithSha1(entry=entry, sha1=sha1)

    total = len(removed_files)

    with ThreadPoolExecutor(max_workers=HASH_MAX_WORKERS) as executor:
        future_map = {
            executor.submit(worker, index, entry): (index, entry)
            for index, entry in enumerate(removed_files)
        }

        completed = 0

        for future in as_completed(future_map):
            index, entry = future_map[future]
            completed += 1

            try:
                result_index, item = future.result()
            except Exception as exc:
                raise RuntimeError(f"Failed hashing removed file '{entry.path}': {exc}") from exc

            results[result_index] = item
            print(f"Hashed removed file {completed}/{total}: {entry.path}")

    return [item for item in results if item is not None]


def write_report(
    output_path: Path,
    old_zip: Path,
    new_zip: Path,
    removed_files: list[RemovedFileWithSha1],
    added_files: list[ZipEntryInfo],
    modified_files: list[tuple[ZipEntryInfo, ZipEntryInfo]],
) -> None:
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"OLD ZIP: {old_zip}\n")
        f.write(f"NEW ZIP: {new_zip}\n\n")

        f.write(f"Removed files ({len(removed_files)}):\n")
        for item in removed_files:
            f.write(f"{{\"{item.entry.path}\", \"{item.sha1}\" }},\n")

        f.write("\n")
        f.write(f"Added files ({len(added_files)}):\n")
        for entry in added_files:
            f.write(f"+ {entry.path}\n")

        f.write("\n")
        f.write(f"Modified files ({len(modified_files)}):\n")
        for old_entry, new_entry in modified_files:
            f.write(f"* {new_entry.path}\n")
            f.write(f"  OLD size={old_entry.size}, crc={old_entry.crc}\n")
            f.write(f"  NEW size={new_entry.size}, crc={new_entry.crc}\n")


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

    output_report = make_output_report_path(OLD_ZIP, NEW_ZIP)

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

    print("Hashing removed files from OLD zip...")
    removed_files_with_sha1 = build_removed_files_with_sha1(OLD_ZIP, removed_files)

    write_report(
        output_report,
        OLD_ZIP,
        NEW_ZIP,
        removed_files_with_sha1,
        added_files,
        modified_files,
    )

    print()
    print(f"Removed:  {len(removed_files_with_sha1)}")
    print(f"Added:    {len(added_files)}")
    print(f"Modified: {len(modified_files)}")
    print(f"Report:   {output_report}")


if __name__ == "__main__":
    main()