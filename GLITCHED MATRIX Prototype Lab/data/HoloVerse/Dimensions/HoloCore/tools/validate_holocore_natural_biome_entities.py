"""Validate natural-shape biome assets and biome-specific entity lifecycle wiring."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panda3d.core import NodePath, PandaNode, Vec3  # noqa: E402
from assets.entities.biome_entity_registry import BIOME_ENTITY_SPECS  # noqa: E402

REPORT = ROOT / "logs" / "holocore_natural_biome_entities_validation_report.json"
EXPECTED_ENTITY_MODULES = {
    "biome4": "holo_kelp_ray",
    "biome5": "holo_glass_fish_swarm",
    "biome6": "holo_archive_turtle",
    "biome7": "holo_storm_eel",
}
FORBIDDEN_SURFACE_TERMS = ("wire_box(", "flat_card(", "vertical_card(", "CardMaker")
REQUIRED_OUTER_WORLD_TERMS = (
    "BIOME_ENTITY_SPECS",
    "biome_entity_mobs",
    "_build_chunk_biome_entity",
    "update_biome_entities",
    "_remove_biome_entity",
    "_clear_biome_entities",
)


def _load_module(path: Path):
    name = f"validate_natural_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    errors: list[str] = []
    surface_results: dict[str, dict] = {}
    entity_results: dict[str, dict] = {}
    assets_root = ROOT / "assets" / "holocore"

    for folder in ("biome4", "biome5", "biome6", "biome7"):
        folder_path = assets_root / folder
        for path in sorted(folder_path.glob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel = f"{folder}/{path.name}"
            forbidden_seen = [term for term in FORBIDDEN_SURFACE_TERMS if term in text]
            if forbidden_seen:
                errors.append(f"boxy-surface-term:{rel}:{forbidden_seen}")
            try:
                module = _load_module(path)
                info = getattr(module, "SURFACE_OBJECT", {})
                silhouette = str(info.get("silhouette", ""))
                if not silhouette:
                    errors.append(f"surface-silhouette-missing:{rel}")
                parent = NodePath(PandaNode(f"natural_surface_parent_{folder}"))
                node = module.build(
                    parent,
                    1000.0,
                    1000.0,
                    0.0,
                    __import__("random").Random(909 + len(surface_results)),
                    {"asset_id": info.get("id", path.stem), "biome_folder": folder, "surface_z_at": lambda sx, sy: 0.0, "surface_height_at": lambda sx, sy: 0.0},
                )
                if node is None or node.isEmpty():
                    errors.append(f"surface-build-empty:{rel}")
                surface_results[rel] = {
                    "asset_id": str(info.get("id", path.stem)),
                    "silhouette": silhouette,
                    "child_count": int(parent.getNumChildren()),
                    "forbidden_terms": forbidden_seen,
                }
            except Exception as exc:
                errors.append(f"surface-build-error:{rel}:{exc.__class__.__name__}:{exc}")

    if set(BIOME_ENTITY_SPECS.keys()) != set(EXPECTED_ENTITY_MODULES.keys()):
        errors.append(f"biome-entity-spec-folders:{sorted(BIOME_ENTITY_SPECS.keys())}")

    parent = NodePath(PandaNode("natural_entity_parent"))
    for folder, expected_id in EXPECTED_ENTITY_MODULES.items():
        spec = BIOME_ENTITY_SPECS.get(folder)
        if spec is None:
            errors.append(f"biome-entity-spec-missing:{folder}")
            continue
        if str(spec.entity_id) != expected_id:
            errors.append(f"biome-entity-id-mismatch:{folder}:{spec.entity_id}!={expected_id}")
        if int(getattr(spec, "spacing_chunks", 0) or 0) < 3:
            errors.append(f"biome-entity-spacing-too-tight:{folder}:{getattr(spec, 'spacing_chunks', None)}")
        height_tiers = tuple(float(v) for v in (getattr(spec, "height_tiers", ()) or ()))
        if len(height_tiers) < 3:
            errors.append(f"biome-entity-height-tiers-missing:{folder}:{height_tiers}")
        elif len(set(round(v, 2) for v in height_tiers)) != len(height_tiers):
            errors.append(f"biome-entity-height-tiers-not-distinct:{folder}:{height_tiers}")
        if not str(getattr(spec, "behavior_id", "")):
            errors.append(f"biome-entity-behavior-id-missing:{folder}")
        if not str(getattr(spec, "habitat_note", "")):
            errors.append(f"biome-entity-habitat-note-missing:{folder}")
        cls = spec.mob_class
        required_methods = ["build", "update_surface_lock", "update_pose", "set_visibility_alpha", "destroy"]
        missing_methods = [name for name in required_methods if not callable(getattr(cls, name, None))]
        if missing_methods:
            errors.append(f"entity-methods-missing:{folder}:{missing_methods}")
            continue
        try:
            seed = spec.seed_func((11, 23), int(spec.seed_salt))
            mob = cls(seed=seed, surface_height_offset=float(spec.height_offset)).build(parent, Vec3(100.0, 150.0, 20.0), scale=1.0, heading=45.0)
            root = getattr(mob, "root", None)
            if root is None or root.isEmpty():
                errors.append(f"entity-root-empty:{folder}")
            mob.update_surface_lock(lambda sx, sy: 12.0)
            mob.update_pose(1.25)
            mob.set_visibility_alpha(0.65)
            root_name = root.getName() if root is not None and not root.isEmpty() else ""
            child_count = int(root.getNumChildren()) if root is not None and not root.isEmpty() else 0
            mob.destroy()
            destroyed = root is None or root.isEmpty()
            if not destroyed:
                errors.append(f"entity-destroy-failed:{folder}")
            entity_results[folder] = {
                "entity_id": str(spec.entity_id),
                "root_name": root_name,
                "child_count": child_count,
                "spawn_chance": float(spec.spawn_chance),
                "height_offset": float(spec.height_offset),
                "height_variance": float(spec.height_variance),
                "min_distance_from_hub": float(spec.min_distance_from_hub),
                "update_interval": float(spec.update_interval),
                "spacing_chunks": int(getattr(spec, "spacing_chunks", 1)),
                "height_tiers": [float(v) for v in getattr(spec, "height_tiers", ())],
                "behavior_id": str(getattr(spec, "behavior_id", "")),
                "habitat_note": str(getattr(spec, "habitat_note", "")),
                "destroyed": bool(destroyed),
            }
        except Exception as exc:
            errors.append(f"entity-build-error:{folder}:{exc.__class__.__name__}:{exc}")

    outer_text = (ROOT / "dimensions" / "outer_flat_world.py").read_text(encoding="utf-8", errors="ignore")
    for term in REQUIRED_OUTER_WORLD_TERMS:
        if term not in outer_text:
            errors.append(f"outer-world-term-missing:{term}")

    main_text = (ROOT / "main.py").read_text(encoding="utf-8", errors="ignore")
    if "--biome-entity-smoke" not in main_text:
        errors.append("biome-entity-smoke-flag-missing")
    if "spacing_chunks" not in main_text or "height_tiers" not in main_text or "behavior_id" not in main_text:
        errors.append("biome-entity-special-smoke-fields-missing")
    if "_biome_entity_spacing_allows" not in outer_text or "_biome_entity_height_offset" not in outer_text:
        errors.append("outer-world-special-spacing-height-hooks-missing")

    report = {
        "schema": 1,
        "kind": "holocore_natural_biome_entities_validation",
        "status": "PASS" if not errors else "FAIL",
        "surface_results": surface_results,
        "entity_results": entity_results,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
