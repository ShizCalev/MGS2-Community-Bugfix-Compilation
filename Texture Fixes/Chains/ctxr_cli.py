from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = {".png", ".tga"}
TRAILING_PADDING = 28


def convert(ctxr_path: str, image_path: str) -> str:
    with open(ctxr_path, "rb") as f:
        ctxr_header = bytearray(f.read(132))

    with Image.open(image_path) as image:
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        width, height = image.size
        pixel_data = image.tobytes("raw", "BGRA")

    struct.pack_into(">H", ctxr_header, 8, width)
    struct.pack_into(">H", ctxr_header, 10, height)
    struct.pack_into(">I", ctxr_header, 0x80, len(pixel_data))
    struct.pack_into(">B", ctxr_header, 0x26, 1)

    output_path = str(Path(image_path).with_suffix(".ctxr"))

    with open(output_path, "wb") as f:
        f.write(ctxr_header)
        f.write(pixel_data)
        f.write(b"\x00" * TRAILING_PADDING)

    return output_path


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {os.path.basename(sys.argv[0])} <input.ctxr> <image.png|image.tga>")
        raise SystemExit(1)

    ctxr_path = sys.argv[1]
    image_path = sys.argv[2]

    ext = Path(image_path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(f"Error: Unsupported image format '{ext}'. Supported: {supported}")
        raise SystemExit(1)

    if not os.path.isfile(ctxr_path):
        print(f"Error: CTXR file not found: {ctxr_path}")
        raise SystemExit(1)

    if not os.path.isfile(image_path):
        print(f"Error: Image file not found: {image_path}")
        raise SystemExit(1)

    try:
        output = convert(ctxr_path, image_path)
        print(f"Done: {output}")
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()