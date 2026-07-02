from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os
import shutil


MGS2_ROOT = Path(r"G:\Steam\steamapps\common\MGS2")
OUTPUT_ROOT = Path(__file__).resolve().parent
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 4)

VALID_FILENAMES = (
    "bp_assets.txt",
    "manifest.txt",
)


def add_suffix(filename: str, suffix: str) -> str:
    if not suffix:
        return filename

    suffix = suffix.removeprefix("_")
    path = Path(filename)

    return f"{path.stem}_{suffix}{path.suffix}"


def collect_files(
    stage_folders: list[str],
    suffix: str,
) -> list[tuple[Path, Path]]:
    files_to_copy: list[tuple[Path, Path]] = []

    for stage_folder in stage_folders:
        for region in ("eu", "jp"):
            source_folder = (
                MGS2_ROOT
                / region
                / "stage"
                / stage_folder
            )

            if not source_folder.is_dir():
                print(f"[MISSING FOLDER] {source_folder}")
                continue

            for filename in VALID_FILENAMES:
                source_file = source_folder / filename
                backup_file = source_folder / f"{filename}.vortex_backup"

                if backup_file.is_file():
                    selected_source = backup_file
                elif source_file.is_file():
                    selected_source = source_file
                else:
                    print(f"[MISSING FILE] {source_file}")
                    continue

                destination_filename = add_suffix(filename, suffix)

                destination_file = (
                    OUTPUT_ROOT
                    / region
                    / "stage"
                    / stage_folder
                    / destination_filename
                )

                files_to_copy.append(
                    (selected_source, destination_file)
                )

    return files_to_copy


def copy_file(
    source_file: Path,
    destination_file: Path,
) -> None:
    destination_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source_file,
        destination_file,
    )


def main() -> None:
    stage_input = input(
        "Enter stage folders separated by commas: "
    ).strip()

    if not stage_input:
        print("No stage folders entered.")
        return

    stage_folders = [
        stage.strip()
        for stage in stage_input.split(",")
        if stage.strip()
    ]

    suffix = input(
        "Enter output filename suffix, or leave blank: "
    ).strip()

    files_to_copy = collect_files(
        stage_folders,
        suffix,
    )

    if not files_to_copy:
        print("No bp_assets.txt or manifest.txt files found.")
        return

    copied_count = 0
    failed_count = 0

    print()
    print(f"Copying {len(files_to_copy)} files...")

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:
        futures = {
            executor.submit(
                copy_file,
                source,
                destination,
            ): (source, destination)
            for source, destination in files_to_copy
        }

        for future in as_completed(futures):
            source, destination = futures[future]

            try:
                future.result()
                copied_count += 1

                relative_destination = (
                    destination.relative_to(OUTPUT_ROOT)
                )

                if source.name.lower().endswith(
                    ".vortex_backup"
                ):
                    print(
                        f"[BACKUP] {relative_destination}"
                    )
                else:
                    print(
                        f"[COPIED] {relative_destination}"
                    )

            except Exception as exception:
                failed_count += 1
                print(
                    f"[FAILED] {source}: {exception}"
                )

    print()
    print(f"Copied: {copied_count}")
    print(f"Failed: {failed_count}")
    print(f"Output: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()