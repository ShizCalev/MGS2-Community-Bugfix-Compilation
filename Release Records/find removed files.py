import csv
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


INDENT = "        "


def clean_path(value: str) -> str:
    value = value.strip().strip('"').strip("'")

    value = "".join(
        character
        for character in value
        if unicodedata.category(character) not in {"Cf", "Cc"}
    )

    return value.replace("\\", "/").rstrip("/").casefold()


def split_path(value: str) -> list[str]:
    return [part for part in clean_path(value).split("/") if part]


def paths_match(input_path: str, csv_path: str) -> bool:
    input_path = clean_path(input_path)
    csv_path = clean_path(csv_path)

    return input_path == csv_path or input_path.endswith("/" + csv_path)


def sanitize_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").upper()

    if not identifier:
        identifier = "UNKNOWN_FILE"

    if identifier[0].isdigit():
        identifier = "_" + identifier

    return identifier


def make_variable_names(input_paths: list[str]) -> dict[str, str]:
    variable_names: dict[str, str] = {}

    for input_path in input_paths:
        parts = split_path(input_path)
        variable_name = sanitize_identifier("_".join(parts)) + "_SHA1S"
        variable_names[input_path] = variable_name

    return variable_names


def get_input_paths() -> list[str]:
    if len(sys.argv) > 1:
        argument = Path(sys.argv[1])

        if len(sys.argv) == 2 and argument.is_file():
            return [
                line
                for line in argument.read_text(encoding="utf-8-sig").splitlines()
                if clean_path(line)
            ]

        return [" ".join(sys.argv[1:])]

    print("Paste file paths, one per line.")
    print("Press Enter on a blank line when finished.\n")

    paths: list[str] = []

    while True:
        line = input()

        if not line.strip():
            break

        paths.append(line)

    return paths


def read_csv_entries(csv_path: Path) -> tuple[str, list[tuple[str, str]], str | None]:
    entries: list[tuple[str, str]] = []

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                return csv_path.name, entries, "CSV has no header"

            normalized_headers = {
                clean_path(header): header
                for header in reader.fieldnames
                if header
            }

            full_path_header = normalized_headers.get("full_path")
            sha1_header = normalized_headers.get("sha1")

            if not full_path_header or not sha1_header:
                return csv_path.name, entries, "missing full_path or sha1 column"

            for row in reader:
                full_path = row.get(full_path_header, "")
                sha1 = row.get(sha1_header, "").strip()

                if full_path and sha1:
                    entries.append((full_path, sha1))

        return csv_path.name, entries, None

    except (OSError, csv.Error, UnicodeError) as error:
        return csv_path.name, entries, str(error)


def print_progress(current: int, total: int, width: int = 40) -> None:
    if total <= 0:
        return

    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = current * 100.0 / total

    print(
        f"\rReading CSV files: [{bar}] {current}/{total} {percent:6.2f}%",
        end="",
        flush=True,
    )

    if current == total:
        print()


def load_all_entries(folder: Path) -> list[tuple[str, str, str]]:
    csv_paths = sorted(folder.glob("*.csv"))

    if not csv_paths:
        return []

    all_entries: list[tuple[str, str, str]] = []
    worker_count = min(len(csv_paths), max(1, os.cpu_count() or 1))

    print(f"Scanning {len(csv_paths)} CSV file(s) with {worker_count} worker thread(s)...")

    completed = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(read_csv_entries, csv_path): csv_path
            for csv_path in csv_paths
        }

        for future in as_completed(futures):
            csv_name, entries, error = future.result()

            if error:
                print(f"\nSkipping {csv_name}: {error}")
            else:
                all_entries.extend(
                    (csv_name, full_path, sha1)
                    for full_path, sha1 in entries
                )

            completed += 1
            print_progress(completed, len(csv_paths))

    return all_entries


def format_source_name(csv_name: str) -> str:
    return Path(csv_name).stem.replace("_", " ")


def format_cpp_array(
    variable_name: str,
    sha1_sources: list[tuple[str, list[str]]],
) -> str:
    lines = [
        f"{INDENT}constexpr const char* {variable_name}[] =",
        f"{INDENT}{{",
    ]

    for index, (sha1, source_names) in enumerate(sha1_sources):
        comma = "," if index < len(sha1_sources) - 1 else ""
        sources = ", ".join(format_source_name(name) for name in source_names)
        lines.append(f'{INDENT}    "{sha1}"{comma} // {sources}')

    lines.append(f"{INDENT}}};")
    return "\n".join(lines)


def format_s_exe_path(file_path: str) -> str:
    parts = split_path(file_path)
    return "sExePath" + "".join(f' / "{part}"' for part in parts)


def format_remove_file_entries(
    matched_paths: list[tuple[str, str]]
) -> str:
    lines = [
        f"{INDENT}const Util::RemoveFileEntry outdatedFiles[] =",
        f"{INDENT}{{",
    ]

    for index, (file_path, variable_name) in enumerate(matched_paths):
        comma = "," if index < len(matched_paths) - 1 else ""
        lines.append(
            f"{INDENT}    "
            f"{{{format_s_exe_path(file_path)}, {variable_name} }}{comma}"
        )

    lines.append(f"{INDENT}}};")
    return "\n".join(lines)


def main() -> None:
    script_folder = Path(__file__).resolve().parent
    input_paths = get_input_paths()

    if not input_paths:
        print("No file paths entered.")
        input("\nPress Enter to exit...")
        return

    entries = load_all_entries(script_folder)

    if not entries:
        print("No usable entries were found in the CSV files beside the script.")
        input("\nPress Enter to exit...")
        return

    variable_names = make_variable_names(input_paths)
    matched_paths: list[tuple[str, str]] = []

    print("\nC++ output:\n")

    for input_path in input_paths:
        sha1_sources: dict[str, list[str]] = {}

        for csv_name, csv_path, sha1 in entries:
            if not paths_match(input_path, csv_path):
                continue

            source_names = sha1_sources.setdefault(sha1, [])

            if csv_name not in source_names:
                source_names.append(csv_name)

        if not sha1_sources:
            print(f"{INDENT}// No match found for: {clean_path(input_path)}\n")
            continue

        variable_name = variable_names[input_path]
        matched_paths.append((clean_path(input_path), variable_name))

        print(format_cpp_array(variable_name, list(sha1_sources.items())))
        print()

    if matched_paths:
        print(format_remove_file_entries(matched_paths))
        print()

    print(f"Matched {len(matched_paths)} of {len(input_paths)} file path(s).")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()