#!/usr/bin/env python3
"""Static contract check for TAB cinematic flycam pass.

This intentionally avoids launching Panda3D.  It verifies the main HoloVerse
input path uses TAB as a clean cinematic camera toggle while preserving native
mode TAB dispatch and preventing the old saved-aircraft requirement from owning
TAB.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
WORLD = ROOT / "world.py"

MAIN_REQUIRED_METHODS = {
    "handle_tab_action",
    "cinematic_flycam_allowed",
    "cinematic_flycam_ui_nodes",
    "set_cinematic_flycam_ui_suppressed",
    "hide_cinematic_player_overlays",
    "enter_cinematic_flycam",
    "exit_cinematic_flycam",
    "toggle_cinematic_flycam",
    "update_cinematic_flycam",
}

WORLD_REQUIRED_METHODS = {
    "cinematic_flycam_allowed",
    "set_cinematic_flycam_ui_suppressed",
    "hide_cinematic_player_overlays",
    "enter_cinematic_flycam",
    "exit_cinematic_flycam",
    "toggle_cinematic_flycam",
    "update_cinematic_flycam",
}


def method_source(text: str, tree: ast.AST, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    return ""


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    text = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(MAIN))
    methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    missing = sorted(MAIN_REQUIRED_METHODS - methods)
    if missing:
        fail(f"missing cinematic flycam methods: {', '.join(missing)}")

    handle = method_source(text, tree, "handle_tab_action")
    if 'self.dispatch_native_action("tab")' not in handle:
        fail("TAB no longer dispatches to active native modes first")
    if "self.exit_cinematic_flycam()" not in handle or "self.enter_cinematic_flycam()" not in handle:
        fail("TAB does not enter/exit cinematic flycam directly")
    if "has_saved_shell_flight_craft" in handle or "toggle_shell_flight_craft" in handle:
        fail("TAB is still coupled to saved Ember aircraft logic")
    if 'self.center_hint["text"]' in handle:
        fail("TAB path emits center-hint UI text")

    refresh = method_source(text, tree, "refresh_ui")
    if 'cinematic_flycam_active' not in refresh or 'set_cinematic_flycam_ui_suppressed(True)' not in refresh:
        fail("refresh_ui does not keep UI suppressed during cinematic flycam")

    update_player = method_source(text, tree, "update_player")
    call = "self.update_cinematic_flycam(dt, Vec2(move), Vec3(forward), Vec3(right), Vec3(up))"
    if call not in update_player:
        fail("update_player does not run the cinematic flycam movement path")
    if update_player.find(call) > update_player.find("if self.is_holospace_active()"):
        fail("cinematic flycam runs after HoloSpace ship movement instead of before it")

    enter = method_source(text, tree, "enter_cinematic_flycam")
    for token in ("cinematic_flycam_return_state", "hide_cinematic_player_overlays", "set_cinematic_flycam_ui_suppressed(True)"):
        if token not in enter:
            fail(f"enter_cinematic_flycam missing {token}")

    exit_src = method_source(text, tree, "exit_cinematic_flycam")
    for token in ("player_pos", "player_yaw", "player_pitch", "camera.setPos", "camera.setHpr"):
        if token not in exit_src:
            fail(f"exit_cinematic_flycam missing return restore token {token}")

    hide = method_source(text, tree, "hide_cinematic_player_overlays")
    for token in ("shell_flight_craft_active", "show_holospace_cockpit(False)", "show_deep_water_hoverboard(False)", "weapon_root"):
        if token not in hide:
            fail(f"player overlay cleanup missing {token}")

    for input_method in ("primary_click_interact", "native_mouse3_down", "on_e_down", "on_q_down", "start_escape_hold", "toggle_menu", "toggle_help_overlay", "handle_h_action"):
        src = method_source(text, tree, input_method)
        if 'cinematic_flycam_active' not in src:
            fail(f"{input_method} can still trigger gameplay/UI while flycam is active")

    world_text = WORLD.read_text(encoding="utf-8")
    world_tree = ast.parse(world_text, filename=str(WORLD))
    world_methods = {node.name for node in ast.walk(world_tree) if isinstance(node, ast.FunctionDef)}
    missing_world = sorted(WORLD_REQUIRED_METHODS - world_methods)
    if missing_world:
        fail(f"world.py missing standalone cinematic methods: {', '.join(missing_world)}")
    if 'self.accept("tab", self.toggle_cinematic_flycam)' not in world_text:
        fail("standalone world.py TAB still does not bind to cinematic flycam")
    if 'self.accept("tab", self.toggle_flight_craft)' in world_text:
        fail("standalone world.py TAB still binds to old craft flight")
    world_refresh = method_source(world_text, world_tree, "refresh_ui")
    if 'cinematic_flycam_active' not in world_refresh or 'set_cinematic_flycam_ui_suppressed(True)' not in world_refresh:
        fail("world.py refresh_ui does not keep UI suppressed during cinematic flycam")
    world_update = method_source(world_text, world_tree, "update_player")
    if "self.update_cinematic_flycam(dt, Vec2(move), Vec3(forward), Vec3(right), Vec3(up))" not in world_update:
        fail("world.py update_player does not run cinematic flycam")
    if world_update.find("update_cinematic_flycam") > world_update.find("update_flight_craft"):
        fail("world.py cinematic flycam runs after old craft movement")
    world_hide = method_source(world_text, world_tree, "hide_cinematic_player_overlays")
    for token in ("flight_craft_active", "weapon_root", "hide_underwater_vehicle"):
        if token not in world_hide:
            fail(f"world.py overlay cleanup missing {token}")
    for input_method in ("on_mouse1_down", "on_mouse3_down", "interact", "core_secondary_action", "toggle_menu"):
        src = method_source(world_text, world_tree, input_method)
        if 'cinematic_flycam_active' not in src:
            fail(f"world.py {input_method} can still trigger gameplay/UI while flycam is active")


    if 'if bool(getattr(self, "cinematic_flycam_active", False)):' not in handle:
        fail("TAB handler must allow active flycam to exit before menu/native gates")
    if 'transition_target > 0.0' in handle or 'self.world_unlocked' in handle:
        fail("TAB handler still inherits aircraft/default-world gates")

    allowed = method_source(text, tree, "cinematic_flycam_allowed")
    if 'self.world_unlocked' in allowed or 'transition_target > 0.0' in allowed:
        fail("flycam allowed gate still blocks legacy/world-shell presentation states")

    print("PASS: cinematic flycam TAB contract hotfix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
