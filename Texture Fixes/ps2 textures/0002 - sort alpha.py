import os
import shutil
import threading
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from datetime import timedelta
import sys

# ==========================================================
# CONFIGURATION
# ==========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

ROOT_DIR = os.path.join(REPO_ROOT, "Texture Fixes", "ps2 textures")
OPAQUE_DIR = os.path.join(ROOT_DIR, "OPAQUE")
HAS_ALPHA_DIR = os.path.join(ROOT_DIR, "HAS ALPHA")
NEXT_SCRIPT = os.path.join(SCRIPT_DIR, "0003 - sort bp remade.py")
MANUAL_OPAQUE_TXT = os.path.join(SCRIPT_DIR, "manual_opaque_textures.txt")
MANUAL_MOVES_LOG = os.path.join(SCRIPT_DIR, "manual_opaque_moves.txt")

MAX_WORKERS = 12
UPDATE_INTERVAL = 1.0
VALID_EXTENSIONS = (".png", ".tga")

# ==========================================================
# UTILITIES
# ==========================================================
def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def load_manual_opaque_stems(txt_path):
    stems = set()

    if not os.path.isfile(txt_path):
        return stems

    with open(txt_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith(";") or line.startswith("//"):
                continue
            stems.add(line.lower())

    return stems


def load_manual_moves_log(log_path):
    entries = []

    if not os.path.isfile(log_path):
        return entries

    with open(log_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            entries.append(line)

    return entries


def write_manual_moves_log(log_path, rel_paths):
    rel_paths = sorted(set(rel_paths), key=str.lower)

    if not rel_paths:
        if os.path.exists(log_path):
            os.remove(log_path)
        return

    with open(log_path, "w", encoding="utf-8", newline="\n") as handle:
        for rel_path in rel_paths:
            handle.write(f"{rel_path}\n")


def has_only_specific_alpha(img):
    """
    Return True if alpha channel is only 128, 255, or not present.
    """
    if img.mode not in ("RGBA", "LA"):
        return True

    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    if not extrema:
        return True

    min_a, max_a = extrema
    if min_a == max_a == 255:
        return True
    if min_a == max_a == 128:
        return True
    return False


def classify_file(path, manual_opaque_stems):
    rel_name = os.path.basename(path)
    stem = os.path.splitext(rel_name)[0].lower()

    if stem in manual_opaque_stems:
        return "OPAQUE_MANUAL"

    with Image.open(path) as img:
        if has_only_specific_alpha(img):
            return "OPAQUE"

    return "HAS_ALPHA"


def move_to_bucket(path, classification):
    rel_name = os.path.basename(path)

    if classification in ("OPAQUE", "OPAQUE_MANUAL"):
        dest_path = os.path.join(OPAQUE_DIR, rel_name)
    else:
        dest_path = os.path.join(HAS_ALPHA_DIR, rel_name)

    ensure_dir(dest_path)

    src_abs = os.path.abspath(path)
    dest_abs = os.path.abspath(dest_path)

    if os.path.normcase(src_abs) == os.path.normcase(dest_abs):
        return dest_path

    if os.path.exists(dest_path):
        raise FileExistsError(
            f"Destination already exists: '{dest_path}' while moving '{path}'"
        )

    shutil.move(path, dest_path)
    return dest_path


def process_file(path, manual_opaque_stems):
    try:
        classification = classify_file(path, manual_opaque_stems)
        dest_path = move_to_bucket(path, classification)

        return {
            "status": classification,
            "source_path": path,
            "dest_path": dest_path,
            "error": None,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "source_path": path,
            "dest_path": None,
            "error": str(e),
        }


def reevaluate_stale_manual_entries(manual_opaque_stems, tracked_rel_paths):
    """
    tracked_rel_paths are relative-to-OPAQUE_DIR paths recorded from previous manual moves.

    If the stem is no longer in manual_opaque_stems, re-evaluate just that file.
    """
    kept_entries = []
    reevaluate_paths = []
    missing_entries = []

    for rel_path in tracked_rel_paths:
        rel_name = os.path.basename(rel_path)
        stem = os.path.splitext(rel_name)[0].lower()
        abs_path = os.path.join(OPAQUE_DIR, rel_path)

        if not os.path.isfile(abs_path):
            missing_entries.append(rel_path)
            continue

        if stem in manual_opaque_stems:
            kept_entries.append(rel_path)
            continue

        reevaluate_paths.append(abs_path)

    return kept_entries, reevaluate_paths, missing_entries


def progress_monitor(total, counter, start_time, stop_event):
    while not stop_event.is_set():
        processed = counter["processed"]
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = (total - processed) / rate if rate > 0 else 0
        pct = (processed / total) * 100 if total else 0
        eta = str(timedelta(seconds=int(remaining)))

        print(
            f"\r[Progress] {processed}/{total} ({pct:.1f}%) | ETA: {eta}",
            end="",
            flush=True,
        )
        time.sleep(UPDATE_INTERVAL)

    print()


# ==========================================================
# MAIN
# ==========================================================
def main():
    print(f"[+] Repo root: {REPO_ROOT}")
    print(f"[+] Scanning top-level of: {ROOT_DIR}")

    manual_opaque_stems = load_manual_opaque_stems(MANUAL_OPAQUE_TXT)
    if os.path.isfile(MANUAL_OPAQUE_TXT):
        print(
            f"[+] Loaded {len(manual_opaque_stems)} manual opaque stem override(s) "
            f"from: {MANUAL_OPAQUE_TXT}"
        )
    else:
        print(f"[+] No manual opaque override file found at: {MANUAL_OPAQUE_TXT}")

    tracked_manual_entries = load_manual_moves_log(MANUAL_MOVES_LOG)
    print(f"[+] Loaded {len(tracked_manual_entries)} tracked manual move entry(s).")

    kept_manual_entries, reevaluate_paths, missing_entries = reevaluate_stale_manual_entries(
        manual_opaque_stems,
        tracked_manual_entries,
    )

    if reevaluate_paths:
        print(f"[+] Reevaluating {len(reevaluate_paths)} stale manual move(s).")
    if missing_entries:
        print(f"[!] {len(missing_entries)} tracked manual move file(s) were missing from OPAQUE.")

    root_files = [
        os.path.join(ROOT_DIR, f)
        for f in os.listdir(ROOT_DIR)
        if f.lower().endswith(VALID_EXTENSIONS)
        and os.path.isfile(os.path.join(ROOT_DIR, f))
    ]

    has_alpha_files = [
        os.path.join(HAS_ALPHA_DIR, f)
        for f in os.listdir(HAS_ALPHA_DIR)
        if f.lower().endswith(VALID_EXTENSIONS)
        and os.path.isfile(os.path.join(HAS_ALPHA_DIR, f))
    ] if os.path.isdir(HAS_ALPHA_DIR) else []

    files_to_process = list(
        dict.fromkeys(reevaluate_paths + root_files + has_alpha_files)
    )

    total = len(files_to_process)
    print(f"[+] Found {len(root_files)} top-level candidate file(s).")
    print(f"[+] Found {len(has_alpha_files)} HAS ALPHA candidate file(s).")
    print(f"[+] Total files to process this run: {total}")

    counter = {"processed": 0}
    errors = []

    opaque = 0
    opaque_manual = 0
    has_alpha = 0

    new_manual_entries = set(kept_manual_entries)

    stop_event = threading.Event()
    start_time = time.time()
    monitor_thread = threading.Thread(
        target=progress_monitor,
        args=(total, counter, start_time, stop_event),
    )
    monitor_thread.start()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_file, f, manual_opaque_stems) for f in files_to_process]

        for fut in as_completed(futures):
            result = fut.result()
            counter["processed"] += 1

            status = result["status"]

            if status == "OPAQUE":
                opaque += 1
            elif status == "OPAQUE_MANUAL":
                opaque_manual += 1
                rel_path_from_opaque = os.path.relpath(result["dest_path"], OPAQUE_DIR)
                new_manual_entries.add(rel_path_from_opaque)
            elif status == "HAS_ALPHA":
                has_alpha += 1
            elif status == "ERROR":
                errors.append(result)

    stop_event.set()
    monitor_thread.join()

    #write_manual_moves_log(MANUAL_MOVES_LOG, new_manual_entries)

    print()
    print(f"[+] Moved {opaque} alpha-validated opaque/128 image(s) to '{OPAQUE_DIR}'")
    print(f"[+] Moved {opaque_manual} manually-forced opaque image(s) to '{OPAQUE_DIR}'")
    print(f"[+] Moved {has_alpha} image(s) with other alpha values to '{HAS_ALPHA_DIR}'")
    print(f"[+] Retained {len(kept_manual_entries)} still-valid tracked manual move entry(s).")
    print(f"[+] Removed {len(missing_entries)} missing tracked manual move entry(s).")
    print(f"[+] Wrote manual move manifest: {MANUAL_MOVES_LOG}")

    if errors:
        print(f"[!] {len(errors)} error(s) encountered:")
        for err in errors:
            print(f"    {err['source_path']}")
            print(f"      {err['error']}")

    if os.path.exists(NEXT_SCRIPT):
        print(f"\n[+] Running next script: {NEXT_SCRIPT}")
        try:
            subprocess.run([sys.executable, NEXT_SCRIPT], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] Next script failed with exit code {e.returncode}")
    else:
        print(f"[!] Next script not found: {NEXT_SCRIPT}")


if __name__ == "__main__":
    main()