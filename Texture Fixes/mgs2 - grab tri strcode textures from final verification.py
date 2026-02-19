# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from PIL import Image
except Exception:
    Image = None 


# -----------------------------
# Config defaults
# -----------------------------
DEFAULT_CSV = r"C:\Development\Git\MGS-Tri-Dumper\mgs2_texture_map.csv"
DEFAULT_PS2_DIR = r"C:\Development\Git\MGS2-PS2-Textures\final_verification_nov22_2025"
DEFAULT_MC_ROOT = r"D:\MG Textures\MGS2\Base Textures\Textures by Location"

DEFAULT_PS2_AS_MC_LIST = r"C:\Development\Git\MGS2-PS2-Textures\u - dumped from substance\mgs2_mc_remastered_textures.txt"

CONVERT_TO_PC_COLORSPACE = True


@dataclass(frozen=True)
class MapRow:
    texture_filename: str
    stage: str
    tri_strcode: str
    texture_strcode: str


@dataclass(frozen=True)
class WorkItem:
    texture_strcode: str
    texture_filename: str
    stage: str
    tri_strcode: str
    ps2_src: Path
    mc_src: Optional[Path]
    out_ps2: Path
    out_mc: Path
    strip_alpha: bool
    do_convert: bool
    overwrite: bool


# -----------------------------
# CSV + discovery
# -----------------------------
def _is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith(";")


