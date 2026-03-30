from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from threading import Lock

from PIL import Image


# ==========================================================
# CONFIG
# ==========================================================
CTXR3_EXE = Path(r"J:\Mega\Games\MG Master Collection\Self made mods\Tooling\CTXR3\CTXR-Converter 1.6\ctxr3.exe")

# Kept for compatibility, but ctxr_list.txt now lists source image filenames only (png/tga), one per line.
PREFIX = "mgs2/textures/flatlist/_win"

NON_UPSCALED_PROCESS_VERSION = "1"


OUT_CTXR_LIST_TXT = "ctxr_list.txt"
DEPLOY_DIRS_TXT = "deploy_directories.txt"
CONVERSION_CSV = "conversion_hashes.csv"

TEXTURE_FIXES_ROOT = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes")

# This script will ONLY process images (PNG or TGA) whose stem matches NO-MIP rules (DPF_NOMIPS equivalent)
NO_MIP_REGEX_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\no_mip_regex.txt")
MANUAL_UI_TEXTURES_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_ui_textures.txt")
MANUAL_OPAQUE_TEXTURES_PATH = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_opaque_textures.txt")

TMP_DIR_NAME = "_tmp"

PRINT_LOCK = Lock()


def log(msg: str) -> None:
    with PRINT_LOCK:
        print(msg)


def pause_and_exit(code: int = 1) -> int:
    try:
        input("\nPress ENTER to exit...")
    except KeyboardInterrupt:
        pass
    return code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch CTXR3 conversion for NO-MIPS textures and deploy results."
    )
    parser.add_argument(
        "-targetdir",
        dest="targetdir",
        type=str,
        required=False,
        help="Single deploy directory (overrides deploy_directories.txt).",
    )
    parser.add_argument(
        "-originfolder",
        dest="originfolder",
        type=str,
        required=False,
        help="Override origin_folder written to conversion_hashes.csv (relative to Texture Fixes root).",
    )
    return parser.parse_args()


def sha1_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _lower_key(s: str) -> str:
    return (s or "").strip().lower()


def safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        try:
            path.unlink()
        except Exception:
            pass
        return
    shutil.rmtree(path, ignore_errors=False)


def cleanup_tmp_dir(cwd: Path) -> None:
    tmp_dir = cwd / TMP_DIR_NAME
    if not tmp_dir.exists():
        return

    log(f"[TMP] Removing existing tmp directory: {tmp_dir}")
    safe_rmtree(tmp_dir)


def image_has_any_transparency(path: Path) -> bool:
    """
    True if image contains any alpha < 255 anywhere (any transparency).
    Supports PNG, TGA, and other formats PIL can open.
    """
    with Image.open(path) as im:
        if im.mode == "P":
            if "transparency" in im.info:
                im = im.convert("RGBA")
            else:
                return False

        if im.mode in ("RGBA", "LA"):
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            alpha = im.getchannel("A")
            lo, _hi = alpha.getextrema()
            return lo < 255

        return False


def image_alpha_extrema(path: Path) -> tuple[bool, int, int]:
    """
    Returns:
      (has_alpha, lo, hi)
    If there is no alpha channel, has_alpha is False and lo/hi are 255/255.
    """
    with Image.open(path) as im:
        if im.mode == "P":
            if "transparency" in im.info:
                im = im.convert("RGBA")
            else:
                return False, 255, 255

        if im.mode in ("RGBA", "LA"):
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            alpha = im.getchannel("A")
            lo, hi = alpha.getextrema()
            return True, int(lo), int(hi)

        return False, 255, 255


