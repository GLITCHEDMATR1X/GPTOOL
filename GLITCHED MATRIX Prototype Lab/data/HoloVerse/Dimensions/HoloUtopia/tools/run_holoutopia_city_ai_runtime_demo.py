#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    root = Path.cwd()
    mod_dir = root / "data" / "HoloUtopia"
    load_module("city_ai_models", mod_dir / "city_ai_models.py")
    runtime_mod = load_module("city_ai_runtime", mod_dir / "city_ai_runtime.py")
    bridge_mod = load_module("city_ai_inspector_bridge", mod_dir / "city_ai_inspector_bridge.py")

    runtime = runtime_mod.CityAIRuntime(root, auto_load_state=False)
    samples = [
        {"id": "citizen_aria_voss", "display_name": "Aria Voss", "role": "harbor_engineer", "friend_name": "Ren Vale"},
        {"id": "citizen_ren_vale", "display_name": "Ren Vale", "role": "simulation_designer", "friend_name": "Aria Voss"},
        {"id": "citizen_mira_sen", "display_name": "Mira Sen", "role": "biomedical_technician", "friend_name": "Sol Hara"},
    ]
    districts = ["port_fabrication", "simulation_belt", "biomedical_quarter"]
    for citizen, district in zip(samples, districts):
        snapshot = runtime.build_snapshot(citizen, district, now=1800.0, force_thought=True)
        tabs = bridge_mod.build_inspector_tabs(snapshot)
        print("=" * 64)
        for line in bridge_mod.flatten_tabs_for_legacy_panel(tabs):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
