from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(text: str, default: str = "panda3d_game") -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default


def _title_from_command(command: str) -> str:
    source = command.strip()
    quoted = re.findall(r"[\"']([^\"']{3,60})[\"']", source)
    if quoted:
        return quoted[0].strip()
    # Remove common request prefixes and use a compact title-like phrase.
    text = re.sub(r"\b(make|create|build|generate|prototype|a|an|the|game|panda3d|template|ready)\b", " ", source, flags=re.I)
    words = re.findall(r"[A-Za-z0-9]+", text)[:5]
    if not words:
        return "Panda3D Game Prototype"
    return " ".join(word.capitalize() for word in words)


def _contains(text: str, *needles: str) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _add_unique(items: list[Any], item: Any) -> None:
    if item not in items:
        items.append(item)


def _color(name: str) -> list[float]:
    colors = {
        "black": [0.01, 0.015, 0.025, 1.0],
        "white": [0.9, 0.95, 1.0, 1.0],
        "green": [0.1, 0.55, 0.25, 1.0],
        "yellow": [0.7, 0.58, 0.15, 1.0],
        "blue": [0.12, 0.35, 0.75, 1.0],
        "cyan": [0.0, 0.85, 1.0, 1.0],
        "purple": [0.45, 0.15, 0.8, 1.0],
        "red": [0.8, 0.08, 0.05, 1.0],
        "amber": [0.9, 0.48, 0.08, 1.0],
        "gray": [0.32, 0.34, 0.36, 1.0],
        "orange": [0.95, 0.35, 0.08, 1.0],
        "ice": [0.55, 0.9, 1.0, 1.0],
    }
    return colors.get(name, colors["cyan"])


def _region(region_id: str, display_name: str, *, color: str, terrain: str, role: str, features: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": region_id,
        "name": display_name,
        "terrain": terrain,
        "color": _color(color),
        "role": role,
        "features": features or [],
        "spawn_density": "normal",
        "navigation": {
            "walkable": terrain not in {"deep_water", "space_void"},
            "avoid_spawn_inside_geometry": True,
            "has_clear_spawn_pad": True,
        },
    }


def _character(char_id: str, display_name: str, *, role: str, region: str, color: str, behavior: str, features: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": char_id,
        "name": display_name,
        "role": role,
        "home_region": region,
        "color": _color(color),
        "silhouette": "clear_non_placeholder",
        "behavior": behavior,
        "features": features or [],
        "must_not": [
            "Do not use egg-like placeholder silhouettes unless explicitly requested.",
            "Do not spawn inside walls or below terrain.",
            "Do not follow the player as a pet unless requested.",
        ],
    }


