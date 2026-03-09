# _staging_main.py

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
from threading import Lock

from PIL import Image

STAGING_FOLDER = Path.cwd()
REQUIRED_SUBPATH = r"Afevis-MGS2-Bugfix-Compilation\Texture Fixes"
FOLDERS_TXT = "folders to process.txt"
CONVERSION_CSV = "conversion_hashes.csv"
ERROR_LOG_PATH = "conversion_error_log.txt"


# ==========================================================
# PARAM EXPORT CONFIG
# ==========================================================
PARAM_FOLDER = Path(r"J:\Mega\Games\MG Master Collection\Self made mods\Tooling\CTXR File Conversion\mgs2-param")
NVTT_EXPORT_EXE = Path(r"C:\Program Files\NVIDIA Corporation\NVIDIA Texture Tools\nvtt_export.exe")

DPF_DEFAULT = Path(r"J:\Mega\Games\MG Master Collection\Self made mods\Tooling\CTXR File Conversion\mgs_kaiser.dpf")
DPF_NOMIPS = Path(r"J:\Mega\Games\MG Master Collection\Self made mods\Tooling\CTXR File Conversion\mgs_nomips.dpf")

CTXR_TOOL_EXE = Path(r"J:\Mega\Games\MG Master Collection\Self made mods\Tooling\CTXR File Conversion\mgs2-param\CtxrTool.exe")
CTXR_TOOL_SUCCESS_LINE = "Running CtxrTool v1.3: Visit https://github.com/Jayveer/CtxrTool for updates:"

NO_MIP_REGEX_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\no_mip_regex.txt")
MANUAL_UI_TEXTURES_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_ui_textures.txt")

NEVER_UPSCALE_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\never_upscale.txt")

UPSCALE_STAGING_DIR = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\_upscaling")
UPSCALE_STAGING_DIR_STRIPPED_OPACITY = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\_upscaling_alpha_stripped"
)

# Root for PS2 textures used as override source in Demastered runs
PS2_TEXTURES_ROOT = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures")

CHAINNER_EXE = Path(r"C:\Users\cmkoo\AppData\Local\chaiNNer\chaiNNer.exe")
CHAINNER_PROJECT_2X = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\2x Upscaling.chn")
CHAINNER_PROJECT_4X = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\4x Upscaling.chn")

CHAINNER_PROJECT_2X_STRIPPED_OPACITY = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\2x Upscaling - Strip Alpha.chn")
CHAINNER_PROJECT_4X_STRIPPED_OPACITY = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\4x Upscaling - Strip Alpha.chn")

# 0 = v1 release
# 1 = corrected opaque texture alpha stripping for upscaling
# 2 = wavelet color fix!!!!! oh dang
UPSCALE_PROCESS_VERSION = "2"

CSV_FLUSH_SECONDS = 5.0

PRINT_LOCK = Lock()


# ==========================================================
# CTXR3 LAUNCH CONFIG
# ==========================================================
LAUNCH_CTXR3_PY = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\_launch_ctxr3.py")


def _clear_progress_line() -> None:
    try:
        width = shutil.get_terminal_size(fallback=(120, 24)).columns
    except Exception:
        width = 120

    sys.stdout.write("\r" + (" " * width) + "\r")
    sys.stdout.flush()


def log(msg: str):
    with PRINT_LOCK:
        _clear_progress_line()
        print(msg)
        sys.stdout.flush()


def pause_and_exit(code: int = 1) -> int:
    try:
        input("\nPress ENTER to exit...")
    except KeyboardInterrupt:
        pass
    return code


def has_any_uppercase(s: str) -> bool:
    if not s:
        return False
    for ch in s:
        if ch.isalpha() and ch.isupper():
            return True
    return False


# ==========================================================
# UPSCALED MODE DETECTION (BOOLEAN)
# ==========================================================
def get_staging_upscaled_bool() -> bool:
    path_lower = str(STAGING_FOLDER).lower()
    if " - 2x upscaled" in path_lower:
        return True
    if " - 4x upscaled" in path_lower:
        return True
    return False


def get_staging_upscale_factor_or_one() -> int:
    path_lower = str(STAGING_FOLDER).lower()
    if " - 2x upscaled" in path_lower:
        return 2
    if " - 4x upscaled" in path_lower:
        return 4
    return 1


def staging_folder_is_demastered() -> bool:
    return "demastered" in str(STAGING_FOLDER).lower()


def get_chainner_project_for_staging(stripped_opacity: bool) -> Path:
    path_lower = str(STAGING_FOLDER).lower()

    if " - 2x upscaled" in path_lower:
        return CHAINNER_PROJECT_2X_STRIPPED_OPACITY if stripped_opacity else CHAINNER_PROJECT_2X

    return CHAINNER_PROJECT_4X_STRIPPED_OPACITY if stripped_opacity else CHAINNER_PROJECT_4X


def get_current_upscaler_metadata_for_run(is_upscaled_run: bool) -> tuple[str, str]:
    if is_upscaled_run:
        return (UPSCALE_PROCESS_VERSION, "remarci_4x")
    return ("0", "none")


# ==========================================================
# PROGRESS / ETA
# ==========================================================
class ProgressTracker:
    def __init__(self, total: int, label: str, min_interval: float = 0.25):
        self.total = max(1, int(total))
        self.label = label
        self.min_interval = min_interval

        self.start = time.monotonic()
        self.last_print = self.start
        self.done = 0

    @staticmethod
    def _format_seconds(secs: float) -> str:
        secs = int(secs)
        if secs < 0:
            secs = 0
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        if h > 0:
            return f"{h:d}h {m:02d}m {s:02d}s"
        return f"{m:02d}m {s:02d}s"

    def update(self, step: int = 1) -> None:
        self.done += step
        now = time.monotonic()
        if now - self.last_print < self.min_interval and self.done < self.total:
            return

        self.last_print = now
        elapsed = now - self.start
        rate = self.done / elapsed if elapsed > 0 else 0.0
        remaining = (self.total - self.done) / rate if rate > 0 and self.done < self.total else 0.0

        elapsed_str = self._format_seconds(elapsed)
        eta_str = self._format_seconds(remaining) if remaining > 0 else "00m 00s"
        pct = (self.done / self.total) * 100.0

        line = f"[{self.label}] {self.done}/{self.total} ({pct:5.1f}%) elapsed {elapsed_str} eta {eta_str}"

        with PRINT_LOCK:
            print("\r" + line, end="", flush=True)

    def finish(self) -> None:
        self.done = self.total
        elapsed = time.monotonic() - self.start
        elapsed_str = self._format_seconds(elapsed)
        line = f"[{self.label}] {self.total}/{self.total} (100.0%) elapsed {elapsed_str} eta 00m 00s"

        with PRINT_LOCK:
            print("\r" + line)
            sys.stdout.flush()


def sha1_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_folder_list(txt_path: Path) -> list[Path]:
    if not txt_path.is_file():
        raise FileNotFoundError(f'Missing "{FOLDERS_TXT}" at {txt_path}')

    folders: list[Path] = []
    for raw in txt_path.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        folders.append(Path(line))
    return folders


def validate_paths_or_die(folders: list[Path]) -> None:
    required_lower = REQUIRED_SUBPATH.lower()
    bad: list[Path] = []

    for f in folders:
        if required_lower not in str(f).lower():
            bad.append(f)

    if not bad:
        return

    log("[FATAL] One or more paths are outside the allowed root!")
    log(f"[FATAL] Required subpath: {REQUIRED_SUBPATH}\n")
    for p in bad:
        log(f"  INVALID: {p}")
    raise RuntimeError("Path validation failed")


def list_image_files_non_recursive(folder: Path) -> list[Path]:
    if not folder.is_dir():
        log(f"[WARN] Not a directory: {folder}")
        return []

    out: list[Path] = []
    try:
        for p in folder.iterdir():
            if not p.is_file():
                continue
            suf = p.suffix.lower()
            if suf == ".png" or suf == ".tga":
                out.append(p)
    except Exception as e:
        log(f"[WARN] Failed scanning {folder}: {e}")
        return []

    out.sort(key=lambda x: x.name.lower())
    return out


def gather_image_files_non_recursive(folders: list[Path]) -> list[Path]:
    image_files: list[Path] = []
    for folder in folders:
        image_files.extend(list_image_files_non_recursive(folder))
    image_files.sort(key=lambda p: p.name.lower())
    return image_files


# ==========================================================
# NO-MIP / UI / UPSCALE FILTERS
# ==========================================================
def load_no_mip_regexes_or_die(path: Path) -> list[re.Pattern]:
    if not path.is_file():
        raise RuntimeError(f"no_mip_regex.txt not found: {path}")

    patterns: list[re.Pattern] = []
    for raw in path.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, flags=re.IGNORECASE))
        except re.error as e:
            raise RuntimeError(f"Invalid regex in {path}: {line} ({e})")

    return patterns


def load_manual_ui_textures_or_die(path: Path) -> set[str]:
    if not path.is_file():
        raise RuntimeError(f"manual_ui_textures.txt not found: {path}")

    out: set[str] = set()
    for raw in path.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line.lower())

    return out


def load_never_upscale_or_die(path: Path) -> set[str]:
    if not path.is_file():
        raise RuntimeError(f"never_upscale.txt not found: {path}")

    out: set[str] = set()
    for raw in path.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line.lower())
    return out


def should_use_nomips(stem_lower: str, rx_list: list[re.Pattern], manual_set: set[str]) -> bool:
    if stem_lower in manual_set:
        return True

    for rx in rx_list:
        if rx.search(stem_lower) is not None:
            return True

    return False


def should_opacity_be_stripped_from_path(path_str: str) -> bool:
    return "opaque" in (path_str or "").lower()


# ==========================================================
# OPACITY (PERFORMANCE-GATED)
# ==========================================================
def path_contains_self_remade(path: Path) -> bool:
    return "self remade" in str(path).lower()


def image_is_fully_opaque_or_no_alpha(path: Path) -> bool:
    try:
        with Image.open(path) as im:
            if "A" not in im.getbands():
                return True

            rgba = im.convert("RGBA")
            a = rgba.getchannel("A")
            mn, mx = a.getextrema()

            # Treat as opaque if:
            # - all alpha == 255 (fully opaque)
            # - OR all alpha == 128 (legacy / half-alpha-but-meant-opaque)
            return (mn == mx) and (mn == 255 or mn == 128)
    except Exception as e:
        raise RuntimeError(f"Failed checking alpha opacity for {path}: {e}")


