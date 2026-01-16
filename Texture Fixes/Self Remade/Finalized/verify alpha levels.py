
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Set, Tuple

from PIL import Image

VERIFY_ALPHA_SCRIPT = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\Self Remade\Finalized\verify alpha levels.py")


# ==========================================================
# PATH FILTERS
# ==========================================================
def is_under_source_files(path: Path) -> bool:
    return "source files" in (p.lower() for p in path.parts)


def collect_images(root: Path) -> List[Path]:
    exts = {".png", ".tga"}
    out: List[Path] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if is_under_source_files(p.parent):
            continue
        out.append(p)

    return out


# ==========================================================
# ALPHA SCAN
# ==========================================================
def analyze_alpha(img: Image.Image) -> Tuple[Set[int], Set[int]]:
    # Returns:
    # (hit_levels, all_levels)
    #
    # hit_levels = alpha values >=129 that triggered hit condition
    # all_levels = all alpha values present in the image
    #
    # Empty sets mean no usable alpha or no hits.

    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")

    elif img.mode == "P":
        if "transparency" not in img.info:
            return set(), set()
        alpha = img.convert("RGBA").getchannel("A")

    else:
        return set(), set()

    # Quick reject: fully opaque alpha everywhere
    lo, hi = alpha.getextrema()
    if lo == 255 and hi == 255:
        return set(), {255}

    hit_levels: Set[int] = set()
    all_levels: Set[int] = set()

    for a in alpha.getdata():
        av = int(a)
        all_levels.add(av)
        if av >= 129:
            hit_levels.add(av)

    return hit_levels, all_levels


def scan_file(path: Path) -> Tuple[Path, Set[int], Set[int], Optional[str]]:
    try:
        with Image.open(path) as im:
            im.load()
            hit_levels, all_levels = analyze_alpha(im)
            return path, hit_levels, all_levels, None
    except Exception as exc:
        return path, set(), set(), f"{type(exc).__name__}: {exc}"


# ==========================================================
# LOG HELPERS
# ==========================================================
def safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except Exception as exc:
        print(f"[WARN] Failed deleting old log {path}: {exc}")


# ==========================================================
# MAIN
# ==========================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root folder to scan (default: script folder).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(2, (os.cpu_count() or 8)),
        help="Worker thread count.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Hit log path (default: alpha_129_255_log.txt in root).",
    )
    parser.add_argument(
        "--error-log",
        type=Path,
        default=None,
        help="Error log path (default: alpha_129_255_errors.txt in root).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Progress print interval.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"[ERROR] Invalid root folder: {root}")
        return 1

    log_path = args.log.resolve() if args.log else (root / "alpha_129_255_log.txt")
    err_path = args.error_log.resolve() if args.error_log else (root / "alpha_129_255_errors.txt")

    files = collect_images(root)
    total = len(files)

    if total == 0:
        print("[DONE] No images found.")
        safe_unlink(log_path)
        safe_unlink(err_path)
        return 0

    print(f"[INFO] Root: {root}")
    print(f"[INFO] Files to scan: {total}")
    print(f"[INFO] Threads: {args.threads}")

    hits: List[Tuple[Path, Set[int], Set[int]]] = []
    errs: List[Tuple[Path, str]] = []

    completed = 0

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futures = [ex.submit(scan_file, p) for p in files]

        for fut in as_completed(futures):
            path, hit_levels, all_levels, err = fut.result()
            completed += 1

            if err:
                errs.append((path, err))
            elif hit_levels:
                hits.append((path, hit_levels, all_levels))

            if args.progress_every and completed % args.progress_every == 0:
                print(f"[...] {completed}/{total} done | Hits {len(hits)} | Errors {len(errs)}")

    hits.sort(key=lambda t: str(t[0]).lower())
    errs.sort(key=lambda t: str(t[0]).lower())

    # Always clean old logs first
    safe_unlink(log_path)
    safe_unlink(err_path)

    if hits:
        with log_path.open("w", encoding="utf-8", newline="\n") as log_f:
            log_f.write("# Files with alpha >=129 detected\n")
            log_f.write(f"# Root: {root}\n")
            log_f.write(f"# Total scanned: {total}\n")
            log_f.write(f"# Hits: {len(hits)}\n\n")

            for p, hit_levels, all_levels in hits:
                hit_str = ", ".join(str(v) for v in sorted(hit_levels))
                all_str = ", ".join(str(v) for v in sorted(all_levels))
                log_f.write(f"{p}\n")
                log_f.write(f"  hit_levels: {hit_str}\n")
                log_f.write(f"  all_levels: {all_str}\n\n")

    if errs:
        with err_path.open("w", encoding="utf-8", newline="\n") as err_f:
            err_f.write("# Files that failed to read/scan\n")
            err_f.write(f"# Root: {root}\n")
            err_f.write(f"# Total scanned: {total}\n")
            err_f.write(f"# Errors: {len(errs)}\n\n")
            for p, e in errs:
                err_f.write(f"{p}\n  {e}\n\n")

    print(f"[DONE] Scanned: {total}")

    if hits:
        print(f"[DONE] Hits: {len(hits)} -> {log_path}")
    else:
        print("[DONE] Hits: 0 (no hit log written)")

    if errs:
        print(f"[DONE] Errors: {len(errs)} -> {err_path}")
    else:
        print("[DONE] Errors: 0 (no error log written)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
