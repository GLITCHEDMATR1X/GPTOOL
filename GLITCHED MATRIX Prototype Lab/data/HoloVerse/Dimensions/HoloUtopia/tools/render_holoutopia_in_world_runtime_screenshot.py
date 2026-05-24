"""Capture HoloUtopia inside a real Panda3D 3D world root.

This is not a 2D layout preview.  The tool creates a tiny HoloVerse-like
root_3d/world_root, installs holoutopia_game_runtime into it, and captures the
same integrated runtime node that the game hook uses.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "holoutopia_game_runtime.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if (candidate / "holoutopia_game_runtime.py").exists():
            return candidate
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_game_runtime.py").exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def _draw_world_reference(root, *, grid_radius: int = 13, spacing: float = 64.0):
    from panda3d.core import LineSegs

    seg = LineSegs("holoverse_reference_floor_grid")
    seg.setThickness(1.15)
    seg.setColor(0.0, 0.82, 1.0, 0.20)
    extent = float(grid_radius) * float(spacing)
    for idx in range(-int(grid_radius), int(grid_radius) + 1):
        p = float(idx) * float(spacing)
        seg.moveTo(-extent, p, 0.0)
        seg.drawTo(extent, p, 0.0)
        seg.moveTo(p, -extent, 0.0)
        seg.drawTo(p, extent, 0.0)
    node = root.attachNewNode(seg.create())
    node.setLightOff(True)
    return node


def _draw_origin_portal_marker(root):
    from panda3d.core import LineSegs

    seg = LineSegs("holoverse_origin_portal_core_marker")
    seg.setThickness(2.6)
    seg.setColor(1.0, 0.16, 0.62, 0.92)
    radius = 34.0
    for k in range(65):
        a = math.tau * k / 64.0
        p = (math.cos(a) * radius, math.sin(a) * radius, 2.0)
        if k == 0:
            seg.moveTo(*p)
        else:
            seg.drawTo(*p)
    for spoke in range(8):
        a = math.tau * spoke / 8.0
        seg.moveTo(0.0, 0.0, 2.0)
        seg.drawTo(math.cos(a) * radius, math.sin(a) * radius, 2.0)
    node = root.attachNewNode(seg.create())
    node.setLightOff(True)
    return node


def _set_runtime_clock(runtime, clock: str) -> None:
    """Set the runtime's monotonic day phase for deterministic screenshots."""
    try:
        hh, mm = [int(part) for part in str(clock or "08:00").split(":", 1)]
        minutes = max(0, min(23 * 60 + 59, hh * 60 + mm))
        config = getattr(runtime, "config", {}) if isinstance(getattr(runtime, "config", {}), dict) else {}
        runtime_cfg = config.get("citizen_runtime", {}) if isinstance(config.get("citizen_runtime"), dict) else {}
        day_seconds = max(30.0, float(runtime_cfg.get("city_day_seconds", 720.0)))
        runtime._started_at = time.monotonic() - (minutes / (24.0 * 60.0)) * day_seconds
        runtime._create_or_update_citizen_markers(force=True)
    except Exception:
        pass


def _set_camera(base, view: str) -> None:
    from panda3d.core import Vec3

    view = str(view or "ground").lower()
    if view == "robots":
        base.cam.setPos(-78.0, -208.0, 34.0)
        base.cam.lookAt(Vec3(-32.0, -104.0, 18.0))
        base.camLens.setFov(42)
    elif view == "citizens":
        base.cam.setPos(-255.0, -515.0, 72.0)
        base.cam.lookAt(Vec3(-32.0, -118.0, 20.0))
        base.camLens.setFov(58)
    elif view == "central":
        base.cam.setPos(-300.0, -420.0, 115.0)
        base.cam.lookAt(Vec3(0.0, 0.0, 24.0))
        base.camLens.setFov(60)
    elif view == "wide":
        base.cam.setPos(-620.0, -730.0, 185.0)
        base.cam.lookAt(Vec3(70.0, 85.0, 30.0))
        base.camLens.setFov(64)
    else:
        base.cam.setPos(-410.0, -555.0, 92.0)
        base.cam.lookAt(Vec3(52.0, 32.0, 22.0))
        base.camLens.setFov(66)
    base.camLens.setNearFar(1.0, 5000.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture HoloUtopia as integrated Panda3D world geometry.")
    parser.add_argument("--out", default="holoutopia_in_world_runtime_screenshot.png")
    parser.add_argument("--size", default="1600x900", help="Screenshot size, e.g. 1600x900")
    parser.add_argument("--view", choices=["ground", "wide", "central", "citizens", "robots"], default="ground")
    parser.add_argument("--clock", default="08:00")
    parser.add_argument("--select-building", default="", help="Open a selected building inspector/site card before capture.")
    parser.add_argument("--building-tab", default="", help="Optional selected building panel tab to show, e.g. status.")
    parser.add_argument("--danger", action="store_true", help="Capture danger override schedule state.")
    args = parser.parse_args(argv)

    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        width_text, height_text = str(args.size).lower().replace(",", "x").split("x", 1)
        width = max(640, int(width_text))
        height = max(360, int(height_text))
    except Exception:
        width, height = 1600, 900

    try:
        from panda3d.core import AmbientLight, DirectionalLight, Filename, Vec4, loadPrcFileData
        loadPrcFileData("", "\n".join([
            "window-type offscreen",
            "load-display p3tinydisplay",
            f"win-size {width} {height}",
            "audio-library-name null",
            "show-frame-rate-meter 0",
            "sync-video 0",
            "framebuffer-multisample 0",
            "textures-power-2 up",
        ]))
        from direct.showbase.ShowBase import ShowBase
    except Exception as exc:
        print(f"Panda3D is required for in-world screenshot capture: {exc}")
        return 2

    from holoutopia_game_runtime import install_holoutopia_runtime

    base = ShowBase(windowType="offscreen")
    base.setBackgroundColor(0.001, 0.006, 0.010, 1.0)
    base.root_3d = base.render.attachNewNode("root_3d")
    base.world_root = base.root_3d.attachNewNode("holoverse_world_root")
    _draw_world_reference(base.world_root)
    _draw_origin_portal_marker(base.world_root)

    ambient = AmbientLight("holoutopia_world_ambient")
    ambient.setColor(Vec4(0.34, 0.52, 0.62, 1.0))
    ambient_node = base.render.attachNewNode(ambient)
    base.render.setLight(ambient_node)
    key = DirectionalLight("holoutopia_world_key")
    key.setColor(Vec4(0.72, 0.94, 1.0, 1.0))
    key_node = base.render.attachNewNode(key)
    key_node.setHpr(38.0, -54.0, 0.0)
    base.render.setLight(key_node)

    runtime = install_holoutopia_runtime(base, root)
    if not runtime.installed:
        print(f"HoloUtopia runtime did not install: {runtime.error}")
        base.destroy()
        return 2
    if args.danger:
        runtime.toggle_danger_state()
    _set_runtime_clock(runtime, args.clock)
    _set_camera(base, args.view)

    for _ in range(18):
        try:
            base.taskMgr.step()
        except Exception:
            pass
        base.graphicsEngine.renderFrame()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = base.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    base.destroy()
    if not ok:
        print(f"Could not save screenshot: {out}")
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
