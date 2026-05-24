"""Validate HoloUtopia district grid parity and city atlas placement."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse" and (parent / "main.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate HoloUtopia even district frames and city atlas placement.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    sys.path.insert(0, str(root)) if str(root) not in sys.path else None
    from holoutopia_town_blocks import city_atlas_path, load_city_atlas, town_data_dir, validate_town
    atlas_path = city_atlas_path(root)
    atlas = load_city_atlas(root)
    canonical_grid = list(atlas.get("canonical_grid_size") or [])
    canonical_block_size = int(atlas.get("block_size") or 0)
    errors: list[str] = []
    checked: list[dict[str, Any]] = []
    atlas_entries = atlas.get("towns") if isinstance(atlas.get("towns"), list) else []
    atlas_by_town: dict[str, dict[str, Any]] = {}
    slots: dict[tuple[int, int], str] = {}
    for entry in atlas_entries:
        if not isinstance(entry, dict):
            errors.append(f"{atlas_path}: town entries must be objects")
            continue
        town_id = str(entry.get("town_id", "")).strip()
        grid = entry.get("city_grid")
        if not town_id or not isinstance(grid, list) or len(grid) != 2:
            errors.append(f"{atlas_path}: invalid town entry {entry!r}")
            continue
        slot = (int(grid[0]), int(grid[1]))
        if slot in slots:
            errors.append(f"{atlas_path}: duplicated city_grid slot {slot} for {town_id} and {slots[slot]}")
        slots[slot] = town_id
        atlas_by_town[town_id] = entry
    towns_dir = town_data_dir(root)
    for path in sorted(towns_dir.glob("*.json")):
        if path.name == "town_schema.json":
            continue
        try:
            town = _load_json(path)
            validate_town(town, source_path=path)
            town_id = str(town.get("id", "")).strip()
            if town.get("grid_size") != canonical_grid:
                errors.append(f"{path}: grid_size {town.get('grid_size')} does not match {canonical_grid}")
            if int(town.get("block_size") or 0) != canonical_block_size:
                errors.append(f"{path}: block_size {town.get('block_size')} does not match {canonical_block_size}")
            frame = town.get("district_frame") or {}
            if frame.get("alignment_id") != atlas.get("alignment_id"):
                errors.append(f"{path}: district_frame alignment_id mismatch")
            if town_id not in atlas_by_town:
                errors.append(f"{path}: missing city_grid_atlas entry")
            checked.append({
                "id": town_id,
                "grid_size": town.get("grid_size"),
                "block_size": town.get("block_size"),
                "city_grid": atlas_by_town.get(town_id, {}).get("city_grid"),
                "blocks": len(town.get("town_blocks", [])),
                "schedule_nodes": len(town.get("schedule_nodes", [])),
            })
        except Exception as exc:
            errors.append(str(exc))
    checked_ids = {str(item.get("id")) for item in checked}
    for town_id in sorted(set(atlas_by_town) - checked_ids):
        errors.append(f"{atlas_path}: references missing town file {town_id}.json")
    summary = {"ok": not errors, "alignment_id": atlas.get("alignment_id"), "canonical_grid_size": canonical_grid, "checked_count": len(checked), "checked": checked, "errors": errors}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if errors:
            print("[holoutopia-grid] FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[holoutopia-grid] OK {len(checked)} town frame(s) aligned to {canonical_grid}")
            for item in checked:
                print(f"  - {item['id']}: city_grid={item['city_grid']} blocks={item['blocks']} nodes={item['schedule_nodes']}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