def should_strip_opacity_and_use_rgb_only(src_path: Path, manual_opaque: set[str]) -> bool:
    """
    True if we should create an RGB-only temp image to avoid alpha affecting colors:
      - stem is listed in manual_opaque_textures.txt, OR
      - path contains 'opaque' (case-insensitive), OR
      - no alpha channel, OR
      - all alpha is 128, OR
      - all alpha is 255
    """
    stem_lower = src_path.stem.lower()

    if stem_lower in manual_opaque:
        return True

    if "opaque" in str(src_path).lower():
        return True

    has_alpha, lo, hi = image_alpha_extrema(src_path)
    if not has_alpha:
        return True

    if lo == hi == 128:
        return True

    if lo == hi == 255:
        return True

    return False


def write_rgb_only_temp(src_path: Path, tmp_dir: Path) -> Path:
    """
    Split RGB and alpha, and save RGB only (no alpha) to tmp_dir with same filename (lowercased).
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)

    out_name = src_path.name.lower()
    out_path = tmp_dir / out_name

    with Image.open(src_path) as im:
        if im.mode == "P":
            if "transparency" in im.info:
                im = im.convert("RGBA")
            else:
                im = im.convert("RGB")
        elif im.mode in ("RGBA", "LA"):
            if im.mode != "RGBA":
                im = im.convert("RGBA")
        else:
            im = im.convert("RGB")

        if im.mode == "RGBA":
            r, g, b, _a = im.split()
            rgb = Image.merge("RGB", (r, g, b))
        else:
            rgb = im.convert("RGB")

        ext = src_path.suffix.lower()
        if ext == ".png":
            rgb.save(out_path, format="PNG")
        elif ext == ".tga":
            rgb.save(out_path, format="TGA")
        else:
            rgb.save(out_path)

    return out_path


def read_deploy_directories(txt_path: Path, base_dir: Path) -> list[Path]:
    if not txt_path.is_file():
        raise FileNotFoundError(f"Missing {DEPLOY_DIRS_TXT} in CWD: {txt_path}")

    out: list[Path] = []
    for raw in txt_path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith(";"):
            continue

        p = Path(s)
        if not p.is_absolute():
            p = (base_dir / p).resolve()

        out.append(p)

    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        k = str(p).lower()
        if k in seen:
            continue
        seen.add(k)
        unique.append(p)

    return unique


def ensure_under_texture_fixes_root(cwd: Path) -> Path:
    try:
        rel = cwd.resolve().relative_to(TEXTURE_FIXES_ROOT.resolve())
    except Exception:
        raise RuntimeError(
            "Current working directory is not under Texture Fixes root.\n"
            f"Texture Fixes root:\n  {TEXTURE_FIXES_ROOT}\n"
            f"Current working directory:\n  {cwd}\n"
        )
    return rel


def load_existing_csv(csv_path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    if not csv_path.is_file():
        return {}, []

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {}, []

        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            fn_raw = row.get("filename") or ""
            fn = _lower_key(fn_raw)
            if not fn:
                continue

            normalized_row: dict[str, str] = {}
            for k, v in row.items():
                kk = (k or "").strip()
                vv = v if v is not None else ""
                if kk == "filename":
                    vv = _lower_key(vv)
                else:
                    vv = (vv or "").strip()
                normalized_row[kk] = vv

            rows[fn] = normalized_row

        return rows, list(reader.fieldnames)


def write_conversion_csv(csv_path: Path, rows_by_filename: dict[str, dict[str, str]]) -> None:
    header = [
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
        "non_upscaled_version",
    ]

    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")

    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()

        for filename in sorted(rows_by_filename.keys(), key=lambda s: s.lower()):
            row = rows_by_filename[filename]
            out = {h: (row.get(h, "") or "") for h in header}
            out["filename"] = _lower_key(out.get("filename", filename))
            writer.writerow(out)

    tmp_path.replace(csv_path)


def cleanup_existing_ctxrs(cwd: Path) -> None:
    ctxrs = sorted(p for p in cwd.iterdir() if p.is_file() and p.suffix.lower() == ".ctxr")
    if not ctxrs:
        return

    log(f"Startup cleanup: removing {len(ctxrs)} existing .ctxr files from CWD...")
    failures: list[tuple[Path, str]] = []

    for p in ctxrs:
        try:
            p.unlink()
            log(f"  deleted {p.name}")
        except Exception as e:
            failures.append((p, str(e)))

    if failures:
        log("ERROR: Failed to delete some existing .ctxr files:")
        for p, err in failures:
            log(f"  {p.name}: {err}")
        raise RuntimeError("Startup cleanup failed due to locked or undeletable .ctxr files")


def delete_ctxrs(paths: list[Path]) -> None:
    deleted = 0
    failed: list[tuple[Path, str]] = []

    for p in paths:
        try:
            if p.is_file():
                p.unlink()
                deleted += 1
        except Exception as e:
            failed.append((p, str(e)))

    log(f"\nCleanup: deleted {deleted} .ctxr file(s).")
    if failed:
        log("Cleanup: some deletions failed:")
        for p, err in failed[:50]:
            log(f"  {p}: {err}")
        if len(failed) > 50:
            log(f"  ...and {len(failed) - 50} more")


# ==========================================================
# NO-MIP FILTER
# ==========================================================
def load_no_mip_regexes_or_die(path: Path) -> list[re.Pattern]:
    if not path.is_file():
        raise RuntimeError(f"no_mip_regex.txt not found: {path}")

    patterns: list[re.Pattern] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
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
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line.lower())

    return out


def load_manual_opaque_textures_or_die(path: Path) -> set[str]:
    if not path.is_file():
        raise RuntimeError(f"manual_opaque_textures.txt not found: {path}")

    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
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


def is_truthy(s: str) -> bool:
    return (s or "").strip().lower() == "true"


# tex_meta maps stem_lower ->
#   (before_hash, opacity_stripped, original_source_path, source_path_for_conversion)
TexMeta = dict[str, tuple[str, str, Path, Path]]


def purge_stale_deploy_entries_and_decide_needed(
    deploy_dirs: list[Path],
    tex_meta: TexMeta,
) -> set[str]:
    needs_convert: set[str] = set()

    for d in deploy_dirs:
        csv_path = d / CONVERSION_CSV
        rows, _hdr = load_existing_csv(csv_path)

        changed = False

        for stem_lower, (before_hash, _opacity_stripped, _orig_path, _conv_path) in tex_meta.items():
            row = rows.get(stem_lower)
            if row is None:
                needs_convert.add(stem_lower)
                continue

            row_ctxr3 = is_truthy(row.get("ctxr3_converted", "false"))
            row_before = _lower_key(row.get("before_hash", ""))
            before_match = (row_before == before_hash.lower())

            if (not row_ctxr3) or (not before_match):
                deployed_ctxr = d / f"{stem_lower}.ctxr"
                try:
                    if deployed_ctxr.is_file():
                        deployed_ctxr.unlink()
                        log(f"[PURGE] Deleted stale ctxr: {deployed_ctxr}")
                except Exception as e:
                    log(f"ERROR: Failed deleting stale ctxr:\n  {deployed_ctxr}\n  {e}")

                try:
                    del rows[stem_lower]
                    changed = True
                except KeyError:
                    pass

                needs_convert.add(stem_lower)

        if changed:
            write_conversion_csv(csv_path, rows)
            log(f"[PURGE] Updated -> {csv_path}")

    return needs_convert


def expected_ctxr_path_for_source(src_for_conv: Path) -> Path:
    return src_for_conv.parent / (src_for_conv.stem + ".ctxr")


def write_ctxr_list_fullpaths(cwd: Path, stems: list[str], tex_meta: TexMeta) -> Path:
    ctxr_list_path = cwd / OUT_CTXR_LIST_TXT
    lines: list[str] = []
    for stem_lower in stems:
        _before_hash, _opacity_stripped, _orig_path, conv_path = tex_meta[stem_lower]
        lines.append(str(conv_path.resolve()))
    ctxr_list_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return ctxr_list_path


def write_ctxr_list_original_names(cwd: Path, stems: list[str], tex_meta: TexMeta) -> Path:
    """
    When finishing/closing with remaining work, write ONLY original filenames (with extension),
    one per line, lowercased. No paths, no _tmp references.
    """
    ctxr_list_path = cwd / OUT_CTXR_LIST_TXT
    lines: list[str] = []
    for stem_lower in stems:
        _before_hash, _opacity_stripped, orig_path, _conv_path = tex_meta[stem_lower]
        lines.append(orig_path.name.lower())
    ctxr_list_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return ctxr_list_path


def main() -> int:
    args = parse_args()
    cwd = Path.cwd()
    tmp_dir = cwd / TMP_DIR_NAME

    try:
        cleanup_existing_ctxrs(cwd)
    except Exception as e:
        log(str(e))
        return pause_and_exit(1)

    # Always hard-delete tmp at start
    try:
        cleanup_tmp_dir(cwd)
    except Exception as e:
        log(f"ERROR: Failed deleting {TMP_DIR_NAME} at start:\n  {e}")
        return pause_and_exit(1)

    if not CTXR3_EXE.is_file():
        log(f"ERROR: ctxr3.exe not found:\n{CTXR3_EXE}")
        return pause_and_exit(1)

    if args.originfolder:
        origin_folder = str(args.originfolder).replace("/", "\\").strip("\\")
    else:
        try:
            origin_rel = ensure_under_texture_fixes_root(cwd)
        except Exception as e:
            log(f"ERROR: {e}")
            return pause_and_exit(1)

        origin_folder = str(origin_rel).replace("/", "\\").strip("\\")

    try:
        no_mip_regexes = load_no_mip_regexes_or_die(NO_MIP_REGEX_PATH)
        manual_ui_textures = load_manual_ui_textures_or_die(MANUAL_UI_TEXTURES_PATH)
        manual_opaque_textures = load_manual_opaque_textures_or_die(MANUAL_OPAQUE_TEXTURES_PATH)
    except Exception as e:
        log(f"ERROR: {e}")
        return pause_and_exit(1)

    if args.targetdir:
        deploy_dirs = [Path(args.targetdir).resolve()]
        log("[MODE] Using -targetdir override:")
        log(f"  {deploy_dirs[0]}")
    else:
        deploy_txt = cwd / DEPLOY_DIRS_TXT
        try:
            deploy_dirs = read_deploy_directories(deploy_txt, cwd)
        except Exception as e:
            log(f"ERROR: {e}")
            return pause_and_exit(1)

        if not deploy_dirs:
            log(f"ERROR: {DEPLOY_DIRS_TXT} has no valid directories.")
            return pause_and_exit(1)

    for d in deploy_dirs:
        if not d.is_dir():
            log(f"ERROR: Deploy directory does not exist or is not a folder:\n  {d}")
            return pause_and_exit(1)

    all_images = sorted(
        p for p in cwd.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".tga"}
    )
    if not all_images:
        log(f"ERROR: No PNG or TGA files found in CWD:\n{cwd}")
        return pause_and_exit(1)

    tex_paths: list[Path] = []
    skipped: list[Path] = []
    for p in all_images:
        stem_lower = p.stem.lower()
        if should_use_nomips(stem_lower, no_mip_regexes, manual_ui_textures):
            tex_paths.append(p)
        else:
            skipped.append(p)

    if skipped:
        log(f"[INFO] Skipping {len(skipped)} image(s) that are NOT NO-MIPS (manual handling expected for these).")
        for p in skipped[:50]:
            log(f"  [SKIP NOT NOMIPS] {p.name}")
        if len(skipped) > 50:
            log(f"  ...and {len(skipped) - 50} more")
        log("")

    if not tex_paths:
        log("ERROR: After NO-MIPS filtering, there are 0 images to process in CWD.")
        log("This script now only processes textures that would use DPF_NOMIPS.")
        return pause_and_exit(1)

    log("\nHashing source images + deciding rgb-only temp usage...")

    tex_meta: TexMeta = {}
    stems_need_tmp: set[str] = set()

    for p in tex_paths:
        stem_lower = p.stem.lower()
        before_hash = sha1_file(p)

        try:
            strip = should_strip_opacity_and_use_rgb_only(p, manual_opaque_textures)
        except Exception as e:
            log(f"ERROR: Failed analyzing alpha for {p.name}:\n  {e}")
            return pause_and_exit(1)

        if strip:
            stems_need_tmp.add(stem_lower)
            opacity_stripped = "true"
        else:
            opacity_stripped = "true" if not image_has_any_transparency(p) else "false"

        # conv_path starts as original; may become _tmp path for this run
        tex_meta[stem_lower] = (before_hash, opacity_stripped, p, p)

    log("\nChecking deploy directories for stale or missing ctxr3 conversions...")
    needs_convert = purge_stale_deploy_entries_and_decide_needed(deploy_dirs, tex_meta)

    stems_to_convert = sorted({p.stem.lower() for p in tex_paths if p.stem.lower() in needs_convert})
    if not stems_to_convert:
        log("\nNothing to convert. All NO-MIPS textures are already ctxr3_converted=true with matching before_hash.")
        log("Done.")
        return 0

    # Create tmp RGB-only sources only for ones we're converting this run
    created_tmp_files: list[Path] = []
    if any(s in stems_need_tmp for s in stems_to_convert):
        log("\n[TMP] Creating rgb-only temp sources for conversion...")
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log(f"ERROR: Failed to create tmp directory:\n  {tmp_dir}\n  {e}")
            return pause_and_exit(1)

        # Generate tmp for only stems_to_convert that need it
        stems_to_convert_set = set(stems_to_convert)
        for stem_lower, (before_hash, opacity_stripped, orig_path, conv_path) in list(tex_meta.items()):
            if stem_lower not in stems_to_convert_set:
                continue
            if stem_lower not in stems_need_tmp:
                continue

            try:
                out_path = write_rgb_only_temp(orig_path, tmp_dir)
                created_tmp_files.append(out_path)
                tex_meta[stem_lower] = (before_hash, opacity_stripped, orig_path, out_path)
                log(f"  [TMP] {orig_path.name} -> {out_path}")
            except Exception as e:
                log(f"ERROR: Failed creating rgb-only temp for:\n  {orig_path}\n  {e}")
                return pause_and_exit(1)

    # Write ctxr_list.txt with FULL paths for conversion (tmp path if used)
    ctxr_list_path = write_ctxr_list_fullpaths(cwd, stems_to_convert, tex_meta)
    log(f"\nWrote {len(stems_to_convert)} full path(s) to: {ctxr_list_path}")

    os.startfile(ctxr_list_path)

    log(f"\nLaunching CTXR3 and waiting for it to close:\n{CTXR3_EXE}")
    proc = subprocess.Popen([str(CTXR3_EXE)], cwd=CTXR3_EXE.parent, shell=False)
    exit_code = proc.wait()
    log(f"CTXR3 exited with code: {exit_code}")

    # Partial-job support: deploy whatever exists
    processed_ctxr_files: list[Path] = []
    processed_stems: set[str] = set()
    missing_ctxrs: list[tuple[str, Path, Path]] = []

    for stem_lower in stems_to_convert:
        _before_hash, _opacity_stripped, _orig_path, conv_path = tex_meta[stem_lower]
        expected = expected_ctxr_path_for_source(conv_path)
        if expected.is_file():
            processed_ctxr_files.append(expected)
            processed_stems.add(stem_lower)
        else:
            missing_ctxrs.append((stem_lower, conv_path, expected))

    if not processed_ctxr_files:
        log("ERROR: No expected .ctxr outputs were found after CTXR3 run. Nothing to deploy.")
        if missing_ctxrs:
            for stem_lower, conv_path, expected in missing_ctxrs[:50]:
                log(f"  stem={stem_lower} input={conv_path} expected_out={expected}")
            if len(missing_ctxrs) > 50:
                log(f"  ...and {len(missing_ctxrs) - 50} more")

        # tmp ALWAYS gets deleted on close
        try:
            cleanup_tmp_dir(cwd)
        except Exception as e:
            log(f"WARNING: Failed deleting {TMP_DIR_NAME}:\n  {e}")

        return pause_and_exit(1)

    if missing_ctxrs:
        log(f"[WARN] Only {len(processed_ctxr_files)}/{len(stems_to_convert)} ctxr(s) were produced. Continuing with partial deploy.")
        for stem_lower, conv_path, expected in missing_ctxrs[:50]:
            log(f"  [MISSING] stem={stem_lower} input={conv_path} expected_out={expected}")
        if len(missing_ctxrs) > 50:
            log(f"  ...and {len(missing_ctxrs) - 50} more")

    log(f"\nFound {len(processed_ctxr_files)} .ctxr file(s) to deploy (located next to their inputs).")

    # Hash ctxrs
    log("\nHashing CTXRs...")
    ctxr_hashes: dict[str, str] = {}
    for p in processed_ctxr_files:
        ctxr_hashes[p.stem.lower()] = sha1_file(p)

    # Deploy and update CSVs ONLY for processed stems
    log("\nDeploying...")
    for d in deploy_dirs:
        copied = 0
        csv_path = d / CONVERSION_CSV
        rows, _hdr = load_existing_csv(csv_path)

        for ctxr_file in processed_ctxr_files:
            stem_lower = ctxr_file.stem.lower()

            lower_name = (ctxr_file.stem.lower() + ".ctxr")
            dst_ctxr = d / lower_name

            shutil.copy2(ctxr_file, dst_ctxr)
            copied += 1

            before_hash, opacity_stripped, _orig_path, _conv_path = tex_meta[stem_lower]
            row = rows.get(stem_lower, {})

            row["filename"] = stem_lower
            row["before_hash"] = before_hash.lower()
            row["ctxr_hash"] = ctxr_hashes[stem_lower].lower()
            row["mipmaps"] = "false"
            row["origin_folder"] = origin_folder
            row["opacity_stripped"] = opacity_stripped

            row["upscaled"] = "false"
            row["upscaler_version"] = "0"
            row["upscaler_type"] = "none"
            row["ctxr3_converted"] = "true"
            row["non_upscaled_version"] = NON_UPSCALED_PROCESS_VERSION

            rows[stem_lower] = row

        write_conversion_csv(csv_path, rows)
        log(f"  Deployed {copied} ctxr file(s) -> {d}")
        log(f"  Updated -> {csv_path}")

    # Delete produced ctxrs from wherever they were generated (tmp or original dirs)
    delete_ctxrs(processed_ctxr_files)

    # tmp ALWAYS gets deleted on close
    try:
        cleanup_tmp_dir(cwd)
        if created_tmp_files:
            log(f"\n[TMP] Deleted {TMP_DIR_NAME}.")
    except Exception as e:
        log(f"\nWARNING: Failed deleting {TMP_DIR_NAME}:\n  {e}")

    # Rewrite ctxr_list.txt for remaining work:
    # - If none remaining: delete ctxr_list.txt
    # - If remaining: write original filenames only (no paths, no _tmp)
    remaining_stems = [s for s in stems_to_convert if s not in processed_stems]

    if not remaining_stems:
        try:
            (cwd / OUT_CTXR_LIST_TXT).unlink()
            log(f"\nAll done. Deleted {OUT_CTXR_LIST_TXT}.")
        except Exception:
            pass

        log("\nDone.")
        return 0

    write_ctxr_list_original_names(cwd, remaining_stems, tex_meta)
    log(f"\nUpdated {OUT_CTXR_LIST_TXT} with {len(remaining_stems)} remaining file(s) (original filenames only).")
    log("\nDone (partial).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())