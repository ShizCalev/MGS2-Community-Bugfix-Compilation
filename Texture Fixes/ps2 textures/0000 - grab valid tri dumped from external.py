import os
import shutil
import subprocess
import sys
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ==========================================================
# CONFIGURATION
# ==========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

SUBMODULE_PATH = os.path.join(REPO_ROOT, "external", "MGS2-PS2-Textures")
MASTER_COLLECTION_DIR = os.path.join(SUBMODULE_PATH, "Tri-Dumped", "Master Collection")

DEST_DIR = os.path.join(REPO_ROOT, "Texture Fixes", "ps2 textures")
FOLLOWUP_SCRIPT = os.path.join(SCRIPT_DIR, "0001 - bring in missing pcsx2 dumped.py")

THREADS = os.cpu_count() or 12
BRANCHES = ["main", "master"]

print_lock = Lock()

# ==========================================================
# UTILITIES
# ==========================================================
def run(cmd, cwd=None, check=True):
    print(f"\n$ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, check=check)
    except subprocess.CalledProcessError as e:
        print(f"[!] Command failed: {' '.join(cmd)} (exit code {e.returncode})")
        if check:
            sys.exit(e.returncode)


def git_output(cmd, cwd):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip()


def submodule_exists():
    if not os.path.isdir(SUBMODULE_PATH):
        print(f"[!] Submodule folder missing: {SUBMODULE_PATH}")
        return False

    git_ref = os.path.join(SUBMODULE_PATH, ".git")
    if os.path.exists(git_ref):
        return True

    print(f"[!] Submodule folder exists but missing .git reference: {git_ref}")
    return False


def calc_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def delete_legacy_tgas(dest_dir):
    deleted = 0
    errors = 0

    if not os.path.isdir(dest_dir):
        return deleted, errors

    for root, _, files in os.walk(dest_dir):
        for filename in files:
            if not filename.lower().endswith(".tga"):
                continue

            path = os.path.join(root, filename)
            try:
                os.remove(path)
                deleted += 1
                with print_lock:
                    print(f"[Deleted legacy TGA] {path}")
            except Exception as e:
                errors += 1
                with print_lock:
                    print(f"[Error deleting legacy TGA] {path}: {e}")

    return deleted, errors

# ==========================================================
# FILE ENUMERATION
# ==========================================================
def get_flat_png_map(folder):
    """
    Return a map of lowercase filename -> full path for a flat folder of PNGs.
    Throws if duplicate lowercase filenames are encountered.
    """
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Folder not found: {folder}")

    result = {}

    for filename in os.listdir(folder):
        full_path = os.path.join(folder, filename)

        if not os.path.isfile(full_path):
            continue
        if not filename.lower().endswith(".png"):
            continue

        key = filename.lower()
        if key in result:
            raise RuntimeError(f"Duplicate lowercase filename found in flat folder: {filename}")

        result[key] = full_path

    return result


def get_dest_png_map(dest_dir):
    """
    Return a map of lowercase filename -> full path for all PNGs in DEST_DIR recursively.
    Throws on duplicate lowercase filenames anywhere under DEST_DIR.
    """
    result = {}

    if not os.path.isdir(dest_dir):
        return result

    for root, _, files in os.walk(dest_dir):
        for filename in files:
            if not filename.lower().endswith(".png"):
                continue

            full_path = os.path.join(root, filename)
            key = filename.lower()

            if key in result:
                raise RuntimeError(
                    "Duplicate lowercase filename found in destination tree:\n"
                    f"  {result[key]}\n"
                    f"  {full_path}"
                )

            result[key] = full_path

    return result


# ==========================================================
# HASHING
# ==========================================================
def hash_file_for_index(path):
    try:
        return path, calc_sha1(path)
    except Exception as e:
        with print_lock:
            print(f"[!] Failed to hash {path}: {e}")
        return path, None


def build_hash_map(paths):
    hash_map = {}

    if not paths:
        return hash_map

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(hash_file_for_index, path) for path in paths]
        for fut in as_completed(futures):
            path, sha1 = fut.result()
            hash_map[path] = sha1

    return hash_map


# ==========================================================
# SYNC ACTIONS
# ==========================================================
def delete_outdated_dest_files(source_map, dest_map):
    deleted = 0
    errors = 0

    for filename, dest_path in sorted(dest_map.items()):
        if filename in source_map:
            continue

        try:
            os.remove(dest_path)
            deleted += 1
            with print_lock:
                print(f"[Deleted] {filename}")
        except Exception as e:
            errors += 1
            with print_lock:
                print(f"[Error deleting] {dest_path}: {e}")

    return deleted, errors


def sync_file(filename, src_path, dest_dir, dest_map, source_hashes, dest_hashes):
    dest_path = os.path.join(dest_dir, filename)

    src_hash = source_hashes.get(src_path)
    if src_hash is None:
        return "error"

    existing_dest_path = dest_map.get(filename)
    if existing_dest_path is not None:
        dest_hash = dest_hashes.get(existing_dest_path)
        if dest_hash is None:
            return "error"

        if dest_hash == src_hash:
            return "skipped"

        try:
            if os.path.normcase(os.path.normpath(existing_dest_path)) != os.path.normcase(os.path.normpath(dest_path)):
                os.remove(existing_dest_path)

            shutil.copy2(src_path, dest_path)
            with print_lock:
                print(f"[Replaced] {filename}")
            return "replaced"
        except Exception as e:
            with print_lock:
                print(f"[Error replacing] {filename}: {e}")
            return "error"

    try:
        shutil.copy2(src_path, dest_path)
        with print_lock:
            print(f"[Copied] {filename}")
        return "copied"
    except Exception as e:
        with print_lock:
            print(f"[Error copying] {filename}: {e}")
        return "error"


