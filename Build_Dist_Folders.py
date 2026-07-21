from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Dict, Optional


MAX_WORKERS = os.cpu_count() or 8
DRY_RUN = False

GIT_ROOT: Optional[Path] = None

# Global map: repo-relative lowercase path -> unix timestamp (last content change)
GIT_MTIME_INDEX: Dict[str, float] = {}
GIT_INDEX_BUILT = False
GIT_INDEX_LOCK = Lock()

# Logging
LOG_PATH = Path(__file__).resolve().with_name("release_structure_sync.log")
LOG_LOCK = Lock()

# End-of-log summaries
SUMMARY_LOCK = Lock()
SUMMARY_LINES: list[str] = []
UNKNOWN_PREFIXES_SEEN: set[str] = set()

# Local sync target prefixes when NOT running in CI.
# These are PREFIXES, not full folder names.
VORTEX_MODS_DIR = Path(r"C:\Vortex\metalgearsolid2mc\mods")

LOCAL_SYNC_PREFIXES: dict[str, str] = {
    "dist": "MGS2 Community Bugfix Compilation - Base",
    #"dist_2x": "MGS2 Community Bugfix Compilation - 2x Upscaled",
    "dist_4x": "MGS2 Community Bugfix Compilation - 4x Upscaled",
}

IGNORED_TARGET_PATH_PREFIXES = {
    Path("plugins"),
    Path("logs"),
}


def log(message: str = "") -> None:
    with LOG_LOCK:
        print(message)
        with LOG_PATH.open("a", encoding="utf-8", newline="\n") as f:
            f.write(message + "\n")


def init_log() -> None:
    with LOG_LOCK:
        with LOG_PATH.open("w", encoding="utf-8", newline="\n") as f:
            f.write("")


def add_summary(message: str) -> None:
    with SUMMARY_LOCK:
        SUMMARY_LINES.append(message)


def flush_summaries() -> None:
    log("\n[SUMMARY]")
    with SUMMARY_LOCK:
        if not SUMMARY_LINES:
            log("No summary entries.")
            return

        for line in SUMMARY_LINES:
            log(line)


def is_ci() -> bool:
    value = os.environ.get("CI", "")
    return value.strip().lower() in {"1", "true", "yes", "y"}


def find_git_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log(f"[ERROR] Failed to find git root via git: {exc}")
        sys.exit(1)

    root = result.stdout.strip()
    if not root:
        log("[ERROR] git rev-parse returned empty path")
        sys.exit(1)

    git_root = Path(root).resolve()
    log(f"[INFO] Git root: {git_root}")
    return git_root


def parse_bool(value: str) -> bool:
    if value is None:
        return False

    value = value.strip().lower()
    return value in {"1", "true", "yes", "y"}


def normalize_repo_path(path: Path) -> Optional[str]:
    """
    Convert a filesystem path to a repo-relative lowercase path with forward slashes.
    Returns None if the path is not under GIT_ROOT.
    """
    global GIT_ROOT

    if GIT_ROOT is None:
        return None

    try:
        rel = path.resolve().relative_to(GIT_ROOT)
    except ValueError:
        return None

    return str(rel).replace("\\", "/").lower()


