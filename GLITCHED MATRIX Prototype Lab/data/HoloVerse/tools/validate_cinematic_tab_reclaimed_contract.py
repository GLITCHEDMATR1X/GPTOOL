#!/usr/bin/env python3
"""Validate that TAB cinematic camera reclaimed the old aircraft path.

This is a static contract check: it verifies the default HoloVerse host no
longer lets the Ember Hangar runtime monkey-patch TAB back to the saved-craft
lockout, and that TAB uses the existing shell-flight branch as a UI-clean
camera-only cinematic toggle.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
WORLD = ROOT / "world.py"
EMBER = ROOT / "Dimensions" / "Ember Hangar" / "runtime.py"

errors: list[str] = []
main = MAIN.read_text(encoding="utf-8")
world = WORLD.read_text(encoding="utf-8")
ember = EMBER.read_text(encoding="utf-8")

for path in (MAIN, WORLD, EMBER):
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        errors.append(f"syntax error in {path.relative_to(ROOT)}: {exc}")

required_main = [
    'tab_cinematic_flycam_owns_shell_flight = True',
    'self.accept("tab", self.handle_tab_action)',
    'def handle_tab_action(self):',
    'def enter_shell_flight_cinematic(self) -> bool:',
    'def exit_shell_flight_cinematic(self) -> bool:',
    'def update_shell_flight_cinematic(self, dt: float, move: Vec2, forward: Vec3, right: Vec3, up: Vec3) -> bool:',
    'self.update_shell_flight_cinematic(dt, Vec2(move), Vec3(forward), Vec3(right), Vec3(up))',
    'self.shell_flight_craft_cinematic = True',
    'self.shell_flight_craft_return_state = {',
    'self.set_shell_flight_cinematic_ui_suppressed(True)',
    'self.hide_shell_flight_cinematic_overlays()',
]
for needle in required_main:
    if needle not in main:
        errors.append(f"main.py missing {needle!r}")

# The old lockout strings may remain in dead/fallback code, but they must not be
# inside handle_tab_action now.
try:
    tree = ast.parse(main)
    class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CommandHubApp")
    handle = next(n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == "handle_tab_action")
    handle_src = ast.get_source_segment(main, handle) or ""
    for forbidden in ("AIRCRAFT LOCKED", "TAB CRAFT // DEFAULT HOLOVERSE ONLY", "has_saved_shell_flight_craft"):
        if forbidden in handle_src:
            errors.append(f"handle_tab_action still contains old aircraft gate/string: {forbidden}")
    if 'self.dispatch_native_action("tab")' not in handle_src:
        errors.append("handle_tab_action no longer preserves native TAB dispatch")
except Exception as exc:
    errors.append(f"could not inspect main.py handle_tab_action: {exc}")

required_ember = [
    'tab_cinematic_flycam_owns_shell_flight',
    'return old_handle_tab(self)',
    'return old_toggle_craft(self)',
]
for needle in required_ember:
    if needle not in ember:
        errors.append(f"Ember Hangar runtime missing defer guard {needle!r}")

required_world = [
    'self.accept("tab", self.toggle_flight_craft)',
    'self.flight_craft_cinematic = True',
    'def enter_flight_cinematic(self):',
    'def exit_flight_cinematic(self):',
    'self.set_flight_cinematic_ui_suppressed(True)',
]
for needle in required_world:
    if needle not in world:
        errors.append(f"world.py missing {needle!r}")

if errors:
    print("cinematic_tab_reclaimed_contract: FAIL")
    for err in errors:
        print(f" - {err}")
    sys.exit(1)
print("cinematic_tab_reclaimed_contract: OK")
