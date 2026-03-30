import subprocess
import csv
import ast
import re
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed




# ==========================================================
# HELPERS
# ==========================================================
def get_git_root() -> Path:
    """Return the repository root by calling Git directly."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        )
        return Path(out.decode().strip())
    except Exception:
        raise RuntimeError("Failed to determine git repo root. Run this script inside a Git repository.")


def load_csv_to_dict(csv_path: Path, key_col: str = "texture_name") -> dict:
    """Load a CSV into a lowercase-keyed dictionary for case-insensitive lookups."""
    data = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get(key_col, "").strip().lower()
            if not key:
                continue
            data[key] = row
    return data


def parse_alpha_list(value):
    """Parse the alpha-level column into integer lists."""
    if not value:
        return []
    try:
        vals = list(map(int, ast.literal_eval(value)))
        return [128 if v == 255 else v for v in vals]
    except Exception:
        return []


def to_int(value, default=0):
    """Safely convert a value to int, with default fallback."""
    try:
        return int(value)
    except Exception:
        return default


def inject_missing_tgas(opaque_dir: Path, tri_dumped_data: dict) -> int:
    """
    Recursively find all TGA textures in OPAQUE folder and inject default
    tri-dumped entries if missing.
    """
    added = 0
    tga_files = list(opaque_dir.rglob("*.tga"))
    existing_keys = set(tri_dumped_data.keys())

    def check_and_build(path: Path):
        key = path.stem.strip().lower()
        if key not in existing_keys:
            return key, {
                "texture_name": path.stem.strip(),
                "mc_tri_dumped_sha1": "",
                "mc_tri_dumped_alpha_levels": "[128]",
                "mc_tri_dumped_width": "",
                "mc_tri_height": "",
                "mc_tri_width_ciel2": "",
                "mc_tri_height_ciel2": "",
            }
        return None

    max_workers = max(1, (os.cpu_count() or 4) // 2)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(check_and_build, p) for p in tga_files]
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                key, row = result
                tri_dumped_data[key] = row
                added += 1

    return added


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



# ==========================================================
# MAIN
# ==========================================================
def main():
    repo_root = get_git_root()
    script_dir = Path(__file__).resolve().parent

    NEXT_SCRIPT = os.path.join(script_dir, "0010 - find ui missing from manual txt.py")


    base_dir = repo_root / "external" / "MGS2-PS2-Textures" / "Tri-Dumped" / "Master Collection" / "Metadata"
    tri_dumped_csv = base_dir / "mgs2_mc_tri_dumped_metadata.csv"
    mc_csv = base_dir / "mgs2_mc_dimensions.csv"

    opaque_dir = repo_root / "Texture Fixes" / "ps2 textures" / "OPAQUE"
    no_mip_regex_path = repo_root / "Texture Fixes" / "no_mip_regex.txt"
    log_path = script_dir / "MC - Incorrect Alpha Report (Verbose).txt"

    if not tri_dumped_csv.exists():
        raise FileNotFoundError(f"Missing tri-dumped metadata CSV: {tri_dumped_csv}")

    if not mc_csv.exists():
        raise FileNotFoundError(f"Missing MC dimensions CSV: {mc_csv}")

    tri_dumped_data = load_csv_to_dict(tri_dumped_csv)
    mc_data = load_csv_to_dict(mc_csv)

    # ======================================================
    # INJECT MISSING PS2 TEXTURES FROM OPAQUE TGA FILES
    # ======================================================
    added_tgas = inject_missing_tgas(opaque_dir, tri_dumped_data)
    print(f"Injected {added_tgas} new TGA entries from {opaque_dir}")

    # ======================================================
    # ALPHA COMPARISON LOGIC
    # ======================================================
    group1_exceeds = []
    group1_below = []
    group2_mismatch = []
    group3_mismatch = []

    for tex_lower, tri_row in tri_dumped_data.items():
        tex = tri_row["texture_name"].strip()
        tri_alpha = parse_alpha_list(tri_row.get("mc_tri_dumped_alpha_levels", ""))

        mc_row = mc_data.get(tex_lower)
        if not mc_row:
            continue

        mc_alpha = parse_alpha_list(mc_row.get("mc_alpha_levels", ""))
        if not tri_alpha or not mc_alpha:
            continue

        tri_unique = sorted(set(tri_alpha))
        mc_unique = sorted(set(mc_alpha))

        # --- Group 1: Single-value tri-dumped alpha list ---
        if len(tri_unique) == 1:
            base_val = tri_unique[0]
            if base_val == 128:
                if any(a < 128 for a in mc_unique):
                    group1_below.append((tex, base_val, mc_unique))
                elif any(a > 128 for a in mc_unique):
                    group1_exceeds.append((tex, base_val, mc_unique))
            else:
                if any(a > base_val for a in mc_unique):
                    group1_exceeds.append((tex, base_val, mc_unique))
                elif any(a < base_val for a in mc_unique):
                    group1_below.append((tex, base_val, mc_unique))

        # --- Group 2: Two distinct tri-dumped alpha values ---
        elif len(tri_unique) == 2:
            if mc_unique != tri_unique:
                group2_mismatch.append((tex, tri_unique, mc_unique))

        # --- Group 3: Complex alpha lists ---
        else:
            if mc_unique != tri_unique:
                group3_mismatch.append((tex, tri_unique, mc_unique))

    # ======================================================
    # DIMENSION CHECKS
    # ======================================================
    def exceeds_bp(tex: str) -> bool:
        mc_row = mc_data.get(tex.lower())
        tri_row = tri_dumped_data.get(tex.lower())
        if not mc_row or not tri_row:
            return False

        mc_w = to_int(mc_row.get("mc_width"))
        mc_h = to_int(mc_row.get("mc_height"))
        tri_w = to_int(tri_row.get("mc_tri_width_ciel2"))
        tri_h = to_int(tri_row.get("mc_tri_height_ciel2"))

        return mc_w > tri_w or mc_h > tri_h

    def is_pot(tex: str) -> bool:
        tri_row = tri_dumped_data.get(tex.lower())
        if not tri_row:
            return False

        w = to_int(tri_row.get("mc_tri_dumped_width"))
        h = to_int(tri_row.get("mc_tri_height"))
        pw = to_int(tri_row.get("mc_tri_width_ciel2"))
        ph = to_int(tri_row.get("mc_tri_height_ciel2"))

        return w == pw and h == ph

    def split_bp(group):
        """Split a group into BP Remade vs OG PS2 based on dimension thresholds."""
        bp = []
        nonbp = []

        for tex, tri_alpha, mc_alpha in group:
            if exceeds_bp(tex):
                bp.append((tex, tri_alpha, mc_alpha))
            else:
                nonbp.append((tex, tri_alpha, mc_alpha))

        return bp, nonbp

    bp1x, nbp1x = split_bp(group1_exceeds)
    bp1b, nbp1b = split_bp(group1_below)
    bp2, nbp2 = split_bp(group2_mismatch)
    bp3, nbp3 = split_bp(group3_mismatch)

    # ======================================================
    # SORTING
    # ======================================================
    def sort_key(item):
        """Sort textures first by source alpha level, then lexicographically by name."""
        tex, tri_alpha, _ = item
        base_val = tri_alpha[0] if isinstance(tri_alpha, list) and tri_alpha else (tri_alpha if isinstance(tri_alpha, int) else 0)
        return (base_val, tex.lower())

    for group in (bp1x, nbp1x, bp1b, nbp1b, bp2, nbp2, bp3, nbp3):
        group.sort(key=sort_key)

    # ======================================================
    # UNREFERENCED / LEFT-TO-FIND SOURCE SET
    # ======================================================
    tri_keys_lower = set(tri_dumped_data.keys())
    mc_keys_lower = set(mc_data.keys())

    # These are textures present in tri-dumped metadata but not in MC metadata.
    unreferenced = sorted(
        [tri_dumped_data[k]["texture_name"].strip() for k in tri_keys_lower if k not in mc_keys_lower],
        key=str.lower,
    )

    # ======================================================
    # LOAD REGEX PATTERNS
    # ======================================================
    no_mip_patterns = []
    if no_mip_regex_path.exists():
        with open(no_mip_regex_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    no_mip_patterns.append(re.compile(line, re.IGNORECASE))

    def regex_split(group):
        matched = []
        unmatched = []
        for tex in group:
            if any(p.search(tex) for p in no_mip_patterns):
                matched.append(tex)
            else:
                unmatched.append(tex)
        return matched, unmatched

    def pot_split(group):
        pot = []
        npot = []
        for tex in group:
            if is_pot(tex):
                pot.append(tex)
            else:
                npot.append(tex)
        return pot, npot

    bp_unref = [t for t in unreferenced if exceeds_bp(t)]
    og_unref = [t for t in unreferenced if not exceeds_bp(t)]

    # ======================================================
    # LOGGING
    # ======================================================
    with open(log_path, "w", encoding="utf-8") as f:
        def section(title, data):
            f.write(f"===== {title} (Count: {len(data)}) =====\n")
            if not data:
                f.write("None\n\n")
                return

            for tex, tri_alpha, mc_alpha in data:
                f.write(f"{tex}\t\t\t\t\tPS2: {tri_alpha}\t\t\t\t\tMC: {mc_alpha}\n")
            f.write("\n")

        # ---------------- BP REMADE SECTION ----------------
        total_bp = len(bp1x) + len(bp1b) + len(bp2) + len(bp3)
        f.write("###############################################################\n")
        f.write(f"########################  BP REMADE  (Total: {total_bp})  ##########################\n")
        f.write("###############################################################\n\n")
        section("GROUP 1 - Single Alpha Value (MC Exceeds)", bp1x)
        section("GROUP 1 - Single Alpha Value (MC Below)", bp1b)
        section("GROUP 2 - Two Alpha Values (Mismatch)", bp2)
        section("GROUP 3 - Complex Alpha Lists (Mismatch)", bp3)

        # ---------------- OG PS2 SECTION ----------------
        total_nonbp = len(nbp1x) + len(nbp1b) + len(nbp2) + len(nbp3)
        f.write("###############################################################\n")
        f.write(f"########################  OG PS2 FILES  (Total: {total_nonbp})  #########################\n")
        f.write("###############################################################\n\n")
        section("GROUP 1 - Single Alpha Value (MC Exceeds)", nbp1x)
        section("GROUP 1 - Single Alpha Value (MC Below)", nbp1b)
        section("GROUP 2 - Two Alpha Values (Mismatch)", nbp2)
        section("GROUP 3 - Complex Alpha Lists (Mismatch)", nbp3)

        # ======================================================
        # UNREFERENCED TEXTURES -> REGEX -> POT/NPOT
        # ======================================================
        f.write("###############################################################\n")
        f.write(f"\n###################  NOT IN MC DIMENSIONS CSV YET  (Count: {len(unreferenced)})  ################\n\n")
        f.write("###############################################################\n")

        summary_counts = {}

        def log_hierarchy(title, group):
            matched, unmatched = regex_split(group)
            matched_pot, matched_npot = pot_split(matched)
            unmatched_pot, unmatched_npot = pot_split(unmatched)

            summary_counts[f"{title} | NEEDS MIPS STRIPPED - POT (NEED TO FIND)"] = len(matched_pot)
            summary_counts[f"{title} | NEEDS MIPS STRIPPED - NPOT (NEED TO FIND)"] = len(matched_npot)
            summary_counts[f"{title} | MIPS CORRECT - POT (LOW PRIORITY)"] = len(unmatched_pot)
            summary_counts[f"{title} | MIPS CORRECT - NPOT (NEED TO FIND)"] = len(unmatched_npot)

            f.write(f"===== {title} (Total: {len(group)}) =====\n\n")

            sections = [
                ("NEEDS MIPS STRIPPED - Power of 2", matched_pot),
                ("NEEDS MIPS STRIPPED - NPOT", matched_npot),
                ("MIPS CORRECT - Power of 2 (LOW PRIORITY)", unmatched_pot),
                ("MIPS CORRECT - NPOT (NPOT)", unmatched_npot),
            ]

            for label, items in sections:
                f.write(f"----- {label} (Count: {len(items)}) -----\n")
                if items:
                    for tex in sorted(items, key=str.lower):
                        f.write(f"{tex}\n")
                else:
                    f.write("None\n")
                f.write("\n")

        log_hierarchy("BP REMADE", bp_unref)
        f.write("\n")
        log_hierarchy("OG PS2 FILES", og_unref)

        # ======================================================
        # FILTERED VERSION 1
        # "Left to Find - TRI Dumped Removed (Texture Fixes only)"
        # ======================================================
        print("\n[Filtered Export] Creating left-to-find list excluding any Texture Fixes assets...")

        texture_fixes_dir = repo_root / "Texture Fixes"
        all_existing_fix_textures = set()

        for ext in ("*.tga", "*.png"):
            for path in texture_fixes_dir.rglob(ext):
                all_existing_fix_textures.add(path.stem.lower())

        filtered_unref_basic = [t for t in unreferenced if t.lower() not in all_existing_fix_textures]

        filtered_basic_csv = script_dir / "left to find - tri dumped removed.csv"
        with open(filtered_basic_csv, "w", newline="", encoding="utf-8") as fcsv:
            writer = csv.writer(fcsv)
            writer.writerow(["texture_name"])
            for tex in sorted(filtered_unref_basic, key=str.lower):
                writer.writerow([tex])

        print(f"[Filtered Export] Saved {len(filtered_unref_basic)} items to {filtered_basic_csv}")
        print(f"[Filtered Export] {len(unreferenced) - len(filtered_unref_basic)} excluded (found in Texture Fixes).")

        # ======================================================
        # FILTERED VERSION 2
        # "Left to Find - no_ui (Texture Fixes + NPOT MC + bp_remade\\no_mip_fixes\\ui excluded)"
        # ======================================================
        ui_textures = set()

        for ui_dir in script_dir.rglob("ui"):
            if not ui_dir.is_dir():
                continue

            parent = ui_dir.parent
            grandparent = parent.parent if parent is not None else None

            if parent is not None and grandparent is not None:
                if parent.name == "no_mip_fixes" and grandparent.name == "bp_remade":
                    for ext in ("*.tga", "*.png"):
                        for path in ui_dir.rglob(ext):
                            ui_textures.add(path.stem.lower())

        def is_npot_mc(tex_name: str) -> bool:
            row = mc_data.get(tex_name.lower())
            if not row:
                return False

            w = to_int(row.get("mc_width"))
            h = to_int(row.get("mc_height"))
            if not w or not h:
                return False

            return not ((w & (w - 1)) == 0 and (h & (h - 1)) == 0)

        filtered_unref_ui_removed = [
            t for t in filtered_unref_basic
            if t.lower() not in ui_textures and not is_npot_mc(t)
        ]

        filtered_ui_csv = script_dir / "left to find - no_ui.csv"
        with open(filtered_ui_csv, "w", newline="", encoding="utf-8") as fcsv:
            writer = csv.writer(fcsv)
            writer.writerow(["texture_name"])
            for tex in sorted(filtered_unref_ui_removed, key=str.lower):
                writer.writerow([tex])

        print(f"[Filtered Export] Saved {len(filtered_unref_ui_removed)} items to {filtered_ui_csv}")
        print(
            f"[Filtered Export] {len(filtered_unref_basic) - len(filtered_unref_ui_removed)} "
            f"excluded (UI folders or NPOT MC)."
        )

        # ======================================================
        # SUMMARY TABLE
        # ======================================================
        total_mips_correct_pot = sum(
            v for k, v in summary_counts.items()
            if "MIPS CORRECT - POT (LOW PRIORITY)" in k
        )
        total_other = sum(summary_counts.values()) - total_mips_correct_pot
        og_left_to_find = sum(
            v for k, v in summary_counts.items()
            if k.startswith("OG PS2 FILES") and "MIPS CORRECT - POT (LOW PRIORITY)" not in k
        )

        f.write("\n###############################################################\n")
        f.write("########################  SUMMARY COUNTS FOR REMAINING UNDUMPED #########################\n")
        f.write("###############################################################\n\n")
        for k, v in summary_counts.items():
            f.write(f"{k}: {v}\n")
        f.write(f"\nTOTAL MIPS CORRECT (POT): {total_mips_correct_pot}\n")
        f.write(f"ALL OTHER CATEGORIES: {total_other}\n")
        f.write(f"COMBINED TOTAL: {total_mips_correct_pot + total_other}\n")
        f.write(f"OG PS2 LEFT TO FIND: {og_left_to_find}\n")

    # ======================================================
    # FINAL SUMMARY (Console)
    # ======================================================
    print(f"\nDone.\nRepo root: {repo_root}")
    print(f"Log written to: {log_path}")
    print(f"Unreferenced total: {len(unreferenced)} (BP+OG split by regex and POT)")
    print(f"MIPS CORRECT (POT / LOW PRIORITY): {total_mips_correct_pot}, LEFT TO DUMP: {total_other}")
    print(f"OG PS2 LEFT TO FIND: {og_left_to_find}")



    # --- Launch subsequent stages ---
    run_next_stage(NEXT_SCRIPT)
    

if __name__ == "__main__":
    main()