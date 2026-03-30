from __future__ import annotations

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


STEMS_TXT = Path(
    r"C:\Development\Git\MGS2-PS2-Textures\Tri-Dumped\Master Collection\Metadata\mgs2_mc_bp_remade_textures.txt"
)

SRC_DIR = Path(
    r"G:\Steam\steamapps\common\MGS2\textures\flatlist\_win"
)

DST_DIR = Path(
    r"C:\Users\cmkoo\OneDrive\Desktop\New folder (2)"
)

EXT = ".ctxr"
WORKERS = min(32, (os.cpu_count() or 8) * 2)


_print_lock = threading.Lock()


def read_stems(path: Path) -> list[str]:
    stems: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            stems.append(s)
    return stems


def copy_one(stem: str) -> tuple[str, bool, str]:
    src = SRC_DIR / f"{stem}{EXT}"
    if not src.is_file():
        return (stem, False, "missing")

    dst = DST_DIR / src.name
    shutil.copy2(src, dst)
    return (stem, True, "")


def main() -> None:
    if not STEMS_TXT.is_file():
        raise FileNotFoundError(f"Missing stems txt: {STEMS_TXT}")

    if not SRC_DIR.is_dir():
        raise FileNotFoundError(f"Missing source dir: {SRC_DIR}")

    DST_DIR.mkdir(parents=True, exist_ok=True)

    stems = read_stems(STEMS_TXT)

    copied = 0
    missing: list[str] = []
    failed: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(copy_one, stem) for stem in stems]

        done = 0
        total = len(futures)

        for fut in as_completed(futures):
            stem, ok, reason = fut.result()

            if ok:
                copied += 1
            else:
                if reason == "missing":
                    missing.append(stem)
                else:
                    failed.append((stem, reason))

            done += 1
            if done % 200 == 0 or done == total:
                with _print_lock:
                    print(f"{done}/{total} done | copied={copied} | missing={len(missing)} | failed={len(failed)}")

    print("\nSummary")
    print(f"Stems in list: {len(stems)}")
    print(f"Copied: {copied}")
    print(f"Missing: {len(missing)}")
    print(f"Failed: {len(failed)}")

    if missing:
        missing_txt = DST_DIR / "missing_ctxr_stems.txt"
        with missing_txt.open("w", encoding="utf-8", newline="\n") as f:
            for stem in sorted(set(missing)):
                f.write(stem + "\n")
        print(f"Wrote missing stems to: {missing_txt}")

    if failed:
        failed_txt = DST_DIR / "failed_ctxr_copies.txt"
        with failed_txt.open("w", encoding="utf-8", newline="\n") as f:
            for stem, reason in sorted(set(failed)):
                f.write(f"{stem}\t{reason}\n")
        print(f"Wrote failed copies to: {failed_txt}")


if __name__ == "__main__":
    main()
