"""Validate HoloUtopia is filled as a complete 3x3 city atlas."""
from __future__ import annotations
import json, sys
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse" and (parent / "holoutopia_town_blocks.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import load_city_atlas, load_town
    atlas = load_city_atlas(root)
    entries = [e for e in atlas.get('towns', []) if isinstance(e, dict)]
    required = {(x, y) for x in range(3) for y in range(3)}
    slots = {}
    errors = []
    for e in entries:
        town_id = str(e.get('town_id'))
        grid = e.get('city_grid')
        if not isinstance(grid, list) or len(grid) != 2:
            errors.append(f'{town_id}: invalid city_grid')
            continue
        slot = (int(grid[0]), int(grid[1]))
        if slot in slots:
            errors.append(f'duplicate slot {slot}: {town_id} and {slots[slot]}')
        slots[slot] = town_id
        town = load_town(town_id, root)
        if town.get('grid_size') != [10, 8]:
            errors.append(f'{town_id}: grid_size must be [10, 8]')
    missing = sorted(required - set(slots))
    extra = sorted(set(slots) - required)
    if missing:
        errors.append(f'missing 3x3 slots: {missing}')
    if extra:
        errors.append(f'extra slots outside 3x3: {extra}')
    result = {'ok': not errors, 'district_count': len(entries), 'filled_slots': {str(k): v for k, v in sorted(slots.items())}, 'errors': errors}
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2

if __name__ == '__main__':
    raise SystemExit(main())
