from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================================
# CONFIG
# ==========================================================
SCRIPT_DIR = Path(__file__).resolve().parent

FOLDERS_TXT_NAME = "folders to process.txt"
STAGING_MAIN_NAME = "_staging_main.py"

# Shared main script that lives next to THIS orchestrator
STAGING_MAIN_PATH = SCRIPT_DIR / STAGING_MAIN_NAME

# Script to run AFTER all staging tiers finish
SET_CTXR_DATES_NAME = "set_ctxr_modified_dates.py"
SET_CTXR_DATES_PATH = SCRIPT_DIR / SET_CTXR_DATES_NAME

# How many jobs to run in parallel within each staging tier
THREADS_PER_TIER = 4

CONVERSION_CSV_NAME = "conversion_hashes.csv"
CONVERSION_CSV_HEADER = "filename,before_hash,ctxr_hash,mipmaps,origin_folder,opacity_stripped,upscaled\n"

NOT_IN_FOLDER_CSV_NAME = "not_in_folder.csv"
UNPROCESSED_FOLDERS_CSV_NAME = "unprocessed_folders.csv"

# Relative location of never_upscale.txt inside the git repo
NEVER_UPSCALE_REL_PATH = Path("Texture Fixes") / "never_upscale.txt"

FIND_UNCONVERTED_SCRIPT = SCRIPT_DIR / "mc textures" / "find unconverted.py"

# ==========================================================
# PRE-FLIGHT VALIDATION (manual_ui_textures vs no_mip_regex)
# ==========================================================
MANUAL_UI_TEXTURES_TXT = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_ui_textures.txt"
)
NO_MIP_REGEX_TXT = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\no_mip_regex.txt"
)

# ==========================================================
# CTXR3 WAITING
# ==========================================================
# If _launch_ctxr3.py spawns CTXR3 and exits, we must wait here.
WAIT_FOR_CTXR3_EXE_NAMES = [
    "ctxr3.exe",
]

CTXR3_WAIT_POLL_SECONDS = 1.0


# ==========================================================
# HARDCODED STAGING ROOTS
# ==========================================================
BUGFIX_ROOT = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes")
DEMASTER_ROOT = Path(r"C:\Development\Git\MGS2-Demastered-Substance-Edition\Textures")
UPSCALED_UI_ROOT = Path(r"C:\Development\Git\MGS2-Upscaled-UI-Textures\Textures")

STAGING_ROOTS: list[Path] = [
    # Bugfix Compilation
    BUGFIX_ROOT / "Staging",
    BUGFIX_ROOT / "Staging - 2x Upscaled",
    BUGFIX_ROOT / "Staging - 4x Upscaled",
    # Demastered pack
    DEMASTER_ROOT / "Staging",
    DEMASTER_ROOT / "Staging - 2x Upscaled",
    DEMASTER_ROOT / "Staging - 4x Upscaled",
    DEMASTER_ROOT / "Staging - UI",
    DEMASTER_ROOT / "Staging - UI - 2x Upscaled",
    DEMASTER_ROOT / "Staging - UI - 4x Upscaled",
    # Upscaled UI pack (2x / 4x only)
    UPSCALED_UI_ROOT / "Staging - 2x Upscaled",
    UPSCALED_UI_ROOT / "Staging - 4x Upscaled",
]

# Self Remade Finalized folder and output CSV name
SELF_REMADE_FINALIZED_DIR = BUGFIX_ROOT / "Self Remade" / "Finalized"
SELF_REMADE_MODIFIED_DATES_CSV_NAME = "self_remade_modified_dates.csv"

# ==========================================================
# BUILD_DIST_FOLDERS.py FILE SYNC
# ==========================================================
BUILD_DIST_SOURCE = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Build_Dist_Folders.py")

BUILD_DIST_COPIES: list[Path] = [
    Path(r"C:\Development\Git\MGS2-Demastered-Substance-Edition\Build_Dist_Folders.py"),
    Path(r"C:\Development\Git\MGS2-Upscaled-UI-Textures\Build_Dist_Folders.py"),
    # Add more targets here
]


