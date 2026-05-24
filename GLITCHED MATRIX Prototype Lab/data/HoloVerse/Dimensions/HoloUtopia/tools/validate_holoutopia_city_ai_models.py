#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FILES = [
    "citizen_mind_model.schema.json",
    "citizen_archetype_catalog.json",
    "district_pressure_model.json",
    "thought_template_catalog.json",
    "event_memory_schema.json",
]

def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"[FAIL] Could not read JSON {path}: {exc}")

def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] {message}")

def main() -> int:
    root = Path.cwd()
    ai_dir = root / "data" / "database" / "utopia" / "ai"
    if not ai_dir.exists():
        fail(f"Missing AI model directory: {ai_dir}")

    for name in REQUIRED_FILES:
        path = ai_dir / name
        if not path.exists():
            fail(f"Missing required AI model file: {path}")
        load_json(path)

    archetypes = load_json(ai_dir / "citizen_archetype_catalog.json")
    if not archetypes.get("archetype_models"):
        fail("citizen_archetype_catalog.json has no archetype_models")

    for key, model in archetypes["archetype_models"].items():
        for field in ("label", "core_needs", "strengths", "weaknesses", "preferred_tasks", "thought_tags"):
            if field not in model:
                fail(f"Archetype {key!r} missing {field!r}")
        if not isinstance(model["thought_tags"], list) or not model["thought_tags"]:
            fail(f"Archetype {key!r} needs at least one thought tag")

    districts = load_json(ai_dir / "district_pressure_model.json")
    if not districts.get("districts"):
        fail("district_pressure_model.json has no districts")
    for key, model in districts["districts"].items():
        if not model.get("display"):
            fail(f"District {key!r} missing display name")
        pressure = float(model.get("default_pressure", -1))
        if not (0.0 <= pressure <= 1.0):
            fail(f"District {key!r} default_pressure must be 0..1")

    thoughts = load_json(ai_dir / "thought_template_catalog.json")
    templates = thoughts.get("templates", [])
    if len(templates) < 5:
        fail("Need at least 5 thought templates")
    seen = set()
    for item in templates:
        item_id = item.get("id")
        if not item_id:
            fail("Thought template missing id")
        if item_id in seen:
            fail(f"Duplicate thought template id: {item_id}")
        seen.add(item_id)
        if not item.get("text"):
            fail(f"Thought template {item_id} missing text")
        if "{" in item["text"] and "}" not in item["text"]:
            fail(f"Thought template {item_id} has malformed placeholder text")

    print("[OK] HoloUtopia city AI model files validated")
    print(f"[OK] archetypes={len(archetypes['archetype_models'])} districts={len(districts['districts'])} thoughts={len(templates)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