def build_nonupscaled_ctxr3_required_stems(
    image_files: list[Path],
    no_mip_regexes: list[re.Pattern],
    manual_ui_textures: set[str],
    is_demastered_run: bool,
) -> set[str]:
    out: set[str] = set()

    for img in image_files:
        stem_lower = img.stem.lower()

        if stem_lower in manual_ui_textures:
            out.add(stem_lower)
            continue

        if not is_demastered_run:
            if path_contains_self_remade(img) and should_use_nomips(stem_lower, no_mip_regexes, manual_ui_textures):
                out.add(stem_lower)

    return out


# ==========================================================
# DEMASTERED PS2 SOURCE REMAP HELPERS
# ==========================================================
def build_ps2_textures_map_or_die(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise RuntimeError(f"PS2 textures root does not exist or is not a directory: {root}")

    mapping: dict[str, Path] = {}
    duplicates: dict[str, list[Path]] = {}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf not in (".png", ".tga"):
            continue

        stem_lower = p.stem.lower()
        prev = mapping.get(stem_lower)
        if prev is None:
            mapping[stem_lower] = p
        else:
            if stem_lower not in duplicates:
                duplicates[stem_lower] = [prev]
            duplicates[stem_lower].append(p)

    if duplicates:
        log("[FATAL] Duplicate stems detected in PS2 textures root while building map:")
        for stem, paths in sorted(duplicates.items(), key=lambda x: x[0]):
            log(f"  {stem}:")
            for p in paths:
                log(f"    {p}")
        raise RuntimeError("PS2 textures map requires unique stems")

    log(f"[INFO] PS2 textures map contains {len(mapping)} unique stems")
    return mapping


def remap_demastered_self_remade_to_ps2(image_files: list[Path]) -> list[Path]:
    if not image_files:
        return image_files

    ps2_map = build_ps2_textures_map_or_die(PS2_TEXTURES_ROOT)

    remapped: list[Path] = []
    skipped: list[Path] = []

    for img in image_files:
        path_lower = str(img).lower()

        if path_contains_self_remade(img) and "demaster fixed" not in path_lower:
            stem_lower = img.stem.lower()
            ps2_path = ps2_map.get(stem_lower)

            if ps2_path is None:
                skipped.append(img)
                log(f"[DEMASTERED SKIP] No PS2 source by stem, skipping: {img}")
                continue

            log(f"[DEMASTERED] Using PS2 texture as source for self remade image:")
            log(f"             staging: {img}")
            log(f"             ps2 src: {ps2_path}")
            remapped.append(ps2_path)
            continue

        remapped.append(img)

    if skipped:
        try:
            out_path = STAGING_FOLDER / "demastered_missing_ps2_sources.txt"

            header = [
                "# Demastered run: missing PS2 source by stem",
                "# These Self Remade textures had no matching file under PS2_TEXTURES_ROOT.",
                "# They were skipped and not processed in this run.",
                "",
            ]

            lines = sorted({p.name.lower() for p in skipped})

            out_path.write_text(
                "\n".join(header + lines) + ("\n" if lines else ""),
                encoding="utf8",
            )

            log(f"[DEMASTERED] Wrote skip log: {out_path}")
        except Exception as e:
            log(f"[DEMASTERED WARN] Failed writing skip log: {e}")

    return remapped


# ==========================================================
# ERROR LOG HELPERS
# ==========================================================
def write_error_log_or_die(path: Path, failed_images: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted({p.name.lower() for p in failed_images})
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf8")


def remove_error_log_if_exists(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except Exception:
        pass


# ==========================================================
# "NOT YET CONVERTED" LOG HELPERS
# ==========================================================
NOT_YET_CONVERTED_TXT = "not yet converted.txt"


def write_not_yet_converted_txt(staging_folder: Path, missing_paths: list[Path]) -> None:
    out_path = staging_folder / NOT_YET_CONVERTED_TXT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = sorted({str(p) for p in missing_paths}, key=lambda s: s.lower())
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf8")


def remove_not_yet_converted_txt_if_exists(staging_folder: Path) -> None:
    out_path = staging_folder / NOT_YET_CONVERTED_TXT
    try:
        if out_path.is_file():
            out_path.unlink()
    except Exception:
        pass


# ==========================================================
# CSV HELPERS
# ==========================================================
def bool_from_csv(val: str) -> bool:
    v = (val or "").strip().lower()
    return v in ("1", "true", "yes", "y", "t")


def bool_to_csv(val: bool) -> str:
    return "true" if val else "false"


def ensure_csv_header_has_columns(header: list[str], needed_cols: list[str]) -> list[str]:
    existing_lower = [h.lower() for h in header]
    out = list(header)
    for col in needed_cols:
        if col.lower() not in existing_lower:
            out.append(col)
            existing_lower.append(col.lower())
    return out


def sort_rows_by_filename(rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda r: ((r.get("filename") or r.get("Filename") or r.get("FILENAME") or "").strip().lower()))


def write_conversion_csv_atomic(csv_path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    sort_rows_by_filename(rows)
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    tmp.replace(csv_path)


def append_conversion_csv_rows(csv_path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    if not csv_path.is_file():
        raise RuntimeError(f"CSV does not exist for append: {csv_path}")

    with csv_path.open("a", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        for row in rows:
            w.writerow(row)


# ==========================================================
# ORIGIN HELPERS
# ==========================================================
def origin_relative_to_required_subpath_or_die(image_path: Path) -> str:
    required_lower = REQUIRED_SUBPATH.lower()
    full_str = str(image_path)

    lower = full_str.lower()
    idx = lower.find(required_lower)
    if idx < 0:
        raise RuntimeError(f'Image path does not contain REQUIRED_SUBPATH "{REQUIRED_SUBPATH}": {image_path}')

    rel = full_str[idx + len(REQUIRED_SUBPATH):]
    rel = rel.lstrip(r"\/")

    rel_folder = str(Path(rel).parent)
    rel_folder = rel_folder.replace("/", "\\").strip("\\")
    return rel_folder


# ==========================================================
# LOAD / MAP CSV
# mapping entry:
# (before_hash, ctxr_hash, used_nomips_bool, origin_folder_string, opacity_stripped_bool, upscaled_bool,
#  upscaler_version_str, upscaler_type_str, upscaler_meta_present_bool, ctxr3_converted_bool,
#  filename_has_uppercase_bool)
#
# NOTE: CSV mipmaps column means "has mipmaps". Internally we track "used_nomips".
# ==========================================================
def load_conversion_csv_unique_or_die(
    csv_path: Path,
) -> tuple[
    dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]],
    list[dict[str, str]],
    list[str],
    bool,
]:
    if not csv_path.is_file():
        raise FileNotFoundError(f'Missing "{CONVERSION_CSV}" at {csv_path}')

    with csv_path.open("r", encoding="utf8", newline="") as f:
        rdr = csv.DictReader(f)
        if rdr.fieldnames is None:
            raise RuntimeError(f"{CONVERSION_CSV} has no header row")

        required = ["filename", "before_hash", "ctxr_hash", "mipmaps", "origin_folder", "opacity_stripped"]
        header_lower = [h.strip().lower() for h in rdr.fieldnames]
        for col in required:
            if col not in header_lower:
                raise RuntimeError(f'{CONVERSION_CSV} missing required column "{col}"')

        header = rdr.fieldnames
        header_has_upscaler_cols = ("upscaler_version" in header_lower) and ("upscaler_type" in header_lower)

        rows: list[dict[str, str]] = []
        mapping: dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]] = {}
        duplicates: list[str] = []

        for row in rdr:
            filename_raw = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "").strip()
            filename_has_upper = has_any_uppercase(filename_raw)

            filename = filename_raw
            before_hash = (row.get("before_hash") or row.get("Before_hash") or row.get("BEFORE_HASH") or "").strip().lower()
            ctxr_hash = (row.get("ctxr_hash") or row.get("Ctxr_hash") or row.get("CTXR_HASH") or "").strip().lower()

            mipmaps_raw = (row.get("mipmaps") or row.get("Mipmaps") or row.get("MIPMAPS") or "").strip()
            origin_folder = (row.get("origin_folder") or row.get("Origin_folder") or row.get("ORIGIN_FOLDER") or "").strip()

            opacity_raw = (row.get("opacity_stripped") or row.get("Opacity_stripped") or row.get("OPACITY_STRIPPED") or "").strip()

            upscaled_raw = (row.get("upscaled") or row.get("Upscaled") or row.get("UPSCALED") or "").strip().lower()

            upscaler_version_raw = (
                row.get("upscaler_version") or row.get("Upscaler_version") or row.get("UPSCALER_VERSION") or ""
            ).strip()
            upscaler_type_raw = (row.get("upscaler_type") or row.get("Upscaler_type") or row.get("UPSCALER_TYPE") or "").strip()

            ctxr3_converted_raw = (row.get("ctxr3_converted") or row.get("Ctxr3_converted") or row.get("CTXR3_CONVERTED") or "").strip()

            if not filename:
                continue

            has_mipmaps = bool_from_csv(mipmaps_raw)
            used_nomips = not has_mipmaps
            opacity_stripped = bool_from_csv(opacity_raw)

            if upscaled_raw:
                upscaled = bool_from_csv(upscaled_raw)
            else:
                upscaled = get_staging_upscaled_bool()

            upscaler_meta_present = bool(header_has_upscaler_cols and upscaler_version_raw and upscaler_type_raw)

            # If the column is missing or blank, treat as false.
            ctxr3_converted = bool_from_csv(ctxr3_converted_raw) if ctxr3_converted_raw else False

            name = filename.lower()
            if name in mapping:
                duplicates.append(filename)
            else:
                mapping[name] = (
                    before_hash,
                    ctxr_hash,
                    used_nomips,
                    origin_folder,
                    opacity_stripped,
                    upscaled,
                    upscaler_version_raw,
                    upscaler_type_raw,
                    upscaler_meta_present,
                    ctxr3_converted,
                    filename_has_upper,
                )

            rows.append(row)

        if duplicates:
            log("[FATAL] conversion_hashes.csv contains duplicate filename rows.")
            for d in sorted(set([x.lower() for x in duplicates])):
                log(f"  DUPLICATE: {d}")
            raise RuntimeError("conversion_hashes.csv filenames must be unique")

    log(f"[INFO] Loaded {len(mapping)} unique entries from {CONVERSION_CSV}\n")
    return mapping, rows, header, header_has_upscaler_cols


# ==========================================================
# IMAGE HASH + ORIGIN + OPACITY STRIPPED EXPECTATION (UNIQUENESS ENFORCED)
# ==========================================================
def hash_images_unique_or_die(
    image_files: list[Path],
    workers: int,
) -> tuple[dict[str, str], dict[str, str], dict[str, bool]]:
    if not image_files:
        log("[WARN] No .png or .tga files found in listed folders.")
        return {}, {}, {}

    log(f"[INFO] Hashing {len(image_files)} png/tga files\n")

    hashes_by_name: dict[str, set[str]] = {}
    origin_by_name: dict[str, set[str]] = {}
    opacity_expected_by_name: dict[str, set[bool]] = {}

    def worker(path: Path) -> tuple[str, str, str, bool]:
        stem = path.stem.lower()
        digest = sha1_file(path)
        origin = origin_relative_to_required_subpath_or_die(path)

        opaque_by_path = should_opacity_be_stripped_from_path(str(path))

        if path_contains_self_remade(path):
            opaque_by_pixels = image_is_fully_opaque_or_no_alpha(path)
            opacity_expected = opaque_by_path or opaque_by_pixels
        else:
            opacity_expected = opaque_by_path

        return (stem, digest, origin, opacity_expected)

    progress = ProgressTracker(len(image_files), "Hash images")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker, p) for p in image_files]
        for fut in as_completed(futures):
            name, digest, origin, opacity_expected = fut.result()

            s = hashes_by_name.get(name)
            if s is None:
                s = set()
                hashes_by_name[name] = s
            s.add(digest)

            o = origin_by_name.get(name)
            if o is None:
                o = set()
                origin_by_name[name] = o
            o.add(origin)

            oe = opacity_expected_by_name.get(name)
            if oe is None:
                oe = set()
                opacity_expected_by_name[name] = oe
            oe.add(opacity_expected)

            progress.update()

    progress.finish()

    bad_hash: list[tuple[str, list[str]]] = []
    bad_origin: list[tuple[str, list[str]]] = []
    bad_opacity: list[str] = []

    out_hash: dict[str, str] = {}
    out_origin: dict[str, str] = {}
    out_opacity_expected: dict[str, bool] = {}

    for name, digests in hashes_by_name.items():
        if len(digests) > 1:
            bad_hash.append((name, sorted(digests)))
            continue
        out_hash[name] = next(iter(digests))

    for name, origins in origin_by_name.items():
        if len(origins) > 1:
            bad_origin.append((name, sorted(origins)))
            continue
        out_origin[name] = next(iter(origins))

    for name, vals in opacity_expected_by_name.items():
        if len(vals) > 1:
            bad_opacity.append(name)
            continue
        out_opacity_expected[name] = next(iter(vals))

    if bad_hash:
        log("[FATAL] The same filename appeared with multiple different image hashes.")
        for name, digests in sorted(bad_hash, key=lambda x: x[0]):
            log(f"  {name}:")
            for d in digests:
                log(f"    {d}")
        raise RuntimeError("Duplicate image filenames with multiple hashes")

    if bad_origin:
        log("[FATAL] The same filename appeared in multiple different origin folders.")
        for name, origins in sorted(bad_origin, key=lambda x: x[0]):
            log(f"  {name}:")
            for o in origins:
                log(f"    {o}")
        raise RuntimeError("Duplicate image filenames across multiple folders")

    if bad_opacity:
        log("[FATAL] The same filename appeared with conflicting opacity_stripped expectations.")
        for n in sorted(bad_opacity):
            log(f"  {n}")
        raise RuntimeError("Duplicate image filenames with conflicting opaque detection")

    log(f"[INFO] Collected {len(out_hash)} unique image names (stems)\n")
    return out_hash, out_origin, out_opacity_expected