def pause_and_exit(code: int = 1) -> None:
    try:
        input("\nPress ENTER to exit...")
    except KeyboardInterrupt:
        pass
    raise SystemExit(code)


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ==========================================================
# PRE-FLIGHT VALIDATION HELPERS
# ==========================================================
def _read_noncomment_lines(path: Path) -> list[str]:
    """
    Read text file lines, stripping whitespace.
    Ignores empty lines and lines starting with '#'.
    """
    if not path.is_file():
        print(f"[ERROR] Required file missing: {path}")
        pause_and_exit(1)

    out: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                out.append(raw)
    except OSError as e:
        print(f"[ERROR] Failed to read {path}: {e}")
        pause_and_exit(1)

    return out


def load_manual_ui_stems(manual_ui_textures_txt: Path) -> set[str]:
    """
    Load stems from manual_ui_textures.txt.

    IMPORTANT:
    - Each non-comment line is already the exact stem string.
    - Do NOT strip extensions via Path(...).stem or any other parsing.
    """
    stems: set[str] = set()

    if not manual_ui_textures_txt.is_file():
        print(f"[ERROR] Required file missing: {manual_ui_textures_txt}")
        pause_and_exit(1)

    try:
        with manual_ui_textures_txt.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                stems.add(raw.lower())
    except OSError as e:
        print(f"[ERROR] Failed to read {manual_ui_textures_txt}: {e}")
        pause_and_exit(1)

    return stems


def load_no_mip_regexes(no_mip_regex_txt: Path) -> list[re.Pattern[str]]:
    """
    Load regex patterns from no_mip_regex.txt.
    Ignores empty/comment lines.
    Compiles with IGNORECASE.
    """
    patterns: list[re.Pattern[str]] = []

    if not no_mip_regex_txt.is_file():
        print(f"[ERROR] Required file missing: {no_mip_regex_txt}")
        pause_and_exit(1)

    try:
        with no_mip_regex_txt.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    patterns.append(re.compile(raw, re.IGNORECASE))
                except re.error as e:
                    print(f"[ERROR] Invalid regex in {no_mip_regex_txt}: '{raw}' ({e})")
                    pause_and_exit(1)
    except OSError as e:
        print(f"[ERROR] Failed to read {no_mip_regex_txt}: {e}")
        pause_and_exit(1)

    return patterns


def verify_manual_ui_covered_by_no_mip_regex() -> None:
    """
    Verify every stem listed in manual_ui_textures.txt is matched by at least one regex in no_mip_regex.txt.
    Aborts if any are not covered.
    """
    stems = load_manual_ui_stems(MANUAL_UI_TEXTURES_TXT)
    regexes = load_no_mip_regexes(NO_MIP_REGEX_TXT)

    if not stems:
        print(f"[WARN] No stems found in {MANUAL_UI_TEXTURES_TXT}. Skipping coverage validation.")
        return

    if not regexes:
        print(f"[ERROR] No regex patterns found in {NO_MIP_REGEX_TXT}. Cannot validate coverage.")
        pause_and_exit(1)

    missing: list[str] = []
    for stem in sorted(stems):
        matched = False
        for rx in regexes:
            if rx.search(stem) is not None:
                matched = True
                break
        if not matched:
            missing.append(stem)

    if missing:
        print("#################################################")
        print("[ERROR] manual_ui_textures.txt contains stem(s) not covered by no_mip_regex.txt:")
        print(f"  Manual list: {MANUAL_UI_TEXTURES_TXT}")
        print(f"  Regex list:  {NO_MIP_REGEX_TXT}")
        print("  Missing coverage for:")
        for s in missing:
            print(f"    - {s}")
        print("#################################################")
        pause_and_exit(1)

    print(f"[INFO] Pre-flight ok: {len(stems)} manual_ui stem(s) are covered by no_mip_regex.txt")


