"""Validate HoloCore asset folder ownership without launching Panda3D."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_asset_layout_validation_report.json"

ENTITY_MODULES = [
    "holo_mermaid.py",
    "holo_jellyfish.py",
    "holo_octopus.py",
    "holo_vessel.py",
]
BIOME_DIRS = [f"biome{i}" for i in range(1, 8)]


def main() -> int:
    errors: list[str] = []
    entity_root = ROOT / "assets" / "entities"
    biome_root = ROOT / "assets" / "holocore"
    if not entity_root.is_dir():
        errors.append("assets/entities-missing")
    if not biome_root.is_dir():
        errors.append("assets/holocore-missing")
    for name in ENTITY_MODULES:
        impl = entity_root / name
        shim = ROOT / name
        if not impl.is_file():
            errors.append(f"entity-implementation-missing:{impl.as_posix()}")
            impl_text = ""
        else:
            impl_text = impl.read_text(encoding="utf-8", errors="ignore")
        if not shim.is_file():
            errors.append(f"compat-shim-missing:{name}")
        else:
            shim_text = shim.read_text(encoding="utf-8", errors="ignore")
            expected = f"assets.entities.{name[:-3]}"
            if expected not in shim_text:
                errors.append(f"compat-shim-not-routing:{name}")
        expected_class = {
            "holo_mermaid.py": "class HoloMermaidMob",
            "holo_jellyfish.py": "class HoloJellyfishMob",
            "holo_octopus.py": "class HoloOctopusMob",
            "holo_vessel.py": "class HoloVessel",
        }[name]
        if expected_class not in impl_text:
            errors.append(f"entity-class-missing:{name}:{expected_class}")
    for name in BIOME_DIRS:
        if not (biome_root / name).is_dir():
            errors.append(f"biome-folder-missing:assets/holocore/{name}")
    outer = ROOT / "dimensions" / "outer_flat_world.py"
    outer_text = outer.read_text(encoding="utf-8", errors="ignore") if outer.exists() else ""
    for term in [
        "from assets.entities.holo_mermaid import",
        "from assets.entities.holo_jellyfish import",
        "from assets.entities.holo_octopus import",
        "local_assets_root = root_dir / \"assets\" / \"holocore\"",
        "host_assets_root",
        "legacy_assets_root",
    ]:
        if term not in outer_text:
            errors.append(f"outer-asset-route-missing:{term}")
    main_text = (ROOT / "main.py").read_text(encoding="utf-8", errors="ignore")
    if "from assets.entities.holo_vessel import HoloVessel" not in main_text:
        errors.append("main-vessel-asset-import-missing")
    report = {
        "schema": 1,
        "kind": "holocore_asset_layout_validation",
        "status": "PASS" if not errors else "FAIL",
        "entity_root": str(entity_root.relative_to(ROOT)),
        "biome_root": str(biome_root.relative_to(ROOT)),
        "entities": ENTITY_MODULES,
        "biome_dirs": BIOME_DIRS,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