# ==========================================================
# CTXR3 LAUNCH HELPERS
# ==========================================================
def _needs_ctxr3_conversion_nonupscaled(
    stem_lower: str,
    conversion_map: dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]],
) -> bool:
    entry = conversion_map.get(stem_lower)
    if entry is None:
        return True
    ctxr3_converted = bool(entry[9])
    return not ctxr3_converted


# ==========================================================
# CTXR3 LAUNCH HELPERS (DEMASTERED PS2 REMAP SAFE, SPLIT OPAQUE/NORMAL)
# ==========================================================
import hashlib as _hashlib


CTX3R_PS2_TMP_ROOT_NAME = "_ctxr3_ps2_tmp"


def _stable_dir_tag(path: Path) -> str:
    b = str(path.resolve()).lower().encode("utf-8", errors="strict")
    return _hashlib.sha1(b).hexdigest()[:12]


def _is_under_path(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _safe_rmtree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except Exception as e:
        log(f"[CTXR3 WARN] Failed deleting temp dir {path}: {e}")


def _copy_ps2_sources_to_ctxr3_tmp_split_or_die(
    ps2_images: list[Path],
    tmp_root: Path,
) -> tuple[Path, list[tuple[Path, Path]]]:
    """
    Copy ONLY the requested PS2 source images into fresh temp subfolders and return:
      (batch_dir, [(run_cwd, representative_original_source_path), ...])

    We must preserve "opaque" knowledge for _launch_ctxr3.py, which checks for "opaque"
    in the path string. So we copy into:
      tmp/<tag>/opaque/<filename.ext>
      tmp/<tag>/normal/<filename.ext>

    Then the caller runs _launch_ctxr3.py with cwd set to each subfolder that has files.
    """
    if not ps2_images:
        raise RuntimeError("Internal error: _copy_ps2_sources_to_ctxr3_tmp_split_or_die called with 0 files")

    src_dir = ps2_images[0].parent
    tag = _stable_dir_tag(src_dir)
    batch_dir = tmp_root / tag

    if batch_dir.exists():
        try:
            shutil.rmtree(batch_dir)
        except Exception as e:
            raise RuntimeError(f"Failed clearing CTXR3 PS2 tmp batch dir: {batch_dir} ({e})")

    opaque_dir = batch_dir / "opaque"
    normal_dir = batch_dir / "normal"
    opaque_dir.mkdir(parents=True, exist_ok=True)
    normal_dir.mkdir(parents=True, exist_ok=True)

    opaque_rep: Path | None = None
    normal_rep: Path | None = None

    copied = 0
    for src in sorted(ps2_images, key=lambda p: p.name.lower()):
        if not src.is_file():
            raise RuntimeError(f"PS2 source does not exist: {src}")

        is_opaque = ("opaque" in str(src).lower())
        dst_parent = opaque_dir if is_opaque else normal_dir
        dst = dst_parent / src.name.lower()

        try:
            shutil.copy2(src, dst)
        except Exception as e:
            raise RuntimeError(
                "Failed copying PS2 source into CTXR3 tmp:\n"
                f"  src={src}\n"
                f"  dst={dst}\n"
                f"  err={e}"
            )

        copied += 1
        if is_opaque and opaque_rep is None:
            opaque_rep = src
        if (not is_opaque) and normal_rep is None:
            normal_rep = src

    out: list[tuple[Path, Path]] = []
    if opaque_rep is not None:
        out.append((opaque_dir, opaque_rep))
    if normal_rep is not None:
        out.append((normal_dir, normal_rep))

    log(f"[CTXR3] Demastered PS2 tmp batch prepared: {batch_dir} ({copied} file(s))")
    return (batch_dir, out)


def _run_launch_ctxr3_or_die(
    run_cwd: Path,
    staging_folder: Path,
    origin_override: str | None,
) -> None:
    target_dir_arg = str(staging_folder)

    args = [
        sys.executable,
        str(LAUNCH_CTXR3_PY),
        "-targetdir",
        target_dir_arg,
    ]

    if origin_override:
        args += ["-originfolder", origin_override]

    try:
        p = subprocess.run(
            args,
            cwd=str(run_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf8",
            errors="replace",
        )
    except Exception as e:
        raise RuntimeError(f"[CTXR3] Failed launching _launch_ctxr3.py in {run_cwd}: {e}")

    out = (p.stdout or "").rstrip()
    if out:
        log("[CTXR3 OUT]")
        log(out)

    if p.returncode != 0:
        raise RuntimeError(f"[CTXR3] _launch_ctxr3.py failed (rc={p.returncode}) in {run_cwd}")

def refresh_not_yet_converted_after_ctxr3(
    staging_folder: Path,
    image_files: list[Path],
    ctxr3_required_stems: set[str],
) -> None:
    remaining: list[Path] = []

    for img in image_files:
        stem_lower = img.stem.lower()

        if stem_lower not in ctxr3_required_stems:
            continue

        staged_ctxr = staging_folder / f"{stem_lower}.ctxr"
        if not staged_ctxr.is_file():
            remaining.append(img)

    if remaining:
        write_not_yet_converted_txt(staging_folder, remaining)
        log(f"[CTXR3] Updated {NOT_YET_CONVERTED_TXT} after ctxr3 run ({len(remaining)} remaining)")
    else:
        remove_not_yet_converted_txt_if_exists(staging_folder)
        log(f"[CTXR3] All pending ctxr3-managed textures are converted, removed {NOT_YET_CONVERTED_TXT}")

def launch_ctxr3_for_pending_or_die(
    image_files: list[Path],
    ctxr3_required_stems: set[str],
    conversion_map: dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]],
    staging_folder: Path,
) -> None:
    # Only used for NON-upscaled runs.
    if not LAUNCH_CTXR3_PY.is_file():
        raise RuntimeError(f"_launch_ctxr3.py not found: {LAUNCH_CTXR3_PY}")

    is_demastered_run = staging_folder_is_demastered()

    tmp_root = staging_folder / CTX3R_PS2_TMP_ROOT_NAME
    if is_demastered_run:
        tmp_root.mkdir(parents=True, exist_ok=True)

    by_dir: dict[Path, list[Path]] = {}
    not_yet_converted_paths: list[Path] = []

    for img in image_files:
        stem = img.stem.lower()
        if stem not in ctxr3_required_stems:
            continue

        if not _needs_ctxr3_conversion_nonupscaled(stem, conversion_map):
            continue

        staged_ctxr = staging_folder / f"{stem}.ctxr"
        if not staged_ctxr.is_file():
            not_yet_converted_paths.append(img)

        d = img.parent
        if d not in by_dir:
            by_dir[d] = []
        by_dir[d].append(img)

    if not_yet_converted_paths:
        write_not_yet_converted_txt(staging_folder, not_yet_converted_paths)
        log(f"[CTXR3] Wrote {NOT_YET_CONVERTED_TXT} with {len(not_yet_converted_paths)} path(s)")
    else:
        remove_not_yet_converted_txt_if_exists(staging_folder)

    if not by_dir:
        if is_demastered_run:
            _safe_rmtree(tmp_root)
        return

    log("[CTXR3] Launching ctxr3 conversion script for pending NON-upscaled ctxr3-managed textures.")

    try:
        for d in sorted(by_dir.keys(), key=lambda p: str(p).lower()):
            imgs = by_dir[d]
            stems = sorted({p.stem.lower() for p in imgs}, key=lambda s: s.lower())

            log(f"[CTXR3] Batch source dir: {d}")
            log(f"[CTXR3] Pending stems in this batch: {len(stems)}")

            if is_demastered_run and _is_under_path(d, PS2_TEXTURES_ROOT):
                batch_dir, runs = _copy_ps2_sources_to_ctxr3_tmp_split_or_die(imgs, tmp_root)

                try:
                    for run_cwd, rep_src in runs:
                        origin_override = origin_relative_to_required_subpath_or_die(rep_src)

                        log(f"[CTXR3] CWD: {run_cwd}")
                        _run_launch_ctxr3_or_die(
                            run_cwd=run_cwd,
                            staging_folder=staging_folder,
                            origin_override=origin_override,
                        )
                finally:
                    _safe_rmtree(batch_dir)

                continue

            log(f"[CTXR3] CWD: {d}")
            _run_launch_ctxr3_or_die(
                run_cwd=d,
                staging_folder=staging_folder,
                origin_override=None,
            )

    finally:
        if is_demastered_run:
            _safe_rmtree(tmp_root)


