"""Validate HoloCore vertical strata math and rescue/encounter wiring without Panda3D."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dimensions.vertical_strata import (  # noqa: E402
    ASCENT_ENCOUNTER_UPDATE_INTERVAL,
    VERTICAL_STRATA,
    VERTICAL_STRATA_BLEND_HEIGHT,
    VERTICAL_STRATA_LAYER_HEIGHT,
    VERTICAL_STRATA_START_ALTITUDE,
    VERTICAL_STRATA_UPDATE_INTERVAL,
    VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS,
    ascent_debug_samples,
    vertical_stratum_state,
)

REPORT = ROOT / "logs" / "holocore_vertical_strata_validation_report.json"

REQUIRED_MAIN_TERMS = (
    "HOLOCORE_VERTICAL_STRATA_SMOKE",
    "vertical_stratum_state",
    "_update_vertical_strata_effects",
    "_update_ascent_entities",
    "_begin_holocore_rescue",
    "_reset_holocore_rescue_to_start",
    "_update_holocore_rescue",
    "HOLOCORE IMPACT",
    "HOLOCORE RECOVERY",
    "VESSEL PARKED AT SAFE ANCHOR",
    "--vertical-strata-smoke",
)
REQUIRED_ASCENT_REGISTRY_TERMS = (
    "AscentEntitySpec",
    "ASCENT_ENTITY_SPECS",
    "holo_storm_serpent",
    "holo_dragon_whale",
    "altitude_spacing",
    "contact_radius",
)
REQUIRED_ENTITY_METHODS = ("build", "update_surface_lock", "update_pose", "set_visibility_alpha", "destroy")


def _class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    return set()


def main() -> int:
    errors: list[str] = []
    samples = ascent_debug_samples()
    if len(VERTICAL_STRATA) < 6:
        errors.append(f"vertical-strata-too-few:{len(VERTICAL_STRATA)}")
    if float(VERTICAL_STRATA_START_ALTITUDE) < 90.0:
        errors.append(f"start-altitude-too-low:{VERTICAL_STRATA_START_ALTITUDE}")
    if float(VERTICAL_STRATA_LAYER_HEIGHT) < 2500.0:
        errors.append(f"layer-height-too-small:{VERTICAL_STRATA_LAYER_HEIGHT}")
    if float(VERTICAL_STRATA_BLEND_HEIGHT) < 1000.0:
        errors.append(f"blend-height-not-gradual:{VERTICAL_STRATA_BLEND_HEIGHT}")
    if float(VERTICAL_STRATA_BLEND_HEIGHT) > float(VERTICAL_STRATA_LAYER_HEIGHT) * 0.55:
        errors.append(f"blend-too-large-for-layer:{VERTICAL_STRATA_BLEND_HEIGHT}/{VERTICAL_STRATA_LAYER_HEIGHT}")
    if float(VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS) < 15.0:
        errors.append(f"visual-smoothing-too-fast:{VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS}")
    if float(VERTICAL_STRATA_UPDATE_INTERVAL) < 0.15:
        errors.append(f"vertical-update-too-frequent:{VERTICAL_STRATA_UPDATE_INTERVAL}")
    if float(ASCENT_ENCOUNTER_UPDATE_INTERVAL) < 0.20:
        errors.append(f"encounter-update-too-frequent:{ASCENT_ENCOUNTER_UPDATE_INTERVAL}")

    start = vertical_stratum_state(0.0)
    pre_start = vertical_stratum_state(VERTICAL_STRATA_START_ALTITUDE - 1.0)
    at_start = vertical_stratum_state(VERTICAL_STRATA_START_ALTITUDE)
    near_boundary = vertical_stratum_state(VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT - 12.0)
    next_layer = vertical_stratum_state(VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT + 2.0)
    high = vertical_stratum_state(VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 9.0)
    if start.layer_id != "safe_reef_layer":
        errors.append(f"start-layer-wrong:{start.layer_id}")
    if pre_start.layer_id != "safe_reef_layer" or pre_start.layer_progress != 0.0 or pre_start.blend_alpha != 0.0:
        errors.append(f"pre-start-not-safe:{pre_start.layer_id}/{pre_start.layer_progress}/{pre_start.blend_alpha}")
    if at_start.layer_progress != 0.0 or at_start.blend_alpha != 0.0:
        errors.append(f"start-altitude-not-zero-progress:{at_start.layer_progress}/{at_start.blend_alpha}")
    for index, layer in enumerate(VERTICAL_STRATA):
        expected_min = float(VERTICAL_STRATA_START_ALTITUDE) + float(VERTICAL_STRATA_LAYER_HEIGHT) * index
        if abs(float(layer.altitude_min) - expected_min) > 0.001:
            errors.append(f"layer-min-altitude-stale:{layer.layer_id}:{layer.altitude_min}!={expected_min}")
    if not (0.92 <= near_boundary.blend_alpha <= 1.0):
        errors.append(f"near-boundary-not-blending:{near_boundary.blend_alpha}")
    if next_layer.layer_id == start.layer_id:
        errors.append("layer-did-not-advance-after-height")
    if high.creature_scale_multiplier <= start.creature_scale_multiplier:
        errors.append("creature-scale-does-not-grow-with-ascent")
    if high.creature_distance_multiplier <= start.creature_distance_multiplier:
        errors.append("creature-distance-does-not-grow-with-ascent")
    if high.creature_rarity_multiplier <= start.creature_rarity_multiplier:
        errors.append("creature-rarity-does-not-grow-with-ascent")

    main_text = (ROOT / "main.py").read_text(encoding="utf-8", errors="ignore")
    for term in REQUIRED_MAIN_TERMS:
        if term not in main_text:
            errors.append(f"main-term-missing:{term}")
    forbidden_rebuild_terms = ("_settle_streaming_queue()", "_activate_dimension_assets(immediate=True)")
    vertical_method_start = main_text.find("def _update_vertical_strata_effects")
    vertical_method_end = main_text.find("def _ascent_entity_key_for_spec", vertical_method_start)
    vertical_method_text = main_text[vertical_method_start:vertical_method_end]
    for term in forbidden_rebuild_terms:
        if term in vertical_method_text:
            errors.append(f"vertical-effect-rebuilds-streaming:{term}")

    vessel_text = (ROOT / "assets" / "entities" / "holo_vessel.py").read_text(encoding="utf-8", errors="ignore")
    if "max_flight_altitude: float = 250000.0" not in vessel_text:
        errors.append("vessel-infinite-ascent-cap-not-expanded")

    registry_text = (ROOT / "assets" / "entities" / "ascent_entity_registry.py").read_text(encoding="utf-8", errors="ignore")
    for term in REQUIRED_ASCENT_REGISTRY_TERMS:
        if term not in registry_text:
            errors.append(f"ascent-registry-term-missing:{term}")
    for path, cls in (
        (ROOT / "assets" / "entities" / "holo_dragon_whale.py", "HoloDragonWhaleMob"),
        (ROOT / "assets" / "entities" / "holo_storm_serpent.py", "HoloStormSerpentMob"),
    ):
        if not path.exists():
            errors.append(f"entity-file-missing:{path.name}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "add_cube" in text or "CardMaker" in text or "wire_box" in text:
            errors.append(f"boxy-giant-entity-term:{path.name}")
        methods = _class_method_names(path, cls)
        missing = [name for name in REQUIRED_ENTITY_METHODS if name not in methods]
        if missing:
            errors.append(f"entity-methods-missing:{cls}:{missing}")

    report = {
        "schema": 1,
        "kind": "holocore_vertical_strata_validation",
        "status": "PASS" if not errors else "FAIL",
        "start_altitude": float(VERTICAL_STRATA_START_ALTITUDE),
        "layer_height": float(VERTICAL_STRATA_LAYER_HEIGHT),
        "blend_height": float(VERTICAL_STRATA_BLEND_HEIGHT),
        "visual_smooth_seconds": float(VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS),
        "update_interval": float(VERTICAL_STRATA_UPDATE_INTERVAL),
        "encounter_update_interval": float(ASCENT_ENCOUNTER_UPDATE_INTERVAL),
        "layers": [item.layer_id for item in VERTICAL_STRATA],
        "samples": samples,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