def build_git_mtime_index(git_root: Path) -> None:
    """
    Walk the entire git history once (oldest to newest) and build a map of:
        repo-relative lowercase path -> last content change timestamp,
    following renames and ignoring pure rename-only commits.
    """
    global GIT_MTIME_INDEX, GIT_INDEX_BUILT

    with GIT_INDEX_LOCK:
        if GIT_INDEX_BUILT:
            return

        log("[INFO] Building git mtime index (reverse log, rename-aware, content changes only)...")

        cmd = [
            "git",
            "-C",
            str(git_root),
            "log",
            "--name-status",
            "--find-renames",
            "--format=%at",
            "--reverse",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            log(f"[ERROR] git not found when building mtime index: {exc}")
            sys.exit(1)

        path_ts: Dict[str, float] = {}
        current_ts: Optional[float] = None

        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")

            if not line:
                continue

            if line[0].isdigit() and line.strip().isdigit():
                try:
                    current_ts = float(line.strip())
                except ValueError:
                    current_ts = None
                continue

            if current_ts is None:
                continue

            parts = line.split("\t")
            if not parts:
                continue

            status = parts[0]
            kind = status[0]

            if kind in {"A", "M", "D"}:
                if len(parts) < 2:
                    continue

                raw_path = parts[1]
                key = raw_path.replace("\\", "/").lower()

                if kind in {"A", "M"}:
                    path_ts[key] = current_ts

            elif kind in {"R", "C"}:
                if len(parts) < 3:
                    continue

                old_path = parts[1]
                new_path = parts[2]

                old_key = old_path.replace("\\", "/").lower()
                new_key = new_path.replace("\\", "/").lower()

                if kind == "R":
                    score_str = status[1:] if len(status) > 1 else ""
                    pure_rename = score_str == "100"

                    if pure_rename:
                        old_ts = path_ts.get(old_key)
                        if old_ts is not None:
                            path_ts[new_key] = old_ts
                        else:
                            path_ts[new_key] = current_ts
                    else:
                        path_ts[new_key] = current_ts
                else:
                    path_ts[new_key] = current_ts

        _, stderr_data = proc.communicate()
        if proc.returncode not in (0, None):
            log(f"[WARN] git log exited with code {proc.returncode}")
            if stderr_data:
                log(f"[WARN] git log stderr:\n{stderr_data}")

        GIT_MTIME_INDEX = path_ts
        GIT_INDEX_BUILT = True

        log(f"[INFO] Git mtime index built with {len(GIT_MTIME_INDEX)} paths.")
        add_summary(f"[INFO] Git mtime index built with {len(GIT_MTIME_INDEX)} paths.")


def get_git_mtime(path: Path) -> Optional[float]:
    key = normalize_repo_path(path)
    if key is None:
        return None

    return GIT_MTIME_INDEX.get(key)


def set_mtime(path: Path, ts: float) -> None:
    try:
        os.utime(path, (ts, ts))
        log(f"  [UTIME] {path} -> {int(ts)}")
    except Exception as exc:
        log(f"  [UTIME FAIL] {path}: {exc}")


def compute_mtime_for_src(
    src: Path,
    ctxr_mtime_map: Optional[dict[str, float]] = None,
) -> Optional[float]:
    ts: Optional[float] = None

    if ctxr_mtime_map is not None and src.suffix.lower() == ".ctxr":
        repo_key = normalize_repo_path(src)
        if repo_key is not None:
            ts = ctxr_mtime_map.get(repo_key)

    if ts is None:
        ts = get_git_mtime(src)

    return ts


def move_tree_all(
    origin: Path,
    dest: Path,
    ctxr_mtime_map: Optional[dict[str, float]] = None,
) -> None:
    for root, _, files in os.walk(origin):
        root_path = Path(root)
        rel_root = root_path.relative_to(origin)
        target_root = dest / rel_root
        target_root.mkdir(parents=True, exist_ok=True)

        for filename in files:
            src_file = root_path / filename
            dst_file = target_root / filename
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            mtime = compute_mtime_for_src(src_file, ctxr_mtime_map)
            shutil.move(str(src_file), str(dst_file))
            log(f"  [MOVE] {src_file} -> {dst_file}")

            if mtime is not None:
                set_mtime(dst_file, mtime)


def move_tree_ctxr_only(
    origin: Path,
    dest: Path,
    ctxr_mtime_map: Optional[dict[str, float]],
) -> None:
    moved_any = False

    for ctxr in origin.rglob("*.ctxr"):
        rel_path = ctxr.relative_to(origin)
        target = dest / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        mtime = compute_mtime_for_src(ctxr, ctxr_mtime_map)
        shutil.move(str(ctxr), str(target))
        log(f"  [MOVE .ctxr] {ctxr} -> {target}")
        moved_any = True

        if mtime is not None:
            set_mtime(target, mtime)

    if not moved_any:
        log("  [INFO] No .ctxr files found to move.")


def prune_empty_dirs(root: Path) -> None:
    if not root.exists() or not root.is_dir():
        return

    removed_any = False

    for current_root, dirs, files in os.walk(root, topdown=False):
        cur_path = Path(current_root)

        if not dirs and not files:
            try:
                os.rmdir(cur_path)
                log(f"  [RMDIR] {cur_path}")
                removed_any = True
            except OSError as exc:
                log(f"  [RMDIR FAIL] {cur_path}: {exc}")

    if not removed_any:
        log("  [INFO] No empty folders to remove under origin.")


def load_ps2_sha1_version_dates(csv_path: Path) -> dict[str, float]:
    mapping: dict[str, float] = {}

    if not csv_path.is_file():
        log(f"[ERROR] PS2 sha1 version dates CSV not found: {csv_path}")
        sys.exit(1)

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"sha1", "first_seen_unix"}
        if not required.issubset(set(reader.fieldnames or [])):
            log("[ERROR] PS2 sha1 version dates CSV missing required headers: sha1,first_seen_unix")
            sys.exit(1)

        for row in reader:
            sha1 = (row.get("sha1") or "").strip().lower()
            ts_str = (row.get("first_seen_unix") or "").strip()
            if not sha1 or not ts_str:
                continue

            try:
                ts = float(ts_str)
            except ValueError:
                log(f"[WARN] Invalid first_seen_unix '{ts_str}' for sha1 '{sha1}'")
                continue

            mapping[sha1] = ts

    log(f"[INFO] Loaded {len(mapping)} PS2 sha1 version date entries.")
    add_summary(f"[INFO] Loaded {len(mapping)} PS2 sha1 version date entries.")
    return mapping