# ==========================================================
# PARAM EXPORT HELPERS
# ==========================================================
def delete_param_outputs_or_die(param_dir: Path) -> None:
    if not param_dir.is_dir():
        raise RuntimeError(f"Param folder does not exist or is not a directory: {param_dir}")

    deleted = 0
    failed = 0

    for p in sorted(param_dir.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf != ".dds" and suf != ".ctxr":
            continue

        try:
            p.unlink()
            deleted += 1
            log(f"[PARAM DEL] {p.name}")
        except Exception as e:
            failed += 1
            log(f"[PARAM FAIL] {p.name} (delete error: {e})")

    log(f"[PARAM] Deleted {deleted} file(s) in param folder")
    if failed:
        raise RuntimeError(f"Failed deleting {failed} file(s) in param folder")


def delete_tmp_rgb_outputs_or_die(tmp_dir: Path) -> None:
    if not tmp_dir.exists():
        return

    if not tmp_dir.is_dir():
        raise RuntimeError(f"Temp RGB folder exists but is not a directory: {tmp_dir}")

    deleted = 0
    failed = 0

    for p in sorted(tmp_dir.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        if p.suffix.lower() != ".png":
            continue

        try:
            p.unlink()
            deleted += 1
            log(f"[TMP RGB DEL] {p.name}")
        except Exception as e:
            failed += 1
            log(f"[TMP RGB FAIL] {p.name} (delete error: {e})")

    if deleted:
        log(f"[TMP RGB] Deleted {deleted} file(s)")
    if failed:
        raise RuntimeError(f"Failed deleting {failed} temp RGB file(s) in {tmp_dir}")


def make_temp_rgb_only_copy_or_die(src: Path, tmp_dir: Path) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / f"{src.stem.lower()}__rgb_tmp.png"

    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        r, g, b, _a = rgba.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgb.save(tmp_path, format="PNG", optimize=False)

    if not tmp_path.is_file():
        raise RuntimeError(f"Failed creating RGB-only temp copy: {tmp_path}")

    return tmp_path


def make_rgb_only_copy_named_or_die(src: Path, dst_png: Path) -> None:
    dst_png.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        r, g, b, _a = rgba.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgb.save(dst_png, format="PNG", optimize=False)

    if not dst_png.is_file():
        raise RuntimeError(f"Failed creating RGB-only PNG: {dst_png}")


def hash_ctxr_files_with_progress(ctxr_files: list[Path], workers: int, label: str) -> dict[Path, str]:
    ctxr_hash_by_path: dict[Path, str] = {}
    if not ctxr_files:
        return ctxr_hash_by_path

    log(f"[INFO] Hashing {len(ctxr_files)} ctxr files\n")

    progress = ProgressTracker(len(ctxr_files), label)

    def worker(path: Path) -> tuple[Path, str]:
        return (path, sha1_file(path))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker, p) for p in ctxr_files]
        for fut in as_completed(futures):
            p, digest = fut.result()
            ctxr_hash_by_path[p] = digest
            progress.update()

    progress.finish()
    return ctxr_hash_by_path


def delete_upscale_staging_dir_if_exists(path: Path) -> None:
    if not path.exists():
        return

    if path.is_file():
        raise RuntimeError(f"Upscaling staging path exists as a file, not a directory: {path}")

    try:
        shutil.rmtree(path)
        log(f"[UPSCALE] Cleared existing upscaling folder: {path}")
    except Exception as e:
        raise RuntimeError(f"Failed deleting existing upscaling folder {path}: {e}")


def delete_upscaled_image_pair_if_exists(path: Path) -> None:
    parent = path.parent
    stem = path.stem

    for ext in (".tga", ".png"):
        candidate = parent / f"{stem}{ext}"
        if candidate.is_file():
            try:
                candidate.unlink()
            except Exception as e:
                log(f"[UPSCALE CLEAN WARN] Failed to delete {candidate}: {e}")


def copy_images_for_upscaling_or_die(images: list[Path], dest_dir: Path) -> dict[Path, Path]:
    mapping: dict[Path, Path] = {}

    if not images:
        return mapping

    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    failed = 0

    for img in sorted(images, key=lambda p: p.name.lower()):
        dest = dest_dir / img.name
        try:
            shutil.copy2(img, dest)
            mapping[img] = dest
            copied += 1
        except Exception as e:
            failed += 1
            log(f"[UPSCALE FAIL] Could not copy {img} to {dest}: {e}")

    log(f"[UPSCALE] Copied {copied} image(s) to {dest_dir}")
    if failed:
        raise RuntimeError(f"Failed copying {failed} image(s) to upscaling folder")

    return mapping


def _is_chainner_running() -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq chaiNNer.exe"],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf8",
            errors="replace",
        )
    except Exception:
        return False

    return "chaiNNer.exe" in out


