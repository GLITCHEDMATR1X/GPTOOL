#!/usr/bin/env python3
"""Validate HoloUtopia procedural visual model-kit profiles."""
from __future__ import annotations

import json
from pathlib import Path
import sys

def _find_holoutopia_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoutopia", "holoverse"} and (parent / "main.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")

ROOT = _find_holoutopia_root()
UTOPIA = ROOT.parent / "database" / "utopia"
CATALOG = UTOPIA / "model_kit" / "visual_model_kit_catalog.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fail(msg: str) -> None:
    raise SystemExit(f"validate_holoutopia_visual_model_profiles failed: {msg}")


def validate_profile(profile: dict, *, source: Path, item_id: str, legal_kits: set[str]) -> None:
    if not isinstance(profile, dict):
        fail(f"{source.name}:{item_id} missing visual_model_profile")
    kit = str(profile.get("kit_id", "")).strip()
    if kit not in legal_kits:
        fail(f"{source.name}:{item_id} unknown kit_id {kit!r}")
    if str(profile.get("interior_visibility", "")).strip() != "solid_until_selected":
        fail(f"{source.name}:{item_id} must use solid_until_selected interior visibility")
    if not bool(profile.get("purpose_driven", False)):
        fail(f"{source.name}:{item_id} must be purpose_driven=true")
    if str(profile.get("silhouette", "")).strip() not in {"procedural_district_model_v1", "procedural_residential_model_v1"}:
        fail(f"{source.name}:{item_id} has invalid silhouette {profile.get('silhouette')!r}")


def main() -> int:
    if not CATALOG.exists():
        fail(f"missing catalog {CATALOG}")
    catalog = load_json(CATALOG)
    district_kits = set((catalog.get("district_kits") or {}).keys())
    residential_kits = set((catalog.get("residential_kits") or {}).keys())
    if len(district_kits) < 6:
        fail("catalog needs at least 6 district kits")
    if len(residential_kits) < 3:
        fail("catalog needs at least 3 residential kits")

    town_count = 0
    block_count = 0
    used_district: set[str] = set()
    for path in sorted((UTOPIA / "towns").glob("*.json")):
        if path.name == "town_schema.json":
            continue
        town_count += 1
        data = load_json(path)
        for block in data.get("town_blocks", []):
            if not isinstance(block, dict):
                continue
            block_count += 1
            profile = block.get("visual_model_profile")
            validate_profile(profile, source=path, item_id=str(block.get("id", "<block>")), legal_kits=district_kits)
            used_district.add(str(profile.get("kit_id")))

    neighborhood_count = 0
    lot_count = 0
    used_residential: set[str] = set()
    for path in sorted((UTOPIA / "neighborhoods").glob("*.json")):
        if path.name == "neighborhood_schema.json":
            continue
        neighborhood_count += 1
        data = load_json(path)
        for lot in data.get("lots", []):
            if not isinstance(lot, dict):
                continue
            lot_count += 1
            profile = lot.get("visual_model_profile")
            validate_profile(profile, source=path, item_id=str(lot.get("id", "<lot>")), legal_kits=residential_kits)
            used_residential.add(str(profile.get("kit_id")))

    if block_count < 300:
        fail(f"expected city block profiles; found {block_count}")
    if lot_count < 50:
        fail(f"expected residential lot profiles; found {lot_count}")
    if len(used_district) < 8:
        fail(f"not enough district kit variety used: {sorted(used_district)}")
    if len(used_residential) < 4:
        fail(f"not enough residential kit variety used: {sorted(used_residential)}")

    print("validate_holoutopia_visual_model_profiles passed")
    print(f"  towns: {town_count}")
    print(f"  district blocks: {block_count}")
    print(f"  district kits used: {len(used_district)}")
    print(f"  neighborhoods: {neighborhood_count}")
    print(f"  residential lots: {lot_count}")
    print(f"  residential kits used: {len(used_residential)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
