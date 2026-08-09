import os
import csv
import hashlib
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

ROOT = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(ROOT, "launcher.exe")
OUTPUT = os.path.join(ROOT, "file_hashes.csv")

THREADS = min(32, (os.cpu_count() or 1) * 4)


def sha1_file(path):
    sha1 = hashlib.sha1()

    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha1.update(chunk)

    return sha1.hexdigest()


def process_file(path):
    stat = os.stat(path)

    return (
        os.path.relpath(path, ROOT),
        datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        sha1_file(path),
    )


def main():
    print("This tool will recursively log all files to a CSV, including their path, modified time, and SHA-1 hash.")
    print("Once finished, we'll open the completed CSV and Pastebin.com.")
    print("You'll then need to copy and paste the full contents of the CSV into Pastebin.")
    print()
    print("This may cause heavy disk activity while the files are being read. No existing files will be modified.")
    print()

    if not os.path.isfile(LAUNCHER):
        print("ERROR: launcher.exe was not found beside this script.")
        print()
        print("Place this script directly beside launcher.exe and run it again.")
        print()
        input("Press Enter to close this window...")
        return

    files = []

    for dirpath, _, filenames in os.walk(ROOT):
        for filename in filenames:
            path = os.path.join(dirpath, filename)

            if os.path.abspath(path) == os.path.abspath(OUTPUT):
                continue

            files.append(path)

    results = []

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {
            executor.submit(process_file, path): path
            for path in files
        }

        with tqdm(
            total=len(futures),
            desc="Hashing",
            unit="file",
            dynamic_ncols=True
        ) as progress:
            for future in as_completed(futures):
                path = futures[future]

                try:
                    results.append(future.result())
                except Exception as e:
                    tqdm.write(f"FAILED: {path}: {e}")

                progress.update(1)

    results.sort(key=lambda x: x[0].lower())

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "modified", "sha1"])
        writer.writerows(results)

    print()
    print(f"Done. Logged {len(results):,} files to:")
    print(OUTPUT)
    print()
    print("The CSV and Pastebin.com will now be opened.")
    print()
    print("1. Copy the FULL contents of the CSV.")
    print("2. Paste them into the large text box on Pastebin.")
    print('3. Click "Create New Paste" at the bottom of the page.')
    print()

    os.startfile(OUTPUT)
    webbrowser.open("https://pastebin.com/")

    input("Press Enter to close this window...")


if __name__ == "__main__":
    main()