def sync_source_to_dest(source_map, dest_dir, dest_map, source_hashes, dest_hashes):
    stats = {"copied": 0, "replaced": 0, "skipped": 0, "error": 0}

    os.makedirs(dest_dir, exist_ok=True)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = []
        for filename, src_path in source_map.items():
            futures.append(
                executor.submit(
                    sync_file,
                    filename,
                    src_path,
                    dest_dir,
                    dest_map,
                    source_hashes,
                    dest_hashes,
                )
            )

        for fut in as_completed(futures):
            result = fut.result()
            if result in stats:
                stats[result] += 1

    return stats


def remove_empty_dirs_under(root_dir):
    if not os.path.isdir(root_dir):
        return 0

    removed = 0

    for current_root, dirnames, _ in os.walk(root_dir, topdown=False):
        for dirname in dirnames:
            full_path = os.path.join(current_root, dirname)
            try:
                if not os.listdir(full_path):
                    os.rmdir(full_path)
                    removed += 1
                    with print_lock:
                        print(f"[Removed empty dir] {full_path}")
            except Exception:
                pass

    return removed


# ==========================================================
# MAIN
# ==========================================================
def main():
    print("=== [ MGS2-PS2-Textures Submodule Sync ] ===\n")
    print(f"[+] Repo root: {REPO_ROOT}")
    print(f"[+] Submodule: {SUBMODULE_PATH}")
    print(f"[+] Source: {MASTER_COLLECTION_DIR}")
    print(f"[+] Destination: {DEST_DIR}\n")

    if not os.path.isdir(REPO_ROOT):
        print(f"[!] Repo root not found: {REPO_ROOT}")
        sys.exit(1)

    run(["git", "submodule", "init"], cwd=REPO_ROOT)
    run(["git", "submodule", "update", "--recursive", "--remote", "--init"], cwd=REPO_ROOT)

    if not submodule_exists():
        print(f"[!] Submodule directory not properly detected: {SUBMODULE_PATH}")
        sys.exit(1)

    old_commit = git_output(["git", "rev-parse", "HEAD"], cwd=SUBMODULE_PATH)
    print(f"[+] Current submodule commit: {old_commit}")

    print("\n[+] Fetching latest commits for submodule...")
    run(["git", "fetch", "origin"], cwd=SUBMODULE_PATH)

    checked_out = False
    for branch in BRANCHES:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=SUBMODULE_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            print(f"[+] Checking out branch: {branch}")
            run(["git", "checkout", branch], cwd=SUBMODULE_PATH)
            run(["git", "pull", "origin", branch], cwd=SUBMODULE_PATH)
            checked_out = True
            break

    if not checked_out:
        print("[!] No main/master branch found - staying on current HEAD.")

    print("[+] Updating nested submodules (if any)...")
    run(["git", "submodule", "update", "--recursive", "--remote", "--init"], cwd=SUBMODULE_PATH)

    print("\n[+] Enumerating source PNGs...")
    source_map = get_flat_png_map(MASTER_COLLECTION_DIR)
    print(f"[+] Source PNG count: {len(source_map)}")

    print("[+] Enumerating destination PNGs...")
    dest_map = get_dest_png_map(DEST_DIR)
    print(f"[+] Destination PNG count: {len(dest_map)}")

    print("\n[+] Hashing source PNGs...")
    source_hashes = build_hash_map(list(source_map.values()))

    print("[+] Hashing destination PNGs...")
    dest_hashes = build_hash_map(list(dest_map.values()))

    print("\n[+] Deleting outdated destination PNGs...")
    deleted, delete_errors = delete_outdated_dest_files(source_map, dest_map)

    print("[+] Syncing source PNGs into destination...")
    sync_stats = sync_source_to_dest(
        source_map,
        DEST_DIR,
        dest_map,
        source_hashes,
        dest_hashes,
    )
    
    print("[+] Deleting legacy TGA files under destination...")
    legacy_tgas_deleted, legacy_tga_errors = delete_legacy_tgas(DEST_DIR)

    print("[+] Removing empty directories under destination...")
    empty_dirs_removed = remove_empty_dirs_under(DEST_DIR)

    print("\n[+] Sync summary:")
    print(f"    Copied:   {sync_stats['copied']}")
    print(f"    Replaced: {sync_stats['replaced']}")
    print(f"    Skipped:  {sync_stats['skipped']}")
    print(f"    Deleted:  {deleted}")
    print(f"    Errors:   {sync_stats['error'] + delete_errors}")
    print(f"    Empty dirs removed: {empty_dirs_removed}")
    print(f"    Legacy TGAs deleted: {legacy_tgas_deleted}")
    print(f"    Errors:   {sync_stats['error'] + delete_errors + legacy_tga_errors}")

    print("\n[+] Final submodule status:")
    run(["git", "status"], cwd=SUBMODULE_PATH)

    print("\n✅ Submodule fully synced and ps2 textures updated in:")
    print(f"   {DEST_DIR}\n")

    print(f"[+] Running follow-up script: {FOLLOWUP_SCRIPT}")
    if os.path.exists(FOLLOWUP_SCRIPT):
        try:
            subprocess.run([sys.executable, FOLLOWUP_SCRIPT], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] Follow-up script failed with exit code {e.returncode}")
        except Exception as e:
            print(f"[!] Error launching follow-up script: {e}")
    else:
        print(f"[!] Follow-up script not found: {FOLLOWUP_SCRIPT}")


if __name__ == "__main__":
    main()