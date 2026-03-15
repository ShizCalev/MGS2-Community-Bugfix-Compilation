from __future__ import annotations

import csv
import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "git_sha1_mismatches.csv"

MAX_WORKERS = max(4, (os.cpu_count() or 4) * 2)
READ_SIZE = 1024 * 1024


def run_git(repo: Path, args: list[str], text: bool = False):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )


def repo_root(start: Path) -> Path:
    r = run_git(start, ["rev-parse", "--show-toplevel"], text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return Path(r.stdout.strip())


def tracked_files(repo: Path) -> list[str]:
    r = run_git(repo, ["ls-files", "-z"])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore"))

    data = r.stdout
    return [x.decode("utf-8", "surrogateescape") for x in data.split(b"\0") if x]


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()

    with path.open("rb") as f:
        while True:
            chunk = f.read(READ_SIZE)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def head_sha1(repo: Path, rel: str) -> str:
    r = run_git(repo, ["show", f"HEAD:{rel}"])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore"))
    return sha1_bytes(r.stdout)


def check(repo: Path, rel: str):
    path = repo / rel

    try:
        committed = head_sha1(repo, rel)

        if not path.exists():
            return (rel, "missing", "", committed)

        if not path.is_file():
            return (rel, "not_file", "", committed)

        working = sha1_file(path)

        if working != committed:
            return (rel, "mismatch", working, committed)

        return None

    except Exception as e:
        return (rel, "error", "", str(e))


def main():
    try:
        repo = repo_root(SCRIPT_DIR)
    except Exception as e:
        print(e)
        return 1

    files = tracked_files(repo)

    print("Repo:", repo)
    print("Tracked files:", len(files))
    print("Threads:", MAX_WORKERS)
    print()

    results = []
    done = 0
    total = len(files)

    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        futures = {pool.submit(check, repo, f): f for f in files}

        for f in as_completed(futures):
            done += 1
            r = f.result()

            if r:
                results.append(r)
                print(f"[{done}/{total}] {r[1]}: {r[0]}")
            elif done % 250 == 0 or done == total:
                print(f"[{done}/{total}] checked")

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "status", "working_sha1", "head_sha1"])
        w.writerows(sorted(results))

    print()
    print("Done")
    print("Mismatches:", len(results))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    sys.exit(main())