def load_mc_resaved_dates(csv_path: Path) -> dict[str, float]:
    mapping: dict[str, float] = {}

    if not csv_path.is_file():
        log(f"[ERROR] MC dimensions CSV not found: {csv_path}")
        sys.exit(1)

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"mc_resaved_sha1", "version_unix_time"}
        if not required.issubset(set(reader.fieldnames or [])):
            log("[ERROR] MC dimensions CSV missing required headers: mc_resaved_sha1,version_unix_time")
            sys.exit(1)

        for row in reader:
            sha1 = (row.get("mc_resaved_sha1") or "").strip().lower()
            ts_str = (row.get("version_unix_time") or "").strip()
            if not sha1 or not ts_str:
                continue

            try:
                ts = float(ts_str)
            except ValueError:
                log(f"[WARN] Invalid version_unix_time '{ts_str}' for mc_resaved_sha1 '{sha1}'")
                continue

            mapping[sha1] = ts

    log(f"[INFO] Loaded {len(mapping)} MC resaved sha1 date entries.")
    add_summary(f"[INFO] Loaded {len(mapping)} MC resaved sha1 date entries.")
    return mapping


def load_self_remade_dates(csv_path: Path) -> dict[str, float]:
    mapping: dict[str, float] = {}

    if not csv_path.is_file():
        log(f"[ERROR] Self Remade dates CSV not found: {csv_path}")
        sys.exit(1)

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"sha1", "modified_unix_time"}
        if not required.issubset(set(reader.fieldnames or [])):
            log("[ERROR] Self Remade dates CSV missing required headers: sha1,modified_unix_time")
            sys.exit(1)

        for row in reader:
            sha1 = (row.get("sha1") or "").strip().lower()
            ts_str = (row.get("modified_unix_time") or "").strip()
            if not sha1 or not ts_str:
                continue

            try:
                ts = float(ts_str)
            except ValueError:
                log(f"[WARN] Invalid Self Remade modified_unix_time '{ts_str}' for sha1 '{sha1}'")
                continue

            existing = mapping.get(sha1)
            if existing is None or ts < existing:
                mapping[sha1] = ts

    log(f"[INFO] Loaded {len(mapping)} Self Remade sha1 date entries.")
    add_summary(f"[INFO] Loaded {len(mapping)} Self Remade sha1 date entries.")
    return mapping


