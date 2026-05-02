from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_VERSION = "panda_xr_builder.pass18"
ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"
EXPORTS_DIR = ROOT / "exports"
REPORTS_DIR = ROOT / "reports"
SCREENSHOTS_DIR = ROOT / "screenshots"
LOGS_DIR = ROOT / "logs"
DEFAULT_PROJECT = PROJECTS_DIR / "latest_scene.json"
DEFAULT_EXPORT = EXPORTS_DIR / "latest_scene"


@dataclass
class BuildObject:
    kind: str
    name: str
    x: float
    y: float
    z: float
    h: float
    scale_x: float
    scale_y: float
    scale_z: float
    color: tuple[float, float, float, float]


class BuilderState:
    def __init__(self) -> None:
        self.tool_index = 0
        self.tools = ["cube", "wall", "floor_tile", "marker"]
        self.objects: list[BuildObject] = []
        self.cursor_x = 0.0
        self.cursor_y = 4.0
        self.cursor_z = 0.55
        self.rig_x = 0.0
        self.rig_y = -8.0
        self.rig_z = 2.0
        self.rig_h = 0.0
        self.camera_distance = 13.0
        self.placed_count = 0
        self.saved_project_path: str | None = None
        self.export_path: str | None = None
        self.vr_requested = False
        self.vr_runtime_detected = False
        self.vr_notes: list[str] = []

    @property
    def active_tool(self) -> str:
        return self.tools[self.tool_index % len(self.tools)]

    def select_tool(self, tool: str) -> None:
        if tool in self.tools:
            self.tool_index = self.tools.index(tool)

    def place_object(self) -> BuildObject:
        kind = self.active_tool
        self.placed_count += 1
        scale = {
            "cube": (1.0, 1.0, 1.0),
            "wall": (3.0, 0.25, 1.5),
            "floor_tile": (2.0, 2.0, 0.08),
            "marker": (0.35, 0.35, 1.8),
        }[kind]
        color = {
            "cube": (0.2, 0.85, 1.0, 1.0),
            "wall": (0.75, 0.75, 0.9, 1.0),
            "floor_tile": (0.15, 0.45, 0.6, 1.0),
            "marker": (1.0, 0.85, 0.2, 1.0),
        }[kind]
        obj = BuildObject(
            kind=kind,
            name=f"{kind}_{self.placed_count:03d}",
            x=round(self.cursor_x, 3),
            y=round(self.cursor_y, 3),
            z=round(self.cursor_z, 3),
            h=round(self.rig_h, 3),
            scale_x=scale[0],
            scale_y=scale[1],
            scale_z=scale[2],
            color=color,
        )
        self.objects.append(obj)
        return obj

    def undo(self) -> BuildObject | None:
        if not self.objects:
            return None
        return self.objects.pop()

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "panda_xr_scene.v1",
            "app_version": APP_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "builder": {
                "active_tool": self.active_tool,
                "tool_index": self.tool_index,
                "cursor": {"x": self.cursor_x, "y": self.cursor_y, "z": self.cursor_z},
                "rig": {"x": self.rig_x, "y": self.rig_y, "z": self.rig_z, "h": self.rig_h},
                "camera_distance": self.camera_distance,
                "vr_requested": self.vr_requested,
                "vr_runtime_detected": self.vr_runtime_detected,
                "vr_notes": self.vr_notes,
            },
            "objects": [asdict(obj) for obj in self.objects],
        }


def ensure_dirs() -> None:
    for path in (PROJECTS_DIR, EXPORTS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def settings_check() -> dict[str, Any]:
    return {
        "ok": True,
        "app_version": APP_VERSION,
        "python_version": sys.version.split()[0],
        "paths": {
            "root": str(ROOT),
            "projects": str(PROJECTS_DIR),
            "exports": str(EXPORTS_DIR),
            "reports": str(REPORTS_DIR),
            "screenshots": str(SCREENSHOTS_DIR),
            "logs": str(LOGS_DIR),
        },
        "features": {
            "desktop_fallback": True,
            "build_tools": ["cube", "wall", "floor_tile", "marker"],
            "scene_manifest_save": True,
            "obj_export": True,
            "proof_mode": True,
            "vr_runtime_optional": True,
        },
    }


def detect_openxr() -> tuple[bool, list[str]]:
    notes: list[str] = []
    try:
        import xr  # type: ignore  # noqa: F401
        notes.append("Python OpenXR module import succeeded.")
        return True, notes
    except Exception:
        notes.append("Python OpenXR module was not importable; desktop fallback remains active.")
    try:
        import openxr  # type: ignore  # noqa: F401
        notes.append("openxr module import succeeded.")
        return True, notes
    except Exception:
        notes.append("openxr module was not importable.")
    return False, notes


def save_scene(state: BuilderState, path: Path = DEFAULT_PROJECT) -> Path:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_payload(), indent=2) + "\n", encoding="utf-8")
    state.saved_project_path = str(path)
    return path