def infer_game_settings(project_root: str | Path | None, profile: str, command: str) -> dict[str, Any]:
    """Convert a natural-language game request into editable deterministic settings.

    The output is intended for AI agents and humans: it is strict enough to use as
    a generation contract, but simple enough to hand-edit before template output.
    """
    source = command.strip()
    text = source.lower()
    title = _title_from_command(source)
    slug = _slugify(title)
    settings_id = hashlib.sha1(f"{profile}\n{source}".encode("utf-8", errors="ignore")).hexdigest()[:12]

    art_style = "vector_neon" if _contains(text, "vector", "tron", "neon", "grid", "holo", "matrix") else "clean_prototype"
    camera = "third_person_orbit"
    if _contains(text, "first person", "fps", "shooter"):
        camera = "first_person"
    elif _contains(text, "top down", "top-down", "strategy"):
        camera = "top_down"
    elif _contains(text, "side view", "side-view", "platformer"):
        camera = "side_view"

    movement = {
        "wasd": True,
        "mouse_look": camera in {"first_person", "third_person_orbit"},
        "jump": True,
        "sprint": True,
        "fly_toggle": _contains(text, "fly", "flight", "hover", "ship", "space", "craft"),
    }

    world_type = "single_arena"
    if _contains(text, "open world", "biome", "region", "regions", "world", "holoverse"):
        world_type = "multi_region_world"
    if _contains(text, "space"):
        world_type = "layered_world"

    regions: list[dict[str, Any]] = []
    # Always include a safe spawn hub for generated templates.
    regions.append(_region("hub", "Spawn Hub", color="cyan", terrain="flat_grid", role="safe start and test area", features=["spawn pad", "command board", "validation markers"]))

    requested_region_map = [
        ("forest", "Forest", "green", "forest_grid", "organic traversal and trees", ["trees", "clear landmarks"]),
        ("hill", "Hills", "yellow", "rolling_hills", "height variation and grown creatures", ["smooth hills", "grown animals", "persistent objects"]),
        ("desert", "Desert", "amber", "sand_grid", "open terrain and pyramids", ["pyramids", "warm sky"]),
        ("ice", "Ice", "ice", "ice_cubes", "slippery geometry and floating cubes", ["cube terrain", "cold sky"]),
        ("water", "Water", "blue", "deep_water", "swimming and no-ground rules", ["ripples", "underwater tint", "sea life"]),
        ("urban", "Urban", "gray", "urban_blocks", "combat route and readable terrain", ["cover", "visible roads", "warzone markers"]),
        ("metropolis", "Metropolis", "purple", "tall_city", "vertical city and robot lab", ["towers", "hover traffic", "robot slots"]),
        ("space", "Space", "black", "space_void", "high altitude endless layer", ["stars", "low gravity", "distant objects"]),
    ]
    for key, name, color, terrain, role, features in requested_region_map:
        if key in text or (key == "hill" and "hills" in text):
            regions.append(_region(key, name, color=color, terrain=terrain, role=role, features=features))

    if len(regions) == 1 and world_type != "single_arena":
        regions.extend([
            _region("forest", "Forest", color="green", terrain="forest_grid", role="organic contrast region", features=["trees"]),
            _region("urban", "Urban", color="gray", terrain="urban_blocks", role="built environment region", features=["roads", "cover"]),
        ])

    characters: list[dict[str, Any]] = []
    if _contains(text, "bot", "robot", "npc", "ally", "enemy", "character", "creature", "animal", "human", "person", "survivor", "avatar"):
        if _contains(text, "human", "person", "survivor", "avatar"):
            characters.append(_character("human_actor", "Human Actor", role="player_or_npc_human", region="hub", color="white", behavior="idle_near_spawn", features=["imported rigged mesh preferred", "Actor runtime path"]))
        if _contains(text, "robot", "bot"):
            characters.append(_character("bot_alpha", "Bot Alpha", role="ally_or_test_bot", region="hub", color="cyan", behavior="idle_then_follow_command", features=["clear silhouette", "state marker"]))
        if _contains(text, "animal", "creature"):
            home = "hill" if any(r["id"] == "hill" for r in regions) else "hub"
            characters.append(_character("grown_creature", "Grown Creature", role="ambient_creature", region=home, color="green", behavior="wander_safe_region", features=["grown body", "not egg-shaped", "persistent spawn"]))
        if _contains(text, "enemy", "war", "combat", "battle"):
            home = "urban" if any(r["id"] == "urban" for r in regions) else "hub"
            characters.append(_character("enemy_test_unit", "Enemy Test Unit", role="combat_test_enemy", region=home, color="red", behavior="patrol_then_engage", features=["line of sight placeholder", "safe spacing"]))
    else:
        characters.append(_character("guide_bot", "Guide Bot", role="noncombat guide", region="hub", color="cyan", behavior="idle_near_spawn", features=["interaction marker"]))

    # Pass 11 baseline simulation actors: every generated Panda3D template now
    # includes two visible, controllable test humans for edit validation.
    playable_testers = [
        _character("playable_male", "Male Simulation Tester", role="playable_test_character", region="hub", color="cyan", behavior="controlled_when_active", features=["Tab swappable", "procedural humanoid body", "male test profile"]),
        _character("playable_female", "Female Simulation Tester", role="playable_test_character", region="hub", color="purple", behavior="controlled_when_active", features=["Tab swappable", "procedural humanoid body", "female test profile"]),
    ]
    existing_ids = {item.get("id") for item in characters}
    missing_playable_testers = []
    for tester in playable_testers:
        if tester.get("id") not in existing_ids:
            missing_playable_testers.append(tester)
            existing_ids.add(tester.get("id"))
    if missing_playable_testers:
        characters = missing_playable_testers + characters

    objectives: list[str] = []
    if _contains(text, "capture", "flag"):
        objectives.append("capture_the_flag_placeholder")
    if _contains(text, "survive", "waves", "war", "combat"):
        objectives.append("survive_test_wave")
    if _contains(text, "explore", "world", "biome", "region"):
        objectives.append("explore_regions")
    if not objectives:
        objectives.append("walk_around_and_validate_template")

    ui = {
        "show_title": True,
        "show_points": _contains(text, "points", "score") or True,
        "show_fps": False,
        "corner_status": True,
        "transparent_panels": True,
        "safe_bounds": True,
    }

    generation_contract = {
        "must_do": [
            "Generate a runnable Panda3D project template.",
            "Create editable settings that preserve the original command.",
            "Include a safe spawn area and clear player controls.",
            "Use simple procedural geometry first so the template has no external asset dependency.",
            "Include smoke/screenshot hooks for bridge validation.",
        ],
        "must_not_do": [
            "Do not require external art assets for the first generated run.",
            "Do not include an FPS counter by default.",
            "Do not generate placeholder characters that look like eggs unless requested.",
            "Do not spawn the player inside geometry.",
        ],
        "acceptance_checks": [
            "Python syntax compiles.",
            "main.py exists at project root.",
            "settings/game_settings.json exists and matches the command.",
            "Panda3D runtime can launch when Panda3D is installed or a portable runtime is supplied.",
            "Screenshot hook is present for bridge proof.",
            "Playable simulation mode spawns two test characters and supports Tab swapping.",
            "Imported human assets, when present, have a human_manifest.json and fall back cleanly if Actor loading is unavailable.",
        ],
    }

    return {
        "schema_version": "game_settings.v1",
        "settings_id": settings_id,
        "created_at": _now_iso(),
        "profile": profile,
        "source_command": source,
        "project": {
            "title": title,
            "slug": slug,
            "engine": "panda3d",
            "python_minimum": "3.10",
            "template_version": "panda3d_playable_simulation_template.v3",
        },
        "style": {
            "art_style": art_style,
            "background": "dark_gradient" if art_style == "vector_neon" else "simple_sky",
            "linework": art_style == "vector_neon",
            "procedural_first": True,
        },
        "world": {
            "type": world_type,
            "scale": "prototype_safe",
            "regions": regions,
            "spawn": {"region": "hub", "position": [0, 0, 2], "heading": 0},
            "navigation_rules": [
                "keep spawn pad clear",
                "avoid unreachable required areas",
                "use visible landmarks per region",
                "keep generated geometry lightweight",
            ],
        },
        "player": {
            "camera": camera,
            "movement": movement,
            "speed": 12.0,
            "sprint_multiplier": 2.0,
            "jump_strength": 8.0,
        },
        "simulation": {
            "mode": "playable_character_edit_test",
            "enabled": True,
            "active_character_id": "playable_male",
            "swap_key": "tab",
            "screenshot_mode": {
                "enabled": True,
                "cli_flag": "--screenshot-mode",
                "default_output": "screenshots/simulation_mode_backup.png"
            },
            "route_proof": {
                "enabled": True,
                "cli_flag": "--route-proof",
                "purpose": "Automatically move both simulation characters and prove Tab swapping without manual input."
            },
            "characters": [
                {"id": "playable_male", "name": "Male Simulation Tester", "gender_profile": "male", "spawn": [-2.2, 2.0, 0.05], "active_by_default": True},
                {"id": "playable_female", "name": "Female Simulation Tester", "gender_profile": "female", "spawn": [2.2, 2.0, 0.05], "active_by_default": False}
            ]
        },
        "characters": characters,
        "assets": {
            "human_manifest": "assets/characters/humans/human_manifest.json",
            "human_mesh_policy": "Run import-human-assets after generation when the command needs rigged human meshes.",
        },
        "objectives": objectives,
        "ui": ui,
        "bridge": {
            "recommended_profile": "panda3d",
            "entry": "main.py",
            "supports_smoke_hook": True,
            "recommended_validate_command": "python bridge.py full-pass . --profile panda3d --smoke --entry main.py --require-proof",
        },
        "generation_contract": generation_contract,
    }


def render_game_settings_markdown(settings: dict[str, Any]) -> str:
    project = settings.get("project") or {}
    world = settings.get("world") or {}
    lines = [
        "# Game Template Settings",
        "",
        f"- Title: `{project.get('title')}`",
        f"- Engine: `{project.get('engine')}`",
        f"- Source command: {settings.get('source_command')}",
        f"- World type: `{world.get('type')}`",
        "",
        "## Regions",
        "",
    ]
    for region in world.get("regions") or []:
        lines.append(f"- **{region.get('name')}** (`{region.get('id')}`): {region.get('terrain')} — {region.get('role')}")
    lines.extend(["", "## Characters", ""])
    for char in settings.get("characters") or []:
        lines.append(f"- **{char.get('name')}** (`{char.get('id')}`): {char.get('role')} in `{char.get('home_region')}`")
    lines.extend(["", "## Generation Contract", "", "### Must Do"])
    for item in (settings.get("generation_contract") or {}).get("must_do") or []:
        lines.append(f"- {item}")
    lines.extend(["", "### Must Not Do"])
    for item in (settings.get("generation_contract") or {}).get("must_not_do") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
