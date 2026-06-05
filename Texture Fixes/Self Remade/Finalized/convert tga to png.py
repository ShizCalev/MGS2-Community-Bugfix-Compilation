from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def pause_and_exit(code: int = 0) -> None:
    try:
        input("Press ENTER to exit...")
    except EOFError:
        pass
    raise SystemExit(code)


def main() -> None:
    script_dir = Path(sys.argv[0]).resolve().parent

    tga_files = list(script_dir.glob("*.tga")) + list(script_dir.glob("*.TGA"))

    if not tga_files:
        print("No TGA files found.")
        pause_and_exit(0)

    converted = 0
    deleted = 0
    skipped = 0
    delete_failed = 0

    for tga_path in tga_files:
        png_path = tga_path.with_suffix(".png")

        if png_path.exists():
            print(f"SKIP (exists): {png_path.name}")
            skipped += 1
            continue

        try:
            with Image.open(tga_path) as img:
                # Preserve alpha if present
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")

                img.save(png_path, format="PNG", optimize=False)

            print(f"OK: {tga_path.name} -> {png_path.name}")
            converted += 1

            try:
                tga_path.unlink()
                print(f"DELETED: {tga_path.name}")
                deleted += 1
            except Exception as e:
                print(f"DELETE ERROR: {tga_path.name} ({e})")
                delete_failed += 1

        except Exception as e:
            print(f"ERROR: {tga_path.name} ({e})")

    print("\nDone.")
    print(f"Converted:     {converted}")
    print(f"Deleted TGAs:  {deleted}")
    print(f"Delete failed: {delete_failed}")
    print(f"Skipped:       {skipped}")

    pause_and_exit(0)


if __name__ == "__main__":
    main()
