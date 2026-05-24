"""Validate the expanded HoloCore biome-band registry and drop-in assets."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panda3d.core import NodePath, PandaNode  # noqa: E402
from dimensions.dimension_manager import DimensionManager  # noqa: E402
from world_grid import BIOME_BLEND_WIDTH, BIOME_DISTANCE_STRIDE  # noqa: E402

REPORT = ROOT / "logs" / "holocore_biome_band_set_validation_report.json"
EXPECTED_BIOME_COUNT = 10
EXPECTED_FOLDERS = [f"biome{i}" for i in range(1, 8)]
EXPECTED_NEW_ASSETS = {
    "biome4": {"abyssal_kelp_column", "glow_frond_cluster"},
    "biome5": {"mirror_glass_plate", "prism_shard_cluster"},
    "biome6": {"archive_pillar_ruin", "data_relay_stone", "broken_holo_arch"},
    "biome7": {"storm_current_pylon", "charged_anemone", "current_ring_marker"},
}


def _load_module(path: Path):
    name = f"validate_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _band_index_for_distance(manager: DimensionManager, distance: float) -> int:
    # Mirrors FlatOuterWorldAdapter._dimension_index_for_distance without
    # constructing a full Panda3D app.  This protects the same spacing rhythm.
    exploration = max(0.0, float(distance or 0.0) - 360.0)
    return int(exploration // max(1.0, BIOME_DISTANCE_STRIDE)) % len(manager.dimensions)


def main() -> int:
    errors: list[str] = []
    assets_root = ROOT / "assets" / "holocore"
    manager = DimensionManager(assets_root=assets_root)
    definitions = list(manager.dimensions)

    if len(definitions) != EXPECTED_BIOME_COUNT:
        errors.append(f"dimension-count:{len(definitions)}!=10")

    ids = [definition.dimension_id for definition in definitions]
    if sorted(ids) != list(range(1, EXPECTED_BIOME_COUNT + 1)):
        errors.append(f"dimension-ids-not-1-through-10:{ids}")
    if len(set(ids)) != len(ids):
        errors.append(f"dimension-ids-not-unique:{ids}")

    names = [definition.name for definition in definitions]
    if len(set(names)) != len(names):
        errors.append("dimension-names-not-unique")

    folders = [definition.biome_folder for definition in definitions]
    for folder in EXPECTED_FOLDERS:
        folder_path = assets_root / folder
        if not folder_path.is_dir():
            errors.append(f"biome-folder-missing:{folder}")
    for definition in definitions:
        if not (assets_root / definition.biome_folder).is_dir():
            errors.append(f"definition-folder-missing:{definition.dimension_id}:{definition.biome_folder}")

    if abs(BIOME_DISTANCE_STRIDE - 1440.0) > 0.001:
        errors.append(f"biome-distance-stride-changed:{BIOME_DISTANCE_STRIDE}")
    if abs(BIOME_BLEND_WIDTH - 260.0) > 0.001:
        errors.append(f"biome-blend-width-changed:{BIOME_BLEND_WIDTH}")

    expected_cycle = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1]
    actual_cycle = [_band_index_for_distance(manager, 360.0 + BIOME_DISTANCE_STRIDE * i + 4.0) for i in range(len(expected_cycle))]
    if actual_cycle != expected_cycle:
        errors.append(f"band-cycle-mismatch:{actual_cycle}")

    build_parent = NodePath(PandaNode("biome_validation_parent"))
    asset_results: dict[str, list[str]] = {}
    for folder, expected_assets in EXPECTED_NEW_ASSETS.items():
        found = {path.stem for path in sorted((assets_root / folder).glob("*.py")) if not path.name.startswith("_")}
        missing = sorted(expected_assets - found)
        if missing:
            errors.append(f"new-biome-assets-missing:{folder}:{missing}")
        asset_results[folder] = sorted(found)
        for path in sorted((assets_root / folder).glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                module = _load_module(path)
                info = getattr(module, "SURFACE_OBJECT", None)
                if not isinstance(info, dict):
                    errors.append(f"surface-object-metadata-missing:{folder}/{path.name}")
                    continue
                if not str(info.get("id") or "").strip():
                    errors.append(f"surface-object-id-missing:{folder}/{path.name}")
                if not callable(getattr(module, "build", None)):
                    errors.append(f"surface-object-build-missing:{folder}/{path.name}")
                    continue
                node = module.build(
                    build_parent,
                    1000.0,
                    1000.0,
                    0.0,
                    Random(1234),
                    {
                        "asset_id": info.get("id", path.stem),
                        "biome_folder": folder,
                        "hierarchy": info.get("hierarchy", 0),
                        "surface_z_at": lambda sx, sy: 0.0,
                        "surface_height_at": lambda sx, sy: 0.0,
                        "floor_z": 0.0,
                    },
                )
                if node is None or node.isEmpty():
                    errors.append(f"surface-object-build-empty:{folder}/{path.name}")
            except Exception as exc:  # pragma: no cover - validation output matters more than traceback here.
                errors.append(f"surface-object-build-error:{folder}/{path.name}:{exc.__class__.__name__}:{exc}")

    report = {
        "schema": 1,
        "kind": "holocore_biome_band_set_validation",
        "status": "PASS" if not errors else "FAIL",
        "dimension_count": len(definitions),
        "dimension_ids": ids,
        "dimension_names": names,
        "dimension_folders": folders,
        "expected_folders": EXPECTED_FOLDERS,
        "new_asset_results": asset_results,
        "biome_distance_stride": BIOME_DISTANCE_STRIDE,
        "biome_blend_width": BIOME_BLEND_WIDTH,
        "band_cycle": actual_cycle,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