def load_texture_map(csv_path: Path) -> Dict[str, List[MapRow]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    mapping: Dict[str, List[MapRow]] = {}
    with csv_path.open("r", encoding="utf-8", errors="strict") as f:
        for lineno, raw in enumerate(f, start=1):
            if _is_comment_or_blank(raw):
                continue

            parts = [p.strip() for p in raw.strip().split(",")]
            if len(parts) != 4:
                raise ValueError(f"Invalid CSV row at line {lineno}: expected 4 fields, got {len(parts)}")

            row = MapRow(*parts)
            mapping.setdefault(row.texture_strcode, []).append(row)

    return mapping


def discover_local_strcodes(script_dir: Path) -> List[str]:
    return sorted(p.stem for p in script_dir.iterdir() if p.is_file() and p.suffix.lower() == ".png")


# -----------------------------
# PS2 helpers
# -----------------------------
def find_ps2_png(ps2_dir: Path, texture_filename: str) -> Path | None:
    exact = ps2_dir / f"{texture_filename}.png"
    if exact.is_file():
        return exact

    target = exact.name.lower()
    for p in ps2_dir.glob("*.png"):
        if p.name.lower() == target:
            return p

    return None


def get_png_resolution(p: Path) -> Optional[Tuple[int, int]]:
    try:
        with Image.open(p) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return None


def format_resolution(res: Optional[Tuple[int, int]]) -> str:
    return "unknown" if res is None else f"{res[0]}x{res[1]}"


def ps2_has_uniform_128_alpha(ps2_png: Path) -> bool:
    try:
        with Image.open(ps2_png) as im:
            a = im.convert("RGBA").split()[3]
            lo, hi = a.getextrema()
            return lo == 128 and hi == 128
    except Exception:
        return False


# -----------------------------
# MC indexing
# -----------------------------
def build_mc_index_by_stem(mc_root: Path) -> Dict[str, List[Path]]:
    if not mc_root.is_dir():
        raise FileNotFoundError(f"MC root not found or not a directory: {mc_root}")

    index: Dict[str, List[Path]] = {}
    for p in mc_root.rglob("*.png"):
        if not p.is_file():
            continue
        index.setdefault(p.stem, []).append(p)

    for k in index:
        index[k].sort(key=lambda x: str(x).lower())

    return index


# -----------------------------
# Override list
# -----------------------------
def load_stem_list(txt_path: Path) -> Set[str]:
    """
    Reads a text file containing stems, one per line.
    Ignores blank lines and lines starting with ';' or '#'.
    Returns a set of stems (no extension).
    """
    stems: Set[str] = set()
    if not txt_path.is_file():
        return stems

    with txt_path.open("r", encoding="utf-8", errors="strict") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            if s.startswith(";") or s.startswith("#"):
                continue
            stems.add(s)
    return stems



def prompt_choice(
    texture_strcode: str,
    rows: List[MapRow],
    ps2_dir: Path,
    local_png: Path,
    ps2_res_cache: Dict[str, str],
) -> MapRow | None:
    # De-dup by (texture_filename, stage, tri_strcode)
    tmp: Dict[Tuple[str, str, str], MapRow] = {}
    for r in rows:
        tmp[(r.texture_filename, r.stage, r.tri_strcode)] = r
    unique = list(tmp.values())

    filenames = {r.texture_filename for r in unique}
    if len(filenames) == 1:
        only_name = next(iter(filenames))
        print("")
        print(f"Multiple stage/tri contexts for texture_strcode = {texture_strcode} (same texture_filename = {only_name})")
        for r in unique:
            print(f"  - stage={r.stage}  tri_strcode={r.tri_strcode}")
        return unique[0]

    local_res = "missing"
    if local_png.is_file():
        local_res = format_resolution(get_png_resolution(local_png))

    grouped: Dict[str, List[MapRow]] = {}
    for r in unique:
        grouped.setdefault(r.texture_filename, []).append(r)

    filename_choices = sorted(grouped.keys())

    def ps2_res_for_filename(fname: str) -> str:
        if fname in ps2_res_cache:
            return ps2_res_cache[fname]

        ps2 = find_ps2_png(ps2_dir, fname)
        if ps2 is None:
            ps2_res_cache[fname] = "missing"
            return ps2_res_cache[fname]

        ps2_res_cache[fname] = format_resolution(get_png_resolution(ps2))
        return ps2_res_cache[fname]

    print("")
    print(f"Multiple matches for texture_strcode = {texture_strcode} (local: {local_res})")
    for i, fname in enumerate(filename_choices, 1):
        res = ps2_res_for_filename(fname)
        contexts = grouped[fname]
        preview = [f"{c.stage}/{c.tri_strcode}" for c in contexts]
        if len(preview) > 4:
            preview = preview[:4] + [f"+{len(contexts) - 4} more"]
        print(f"  {i}) {fname}  [{res}]  contexts: {', '.join(preview)}")

    print("  s) skip")
    while True:
        choice = input("Select option: ").strip().lower()
        if choice == "s":
            return None
        if not choice.isdigit():
            print("Invalid input. Enter a number or 's'.")
            continue

        n = int(choice)
        if n < 1 or n > len(filename_choices):
            print(f"Out of range. Enter 1..{len(filename_choices)} or 's'.")
            continue

        selected = filename_choices[n - 1]
        return grouped[selected][0]


# -----------------------------
def convert_and_save(src: Path, dst: Path, strip_alpha: bool) -> None:
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        r, g, b, a = rgba.split()

        dst.parent.mkdir(parents=True, exist_ok=True)

        if strip_alpha:
            Image.merge("RGB", (r, g, b)).save(dst, format="PNG", optimize=False)
            return

        a2 = a.point(lambda v: 255 if v >= 128 else v * 2)
        Image.merge("RGBA", (r, g, b, a2)).save(dst, format="PNG", optimize=False)


def process_item(item: WorkItem) -> Tuple[str, bool, bool]:
    wrote_ps2 = False
    wrote_mc = False

    if item.overwrite or not item.out_ps2.exists():
        if item.do_convert:
            convert_and_save(item.ps2_src, item.out_ps2, item.strip_alpha)
        else:
            item.out_ps2.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.ps2_src, item.out_ps2)
        wrote_ps2 = True

    if item.mc_src is not None:
        if item.overwrite or not item.out_mc.exists():
            if item.do_convert:
                convert_and_save(item.mc_src, item.out_mc, item.strip_alpha)
            else:
                item.out_mc.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.mc_src, item.out_mc)
            wrote_mc = True

    return item.texture_strcode, wrote_ps2, wrote_mc


