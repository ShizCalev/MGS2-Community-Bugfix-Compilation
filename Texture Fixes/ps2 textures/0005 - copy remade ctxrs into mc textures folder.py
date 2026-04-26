from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from tqdm import tqdm

NEXT_SCRIPT_2 = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\0009 - find incorrect ps2 to mc alpha levels.py"
)

MC_DIMENSIONS_CSV = Path(
    r"C:\Development\Git\MGS2-PS2-Textures\Tri-Dumped\Master Collection\Metadata\mgs2_mc_dimensions_including_override_folders.csv"
)
MC_TEXTURES_DIR = Path(r"G:\Steam\steamapps\common\MGS2\textures\flatlist")
BASE_TEXTURES_DIR = Path(r"D:\MG Textures\MGS2\Base Textures\textures\flatlist")
BASE_TEXTURES_WIN_DIR = Path(r"D:\MG Textures\MGS2\Base Textures\textures\flatlist\_win")

PS2_OPAQUE_DIR = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\OPAQUE"
)
PS2_HAS_ALPHA_DIR = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\HAS ALPHA"
)
MANUAL_OPAQUE_TEXTURES_TXT = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_opaque_textures.txt"
)

MC_OPAQUE_DIR = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\mc textures\OPAQUE"
)
MC_HAS_ALPHA_DIR = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\mc textures\HAS ALPHA"
)
MC_NOT_DUMPED_DIR = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\mc textures\not dumped"
)

NO_MIP_REGEX_FILE = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\no_mip_regex.txt"
)
DXT5_STEMS_FILE = Path(
    r"C:\Development\Git\MGS2-PS2-Textures\Tri-Dumped\Master Collection\Metadata\mgs2_mc_dxt5_stems.txt"
)
MANUAL_UI_FILE = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_ui_textures.txt"
)
MANUAL_BP_REMADE_FILE = Path(
    r"C:\Development\Git\MGS2-PS2-Textures\Tri-Dumped\Master Collection\Metadata\mgs2_mc_manually_identified_bp_remade.txt"
)

CSV_TEXTURE_NAME_COLUMN = "texture_name"
CSV_CTXR_SHA1_COLUMN = "mc_ctxr_sha1"
CSV_RESAVED_SHA1_COLUMN = "mc_resaved_sha1"
CSV_RELATIVE_PATH_COLUMN = "relative_path"
CSV_MC_WIDTH_COLUMN = "mc_width"
CSV_MC_HEIGHT_COLUMN = "mc_height"

MAX_WORKERS = os.cpu_count() or 8
SHA1_BUFFER_SIZE = 8 * 1024 * 1024

PRIMARY_BUCKETS = {
    "manual",
    "bp_remade",
    "mismatched sha1",
    "bp_mismatch",
    "bp_remade",
}

NO_MIP_ROOT = "no_mip_fixes"
NO_MIP_CHILDREN = {"ui", "not_regex_matched_ui"}

MANUAL_LIST = {
    "0015d707",
    "0015d707_cd82fa959c0f81d19f22c0b0fdf8d230",
    "008ae623",
    "008ae623_fad237f35f44f84013d072b01d34bfc0",
}


def pause_and_exit(exit_code: int) -> None:
    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass

    raise SystemExit(exit_code)


def sha1_of_file(path: Path) -> str:
    h = hashlib.sha1()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(SHA1_BUFFER_SIZE), b""):
            h.update(chunk)

    return h.hexdigest().lower()


