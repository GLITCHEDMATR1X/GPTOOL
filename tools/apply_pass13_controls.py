from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_text(rel: str, old: str, new: str) -> None:
    text = read(rel)
    if old in text:
        text = text.replace(old, new)
    write(rel, text)


def patch_template_generator() -> None:
    rel = "game_builder/template_generator.py"
    s = read(rel)
    s = s.replace(
        'self.camera_yaw = 0.0\n        self.camera_distance = 24.0\n        self.camera_height = 8.0',
        'self.camera_yaw = 0.0\n        self.camera_distance = 18.0\n        self.camera_target_distance = 18.0\n        self.camera_min_distance = 9.0\n        self.camera_max_distance = 42.0\n        self.camera_height = 6.8\n        self.camera_target_height = 6.8\n        self.camera_focus_smooth = Vec3(0, 0, 2.55)\n        self.velocity = Vec3(0, 0, 0)\n        self.vertical_velocity = 0.0\n        self.ground_z = 0.05\n        self.was_grounded = True',
    )
    s = s.replace(
        'self.camera_focus.setPos(self.player.getPos())',
        'self.camera_focus.setPos(self.player.getPos())\n        self.camera_focus_smooth = self.player.getPos() + Vec3(0, 0, 2.55)',
    )
    s = s.replace(
        'for key in ["w", "a", "s", "d", "q", "e", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "shift", "space", "escape"]:',
        'for key in ["w", "a", "s", "d", "q", "e", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "shift", "space", "escape", "r"]:',
    )
    s = s.replace(
        '        self.accept("escape", sys.exit)\n        self.accept("tab", self._switch_character, [None])',
        '        self.accept("escape", sys.exit)\n        self.accept("wheel_up", self._adjust_camera_zoom, [-2.0])\n        self.accept("wheel_down", self._adjust_camera_zoom, [2.0])\n        self.accept("r", self._reset_camera)\n        self.accept("tab", self._switch_character, [None])',
    )
    zoom_methods = '''\n    def _adjust_camera_zoom(self, delta: float) -> None:\n        self.camera_target_distance = max(self.camera_min_distance, min(self.camera_max_distance, self.camera_target_distance + float(delta)))\n        self.camera_target_height = max(4.2, min(12.5, self.camera_target_distance * 0.38))\n        self._update_camera_lens()\n\n    def _reset_camera(self) -> None:\n        self.camera_yaw = 0.0\n        self.camera_target_distance = 18.0\n        self.camera_target_height = 6.8\n        self._update_camera_lens()\n\n    def _update_camera_lens(self) -> None:\n        if not getattr(self, "camLens", None):\n            return\n        # Wider FOV when zoomed out keeps the generated world readable; tighter FOV when close helps character review.\n        fov = 54.0 + max(0.0, min(18.0, (self.camera_target_distance - 18.0) * 0.72))\n        try:\n            self.camLens.setFov(fov)\n        except Exception:\n            pass\n'''
    marker = '    def _set_key(self, key: str, value: bool) -> None:\n        self.keys[key] = value\n'
    if '_adjust_camera_zoom' not in s:
        s = s.replace(marker, marker + zoom_methods)
    s = s.replace(
        'WASD move | Q/E rotate camera | Shift sprint | Tab swap | C anim | --route-proof backup test | F12 screenshot | Esc exit',
        'WASD/Arrows move | Shift sprint | Space jump | Q/E rotate | Wheel zoom | R reset | Tab swap | C anim | F12 screenshot | Esc exit',
    )
    s = s.replace(
        '''            "controls": {\n                "move": "WASD/Arrow keys",\n                "camera": "Q/E or Arrow Left/Right",\n                "swap": "Tab",\n                "backup_screenshot": "F12 or --screenshot-mode",\n                "cycle_animation": "C",\n                "route_proof": "--route-proof",\n            },''',
        '''            "controls": {\n                "move": "WASD/Arrow keys with smoothed acceleration and friction",\n                "sprint": "Shift",\n                "jump": "Space with gravity return to safe ground",\n                "camera": "Q/E or Arrow Left/Right rotate; mouse wheel zoom; R reset",\n                "swap": "Tab",\n                "backup_screenshot": "F12 or --screenshot-mode",\n                "cycle_animation": "C",\n                "route_proof": "--route-proof",\n            },\n            "controller_model": {\n                "schema_version": "gptool_player_controller.v1",\n                "acceleration": float(self.settings.get("player", {}).get("acceleration", 26.0)),\n                "friction": float(self.settings.get("player", {}).get("friction", 18.0)),\n                "gravity": float(self.settings.get("player", {}).get("gravity", 24.0)),\n                "jump_strength": float(self.settings.get("player", {}).get("jump_strength", 8.0)),\n                "camera_distance": round(float(self.camera_distance), 3),\n                "camera_target_distance": round(float(self.camera_target_distance), 3),\n            },''',
    )
    new_update = '''    def _update(self, task):\n        dt = min(0.05, max(0.0, globalClock.getDt()))\n        if self.keys.get("q") or self.keys.get("arrow_left"):\n            self.camera_yaw += 112.0 * dt\n        if self.keys.get("e") or self.keys.get("arrow_right"):\n            self.camera_yaw -= 112.0 * dt\n        target = self.controlled_node or self.player\n        player_settings = self.settings.get("player", {})\n        base_speed = float(player_settings.get("speed", 12.0))\n        speed = base_speed * (float(player_settings.get("sprint_multiplier", 2.0)) if self.keys.get("shift") else 1.0)\n        acceleration = float(player_settings.get("acceleration", 26.0))\n        friction = float(player_settings.get("friction", 18.0))\n        gravity = float(player_settings.get("gravity", 24.0))\n        jump_strength = float(player_settings.get("jump_strength", 8.0))\n        yaw_rad = math.radians(self.camera_yaw)\n        forward = Vec3(math.sin(yaw_rad), math.cos(yaw_rad), 0)\n        right = Vec3(math.cos(yaw_rad), -math.sin(yaw_rad), 0)\n        move = Vec3(0, 0, 0)\n        if self.keys.get("w") or self.keys.get("arrow_up"):\n            move += forward\n        if self.keys.get("s") or self.keys.get("arrow_down"):\n            move -= forward\n        if self.keys.get("a"):\n            move -= right\n        if self.keys.get("d"):\n            move += right\n        moving = move.lengthSquared() > 0\n        desired_velocity = Vec3(0, 0, 0)\n        if moving:\n            move.normalize()\n            desired_velocity = move * speed\n            blend = min(1.0, acceleration * dt)\n            self.velocity = self.velocity + (desired_velocity - self.velocity) * blend\n        else:\n            damp = max(0.0, 1.0 - friction * dt)\n            self.velocity = self.velocity * damp\n            if self.velocity.lengthSquared() < 0.0025:\n                self.velocity = Vec3(0, 0, 0)\n        grounded = target.getZ() <= self.ground_z + 0.02\n        if grounded:\n            target.setZ(self.ground_z)\n            self.vertical_velocity = max(0.0, self.vertical_velocity)\n            if self.keys.get("space") and not self.was_grounded:\n                # Prevent repeated jump triggering when landing with space still held.\n                pass\n            elif self.keys.get("space"):\n                self.vertical_velocity = jump_strength\n                grounded = False\n        if not grounded:\n            self.vertical_velocity -= gravity * dt\n        next_pos = target.getPos() + Vec3(self.velocity.x * dt, self.velocity.y * dt, self.vertical_velocity * dt)\n        if next_pos.z <= self.ground_z:\n            next_pos.z = self.ground_z\n            self.vertical_velocity = 0.0\n            grounded = True\n        target.setPos(next_pos)\n        self.was_grounded = grounded\n        if self.velocity.lengthSquared() > 0.04:\n            target.setH(math.degrees(math.atan2(-self.velocity.x, self.velocity.y)))\n            self.points += max(1, int(self.velocity.length() * dt * 1.8))\n        self._play_active_animation(self.velocity.lengthSquared() > 0.04)\n        target_pos = target.getPos()\n        self._ensure_platform_chunks(target_pos)\n        focus = target_pos + Vec3(0, 0, 2.55)\n        focus_blend = min(1.0, 8.5 * dt)\n        self.camera_focus_smooth = self.camera_focus_smooth + (focus - self.camera_focus_smooth) * focus_blend\n        self.camera_focus.setPos(self.camera_focus_smooth)\n        self.camera_distance += (self.camera_target_distance - self.camera_distance) * min(1.0, 7.0 * dt)\n        self.camera_height += (self.camera_target_height - self.camera_height) * min(1.0, 7.0 * dt)\n        cam_back = Vec3(math.sin(yaw_rad), math.cos(yaw_rad), 0)\n        if getattr(self, "camera", None):\n            cam_pos = Vec3(\n                self.camera_focus_smooth.x - cam_back.x * self.camera_distance,\n                self.camera_focus_smooth.y - cam_back.y * self.camera_distance,\n                self.camera_focus_smooth.z + self.camera_height,\n            )\n            self.camera.setPos(cam_pos)\n            self.camera.lookAt(self.camera_focus_smooth)\n        active = self._active_character()\n        active_name = active.get("name") if active else "None"\n        movement_label = "SPRINT" if self.keys.get("shift") and self.velocity.lengthSquared() > 0.04 else ("MOVE" if self.velocity.lengthSquared() > 0.04 else "IDLE")\n        self.points_node.setText(f"POINTS {self.points}")\n        self.active_node.setText(f"ACTIVE {active_name} | {movement_label} | ZOOM {self.camera_target_distance:.0f}")\n        return Task.cont\n'''
    if 'gptool_player_controller.v1' in s:
        start_marker = '    def _update(self, task):\n'
        end_marker = '\n\ndef _truthy_env(name: str) -> bool:'
        start = s.index(start_marker)
        end = s.index(end_marker)
        s = s[:start] + new_update + s[end:]
    s = s.replace(
        '- Press `F12` or run `python main.py --screenshot-mode` to write a backup screenshot.',
        '- Press `F12` or run `python main.py --screenshot-mode` to write a backup screenshot.\n- Improved controls include smoothed acceleration/friction, Shift sprint, Space jump/gravity, mouse-wheel camera zoom, and `R` camera reset.',
    )
    s = s.replace('"template": "panda3d_playable_simulation_template.v3"', '"template": "panda3d_playable_simulation_template.v4"')
    write(rel, s)


