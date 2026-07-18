import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


INDENT = "        "
OUTPUT_FILE_NAME = "combined mod sha1 output.txt"
BUFFER_SIZE = 1024 * 1024


def sanitize_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").upper()

    if not identifier:
        identifier = "UNKNOWN_FILE"

    if identifier[0].isdigit():
        identifier = "_" + identifier

    return identifier


def make_variable_name(relative_path: Path) -> str:
    return "_".join(
        sanitize_identifier(part)
        for part in relative_path.parts
    ) + "_SHA1S"


def calculate_sha1(file_path: Path) -> str:
    sha1 = hashlib.sha1()

    with file_path.open("rb") as file:
        while chunk := file.read(BUFFER_SIZE):
            sha1.update(chunk)

    return sha1.hexdigest()


def print_progress(current: int, total: int, width: int = 40) -> None:
    if total <= 0:
        return

    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = current * 100.0 / total

    print(
        f"\rHashing files: [{bar}] {current}/{total} {percent:6.2f}%",
        end="",
        flush=True,
    )

    if current == total:
        print()


def find_mod_files(script_folder: Path) -> list[tuple[Path, Path, str]]:
    files: list[tuple[Path, Path, str]] = []
    script_path = Path(__file__).resolve()
    output_path = script_folder / OUTPUT_FILE_NAME

    for mod_folder in sorted(path for path in script_folder.iterdir() if path.is_dir()):
        for file_path in mod_folder.rglob("*"):
            if not file_path.is_file():
                continue

            resolved_path = file_path.resolve()

            if resolved_path == script_path or resolved_path == output_path.resolve():
                continue

            relative_path = file_path.relative_to(mod_folder)
            files.append((file_path, relative_path, mod_folder.name))

    return files


def format_cpp_array(variable_name: str, sha1s: list[str]) -> str:
    lines = [
        f"{INDENT}constexpr const char* {variable_name}[] =",
        f"{INDENT}{{",
    ]

    for index, sha1 in enumerate(sha1s):
        comma = "," if index < len(sha1s) - 1 else ""
        lines.append(f'{INDENT}    "{sha1}"{comma}')

    lines.append(f"{INDENT}}};")
    return "\n".join(lines)


def format_s_exe_path(relative_path: Path) -> str:
    return "sExePath" + "".join(
        f' / "{part}"'
        for part in relative_path.parts
    )


def format_remove_file_entries(
    entries: list[tuple[Path, str]]
) -> str:
    lines = [
        f"{INDENT}const Util::RemoveFileEntry outdatedFiles[] =",
        f"{INDENT}{{",
    ]

    for index, (relative_path, variable_name) in enumerate(entries):
        comma = "," if index < len(entries) - 1 else ""
        lines.append(
            f"{INDENT}    "
            f"{{{format_s_exe_path(relative_path)}, {variable_name} }}{comma}"
        )

    lines.append(f"{INDENT}}};")
    return "\n".join(lines)


def main() -> None:
    script_folder = Path(__file__).resolve().parent
    files = find_mod_files(script_folder)

    if not files:
        print("No files were found inside any subfolders.")
        input("\nPress Enter to exit...")
        return

    worker_count = min(
        len(files),
        max(1, (os.cpu_count() or 1) * 2),
    )

    print(f"Found {len(files)} file(s) across downloaded mod folders.")
    print(f"Hashing with {worker_count} worker thread(s)...")

    hashes_by_relative_path: dict[Path, list[str]] = {}
    sources_by_relative_path: dict[Path, list[str]] = {}

    completed = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(calculate_sha1, file_path):
                (relative_path, mod_name)
            for file_path, relative_path, mod_name in files
        }

        for future in as_completed(futures):
            relative_path, mod_name = futures[future]

            try:
                sha1 = future.result()
            except OSError as error:
                print(f"\nFailed to hash {mod_name}\\{relative_path}: {error}")
                completed += 1
                print_progress(completed, len(files))
                continue

            sha1s = hashes_by_relative_path.setdefault(relative_path, [])

            if sha1 not in sha1s:
                sha1s.append(sha1)

            sources = sources_by_relative_path.setdefault(relative_path, [])

            if mod_name not in sources:
                sources.append(mod_name)

            completed += 1
            print_progress(completed, len(files))

    sorted_paths = sorted(
        hashes_by_relative_path,
        key=lambda path: path.as_posix().casefold(),
    )

    output_lines: list[str] = []
    remove_entries: list[tuple[Path, str]] = []

    for relative_path in sorted_paths:
        variable_name = make_variable_name(relative_path)
        sha1s = sorted(hashes_by_relative_path[relative_path])

        output_lines.append(
            f"{INDENT}// Found in: {', '.join(sorted(sources_by_relative_path[relative_path]))}"
        )
        output_lines.append(format_cpp_array(variable_name, sha1s))
        output_lines.append("")

        remove_entries.append((relative_path, variable_name))

    output_lines.append(format_remove_file_entries(remove_entries))
    output_lines.append("")

    output_path = script_folder / OUTPUT_FILE_NAME
    output_path.write_text("\n".join(output_lines), encoding="utf-8")

    print(f"\nCombined {len(files)} file(s) into {len(sorted_paths)} unique relative path(s).")
    print(f"Output written to:\n{output_path}")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
