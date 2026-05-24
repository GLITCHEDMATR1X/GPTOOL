"""Validate HoloUtopia district structure variants and purpose layers."""
from __future__ import annotations
import json
import sys
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
    from holoutopia_town_blocks import load_structure_variant_catalog, load_town, town_data_dir, validate_structure_variant_profile
    catalog = load_structure_variant_catalog(root)
    catalog_districts = catalog.get("districts", {}) if isinstance(catalog, dict) else {}
    results = []
    total_blocks = 0
    total_variants = 0
    purpose_counts: dict[str, int] = {}
    for path in sorted(town_data_dir(root).glob("*.json")):
        if path.name == "town_schema.json":
            continue
        town = load_town(path.stem, root)
        validate_structure_variant_profile(town, source_path=path)
        town_id = str(town.get("id"))
        if town_id not in catalog_districts:
            raise SystemExit(f"{town_id}: missing from structure variant catalog")
        profile = town.get("structure_variant_profile", {})
        variant_ids = {str(v.get("id")) for v in profile.get("variant_library", []) if isinstance(v, dict)}
        purposes = {str(p.get("id")) for p in profile.get("purpose_layers", []) if isinstance(p, dict)}
        used_variants = {str(b.get("structure_variant_id")) for b in town.get("town_blocks", []) if isinstance(b, dict)}
        used_purposes = {str(b.get("purpose_id")) for b in town.get("town_blocks", []) if isinstance(b, dict)}
        if not used_variants.issubset(variant_ids):
            raise SystemExit(f"{town_id}: block references unknown variant")
        if not used_purposes.issubset(purposes):
            raise SystemExit(f"{town_id}: block references unknown purpose")
        for pid in used_purposes:
            purpose_counts[pid] = purpose_counts.get(pid, 0) + 1
        total_blocks += len(town.get("town_blocks", []))
        total_variants += len(variant_ids)
        results.append({
            "town_id": town_id,
            "district_kind": profile.get("district_kind"),
            "blocks": len(town.get("town_blocks", [])),
            "variants": len(variant_ids),
            "purposes": len(purposes),
            "used_variants": len(used_variants),
            "used_purposes": len(used_purposes),
        })
    print(json.dumps({
        "ok": True,
        "towns": len(results),
        "total_blocks": total_blocks,
        "total_variants": total_variants,
        "purpose_kinds_used": len(purpose_counts),
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
