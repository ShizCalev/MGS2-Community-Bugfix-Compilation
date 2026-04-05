import os
import csv
import shutil
import re
import subprocess
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from PIL import Image

# ==========================================================
# CONFIGURATION
# ==========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

CSV_PATH = os.path.join(
    REPO_ROOT,
    "external",
    "MGS2-PS2-Textures",
    "Tri-Dumped",
    "Master Collection",
    "Metadata",
    "mgs2_mc_dimensions.csv",
)

ROOT_DIR = os.path.join(REPO_ROOT, "Texture Fixes", "ps2 textures")
HAS_ALPHA_DIR = os.path.join(ROOT_DIR, "HAS ALPHA")
OPAQUE_DIR = os.path.join(ROOT_DIR, "OPAQUE")

NO_MIP_REGEX_FILE = os.path.join(REPO_ROOT, "Texture Fixes", "no_mip_regex.txt")

DXT5_STEMS_FILE = os.path.join(
    REPO_ROOT,
    "external",
    "MGS2-PS2-Textures",
    "Tri-Dumped",
    "Master Collection",
    "Metadata",
    "mgs2_mc_dxt5_stems.txt",
)

MANUAL_UI_FILE = os.path.join(SCRIPT_DIR, "manual_ui_textures.txt")

MANUAL_BP_REMADE_FILE = os.path.join(
    REPO_ROOT,
    "external",
    "MGS2-PS2-Textures",
    "Tri-Dumped",
    "Master Collection",
    "Metadata",
    "mgs2_mc_manually_identified_bp_remade.txt",
)

FOLLOWUP_SCRIPT = os.path.join(SCRIPT_DIR, "0004 - log opaque with wrong alpha.py")

THREADS = 12
SHA1_BUFFER_SIZE = 8 * 1024 * 1024

SCAN_SKIP_TERMS = {
    "processed",
}

IMAGE_EXTENSIONS = {".png", ".tga"}

PRIMARY_BUCKETS = {
    "manual",
    "mismatched sha1",
    "power of two",
    "bp_mismatch",
    "bp_remade",
}

NO_MIP_ROOT = "no_mip_fixes"
NO_MIP_CHILDREN = {"ui", "not_regex_matched_ui"}

# Manual blacklist (filenames without extension)
MANUAL_LIST = {
    "0015d707",
    "0015d707_cd82fa959c0f81d19f22c0b0fdf8d230",
    "008ae623",
    "008ae623_fad237f35f44f84013d072b01d34bfc0",
}

print_lock = Lock()


# ==========================================================
# HELPERS
# ==========================================================
def is_image_file(filename):
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS


def norm_abs(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def sha1_of_file(path):
    h = hashlib.sha1()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(SHA1_BUFFER_SIZE), b""):
            h.update(chunk)

    return h.hexdigest().lower()


def next_power_of_two(n):
    return 1 if n <= 0 else 1 << (n - 1).bit_length()


def is_power_of_two(n):
    return n > 0 and (n & (n - 1) == 0)


def load_stem_list(path):
    stems = set()

    if not os.path.exists(path):
        print(f"[!] Stem list not found: {path}")
        return stems

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            stems.add(line)

    print(f"[+] Loaded {len(stems)} stems from {path}")
    return stems


def load_manual_ui_list(path):
    manual_set = set()

    if not os.path.exists(path):
        print(f"[!] Manual UI texture list not found: {path}")
        return manual_set

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            manual_set.add(line)

    print(f"[+] Loaded {len(manual_set)} manual UI texture names.")
    return manual_set


def load_manual_bp_remade_list(path):
    manual_set = set()

    if not os.path.exists(path):
        print(f"[!] Manual bp_remade list not found: {path}")
        return manual_set

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            manual_set.add(line)

    print(f"[+] Loaded {len(manual_set)} manually identified bp_remade texture names.")
    return manual_set


def load_no_mip_patterns(path):
    patterns = []

    if not os.path.exists(path):
        print(f"[!] No-Mip regex file not found: {path}")
        return patterns

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line, re.IGNORECASE))
            except re.error as e:
                print(f"[!] Invalid regex skipped: {line} ({e})")

    print(f"[+] Loaded {len(patterns)} no-mip regex patterns.")
    return patterns


