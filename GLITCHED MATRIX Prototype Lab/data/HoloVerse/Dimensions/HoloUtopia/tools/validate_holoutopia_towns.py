"""Validate authored HoloUtopia town-block JSON files.

Run from repo root or data/HoloVerse:

    python data/HoloVerse/tools/validate_holoutopia_towns.py

The validator intentionally avoids Panda3D. It verifies the safe-edit JSON lane
for town blocks, portals, roads, schedule nodes, patrol loops, and starter NPC
slots before the runtime tries to render or simulate them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse" and (parent / "main.py").exists():
            return parent
    # Patch-only folder fallback.
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def _import_runtime(root: Path):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import HoloUtopiaTownError, town_data_dir, validate_town

    return HoloUtopiaTownError, town_data_dir, validate_town


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: JSON parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate authored HoloUtopia town-block JSON files.")
    parser.add_argument("--town", default="", help="Validate one town id without .json. Defaults to all towns.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    args = parser.parse_args(argv)

    root = _find_holoverse_root()
    HoloUtopiaTownError, town_data_dir, validate_town = _import_runtime(root)
    towns_dir = town_data_dir(root)
    if not towns_dir.exists():
        print(f"[holoutopia] FAIL town data folder missing: {towns_dir}")
        return 2

    if args.town:
        paths = [towns_dir / f"{args.town}.json"]
    else:
        paths = sorted(path for path in towns_dir.glob("*.json") if path.name != "town_schema.json")
    errors: list[str] = []
    checked: list[dict[str, Any]] = []

    for path in paths:
        try:
            town = _load_json(path)
            validate_town(town, source_path=path)
            checked.append({
                "id": town.get("id"),
                "path": str(path),
                "blocks": len(town.get("town_blocks", [])),
                "roads": len(town.get("roads", [])),
                "schedule_nodes": len(town.get("schedule_nodes", [])),
                "portal_count": len(town.get("portal_hub", {}).get("portals", [])),
            })
        except (ValueError, HoloUtopiaTownError) as exc:
            errors.append(str(exc))

    summary = {
        "ok": not errors,
        "towns_dir": str(towns_dir),
        "checked_count": len(checked),
        "checked": checked,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if errors:
            print("[holoutopia] FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[holoutopia] OK validated {len(checked)} town file(s)")
            for item in checked:
                print(
                    f"  - {item['id']}: {item['blocks']} blocks, {item['roads']} roads, "
                    f"{item['schedule_nodes']} schedule nodes, {item['portal_count']} portals"
                )
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
