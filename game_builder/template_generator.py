from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(text: str, default: str = "panda3d_game") -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default


def _safe_write(path: Path, content: str, *, overwrite: bool = False) -> dict[str, Any]:
    if path.exists() and not overwrite:
        return {"path": str(path), "written": False, "reason": "exists"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": str(path), "written": True}


def _safe_write_json(path: Path, payload: Any, *, overwrite: bool = False) -> dict[str, Any]:
    return _safe_write(path, json.dumps(payload, indent=2) + "\n", overwrite=overwrite)


def _main_py_template() -> str:
    # Kept as a plain string so generated projects do not depend on this bridge package.
    return r'''from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "settings" / "game_settings.json"
HUMAN_MANIFEST_PATH = BASE_DIR / "assets" / "characters" / "humans" / "human_manifest.json"


def _arg_value(flag: str, default: str | None = None) -> str | None:
    if flag not in sys.argv:
        return default
    index = sys.argv.index(flag)
    if index + 1 >= len(sys.argv):
        return default
    return sys.argv[index + 1]


def _strip_generated_cli_args() -> None:
    takes_value = {"--screenshot-path", "--proof-path", "--window-type"}
    filtered = [sys.argv[0]]
    skip_next = False
    for item in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if item in {"--screenshot-mode", "--route-proof", "--simulation-route-proof"}:
            continue
        if item in takes_value:
            skip_next = True
            continue
        filtered.append(item)
    sys.argv[:] = filtered


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _prepare_screenshot_mode() -> None:
    route_requested = "--route-proof" in sys.argv or "--simulation-route-proof" in sys.argv
    if "--screenshot-mode" not in sys.argv and not route_requested:
        return
    screenshot_path = _arg_value("--screenshot-path") or str(BASE_DIR / "screenshots" / "simulation_mode_backup.png")
    proof_path = _arg_value("--proof-path") or str(BASE_DIR / "reports" / "simulation_mode_scene_proof.json")
    window_type = _arg_value("--window-type") or "offscreen"
    os.environ.setdefault("GPT_BRIDGE_TEST_MODE", "1")
    os.environ.setdefault("GPT_BRIDGE_SMOKE", "1")
    os.environ.setdefault("GPT_BRIDGE_SCREENSHOT_PATH", screenshot_path)
    os.environ.setdefault("GPT_BRIDGE_SMOKE_PROOF_PATH", proof_path)
    os.environ.setdefault("GPT_BRIDGE_WINDOW_TYPE", window_type)
    os.environ.setdefault("GPT_BRIDGE_SMOKE_FRAMES", "64" if route_requested else "8")
    if route_requested:
        os.environ.setdefault("GPT_BRIDGE_SIMULATION_ROUTE_PROOF", "1")
    os.environ.setdefault("GPT_BRIDGE_EXIT_AFTER_SCREENSHOT", "1")
    print(f"GPT_SIMULATION_SCREENSHOT_MODE: screenshot={screenshot_path}", flush=True)
    print(f"GPT_SIMULATION_SCREENSHOT_MODE: proof={proof_path}", flush=True)
    if route_requested:
        print("GPT_SIMULATION_ROUTE_PROOF_MODE: enabled", flush=True)
    _strip_generated_cli_args()


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        raise FileNotFoundError(f"Missing settings file: {SETTINGS_PATH}")
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def settings_check() -> int:
    settings = load_settings()
    project = settings.get("project", {})
    world = settings.get("world", {})
    regions = world.get("regions", [])
    simulation = settings.get("simulation", {})
    sim_chars = simulation.get("characters", [])
    print(f"Settings OK: {project.get('title', 'Untitled')} regions={len(regions)} simulation_characters={len(sim_chars)}")
    if len(sim_chars) < 2:
        print("Settings warning: playable simulation mode expects two test characters.", file=sys.stderr)
        return 1
    return 0


if "--settings-check" in sys.argv:
    raise SystemExit(settings_check())

_prepare_screenshot_mode()

try:
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    from direct.task import Task
    from panda3d.core import AmbientLight, CardMaker, DirectionalLight, Filename, LColor, LineSegs, NodePath, TextNode, TransparencyAttrib, Vec3, loadPrcFileData
except Exception as exc:
    print("Panda3D is required to run this generated template.", file=sys.stderr)
    print("Install with: python -m pip install panda3d", file=sys.stderr)
    print(f"Import error: {exc}", file=sys.stderr)
    raise SystemExit(1)

_window_type_hint = os.environ.get("GPT_BRIDGE_WINDOW_TYPE", "default").strip().lower()
if _window_type_hint == "offscreen":
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "load-display p3tinydisplay")
    loadPrcFileData("", "audio-library-name null")
elif _window_type_hint == "none":
    loadPrcFileData("", "audio-library-name null")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "window-title GPTOOL Playable Simulation Mode")
loadPrcFileData("", "framebuffer-multisample 1")
loadPrcFileData("", "multisamples 4")


class GeneratedGame(ShowBase):
    def __init__(self) -> None:
        requested_window_type = os.environ.get("GPT_BRIDGE_WINDOW_TYPE", "").strip().lower()
        if requested_window_type in {"none", "offscreen"}:
            super().__init__(windowType=requested_window_type)
        else:
            super().__init__()
        self.settings = load_settings()
        self.human_manifest = self._load_human_manifest()
        self.disableMouse()
        self.setBackgroundColor(0.055, 0.065, 0.085, 1)
        self.keys: dict[str, bool] = {}
        self.points = 0
        self.platform_chunks: dict[tuple[int, int], NodePath] = {}
        self.chunk_size = 36
        self.camera_yaw = 0.0
        self.camera_distance = 18.0
        self.camera_target_distance = 18.0
        self.camera_min_distance = 9.0
        self.camera_max_distance = 42.0
        self.camera_height = 6.8
        self.camera_target_height = 6.8
        self.camera_focus_smooth = Vec3(0, 0, 2.55)
        self.velocity = Vec3(0, 0, 0)
        self.vertical_velocity = 0.0
        self.ground_z = 0.05
        self.was_grounded = True
        self.simulation_characters: list[dict] = []
        self.active_character_index = 0
        self.preview_actor = None
        self.preview_asset_index = 0
        self.preview_anim_index = 0
        self.simulation_route_events: list[dict] = []
        self.simulation_route_summary: dict = {}
        self.route_proof_completed = False
        self.route_marker_count = 0
        self.player = self.render.attachNewNode("legacy_player_anchor")
        self.controlled_node = self.player
        self.camera_focus = self.render.attachNewNode("camera_focus")
        spawn = self.settings.get("world", {}).get("spawn", {}).get("position", [0, 0, 2])
        self.player.setPos(float(spawn[0]), float(spawn[1]), float(spawn[2]))
        self.camera_focus.setPos(self.player.getPos())
        self.camera_focus_smooth = self.player.getPos() + Vec3(0, 0, 2.55)
        self._bind_controls()
        self._build_lights()
        self._build_world()
        self._build_simulation_characters()
        self._build_support_characters()
        self._build_ui()
        self._switch_character(0, announce=False)
        self.taskMgr.add(self._update, "generated_playable_simulation_update")
        self._install_simulation_route_proof()
        self._install_smoke_capture()

    def _bind_controls(self) -> None:
        for key in ["w", "a", "s", "d", "q", "e", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "shift", "space", "escape", "r"]:
            self.accept(key, self._set_key, [key, True])
            self.accept(key + "-up", self._set_key, [key, False])
        self.accept("escape", sys.exit)
        self.accept("wheel_up", self._adjust_camera_zoom, [-2.0])
        self.accept("wheel_down", self._adjust_camera_zoom, [2.0])
        self.accept("r", self._reset_camera)
        self.accept("tab", self._switch_character, [None])
        self.accept("f12", self._manual_screenshot)
        self.accept("[", self._cycle_human_asset, [-1])
        self.accept("]", self._cycle_human_asset, [1])
        self.accept("c", self._cycle_preview_animation, [1])

    def _set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def _build_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.58, 0.62, 0.68, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        key = DirectionalLight("key")
        key.setColor((1.0, 0.98, 0.9, 1))
        key_np = self.render.attachNewNode(key)
        key_np.setHpr(-32, -38, 0)
        self.render.setLight(key_np)
        fill = DirectionalLight("fill")
        fill.setColor((0.25, 0.38, 0.56, 1))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(150, -18, 0)
        self.render.setLight(fill_np)

    def _load_human_manifest(self) -> dict:
        if not HUMAN_MANIFEST_PATH.exists():
            return {}
        try:
            return json.loads(HUMAN_MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _panda_asset_path(self, rel_path: str) -> str:
        return Filename.fromOsSpecific(str((BASE_DIR / rel_path).resolve())).getFullpath()

    def _human_animation_library(self) -> dict[str, str]:
        library: dict[str, str] = {}
        for item in self.human_manifest.get("animations", []) or []:
            rel_path = item.get("relative_path")
            if not rel_path:
                continue
            key = item.get("role") or item.get("id") or Path(rel_path).stem
            key = str(key).lower().replace(" ", "_")
            library[key] = self._panda_asset_path(rel_path)
        return library

    def _find_human_asset(self, char: dict, index: int) -> dict | None:
        assets = self.human_manifest.get("base_assets", []) or []
        if not assets:
            return None
        requested = char.get("asset_manifest_id")
        if requested:
            for asset in assets:
                if asset.get("id") == requested:
                    return asset
        return assets[index % len(assets)]

    def _choose_anim(self, names: list[str]) -> str:
        for wanted in ("idle", "walk", "run", "nlatrack"):
            for name in names:
                if wanted in name.lower():
                    return name
        return names[0] if names else ""

    def _play_active_animation(self, moving: bool) -> None:
        char = self._active_character()
        actor = char.get("actor") if char else None
        if actor is None or not hasattr(actor, "getAnimNames"):
            return
        try:
            names = list(actor.getAnimNames())
        except Exception:
            return
        if not names:
            return
        preferred = ("run", "walk", "nlatrack") if moving else ("idle", "nlatrack")
        current = ""
        try:
            current = actor.getCurrentAnim() or ""
        except Exception:
            pass
        for token in preferred:
            for name in names:
                if token in name.lower() and name != current:
                    try:
                        actor.loop(name)
                    except Exception:
                        pass
                    return

    def _load_human_actor(self, char: dict, index: int) -> NodePath | None:
        asset = self._find_human_asset(char, index)
        if not asset:
            return None
        rel_path = asset.get("relative_path")
        if not rel_path:
            return None
        model_path = self._panda_asset_path(rel_path)
        animation_library = self._human_animation_library()
        for args in ((model_path,), (model_path, animation_library)):
            try:
                actor = Actor(*args)
                names = actor.getAnimNames()
                chosen = self._choose_anim(list(names))
                if chosen:
                    actor.loop(chosen)
                actor.setTwoSided(True)
                return actor
            except Exception:
                pass
        try:
            model = self.loader.loadModel(model_path)
            model.setTwoSided(True)
            return model
        except Exception:
            return None

    def _model_bounds(self, node: NodePath):
        try:
            bounds = node.getTightBounds()
        except Exception:
            return None
        if not bounds or bounds[0] is None or bounds[1] is None:
            return None
        return bounds

    def _fit_character_model(self, node: NodePath, target_height: float = 3.2) -> None:
        node.setScale(1)
        bounds = self._model_bounds(node)
        if not bounds:
            return
        size = bounds[1] - bounds[0]
        if size.z <= 0.01:
            return
        node.setScale(target_height / float(size.z))
        node.setZ(node.getZ() - float(bounds[0].z) * node.getScale().z)

    def _make_card(self, name: str, width: float, height: float, color: list[float]) -> NodePath:
        cm = CardMaker(name)
        cm.setFrame(-width / 2, width / 2, -height / 2, height / 2)
        np = self.render.attachNewNode(cm.generate())
        np.setP(-90)
        np.setColor(*color)
        return np

    def _build_grid(self, parent: NodePath, size: int, step: int, color: list[float]) -> None:
        lines = LineSegs()
        lines.setThickness(1.4)
        lines.setColor(color[0], color[1], color[2], 0.72)
        half = size // 2
        for x in range(-half, half + 1, step):
            lines.moveTo(x, -half, 0.04)
            lines.drawTo(x, half, 0.04)
        for y in range(-half, half + 1, step):
            lines.moveTo(-half, y, 0.04)
            lines.drawTo(half, y, 0.04)
        parent.attachNewNode(lines.create())

    def _create_platform_chunk(self, ix: int, iy: int) -> NodePath:
        root = self.world_root.attachNewNode(f"chunk_{ix}_{iy}")
        root.setPos(ix * self.chunk_size, iy * self.chunk_size, 0)
        shade = 0.105 + (((ix * 13 + iy * 7) % 3) * 0.018)
        ground = self._make_card(f"ground_{ix}_{iy}", self.chunk_size, self.chunk_size, [shade, shade + 0.015, shade + 0.03, 1])
        ground.reparentTo(root)
        self._build_grid(root, self.chunk_size, 6, [0.0, 0.72, 0.95, 1])
        return root

    def _ensure_platform_chunks(self, center: Vec3) -> None:
        ix = int(math.floor((center.x + self.chunk_size / 2) / self.chunk_size))
        iy = int(math.floor((center.y + self.chunk_size / 2) / self.chunk_size))
        wanted = {(x, y) for x in range(ix - 2, ix + 3) for y in range(iy - 2, iy + 3)}
        for key in wanted:
            if key not in self.platform_chunks:
                self.platform_chunks[key] = self._create_platform_chunk(*key)
        for key in list(self.platform_chunks):
            if key not in wanted:
                self.platform_chunks[key].removeNode()
                del self.platform_chunks[key]

    def _build_world(self) -> None:
        self.world_root = self.render.attachNewNode("simulation_streaming_platform")
        self._ensure_platform_chunks(Vec3(0, 0, 0))
        world = self.settings.get("world", {})
        regions = world.get("regions", [])
        spacing = 60
        for idx, region in enumerate(regions):
            root = self.render.attachNewNode(f"region_{region.get('id', idx)}")
            x = (idx % 3 - 1) * spacing
            if len(regions) == 1:
                x = 0
            y = (idx // 3) * spacing + 32
            root.setPos(x, y, 0)
            color = region.get("color", [0.0, 0.85, 1.0, 1.0])
            terrain = region.get("terrain", "flat_grid")
            if terrain != "space_void":
                ground = self._make_card(f"ground_{region.get('id', idx)}", 44, 44, [0.12, 0.13, 0.16, 1])
                ground.reparentTo(root)
                self._build_grid(root, 44, 4, [color[0], color[1], color[2], 1])
            self._add_region_landmarks(root, region, color)
            self._add_label(root, region.get("name", "Region"), pos=(0, -24, 3), scale=1.25, color=color)

    def _add_region_landmarks(self, root: NodePath, region: dict, color: list[float]) -> None:
        terrain = region.get("terrain", "")
        rid = region.get("id", "region")
        if terrain in {"tall_city", "urban_blocks"}:
            for i in range(8):
                cube = self.loader.loadModel("models/box")
                cube.reparentTo(root)
                cube.setScale(2.5, 2.5, 2 + (i % 4) * 1.7)
                cube.setPos(-15 + i * 4.4, 4 + (i % 2) * 7, cube.getSz() / 2)
                cube.setColor(color[0], color[1], color[2], 1)
        elif terrain == "rolling_hills":
            for i in range(7):
                hill = self.loader.loadModel("models/smiley")
                hill.reparentTo(root)
                hill.setScale(2.2 + (i % 3), 2.2 + (i % 3), 0.65)
                hill.setPos(-16 + i * 5.5, 8 if i % 2 else -3, 0.8)
                hill.setColor(color[0], color[1], color[2], 1)
        elif terrain == "sand_grid":
            for i in range(3):
                pyr = self.loader.loadModel("models/box")
                pyr.reparentTo(root)
                pyr.setScale(3.2 - i * 0.45, 3.2 - i * 0.45, 1.0 + i * 0.8)
                pyr.setPos(-8 + i * 8, 6, 1 + i * 0.8)
                pyr.setH(45)
                pyr.setColor(color[0], color[1], color[2], 1)
        elif terrain in {"forest_grid", "ice_cubes"}:
            for i in range(10):
                obj = self.loader.loadModel("models/box")
                obj.reparentTo(root)
                height = 2 + (i % 5)
                obj.setScale(0.8, 0.8, height)
                obj.setPos(-18 + (i % 5) * 8, -12 + (i // 5) * 12, height)
                obj.setColor(color[0], color[1], color[2], 1)
        elif terrain == "deep_water":
            water = self._make_card(f"water_{rid}", 40, 40, [color[0], color[1], color[2], 0.55])
            water.reparentTo(root)
            water.setTransparency(TransparencyAttrib.MAlpha)

    def _add_label(self, parent: NodePath, text: str, *, pos: tuple[float, float, float], scale: float, color: list[float]) -> None:
        node = TextNode(f"label_{text}")
        node.setText(text)
        node.setAlign(TextNode.ACenter)
        np = parent.attachNewNode(node)
        np.setPos(*pos)
        np.setScale(scale)
        np.setHpr(0, -35, 0)
        np.setColor(color[0], color[1], color[2], 1)

    def _make_marker_ring(self, parent: NodePath, name: str, color: list[float]) -> NodePath:
        lines = LineSegs()
        lines.setThickness(3.0)
        lines.setColor(color[0], color[1], color[2], 1)
        radius = 1.65
        steps = 48
        for i in range(steps + 1):
            a = (math.pi * 2.0) * (i / steps)
            x = math.cos(a) * radius
            y = math.sin(a) * radius
            if i == 0:
                lines.moveTo(x, y, 0.08)
            else:
                lines.drawTo(x, y, 0.08)
        return parent.attachNewNode(lines.create())

    def _make_procedural_humanoid(self, char_id: str, name: str, gender_profile: str, color: list[float]) -> NodePath:
        root = self.render.attachNewNode(char_id)
        height_scale = 1.0 if gender_profile == "male" else 0.94
        shoulder = 1.0 if gender_profile == "male" else 0.86
        body = self.loader.loadModel("models/box")
        body.reparentTo(root)
        body.setScale(0.62 * shoulder, 0.48, 1.55 * height_scale)
        body.setPos(0, 0, 2.05 * height_scale)
        body.setColor(color[0], color[1], color[2], 1)
        head = self.loader.loadModel("models/smiley")
        head.reparentTo(root)
        head.setScale(0.52, 0.52, 0.52)
        head.setPos(0, 0, 3.85 * height_scale)
        head.setColor(0.92, 0.92, 0.86, 1)
        for side in (-1, 1):
            arm = self.loader.loadModel("models/box")
            arm.reparentTo(root)
            arm.setScale(0.18, 0.18, 0.95 * height_scale)
            arm.setPos(side * shoulder, 0, 2.08 * height_scale)
            arm.setColor(color[0] * 0.8, color[1] * 0.8, color[2] * 0.8, 1)
            leg = self.loader.loadModel("models/box")
            leg.reparentTo(root)
            leg.setScale(0.22, 0.22, 0.8 * height_scale)
            leg.setPos(side * 0.28, 0, 0.78 * height_scale)
            leg.setColor(color[0] * 0.55, color[1] * 0.55, color[2] * 0.55, 1)
        root.setTwoSided(True)
        self._make_marker_ring(root, f"{char_id}_ring", color)
        self._add_label(root, name, pos=(0, 0, 4.65 * height_scale), scale=0.45, color=color)
        return root

    def _build_simulation_characters(self) -> None:
        simulation = self.settings.get("simulation", {}) or {}
        sim_chars = simulation.get("characters") or [
            {"id": "playable_male", "name": "Male Simulation Tester", "gender_profile": "male", "spawn": [-2.2, 2.0, 0.05], "active_by_default": True},
            {"id": "playable_female", "name": "Female Simulation Tester", "gender_profile": "female", "spawn": [2.2, 2.0, 0.05], "active_by_default": False},
        ]
        palette = {
            "male": [0.0, 0.84, 1.0, 1.0],
            "female": [0.78, 0.28, 1.0, 1.0],
        }
        for idx, char in enumerate(sim_chars[:2]):
            gender = str(char.get("gender_profile") or ("male" if idx == 0 else "female")).lower()
            color = palette.get(gender, [0.0, 0.85, 1.0, 1.0])
            node = self._make_procedural_humanoid(str(char.get("id") or f"playable_{idx+1}"), str(char.get("name") or f"Simulation Tester {idx+1}"), gender, color)
            spawn = char.get("spawn") or [idx * 4 - 2, 2, 0.05]
            node.setPos(float(spawn[0]), float(spawn[1]), float(spawn[2]))
            entry = dict(char)
            entry.update({"node": node, "color": color, "gender_profile": gender, "actor": None})
            self.simulation_characters.append(entry)
            if char.get("active_by_default"):
                self.active_character_index = idx
        if self.simulation_characters:
            self.controlled_node = self.simulation_characters[self.active_character_index]["node"]

    def _build_support_characters(self) -> None:
        if self.human_manifest.get("base_assets"):
            return
        chars = [c for c in self.settings.get("characters", []) if str(c.get("id", "")).lower() not in {"playable_male", "playable_female"}]
        for idx, char in enumerate(chars[:4]):
            model_name = "models/smiley" if idx % 2 else "models/box"
            try:
                actor = self.loader.loadModel(model_name)
            except Exception:
                continue
            actor.reparentTo(self.render)
            actor.setPos(-9 + idx * 5, 10, 1.05)
            actor.setScale(0.9 if model_name == "models/smiley" else 1.15)
            color = char.get("color", [0.0, 0.85, 1.0, 1.0])
            actor.setColor(color[0], color[1], color[2], 1)
            self._add_label(actor, char.get("name", "Support Character"), pos=(0, 0, 2.5), scale=0.5, color=color)

    def _build_ui(self) -> None:
        project = self.settings.get("project", {})
        self.title_node = TextNode("title")
        self.title_node.setText(project.get("title", "Generated Panda3D Game"))
        self.title_node.setAlign(TextNode.ALeft)
        self.title_np = self.aspect2d.attachNewNode(self.title_node)
        self.title_np.setScale(0.052)
        self.title_np.setPos(-1.28, 0, 0.88)
        self.title_np.setColor(0.86, 0.94, 1.0, 1)

        self.points_node = TextNode("points")
        self.points_node.setAlign(TextNode.ARight)
        self.points_np = self.aspect2d.attachNewNode(self.points_node)
        self.points_np.setScale(0.043)
        self.points_np.setPos(1.28, 0, 0.88)
        self.points_np.setColor(0.86, 0.94, 1.0, 1)

        self.active_node = TextNode("active_character")
        self.active_node.setAlign(TextNode.ALeft)
        self.active_np = self.aspect2d.attachNewNode(self.active_node)
        self.active_np.setScale(0.041)
        self.active_np.setPos(-1.28, 0, 0.80)
        self.active_np.setColor(1.0, 0.96, 0.56, 1)

        self.help_node = TextNode("help")
        self.help_node.setText("WASD/Arrows move | Shift sprint | Space jump | Q/E rotate | Wheel zoom | R reset | Tab swap | C anim | F12 screenshot | Esc exit")
        self.help_node.setAlign(TextNode.ALeft)
        self.help_np = self.aspect2d.attachNewNode(self.help_node)
        self.help_np.setScale(0.031)
        self.help_np.setPos(-1.28, 0, -0.91)
        self.help_np.setColor(0.84, 0.92, 1.0, 0.92)

    def _active_character(self) -> dict | None:
        if not self.simulation_characters:
            return None
        return self.simulation_characters[self.active_character_index % len(self.simulation_characters)]

    def _switch_character(self, index: int | None = None, announce: bool = True) -> None:
        if not self.simulation_characters:
            return
        if index is None:
            self.active_character_index = (self.active_character_index + 1) % len(self.simulation_characters)
        else:
            self.active_character_index = int(index) % len(self.simulation_characters)
        for idx, char in enumerate(self.simulation_characters):
            node = char["node"]
            if idx == self.active_character_index:
                node.setColorScale(1.18, 1.18, 1.18, 1.0)
            else:
                node.setColorScale(0.65, 0.65, 0.65, 0.88)
        active = self._active_character()
        self.controlled_node = active["node"] if active else self.player
        if announce and active:
            print(f"GPT_SIMULATION_ACTIVE_CHARACTER: {active.get('id')} ({active.get('name')})", flush=True)

    def _cycle_human_asset(self, delta: int) -> None:
        # Kept for imported-human workflows. Procedural simulation characters stay active.
        assets = self.human_manifest.get("base_assets", []) or []
        if not assets:
            return
        self.preview_asset_index = (self.preview_asset_index + delta) % len(assets)

    def _cycle_preview_animation(self, delta: int) -> None:
        self.preview_anim_index += delta

    def _route_proof_requested(self) -> bool:
        return str(os.environ.get("GPT_BRIDGE_SIMULATION_ROUTE_PROOF") or "").lower() in {"1", "true", "yes", "on"}

    def _character_positions_snapshot(self) -> dict:
        return {
            str(item.get("id")): [round(float(v), 3) for v in item["node"].getPos()]
            for item in self.simulation_characters
        }

    def _drop_route_marker(self, owner_id: str, color: list[float]) -> None:
        active = self._active_character()
        if not active:
            return
        try:
            marker = self.loader.loadModel("models/box")
            marker.reparentTo(self.render)
            marker.setScale(0.18, 0.18, 0.08)
            pos = active["node"].getPos()
            marker.setPos(pos.x, pos.y, 0.12)
            marker.setColor(color[0], color[1], color[2], 0.92)
            marker.setName(f"route_marker_{owner_id}_{self.route_marker_count:03d}")
            self.route_marker_count += 1
        except Exception:
            pass

    def _install_simulation_route_proof(self) -> None:
        if not self._route_proof_requested() or len(self.simulation_characters) < 2:
            return
        state = {
            "frame": 0,
            "start_positions": self._character_positions_snapshot(),
            "swap_count": 0,
        }

        def route_task(task):
            state["frame"] += 1
            frame = state["frame"]
            if frame == 1:
                self._switch_character(0, announce=True)
                self.simulation_route_events.append({"frame": frame, "event": "active_start", "character": "playable_male"})
            if 4 <= frame <= 22:
                active = self._active_character()
                if active:
                    active["node"].setY(active["node"].getY() + 0.24)
                    active["node"].setH(0)
                    self.points += 1
                    if frame in {4, 10, 16, 22}:
                        self._drop_route_marker(str(active.get("id")), active.get("color", [0.0, 0.84, 1.0, 1.0]))
            if frame == 28:
                self._switch_character(1, announce=True)
                state["swap_count"] += 1
                self.simulation_route_events.append({"frame": frame, "event": "tab_swap_simulated", "character": "playable_female"})
            if 32 <= frame <= 50:
                active = self._active_character()
                if active:
                    active["node"].setX(active["node"].getX() + 0.24)
                    active["node"].setH(-90)
                    self.points += 1
                    if frame in {32, 38, 44, 50}:
                        self._drop_route_marker(str(active.get("id")), active.get("color", [0.78, 0.28, 1.0, 1.0]))
            if frame == 56:
                state["end_positions"] = self._character_positions_snapshot()
                self.route_proof_completed = True
                self.simulation_route_summary = {
                    "enabled": True,
                    "completed": True,
                    "frames": frame,
                    "swap_count": state["swap_count"],
                    "start_positions": state["start_positions"],
                    "end_positions": state["end_positions"],
                    "route_marker_count": self.route_marker_count,
                    "events": list(self.simulation_route_events),
                }
                print("GPT_SIMULATION_ROUTE_PROOF_COMPLETE", flush=True)
                return Task.done
            return Task.cont

        self.taskMgr.add(route_task, "gpt_simulation_route_proof")
        print("GPT_SIMULATION_ROUTE_PROOF_INSTALLED", flush=True)

    def run_simulation_route_proof_now(self) -> None:
        if len(self.simulation_characters) < 2:
            self._write_fallback_scene_proof(os.environ.get("GPT_BRIDGE_SCREENSHOT_PATH"), False)
            return
        start_positions = self._character_positions_snapshot()
        self.simulation_route_events = []
        self.route_marker_count = 0
        self._switch_character(0, announce=True)
        self.simulation_route_events.append({"step": 1, "event": "active_start", "character": "playable_male"})
        for step in range(1, 20):
            active = self._active_character()
            active["node"].setY(active["node"].getY() + 0.24)
            active["node"].setH(0)
            self.points += 1
            if step in {1, 7, 13, 19}:
                self._drop_route_marker(str(active.get("id")), active.get("color", [0.0, 0.84, 1.0, 1.0]))
        self._switch_character(1, announce=True)
        self.simulation_route_events.append({"step": 21, "event": "tab_swap_simulated", "character": "playable_female"})
        for step in range(1, 20):
            active = self._active_character()
            active["node"].setX(active["node"].getX() + 0.24)
            active["node"].setH(-90)
            self.points += 1
            if step in {1, 7, 13, 19}:
                self._drop_route_marker(str(active.get("id")), active.get("color", [0.78, 0.28, 1.0, 1.0]))
        end_positions = self._character_positions_snapshot()
        self.route_proof_completed = True
        self.simulation_route_summary = {
            "enabled": True,
            "completed": True,
            "mode": "synchronous_backup_route",
            "swap_count": 1,
            "start_positions": start_positions,
            "end_positions": end_positions,
            "route_marker_count": self.route_marker_count,
            "events": list(self.simulation_route_events),
        }
        active = self._active_character()
        active_name = active.get("name") if active else "None"
        self.points_node.setText(f"POINTS {self.points}")
        self.active_node.setText(f"ACTIVE {active_name}")
        points = [item["node"].getPos() for item in self.simulation_characters]
        mid = Vec3(sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points), 2.6)
        self._ensure_platform_chunks(mid)
        if getattr(self, "camera", None):
            self.camera.setPos(mid.x, mid.y - 24.0, mid.z + 9.5)
            self.camera.lookAt(mid)
        screenshot_path = os.environ.get("GPT_BRIDGE_SCREENSHOT_PATH")
        screenshot_exists = False
        if screenshot_path:
            out = Path(screenshot_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.graphicsEngine.renderFrame()
                self.graphicsEngine.renderFrame()
            except Exception:
                pass
            if getattr(self, "win", None):
                self.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
                screenshot_exists = out.exists()
        self._write_fallback_scene_proof(screenshot_path, screenshot_exists)
        print("GPT_SIMULATION_ROUTE_PROOF_COMPLETE", flush=True)

    def _manual_screenshot(self) -> None:
        out = BASE_DIR / "screenshots" / f"manual_simulation_backup_{_timestamp()}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.graphicsEngine.renderFrame()
        except Exception:
            pass
        if getattr(self, "win", None):
            self.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
            print(f"GPT_SIMULATION_BACKUP_SCREENSHOT_WRITTEN: {out}", flush=True)
        else:
            print("GPT_SIMULATION_BACKUP_SCREENSHOT_SKIPPED: no active Panda3D window", flush=True)

    def gpt_bridge_scene_state(self) -> dict:
        active = self._active_character()
        return {
            "mode": "playable_character_edit_test",
            "controls": {
                "move": "WASD/Arrow keys with smoothed acceleration and friction",
                "sprint": "Shift",
                "jump": "Space with gravity return to safe ground",
                "camera": "Q/E or Arrow Left/Right rotate; mouse wheel zoom; R reset",
                "swap": "Tab",
                "backup_screenshot": "F12 or --screenshot-mode",
                "cycle_animation": "C",
                "route_proof": "--route-proof",
            },
            "controller_model": {
                "schema_version": "gptool_player_controller.v1",
                "acceleration": float(self.settings.get("player", {}).get("acceleration", 26.0)),
                "friction": float(self.settings.get("player", {}).get("friction", 18.0)),
                "gravity": float(self.settings.get("player", {}).get("gravity", 24.0)),
                "jump_strength": float(self.settings.get("player", {}).get("jump_strength", 8.0)),
                "camera_distance": round(float(self.camera_distance), 3),
                "camera_target_distance": round(float(self.camera_target_distance), 3),
            },
            "playable_character_count": len(self.simulation_characters),
            "active_character_id": active.get("id") if active else None,
            "active_character_name": active.get("name") if active else None,
            "characters": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "gender_profile": item.get("gender_profile"),
                    "active": idx == self.active_character_index,
                    "position": [round(float(v), 3) for v in item["node"].getPos()],
                }
                for idx, item in enumerate(self.simulation_characters)
            ],
            "points": int(self.points),
            "streamed_chunks": len(self.platform_chunks),
            "route_proof": self.simulation_route_summary or {
                "enabled": self._route_proof_requested(),
                "completed": bool(self.route_proof_completed),
                "route_marker_count": self.route_marker_count,
                "events": list(self.simulation_route_events),
            },
        }

    def _write_fallback_scene_proof(self, screenshot_path: str | None, screenshot_exists: bool) -> None:
        proof_path = os.environ.get("GPT_BRIDGE_SMOKE_PROOF_PATH")
        if not proof_path:
            return
        out = Path(proof_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "panda3d_smoke_proof.v1",
            "status": "screenshot_captured" if screenshot_exists else "headless_scene_built",
            "window_type_hint": os.environ.get("GPT_BRIDGE_WINDOW_TYPE", "default"),
            "has_window": bool(getattr(self, "win", None)),
            "scene": {
                "render_child_count": int(self.render.getNumChildren()),
                "aspect2d_child_count": int(self.aspect2d.getNumChildren()),
                "camera_position": [round(float(v), 4) for v in self.camera.getPos()] if getattr(self, "camera", None) else None,
            },
            "screenshot": {
                "path": str(Path(screenshot_path).resolve()) if screenshot_path else None,
                "exists": bool(screenshot_exists),
                "requested": bool(screenshot_path),
            },
            "app_state": self.gpt_bridge_scene_state(),
        }
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"GPT_BRIDGE_SCENE_PROOF_WRITTEN: {out}", flush=True)

    def _install_smoke_capture(self) -> None:
        try:
            from runtime_hooks.panda3d_smoke_hook import install_from_env
            if install_from_env(self):
                return
        except Exception:
            pass
        screenshot_path = os.environ.get("GPT_BRIDGE_SCREENSHOT_PATH")
        proof_path = os.environ.get("GPT_BRIDGE_SMOKE_PROOF_PATH")
        if not screenshot_path and not proof_path:
            return
        frames_raw = os.environ.get("GPT_BRIDGE_SCREENSHOT_FRAMES") or os.environ.get("GPT_BRIDGE_SMOKE_FRAMES", "4")
        try:
            frames = max(1, int(frames_raw))
        except ValueError:
            frames = 4
        state = {"frames": frames}

        def capture(task):
            state["frames"] -= 1
            if state["frames"] <= 0:
                screenshot_exists = False
                if screenshot_path:
                    out = Path(screenshot_path)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        self.graphicsEngine.renderFrame()
                    except Exception:
                        pass
                    if getattr(self, "win", None):
                        self.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
                        screenshot_exists = out.exists()
                self._write_fallback_scene_proof(screenshot_path, screenshot_exists)
                if os.environ.get("GPT_BRIDGE_EXIT_AFTER_SCREENSHOT", "1") != "0":
                    raise SystemExit(0)
                return Task.done
            return Task.cont

        self.taskMgr.add(capture, "gpt_bridge_screenshot_capture")

    def _update(self, task):
        dt = min(0.05, max(0.0, globalClock.getDt()))
        if self.keys.get("q") or self.keys.get("arrow_left"):
            self.camera_yaw += 112.0 * dt
        if self.keys.get("e") or self.keys.get("arrow_right"):
            self.camera_yaw -= 112.0 * dt
        target = self.controlled_node or self.player
        player_settings = self.settings.get("player", {})
        base_speed = float(player_settings.get("speed", 12.0))
        speed = base_speed * (float(player_settings.get("sprint_multiplier", 2.0)) if self.keys.get("shift") else 1.0)
        acceleration = float(player_settings.get("acceleration", 26.0))
        friction = float(player_settings.get("friction", 18.0))
        gravity = float(player_settings.get("gravity", 24.0))
        jump_strength = float(player_settings.get("jump_strength", 8.0))
        yaw_rad = math.radians(self.camera_yaw)
        forward = Vec3(math.sin(yaw_rad), math.cos(yaw_rad), 0)
        right = Vec3(math.cos(yaw_rad), -math.sin(yaw_rad), 0)
        move = Vec3(0, 0, 0)
        if self.keys.get("w") or self.keys.get("arrow_up"):
            move += forward
        if self.keys.get("s") or self.keys.get("arrow_down"):
            move -= forward
        if self.keys.get("a"):
            move -= right
        if self.keys.get("d"):
            move += right
        moving = move.lengthSquared() > 0
        desired_velocity = Vec3(0, 0, 0)
        if moving:
            move.normalize()
            desired_velocity = move * speed
            blend = min(1.0, acceleration * dt)
            self.velocity = self.velocity + (desired_velocity - self.velocity) * blend
        else:
            damp = max(0.0, 1.0 - friction * dt)
            self.velocity = self.velocity * damp
            if self.velocity.lengthSquared() < 0.0025:
                self.velocity = Vec3(0, 0, 0)
        grounded = target.getZ() <= self.ground_z + 0.02
        if grounded:
            target.setZ(self.ground_z)
            self.vertical_velocity = max(0.0, self.vertical_velocity)
            if self.keys.get("space") and not self.was_grounded:
                # Prevent repeated jump triggering when landing with space still held.
                pass
            elif self.keys.get("space"):
                self.vertical_velocity = jump_strength
                grounded = False
        if not grounded:
            self.vertical_velocity -= gravity * dt
        next_pos = target.getPos() + Vec3(self.velocity.x * dt, self.velocity.y * dt, self.vertical_velocity * dt)
        if next_pos.z <= self.ground_z:
            next_pos.z = self.ground_z
            self.vertical_velocity = 0.0
            grounded = True
        target.setPos(next_pos)
        self.was_grounded = grounded
        if self.velocity.lengthSquared() > 0.04:
            target.setH(math.degrees(math.atan2(-self.velocity.x, self.velocity.y)))
            self.points += max(1, int(self.velocity.length() * dt * 1.8))
        self._play_active_animation(self.velocity.lengthSquared() > 0.04)
        target_pos = target.getPos()
        self._ensure_platform_chunks(target_pos)
        focus = target_pos + Vec3(0, 0, 2.55)
        focus_blend = min(1.0, 8.5 * dt)
        self.camera_focus_smooth = self.camera_focus_smooth + (focus - self.camera_focus_smooth) * focus_blend
        self.camera_focus.setPos(self.camera_focus_smooth)
        self.camera_distance += (self.camera_target_distance - self.camera_distance) * min(1.0, 7.0 * dt)
        self.camera_height += (self.camera_target_height - self.camera_height) * min(1.0, 7.0 * dt)
        cam_back = Vec3(math.sin(yaw_rad), math.cos(yaw_rad), 0)
        if getattr(self, "camera", None):
            cam_pos = Vec3(
                self.camera_focus_smooth.x - cam_back.x * self.camera_distance,
                self.camera_focus_smooth.y - cam_back.y * self.camera_distance,
                self.camera_focus_smooth.z + self.camera_height,
            )
            self.camera.setPos(cam_pos)
            self.camera.lookAt(self.camera_focus_smooth)
        active = self._active_character()
        active_name = active.get("name") if active else "None"
        movement_label = "SPRINT" if self.keys.get("shift") and self.velocity.lengthSquared() > 0.04 else ("MOVE" if self.velocity.lengthSquared() > 0.04 else "IDLE")
        self.points_node.setText(f"POINTS {self.points}")
        self.active_node.setText(f"ACTIVE {active_name} | {movement_label} | ZOOM {self.camera_target_distance:.0f}")
        return Task.cont


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").lower() in {"1", "true", "yes", "on"}


def _run_generated_app() -> None:
    app = GeneratedGame()
    if _truthy_env("GPT_BRIDGE_SIMULATION_ROUTE_PROOF"):
        app.run_simulation_route_proof_now()
        os._exit(0)
    if _truthy_env("GPT_BRIDGE_TEST_MODE") or _truthy_env("GPT_BRIDGE_SMOKE"):
        try:
            frames = max(1, int(os.environ.get("GPT_BRIDGE_SMOKE_FRAMES") or "4"))
        except ValueError:
            frames = 4
        for _ in range(frames + 8):
            app.taskMgr.step()
        os._exit(0)
    app.run()


if __name__ == "__main__":
    _run_generated_app()
'''

def _readme_template(settings: dict[str, Any]) -> str:
    project = settings.get("project") or {}
    bridge = settings.get("bridge") or {}
    title = project.get("title", "Generated Panda3D Game")
    return f"""# {title}

Generated by GPT Game Generation Bridge from this command:

```text
{settings.get('source_command', '')}
```

## Run

```bash
python -m pip install -r requirements.txt
python main.py
```

## Settings check without Panda3D

```bash
python main.py --settings-check
```

## Bridge validation

From the GPT Tool folder, run something like:

```bash
{bridge.get('recommended_validate_command', 'python bridge.py full-pass . --profile panda3d --smoke --entry main.py --require-screenshot')}
```

## Design notes

- Procedural-first: the template should run without custom art assets.
- No FPS counter is shown by default.
- Points are displayed in the top-right corner.
- Simulation mode spawns male and female procedural test characters.
- Press `Tab` to swap which character is playable.
- Press `C` to cycle embedded imported-human animations when they are available.
- Press `F12` or run `python main.py --screenshot-mode` to write a backup screenshot.
- Improved controls include smoothed acceleration/friction, Shift sprint, Space jump/gravity, mouse-wheel camera zoom, and `R` camera reset.
- Run `python main.py --screenshot-mode --route-proof` to automatically move both testers, simulate a Tab swap, drop route markers, write proof JSON, and capture one backup screenshot.
- Characters use non-placeholder silhouettes where possible.
- The settings file is the source of truth for AI edits.
- Bridge smoke tests can run headless with `--window-type none --require-proof` when no display is available, or offscreen with `--window-type offscreen --require-screenshot` when the runtime can provide a fallback framebuffer.
"""


def _bridge_project(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "bridge_project.v1",
        "created_at": _now_iso(),
        "profile": "panda3d",
        "entry": "main.py",
        "settings": "settings/game_settings.json",
        "expected_outputs": {
            "logs": "logs/",
            "screenshots": "screenshots/",
            "reports": "reports/",
        },
        "validation": {
            "syntax": True,
            "imports": True,
            "panda3d_smoke": True,
            "screenshot_proof": True,
            "playable_simulation": True,
            "asset_scan": True,
        },
        "source_command": settings.get("source_command"),
    }


def generate_panda3d_template(output_dir: str | Path, settings: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
    out = Path(output_dir).resolve()
    project = settings.get("project") or {}
    slug = _slugify(project.get("slug") or project.get("title") or "panda3d_game")

    if out.exists() and any(out.iterdir()) and not overwrite:
        return {
            "schema_version": "template_generation_result.v1",
            "ok": False,
            "output_dir": str(out),
            "reason": "Output directory exists and is not empty. Re-run with --force or choose a new directory.",
            "files": [],
        }

    files: list[dict[str, Any]] = []
    directories = [
        "settings",
        "data/regions",
        "data/characters",
        "assets/models",
        "assets/textures",
        "assets/sfx",
        "assets/music",
        "logs",
        "reports",
        "screenshots",
        "tools",
    ]
    for rel in directories:
        (out / rel).mkdir(parents=True, exist_ok=True)

    files.append(_safe_write(out / "main.py", _main_py_template(), overwrite=overwrite))
    files.append(_safe_write_json(out / "settings" / "game_settings.json", settings, overwrite=overwrite))
    files.append(_safe_write_json(out / "bridge_project.json", _bridge_project(settings), overwrite=overwrite))
    files.append(_safe_write(out / "README.md", _readme_template(settings), overwrite=overwrite))
    files.append(_safe_write(out / "requirements.txt", "panda3d>=1.10.16\n", overwrite=overwrite))
    files.append(_safe_write(out / ".gitignore", "__pycache__/\n*.pyc\nlogs/*.log\nreports/latest_report.*\nscreenshots/*.png\nbuild/\ndist/\n", overwrite=overwrite))
    files.append(_safe_write(out / "run_game.bat", "@echo off\npython main.py\n", overwrite=overwrite))
    files.append(_safe_write(out / "run_game.sh", "#!/usr/bin/env bash\npython3 main.py\n", overwrite=overwrite))
    try:
        os.chmod(out / "run_game.sh", 0o755)
    except Exception:
        pass

    for region in (settings.get("world") or {}).get("regions") or []:
        rid = _slugify(region.get("id") or region.get("name") or "region")
        files.append(_safe_write_json(out / "data" / "regions" / f"{rid}.json", region, overwrite=overwrite))
    for char in settings.get("characters") or []:
        cid = _slugify(char.get("id") or char.get("name") or "character")
        files.append(_safe_write_json(out / "data" / "characters" / f"{cid}.json", char, overwrite=overwrite))

    validation_commands = [
        "python main.py --settings-check",
        "python -m py_compile main.py",
        "python -m pip install -r requirements.txt",
        "python main.py",
        "python main.py --screenshot-mode --route-proof --screenshot-path screenshots/simulation_mode_backup.png",
        "# From GPT Tool: python bridge.py panda3d-smoke <project> --entry main.py --runtime-path /path/to/panda3d_py --window-type offscreen --require-screenshot --require-proof",
    ]
    files.append(_safe_write(out / "VALIDATION_COMMANDS.txt", "\n".join(validation_commands) + "\n", overwrite=overwrite))

    manifest = {
        "schema_version": "generated_template_manifest.v1",
        "generated_at": _now_iso(),
        "generator": "GPT Game Generation Bridge",
        "template": "panda3d_playable_simulation_template.v4",
        "project_slug": slug,
        "settings_id": settings.get("settings_id"),
        "file_count": len([f for f in files if f.get("written")]),
        "files": files,
    }
    files.append(_safe_write_json(out / "generated_template_manifest.json", manifest, overwrite=overwrite))
    manifest["files"] = files
    manifest["file_count"] = len([f for f in files if f.get("written")])
    (out / "generated_template_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "schema_version": "template_generation_result.v1",
        "ok": True,
        "output_dir": str(out),
        "project_slug": slug,
        "entry": str(out / "main.py"),
        "settings": str(out / "settings" / "game_settings.json"),
        "manifest": str(out / "generated_template_manifest.json"),
        "files": files,
        "next_commands": validation_commands,
    }


def render_generation_result_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Panda3D Template Generation Result",
        "",
        f"- Status: **{'PASS' if result.get('ok') else 'FAIL'}**",
        f"- Output: `{result.get('output_dir')}`",
    ]
    if not result.get("ok"):
        lines.append(f"- Reason: {result.get('reason')}")
        return "\n".join(lines) + "\n"
    lines.extend([
        f"- Entry: `{result.get('entry')}`",
        f"- Settings: `{result.get('settings')}`",
        f"- Manifest: `{result.get('manifest')}`",
        "",
        "## Next Commands",
        "",
    ])
    for command in result.get("next_commands") or []:
        lines.append(f"```bash\n{command}\n```")
    return "\n".join(lines) + "\n"