def sync_build_dist_files() -> None:
    """
    Copy Build_Dist_Folders.py from BUILD_DIST_SOURCE to each path in BUILD_DIST_COPIES
    if missing or if sha1 differs.
    """
    if not BUILD_DIST_SOURCE.is_file():
        print(f"[ERROR] Build_Dist_Folders.py source missing: {BUILD_DIST_SOURCE}")
        pause_and_exit(1)

    try:
        src_hash = _sha1_file(BUILD_DIST_SOURCE)
    except OSError as e:
        print(f"[ERROR] Failed to hash source Build_Dist_Folders.py: {BUILD_DIST_SOURCE} ({e})")
        pause_and_exit(1)

    for dst in BUILD_DIST_COPIES:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] Failed creating folder {dst.parent}: {e}")
            pause_and_exit(1)

        if dst.is_file():
            try:
                dst_hash = _sha1_file(dst)
            except OSError:
                dst_hash = None

            if dst_hash == src_hash:
                print(f"[INFO] Build_Dist_Folders.py already up to date: {dst}")
                continue
        elif dst.exists():
            print(f"[ERROR] Destination exists but is not a file: {dst}")
            pause_and_exit(1)

        try:
            shutil.copy2(BUILD_DIST_SOURCE, dst)
            print(f"[INFO] Synced Build_Dist_Folders.py -> {dst}")
        except OSError as e:
            print(f"[ERROR] Copy failed {BUILD_DIST_SOURCE} -> {dst}: {e}")
            pause_and_exit(1)


def run_find_unconverted() -> None:
    if not FIND_UNCONVERTED_SCRIPT.is_file():
        print(f"[ERROR] Required pre-flight script missing: {FIND_UNCONVERTED_SCRIPT}")
        pause_and_exit(1)

    print("#################################################")
    print(f"Running pre-flight check: {FIND_UNCONVERTED_SCRIPT}")
    print("#################################################")

    result = subprocess.run(
        [sys.executable, str(FIND_UNCONVERTED_SCRIPT)],
        cwd=str(SCRIPT_DIR),
    )

    if result.returncode == 1:
        print("[ERROR] find unconverted.py reported unconverted textures. Aborting.")
        pause_and_exit(1)

    if result.returncode != 0:
        print(f"[ERROR] find unconverted.py failed with exit code {result.returncode}")
        pause_and_exit(result.returncode)

    print("[INFO] Pre-flight check passed.")