def build_ctxr_mtime_map(
    origin_root: Path,
    ps2_sha1_dates: dict[str, float],
    mc_resaved_dates: dict[str, float],
    self_remade_dates: dict[str, float],
) -> dict[str, float]:
    ctxr_mtime_map: dict[str, float] = {}
    csv_count = 0
    rows_used = 0

    ps2_fallback_ts = 1503360000.0  # 2017-08-22 00:00:00 UTC

    for csv_path in origin_root.rglob("conversion_hashes.csv"):
        csv_count += 1

        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"filename", "before_hash", "origin_folder"}
            if not required.issubset(set(reader.fieldnames or [])):
                log(
                    f"[WARN] conversion_hashes.csv at {csv_path} missing "
                    f"filename/before_hash/origin_folder columns, skipping."
                )
                continue

            for row in reader:
                filename = (row.get("filename") or "").strip()
                before_hash = (row.get("before_hash") or "").strip().lower()
                origin_folder = (row.get("origin_folder") or "").strip().lower()

                if not filename:
                    continue

                ts: Optional[float] = None

                if before_hash:
                    ts = ps2_sha1_dates.get(before_hash)
                    if ts is None:
                        ts = mc_resaved_dates.get(before_hash)
                    if ts is None:
                        ts = self_remade_dates.get(before_hash)

                if ts is None and origin_folder.startswith("ps2 textures"):
                    ts = ps2_fallback_ts

                if ts is None:
                    log("[ERROR] Failed to resolve timestamp for conversion row:")
                    log(f"        CSV:          {csv_path}")
                    log(f"        filename:     {filename}")
                    log(f"        before_hash:  {before_hash or '<empty>'}")
                    log(f"        origin_folder:{origin_folder or '<empty>'}")
                    log("")
                    log("Unable to match before_hash against:")
                    log("  - mgs2_ps2_sha1_version_dates.csv")
                    log("  - mgs2_mc_dimensions.csv (mc_resaved_sha1)")
                    log("  - self_remade_modified_dates.csv (sha1)")
                    log("")
                    input("Press Enter to exit...")
                    sys.exit(1)

                ctxr_filename = f"{filename}.ctxr"
                ctxr_path = (csv_path.parent / ctxr_filename).resolve()

                if not ctxr_path.is_file():
                    continue

                repo_key = normalize_repo_path(ctxr_path)
                if repo_key is None:
                    continue

                if repo_key not in ctxr_mtime_map:
                    ctxr_mtime_map[repo_key] = ts
                    rows_used += 1

    if csv_count:
        log(
            f"[INFO] Built ctxr_mtime_map from {csv_count} conversion_hashes.csv files, "
            f"{rows_used} ctxr files with PS2/MC/Self Remade/fallback timestamps."
        )
    else:
        log("[INFO] No conversion_hashes.csv found under origin for ctxr mtime mapping.")

    return ctxr_mtime_map


def process_mapping(
    origin_abs: Path,
    dest_abs: Path,
    prune_non_ctxr: bool,
    idx: int,
    ps2_dates: dict[str, float],
    mc_dates: dict[str, float],
    self_remade_dates: dict[str, float],
) -> None:
    log(f"\n[MAP {idx}]")
    log(f"  Origin:          {origin_abs}")
    log(f"  Destination:     {dest_abs}")
    log(f"  prune_non_ctxr:  {prune_non_ctxr}")

    if not origin_abs.exists():
        log(f"[WARN] Origin does not exist, skipping: {origin_abs}")
        return

    ctxr_mtime_map: Optional[dict[str, float]] = None
    if prune_non_ctxr and origin_abs.is_dir():
        ctxr_mtime_map = build_ctxr_mtime_map(origin_abs, ps2_dates, mc_dates, self_remade_dates)

    if origin_abs.is_file():
        dest_abs.parent.mkdir(parents=True, exist_ok=True)

        if prune_non_ctxr and origin_abs.suffix.lower() != ".ctxr":
            log(f"[SKIP] prune_non_ctxr enabled, skipping non .ctxr file: {origin_abs}")
            return

        mtime = compute_mtime_for_src(origin_abs, ctxr_mtime_map)
        shutil.move(str(origin_abs), str(dest_abs))
        log(f"[MOVE FILE] {origin_abs} -> {dest_abs}")

        if mtime is not None:
            set_mtime(dest_abs, mtime)

        return

    dest_abs.mkdir(parents=True, exist_ok=True)

    if prune_non_ctxr:
        log("[INFO] prune_non_ctxr = TRUE, moving only .ctxr files:")
        log(f"       {origin_abs} -> {dest_abs}")
        move_tree_ctxr_only(origin_abs, dest_abs, ctxr_mtime_map)
    else:
        log("[INFO] Moving full tree:")
        log(f"       {origin_abs} -> {dest_abs}")
        move_tree_all(origin_abs, dest_abs)

    log(f"[INFO] Pruning empty folders under origin: {origin_abs}")
    prune_empty_dirs(origin_abs)


def verify_origin_paths(mappings: list[tuple[int, Path, Path, bool]]) -> None:
    missing: list[tuple[int, Path]] = []

    for idx, origin_abs, _, _ in mappings:
        if not origin_abs.exists():
            missing.append((idx, origin_abs))

    if not missing:
        return

    log("\n[ERROR] One or more origin_path entries do not exist:\n")
    for idx, path in missing:
        log(f"  Row {idx}: {path}")

    log("\nFix Release_Structure.csv and try again.")
    input("Press Enter to exit...")
    sys.exit(1)


def _dest_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").lower()


