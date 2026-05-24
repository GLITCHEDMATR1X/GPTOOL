#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] {message}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"Could not load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    root = Path.cwd()
    data_module_dir = root / "data" / "HoloUtopia"
    ai_dir = root / "data" / "database" / "utopia" / "ai"
    for path in (
        data_module_dir / "city_ai_models.py",
        data_module_dir / "city_ai_runtime.py",
        data_module_dir / "city_ai_inspector_bridge.py",
        ai_dir / "city_ai_runtime_defaults.json",
        ai_dir / "social_relation_template_catalog.json",
    ):
        if not path.exists():
            fail(f"Missing Pass 30 file: {path}")

    # Load city_ai_models under the flat name expected by direct fallback imports.
    models_mod = load_module("city_ai_models", data_module_dir / "city_ai_models.py")
    runtime_mod = load_module("city_ai_runtime", data_module_dir / "city_ai_runtime.py")
    bridge_mod = load_module("city_ai_inspector_bridge", data_module_dir / "city_ai_inspector_bridge.py")

    models = models_mod.load_city_ai_models(root)
    if not models.archetypes or not models.districts or not models.thoughts:
        fail("AI models did not load usable archetypes/districts/thoughts")

    sample = {
        "id": "citizen_aria_voss",
        "display_name": "Aria Voss",
        "role": "harbor_engineer",
        "friend_name": "Ren Vale",
    }

    first = models_mod.choose_thought(sample, "port_fabrication", models, now=1800.0)
    second = models_mod.choose_thought(sample, "port_fabrication", models, now=1800.0)
    if first.get("id") != second.get("id") or first.get("text") != second.get("text"):
        fail("Thought choice is not deterministic inside the same cadence slot")

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "citizen_ai_state.json"
        runtime = runtime_mod.CityAIRuntime(root, models=models, state_path=state_path, auto_load_state=False)
        snapshot = runtime.build_snapshot(sample, "port_fabrication", now=1800.0, force_thought=True)
        tabs = bridge_mod.build_inspector_tabs(snapshot, debug=False)
        bridge_mod.assert_no_raw_ids_in_player_tabs(tabs)
        runtime.remember_event(sample, kind="task", summary="Repaired a tide-power relay near the harbor.", location_id="port_fabrication", importance=0.7, now=1812.0)
        if not runtime.get_recent_memories(sample):
            fail("Runtime did not keep citizen memory")
        if not runtime.save_state(force=True, now=1830.0):
            fail("Runtime did not save forced state")
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if not payload.get("citizens"):
            fail("Saved state did not include citizens")

    defaults = json.loads((ai_dir / "city_ai_runtime_defaults.json").read_text(encoding="utf-8"))
    contract = defaults.get("integration_contract", {})
    if contract.get("external_ai_calls_allowed") is not False:
        fail("Runtime contract must keep external AI calls disabled")
    if contract.get("disk_writes_allowed_per_frame") is not False:
        fail("Runtime contract must disallow per-frame disk writes")

    relations = json.loads((ai_dir / "social_relation_template_catalog.json").read_text(encoding="utf-8"))
    if len(relations.get("relationship_tones", {})) < 4:
        fail("Need at least four relationship tones")

    print("[OK] HoloUtopia city AI runtime validated")
    print(f"[OK] archetypes={len(models.archetypes)} districts={len(models.districts)} thoughts={len(models.thoughts)}")
    print("[OK] deterministic thoughts, memory trim/save, inspector tabs, and raw-ID guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