# ==========================================================
# CTXR3 PROCESS WAIT HELPERS
# ==========================================================
def _tasklist_text() -> str:
    try:
        out = subprocess.check_output(
            ["tasklist"],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return out
    except Exception:
        return ""


def is_process_running_any(exe_names: list[str]) -> bool:
    """
    Returns True if any process in exe_names is currently running.
    Uses tasklist (Windows).
    """
    tl = _tasklist_text().lower()
    if not tl:
        return False

    for n in exe_names:
        nn = (n or "").strip().lower()
        if not nn:
            continue
        if nn in tl:
            return True

    return False


def wait_for_processes_to_exit(exe_names: list[str], context: str) -> None:
    """
    Block until none of the exe_names are running.
    """
    if not exe_names:
        return

    if not is_process_running_any(exe_names):
        return

    print(f"[WAIT] Detected running process(es) {exe_names} after {context}. Waiting for them to exit...")

    while is_process_running_any(exe_names):
        time.sleep(CTXR3_WAIT_POLL_SECONDS)

    print(f"[WAIT] All {exe_names} have exited. Continuing.")


# ==========================================================
# GIT / CSV HELPERS
# ==========================================================
def get_git_root() -> Path:
    """
    Use git to find the repository root.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("ERROR: git is not installed or not on PATH.")
        pause_and_exit(1)

    if result.returncode != 0:
        print("ERROR: Not inside a git repository.")
        stderr = result.stderr.strip()
        if stderr:
            print(stderr)
        pause_and_exit(1)

    root = Path(result.stdout.strip()).resolve()
    if not root.is_dir():
        print(f"ERROR: Git root reported by git does not exist: {root}")
        pause_and_exit(1)

    return root


def _normalize_newlines(b: bytes) -> bytes:
    # Treat CRLF/LF as equivalent so Windows newline differences don't force rewrites
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _write_bytes_if_changed(path: Path, new_bytes: bytes) -> bool:
    """
    Write file only if content differs (ignoring newline style).
    Returns True if written, False if skipped.
    """
    try:
        if path.is_file():
            old_bytes = path.read_bytes()
            if _normalize_newlines(old_bytes) == _normalize_newlines(new_bytes):
                return False
    except OSError:
        # If we can't read it, fall back to rewriting
        pass

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(new_bytes)
        os.replace(tmp, path)  # atomic replace on Windows too
        return True
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _build_csv_bytes(rows: list[list[str]]) -> bytes:
    """
    Build CSV bytes deterministically using LF.
    """
    import io

    buf = io.StringIO(newline="\n")
    w = csv.writer(buf, lineterminator="\n")
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def load_dimensions_names(dimensions_csv: Path) -> dict[str, str]:
    """
    Load texture_name entries from mgs2_ps2_dimensions.csv.

    Returns dict:
        logical_name_lower (full filename including .bmp) -> original texture_name
    """
    if not dimensions_csv.is_file():
        print(f"ERROR: Dimensions CSV not found at: {dimensions_csv}")
        pause_and_exit(1)

    names: dict[str, str] = {}
    with dimensions_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "texture_name" not in reader.fieldnames:
            print(f"ERROR: 'texture_name' column not found in {dimensions_csv}")
            pause_and_exit(1)

        for row in reader:
            name = (row.get("texture_name") or "").strip()
            if not name:
                continue

            key = name.lower()
            if key not in names:
                names[key] = name

    if not names:
        print(f"WARNING: No texture_name entries found in {dimensions_csv}")

    return names


def build_ps2_texture_index(ps2_root: Path) -> dict[str, Path]:
    """
    Index all .tga and .png files under 'Texture Fixes/ps2 textures',
    mapping lowercase Path(path).stem -> full path.
    """
    if not ps2_root.is_dir():
        print(f"WARNING: PS2 textures root does not exist: {ps2_root}")
        return {}

    index: dict[str, Path] = {}

    for ext in ("*.tga", "*.png"):
        for path in ps2_root.rglob(ext):
            if not path.is_file():
                continue
            key = path.stem.lower()
            if key not in index:
                index[key] = path

    if not index:
        print(f"WARNING: No .tga or .png files found under {ps2_root}")

    return index


def collect_converted_names(conversion_csv: Path) -> set[str]:
    """
    Read conversion_hashes.csv and collect lowercase full filenames from the 'filename' column.
    """
    names: set[str] = set()

    if not conversion_csv.is_file():
        print(f"WARNING: conversion_hashes.csv not found at {conversion_csv}, treating as empty.")
        return names

    with conversion_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "filename" not in (reader.fieldnames or []):
            print(f"WARNING: 'filename' column missing in {conversion_csv}, treating as no entries.")
            return names

        for row in reader:
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            names.add(filename.lower())

    return names


def load_never_upscale_stems(never_upscale_path: Path) -> set[str]:
    """
    Load logical names from never_upscale.txt.
    """
    stems: set[str] = set()

    if not never_upscale_path.is_file():
        print(f"[WARN] never_upscale.txt not found at {never_upscale_path}, no stems will be skipped.")
        return stems

    try:
        with never_upscale_path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                stems.add(raw.lower())
    except OSError as e:
        print(f"[ERROR] Failed to read never_upscale.txt at {never_upscale_path}: {e}")

    if stems:
        print(f"[INFO] Loaded {len(stems)} stem(s) from never_upscale.txt")

    return stems


def write_not_in_folder_csv(
    job_dir: Path,
    dim_names: dict[str, str],
    ps2_texture_index: dict[str, Path],
    never_upscale_stems: set[str],
) -> None:
    conversion_csv = job_dir / CONVERSION_CSV_NAME
    if not conversion_csv.is_file():
        print(f"[WARN] {CONVERSION_CSV_NAME} missing in job dir, skipping not_in_folder.csv: {job_dir}")
        return

    converted_names = collect_converted_names(conversion_csv)
    if not dim_names:
        print(f"[INFO] No dimension names loaded, skipping not_in_folder for {job_dir}")
        return

    output_csv = job_dir / NOT_IN_FOLDER_CSV_NAME
    output_folders_csv = job_dir / UNPROCESSED_FOLDERS_CSV_NAME

    rows: list[tuple[str, str]] = []

    for logical_name_lower in sorted(dim_names.keys()):
        if logical_name_lower in converted_names:
            continue

        if logical_name_lower in never_upscale_stems:
            continue

        original_name = dim_names[logical_name_lower]

        stem_key = original_name.lower()
        tex_path = ps2_texture_index.get(stem_key)
        full_path_str = str(tex_path) if tex_path is not None else ""

        rows.append((original_name, full_path_str))

    not_in_rows: list[list[str]] = [["filename", "full_path"]]
    for filename, full_path in rows:
        not_in_rows.append([filename, full_path])
    not_in_bytes = _build_csv_bytes(not_in_rows)

    folder_set: set[str] = set()
    for _, full_path in rows:
        if not full_path:
            continue
        folder_set.add(str(Path(full_path).parent))

    folders_rows: list[list[str]] = [["folder"]]
    for folder in sorted(folder_set):
        folders_rows.append([folder])
    folders_bytes = _build_csv_bytes(folders_rows)

    wrote_not_in = _write_bytes_if_changed(output_csv, not_in_bytes)
    wrote_folders = _write_bytes_if_changed(output_folders_csv, folders_bytes)

    if not rows:
        if wrote_not_in:
            print(f"[INFO] No missing textures for job, updated empty {output_csv}")
        else:
            print(f"[INFO] No missing textures for job, {output_csv} already up to date")

        if wrote_folders:
            print(f"[INFO] No missing textures for job, updated empty {output_folders_csv}")
        else:
            print(f"[INFO] No missing textures for job, {output_folders_csv} already up to date")
        return

    if wrote_not_in:
        print(f"[INFO] Wrote {len(rows)} missing entries to {output_csv}")
    else:
        print(f"[INFO] Skipped unchanged {output_csv} ({len(rows)} missing entries)")

    if wrote_folders:
        print(f"[INFO] Wrote {len(folder_set)} folders to {output_folders_csv}")
    else:
        print(f"[INFO] Skipped unchanged {output_folders_csv} ({len(folder_set)} folders)")


# ==========================================================
# STAGING HELPERS
# ==========================================================
def find_jobs(root: Path) -> list[Path]:
    """
    Find all "folders to process.txt" files under root.
    Return their parent directories as job directories.
    """
    if not root.is_dir():
        print(f"[WARN] Staging root does not exist, skipping: {root}")
        return []

    jobs: list[Path] = []
    for txt in root.rglob(FOLDERS_TXT_NAME):
        if txt.is_file():
            jobs.append(txt.parent)

    jobs.sort()
    return jobs


def run_staging_main(job_dir: Path) -> None:
    """
    Run shared _staging_main.py with CWD set to the job directory.
    Then wait for ctxr3.exe (or other configured CTXR3 exe names) to finish if it is running.
    """
    if not STAGING_MAIN_PATH.is_file():
        raise SystemExit(f"ERROR: Cannot find {STAGING_MAIN_NAME} at {STAGING_MAIN_PATH}")

    print("=================================================")
    print(f"Running: {STAGING_MAIN_PATH}")
    print(f"CWD:     {job_dir}")
    print("=================================================")

    result = subprocess.run(
        [sys.executable, str(STAGING_MAIN_PATH)],
        cwd=str(job_dir),
    )

    if result.returncode != 0:
        raise SystemExit(
            f"{STAGING_MAIN_NAME} failed in {job_dir} with exit code {result.returncode}"
        )

    # If ctxr3 was spawned and is still running, block here until it exits.
    wait_for_processes_to_exit(WAIT_FOR_CTXR3_EXE_NAMES, context=f"job {job_dir}")


def _tier_is_upscaled(root: Path) -> bool:
    root_lower = str(root).lower()
    return ("2x upscaled" in root_lower) or ("4x upscaled" in root_lower)


def run_tier(root: Path) -> list[Path]:
    """
    Run all jobs under a single staging root.

    Updated behavior:
    - Sequential execution for:
        * 2x/4x tiers (existing)
        * non-upscaled tiers too (because ctxr3 can be spawned and must not overlap)
    - Parallel execution is only used if you later relax this.
    """
    jobs = find_jobs(root)

    if not jobs:
        print(f"[INFO] No '{FOLDERS_TXT_NAME}' found under {root}")
        return []

    print(f"[INFO] Found {len(jobs)} job(s) under {root}")

    # Force sequential for anything that could cause interactive ctxr3 work.
    sequential = True

    if sequential:
        print("[INFO] Running jobs sequentially (ctxr3-safe mode)")

        for idx, job_dir in enumerate(jobs, start=1):
            try:
                run_staging_main(job_dir)
                print(f"[INFO] Completed ({idx}/{len(jobs)}): {job_dir}")
            except SystemExit as e:
                print(f"[ERROR] Job failed in {job_dir}: {e}")
                pause_and_exit(1)
            except Exception as e:
                print(f"[ERROR] Unexpected error in {job_dir}: {e}")
                pause_and_exit(1)

        # Extra: after the whole tier, ensure CTXR3 is not still running.
        wait_for_processes_to_exit(WAIT_FOR_CTXR3_EXE_NAMES, context=f"tier {root}")

        print(f"[INFO] Finished all jobs under {root}")
        return jobs

    # ======================================================
    # PARALLEL MODE (disabled by default now)
    # ======================================================
    workers = min(max(1, THREADS_PER_TIER), len(jobs))
    print(f"[INFO] Running up to {workers} job(s) in parallel")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(run_staging_main, job_dir): job_dir
            for job_dir in jobs
        }

        for idx, future in enumerate(as_completed(future_map), start=1):
            job_dir = future_map[future]
            try:
                future.result()
                print(f"[INFO] Completed ({idx}/{len(jobs)}): {job_dir}")
            except SystemExit as e:
                print(f"[ERROR] Job failed in {job_dir}: {e}")
                pause_and_exit(1)
            except Exception as e:
                print(f"[ERROR] Unexpected error in {job_dir}: {e}")
                pause_and_exit(1)

    wait_for_processes_to_exit(WAIT_FOR_CTXR3_EXE_NAMES, context=f"tier {root}")

    print(f"[INFO] Finished all jobs under {root}")
    return jobs


def run_set_ctxr_dates() -> None:
    if not SET_CTXR_DATES_PATH.is_file():
        print(f"ERROR: Could not find {SET_CTXR_DATES_NAME} at: {SET_CTXR_DATES_PATH}")
        pause_and_exit(1)

    print()
    print("#################################################")
    print(f"Running final script: {SET_CTXR_DATES_PATH}")
    print("#################################################")

    result = subprocess.run(
        [sys.executable, str(SET_CTXR_DATES_PATH)],
        cwd=str(SCRIPT_DIR),
    )

    if result.returncode != 0:
        print(f"ERROR: {SET_CTXR_DATES_NAME} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    print("[INFO] set_ctxr_modified_dates.py completed successfully.")


def _sync_2x_4x_pair(root_2x: Path, root_4x: Path) -> None:
    if not root_2x.is_dir():
        print(f"[INFO] 2x staging root does not exist, skipping 2x sync: {root_2x}")
        return

    if not root_4x.is_dir():
        print(f"[WARN] 4x staging root does not exist, skipping 2x sync: {root_4x}")
        return

    rel_paths_4x: set[Path] = set()
    for txt_4x in root_4x.rglob(FOLDERS_TXT_NAME):
        if txt_4x.is_file():
            rel_paths_4x.add(txt_4x.relative_to(root_4x))

    if not rel_paths_4x:
        print(f"[WARN] No '{FOLDERS_TXT_NAME}' found under 4x: {root_4x}, skipping 2x sync.")
        return

    print("[INFO] Syncing 'folders to process.txt' between 2x and 4x tiers")
    print(f"       2x root: {root_2x}")
    print(f"       4x root: {root_4x}")

    seen_rel_2x: set[Path] = set()

    for txt_2x in root_2x.rglob(FOLDERS_TXT_NAME):
        if not txt_2x.is_file():
            continue

        rel = txt_2x.relative_to(root_2x)
        seen_rel_2x.add(rel)

        if rel not in rel_paths_4x:
            print(f"[INFO] Removing 2x only '{FOLDERS_TXT_NAME}': {txt_2x}")
            try:
                txt_2x.unlink()
            except OSError as e:
                print(f"[ERROR] Failed to delete {txt_2x}: {e}")
            continue

        txt_4x = root_4x / rel
        try:
            data_2x = txt_2x.read_bytes()
            data_4x = txt_4x.read_bytes()
        except OSError as e:
            print(f"[ERROR] Failed to read one of the paired files {txt_2x} / {txt_4x}: {e}")
            continue

        if data_2x != data_4x:
            print(f"[INFO] Updating 2x '{FOLDERS_TXT_NAME}' to match 4x: {txt_2x}")
            try:
                txt_2x.write_bytes(data_4x)
            except OSError as e:
                print(f"[ERROR] Failed to overwrite {txt_2x} with {txt_4x}: {e}")

    for rel in rel_paths_4x:
        if rel in seen_rel_2x:
            continue

        src = root_4x / rel
        dst = root_2x / rel

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            print(f"[INFO] Added missing 2x '{FOLDERS_TXT_NAME}': {dst}")
        except OSError as e:
            print(f"[ERROR] Failed to copy missing 4x file to 2x: {src} -> {dst}: {e}")

    for dirpath, _dirnames, _filenames in os.walk(root_2x, topdown=False):
        p = Path(dirpath)
        if p == root_2x:
            continue

        try:
            if not any(p.iterdir()):
                print(f"[INFO] Removing empty directory under 2x: {p}")
                p.rmdir()
        except OSError as e:
            print(f"[ERROR] Failed to remove empty directory {p}: {e}")


def sync_2x_folders_txt_with_4x() -> None:
    _sync_2x_4x_pair(
        BUGFIX_ROOT / "Staging - 2x Upscaled",
        BUGFIX_ROOT / "Staging - 4x Upscaled",
    )

    _sync_2x_4x_pair(
        DEMASTER_ROOT / "Staging - 2x Upscaled",
        DEMASTER_ROOT / "Staging - 4x Upscaled",
    )

    _sync_2x_4x_pair(
        DEMASTER_ROOT / "Staging - UI - 2x Upscaled",
        DEMASTER_ROOT / "Staging - UI - 4x Upscaled",
    )

    _sync_2x_4x_pair(
        UPSCALED_UI_ROOT / "Staging - 2x Upscaled",
        UPSCALED_UI_ROOT / "Staging - 4x Upscaled",
    )


def ensure_conversion_csv_for_all_jobs() -> None:
    for root in STAGING_ROOTS:
        if not root.is_dir():
            continue

        for txt in root.rglob(FOLDERS_TXT_NAME):
            if not txt.is_file():
                continue

            job_dir = txt.parent
            csv_path = job_dir / CONVERSION_CSV_NAME

            if csv_path.exists():
                continue

            print(f"[INFO] Creating missing {CONVERSION_CSV_NAME}: {csv_path}")
            try:
                csv_path.write_text(CONVERSION_CSV_HEADER, encoding="utf-8", newline="")
            except OSError as e:
                print(f"[ERROR] Failed to create {csv_path}: {e}")


def is_eligible_upscale_job(job_dir: Path) -> bool:
    p = str(job_dir).replace("\\", "/").lower()

    return (
        "/ovr_stm/_win/" in p
        or p.endswith("/ovr_stm/_win")
        or "/flatlist/_win/" in p
        or p.endswith("/flatlist/_win")
    )


def generate_not_in_folder_for_tier(
    root: Path,
    dim_names: dict[str, str],
    ps2_texture_index: dict[str, Path],
    never_upscale_stems: set[str],
) -> None:
    jobs = find_jobs(root)
    if not jobs:
        print(f"[INFO] No jobs under {root} for not_in_folder.csv generation.")
        return

    print(f"[INFO] Generating {NOT_IN_FOLDER_CSV_NAME} and {UNPROCESSED_FOLDERS_CSV_NAME} for {len(jobs)} job(s) under {root}")
    for job_dir in jobs:
        if not is_eligible_upscale_job(job_dir):
            print(f"[INFO] Skipping not_in_folder generation for non-target job: {job_dir}")
            continue

        write_not_in_folder_csv(job_dir, dim_names, ps2_texture_index, never_upscale_stems)


def write_self_remade_modified_dates() -> None:
    target_dir = SELF_REMADE_FINALIZED_DIR

    if not target_dir.is_dir():
        print(f"[WARN] Self Remade Finalized directory does not exist: {target_dir}")
        return

    output_roots: list[Path] = []
    for project_root in (BUGFIX_ROOT, DEMASTER_ROOT, UPSCALED_UI_ROOT):
        parent = project_root.parent
        if parent.is_dir():
            output_roots.append(parent)

    if not output_roots:
        print("[WARN] No valid parent directories found for writing self_remade_modified_dates.csv")
        return

    print()
    print("#################################################")
    print(f"Collecting modified dates for Self Remade Finalized under: {target_dir}")
    print(f"Skipping: {target_dir / 'Source Files'}")
    print("Will write self_remade_modified_dates.csv to:")
    for out_root in output_roots:
        print(f"  - {out_root / SELF_REMADE_MODIFIED_DATES_CSV_NAME}")
    print("#################################################")

    stem_to_time: dict[str, int] = {}

    skip_dir_name = "source files"

    for root_dir, dirnames, filenames in os.walk(target_dir):
        dirnames[:] = [d for d in dirnames if d.lower() != skip_dir_name]

        base = Path(root_dir)
        for fname in filenames:
            path = base / fname
            if not path.is_file():
                continue

            suffix = path.suffix.lower()
            if suffix not in {".png", ".tga"}:
                continue

            try:
                stat = path.stat()
                mtime = int(stat.st_mtime)
                ctime = int(stat.st_ctime)
                chosen_time = ctime if ctime < mtime else mtime
            except OSError as e:
                print(f"[ERROR] Failed to stat {path}: {e}")
                continue

            stem = path.stem
            existing = stem_to_time.get(stem)
            if existing is None or chosen_time < existing:
                stem_to_time[stem] = chosen_time

    rows = sorted(stem_to_time.items(), key=lambda r: r[0])

    for out_root in output_roots:
        csv_path = out_root / SELF_REMADE_MODIFIED_DATES_CSV_NAME

        try:
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["stem", "modified_unix_time"])
                for stem, mtime in rows:
                    writer.writerow([stem, mtime])

            print(f"[INFO] Wrote {len(rows)} entries to {csv_path}")
        except OSError as e:
            print(f"[ERROR] Failed to write {csv_path}: {e}")


# ==========================================================
# MAIN
# ==========================================================
def main() -> None:
    verify_manual_ui_covered_by_no_mip_regex()

    run_find_unconverted()
    sync_build_dist_files()
    sync_2x_folders_txt_with_4x()
    ensure_conversion_csv_for_all_jobs()

    if not STAGING_MAIN_PATH.is_file():
        print(f"ERROR: _staging_main.py not found at: {STAGING_MAIN_PATH}")
        pause_and_exit(1)

    git_root = get_git_root()

    dimensions_csv = (
        git_root
        / "external"
        / "MGS2-PS2-Textures"
        / "u - dumped from substance"
        / "mgs2_ps2_dimensions.csv"
    )
    dim_names = load_dimensions_names(dimensions_csv)

    ps2_textures_root = git_root / "Texture Fixes" / "ps2 textures"
    ps2_texture_index = build_ps2_texture_index(ps2_textures_root)

    never_upscale_path = git_root / NEVER_UPSCALE_REL_PATH
    never_upscale_stems = load_never_upscale_stems(never_upscale_path)

    for root in STAGING_ROOTS:
        print()
        print("#################################################")
        print(f"Processing staging root: {root}")
        print("#################################################")

        run_tier(root)

        root_lower = str(root).lower()
        if "2x upscaled" in root_lower or "4x upscaled" in root_lower:
            tier_blocklist = never_upscale_stems
        else:
            tier_blocklist = set()

        generate_not_in_folder_for_tier(root, dim_names, ps2_texture_index, tier_blocklist)

    print()
    print("[INFO] All staging roots processed.")

    run_set_ctxr_dates()
    write_self_remade_modified_dates()


if __name__ == "__main__":
    main()