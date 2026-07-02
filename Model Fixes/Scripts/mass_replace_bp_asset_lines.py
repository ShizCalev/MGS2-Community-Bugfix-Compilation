from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os


ROOT_FOLDER = Path(__file__).resolve().parent
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 4)

ASSETS = [
    # Texture path, tri strcode, texture strcode
    ("textures/flatlist/null_msk.bmp.ctxr", "0055aab1", "00b7e31e"),
    #("textures/flatlist/wig1_alp_ovl.bmp.ctxr", "00899c71", "0045997c"),
    #("textures/flatlist/wig2_alp_ovl.bmp.ctxr", "00899c71", "0046997c"),

    # Asset path, file hash
    #("assets/evm/us/iro_glass_black_mh_mt_stage_r_plt0_r.cmdl", "00df6ff2"),
    #("assets/evm/us/iro_glass_mh_mt.cmdl", "001560de"),
    #("assets/evm/us/rai_glass_mh_mt.cmdl", "003300e0"),
    #("assets/kms/us/aks_amo_stage_r_plt0_r.cmdl", "00612b2c"),
]


def get_region_and_stage(bp_assets_path: Path) -> tuple[str, str]:
    relative_path = bp_assets_path.relative_to(ROOT_FOLDER)
    parts = relative_path.parts

    if len(parts) < 4 or parts[1].lower() != "stage":
        raise ValueError(
            f"Expected path like region\\stage\\stage_name\\bp_assets*.txt: "
            f"{relative_path}"
        )

    region = parts[0]
    stage = parts[2]

    return region, stage


def build_asset_line(
    asset: tuple[str, ...],
    region: str,
    stage: str,
) -> str:
    source_path = asset[0]
    source_filename = source_path.rsplit("/", 1)[-1]
    extension = Path(source_filename).suffix

    if source_path.startswith("textures/flatlist/"):
        if len(asset) != 3:
            raise ValueError(
                f"Texture entry requires a parent hash and file hash: {asset}"
            )

        parent_hash = asset[1]
        file_hash = asset[2]

        return (
            f"{source_path},"
            f"stage/{stage}/resident/{source_filename},"
            f"{region}/stage/{stage}/resident/"
            f"{parent_hash}/{file_hash}{extension}"
        )

    if source_path.startswith("assets/"):
        if len(asset) != 2:
            raise ValueError(
                f"Asset entry requires one file hash: {asset}"
            )

        file_hash = asset[1]

        return (
            f"{source_path},"
            f"us/stage/{stage}/resident/{file_hash}{extension},"
            f"{region}/stage/{stage}/resident/{file_hash}{extension}"
        )

    raise ValueError(f"Unsupported asset path: {source_path}")


def process_bp_assets(bp_assets_path: Path) -> tuple[Path, int]:
    region, stage = get_region_and_stage(bp_assets_path)

    output_lines = [
        build_asset_line(asset, region, stage)
        for asset in ASSETS
    ]

    output_text = "\r\n".join(output_lines)

    if output_lines:
        output_text += "\r\n"

    with bp_assets_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        file.write(output_text)

    return bp_assets_path, len(output_lines)


def main() -> None:
    bp_assets_files = [
        path
        for path in ROOT_FOLDER.rglob("bp_assets*.txt")
        if path.is_file()
    ]

    if not bp_assets_files:
        print("No bp_assets TXT files found.")
        return

    processed_count = 0
    failed_count = 0

    print(f"Generating {len(bp_assets_files)} bp_assets files...")
    print()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_bp_assets, bp_assets_path): bp_assets_path
            for bp_assets_path in bp_assets_files
        }

        for future in as_completed(futures):
            bp_assets_path = futures[future]

            try:
                path, line_count = future.result()
                processed_count += 1

                print(
                    f"[GENERATED] {path.relative_to(ROOT_FOLDER)} "
                    f"Lines: {line_count}"
                )

            except Exception as exception:
                failed_count += 1
                print(f"[FAILED] {bp_assets_path}: {exception}")

    print()
    print(f"Processed: {processed_count}")
    print(f"Failed: {failed_count}")


if __name__ == "__main__":
    main()