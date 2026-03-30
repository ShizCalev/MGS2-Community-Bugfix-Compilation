from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS = [
    Path(r"C:\Development\Git\Afevis-MGS2-Bugfix-Compilation\Build_Dist_Folders.py"),
    Path(r"C:\Development\Git\MGS2-Demastered-Substance-Edition\Build_Dist_Folders.py"),
    Path(r"C:\Development\Git\MGS2-Upscaled-UI-Textures\Build_Dist_Folders.py"),
]


def run_script(script: Path) -> None:
    print(f"\n[RUN] {script}")

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            check=True
        )

        print(f"[OK] {script}")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {script}")
        print(f"Exit code: {e.returncode}")
        input("Press Enter to continue to the next script...")


def main() -> None:
    for script in SCRIPTS:
        #run_script(script)

    print("\nAll scripts finished.")


if __name__ == "__main__":
    main()