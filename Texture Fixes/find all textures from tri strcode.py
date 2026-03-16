from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


CSV_PATH = Path(r"C:\Development\Git\MGS2-PS2-Textures\u - dumped from substance\mgs2_texture_map.csv")

CANCEL_INPUTS = {
    "",
    "q",
    "quit",
}


class ReturnToMenu(Exception):
    pass


def normalize(value: str) -> str:
    return value.strip().lower()


def is_cancel_input(value: str) -> bool:
    return normalize(value) in CANCEL_INPUTS


def safe_input(prompt: str) -> str:
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print("\n^C ignored. Returning to menu.\n")
        raise ReturnToMenu()


def normalize_strcode_input(value: str) -> str | None:
    value = value.strip()

    if len(value) == 6:
        return value

    if len(value) == 8:
        if value.startswith("00"):
            fixed = value[2:]
            print(f"Auto-corrected 8-character strcode to {fixed}")
            return fixed

        print("Warning: 8-character strcodes must start with '00'.")
        return None

    print("Warning: strcodes must be exactly 6 characters, or 8 characters starting with '00'.")
    return None


def load_texture_map(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows: list[dict[str, str]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith(";"):
                continue

            parts = next(csv.reader([raw_line]))
            if len(parts) < 4:
                continue

            texture_filename = parts[0].strip()
            stage = parts[1].strip()
            tri_strcode = parts[2].strip()
            texture_strcode = parts[3].strip()

            if not texture_filename:
                continue

            rows.append(
                {
                    "texture_filename": texture_filename,
                    "stage": stage,
                    "tri_strcode": tri_strcode,
                    "texture_strcode": texture_strcode,
                }
            )

    return rows


def build_indexes(
    rows: list[dict[str, str]],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[tuple[str, str], set[str]],
    dict[str, set[tuple[str, str]]],
]:
    by_tri: dict[str, set[str]] = defaultdict(set)
    by_texture: dict[str, set[str]] = defaultdict(set)
    by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in rows:
        texture_filename = row["texture_filename"]
        tri_strcode = normalize(row["tri_strcode"])
        texture_strcode = normalize(row["texture_strcode"])

        by_tri[tri_strcode].add(texture_filename)
        by_texture[texture_strcode].add(texture_filename)
        by_pair[(tri_strcode, texture_strcode)].add(texture_filename)
        by_name[normalize(texture_filename)].add((tri_strcode, texture_strcode))

    return by_tri, by_texture, by_pair, by_name


def print_header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_string_results(values: set[str]) -> None:
    sorted_values = sorted(values, key=str.lower)

    print()
    print(f"Count: {len(sorted_values)}")

    if not sorted_values:
        print("No results found.")
        return

    print()
    for value in sorted_values:
        print(f"  {value}")


def print_pair_results(values: set[tuple[str, str]]) -> list[tuple[str, str]]:
    sorted_values = sorted(values, key=lambda x: (x[0].lower(), x[1].lower()))

    print()
    print(f"Count: {len(sorted_values)}")

    if not sorted_values:
        print("No tri / texture strcode pairs found.")
        return sorted_values

    print()
    for index, (tri_strcode, texture_strcode) in enumerate(sorted_values, start=1):
        print(f"  {index}. tri_strcode={tri_strcode}, texture_strcode={texture_strcode}")

    return sorted_values


def print_collision_results(
    mapping: dict[object, set[str]],
    key_formatter,
    title: str,
) -> None:
    collisions: list[tuple[object, list[str]]] = []

    for key, values in mapping.items():
        if len(values) > 1:
            collisions.append((key, sorted(values, key=str.lower)))

    collisions.sort(key=lambda item: key_formatter(item[0]).lower())

    print()
    print(f"Count: {len(collisions)}")

    if not collisions:
        print(f"No {title} found.")
        return

    print()
    for key, values in collisions:
        print(key_formatter(key))
        for value in values:
            print(f"  {value}")
        print()


def print_name_to_pair_collisions(by_name: dict[str, set[tuple[str, str]]]) -> None:
    collisions: list[tuple[str, list[tuple[str, str]]]] = []

    for texture_name, pairs in by_name.items():
        if len(pairs) > 1:
            collisions.append((texture_name, sorted(pairs, key=lambda x: (x[0].lower(), x[1].lower()))))

    collisions.sort(key=lambda item: item[0].lower())

    print()
    print(f"Count: {len(collisions)}")

    if not collisions:
        print("No filenames mapping to multiple tri / texture strcode pairs found.")
        return

    print()
    for texture_name, pairs in collisions:
        print(texture_name)
        for tri_strcode, texture_strcode in pairs:
            print(f"  tri_strcode={tri_strcode}, texture_strcode={texture_strcode}")
        print()


def prompt_nonempty(prompt: str) -> str:
    while True:
        value = safe_input(prompt)

        if is_cancel_input(value):
            raise ReturnToMenu()

        value = value.strip()

        if value:
            return value

        print("Input cannot be empty.")


def prompt_strcode(prompt: str) -> str:
    while True:
        raw_value = safe_input(prompt)

        if is_cancel_input(raw_value):
            raise ReturnToMenu()

        normalized = normalize_strcode_input(raw_value.strip())

        if normalized is not None:
            return normalize(normalized)


def prompt_optional_selection(max_index: int) -> int | None:
    while True:
        value = safe_input(
            f"Select a tri entry number to list all textures in that tri "
            f"(1-{max_index}), or press Enter/q to return to menu: "
        )

        if is_cancel_input(value):
            raise ReturnToMenu()

        value = value.strip()

        if not value:
            raise ReturnToMenu()

        if not value.isdigit():
            print("Please enter a valid number.")
            continue

        index = int(value)

        if index < 1 or index > max_index:
            print("Selection out of range.")
            continue

        return index


def option_4_followup(
    pairs: list[tuple[str, str]],
    by_tri: dict[str, set[str]],
) -> None:
    if not pairs:
        return

    try:
        selection = prompt_optional_selection(len(pairs))
    except ReturnToMenu:
        return

    if selection is None:
        return

    selected_tri_strcode, _ = pairs[selection - 1]

    print_header(f"All Textures In Tri Strcode {selected_tri_strcode}")
    results = by_tri.get(selected_tri_strcode, set())
    print_string_results(results)


def menu_loop(
    by_tri: dict[str, set[str]],
    by_texture: dict[str, set[str]],
    by_pair: dict[tuple[str, str], set[str]],
    by_name: dict[str, set[tuple[str, str]]],
) -> None:
    while True:
        print_header("MGS2 Texture Map Lookup")
        print("1. Find unique textures from tri strcode")
        print("2. Find unique textures from texture strcode")
        print("3. Find unique textures from tri / texture strcode pair")
        print("4. Find all tri / texture strcode pairs containing texture")
        print("5. Find all tri / texture strcode pairs that map to multiple textures")
        print("6. Find all textures that map to multiple tri / texture strcode pairs")
        print("7. Exit")
        print()

        try:
            choice = safe_input("Select an option: ").strip()
        except ReturnToMenu:
            continue

        if choice == "1":
            try:
                print_header("Find Unique Textures From Tri Strcode")
                tri_strcode = prompt_strcode("Enter tri strcode: ")
                results = by_tri.get(tri_strcode, set())
                print_string_results(results)
            except ReturnToMenu:
                continue

        elif choice == "2":
            try:
                print_header("Find Unique Textures From Texture Strcode")
                texture_strcode = prompt_strcode("Enter texture strcode: ")
                results = by_texture.get(texture_strcode, set())
                print_string_results(results)
            except ReturnToMenu:
                continue

        elif choice == "3":
            try:
                print_header("Find Unique Textures From Tri / Texture Strcode Pair")
                tri_strcode = prompt_strcode("Enter tri strcode: ")
                texture_strcode = prompt_strcode("Enter texture strcode: ")
                results = by_pair.get((tri_strcode, texture_strcode), set())
                print_string_results(results)
            except ReturnToMenu:
                continue

        elif choice == "4":
            try:
                print_header("Find All Tri / Texture Strcode Pairs For Texture")
                texture_filename = prompt_nonempty("Enter texturename: ")
                results = by_name.get(normalize(texture_filename), set())
                sorted_pairs = print_pair_results(results)
                option_4_followup(sorted_pairs, by_tri)
            except ReturnToMenu:
                continue

        elif choice == "5":
            print_header("Find All Tri / Texture Strcode Pairs That Map To Multiple Filenames")
            print_collision_results(
                mapping=by_pair,
                key_formatter=lambda pair: f"tri_strcode={pair[0]}, texture_strcode={pair[1]}",
                title="tri / texture strcode pair collision(s)",
            )

        elif choice == "6":
            print_header("Find All Filenames That Map To Multiple Tri / Texture Strcode Pairs")
            print_name_to_pair_collisions(by_name)

        elif choice == "7":
            print("Exiting.")
            return

        else:
            print("\nInvalid option.")


def main() -> int:
    try:
        rows = load_texture_map(CSV_PATH)
    except Exception as exc:
        print(f"Failed to load CSV: {exc}")
        return 1

    if not rows:
        print("No usable rows were found in the CSV.")
        return 1

    by_tri, by_texture, by_pair, by_name = build_indexes(rows)

    print(f"Loaded {len(rows)} rows from:")
    print(f"  {CSV_PATH}")

    menu_loop(by_tri, by_texture, by_pair, by_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())