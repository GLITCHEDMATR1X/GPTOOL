#!/usr/bin/env python3
"""Project-specific patch gate rules for GPTOOL Pass 17.

These rules are intentionally specialized for the GLITCHED MATRIX / GX / HoloVerse
project family.  They are not meant to be a generic software merge policy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

RULESET_VERSION = "gptool.patch_gate.rules.v1"

CORE_RULES = [
    "Protected project files are never blindly overwritten by patch zips.",
    "Patch zips propose code additions/merges; GPTOOL produces a review report before anything is applied.",
    "Incoming Python code is combined additively when safe: imports, constants, new functions, new classes, and new class methods.",
    "Changing an existing protected function/method body requires approval or override review.",
    "Smaller or stale protected files are blocked/staged instead of replacing current integrated files.",
    "Risky updates are staged under _pass_overrides/<pass-name>/<target-path>.",
    "Validation and approval must pass before a final-looking combined zip or repo patch is treated as clean.",
    "Logs, screenshots, crash reports, pycache, and temporary reports are dev evidence, not release/package content.",
    "Notes and pass logs should be combined/sorted into curated docs/reports, not scattered through the project.",
]

@dataclass(frozen=True)
class ProjectRuleProfile:
    name: str
    description: str
    protected_patterns: tuple[str, ...]
    validator_hints: tuple[str, ...]
    banned_text: tuple[str, ...] = ()
    cleanup_policy: tuple[str, ...] = ()

PROFILES: dict[str, ProjectRuleProfile] = {
    "gx-prototype-lab": ProjectRuleProfile(
        name="gx-prototype-lab",
        description="GX launcher/build/runtime profile. Protects the app shell, build scripts, specs, requirements, and bundled HoloVerse tree.",
        protected_patterns=(
            "GXPrototypeLab.py",
            "data/gx_app_main.py",
            "data/gx_core/*.py",
            "data/gx_core/**/*.py",
            "data/HoloVerse/**/*.py",
            "data/HoloVerse/**/manifest*.json",
            "data/HoloVerse/**/ui_manifest.json",
            "build_GXPrototypeLab.ps1",
            "GXPrototypeLab.spec",
            "py_runner.spec",
            "requirements.txt",
            "install_requirements.bat",
            "README_BUILD_EXE.md",
        ),
        validator_hints=(
            "python -m compileall -q GXPrototypeLab.py data",
            "python bridge.py package-audit .",
        ),
        cleanup_policy=(
            "No duplicate root-level assets/ or data/ in release output.",
            "Keep py_runner runtime bundled as its own child-runtime folder.",
            "Do not package logs/latest.log, crash_reports, screenshots, __pycache__, or .pyc.",
        ),
    ),
    "holoverse": ProjectRuleProfile(
        name="holoverse",
        description="HoloVerse route/adaptor contract profile. Protects native dimension routing and same-window artifact behavior.",
        protected_patterns=(
            "main.py",
            "world.py",
            "runtime.py",
            "Dimensions/**/*.py",
            "dimensions/**/*.py",
            "adapters/**/*.py",
            "*adapter*.py",
            "*route*.py",
            "*routes*.py",
            "*manifest*.json",
            "ui/ui_manifest.json",
            "tools/validate_*.py",
        ),
        validator_hints=(
            "python -m compileall -q .",
            "python tools/validate_holoverse_routes.py",
            "python tools/validate_dimension_contracts.py",
            "python tools/validate_dimension_launches.py",
            "python tools/validate_dimension_presentation_contracts.py",
        ),
        banned_text=("embedded_external", "placeholder_mode", "child-window"),
        cleanup_policy=(
            "HoloCore remains same_window_mode_holocore unless deliberately redesigned.",
            "Artifact routes should not regress to child windows or placeholder modes.",
            "TAB aircraft/travel behavior must not leak into native dimensions or HoloCore.",
        ),
    ),
    "holocore": ProjectRuleProfile(
        name="holocore",
        description="HoloCore profile. Protects vessel, vertical strata, Ocean-Space, entity registries, and same-window adapter safety.",
        protected_patterns=(
            "main.py",
            "dimensions/**/*.py",
            "assets/entities/**/*.py",
            "assets/holocore/**/*.py",
            "tools/validate_holocore*.py",
        ),
        validator_hints=(
            "python -m compileall -q .",
            "python tools/validate_holocore_asset_layout.py",
            "python tools/validate_holocore_vertical_strata.py",
            "python tools/validate_holocore_ocean_space.py",
            "python tools/validate_holocore_vessel.py",
        ),
        cleanup_policy=(
            "Screenshots must prove the actual intended state, not a reset/ground-level fallback.",
            "High-altitude/Ocean-Space tests should capture after ascent/outward travel when that is the feature.",
            "Entity changes should keep sparse spacing/performance rules intact.",
        ),
    ),
    "holoutopia": ProjectRuleProfile(
        name="holoutopia",
        description="Standalone HoloUtopia profile. Protects standalone data shape, citizen simulation, panels, and runtime validators.",
        protected_patterns=(
            "main.py",
            "data/HoloUtopia/**/*.py",
            "data/database/utopia/**/*.json",
            "data/HoloUtopia/tools/validate_*.py",
        ),
        validator_hints=(
            "python -m compileall -q main.py data/HoloUtopia",
        ),
        cleanup_policy=(
            "Standalone modules stay under data/HoloUtopia.",
            "Authored data stays under data/database/utopia.",
            "Debug IDs stay hidden unless debug mode is on.",
        ),
    ),
    "vector-arena": ProjectRuleProfile(
        name="vector-arena",
        description="Vector Arena / arcade shooter profile for focused same-window Panda3D gameplay passes.",
        protected_patterns=(
            "main.py",
            "runtime.py",
            "assets/**/*.py",
            "tools/validate_*.py",
        ),
        validator_hints=("python -m compileall -q .",),
        cleanup_policy=("Avoid cluttered HUD or performance-heavy effects in presentation passes.",),
    ),
    "panda3d-ai-game": ProjectRuleProfile(
        name="panda3d-ai-game",
        description="Generic profile for the user's Panda3D AI-created game projects.",
        protected_patterns=("main.py", "world.py", "runtime.py", "assets/**/*.py", "tools/validate_*.py"),
        validator_hints=("python -m compileall -q .",),
    ),
}

def as_json() -> str:
    return json.dumps({
        "schema_version": RULESET_VERSION,
        "core_rules": CORE_RULES,
        "profiles": {key: asdict(value) for key, value in PROFILES.items()},
    }, indent=2)

def write_rules_report(path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(as_json() + "\n", encoding="utf-8")
    return out

if __name__ == "__main__":
    print(as_json())
