#!/usr/bin/env python3

import os
import subprocess
import tempfile
from pathlib import Path

MAX_MIB = 8000
MAX_BYTES = MAX_MIB * 1024 * 1024
COMMIT_MESSAGE = "RECONVERT"

def run(args: list[str], check: bool = True) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed:\n"
            f"{' '.join(args)}\n\n"
            f"{result.stderr}"
        )

    return result.stdout.strip()

def git(args: list[str], check: bool = True) -> str:
    return run(["git", *args], check)

def get_ctxr_files() -> list[str]:
    output = git([
        "ls-files",
        "--others",
        "--modified",
        "--exclude-standard",
        "--",
        "*.ctxr"
    ])

    return [line.strip() for line in output.splitlines() if line.strip()]

def get_file_size(file: str) -> int:
    path = Path(file)

    if not path.exists():
        return 0

    return path.stat().st_size

def git_add_many(files: list[str]) -> None:
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp:
            temp_path = temp.name

            for file in files:
                temp.write(file.encode("utf-8"))
                temp.write(b"\0")

        git([
            "add",
            f"--pathspec-from-file={temp_path}",
            "--pathspec-file-nul"
        ])

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def main() -> None:
    files = get_ctxr_files()

    if not files:
        print("No changed or untracked .ctxr files found.")
        return

    batch: list[str] = []
    batch_size = 0

    for file in files:
        size = get_file_size(file)

        if size > MAX_BYTES:
            print(f"Skipping oversized file: {file}")
            print(f"Size: {size / 1024 / 1024:.1f} MiB")
            print("This single file is larger than the 1900 MiB cap.")
            continue

        if batch and batch_size + size > MAX_BYTES:
            break

        batch.append(file)
        batch_size += size

    if not batch:
        print("No .ctxr files could fit into a commit.")
        return

    git(["reset"])

    git_add_many(batch)

    staged = git(["diff", "--cached", "--name-only"])
    if not staged.strip():
        print("Nothing staged.")
        return

    git(["commit", "-m", COMMIT_MESSAGE])

    print(f"Created one commit: {COMMIT_MESSAGE}")
    print(f"Files committed: {len(batch)}")
    print(f"Approx source file size: {batch_size / 1024 / 1024:.1f} MiB")

    remaining = len(files) - len(batch)
    if remaining > 0:
        print(f"Remaining .ctxr files for next run: {remaining}")

if __name__ == "__main__":
    main()