from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Set

from PIL import Image


# ==========================================================
# CONFIG
# ==========================================================
ROOT_DIR = Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures")
OUTPUT_LOG = Path(__file__).resolve().with_name("single_color_rgb_stems_report.txt")

SHADOW_MAP_STEMS_PATH = Path(__file__).resolve().with_name("shadow_map_stems.txt")
MANUAL_UI_STEMS_PATH = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\ps2 textures\manual_ui_textures.txt"
)

NEVER_UPSCALE_STEMS_PATH = Path(
    r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Texture Fixes\never_upscale.txt"
)

IGNORE_NEVER_UPSCALE = True


VALID_EXTENSIONS = {".png", ".tga"}
MAX_WORKERS = min(32, max(4, os.cpu_count() or 4))


# ==========================================================
# REGEX SKIP CONFIG
# ==========================================================
# Add regex patterns here to skip stems matching certain patterns.
# These are matched against the file stem only, case-insensitive.
SKIP_STEM_REGEX_PATTERNS = [
     r"sub_alp",
     r"sub_ovl_alp",
     r"alp_ovl_sub",
     r"alp_sub_ovl",
]

SKIP_STEM_REGEX = [re.compile(pattern, re.IGNORECASE) for pattern in SKIP_STEM_REGEX_PATTERNS]


# ==========================================================
# HELPERS
# ==========================================================
def load_stem_list(path: Path, label: str) -> Set[str]:
    if not path.is_file():
        print(f"[!] {label} not found: {path}")
        return set()

    stems: Set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            stems.add(line.lower())

    print(f"[+] Loaded {len(stems)} {label}")
    return stems


def should_skip_stem(
    stem: str,
    shadow_map_stems: Set[str],
    manual_ui_stems: Set[str],
    never_upscale_stems: Set[str],
) -> bool:
    stem_lower = stem.lower()

    if stem_lower in shadow_map_stems:
        return True

    if stem_lower in manual_ui_stems:
        return True

    if IGNORE_NEVER_UPSCALE and stem_lower in never_upscale_stems:
        return True

    for pattern in SKIP_STEM_REGEX:
        if pattern.search(stem_lower):
            return True

    return False


def iter_image_files(
    root: Path,
    shadow_map_stems: Set[str],
    manual_ui_stems: Set[str],
    never_upscale_stems: Set[str],
) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in VALID_EXTENSIONS:
            continue

        if should_skip_stem(
            path.stem,
            shadow_map_stems,
            manual_ui_stems,
            never_upscale_stems,
        ):
            continue

        yield path


def image_has_exactly_one_rgb_color(path: Path) -> bool:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        first_pixel = rgb.getpixel((0, 0))

        for pixel in rgb.getdata():
            if pixel != first_pixel:
                return False

        return True


def process_file(path: Path) -> tuple[Path, bool, str | None]:
    try:
        is_single_color = image_has_exactly_one_rgb_color(path)
        return path, is_single_color, None
    except Exception as exc:
        return path, False, str(exc)


# ==========================================================
# MAIN
# ==========================================================
def main() -> None:
    if not ROOT_DIR.is_dir():
        print(f"[!] Root directory does not exist: {ROOT_DIR}")
        return

    shadow_map_stems = load_stem_list(SHADOW_MAP_STEMS_PATH, "shadow-map stems")
    manual_ui_stems = load_stem_list(MANUAL_UI_STEMS_PATH, "manual-ui stems")

    never_upscale_stems = set()
    if IGNORE_NEVER_UPSCALE:
        never_upscale_stems = load_stem_list(NEVER_UPSCALE_STEMS_PATH, "never-upscale stems")

    image_files = sorted(
        iter_image_files(
            ROOT_DIR,
            shadow_map_stems,
            manual_ui_stems,
            never_upscale_stems,
        )
    )

    if not image_files:
        print("[!] No PNG/TGA files found after filtering.")
        OUTPUT_LOG.write_text("", encoding="utf-8")
        return

    print(f"[+] Found {len(image_files)} image files (after filtering)")
    print(f"[+] Scanning with {MAX_WORKERS} workers...")

    matching_stems: list[str] = []
    errors: list[tuple[Path, str]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_file, path) for path in image_files]

        completed = 0
        total = len(futures)

        for future in as_completed(futures):
            path, is_single_color, error = future.result()
            completed += 1

            if error is not None:
                errors.append((path, error))
            elif is_single_color:
                matching_stems.append(path.stem)

            if completed % 100 == 0 or completed == total:
                print(f"[+] Processed {completed}/{total}")

    matching_stems.sort()

    OUTPUT_LOG.write_text(
        "\n".join(matching_stems) + ("\n" if matching_stems else ""),
        encoding="utf-8",
    )

    print(f"[+] Found {len(matching_stems)} single-color RGB images")
    print(f"[+] Wrote log: {OUTPUT_LOG}")

    if errors:
        error_log = OUTPUT_LOG.with_name("single_color_rgb_errors.txt")
        error_lines = [f"{path}: {message}" for path, message in sorted(errors)]
        error_log.write_text("\n".join(error_lines) + "\n", encoding="utf-8")
        print(f"[!] {len(errors)} files failed to process")
        print(f"[!] Wrote error log: {error_log}")


if __name__ == "__main__":
    main()