def detect_destination_conflicts(mappings: list[tuple[int, Path, Path, bool]]) -> None:
    log("[INFO] Preflight: scanning for destination overwrite conflicts...")

    dest_to_sources: dict[str, list[tuple[int, Path, Path]]] = {}
    lock = Lock()

    def scan_one(mapping: tuple[int, Path, Path, bool]) -> None:
        idx, origin_abs, dest_abs, prune_flag = mapping

        if origin_abs.is_file():
            if prune_flag and origin_abs.suffix.lower() != ".ctxr":
                return

            key = _dest_key(dest_abs)
            with lock:
                dest_to_sources.setdefault(key, []).append((idx, origin_abs, dest_abs))
            return

        if not origin_abs.is_dir():
            return

        if prune_flag:
            it = origin_abs.rglob("*.ctxr")
        else:
            it = origin_abs.rglob("*")

        for src in it:
            if not src.is_file():
                continue

            rel = src.relative_to(origin_abs)
            dst = dest_abs / rel

            key = _dest_key(dst)
            with lock:
                dest_to_sources.setdefault(key, []).append((idx, src, dst))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scan_one, m) for m in mappings]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                log(f"[ERROR] Conflict scan task raised an exception: {exc}")
                input("Press Enter to exit...")
                sys.exit(1)

    conflicts = [(k, v) for (k, v) in dest_to_sources.items() if len(v) > 1]
    if not conflicts:
        log("[INFO] Preflight: no destination conflicts found.")
        add_summary("[INFO] Preflight: no destination conflicts found.")
        return

    conflicts.sort(key=lambda kv: kv[0])

    log("\n[ERROR] Conflicting destinations detected. These files would overwrite one another:\n")
    for _, entries in conflicts:
        _, _, dst_path = entries[0]
        log(f"DEST: {dst_path}")
        entries_sorted = sorted(entries, key=lambda t: (t[0], str(t[1]).lower()))
        for idx, src_path, _ in entries_sorted:
            log(f"  - Row {idx}: {src_path}")
        log()

    log("[ERROR] Fix Release_Structure.csv so destinations do not collide, then try again.")
    input("Press Enter to exit...")
    sys.exit(1)


def resolve_local_sync_roots() -> dict[str, Path]:
    if not VORTEX_MODS_DIR.is_dir():
        log(f"[ERROR] Vortex mods directory not found: {VORTEX_MODS_DIR}")
        sys.exit(1)

    resolved: dict[str, Path] = {}

    for key, prefix in LOCAL_SYNC_PREFIXES.items():
        matches = [
            p
            for p in VORTEX_MODS_DIR.iterdir()
            if p.is_dir() and p.name.startswith(prefix)
        ]

        if not matches:
            log(
                f"[ERROR] No Vortex mod folder found for '{key}' "
                f"with prefix '{prefix}' under: {VORTEX_MODS_DIR}"
            )
            sys.exit(1)

        if len(matches) > 1:
            log(
                f"[ERROR] Multiple Vortex mod folders matched '{key}' "
                f"with prefix '{prefix}'. Refusing to guess:"
            )
            for match in sorted(matches, key=lambda p: p.name.lower()):
                log(f"        {match}")
            sys.exit(1)

        resolved[key] = matches[0]
        log(f"[INFO] Resolved local sync root for {key}: {matches[0]}")
        add_summary(f"[INFO] Resolved local sync root for {key}: {matches[0]}")

    return resolved


def get_sync_root_for_destination(
    dest_abs: Path,
    git_root: Path,
    resolved_sync_roots: dict[str, Path],
) -> tuple[Optional[Path], Optional[Path], Optional[str]]:
    try:
        rel = dest_abs.resolve().relative_to(git_root.resolve())
    except ValueError:
        return None, None, None

    parts = rel.parts
    if not parts:
        return None, None, None

    root_name = parts[0].lower()
    sync_root = resolved_sync_roots.get(root_name)
    if sync_root is None:
        should_log = False
        with SUMMARY_LOCK:
            if root_name not in UNKNOWN_PREFIXES_SEEN:
                UNKNOWN_PREFIXES_SEEN.add(root_name)
                should_log = True

        if should_log:
            message = (
                f"[WARN] Local sync prefix '{root_name}' is not defined in LOCAL_SYNC_PREFIXES. "
                f"Skipping any mappings targeting it."
            )
            log(message)
            add_summary(f"[WARN] Undefined local sync prefix skipped: {root_name}")

        return None, None, None

    remainder = Path(*parts[1:]) if len(parts) > 1 else Path()
    return sync_root, remainder, root_name


