from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os


ROOT_FOLDER = Path(__file__).resolve().parent
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 4)

# Original first-field filename: replacement first-field filename
ASSET_REPLACEMENTS = {
    "sna_def_mt_stage_r_plt_s_r.tri": "afevis_sna_def_mt_stage_r_plt_s_r.tri",
    #"sna_def_mt_stage_r_plt_s_r.tri": "afevis_sna_def_mt_stage_r_plt_s_r.tri",
}


def replace_first_field_filename(line: str) -> str | None:
    fields = line.split(",")

    if len(fields) < 2:
        return None

    first_path = fields[0]
    first_filename = first_path.rsplit("/", 1)[-1]

    replacement_filename = ASSET_REPLACEMENTS.get(first_filename)

    if replacement_filename is None:
        return None

    if "/" in first_path:
        first_directory = first_path.rsplit("/", 1)[0]
        fields[0] = f"{first_directory}/{replacement_filename}"
    else:
        fields[0] = replacement_filename

    return ",".join(fields)


def process_manifest(manifest_path: Path) -> tuple[Path, int, int]:
    with manifest_path.open(
        "r",
        encoding="utf-8-sig",
        newline=None,
    ) as file:
        source_lines = file.read().splitlines()

    output_lines = []

    for line in source_lines:
        replacement_line = replace_first_field_filename(line)

        if replacement_line is not None:
            output_lines.append(replacement_line)

    output_text = "\r\n".join(output_lines)

    if output_lines:
        output_text += "\r\n"

    with manifest_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        file.write(output_text)

    matched_count = len(output_lines)
    removed_count = len(source_lines) - matched_count

    return manifest_path, matched_count, removed_count


def main() -> None:
    manifest_files = [
        path
        for path in ROOT_FOLDER.rglob("bp_assets*.txt")
        if path.is_file()
    ]

    if not manifest_files:
        print("No bp_assets TXT files found.")
        return

    processed_count = 0
    failed_count = 0
    total_matched = 0
    total_removed = 0

    print(f"Processing {len(manifest_files)} manifest files...")
    print()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_manifest, manifest_path): manifest_path
            for manifest_path in manifest_files
        }

        for future in as_completed(futures):
            manifest_path = futures[future]

            try:
                path, matched_count, removed_count = future.result()

                processed_count += 1
                total_matched += matched_count
                total_removed += removed_count

                relative_path = path.relative_to(ROOT_FOLDER)

                print(
                    f"[PROCESSED] {relative_path} "
                    f"Matched: {matched_count}, Removed: {removed_count}"
                )

            except Exception as exception:
                failed_count += 1
                print(f"[FAILED] {manifest_path}: {exception}")

    print()
    print(f"Processed: {processed_count}")
    print(f"Failed: {failed_count}")
    print(f"Matched lines: {total_matched}")
    print(f"Removed lines: {total_removed}")


if __name__ == "__main__":
    main()