def run_chaiNNer_or_die(project: Path) -> None:
    if not CHAINNER_EXE.is_file():
        raise RuntimeError(f"chaiNNer.exe not found: {CHAINNER_EXE}")

    if not project.is_file():
        raise RuntimeError(f"chaiNNer project file not found: {project}")

    log(f"[UPSCALE] Launching chaiNNer with project:")
    log(f"         {project}")

    try:
        subprocess.Popen(
            [str(CHAINNER_EXE), str(project)],
            cwd=str(project.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to launch chaiNNer with project: {e}")

    log("[UPSCALE] Waiting for chaiNNer.exe to appear...")
    started = False
    start_wait_deadline = time.time() + 30.0

    while time.time() < start_wait_deadline:
        if _is_chainner_running():
            started = True
            break
        time.sleep(1.0)

    if not started:
        log("[UPSCALE WARN] chaiNNer.exe never appeared in tasklist; continuing WITHOUT waiting.")
        return

    log("[UPSCALE] chaiNNer detected. Waiting for it to close...")
    while _is_chainner_running():
        time.sleep(5.0)

    log("[UPSCALE] chaiNNer closed, continuing.")


# ==========================================================
# UPSCALED RESAVE TO POWER-OF-TWO (NO HASH CHANGES)
# ==========================================================
def _next_power_of_two(n: int) -> int:
    if n <= 0:
        return 1
    if (n & (n - 1)) == 0:
        return n
    p = 1
    while p < n:
        p <<= 1
    return p


def resave_images_to_pot_or_die(image_paths: list[Path]) -> None:
    if not image_paths:
        return

    processed = 0
    failed = 0

    for path in sorted(image_paths, key=lambda p: p.name.lower()):
        try:
            with Image.open(path) as im:
                width, height = im.size
                new_w = _next_power_of_two(width)
                new_h = _next_power_of_two(height)

                if new_w != width or new_h != height:
                    im = im.resize((new_w, new_h), Image.LANCZOS)

                suffix = path.suffix.lower()
                if suffix == ".png":
                    im.save(path, format="PNG", optimize=False)
                elif suffix == ".tga":
                    im.save(path, format="TGA")
                else:
                    im.save(path)

            processed += 1
            log(f"[UPSCALE POT] {path} -> {new_w}x{new_h}")
        except Exception as e:
            failed += 1
            log(f"[UPSCALE POT FAIL] {path}: {e}")

    log(f"[UPSCALE POT] Processed {processed} image(s) for power-of-two resizing")
    if failed:
        raise RuntimeError(f"Failed resizing/resaving {failed} image(s) to power-of-two dimensions")


def remap_chainner_tgas_to_png(mapping: dict[Path, Path]) -> None:
    switched = 0

    for orig, ups in list(mapping.items()):
        if ups.suffix.lower() != ".tga":
            continue

        png = ups.with_suffix(".png")
        if not png.is_file():
            continue

        if ups.is_file():
            try:
                ups.unlink()
                log(f"[UPSCALE] Deleted obsolete TGA after chaiNNer: {ups.name}")
            except Exception as e:
                log(f"[UPSCALE WARN] Failed to delete TGA {ups}: {e}")

        mapping[orig] = png
        switched += 1

    if switched:
        log(f"[UPSCALE] Switched {switched} upscaled TGA input(s) to PNG outputs")


def _dims_within_factor_wiggle(before: tuple[int, int], after: tuple[int, int], factor: int) -> bool:
    bw, bh = before
    aw, ah = after

    if bw <= 0 or bh <= 0 or aw <= 0 or ah <= 0:
        return False

    # Hard requirement: must actually upscale, cannot be same size (or smaller).
    if aw <= bw or ah <= bh:
        return False

    abs_wiggle = 4
    pct_wiggle = 0.03

    exp_w = bw * factor
    exp_h = bh * factor

    wig_w = max(abs_wiggle, int(round(exp_w * pct_wiggle)))
    wig_h = max(abs_wiggle, int(round(exp_h * pct_wiggle)))

    min_w = exp_w - wig_w
    max_w = exp_w + wig_w
    min_h = exp_h - wig_h
    max_h = exp_h + wig_h

    if aw < min_w or aw > max_w:
        return False
    if ah < min_h or ah > max_h:
        return False

    return True


def run_nvtt_exports_or_die(
    image_files: list[Path],
    conversion_map: dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]],
    image_hash_by_name: dict[str, str],
    image_origin_by_name: dict[str, str],
    image_used_nomips_by_name: dict[str, bool],
    image_opacity_expected_by_name: dict[str, bool],
    workers: int,
    no_mip_regexes: list[re.Pattern],
    manual_ui_textures: set[str],
    conversion_csv_path: Path,
    conversion_rows: list[dict[str, str]],
    conversion_header: list[str],
    ctxr3_required_stems: set[str],
) -> None:
    if not NVTT_EXPORT_EXE.is_file():
        raise RuntimeError(f"nvtt_export.exe not found: {NVTT_EXPORT_EXE}")
    if not DPF_DEFAULT.is_file():
        raise RuntimeError(f"Default DPF not found: {DPF_DEFAULT}")
    if not DPF_NOMIPS.is_file():
        raise RuntimeError(f"No-mips DPF not found: {DPF_NOMIPS}")
    if not PARAM_FOLDER.is_dir():
        raise RuntimeError(f"Param folder not found: {PARAM_FOLDER}")
    if not CTXR_TOOL_EXE.is_file():
        raise RuntimeError(f"CtxrTool.exe not found: {CTXR_TOOL_EXE}")

    upscaled_expected = get_staging_upscaled_bool()
    upscale_factor = get_staging_upscale_factor_or_one()
    upscaler_version, upscaler_type = get_current_upscaler_metadata_for_run(upscaled_expected)

    # ==========================================================
    # Build missing list.
    # For NON-upscaled runs:
    #   - Skip any stem handled by the ctxr3 pipeline.
    # For upscaled runs:
    #   - No ctxr3-managed skipping.
    # ==========================================================
    missing: list[Path] = []
    skipped_ctxr3_managed_nonupscaled: list[Path] = []

    for img in image_files:
        name = img.stem.lower()

        if (not upscaled_expected) and (name in ctxr3_required_stems):
            skipped_ctxr3_managed_nonupscaled.append(img)
            continue

        if name in conversion_map:
            continue

        missing.append(img)

    if skipped_ctxr3_managed_nonupscaled:
        log(
            f"[PARAM] Skipping {len(skipped_ctxr3_managed_nonupscaled)} NON-upscaled ctxr3-managed texture(s) "
            "(handled by _launch_ctxr3.py)."
        )

    error_log = STAGING_FOLDER / ERROR_LOG_PATH

    if not missing:
        log("[PARAM] No images missing from conversion_hashes.csv for nvtt/CtxrTool. Nothing to export.")
        remove_error_log_if_exists(error_log)
        return

    if upscaled_expected:
        log("[UPSCALE] Staging folder is an upscaled variant (2x/4x).")
        log(f"[UPSCALE] Preparing {len(missing)} image(s) for external upscaling.")

        chain_alpha: list[Path] = []
        chain_normal: list[Path] = []

        for img in missing:
            stem_lower = img.stem.lower()
            if image_opacity_expected_by_name.get(stem_lower, False):
                chain_alpha.append(img)
            else:
                chain_normal.append(img)

        mapping_normal: dict[Path, Path] = {}
        mapping_alpha: dict[Path, Path] = {}

        if chain_normal:
            mapping_normal = copy_images_for_upscaling_or_die(chain_normal, UPSCALE_STAGING_DIR)

        if chain_alpha:
            mapping_alpha = copy_images_for_upscaling_or_die(chain_alpha, UPSCALE_STAGING_DIR_STRIPPED_OPACITY)

            for orig, ups in list(mapping_alpha.items()):
                stem_lower = orig.stem.lower()
                opacity_expected = image_opacity_expected_by_name.get(stem_lower, False)
                if not opacity_expected:
                    continue

                rgb_dest = ups.with_suffix(".png")

                try:
                    if rgb_dest.resolve() == ups.resolve():
                        tmp = ups.with_name(ups.name + ".rgbtmp.png")
                        if tmp.is_file():
                            tmp.unlink()

                        make_rgb_only_copy_named_or_die(ups, tmp)
                        tmp.replace(ups)

                        mapping_alpha[orig] = ups
                        log(f"[UPSCALE OPACITY] Stripped alpha before upscaling (in-place PNG): {orig.name} -> {ups.name}")
                    else:
                        if rgb_dest.is_file():
                            rgb_dest.unlink()

                        make_rgb_only_copy_named_or_die(ups, rgb_dest)

                        for ext in (".tga", ".png"):
                            candidate = ups.with_suffix(ext)
                            if candidate.resolve() == rgb_dest.resolve():
                                continue
                            if candidate.is_file():
                                try:
                                    candidate.unlink()
                                except Exception as e:
                                    log(f"[UPSCALE OPACITY WARN] Failed deleting {candidate}: {e}")

                        mapping_alpha[orig] = rgb_dest
                        log(f"[UPSCALE OPACITY] Stripped alpha before upscaling: {orig.name} -> {rgb_dest.name}")

                except Exception as e:
                    raise RuntimeError(f"Failed pre-upscale opacity stripping for {ups}: {e}")

        dims_before_normal: dict[Path, tuple[int, int]] = {}
        dims_before_alpha: dict[Path, tuple[int, int]] = {}

        for orig, ups in mapping_normal.items():
            try:
                with Image.open(ups) as im:
                    dims_before_normal[orig] = im.size
            except Exception as e:
                raise RuntimeError(f"Failed reading dimensions before upscaling for {ups}: {e}")

        for orig, ups in mapping_alpha.items():
            try:
                with Image.open(ups) as im:
                    dims_before_alpha[orig] = im.size
            except Exception as e:
                raise RuntimeError(f"Failed reading dimensions before upscaling for {ups}: {e}")

        if mapping_normal:
            run_chaiNNer_or_die(get_chainner_project_for_staging(stripped_opacity=False))
            remap_chainner_tgas_to_png(mapping_normal)

        if mapping_alpha:
            run_chaiNNer_or_die(get_chainner_project_for_staging(stripped_opacity=True))
            remap_chainner_tgas_to_png(mapping_alpha)

        failed_factor: list[Path] = []
        dims_after_normal: dict[Path, tuple[int, int]] = {}
        dims_after_alpha: dict[Path, tuple[int, int]] = {}

        def validate_mapping(
            mapping: dict[Path, Path],
            dims_before: dict[Path, tuple[int, int]],
            dims_after_out: dict[Path, tuple[int, int]],
        ) -> None:
            for orig, ups in mapping.items():
                try:
                    with Image.open(ups) as im:
                        dims_after_out[orig] = im.size
                except Exception as e:
                    raise RuntimeError(f"Failed reading dimensions after upscaling for {ups}: {e}")

                before = dims_before.get(orig)
                after = dims_after_out[orig]
                if before is None:
                    failed_factor.append(orig)
                    continue

                if not _dims_within_factor_wiggle(before, after, upscale_factor):
                    failed_factor.append(orig)

        validate_mapping(mapping_normal, dims_before_normal, dims_after_normal)
        validate_mapping(mapping_alpha, dims_before_alpha, dims_after_alpha)

        if failed_factor:
            log("[UPSCALE WARN] The following image(s) failed the expected upscaling factor check and will be skipped:")

            failed_set = set(failed_factor)

            for p in sorted(failed_set, key=lambda x: x.name.lower()):
                b = dims_before_normal.get(p) or dims_before_alpha.get(p) or ("?", "?")
                a = dims_after_normal.get(p) or dims_after_alpha.get(p) or ("?", "?")
                log(f"  {p}  ({b[0]}x{b[1]} -> {a[0]}x{a[1]}) expected ~{upscale_factor}x")

            for orig in failed_set:
                ups = mapping_normal.get(orig) or mapping_alpha.get(orig)
                if ups is not None:
                    delete_upscaled_image_pair_if_exists(ups)

            missing = [img for img in missing if img not in failed_set]

            log(f"[UPSCALE] {len(failed_set)} image(s) failed factor check and were removed.")

            if not missing:
                log("[UPSCALE] No images left after removing failed upscales; skipping nvtt_export stage.")
                remove_error_log_if_exists(error_log)
                return

        merged_mapping: dict[Path, Path] = {}
        merged_mapping.update(mapping_normal)
        merged_mapping.update(mapping_alpha)

        new_missing: list[Path] = []
        for orig in missing:
            ups = merged_mapping.get(orig)
            if ups is None:
                log(f"[UPSCALE WARN] No upscaled file found for {orig} in mapping; skipping.")
                continue
            new_missing.append(ups)

        missing = new_missing

        if not missing:
            log("[UPSCALE] No images left to process after mapping to upscaled copies; skipping nvtt_export stage.")
            remove_error_log_if_exists(error_log)
            return

        log("[UPSCALE] Resaving upscaled images to power-of-two dimensions...")
        resave_images_to_pot_or_die(missing)

    needed_cols = [
        "filename",
        "before_hash",
        "ctxr_hash",
        "mipmaps",
        "origin_folder",
        "opacity_stripped",
        "upscaled",
        "upscaler_version",
        "upscaler_type",
        "ctxr3_converted",
    ]
    conversion_header = ensure_csv_header_has_columns(list(conversion_header), needed_cols)

    log(f"[PARAM] Exporting {len(missing)} missing image(s) via nvtt_export + CtxrTool\n")

    os.chdir(str(PARAM_FOLDER))

    tmp_rgb_dir = PARAM_FOLDER / "_tmp_rgb_only"
    progress = ProgressTracker(len(missing), "Param export")

    def worker(img_path: Path) -> tuple[Path, bool, str, str, str, bool, str, bool]:
        stem_lower = img_path.stem.lower()
        out_dds = PARAM_FOLDER / f"{stem_lower}.dds"
        out_ctxr = PARAM_FOLDER / f"{stem_lower}.ctxr"

        tmp_rgb_path: Path | None = None

        def cleanup_param_ctxr():
            try:
                if out_ctxr.is_file():
                    out_ctxr.unlink()
            except Exception:
                pass

        def cleanup_tmp_rgb():
            nonlocal tmp_rgb_path
            if tmp_rgb_path is None:
                return
            try:
                if tmp_rgb_path.is_file():
                    tmp_rgb_path.unlink()
            except Exception:
                pass
            tmp_rgb_path = None

        used_nomips = should_use_nomips(stem_lower, no_mip_regexes, manual_ui_textures)
        if upscaled_expected and stem_lower in manual_ui_textures:
            used_nomips = False

        dpf_to_use = DPF_NOMIPS if used_nomips else DPF_DEFAULT

        before_hash = image_hash_by_name.get(stem_lower, "").lower()
        if not before_hash:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, "Missing before_hash for image (unexpected)", "", "", used_nomips, "", False)

        origin_folder = image_origin_by_name.get(stem_lower, "")
        if not origin_folder:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, "Missing origin_folder for image (unexpected)", before_hash, "", used_nomips, origin_folder, False)

        opacity_expected = image_opacity_expected_by_name.get(stem_lower, False)

        nvtt_input_path = img_path
        if opacity_expected:
            try:
                tmp_rgb_path = make_temp_rgb_only_copy_or_die(img_path, tmp_rgb_dir)
                nvtt_input_path = tmp_rgb_path
            except Exception as e:
                cleanup_tmp_rgb()
                if upscaled_expected:
                    delete_upscaled_image_pair_if_exists(img_path)
                cleanup_param_ctxr()
                return (img_path, False, f"Failed creating RGB-only temp copy: {e}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        nvtt_args = [
            str(NVTT_EXPORT_EXE),
            "-p",
            str(dpf_to_use),
            "-o",
            str(out_dds),
            str(nvtt_input_path),
        ]

        try:
            nvtt = subprocess.run(
                nvtt_args,
                cwd=str(PARAM_FOLDER),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf8",
                errors="replace",
            )
        except Exception as e:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"nvtt_export exception: {e}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        if nvtt.returncode != 0:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            out = (nvtt.stdout or "").rstrip()
            msg = f"nvtt_export failed (rc={nvtt.returncode})"
            if out:
                msg += "\n" + out
            return (img_path, False, msg, before_hash, "", used_nomips, origin_folder, opacity_expected)

        if not out_dds.is_file():
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"nvtt_export reported success but DDS was not created: {out_dds}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        ctxr_args = [str(CTXR_TOOL_EXE), str(out_dds)]

        try:
            ctxr = subprocess.run(
                ctxr_args,
                cwd=str(PARAM_FOLDER),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf8",
                errors="replace",
            )
        except Exception as e:
            try:
                out_dds.unlink()
            except Exception:
                pass
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"CtxrTool exception: {e}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        ctxr_out = (ctxr.stdout or "").strip()
        ctxr_ok = (ctxr_out == CTXR_TOOL_SUCCESS_LINE)

        try:
            out_dds.unlink()
        except Exception as e:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            msg = "DDS delete failed"
            if ctxr_ok:
                msg += f": {e}"
            return (img_path, False, msg, before_hash, "", used_nomips, origin_folder, opacity_expected)

        if not ctxr_ok:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            msg = "CtxrTool failed (unexpected output)"
            if ctxr_out:
                msg += "\n" + ctxr_out
            return (img_path, False, msg, before_hash, "", used_nomips, origin_folder, opacity_expected)

        if not out_ctxr.is_file():
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"CtxrTool reported success but CTXR was not created: {out_ctxr}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        try:
            ctxr_hash = sha1_file(out_ctxr).lower()
        except Exception as e:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"Failed hashing produced CTXR: {e}", before_hash, "", used_nomips, origin_folder, opacity_expected)

        staging_ctxr = STAGING_FOLDER / out_ctxr.name
        try:
            if staging_ctxr.exists():
                staging_ctxr.unlink()

            shutil.copy2(out_ctxr, staging_ctxr)

            if not staging_ctxr.is_file():
                cleanup_tmp_rgb()
                if upscaled_expected:
                    delete_upscaled_image_pair_if_exists(img_path)
                cleanup_param_ctxr()
                return (img_path, False, "Copy reported success but staged CTXR does not exist", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)

            try:
                dst_hash = sha1_file(staging_ctxr).lower()
                if dst_hash != ctxr_hash:
                    cleanup_tmp_rgb()
                    if upscaled_expected:
                        delete_upscaled_image_pair_if_exists(img_path)
                    cleanup_param_ctxr()
                    return (img_path, False, f"Staged CTXR hash mismatch (src={ctxr_hash} dst={dst_hash})", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)
            except Exception as e:
                cleanup_tmp_rgb()
                if upscaled_expected:
                    delete_upscaled_image_pair_if_exists(img_path)
                cleanup_param_ctxr()
                return (img_path, False, f"Failed verifying staged CTXR hash: {e}", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)

            try:
                out_ctxr.unlink()
            except Exception as e:
                cleanup_tmp_rgb()
                if upscaled_expected:
                    delete_upscaled_image_pair_if_exists(img_path)
                cleanup_param_ctxr()
                return (img_path, False, f"Failed deleting param CTXR after copy: {e}", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)

        except Exception as e:
            cleanup_tmp_rgb()
            if upscaled_expected:
                delete_upscaled_image_pair_if_exists(img_path)
            cleanup_param_ctxr()
            return (img_path, False, f"Failed copying CTXR to staging: {e}", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)

        cleanup_tmp_rgb()
        if upscaled_expected:
            delete_upscaled_image_pair_if_exists(img_path)

        return (img_path, True, "", before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected)

    ok = 0
    fail = 0
    failed_images: list[Path] = []

    pending_rows: list[dict[str, str]] = []
    last_flush = time.monotonic()

    def flush_pending_rows() -> None:
        nonlocal last_flush, pending_rows

        if not pending_rows:
            last_flush = time.monotonic()
            return

        append_conversion_csv_rows(conversion_csv_path, conversion_header, pending_rows)

        conversion_rows.extend(pending_rows)
        for r in pending_rows:
            name = (r.get("filename") or "").strip().lower()
            has_mipmaps = bool_from_csv(r.get("mipmaps", ""))
            used_nomips_local = not has_mipmaps
            opacity_stripped = bool_from_csv(r.get("opacity_stripped", ""))
            upscaled_val = bool_from_csv(r.get("upscaled", ""))
            uv = (r.get("upscaler_version") or "").strip()
            ut = (r.get("upscaler_type") or "").strip()
            meta_present = bool(uv and ut)
            ctxr3_converted_val = bool_from_csv((r.get("ctxr3_converted") or "").strip()) if (r.get("ctxr3_converted") or "").strip() else False

            conversion_map[name] = (
                (r.get("before_hash") or "").lower(),
                (r.get("ctxr_hash") or "").lower(),
                used_nomips_local,
                (r.get("origin_folder") or ""),
                opacity_stripped,
                upscaled_val,
                uv,
                ut,
                meta_present,
                ctxr3_converted_val,
                False,
            )

        log(f"[CSV] Appended {len(pending_rows)} row(s)")
        pending_rows = []
        last_flush = time.monotonic()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker, p) for p in missing]
        for fut in as_completed(futures):
            img_path, success, details, before_hash, ctxr_hash, used_nomips, origin_folder, opacity_expected = fut.result()

            if success:
                ok += 1
                log(f"[PARAM OK] {img_path}")

                filename = img_path.stem.lower()
                has_mipmaps = not used_nomips

                pending_rows.append(
                    {
                        "filename": filename,
                        "before_hash": before_hash,
                        "ctxr_hash": ctxr_hash,
                        "mipmaps": bool_to_csv(has_mipmaps),
                        "origin_folder": origin_folder,
                        "opacity_stripped": bool_to_csv(opacity_expected),
                        "upscaled": bool_to_csv(upscaled_expected),
                        "upscaler_version": upscaler_version,
                        "upscaler_type": upscaler_type,
                        "ctxr3_converted": "false",
                    }
                )
            else:
                fail += 1
                failed_images.append(img_path)
                log(f"[PARAM FAIL] {img_path}")
                if details.strip():
                    log(details.rstrip())

            progress.update()

            now = time.monotonic()
            if now - last_flush >= CSV_FLUSH_SECONDS:
                flush_pending_rows()

    progress.finish()
    flush_pending_rows()

    log(f"\n[PARAM RESULT] OK: {ok}")
    log(f"[PARAM RESULT] FAIL: {fail}")

    if fail:
        write_error_log_or_die(error_log, failed_images)
        raise RuntimeError("One or more nvtt_export/CtxrTool jobs failed")
    else:
        remove_error_log_if_exists(error_log)

    write_conversion_csv_atomic(conversion_csv_path, conversion_header, conversion_rows)
    log("[CSV] Final alphabetical normalization complete")