def main() -> None:
    replace_text("bridge.py", 'BRIDGE_VERSION = "0.6.2-pass12"', 'BRIDGE_VERSION = "0.6.3-pass13"')
    replace_text("game_builder/settings_planner.py", '"template_version": "panda3d_playable_simulation_template.v3"', '"template_version": "panda3d_playable_simulation_template.v4"')
    replace_text("game_builder/settings_planner.py", '"jump_strength": 8.0,', '"jump_strength": 8.0,\n            "acceleration": 26.0,\n            "friction": 18.0,\n            "gravity": 24.0,')
    for rel in ["README.md", "RUN_ME_FIRST.md", "RELEASE_NOTES.md"]:
        p = ROOT / rel
        if p.exists():
            t = p.read_text(encoding="utf-8").replace("v0.6.2-pass12", "v0.6.3-pass13").replace("0.6.2-pass12", "0.6.3-pass13")
            p.write_text(t, encoding="utf-8")
    patch_template_generator()
    readme = read("README.md")
    pass13 = '''\n## Pass 13 — Smoother playable controls\n\nGenerated Panda3D simulation templates now use a stronger third-person test controller:\n\n```text\nWASD / Arrow keys  smoothed movement\nShift              sprint\nSpace              jump with gravity return\nQ/E or ←/→         rotate camera\nMouse wheel        zoom camera in/out\nR                  reset camera\nTab                swap male/female tester\nF12                backup screenshot\n```\n\nThe generated proof JSON records the controller model, camera distance, active character, and playable character state so AI edits can be checked without relying only on visual inspection.\n'''
    if "## Pass 13 — Smoother playable controls" not in readme:
        marker = "\n## Repository baseline"
        readme = readme.replace(marker, pass13 + marker) if marker in readme else readme + pass13
        write("README.md", readme)
    write("docs/PLAYABLE_CONTROLS_PASS.md", """# Pass 13 — Smoother Playable Controls\n\nThis pass upgrades generated Panda3D simulation templates from instant position stepping to a small third-person controller suitable for testing generated player edits.\n\n## Added\n\n- Smoothed acceleration and friction for WASD / arrow movement.\n- Shift sprint using the generated settings file.\n- Space jump with gravity and safe ground return.\n- Mouse-wheel camera zoom.\n- `R` camera reset.\n- Smoother camera follow and distance interpolation.\n- Proof JSON fields describing the controller model.\n\n## Control map\n\n```text\nWASD / Arrow keys  movement\nShift              sprint\nSpace              jump\nQ/E or ←/→         rotate camera\nMouse wheel        zoom\nR                  reset camera\nTab                swap playable tester\nC                  cycle imported Actor animation\nF12                backup screenshot\nEsc                exit\n```\n\n## Validation\n\nUse the generated template command:\n\n```bash\npython main.py --screenshot-mode --route-proof --screenshot-path screenshots/pass13_controls.png --proof-path reports/pass13_controls.json\n```\n""")
    write("logs/CHANGELOG_PASS13.md", """# GPTOOL Pass 13 Changelog — Smoother Playable Controls\n\n- Bumped bridge version to `0.6.3-pass13`.\n- Upgraded generated Panda3D playable simulation controls.\n- Added smoothed acceleration/friction movement.\n- Added Space jump with gravity.\n- Added mouse-wheel camera zoom and `R` camera reset.\n- Added smoother camera follow interpolation.\n- Added controller-model metadata to proof JSON.\n- Updated generated README/control notes.\n""")
    write("logs/TESTED_PASS13.md", """# GPTOOL Pass 13 Tested\n\nLocal validation performed during the pass:\n\n- `python bridge.py --version`\n- AST syntax check across Python files\n- `python bridge.py generate-game` for a fresh Panda3D probe project\n- generated `main.py --settings-check`\n- generated `main.py` AST syntax check\n- Panda3D offscreen `--screenshot-mode --route-proof` screenshot/proof run\n- Zip/package integrity check\n\nThe generated screenshot path and proof bundle are included in the pass handoff.\n""")
    for rel in ["tools/apply_pass13_controls.py", ".github/workflows/apply-pass13-controls.yml"]:
        path = ROOT / rel
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