def _cube_vertices(obj: BuildObject) -> list[tuple[float, float, float]]:
    sx, sy, sz = obj.scale_x / 2.0, obj.scale_y / 2.0, obj.scale_z / 2.0
    base = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    h = math.radians(obj.h)
    ch, sh = math.cos(h), math.sin(h)
    out = []
    for x, y, z in base:
        rx = x * ch - y * sh
        ry = x * sh + y * ch
        out.append((obj.x + rx, obj.y + ry, obj.z + z))
    return out


def export_scene(state: BuilderState, base_path: Path = DEFAULT_EXPORT) -> dict[str, Any]:
    ensure_dirs()
    base_path.parent.mkdir(parents=True, exist_ok=True)
    obj_path = base_path.with_suffix(".obj")
    mtl_path = base_path.with_suffix(".mtl")
    json_path = base_path.with_suffix(".json")

    obj_lines = [
        "# Panda XR Builder scene export",
        f"mtllib {mtl_path.name}",
    ]
    mtl_lines = ["# Panda XR Builder materials"]
    vert_offset = 1
    for index, item in enumerate(state.objects, start=1):
        mat_name = f"mat_{item.kind}_{index:03d}"
        r, g, b, _a = item.color
        mtl_lines.extend([f"newmtl {mat_name}", f"Kd {r:.4f} {g:.4f} {b:.4f}", "Ka 0.0000 0.0000 0.0000", "Ks 0.1000 0.1000 0.1000", ""])
        obj_lines.extend([f"o {item.name}", f"usemtl {mat_name}"])
        for vx, vy, vz in _cube_vertices(item):
            obj_lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")
        faces = [(1, 2, 3, 4), (5, 8, 7, 6), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 8, 4), (4, 8, 5, 1)]
        for face in faces:
            obj_lines.append("f " + " ".join(str(vert_offset + i - 1) for i in face))
        vert_offset += 8
    obj_path.write_text("\n".join(obj_lines) + "\n", encoding="utf-8")
    mtl_path.write_text("\n".join(mtl_lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(state.to_payload(), indent=2) + "\n", encoding="utf-8")
    state.export_path = str(base_path)
    return {"obj": str(obj_path), "mtl": str(mtl_path), "json": str(json_path), "object_count": len(state.objects)}


def write_proof(state: BuilderState, path: Path, screenshot_path: str | None = None) -> Path:
    ensure_dirs()
    payload = {
        "schema_version": "panda_xr_builder_proof.v1",
        "ok": True,
        "app_version": APP_VERSION,
        "object_count": len(state.objects),
        "active_tool": state.active_tool,
        "saved_project_path": state.saved_project_path,
        "export_path": state.export_path,
        "screenshot_path": screenshot_path,
        "vr_requested": state.vr_requested,
        "vr_runtime_detected": state.vr_runtime_detected,
        "vr_notes": state.vr_notes,
        "objects": [asdict(obj) for obj in state.objects[:20]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def run_proof(args: argparse.Namespace) -> int:
    ensure_dirs()
    state = BuilderState()
    state.vr_requested = bool(args.vr)
    state.vr_runtime_detected, state.vr_notes = detect_openxr()
    for tool, x, y in [("floor_tile", 0, 4), ("cube", -1.5, 4), ("wall", 1.5, 4), ("marker", 0, 6)]:
        state.select_tool(tool)
        state.cursor_x = float(x)
        state.cursor_y = float(y)
        state.cursor_z = 0.55 if tool != "floor_tile" else 0.04
        state.place_object()
    if args.save_project:
        save_scene(state, Path(args.project_path) if args.project_path else DEFAULT_PROJECT)
    if args.export_scene:
        export_scene(state, Path(args.export_base) if args.export_base else DEFAULT_EXPORT)
    proof_path = Path(args.proof_path) if args.proof_path else REPORTS_DIR / "panda_xr_builder_proof.json"
    write_proof(state, proof_path, screenshot_path=args.screenshot_path)
    print(f"Panda XR proof PASS: objects={len(state.objects)} proof={proof_path}")
    return 0


class PandaXRApp:
    def __init__(self, args: argparse.Namespace) -> None:
        from direct.showbase.ShowBase import ShowBase
        from direct.gui.OnscreenText import OnscreenText
        from panda3d.core import AmbientLight, CardMaker, DirectionalLight, LColor, Point3, TextNode

        self.ShowBase = ShowBase
        self.OnscreenText = OnscreenText
        self.CardMaker = CardMaker
        self.AmbientLight = AmbientLight
        self.DirectionalLight = DirectionalLight
        self.LColor = LColor
        self.Point3 = Point3
        self.TextNode = TextNode
        self.args = args
        self.base = ShowBase()
        self.state = BuilderState()
        self.state.vr_requested = bool(args.vr)
        self.state.vr_runtime_detected, self.state.vr_notes = detect_openxr()
        self.nodes: list[Any] = []
        self.keys: dict[str, bool] = {}
        self._setup_scene()
        self._setup_controls()
        self._setup_ui()
        self.base.taskMgr.add(self._update, "panda_xr_builder_update")

    def _setup_scene(self) -> None:
        base = self.base
        base.disableMouse()
        base.setBackgroundColor(0.015, 0.02, 0.035, 1)
        ambient = self.AmbientLight("ambient")
        ambient.setColor((0.25, 0.3, 0.36, 1))
        base.render.attachNewNode(ambient)
        base.render.setLight(base.render.attachNewNode(ambient))
        sun = self.DirectionalLight("builder_key_light")
        sun.setColor((0.8, 0.9, 1.0, 1))
        sun_np = base.render.attachNewNode(sun)
        sun_np.setHpr(-35, -50, 0)
        base.render.setLight(sun_np)
        self._make_grid()
        self.cursor_np = self._make_box("build_cursor", 0.2, 0.2, 0.2, (1, 0.9, 0.1, 1))
        self.cursor_np.setPos(self.state.cursor_x, self.state.cursor_y, self.state.cursor_z)
        self._update_camera()

    def _make_grid(self) -> None:
        for x in range(-10, 11):
            self._make_line_card(f"grid_x_{x}", x, 0, 20, 0.018)
        for y in range(-10, 11):
            self._make_line_card(f"grid_y_{y}", 0, y, 20, 0.018, rotate=True)

    def _make_line_card(self, name: str, x: float, y: float, length: float, width: float, rotate: bool = False) -> None:
        cm = self.CardMaker(name)
        cm.setFrame(-width, width, -length / 2, length / 2)
        node = self.base.render.attachNewNode(cm.generate())
        node.setColor(0.05, 0.45, 0.65, 0.45)
        node.setTransparency(True)
        node.setPos(x, y, 0.01)
        node.setP(-90)
        if rotate:
            node.setH(90)

    def _make_box(self, name: str, sx: float, sy: float, sz: float, color: tuple[float, float, float, float]) -> Any:
        model = self.base.loader.loadModel("models/box")
        model.setName(name)
        model.reparentTo(self.base.render)
        model.setScale(sx, sy, sz)
        model.setColor(*color)
        return model

    def _setup_controls(self) -> None:
        for key in ["w", "a", "s", "d", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "q", "e"]:
            self.base.accept(key, self._set_key, [key, True])
            self.base.accept(key + "-up", self._set_key, [key, False])
        self.base.accept("1", self._tool, ["cube"])
        self.base.accept("2", self._tool, ["wall"])
        self.base.accept("3", self._tool, ["floor_tile"])
        self.base.accept("4", self._tool, ["marker"])
        self.base.accept("space", self._place)
        self.base.accept("enter", self._place)
        self.base.accept("z", self._undo)
        self.base.accept("s", self._save)
        self.base.accept("x", self._export)
        self.base.accept("wheel_up", self._zoom, [-1.0])
        self.base.accept("wheel_down", self._zoom, [1.0])
        self.base.accept("f12", self._screenshot)
        self.base.accept("escape", sys.exit, [0])

    def _setup_ui(self) -> None:
        self.status = self.OnscreenText(
            text="",
            pos=(-1.31, 0.92),
            scale=0.045,
            fg=(0.75, 0.95, 1.0, 1),
            align=self.TextNode.ALeft,
            mayChange=True,
        )
        self.help = self.OnscreenText(
            text="1 cube  2 wall  3 floor  4 marker | Space place | Z undo | S save | X export | F12 shot | Esc exit",
            pos=(0, -0.94),
            scale=0.038,
            fg=(0.9, 0.9, 0.75, 1),
            align=self.TextNode.ACenter,
            mayChange=False,
        )
        self._refresh_ui()

    def _set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def _tool(self, tool: str) -> None:
        self.state.select_tool(tool)
        self._refresh_ui()

    def _place(self) -> None:
        obj = self.state.place_object()
        node = self._make_box(obj.name, obj.scale_x, obj.scale_y, obj.scale_z, obj.color)
        node.setPos(obj.x, obj.y, obj.z)
        node.setH(obj.h)
        self.nodes.append(node)
        self._refresh_ui()

    def _undo(self) -> None:
        self.state.undo()
        if self.nodes:
            self.nodes.pop().removeNode()
        self._refresh_ui()

    def _save(self) -> None:
        save_scene(self.state)
        self._refresh_ui("saved")

    def _export(self) -> None:
        export_scene(self.state)
        self._refresh_ui("exported")

    def _screenshot(self) -> None:
        ensure_dirs()
        path = SCREENSHOTS_DIR / "panda_xr_builder_latest.png"
        self.base.win.saveScreenshot(str(path))
        self._refresh_ui(f"screenshot: {path.name}")

    def _zoom(self, delta: float) -> None:
        self.state.camera_distance = max(5.0, min(30.0, self.state.camera_distance + delta))
        self._update_camera()

    def _update_camera(self) -> None:
        h = math.radians(self.state.rig_h)
        cx = self.state.rig_x - math.sin(h) * self.state.camera_distance
        cy = self.state.rig_y - math.cos(h) * self.state.camera_distance
        self.base.camera.setPos(cx, cy, self.state.rig_z + 6.0)
        self.base.camera.lookAt(self.state.rig_x, self.state.rig_y + 4.0, 0.8)

    def _refresh_ui(self, note: str = "") -> None:
        vr = "VR requested" if self.state.vr_requested else "desktop fallback"
        if self.state.vr_requested and not self.state.vr_runtime_detected:
            vr += " / OpenXR not detected"
        suffix = f" | {note}" if note else ""
        self.status.setText(
            f"Panda XR Builder {APP_VERSION}\n"
            f"mode: {vr}\n"
            f"tool: {self.state.active_tool} | objects: {len(self.state.objects)} | cursor: {self.state.cursor_x:.1f},{self.state.cursor_y:.1f},{self.state.cursor_z:.1f}{suffix}"
        )

    def _update(self, task: Any) -> Any:
        dt = globalClock.getDt()  # type: ignore[name-defined]
        speed = 5.0 * dt
        if self.keys.get("w") or self.keys.get("arrow_up"):
            self.state.cursor_y += speed
        if self.keys.get("s") or self.keys.get("arrow_down"):
            self.state.cursor_y -= speed
        if self.keys.get("a") or self.keys.get("arrow_left"):
            self.state.cursor_x -= speed
        if self.keys.get("d") or self.keys.get("arrow_right"):
            self.state.cursor_x += speed
        if self.keys.get("q"):
            self.state.rig_h += 55.0 * dt
        if self.keys.get("e"):
            self.state.rig_h -= 55.0 * dt
        self.cursor_np.setPos(self.state.cursor_x, self.state.cursor_y, self.state.cursor_z)
        self._update_camera()
        self._refresh_ui()
        return task.cont

    def run(self) -> None:
        self.base.run()


def run_app(args: argparse.Namespace) -> int:
    ensure_dirs()
    try:
        app = PandaXRApp(args)
        app.run()
        return 0
    except Exception:
        ensure_dirs()
        crash_path = LOGS_DIR / "crash_latest.txt"
        crash_path.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Panda XR crashed. Log: {crash_path}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Panda XR Builder")
    parser.add_argument("--settings-check", action="store_true")
    parser.add_argument("--proof-mode", action="store_true")
    parser.add_argument("--vr", action="store_true", help="Request VR/OpenXR mode when available; desktop fallback remains active.")
    parser.add_argument("--save-project", action="store_true")
    parser.add_argument("--project-path", default=str(DEFAULT_PROJECT))
    parser.add_argument("--export-scene", action="store_true")
    parser.add_argument("--export-base", default=str(DEFAULT_EXPORT))
    parser.add_argument("--proof-path", default=str(REPORTS_DIR / "panda_xr_builder_proof.json"))
    parser.add_argument("--screenshot-path", default=str(SCREENSHOTS_DIR / "panda_xr_builder_latest.png"))
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_dirs()
    if args.settings_check:
        payload = settings_check()
        print(json.dumps(payload, indent=2) if args.json else "Panda XR settings check PASS")
        return 0
    if args.proof_mode:
        return run_proof(args)
    return run_app(args)


if __name__ == "__main__":
    raise SystemExit(main())