# ==========================================================
# PRUNE: CSV entries that have no staged CTXR file
# ==========================================================
def prune_csv_entries_missing_staged_ctxr(
    conversion_csv_path: Path,
    conversion_header: list[str],
    conversion_rows: list[dict[str, str]],
    conversion_map: dict[str, tuple[str, str, bool, str, bool, bool, str, str, bool, bool, bool]],
) -> int:
    staged_ctxr_stems: set[str] = set()
    for p in STAGING_FOLDER.iterdir():
        if p.is_file() and p.suffix.lower() == ".ctxr":
            staged_ctxr_stems.add(p.stem.lower())

    if not staged_ctxr_stems:
        removed = len(conversion_rows)
        if removed:
            conversion_rows[:] = []
            conversion_map.clear()
            write_conversion_csv_atomic(conversion_csv_path, conversion_header, conversion_rows)
            log(f"[CSV] Removed {removed} row(s): no staged CTXR files exist")
        return removed

    pruned_rows: list[dict[str, str]] = []
    removed = 0

    for row in conversion_rows:
        filename = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "").strip().lower()
        if not filename:
            continue

        if filename not in staged_ctxr_stems:
            removed += 1
            continue

        pruned_rows.append(row)

    if removed:
        conversion_rows[:] = pruned_rows

        for k in list(conversion_map.keys()):
            if k not in staged_ctxr_stems:
                del conversion_map[k]

        write_conversion_csv_atomic(conversion_csv_path, conversion_header, conversion_rows)
        log(f"[CSV] Removed {removed} row(s): listed in CSV but missing staged CTXR")

    return removed