def should_ignore_target_rel(rel_path: Path) -> bool:
    rel_lower = Path(*[p.lower() for p in rel_path.parts])

    for prefix in IGNORED_TARGET_PATH_PREFIXES:
        if rel_lower.parts[:len(prefix.parts)] == prefix.parts:
            return True

    return False


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def files_are_identical(src: Path, dst: Path) -> bool:
    if not dst.is_file():
        return False

    try:
        if src.stat().st_size != dst.stat().st_size:
            return False
    except OSError:
        return False

    return sha1_file(src) == sha1_file(dst)


def copy_with_mtime(src: Path, dst: Path, mtime: Optional[float], dry_run: bool) -> bool:
    """
    Returns True if destination already existed and this was an update,
    False if this was a brand new copy.
    """
    existed_already = dst.exists()

    if dry_run:
        action = "[DRY UPDATE]" if existed_already else "[DRY COPY]"
        log(f"  {action} {src} -> {dst}")
        if mtime is not None:
            log(f"  [DRY UTIME] {dst} -> {int(mtime)}")
        return existed_already

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dst))

    action = "[UPDATE]" if existed_already else "[COPY]"
    log(f"  {action} {src} -> {dst}")

    if mtime is not None:
        set_mtime(dst, mtime)

    return existed_already


def delete_path(path: Path, dry_run: bool) -> None:
    if dry_run:
        log(f"  [DRY DELETE] {path}")
        return

    if path.is_file() or path.is_symlink():
        path.unlink()
        log(f"  [DELETE FILE] {path}")
    elif path.is_dir():
        shutil.rmtree(path)
        log(f"  [DELETE DIR] {path}")


def prune_empty_dirs_with_ignores(root: Path, dry_run: bool) -> None:
    if not root.exists() or not root.is_dir():
        return

    for current_root, _, _ in os.walk(root, topdown=False):
        cur_path = Path(current_root)

        if cur_path == root:
            continue

        rel = cur_path.relative_to(root)
        if should_ignore_target_rel(rel):
            continue

        try:
            next(cur_path.iterdir())
            continue
        except StopIteration:
            pass
        except OSError as exc:
            log(f"  [RMDIR CHECK FAIL] {cur_path}: {exc}")
            continue

        if dry_run:
            log(f"  [DRY RMDIR] {cur_path}")
            continue

        try:
            os.rmdir(cur_path)
            log(f"  [RMDIR] {cur_path}")
        except OSError as exc:
            log(f"  [RMDIR FAIL] {cur_path}: {exc}")


def gather_mapping_outputs(
    mapping: tuple[int, Path, Path, bool],
    git_root: Path,
    resolved_sync_roots: dict[str, Path],
    ps2_dates: dict[str, float],
    mc_dates: dict[str, float],
    self_remade_dates: dict[str, float],
) -> list[tuple[Path, Path, Optional[float]]]:
    idx, origin_abs, dest_abs, prune_flag = mapping
    outputs: list[tuple[Path, Path, Optional[float]]] = []

    ctxr_mtime_map: Optional[dict[str, float]] = None
    if prune_flag and origin_abs.is_dir():
        ctxr_mtime_map = build_ctxr_mtime_map(origin_abs, ps2_dates, mc_dates, self_remade_dates)

    sync_root, sync_rel_root, _ = get_sync_root_for_destination(
        dest_abs,
        git_root,
        resolved_sync_roots,
    )
    if sync_root is None or sync_rel_root is None:
        return outputs

    log(
        f"\n[SYNC MAP {idx}]\n"
        f"  Origin:          {origin_abs}\n"
        f"  CSV Destination: {dest_abs}\n"
        f"  Sync Root:       {sync_root}\n"
        f"  Sync Prefix:     {sync_rel_root}\n"
        f"  prune_non_ctxr:  {prune_flag}"
    )

    if origin_abs.is_file():
        if prune_flag and origin_abs.suffix.lower() != ".ctxr":
            log(f"  [SKIP] prune_non_ctxr enabled, skipping non .ctxr file: {origin_abs}")
            return outputs

        target = sync_root / sync_rel_root
        mtime = compute_mtime_for_src(origin_abs, ctxr_mtime_map)
        outputs.append((origin_abs, target, mtime))
        return outputs

    if not origin_abs.is_dir():
        return outputs

    if prune_flag:
        iterator = origin_abs.rglob("*.ctxr")
    else:
        iterator = origin_abs.rglob("*")

    for src in iterator:
        if not src.is_file():
            continue

        rel = src.relative_to(origin_abs)
        target = sync_root / sync_rel_root / rel
        mtime = compute_mtime_for_src(src, ctxr_mtime_map)
        outputs.append((src, target, mtime))

    return outputs