# -----------------------------
# Main
# -----------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--ps2-dir", default=DEFAULT_PS2_DIR)
    parser.add_argument("--mc-root", default=DEFAULT_MC_ROOT)
    parser.add_argument("--ps2-as-mc-list", default=DEFAULT_PS2_AS_MC_LIST)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--convert-to-pc-colorspace", action="store_true")
    parser.add_argument("--workers", type=int, default=0, help="0 = auto")
    args = parser.parse_args()

    if Image is None:
        print("Error: Pillow required. Install with: pip install pillow")
        return 2

    csv_path = Path(args.csv)
    ps2_dir = Path(args.ps2_dir)
    mc_root = Path(args.mc_root)
    ps2_as_mc_list_path = Path(args.ps2_as_mc_list)

    if not ps2_dir.is_dir():
        print(f"Error: PS2 dir not found: {ps2_dir}")
        return 2
    if not mc_root.is_dir():
        print(f"Error: MC root not found: {mc_root}")
        return 2

    mapping = load_texture_map(csv_path)

    print(f"Indexing MC textures recursively: {mc_root}")
    mc_index = build_mc_index_by_stem(mc_root)
    print(f"MC index ready: {len(mc_index)} unique stems")

    ps2_as_mc_stems = load_stem_list(ps2_as_mc_list_path)
    if ps2_as_mc_stems:
        print(f"Loaded PS2-as-MC override stems: {len(ps2_as_mc_stems)}")
    else:
        print("Loaded PS2-as-MC override stems: 0 (file missing or empty)")

    script_dir = Path(__file__).resolve().parent
    out_ps2_dir = script_dir / "found - ps2"
    out_mc_dir = script_dir / "found - mc"
    out_ps2_dir.mkdir(parents=True, exist_ok=True)
    out_mc_dir.mkdir(parents=True, exist_ok=True)

    strcodes = discover_local_strcodes(script_dir)
    if not strcodes:
        print(f"No local *.png files found next to the script: {script_dir}")
        return 2

    do_convert = bool(args.convert_to_pc_colorspace or CONVERT_TO_PC_COLORSPACE)

    ps2_res_cache: Dict[str, str] = {}
    work_items: List[WorkItem] = []

    missing_map = 0
    missing_ps2 = 0
    missing_mc = 0
    skipped = 0
    mc_overridden_to_ps2 = 0

    for strcode in strcodes:
        rows = mapping.get(strcode)
        if not rows:
            missing_map += 1
            continue

        local_png = script_dir / f"{strcode}.png"
        chosen = rows[0] if len(rows) == 1 else prompt_choice(strcode, rows, ps2_dir, local_png, ps2_res_cache)
        if chosen is None:
            skipped += 1
            continue

        ps2_src = find_ps2_png(ps2_dir, chosen.texture_filename)
        if ps2_src is None:
            missing_ps2 += 1
            continue

        # Alpha decision is based on PS2 version always
        strip_alpha = False
        if do_convert:
            strip_alpha = ps2_has_uniform_128_alpha(ps2_src)

        # Default MC source: first MC match by texture_filename (stem)
        mc_matches = mc_index.get(chosen.texture_filename, [])
        mc_src = mc_matches[0] if mc_matches else None

        # Override (inverted):
        # If texture_filename stem is NOT in the list, use PS2 as the MC output
        if chosen.texture_filename not in ps2_as_mc_stems:
            mc_src = ps2_src
            mc_overridden_to_ps2 += 1


        if mc_src is None:
            missing_mc += 1

        item = WorkItem(
            texture_strcode=strcode,
            texture_filename=chosen.texture_filename,
            stage=chosen.stage,
            tri_strcode=chosen.tri_strcode,
            ps2_src=ps2_src,
            mc_src=mc_src,
            out_ps2=(out_ps2_dir / f"{strcode}.png"),
            out_mc=(out_mc_dir / f"{strcode}.png"),
            strip_alpha=strip_alpha,
            do_convert=do_convert,
            overwrite=bool(args.overwrite),
        )
        work_items.append(item)

    if not work_items:
        print("No work items to process.")
        print(f"missing_map={missing_map} missing_ps2={missing_ps2} skipped={skipped}")
        return 0

    cpu = os.cpu_count() or 8
    if args.workers and args.workers > 0:
        workers = args.workers
    else:
        workers = min(12, max(4, cpu))

    total = len(work_items)
    wrote_ps2 = 0
    wrote_mc = 0
    errors = 0

    print(f"Processing {total} textures with {workers} workers...")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process_item, item) for item in work_items]

        done_count = 0
        for f in as_completed(futures):
            done_count += 1
            try:
                _strcode, did_ps2, did_mc = f.result()
                if did_ps2:
                    wrote_ps2 += 1
                if did_mc:
                    wrote_mc += 1

                if done_count == total or (done_count % 25) == 0:
                    print(f"Progress: {done_count}/{total} (ps2 wrote: {wrote_ps2}, mc wrote: {wrote_mc})")
            except Exception as e:
                errors += 1
                print(f"Error: {e}")

    print("")
    print("Done")
    print(f"  Output PS2: {out_ps2_dir}")
    print(f"  Output MC:  {out_mc_dir}")
    print(f"  Total queued: {total}")
    print(f"  PS2 wrote: {wrote_ps2}")
    print(f"  MC wrote: {wrote_mc}")
    print(f"  Errors: {errors}")
    print(f"  Missing in CSV: {missing_map}")
    print(f"  Missing PS2 source: {missing_ps2}")
    print(f"  Missing MC source: {missing_mc}")
    print(f"  Skipped: {skipped}")
    print(f"  convert_to_pc_colorspace: {do_convert}")
    print(f"  mc_overridden_to_ps2: {mc_overridden_to_ps2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