def matches_no_mip_patterns(filename_no_ext, patterns):
    for pattern in patterns:
        if pattern.search(filename_no_ext):
            return True
    return False


def read_csv_dimensions(path):
    dims = {}

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row["texture_name"].strip().lower()

            try:
                mc_width = int(row["mc_width"])
                mc_height = int(row["mc_height"])
            except (ValueError, TypeError):
                continue

            mc_resaved_sha1 = row.get("mc_resaved_sha1", "").strip().lower()

            dims[name] = {
                "mc_width": mc_width,
                "mc_height": mc_height,
                "mc_resaved_sha1": mc_resaved_sha1,
            }

    return dims


def cleanup_empty_folders(root_dir):
    removed = 0

    for current_root, _, _ in os.walk(root_dir, topdown=False):
        try:
            if not os.listdir(current_root):
                os.rmdir(current_root)
                removed += 1
                with print_lock:
                    print(f"[Removed empty folder] {current_root}")
        except Exception as e:
            with print_lock:
                print(f"[Error removing empty folder] {current_root}: {e}")

    print(f"[+] Empty folder cleanup complete. Removed {removed} folders.")


def should_skip_scan_dir(path):
    lower_path = path.lower()
    return any(term in lower_path for term in SCAN_SKIP_TERMS)


def get_bucket_name_from_path(path):
    parts_lower = [p.lower() for p in os.path.normpath(path).split(os.sep)]

    if "has alpha" in parts_lower:
        return "HAS ALPHA"

    if "opaque" in parts_lower:
        return "OPAQUE"

    return None


def get_bucket_root_and_rel_dir(path):
    parts = os.path.normpath(path).split(os.sep)
    parts_lower = [p.lower() for p in parts]

    if "has alpha" in parts_lower:
        bucket_name = "HAS ALPHA"
    elif "opaque" in parts_lower:
        bucket_name = "OPAQUE"
    else:
        return None, None, None

    bucket_idx = parts_lower.index(bucket_name.lower())
    bucket_root = os.sep.join(parts[:bucket_idx + 1])
    rel_parts = parts[bucket_idx + 1:]

    return bucket_name, bucket_root, rel_parts


def strip_known_classification_parts(rel_parts):
    idx = 0

    while idx < len(rel_parts):
        lowered = rel_parts[idx].lower()

        if lowered == "dxt5":
            idx += 1
            continue

        if lowered in PRIMARY_BUCKETS:
            idx += 1
            continue

        if lowered == NO_MIP_ROOT:
            idx += 1
            if idx < len(rel_parts) and rel_parts[idx].lower() in NO_MIP_CHILDREN:
                idx += 1
            continue

        break

    return rel_parts[idx:]


def detect_existing_primary_buckets(rel_parts):
    buckets = []

    for part in rel_parts:
        lowered = part.lower()

        if lowered == "dxt5":
            continue

        if lowered in PRIMARY_BUCKETS:
            buckets.append(lowered)
            continue

        if lowered == NO_MIP_ROOT:
            break

        break

    return buckets


def classify_primary_buckets(file_path, stem, dims_map, manual_bp_remade_set, bucket_name):
    buckets = []

    if stem in MANUAL_LIST:
        buckets.append("manual")

    entry = dims_map.get(stem)

    if stem in manual_bp_remade_set:
        buckets.append("bp_remade")
        return buckets

    if not entry:
        return buckets

    try:
        file_sha1 = sha1_of_file(file_path)
        mc_resaved_sha1 = entry["mc_resaved_sha1"]

        if mc_resaved_sha1 and file_sha1 == mc_resaved_sha1:
            if bucket_name != "OPAQUE":
                buckets.append("power of two")
            return buckets

        with Image.open(file_path) as img:
            width, height = img.size
    except Exception as e:
        with print_lock:
            print(f"[Error reading for primary classification] {file_path}: {e}")
        return buckets

    mc_w = entry["mc_width"]
    mc_h = entry["mc_height"]

    if mc_w > next_power_of_two(width) or mc_h > next_power_of_two(height):
        buckets.append("bp_remade")
        return buckets

    pow2_w = next_power_of_two(width)
    pow2_h = next_power_of_two(height)

    if mc_w < pow2_w or mc_h < pow2_h:
        buckets.append("bp_mismatch")
        return buckets

    if is_power_of_two(width) and is_power_of_two(height):
        buckets.append("mismatched sha1")
        return buckets

    return buckets