def sync_target_group(
    target_root: Path,
    expected: dict[str, tuple[Path, Path, Optional[float]]],
    dry_run: bool,
) -> None:
    log(f"\n[SYNC ROOT] {target_root}")
    log(f"[INFO] Expected managed files: {len(expected)}")
    log(f"[INFO] Dry run: {dry_run}")

    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)

    existing_files: dict[str, Path] = {}

    if target_root.exists():
        for path in target_root.rglob("*"):
            if not path.is_file():
                continue

            rel = path.relative_to(target_root)
            if should_ignore_target_rel(rel):
                continue

            key = str(rel).replace("\\", "/").lower()
            existing_files[key] = path

    copy_count = 0
    update_count = 0
    skip_count = 0
    delete_count = 0
    count_lock = Lock()

    expected_keys_sorted = sorted(expected.keys())

    def process_expected(key: str) -> None:
        nonlocal copy_count, update_count, skip_count

        src, dst, mtime = expected[key]

        if dst.exists() and files_are_identical(src, dst):
            if mtime is not None:
                current_mtime = None
                try:
                    current_mtime = dst.stat().st_mtime
                except OSError:
                    current_mtime = None

                if current_mtime is None or abs(current_mtime - mtime) > 1.0:
                    if dry_run:
                        log(f"  [DRY UTIME] {dst} -> {int(mtime)}")
                    else:
                        set_mtime(dst, mtime)

            with count_lock:
                skip_count += 1
            return

        was_update = copy_with_mtime(src, dst, mtime, dry_run=dry_run)

        with count_lock:
            if was_update:
                update_count += 1
            else:
                copy_count += 1

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_expected, key) for key in expected_keys_sorted]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                log(f"[ERROR] Sync copy/update task raised an exception: {exc}")
                raise

    existing_keys = set(existing_files.keys())
    expected_keys = set(expected.keys())
    stale_keys = sorted(existing_keys - expected_keys)

    def process_stale(key: str) -> None:
        nonlocal delete_count

        stale_path = existing_files[key]
        rel = stale_path.relative_to(target_root)
        if should_ignore_target_rel(rel):
            return

        delete_path(stale_path, dry_run=dry_run)
        with count_lock:
            delete_count += 1

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_stale, key) for key in stale_keys]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                log(f"[ERROR] Sync delete task raised an exception: {exc}")
                raise

    if target_root.exists():
        prune_empty_dirs_with_ignores(target_root, dry_run=dry_run)

    add_summary(f"[INFO] Sync summary for {target_root}")
    add_summary(f"       copied:  {copy_count}")
    add_summary(f"       updated: {update_count}")
    add_summary(f"       skipped: {skip_count}")
    add_summary(f"       deleted: {delete_count}")


def run_sync_mode(
    mappings: list[tuple[int, Path, Path, bool]],
    git_root: Path,
    ps2_dates: dict[str, float],
    mc_dates: dict[str, float],
    self_remade_dates: dict[str, float],
    dry_run: bool,
) -> None:
    log("\n[INFO] Running in local sync mode.")
    log(f"[INFO] DRY_RUN = {dry_run}")
    add_summary("[INFO] Mode: local sync")
    add_summary(f"[INFO] DRY_RUN = {dry_run}")
    add_summary(f"[INFO] Worker threads: {MAX_WORKERS}")
    add_summary("[INFO] Sync planning: multithreaded")
    add_summary("[INFO] Sync copy/update/delete: multithreaded")

    resolved_sync_roots = resolve_local_sync_roots()

    expected_by_root: dict[Path, dict[str, tuple[Path, Path, Optional[float]]]] = {
        root: {} for root in resolved_sync_roots.values()
    }
    lock = Lock()

    def worker(mapping: tuple[int, Path, Path, bool]) -> None:
        outputs = gather_mapping_outputs(
            mapping,
            git_root,
            resolved_sync_roots,
            ps2_dates,
            mc_dates,
            self_remade_dates,
        )

        for src, dst, mtime in outputs:
            root = None
            for candidate in expected_by_root.keys():
                try:
                    dst.relative_to(candidate)
                    root = candidate
                    break
                except ValueError:
                    continue

            if root is None:
                continue

            rel_key = str(dst.relative_to(root)).replace("\\", "/").lower()

            with lock:
                existing = expected_by_root[root].get(rel_key)
                if existing is not None:
                    prev_src, prev_dst, _ = existing
                    log("[ERROR] Internal sync collision detected:")
                    log(f"        DEST: {prev_dst}")
                    log(f"        SRC1: {prev_src}")
                    log(f"        SRC2: {src}")
                    sys.exit(1)

                expected_by_root[root][rel_key] = (src, dst, mtime)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(worker, m) for m in mappings]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                log(f"[ERROR] Sync planning task raised an exception: {exc}")
                sys.exit(1)

    for root, expected in expected_by_root.items():
        sync_target_group(root, expected, dry_run=dry_run)

    log("\n[INFO] Local sync mode complete.")
    add_summary("[INFO] Local sync mode complete.")