def main() -> int:
    folders_txt = STAGING_FOLDER / FOLDERS_TXT
    conversion_csv = STAGING_FOLDER / CONVERSION_CSV

    try:
        delete_upscale_staging_dir_if_exists(UPSCALE_STAGING_DIR)
        delete_upscale_staging_dir_if_exists(UPSCALE_STAGING_DIR_STRIPPED_OPACITY)

        log(f"[INFO] STAGING_FOLDER: {STAGING_FOLDER}")
        is_upscaled_run = get_staging_upscaled_bool()
        is_demastered_run = staging_folder_is_demastered()
        log(f"[INFO] This run is treated as {'UPSCALED (2x/4x)' if is_upscaled_run else 'NON-upscaled'}")
        if is_demastered_run:
            log("[INFO] Detected Demastered staging run. Self remade images (except 'Demaster Fixed') will use PS2 sources.")

        folders = read_folder_list(folders_txt)
        if not folders:
            log("[ERROR] No folders listed")
            return pause_and_exit(1)

        validate_paths_or_die(folders)

        workers = max(1, min(32, (os.cpu_count() or 8) * 2))

        no_mip_regexes = load_no_mip_regexes_or_die(NO_MIP_REGEX_PATH)
        manual_ui_textures = load_manual_ui_textures_or_die(MANUAL_UI_TEXTURES_PATH)

        never_upscale_stems: set[str] = set()
        if is_upscaled_run:
            never_upscale_stems = load_never_upscale_or_die(NEVER_UPSCALE_PATH)

        original_image_files = gather_image_files_non_recursive(folders)

        ctxr3_required_stems: set[str] = set()
        if not is_upscaled_run:
            ctxr3_required_stems = build_nonupscaled_ctxr3_required_stems(
                original_image_files,
                no_mip_regexes,
                manual_ui_textures,
                is_demastered_run,
            )
            if ctxr3_required_stems:
                log(f"[CTXR3] NON-upscaled ctxr3-managed stems discovered: {len(ctxr3_required_stems)}")

        image_files = list(original_image_files)

        if is_upscaled_run and never_upscale_stems:
            filtered: list[Path] = []
            skipped = 0
            for img in image_files:
                if img.stem.lower() in never_upscale_stems:
                    skipped += 1
                    continue
                filtered.append(img)
            image_files = filtered
            if skipped:
                log(f"[UPSCALE] Skipped {skipped} image(s) listed in never_upscale.txt for upscaled staging run")

        if is_demastered_run:
            image_files = remap_demastered_self_remade_to_ps2(image_files)

        image_hash_by_name, image_origin_by_name, image_opacity_expected_by_name = hash_images_unique_or_die(image_files, workers)

        image_used_nomips_by_name: dict[str, bool] = {}
        for img in image_files:
            stem_lower = img.stem.lower()
            if stem_lower not in image_used_nomips_by_name:
                used_nomips = should_use_nomips(stem_lower, no_mip_regexes, manual_ui_textures)
                if is_upscaled_run and stem_lower in manual_ui_textures:
                    used_nomips = False
                image_used_nomips_by_name[stem_lower] = used_nomips

        conversion_map, conversion_rows, conversion_header, header_has_upscaler_cols = load_conversion_csv_unique_or_die(conversion_csv)
        if not conversion_header:
            conversion_header = [
                "filename",
                "before_hash",
                "ctxr_hash",
                "mipmaps",
                "origin_folder",
                "opacity_stripped",
                "upscaled",
                "upscaler_version",
                "upscaler_type",
                "ctxr3_converted",
            ]

        needed_cols = [
            "filename",
            "before_hash",
            "ctxr_hash",
            "mipmaps",
            "origin_folder",
            "opacity_stripped",
            "upscaled",
            "upscaler_version",
            "upscaler_type",
            "ctxr3_converted",
        ]
        conversion_header = ensure_csv_header_has_columns(list(conversion_header), needed_cols)

        with conversion_csv.open("r", encoding="utf8", newline="") as f:
            rdr = csv.reader(f)
            first = next(rdr, None)
        if first is None:
            raise RuntimeError(f"{CONVERSION_CSV} is empty or unreadable")
        file_header_lower = [h.strip().lower() for h in first]

        if any(col.lower() not in file_header_lower for col in needed_cols):
            if not is_upscaled_run:
                for row in conversion_rows:
                    if "upscaler_version" not in row or not (row.get("upscaler_version") or "").strip():
                        row["upscaler_version"] = "0"
                    if "upscaler_type" not in row or not (row.get("upscaler_type") or "").strip():
                        row["upscaler_type"] = "none"
            else:
                for row in conversion_rows:
                    if "upscaler_version" not in row:
                        row["upscaler_version"] = ""
                    if "upscaler_type" not in row:
                        row["upscaler_type"] = ""

            for row in conversion_rows:
                if "ctxr3_converted" not in row or not (row.get("ctxr3_converted") or "").strip():
                    row["ctxr3_converted"] = "false"

            write_conversion_csv_atomic(conversion_csv, conversion_header, conversion_rows)
            log(f"[CSV] Rewrote {CONVERSION_CSV} to add missing columns")

            conversion_map, conversion_rows, conversion_header, header_has_upscaler_cols = load_conversion_csv_unique_or_die(conversion_csv)

        case_mismatch_names: set[str] = set()

        for name, entry in conversion_map.items():
            filename_has_upper = bool(entry[10])
            if filename_has_upper:
                case_mismatch_names.add(name)

        staged_ctxr_case_bad: list[Path] = []
        staged_ctxr_all: list[Path] = sorted(
            [p for p in STAGING_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr"],
            key=lambda p: p.name.lower(),
        )
        for p in staged_ctxr_all:
            if has_any_uppercase(p.name):
                staged_ctxr_case_bad.append(p)
                case_mismatch_names.add(p.stem.lower())

        if staged_ctxr_case_bad:
            delete_failures = 0
            for p in staged_ctxr_case_bad:
                try:
                    p.unlink()
                    log(f"[DEL CASE-MISMATCH] {p.name}")
                except Exception as e:
                    log(f"[FAIL CASE-MISMATCH] {p.name} (delete error: {e})")
                    delete_failures += 1
            if delete_failures:
                return pause_and_exit(1)

        if case_mismatch_names:
            pruned_rows: list[dict[str, str]] = []
            removed = 0

            for row in conversion_rows:
                filename_raw = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "").strip()
                filename_lower = filename_raw.lower()
                if filename_lower and filename_lower in case_mismatch_names:
                    removed += 1
                    continue
                pruned_rows.append(row)

            if removed:
                conversion_rows[:] = pruned_rows

                for k in list(conversion_map.keys()):
                    if k in case_mismatch_names:
                        del conversion_map[k]

                write_conversion_csv_atomic(conversion_csv, conversion_header, conversion_rows)
                log(f"[CSV] Removed {removed} row(s) from {CONVERSION_CSV} due to uppercase filename mismatch")

            delete_failures = 0
            deleted = 0
            for stem in sorted(case_mismatch_names):
                ctxr_path = STAGING_FOLDER / f"{stem}.ctxr"
                if ctxr_path.is_file():
                    try:
                        ctxr_path.unlink()
                        log(f"[DEL CASE-MISMATCH] {ctxr_path.name}")
                        deleted += 1
                    except Exception as e:
                        log(f"[FAIL CASE-MISMATCH] {ctxr_path.name} (delete error: {e})")
                        delete_failures += 1

            if delete_failures:
                return pause_and_exit(1)

        if is_upscaled_run and never_upscale_stems:
            never_names_lower = {s.lower() for s in never_upscale_stems}
            pruned_rows: list[dict[str, str]] = []
            removed_never = 0
            delete_failures = 0

            for row in conversion_rows:
                filename = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "")
                filename_lower = filename.strip().lower()
                if filename_lower and filename_lower in never_names_lower:
                    removed_never += 1

                    if filename_lower in conversion_map:
                        del conversion_map[filename_lower]

                    ctxr_path = STAGING_FOLDER / f"{filename_lower}.ctxr"
                    if ctxr_path.is_file():
                        try:
                            ctxr_path.unlink()
                            log(f"[DEL NEVER_UPSCALE] {ctxr_path.name}")
                        except Exception as e:
                            log(f"[FAIL NEVER_UPSCALE] {ctxr_path.name} (delete error: {e})")
                            delete_failures += 1
                    continue

                pruned_rows.append(row)

            if removed_never:
                conversion_rows[:] = pruned_rows
                write_conversion_csv_atomic(conversion_csv, conversion_header, conversion_rows)
                log(f"[CSV] Removed {removed_never} row(s) for never_upscale entries")

            if delete_failures:
                return pause_and_exit(1)

        ctxr_files = sorted(
            [p for p in STAGING_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr"],
            key=lambda p: p.name.lower(),
        )

        upscaled_expected_main = is_upscaled_run
        current_upscaler_version, current_upscaler_type = get_current_upscaler_metadata_for_run(upscaled_expected_main)

        early_mismatch_names: set[str] = set()

        for name, (
            csv_before,
            _csv_ctxr,
            csv_used_nomips,
            csv_origin,
            csv_opacity_stripped,
            csv_upscaled,
            csv_upscaler_version,
            csv_upscaler_type,
            csv_upscaler_meta_present,
            csv_ctxr3_converted,
            csv_filename_has_upper,
        ) in conversion_map.items():
            img_before = image_hash_by_name.get(name)
            img_origin = image_origin_by_name.get(name)
            img_used_nomips = image_used_nomips_by_name.get(name)
            img_opacity_expected = image_opacity_expected_by_name.get(name)

            if img_before is None or img_origin is None or img_used_nomips is None or img_opacity_expected is None:
                continue

            if csv_filename_has_upper:
                early_mismatch_names.add(name)
                continue

            origin_ok = (str(csv_origin).strip().lower() == str(img_origin).strip().lower())
            mip_ok = (csv_used_nomips == img_used_nomips)
            before_ok = (csv_before == (img_before or "").lower())
            opacity_ok = (csv_opacity_stripped == img_opacity_expected)
            upscaled_ok = (csv_upscaled == upscaled_expected_main)

            if upscaled_expected_main:
                upscaler_ok = bool(
                    csv_upscaler_meta_present
                    and (csv_upscaler_version == current_upscaler_version)
                    and (csv_upscaler_type == current_upscaler_type)
                )
            else:
                uv = (csv_upscaler_version or "").strip() or "0"
                ut = (csv_upscaler_type or "").strip() or "none"
                upscaler_ok = (uv == "0" and ut == "none")

            ctxr3_ok = True
            if (not upscaled_expected_main) and (name in ctxr3_required_stems):
                ctxr3_ok = (csv_ctxr3_converted is True)

            if not (origin_ok and mip_ok and before_ok and opacity_ok and upscaled_ok and upscaler_ok and ctxr3_ok):
                early_mismatch_names.add(name)

        delete_failures = 0
        if early_mismatch_names and ctxr_files:
            for ctxr in ctxr_files:
                name = ctxr.stem.lower()
                if name not in early_mismatch_names:
                    continue
                try:
                    ctxr.unlink()
                    log(f"[DEL META-MISMATCH] {ctxr.name}")
                except Exception as e:
                    log(f"[FAIL META-MISMATCH] {ctxr.name} (delete error: {e})")
                    delete_failures += 1

        if early_mismatch_names:
            pruned_rows: list[dict[str, str]] = []
            removed = 0

            for row in conversion_rows:
                filename = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "").strip().lower()
                if filename and filename in early_mismatch_names:
                    removed += 1
                    continue
                pruned_rows.append(row)

            if removed:
                conversion_rows[:] = pruned_rows

                for k in list(conversion_map.keys()):
                    if k in early_mismatch_names:
                        del conversion_map[k]

                write_conversion_csv_atomic(conversion_csv, conversion_header, conversion_rows)
                log(f"[CSV] Removed {removed} row(s) from {CONVERSION_CSV} due to metadata changes")

        if delete_failures:
            return pause_and_exit(1)

        ctxr_files = sorted(
            [p for p in STAGING_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr"],
            key=lambda p: p.name.lower(),
        )

        prune_csv_entries_missing_staged_ctxr(conversion_csv, conversion_header, conversion_rows, conversion_map)

        ctxr_files = sorted(
            [p for p in STAGING_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr"],
            key=lambda p: p.name.lower(),
        )

        deleted_missing_csv = 0
        delete_failures = 0

        for ctxr in ctxr_files:
            name = ctxr.stem.lower()
            if name not in image_hash_by_name:
                continue

            if name in conversion_map:
                continue

            try:
                ctxr.unlink()
                deleted_missing_csv += 1
            except Exception as e:
                log(f"[FAIL MISSING CSV] {ctxr.name} (delete error: {e})")
                delete_failures += 1

        if deleted_missing_csv:
            log(f"[INFO] Deleted {deleted_missing_csv} staged CTXR file(s) that were missing CSV entries")

        if delete_failures:
            return pause_and_exit(1)

        ctxr_files = sorted(
            [p for p in STAGING_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr"],
            key=lambda p: p.name.lower(),
        )

        if not ctxr_files:
            log("[INFO] No .ctxr files found in staging folder.")

            log("\n[PARAM] Starting param export stage\n")
            delete_param_outputs_or_die(PARAM_FOLDER)
            delete_tmp_rgb_outputs_or_die(PARAM_FOLDER / "_tmp_rgb_only")
            run_nvtt_exports_or_die(
                image_files=image_files,
                conversion_map=conversion_map,
                image_hash_by_name=image_hash_by_name,
                image_origin_by_name=image_origin_by_name,
                image_used_nomips_by_name=image_used_nomips_by_name,
                image_opacity_expected_by_name=image_opacity_expected_by_name,
                workers=workers,
                no_mip_regexes=no_mip_regexes,
                manual_ui_textures=manual_ui_textures,
                conversion_csv_path=conversion_csv,
                conversion_rows=conversion_rows,
                conversion_header=conversion_header,
                ctxr3_required_stems=ctxr3_required_stems,
            )

            if not is_upscaled_run:
                conversion_map2, _rows2, _hdr2, _ = load_conversion_csv_unique_or_die(conversion_csv)
                launch_ctxr3_for_pending_or_die(
                    image_files=image_files,
                    ctxr3_required_stems=ctxr3_required_stems,
                    conversion_map=conversion_map2,
                    staging_folder=STAGING_FOLDER,
                )
                refresh_not_yet_converted_after_ctxr3(
                    staging_folder=STAGING_FOLDER,
                    image_files=image_files,
                    ctxr3_required_stems=ctxr3_required_stems,
                )
            return 0

        ctxr_hash_by_path = hash_ctxr_files_with_progress(ctxr_files, workers, "Hash ctxr")

        orphans: list[Path] = []
        mismatches: list[Path] = []
        keeps: list[Path] = []
        mismatched_names: set[str] = set()

        for ctxr in ctxr_files:
            if has_any_uppercase(ctxr.name):
                mismatches.append(ctxr)
                mismatched_names.add(ctxr.stem.lower())
                continue

            name = ctxr.stem.lower()
            ctxr_digest = ctxr_hash_by_path[ctxr].lower()

            img_digest = image_hash_by_name.get(name)
            if img_digest is None:
                orphans.append(ctxr)
                continue

            (
                expected_before,
                expected_ctxr,
                expected_used_nomips,
                expected_origin,
                expected_opacity_stripped,
                expected_upscaled,
                expected_upscaler_version,
                expected_upscaler_type,
                expected_upscaler_meta_present,
                expected_ctxr3_converted,
                expected_filename_has_upper,
            ) = conversion_map[name]

            if expected_filename_has_upper:
                mismatches.append(ctxr)
                mismatched_names.add(name)
                continue

            current_origin = image_origin_by_name.get(name, "")
            current_used_nomips = image_used_nomips_by_name.get(name, False)
            current_opacity_expected = image_opacity_expected_by_name.get(name, False)

            before_ok = (expected_before == (img_digest or "").lower())
            ctxr_ok = (expected_ctxr == (ctxr_digest or "").lower())
            mip_ok = (expected_used_nomips == current_used_nomips)
            origin_ok = (str(expected_origin).strip().lower() == str(current_origin).strip().lower())
            opacity_ok = (expected_opacity_stripped == current_opacity_expected)
            upscaled_ok = (expected_upscaled == upscaled_expected_main)

            if upscaled_expected_main:
                upscaler_ok = bool(
                    expected_upscaler_meta_present
                    and (expected_upscaler_version == current_upscaler_version)
                    and (expected_upscaler_type == current_upscaler_type)
                )
            else:
                uv = (expected_upscaler_version or "").strip() or "0"
                ut = (expected_upscaler_type or "").strip() or "none"
                upscaler_ok = (uv == "0" and ut == "none")

            ctxr3_ok = True
            if (not upscaled_expected_main) and (name in ctxr3_required_stems):
                ctxr3_ok = (expected_ctxr3_converted is True)

            if before_ok and ctxr_ok and mip_ok and origin_ok and opacity_ok and upscaled_ok and upscaler_ok and ctxr3_ok:
                keeps.append(ctxr)
            else:
                mismatches.append(ctxr)
                mismatched_names.add(name)

        deleted_orphans = 0
        deleted_mismatches = 0
        delete_failures = 0

        if keeps:
            for ctxr in keeps:
                log(f"[KEEP] {ctxr_hash_by_path[ctxr]}  {ctxr.name}")

        for ctxr in orphans:
            digest = ctxr_hash_by_path[ctxr]
            try:
                ctxr.unlink()
                log(f"[DEL ORPHAN] {digest}  {ctxr.name}")
                deleted_orphans += 1
            except Exception as e:
                log(f"[FAIL ORPHAN] {digest}  {ctxr.name} (delete error: {e})")
                delete_failures += 1

        for ctxr in mismatches:
            name = ctxr.stem.lower()
            ctxr_digest = (ctxr_hash_by_path.get(ctxr) or "").lower()

            img_digest = (image_hash_by_name.get(name) or "").lower()
            current_origin = image_origin_by_name.get(name, "")
            current_used_nomips = image_used_nomips_by_name.get(name, False)
            current_opacity_expected = image_opacity_expected_by_name.get(name, False)

            expected_before = ""
            expected_ctxr = ""
            expected_used_nomips = False
            expected_origin = ""
            expected_opacity_stripped = False
            expected_upscaled = upscaled_expected_main
            expected_upscaler_version = ""
            expected_upscaler_type = ""
            expected_upscaler_meta_present = False
            expected_ctxr3_converted = False
            expected_filename_has_upper = False

            if name in conversion_map:
                (
                    expected_before,
                    expected_ctxr,
                    expected_used_nomips,
                    expected_origin,
                    expected_opacity_stripped,
                    expected_upscaled,
                    expected_upscaler_version,
                    expected_upscaler_type,
                    expected_upscaler_meta_present,
                    expected_ctxr3_converted,
                    expected_filename_has_upper,
                ) = conversion_map[name]

            try:
                ctxr.unlink()
                log(f"[DEL MISMATCH] {ctxr_digest}  {ctxr.name}")

                if has_any_uppercase(ctxr.name) or expected_filename_has_upper:
                    log("  reason=uppercase filename mismatch (CSV and/or CTXR)")
                else:
                    log(f"  expected_before={expected_before} actual_image={img_digest}")
                    log(f"  expected_ctxr  ={expected_ctxr} actual_ctxr ={ctxr_digest}")
                    log(f"  expected_mipmaps={bool_to_csv(not expected_used_nomips)} actual_mipmaps={bool_to_csv(not current_used_nomips)}")
                    log(f"  expected_origin={expected_origin} actual_origin={current_origin}")
                    log(f"  expected_opacity_stripped={bool_to_csv(expected_opacity_stripped)} actual_opacity_stripped={bool_to_csv(current_opacity_expected)}")
                    log(f"  expected_upscaled={bool_to_csv(expected_upscaled)} actual_upscaled={bool_to_csv(upscaled_expected_main)}")

                    if upscaled_expected_main:
                        log(f"  expected_upscaler_version={(expected_upscaler_version or '').strip() or '<missing>'} actual_upscaler_version={current_upscaler_version}")
                        log(f"  expected_upscaler_type={(expected_upscaler_type or '').strip() or '<missing>'} actual_upscaler_type={current_upscaler_type}")
                        log(f"  expected_upscaler_meta_present={bool_to_csv(expected_upscaler_meta_present)}")

                    if (not upscaled_expected_main) and (name in ctxr3_required_stems):
                        log(f"  expected_ctxr3_converted=true actual_ctxr3_converted={bool_to_csv(expected_ctxr3_converted)}")

                deleted_mismatches += 1
            except Exception as e:
                log(f"[FAIL MISMATCH] {ctxr_digest}  {ctxr.name} (delete error: {e})")
                delete_failures += 1

        if mismatched_names:
            pruned_rows: list[dict[str, str]] = []
            removed = 0

            for row in conversion_rows:
                filename = (row.get("filename") or row.get("Filename") or row.get("FILENAME") or "").strip().lower()
                if filename and filename in mismatched_names:
                    removed += 1
                    continue
                pruned_rows.append(row)

            if removed > 0:
                conversion_rows[:] = pruned_rows

                for k in list(conversion_map.keys()):
                    if k in mismatched_names:
                        del conversion_map[k]

                write_conversion_csv_atomic(conversion_csv, conversion_header, conversion_rows)
                log(f"[CSV] Removed {removed} row(s) from {CONVERSION_CSV} due to mismatches")

        log("")
        log(f"[RESULT] Keep: {len(keeps)}")
        log(f"[RESULT] Deleted orphans: {deleted_orphans} (out of {len(orphans)})")
        log(f"[RESULT] Deleted mismatches: {deleted_mismatches} (out of {len(mismatches)})")
        if delete_failures:
            log(f"[RESULT] Delete failures: {delete_failures}")

        if delete_failures:
            return pause_and_exit(1)

        log("\n[PARAM] Starting param export stage\n")
        delete_param_outputs_or_die(PARAM_FOLDER)
        delete_tmp_rgb_outputs_or_die(PARAM_FOLDER / "_tmp_rgb_only")
        run_nvtt_exports_or_die(
            image_files=image_files,
            conversion_map=conversion_map,
            image_hash_by_name=image_hash_by_name,
            image_origin_by_name=image_origin_by_name,
            image_used_nomips_by_name=image_used_nomips_by_name,
            image_opacity_expected_by_name=image_opacity_expected_by_name,
            workers=workers,
            no_mip_regexes=no_mip_regexes,
            manual_ui_textures=manual_ui_textures,
            conversion_csv_path=conversion_csv,
            conversion_rows=conversion_rows,
            conversion_header=conversion_header,
            ctxr3_required_stems=ctxr3_required_stems,
        )

        if not is_upscaled_run:
            conversion_map2, _rows2, _hdr2, _ = load_conversion_csv_unique_or_die(conversion_csv)
            launch_ctxr3_for_pending_or_die(
                image_files=image_files,
                ctxr3_required_stems=ctxr3_required_stems,
                conversion_map=conversion_map2,
                staging_folder=STAGING_FOLDER,
            )
            refresh_not_yet_converted_after_ctxr3(
                staging_folder=STAGING_FOLDER,
                image_files=image_files,
                ctxr3_required_stems=ctxr3_required_stems,
            )
        return 0

    except Exception as e:
        log(f"[FATAL] {e}")
        return pause_and_exit(1)


if __name__ == "__main__":
    raise SystemExit(main())