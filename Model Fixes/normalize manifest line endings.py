from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TARGET_NAMES = {"bp_assets.txt", "manifest.txt"}
ROOT_DIR = Path(__file__).resolve().parent
MAX_WORKERS = min(32, (os.cpu_count() or 8) * 2)


def collect_text_lines(raw_text: str) -> list[str]:
    lines = raw_text.splitlines()

    text_lines: list[str] = []
    for line in lines:
        if line.strip():
            text_lines.append(line)

    return text_lines


def build_normalized_content(text_lines: list[str]) -> bytes:
    if not text_lines:
        return b""

    parts: list[str] = []

    # First line must contain text and end with CR
    parts.append(text_lines[0])
    parts.append("\r")

    # Later text lines: blank CRLF line before them, and they end with CR
    for line in text_lines[1:]:
        parts.append("\r\n")
        parts.append(line)
        parts.append("\r")

    # Final blank line
    parts.append("\r\n")

    return "".join(parts).encode("utf-8")


def normalize_file(path: Path) -> tuple[Path, bool]:
    original_bytes = path.read_bytes()

    try:
        original_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        original_text = original_bytes.decode("utf-8-sig")

    text_lines = collect_text_lines(original_text)
    normalized_bytes = build_normalized_content(text_lines)

    if original_bytes == normalized_bytes:
        return path, False

    path.write_bytes(normalized_bytes)
    return path, True


def main() -> None:
    matched_files = [
        p for p in ROOT_DIR.rglob("*")
        if p.is_file() and p.name.lower() in TARGET_NAMES
    ]

    if not matched_files:
        print("No bp_assets.txt or manifest.txt files found.")
        return

    updated = 0
    unchanged = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(normalize_file, p): p for p in matched_files}

        for future in as_completed(futures):
            path = futures[future]

            try:
                _, did_update = future.result()

                if did_update:
                    updated += 1
                    print(f"[UPDATED] {path}")
                else:
                    unchanged += 1

            except Exception as ex:
                failed += 1
                print(f"[FAILED] {path} :: {ex}")

    print()
    print(f"Workers: {MAX_WORKERS}")
    print(f"Scanned: {len(matched_files)}")
    print(f"Updated: {updated}")
    print(f"Unchanged: {unchanged}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()