def main() -> None:
    global GIT_ROOT

    init_log()
    log(f"[INFO] Log file: {LOG_PATH}")

    git_root = find_git_root()
    GIT_ROOT = git_root

    csv_path = git_root / "Release_Structure.csv"

    if not csv_path.is_file():
        log(f"[ERROR] Release_Structure.csv not found at git root: {csv_path}")
        sys.exit(1)

    log(f"[INFO] Using mapping file: {csv_path}")
    add_summary(f"[INFO] Mapping file: {csv_path}")

    mappings: list[tuple[int, Path, Path, bool]] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        required = {"origin_path", "destination_path", "prune_non_ctxr"}
        if not required.issubset(set(reader.fieldnames or [])):
            log("[ERROR] CSV must have headers: origin_path,destination_path,prune_non_ctxr")
            sys.exit(1)

        for idx, row in enumerate(reader, start=1):
            origin_rel = (row.get("origin_path") or "").strip()
            dest_rel = (row.get("destination_path") or "").strip()
            prune_flag = parse_bool(row.get("prune_non_ctxr") or "")

            if not origin_rel or not dest_rel:
                log(f"[WARN] Row {idx} has empty origin or destination, skipping")
                continue

            if origin_rel.startswith("#"):
                continue

            origin_abs = (git_root / origin_rel).resolve()
            dest_abs = (git_root / dest_rel).resolve()

            mappings.append((idx, origin_abs, dest_abs, prune_flag))

    if not mappings:
        log("[INFO] No valid mappings found in CSV.")
        add_summary("[INFO] No valid mappings found in CSV.")
        log("\n[INFO] Done.")
        flush_summaries()
        return

    add_summary(f"[INFO] Valid mappings loaded: {len(mappings)}")

    verify_origin_paths(mappings)
    detect_destination_conflicts(mappings)
    build_git_mtime_index(git_root)

    any_pruned = any(prune_flag for (_, _, _, prune_flag) in mappings)
    if any_pruned:
        metadata_dir = (
            git_root
            / "external"
            / "MGS2-PS2-Textures"
            / "Tri-Dumped"
            / "Master Collection"
            / "Metadata"
        )

        ps2_dates_csv = metadata_dir / "mgs2_ps2_sha1_version_dates.csv"
        mc_dates_csv = metadata_dir / "mgs2_mc_dimensions.csv"
        self_remade_csv = git_root / "self_remade_modified_dates.csv"

        ps2_dates = load_ps2_sha1_version_dates(ps2_dates_csv)
        mc_dates = load_mc_resaved_dates(mc_dates_csv)
        self_remade_dates = load_self_remade_dates(self_remade_csv)
    else:
        ps2_dates = {}
        mc_dates = {}
        self_remade_dates = {}
        add_summary("[INFO] No prune_non_ctxr mappings detected. External date CSV loads skipped.")

    if is_ci():
        log(f"[INFO] CI detected. Processing {len(mappings)} mappings with move mode.")
        log(f"[INFO] Worker threads: {MAX_WORKERS}\n")
        add_summary("[INFO] Mode: CI move")
        add_summary(f"[INFO] Worker threads: {MAX_WORKERS}")

        def worker(mapping: tuple[int, Path, Path, bool]) -> None:
            idx, origin_abs, dest_abs, prune_flag = mapping
            process_mapping(
                origin_abs,
                dest_abs,
                prune_flag,
                idx,
                ps2_dates,
                mc_dates,
                self_remade_dates,
            )

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(worker, m) for m in mappings]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    log(f"[ERROR] Mapping task raised an exception: {exc}")
                    add_summary(f"[ERROR] Mapping task raised an exception: {exc}")
    else:
        run_sync_mode(
            mappings=mappings,
            git_root=git_root,
            ps2_dates=ps2_dates,
            mc_dates=mc_dates,
            self_remade_dates=self_remade_dates,
            dry_run=DRY_RUN,
        )

    log("\n[INFO] Done.")
    add_summary("[INFO] Done.")
    flush_summaries()


if __name__ == "__main__":
    main()