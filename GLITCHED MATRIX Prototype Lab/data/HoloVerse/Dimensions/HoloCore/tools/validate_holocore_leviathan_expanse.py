"""Validate the high-altitude Leviathan Expanse polish contract."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def require_text(path: Path, needles: list[str]) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path.relative_to(ROOT)} missing marker: {needle}")
    return text


def _literal_number_from_assign(tree: ast.AST, name: str) -> float:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                        return float(node.value.value)
    fail(f"missing numeric constant {name}")
    return 0.0


def main() -> None:
    main_text = require_text(
        ROOT / "main.py",
        [
            "holocore_leviathan_expanse_ambient_root",
            "_setup_leviathan_expanse_ambient",
            "_update_leviathan_expanse_ambient",
            "leviathan_expanse_aurora_veil",
            "distant_current_spine",
            "leviathan_ambient_nodes",
        ],
    )
    if main_text.count("LineSegs(") < 2:
        fail("Leviathan Expanse ambient field should use at least two cheap line-based veil types")
    if "sync_around" in main_text[main_text.find("def _update_vertical_strata_effects"):main_text.find("def _ascent_entity_key_for_spec")]:
        fail("vertical strata update must not rebuild/sync chunks during altitude transitions")

    dragon_text = require_text(
        ROOT / "assets" / "entities" / "holo_dragon_whale.py",
        [
            "DRAGON_WHALE_MASSIVE_SHADOW_COUNT",
            "DRAGON_WHALE_SONAR_LOOP_COUNT",
            "cathedral_slow_breach_sonar_with_shadow_escorts",
            "dragon_whale_far_shadow_lobe",
            "_deep_eye",
        ],
    )
    serpent_text = require_text(
        ROOT / "assets" / "entities" / "holo_storm_serpent.py",
        [
            "STORM_SERPENT_SEGMENT_COUNT",
            "STORM_SERPENT_WARNING_RING_COUNT",
            "cathedral_column_coil_warning_flash_then_vertical_dash",
            "storm_serpent_tail_lightning_spine",
            "_warning_eye",
        ],
    )
    dragon_tree = ast.parse(dragon_text)
    serpent_tree = ast.parse(serpent_text)
    if _literal_number_from_assign(dragon_tree, "DRAGON_WHALE_CONTACT_RADIUS") < 80.0:
        fail("dragon whale contact radius should match its larger silhouette")
    if _literal_number_from_assign(serpent_tree, "STORM_SERPENT_SEGMENT_COUNT") < 15.0:
        fail("storm serpent should be long enough to read as serpent-like")

    registry_text = require_text(
        ROOT / "assets" / "entities" / "ascent_entity_registry.py",
        [
            "altitude_spacing=3800.0",
            "base_distance=1280.0",
            "spawn_chance=0.14",
            "scale_max=12.5",
            "colossal Leviathan Expanse dragon whale",
            "cathedral-scale storm serpent",
        ],
    )
    if "spawn_chance=0.32" in registry_text or "base_distance=520.0" in registry_text:
        fail("old closer/denser serpent tuning remains in registry")

    vertical_text = require_text(
        ROOT / "dimensions" / "vertical_strata.py",
        ["Leviathan Expanse", "dragon whales and elder serpents", "VERTICAL_STRATA_LAYER_HEIGHT = 3200.0"],
    )
    if "VERTICAL_STRATA_START_ALTITUDE = 100.0" not in vertical_text:
        fail("vertical strata should retain 100-unit safe launch offset")

    print("PASS: holocore Leviathan Expanse polish contract is intact")


if __name__ == "__main__":
    main()