def classify_no_mip_bucket(stem, dims_map, patterns, manual_ui_set):
    matched_regex = matches_no_mip_patterns(stem, patterns)
    entry = dims_map.get(stem)

    if not entry:
        if matched_regex:
            return (NO_MIP_ROOT, None)
        return None

    mc_w = entry["mc_width"]
    mc_h = entry["mc_height"]
    is_npot = not is_power_of_two(mc_w) or not is_power_of_two(mc_h)

    if stem in manual_ui_set:
        return (NO_MIP_ROOT, "ui")

    if is_npot:
        if matched_regex:
            return (NO_MIP_ROOT, "ui")
        return (NO_MIP_ROOT, "not_regex_matched_ui")

    if matched_regex:
        return (NO_MIP_ROOT, None)

    return None


def compute_final_dest(file_path, dims_map, dxt5_stems, manual_bp_remade_set, patterns, manual_ui_set):
    filename = os.path.basename(file_path)
    stem = os.path.splitext(filename)[0].lower()

    parent_dir = os.path.dirname(file_path)
    bucket_name, bucket_root, rel_parts = get_bucket_root_and_rel_dir(parent_dir)

    if not bucket_root:
        return None, "not under HAS ALPHA/OPAQUE"

    cleaned_tail = strip_known_classification_parts(rel_parts)

    classification_parts = []

    if stem in dxt5_stems:
        classification_parts.append("dxt5")

    primary_buckets = classify_primary_buckets(
        file_path=file_path,
        stem=stem,
        dims_map=dims_map,
        manual_bp_remade_set=manual_bp_remade_set,
        bucket_name=bucket_name,
    )

    if primary_buckets:
        classification_parts.extend(primary_buckets)
    else:
        existing_primary_buckets = detect_existing_primary_buckets(rel_parts)
        if existing_primary_buckets:
            classification_parts.extend(existing_primary_buckets)

    no_mip_bucket = classify_no_mip_bucket(
        stem=stem,
        dims_map=dims_map,
        patterns=patterns,
        manual_ui_set=manual_ui_set,
    )

    if no_mip_bucket:
        classification_parts.append(no_mip_bucket[0])
        if no_mip_bucket[1]:
            classification_parts.append(no_mip_bucket[1])

    final_dir = os.path.join(bucket_root, *classification_parts, *cleaned_tail)
    final_path = os.path.join(final_dir, filename)

    return final_path, None


def collect_candidate_files():
    files = []

    for root, dirs, filenames in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not should_skip_scan_dir(os.path.join(root, d))]

        if should_skip_scan_dir(root):
            continue

        bucket_name = get_bucket_name_from_path(root)
        if not bucket_name:
            continue

        for filename in filenames:
            if is_image_file(filename):
                files.append(os.path.join(root, filename))

    return files


def build_move_plan(candidate_files, dims_map, dxt5_stems, manual_bp_remade_set, patterns, manual_ui_set):
    move_plan = []
    unchanged = 0
    skipped = 0
    errors = 0

    for file_path in candidate_files:
        try:
            final_path, reason = compute_final_dest(
                file_path=file_path,
                dims_map=dims_map,
                dxt5_stems=dxt5_stems,
                manual_bp_remade_set=manual_bp_remade_set,
                patterns=patterns,
                manual_ui_set=manual_ui_set,
            )

            if not final_path:
                skipped += 1
                with print_lock:
                    print(f"[Skipped] {file_path}: {reason}")
                continue

            src_norm = norm_abs(file_path)
            dst_norm = norm_abs(final_path)

            if src_norm == dst_norm:
                unchanged += 1
                continue

            move_plan.append((file_path, final_path))
        except Exception as e:
            errors += 1
            with print_lock:
                print(f"[Plan Error] {file_path}: {e}")

    return move_plan, unchanged, skipped, errors


