"""Validate lightweight ambient motion metadata for expanded HoloCore biomes."""
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

REPORT = ROOT / "logs" / "holocore_biome_motion_validation_report.json"
EXPECTED_MOTION_KINDS = {
    "biome4/abyssal_kelp_column.py": "sway",
    "biome4/glow_frond_cluster.py": "sway",
    "biome5/mirror_glass_plate.py": "signal_pulse",
    "biome5/prism_shard_cluster.py": "signal_pulse",
    "biome6/archive_pillar_ruin.py": "signal_pulse",
    "biome6/broken_holo_arch.py": "signal_pulse",
    "biome6/data_relay_stone.py": "orbit_spin",
    "biome7/storm_current_pylon.py": "electric_flicker",
    "biome7/charged_anemone.py": "electric_flicker",
    "biome7/current_ring_marker.py": "orbit_spin",
}
REQUIRED_RUNTIME_TERMS = [
    'kind == "orbit_spin"',
    'kind == "signal_pulse"',
    'kind == "electric_flicker"',
    'ambient_base_h',
    'flow_spin_rate',
    'flow_scale_amplitude',
]


def _load_module(path: Path):
    name = f"validate_motion_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    errors: list[str] = []
    results: dict[str, dict] = {}
    surface_text = (ROOT / "dimensions" / "surface_placement.py").read_text(encoding="utf-8", errors="ignore")
    primitive_text = (ROOT / "assets" / "holocore_object_primitives.py").read_text(encoding="utf-8", errors="ignore")
    for term in REQUIRED_RUNTIME_TERMS:
        if term not in surface_text and term not in primitive_text:
            errors.append(f"motion-runtime-term-missing:{term}")

    parent = NodePath(PandaNode("biome_motion_validation_parent"))
    for rel, expected_kind in EXPECTED_MOTION_KINDS.items():
        path = ROOT / "assets" / "holocore" / rel
        if not path.is_file():
            errors.append(f"motion-asset-missing:{rel}")
            continue
        try:
            module = _load_module(path)
            info = getattr(module, "SURFACE_OBJECT", {})
            node = module.build(
                parent,
                1000.0,
                1000.0,
                0.0,
                Random(7341),
                {
                    "asset_id": info.get("id", path.stem),
                    "biome_folder": path.parent.name,
                    "hierarchy": info.get("hierarchy", 0),
                    "surface_z_at": lambda sx, sy: 0.0,
                    "surface_height_at": lambda sx, sy: 0.0,
                    "floor_z": 0.0,
                },
            )
            if node is None or node.isEmpty():
                errors.append(f"motion-build-empty:{rel}")
                continue
            animated = bool(node.getPythonTag("animated_surface_object"))
            kind = str(node.getPythonTag("ambient_motion_kind") or "sway")
            has_base = all(node.hasPythonTag(tag) for tag in ("ambient_base_h", "ambient_base_p", "ambient_base_r", "ambient_base_sx", "ambient_base_sy", "ambient_base_sz"))
            has_motion_fields = all(node.hasPythonTag(tag) for tag in ("flow_phase", "flow_amplitude", "flow_rate", "flow_pulse_amplitude"))
            results[rel] = {
                "asset_id": str(info.get("id", path.stem)),
                "expected_kind": expected_kind,
                "kind": kind,
                "animated": animated,
                "has_base_transform": has_base,
                "has_motion_fields": has_motion_fields,
            }
            if not animated:
                errors.append(f"not-marked-animated:{rel}")
            if kind != expected_kind:
                errors.append(f"motion-kind-mismatch:{rel}:{kind}!={expected_kind}")
            if not has_base:
                errors.append(f"base-transform-tags-missing:{rel}")
            if not has_motion_fields:
                errors.append(f"motion-field-tags-missing:{rel}")
        except Exception as exc:  # pragma: no cover
            errors.append(f"motion-asset-error:{rel}:{exc.__class__.__name__}:{exc}")

    report = {
        "schema": 1,
        "kind": "holocore_biome_motion_validation",
        "status": "PASS" if not errors else "FAIL",
        "expected_motion_kinds": EXPECTED_MOTION_KINDS,
        "results": results,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
