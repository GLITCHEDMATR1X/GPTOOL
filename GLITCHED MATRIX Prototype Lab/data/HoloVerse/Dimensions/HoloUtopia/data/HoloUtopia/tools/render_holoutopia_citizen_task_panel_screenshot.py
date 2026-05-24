"""Capture tiny robot citizens with the polished citizen inspector in 3D world."""
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
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_game_runtime.py").exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def _draw_world_reference(root, *, grid_radius: int = 10, spacing: float = 64.0):
    from panda3d.core import LineSegs
    seg = LineSegs("holoverse_reference_floor_grid")
    seg.setThickness(1.0)
    seg.setColor(0.0, 0.82, 1.0, 0.14)
    extent = float(grid_radius) * float(spacing)
    for idx in range(-int(grid_radius), int(grid_radius) + 1):
        p = float(idx) * float(spacing)
        seg.moveTo(-extent, p, 0.0); seg.drawTo(extent, p, 0.0)
        seg.moveTo(p, -extent, 0.0); seg.drawTo(p, extent, 0.0)
    node = root.attachNewNode(seg.create())
    node.setLightOff(True)
    return node


def _set_runtime_clock(runtime, clock: str) -> None:
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


def _set_camera(base) -> None:
    from panda3d.core import Vec3
    base.cam.setPos(-96.0, -236.0, 42.0)
    base.cam.lookAt(Vec3(-40.0, -112.0, 18.0))
    base.camLens.setFov(45)
    base.camLens.setNearFar(1.0, 5000.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture HoloUtopia citizen panel in a 3D runtime scene.")
    parser.add_argument("--out", default="holoutopia_pass26_citizen_panel_3d_screenshot.png")
    parser.add_argument("--size", default="1600x900")
    parser.add_argument("--clock", default="08:00")
    parser.add_argument("--citizen", default="npc_aria_voss")
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        width_text, height_text = str(args.size).lower().replace(",", "x").split("x", 1)
        width = max(640, int(width_text)); height = max(360, int(height_text))
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
        print(f"Panda3D is required for task panel screenshot: {exc}")
        return 2
    from holoutopia_game_runtime import install_holoutopia_runtime
    base = ShowBase(windowType="offscreen")
    base.setBackgroundColor(0.001, 0.006, 0.010, 1.0)
    base.root_3d = base.render.attachNewNode("root_3d")
    base.world_root = base.root_3d.attachNewNode("holoverse_world_root")
    _draw_world_reference(base.world_root)
    ambient = AmbientLight("task_panel_ambient"); ambient.setColor(Vec4(0.34, 0.52, 0.62, 1.0))
    ambient_node = base.render.attachNewNode(ambient); base.render.setLight(ambient_node)
    key = DirectionalLight("task_panel_key"); key.setColor(Vec4(0.72, 0.94, 1.0, 1.0))
    key_node = base.render.attachNewNode(key); key_node.setHpr(38.0, -54.0, 0.0); base.render.setLight(key_node)
    runtime = install_holoutopia_runtime(base, root)
    if not runtime.installed:
        print(f"HoloUtopia runtime did not install: {runtime.error}")
        base.destroy(); return 2
    _set_runtime_clock(runtime, args.clock)
    _set_camera(base)
    runtime.select_citizen(args.citizen)
    try:
        runtime.panel_manager.snap_panel(f"citizen:{args.citizen}", "right")
    except Exception:
        pass
    for _ in range(24):
        try: base.taskMgr.step()
        except Exception: pass
        base.graphicsEngine.renderFrame()
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    ok = base.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    base.destroy()
    if not ok:
        print(f"Could not save screenshot: {out}")
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