def validate_move_plan(move_plan):
    errors = 0

    seen_src = set()
    seen_dst = {}

    for src, dst in move_plan:
        src_norm = norm_abs(src)
        dst_norm = norm_abs(dst)

        if src_norm == dst_norm:
            errors += 1
            with print_lock:
                print(f"[Plan Error] Source equals destination: {src}")
            continue

        if src_norm in seen_src:
            errors += 1
            with print_lock:
                print(f"[Plan Error] Duplicate source in plan: {src}")
        else:
            seen_src.add(src_norm)

        if dst_norm in seen_dst:
            errors += 1
            with print_lock:
                print(f"[Plan Error] Two files want same destination:\n    {seen_dst[dst_norm]}\n    {src}\n -> {dst}")
        else:
            seen_dst[dst_norm] = src

    return errors


def execute_one_move(src, dst):
    try:
        src_norm = norm_abs(src)
        dst_norm = norm_abs(dst)

        if src_norm == dst_norm:
            return ("unchanged", src, None)

        if not os.path.exists(src):
            return ("error", src, "source no longer exists")

        os.makedirs(os.path.dirname(dst), exist_ok=True)

        if os.path.exists(dst):
            try:
                if os.path.samefile(src, dst):
                    return ("unchanged", src, None)
            except OSError:
                pass

            return ("error", src, f"destination already exists: {dst}")

        shutil.move(src, dst)
        return ("moved", src, dst)
    except Exception as e:
        return ("error", src, str(e))


def main():
    print(f"[+] Repo root: {REPO_ROOT}")

    dims_map = read_csv_dimensions(CSV_PATH)
    print(f"[+] Loaded {len(dims_map)} CSV entries")

    manual_bp_remade_set = load_manual_bp_remade_list(MANUAL_BP_REMADE_FILE)
    dxt5_stems = load_stem_list(DXT5_STEMS_FILE)
    patterns = load_no_mip_patterns(NO_MIP_REGEX_FILE)
    manual_ui_set = load_manual_ui_list(MANUAL_UI_FILE)

    candidate_files = collect_candidate_files()
    print(f"[+] Found {len(candidate_files)} candidate texture files")

    move_plan, unchanged, skipped, plan_errors = build_move_plan(
        candidate_files=candidate_files,
        dims_map=dims_map,
        dxt5_stems=dxt5_stems,
        manual_bp_remade_set=manual_bp_remade_set,
        patterns=patterns,
        manual_ui_set=manual_ui_set,
    )

    print(f"[+] Planned {len(move_plan)} actual moves")
    print(f"[+] Unchanged during planning: {unchanged}")
    print(f"[+] Skipped during planning: {skipped}")
    print(f"[+] Planning errors: {plan_errors}")

    validation_errors = validate_move_plan(move_plan)
    if validation_errors:
        print(f"[!] Move plan validation failed with {validation_errors} error(s). Aborting before any move.")
        return

    moved = 0
    unchanged_during_move = 0
    move_errors = 0

    with ThreadPoolExecutor(max_workers=THREADS) as exe:
        futures = [exe.submit(execute_one_move, src, dst) for src, dst in move_plan]

        for future in as_completed(futures):
            status, src, extra = future.result()

            if status == "moved":
                moved += 1
                with print_lock:
                    print(f"[Moved] {src} -> {extra}")
            elif status == "unchanged":
                unchanged_during_move += 1
            else:
                move_errors += 1
                with print_lock:
                    print(f"[Error] {src}: {extra}")

    print(f"[+] Move pass complete. Moved: {moved}, Unchanged during move: {unchanged_during_move}, Move errors: {move_errors}")

    cleanup_empty_folders(ROOT_DIR)

    print("[+] Completed all stages.")

    if os.path.exists(FOLLOWUP_SCRIPT):
        print(f"[+] Running follow-up script: {FOLLOWUP_SCRIPT}")

        try:
            subprocess.run(["py", FOLLOWUP_SCRIPT], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] Follow-up script returned error code {e.returncode}")
        except Exception as e:
            print(f"[!] Failed to run follow-up script: {e}")
    else:
        print(f"[!] Follow-up script not found: {FOLLOWUP_SCRIPT}")


if __name__ == "__main__":
    main()