def atomic_copy2(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(dst.parent),
        prefix=f"{dst.name}.tmp.",
        suffix=".part",
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        shutil.copy2(src, tmp_path)
        os.replace(tmp_path, dst)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def remove_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return

    for current_root, dir_names, file_names in os.walk(root, topdown=False):
        current_path = Path(current_root)

        if dir_names or file_names:
            try:
                next(current_path.iterdir())
                continue
            except StopIteration:
                pass

        try:
            current_path.rmdir()
        except OSError:
            pass


def load_expected(csv_path: Path) -> dict[str, dict[str, str | int]]:
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    result: dict[str, dict[str, str | int]] = {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for col in (
            CSV_TEXTURE_NAME_COLUMN,
            CSV_CTXR_SHA1_COLUMN,
            CSV_RESAVED_SHA1_COLUMN,
            CSV_RELATIVE_PATH_COLUMN,
            CSV_MC_WIDTH_COLUMN,
            CSV_MC_HEIGHT_COLUMN,
        ):
            if col not in reader.fieldnames:
                raise ValueError(f"Missing column: {col}")

        for i, row in enumerate(reader, start=2):
            stem = (row.get(CSV_TEXTURE_NAME_COLUMN) or "").strip()
            ctxr_sha1 = (row.get(CSV_CTXR_SHA1_COLUMN) or "").strip().lower()
            resaved_sha1 = (row.get(CSV_RESAVED_SHA1_COLUMN) or "").strip().lower()
            rel = (row.get(CSV_RELATIVE_PATH_COLUMN) or "").strip()

            if not stem:
                raise ValueError(f"Blank texture_name at row {i}")

            if not ctxr_sha1:
                raise ValueError(f"Blank mc_ctxr_sha1 for {stem} at row {i}")

            if not resaved_sha1:
                raise ValueError(f"Blank mc_resaved_sha1 for {stem} at row {i}")

            try:
                mc_width = int((row.get(CSV_MC_WIDTH_COLUMN) or "").strip())
                mc_height = int((row.get(CSV_MC_HEIGHT_COLUMN) or "").strip())
            except ValueError:
                raise ValueError(f"Invalid mc_width/mc_height for {stem} at row {i}")

            key = f"{rel}{stem}" if rel else stem

            if key in result:
                raise ValueError(f"Duplicate texture at row {i}: {key}")

            result[key] = {
                "ctxr_sha1": ctxr_sha1,
                "resaved_sha1": resaved_sha1,
                "relative_path": rel,
                "texture_name": stem,
                "mc_width": mc_width,
                "mc_height": mc_height,
            }

    return result


def collect_ctxr_files(root: Path) -> dict[str, list[Path]]:
    files = list(root.rglob("*.ctxr"))
    key_map: dict[str, list[Path]] = {}

    for f in files:
        rel_dir = f.parent.relative_to(root)
        rel_str = str(rel_dir).replace("\\", "/")

        if rel_str == ".":
            rel_str = ""
        else:
            rel_str = rel_str + "/"

        key = f"{rel_str}{f.stem}"
        key_map.setdefault(key, []).append(f)

    return key_map


def validate_ctxr_entry(
    key: str,
    expected_sha1: str,
    paths: list[Path] | None,
) -> list[str]:
    errors: list[str] = []

    if not paths:
        errors.append(f"[MISSING ON DISK] {key}")
        return errors

    if len(paths) > 1:
        errors.append(f"[DUPLICATE] {key}")
        for p in sorted(paths):
            errors.append(f"  {p}")

    base_path = sorted(paths)[0]
    backup_path = base_path.with_suffix(base_path.suffix + ".vortex_backup")

    if not backup_path.exists() and base_path.is_symlink():
        return errors

    try_paths: list[tuple[str, Path]] = []

    if backup_path.exists():
        try_paths.append(("backup", backup_path))

    try_paths.append(("main", base_path))

    matched = False
    checked_hashes: list[str] = []

    for label, path in try_paths:
        try:
            file_sha1 = sha1_of_file(path)
        except Exception as e:
            errors.append(f"[HASH ERROR] {path}: {e}")
            continue

        checked_hashes.append(f"{label}:{file_sha1}")

        if file_sha1 == expected_sha1:
            matched = True
            break

    if not matched:
        errors.append(f"[SHA1 MISMATCH] {key}")
        errors.append(f"  expected: {expected_sha1}")
        for h in checked_hashes:
            errors.append(f"  got: {h}")
        for _, p in try_paths:
            errors.append(f"  checked: {p}")

    return errors


def collect_png_files(root: Path, expected: dict[str, dict[str, str | int]]) -> dict[str, list[Path]]:
    key_map: dict[str, list[Path]] = {}
    rel_paths = {str(entry["relative_path"]) for entry in expected.values()}

    for rel in rel_paths:
        if rel:
            scan_dir = root / rel.rstrip("/")
        else:
            scan_dir = root

        if not scan_dir.is_dir():
            continue

        files = scan_dir.glob("*.png")

        for f in files:
            key = f"{rel}{f.stem}"
            key_map.setdefault(key, []).append(f)

    return key_map


def validate_png_entry(
    key: str,
    expected_sha1: str,
    paths: list[Path] | None,
) -> list[str]:
    errors: list[str] = []

    if not paths:
        errors.append(f"[MISSING ON DISK] {key}")
        return errors

    if len(paths) > 1:
        errors.append(f"[DUPLICATE] {key}")
        for p in sorted(paths):
            errors.append(f"  {p}")

    base_path = sorted(paths)[0]

    try:
        file_sha1 = sha1_of_file(base_path)
    except Exception as e:
        errors.append(f"[HASH ERROR] {base_path}: {e}")
        return errors

    if file_sha1 != expected_sha1:
        errors.append(f"[SHA1 MISMATCH] {key}")
        errors.append(f"  expected: {expected_sha1}")
        errors.append(f"  got:      {file_sha1}")
        errors.append(f"  checked:  {base_path}")

    return errors


def run_threaded_validation(
    label: str,
    keys_to_check: list[str],
    submit_fn,
) -> list[str]:
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(submit_fn, key): key for key in keys_to_check}

        with tqdm(
            total=len(futures),
            desc=label,
            unit="file",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            for future in as_completed(futures):
                errors.extend(future.result())
                pbar.update(1)

    return errors


def build_base_png_name_map(root: Path) -> dict[str, list[Path]]:
    if not root.is_dir():
        raise FileNotFoundError(root)

    result: dict[str, list[Path]] = {}

    for path in root.rglob("*.png"):
        if not path.is_file():
            continue

        key = path.name.lower()
        result.setdefault(key, []).append(path)

    return result


def build_ps2_bucket_stem_set(*roots: Path) -> set[str]:
    stems: set[str] = set()

    for root in roots:
        if not root.is_dir():
            raise FileNotFoundError(root)

        for path in root.rglob("*.png"):
            if not path.is_file():
                continue
            stems.add(path.stem.lower())

    return stems


def load_manual_opaque_stems(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(path)

    stems: set[str] = set()

    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            normalized = line.replace("\\", "/").rstrip("/")
            stem = Path(normalized).stem.strip().lower()

            if not stem:
                raise ValueError(f"Blank manual opaque entry at line {line_number}")

            stems.add(stem)

    return stems


def load_stem_list(path: Path) -> set[str]:
    stems: set[str] = set()

    if not path.is_file():
        return stems

    with path.open("r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip().lower()
            if not line or line.startswith("#"):
                continue
            stems.add(line)

    return stems


def load_no_mip_patterns(path: Path) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []

    if not path.is_file():
        return patterns

    with path.open("r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                patterns.append(re.compile(line, re.IGNORECASE))
            except re.error as e:
                raise ValueError(f"Invalid regex in {path}: {line} ({e})")

    return patterns


def matches_no_mip_patterns(filename_no_ext: str, patterns: list[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        if pattern.search(filename_no_ext):
            return True
    return False


def next_power_of_two(n: int) -> int:
    return 1 if n <= 0 else 1 << (n - 1).bit_length()


def is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def image_is_effectively_opaque(path: Path) -> bool:
    with Image.open(path) as img:
        if "A" not in img.getbands():
            return True

        if img.mode not in ("RGBA", "LA"):
            img = img.convert("RGBA")

        alpha = img.getchannel("A")
        min_alpha, _ = alpha.getextrema()

        return min_alpha >= 128


def classify_primary_buckets_for_not_dumped(
    file_path: Path,
    stem: str,
    expected_entry: dict[str, str | int] | None,
    manual_bp_remade_set: set[str],
) -> list[str]:
    buckets: list[str] = []

    if stem in MANUAL_LIST:
        buckets.append("manual")

    if stem in manual_bp_remade_set:
        buckets.append("bp_remade")
        return buckets

    if not expected_entry:
        return buckets

    mc_resaved_sha1 = str(expected_entry["resaved_sha1"])
    mc_width = int(expected_entry["mc_width"])
    mc_height = int(expected_entry["mc_height"])

    try:
        file_sha1 = sha1_of_file(file_path)

        if mc_resaved_sha1 and file_sha1 == mc_resaved_sha1:
            buckets.append("bp_remade")
            return buckets

        with Image.open(file_path) as img:
            width, height = img.size
    except Exception as e:
        raise RuntimeError(f"primary classification failed for {file_path}: {e}") from e

    if mc_width > next_power_of_two(width) or mc_height > next_power_of_two(height):
        buckets.append("bp_remade")
        return buckets

    pow2_w = next_power_of_two(width)
    pow2_h = next_power_of_two(height)

    if mc_width < pow2_w or mc_height < pow2_h:
        buckets.append("bp_mismatch")
        return buckets

    if is_power_of_two(width) and is_power_of_two(height):
        buckets.append("mismatched sha1")
        return buckets

    return buckets


def classify_no_mip_bucket_for_not_dumped(
    stem: str,
    expected_entry: dict[str, str | int] | None,
    patterns: list[re.Pattern[str]],
    manual_ui_set: set[str],
) -> tuple[str, str | None] | None:
    matched_regex = matches_no_mip_patterns(stem, patterns)

    if not expected_entry:
        if matched_regex:
            return (NO_MIP_ROOT, None)
        return None

    mc_width = int(expected_entry["mc_width"])
    mc_height = int(expected_entry["mc_height"])
    is_npot = not is_power_of_two(mc_width) or not is_power_of_two(mc_height)

    if stem in manual_ui_set:
        return (NO_MIP_ROOT, "ui")

    if is_npot:
        if matched_regex:
            return (NO_MIP_ROOT, "ui")
        return (NO_MIP_ROOT, "not_regex_matched_ui")

    if matched_regex:
        return (NO_MIP_ROOT, None)

    return None


def classify_not_dumped_relative_dest(
    source_png: Path,
    expected_entry: dict[str, str | int],
    manual_opaque_stems: set[str],
    dxt5_stems: set[str],
    manual_bp_remade_set: set[str],
    patterns: list[re.Pattern[str]],
    manual_ui_set: set[str],
) -> Path:
    stem = source_png.stem.lower()

    if stem in manual_opaque_stems or image_is_effectively_opaque(source_png):
        bucket_parts: list[str] = ["OPAQUE"]
    else:
        bucket_parts = ["HAS ALPHA"]

    if stem in dxt5_stems:
        bucket_parts.append("dxt5")

    primary_buckets = classify_primary_buckets_for_not_dumped(
        file_path=source_png,
        stem=stem,
        expected_entry=expected_entry,
        manual_bp_remade_set=manual_bp_remade_set,
    )
    bucket_parts.extend(primary_buckets)

    no_mip_bucket = classify_no_mip_bucket_for_not_dumped(
        stem=stem,
        expected_entry=expected_entry,
        patterns=patterns,
        manual_ui_set=manual_ui_set,
    )
    if no_mip_bucket:
        bucket_parts.append(no_mip_bucket[0])
        if no_mip_bucket[1]:
            bucket_parts.append(no_mip_bucket[1])

    return Path(*bucket_parts) / f"{expected_entry['texture_name']}.png"


def build_bp_remade_sync_entries(
    ps2_root: Path,
    mc_root: Path,
    base_name_map: dict[str, list[Path]],
) -> tuple[list[tuple[Path, Path, Path]], list[str], set[Path]]:
    if not ps2_root.is_dir():
        raise FileNotFoundError(ps2_root)

    operations: list[tuple[Path, Path, Path]] = []
    errors: list[str] = []
    expected_dest_files: set[Path] = set()

    for ps2_png in sorted(ps2_root.rglob("*.png")):
        if not ps2_png.is_file():
            continue

        rel = ps2_png.relative_to(ps2_root)
        rel_posix = rel.as_posix().lower()

        if "/bp_remade/" not in f"/{rel_posix}":
            continue

        dest = mc_root / rel
        expected_dest_files.add(dest.resolve())

        matches = base_name_map.get(ps2_png.name.lower(), [])

        if not matches:
            errors.append(
                f"[SYNC MISSING BASE PNG] {ps2_png.name} required by {ps2_png}"
            )
            continue

        if len(matches) > 1:
            errors.append(f"[SYNC DUPLICATE BASE PNG] {ps2_png.name}")
            for match in sorted(matches):
                errors.append(f"  {match}")
            errors.append(f"  required by: {ps2_png}")
            continue

        operations.append((matches[0], dest, ps2_png))

    return operations, errors, expected_dest_files


def build_not_dumped_sync_entries(
    expected: dict[str, dict[str, str | int]],
    ps2_bucket_stems: set[str],
    base_name_map: dict[str, list[Path]],
    mc_root: Path,
    manual_opaque_stems: set[str],
    dxt5_stems: set[str],
    manual_bp_remade_set: set[str],
    patterns: list[re.Pattern[str]],
    manual_ui_set: set[str],
) -> tuple[list[tuple[Path, Path, str]], list[str], set[Path]]:
    operations: list[tuple[Path, Path, str]] = []
    errors: list[str] = []
    expected_dest_files: set[Path] = set()

    for key, entry in sorted(expected.items()):
        rel = str(entry["relative_path"])
        stem = str(entry["texture_name"])

        if rel != "_win/":
            continue

        if stem.lower() in ps2_bucket_stems:
            continue

        matches = base_name_map.get(f"{stem}.png".lower(), [])

        if not matches:
            errors.append(f"[NOT DUMPED MISSING BASE PNG] _win/{stem}")
            continue

        if len(matches) > 1:
            errors.append(f"[NOT DUMPED DUPLICATE BASE PNG] _win/{stem}")
            for match in sorted(matches):
                errors.append(f"  {match}")
            continue

        source_png = matches[0]

        try:
            rel_dest = classify_not_dumped_relative_dest(
                source_png=source_png,
                expected_entry=entry,
                manual_opaque_stems=manual_opaque_stems,
                dxt5_stems=dxt5_stems,
                manual_bp_remade_set=manual_bp_remade_set,
                patterns=patterns,
                manual_ui_set=manual_ui_set,
            )
        except Exception as e:
            errors.append(f"[NOT DUMPED CLASSIFY ERROR] {source_png}: {e}")
            continue

        dest = mc_root / rel_dest
        expected_dest_files.add(dest.resolve())
        operations.append((source_png, dest, stem))

    return operations, errors, expected_dest_files


def sync_one_file(src: Path, dest: Path) -> tuple[str, Path]:
    if dest.exists():
        try:
            if sha1_of_file(src) == sha1_of_file(dest):
                return ("unchanged", dest)
        except Exception:
            pass

    atomic_copy2(src, dest)
    return ("copied", dest)


def delete_stray_files(mc_root: Path, expected_dest_files: set[Path]) -> tuple[int, list[str]]:
    removed = 0
    errors: list[str] = []

    if not mc_root.is_dir():
        return removed, errors

    for path in sorted(mc_root.rglob("*")):
        if not path.is_file():
            continue

        resolved = path.resolve()
        if resolved in expected_dest_files:
            continue

        try:
            path.unlink()
            removed += 1
        except Exception as e:
            errors.append(f"[DELETE ERROR] {path}: {e}")

    remove_empty_dirs(mc_root)
    return removed, errors


def run_bp_remade_sync_stage(
    ps2_root: Path,
    mc_root: Path,
    base_name_map: dict[str, list[Path]],
) -> list[str]:
    print(f"\nPreparing sync: {ps2_root} -> {mc_root}")

    errors: list[str] = []

    try:
        operations, prep_errors, expected_dest_files = build_bp_remade_sync_entries(
            ps2_root,
            mc_root,
            base_name_map,
        )
    except Exception as e:
        return [f"[SYNC PREP ERROR] {ps2_root} -> {mc_root}: {e}"]

    errors.extend(prep_errors)

    if errors:
        return errors

    copied = 0
    unchanged = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(sync_one_file, src, dest): (src, dest, ps2_png)
            for src, dest, ps2_png in operations
        }

        with tqdm(
            total=len(futures),
            desc=f"Syncing {mc_root.name}",
            unit="file",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            for future in as_completed(futures):
                src, dest, ps2_png = futures[future]

                try:
                    status, _ = future.result()
                except Exception as e:
                    errors.append(f"[SYNC COPY ERROR] {src} -> {dest}: {e}")
                    pbar.update(1)
                    continue

                if status == "copied":
                    copied += 1
                else:
                    unchanged += 1

                pbar.update(1)

    removed, delete_errors = delete_stray_files(mc_root, expected_dest_files)
    errors.extend(delete_errors)

    print(
        f"  planned: {len(operations)} | copied: {copied} | unchanged: {unchanged} | removed stray: {removed}"
    )

    return errors


def run_not_dumped_sync_stage(
    expected: dict[str, dict[str, str | int]],
    ps2_bucket_stems: set[str],
    base_name_map: dict[str, list[Path]],
    mc_root: Path,
    manual_opaque_stems: set[str],
    dxt5_stems: set[str],
    manual_bp_remade_set: set[str],
    patterns: list[re.Pattern[str]],
    manual_ui_set: set[str],
) -> list[str]:
    print(f"\nPreparing sync: missing PS2 bucket textures -> {mc_root}")

    errors: list[str] = []

    try:
        operations, prep_errors, expected_dest_files = build_not_dumped_sync_entries(
            expected,
            ps2_bucket_stems,
            base_name_map,
            mc_root,
            manual_opaque_stems,
            dxt5_stems,
            manual_bp_remade_set,
            patterns,
            manual_ui_set,
        )
    except Exception as e:
        return [f"[NOT DUMPED SYNC PREP ERROR] {mc_root}: {e}"]

    errors.extend(prep_errors)

    if errors:
        return errors

    copied = 0
    unchanged = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(sync_one_file, src, dest): (src, dest, stem)
            for src, dest, stem in operations
        }

        with tqdm(
            total=len(futures),
            desc=f"Syncing {mc_root.name}",
            unit="file",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            for future in as_completed(futures):
                src, dest, stem = futures[future]

                try:
                    status, _ = future.result()
                except Exception as e:
                    errors.append(f"[NOT DUMPED SYNC COPY ERROR] {src} -> {dest}: {e}")
                    pbar.update(1)
                    continue

                if status == "copied":
                    copied += 1
                else:
                    unchanged += 1

                pbar.update(1)

    removed, delete_errors = delete_stray_files(mc_root, expected_dest_files)
    errors.extend(delete_errors)

    print(
        f"  planned: {len(operations)} | copied: {copied} | unchanged: {unchanged} | removed stray: {removed}"
    )

    return errors

# ==========================================================
# STAGE RUNNER
# ==========================================================
def run_next_stage(script_path):
    """Run the next Python script, handling output and errors cleanly."""
    print(f"\n[+] Launching next stage: {os.path.basename(script_path)}")

    try:
        subprocess.run(["python", script_path], check=True)
        print(f"[✓] Stage completed successfully: {os.path.basename(script_path)}")
    except subprocess.CalledProcessError as e:
        print(f"[!] Stage failed with non-zero exit code ({e.returncode}): {script_path}")
    except FileNotFoundError:
        print(f"[!] Stage script not found: {script_path}")
    except Exception as e:
        print(f"[!] Failed to launch next stage ({script_path}): {e}")
        

def main() -> None:
    print("Loading CSV...")
    try:
        expected = load_expected(MC_DIMENSIONS_CSV)
    except Exception as e:
        print(f"[ERROR] {e}")
        pause_and_exit(1)

    print("Loading manual opaque texture list...")
    try:
        manual_opaque_stems = load_manual_opaque_stems(MANUAL_OPAQUE_TEXTURES_TXT)
    except Exception as e:
        print(f"[ERROR] Failed to load manual opaque texture list: {e}")
        pause_and_exit(1)

    print("Loading additional classification inputs...")
    try:
        dxt5_stems = load_stem_list(DXT5_STEMS_FILE)
        manual_bp_remade_set = load_stem_list(MANUAL_BP_REMADE_FILE)
        manual_ui_set = load_stem_list(MANUAL_UI_FILE)
        patterns = load_no_mip_patterns(NO_MIP_REGEX_FILE)
    except Exception as e:
        print(f"[ERROR] Failed to load additional classification inputs: {e}")
        pause_and_exit(1)

    all_errors: list[str] = []

    print("\nScanning .ctxr files on disk...")
    try:
        ctxr_map = collect_ctxr_files(MC_TEXTURES_DIR)
    except Exception as e:
        print(f"[ERROR] {e}")
        pause_and_exit(1)

    ctxr_errors: list[str] = []

    expected_keys = set(expected.keys())
    ctxr_keys = set(ctxr_map.keys())

    for key in sorted(ctxr_keys - expected_keys):
        for p in ctxr_map.get(key, []):
            backup = p.with_suffix(p.suffix + ".vortex_backup")
            if not backup.exists() and p.is_symlink():
                continue
            ctxr_errors.append(f"[NOT IN CSV] {key} -> {p}")

    for key in sorted(expected_keys - ctxr_keys):
        ctxr_errors.append(f"[MISSING ON DISK] {key}")

    ctxr_to_check = sorted(expected_keys & ctxr_keys)
    ctxr_errors.extend(
        run_threaded_validation(
            "Validating CTXR SHA1",
            ctxr_to_check,
            lambda key: validate_ctxr_entry(key, str(expected[key]["ctxr_sha1"]), ctxr_map.get(key)),
        )
    )

    print(f"  CSV entries: {len(expected_keys)}")
    print(f"  .ctxr files on disk: {len(ctxr_keys)}")

    if ctxr_errors:
        all_errors.append("=== CTXR ERRORS ===")
        all_errors.extend(ctxr_errors)

    print("\nScanning .png files on disk...")
    try:
        png_map = collect_png_files(BASE_TEXTURES_DIR, expected)
    except Exception as e:
        print(f"[ERROR] {e}")
        pause_and_exit(1)

    png_errors: list[str] = []

    png_keys = set(png_map.keys())

    for key in sorted(png_keys - expected_keys):
        for p in png_map.get(key, []):
            png_errors.append(f"[NOT IN CSV] {key} -> {p}")

    for key in sorted(expected_keys - png_keys):
        png_errors.append(f"[MISSING ON DISK] {key}")

    png_to_check = sorted(expected_keys & png_keys)
    png_errors.extend(
        run_threaded_validation(
            "Validating PNG SHA1",
            png_to_check,
            lambda key: validate_png_entry(key, str(expected[key]["resaved_sha1"]), png_map.get(key)),
        )
    )

    print(f"  CSV entries: {len(expected_keys)}")
    print(f"  .png files on disk: {len(png_keys)}")

    if png_errors:
        all_errors.append("=== PNG ERRORS ===")
        all_errors.extend(png_errors)

    if all_errors:
        print("\nValidation failed:\n")
        print("\n".join(all_errors))
        pause_and_exit(1)

    print("\nAll validation passed.")

    print("\nBuilding PS2 bucket stem set...")
    try:
        ps2_bucket_stems = build_ps2_bucket_stem_set(PS2_OPAQUE_DIR, PS2_HAS_ALPHA_DIR)
    except Exception as e:
        print(f"[ERROR] Failed to build PS2 bucket stem set: {e}")
        pause_and_exit(1)

    print("\nBuilding base-texture filename map...")
    try:
        base_name_map = build_base_png_name_map(BASE_TEXTURES_WIN_DIR)
    except Exception as e:
        print(f"[ERROR] Failed to build base-texture filename map: {e}")
        pause_and_exit(1)

    sync_errors: list[str] = []

    sync_errors.extend(run_bp_remade_sync_stage(PS2_OPAQUE_DIR, MC_OPAQUE_DIR, base_name_map))
    sync_errors.extend(run_bp_remade_sync_stage(PS2_HAS_ALPHA_DIR, MC_HAS_ALPHA_DIR, base_name_map))
    sync_errors.extend(
        run_not_dumped_sync_stage(
            expected,
            ps2_bucket_stems,
            base_name_map,
            MC_NOT_DUMPED_DIR,
            manual_opaque_stems,
            dxt5_stems,
            manual_bp_remade_set,
            patterns,
            manual_ui_set,
        )
    )

    if sync_errors:
        print("\nSync failed:\n")
        print("\n".join(sync_errors))
        pause_and_exit(1)

    print("\nSync completed successfully.")
    run_next_stage(NEXT_SCRIPT_2)


if __name__ == "__main__":
    main()