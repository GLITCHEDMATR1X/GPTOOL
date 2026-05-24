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
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_game_runtime.py").exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


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
        runtime._screenshot_clock_override = f"{minutes // 60:02d}:{minutes % 60:02d}"
        runtime._create_or_update_citizen_markers(force=True)
    except Exception:
        pass


def _set_camera(base, view: str) -> None:
    from panda3d.core import Vec3

    view = str(view or "ground").lower()
    if view == "residential_people_close":
        base.cam.setPos(-635.0, -45.0, 82.0)
        base.cam.lookAt(Vec3(-520.0, 28.0, 3.0))
        base.camLens.setFov(28)
    elif view == "residential_population":
        base.cam.setPos(-730.0, -255.0, 64.0)
        base.cam.lookAt(Vec3(-470.0, 0.0, 18.0))
        base.camLens.setFov(52)
    elif view == "residential_overview":
        base.cam.setPos(-820.0, -365.0, 138.0)
        base.cam.lookAt(Vec3(-455.0, 0.0, 26.0))
        base.camLens.setFov(60)
    elif view == "robots":
        base.cam.setPos(-78.0, -208.0, 34.0)
        base.cam.lookAt(Vec3(-32.0, -104.0, 18.0))
        base.camLens.setFov(42)
    elif view == "citizens":
        base.cam.setPos(-255.0, -515.0, 72.0)
        base.cam.lookAt(Vec3(-32.0, -118.0, 20.0))
        base.camLens.setFov(58)
    elif view == "simulation_hub_activity":
        base.cam.setPos(-118.0, -205.0, 58.0)
        base.cam.lookAt(Vec3(0.0, 4.0, 7.0))
        base.camLens.setFov(36)
    elif view == "simulation_pathfinding":
        base.cam.setPos(-92.0, -138.0, 34.0)
        base.cam.lookAt(Vec3(-7.0, 4.0, 5.0))
        base.camLens.setFov(32)
    elif view == "simulation_activity_clusters":
        base.cam.setPos(-128.0, -152.0, 42.0)
        base.cam.lookAt(Vec3(-4.0, 2.0, 6.5))
        base.camLens.setFov(34)
    elif view == "adventure_hub":
        base.cam.setPos(-245.0, -340.0, 116.0)
        base.cam.lookAt(Vec3(0.0, 0.0, 58.0))
        base.camLens.setFov(42)
    elif view == "adventure_watch":
        base.cam.setPos(-360.0, -535.0, 160.0)
        base.cam.lookAt(Vec3(-98.0, -130.0, 70.0))
        base.camLens.setFov(39)
    elif view == "commute_departure":
        base.cam.setPos(-635.0, -45.0, 82.0)
        base.cam.lookAt(Vec3(-520.0, 28.0, 3.0))
        base.camLens.setFov(28)
    elif view == "commute_return":
        base.cam.setPos(-170.0, -175.0, 64.0)
        base.cam.lookAt(Vec3(-8.0, 7.0, 7.0))
        base.camLens.setFov(42)
    elif view == "watch_mode":
        base.cam.setPos(-390.0, -565.0, 168.0)
        base.cam.lookAt(Vec3(-80.0, -76.0, 44.0))
        base.camLens.setFov(54)
    elif view == "watch_mode_close":
        base.cam.setPos(-342.0, -512.0, 146.0)
        base.cam.lookAt(Vec3(-135.0, -250.0, 72.0))
        base.camLens.setFov(36)
    elif view == "world_atlas":
        # High oblique city-map view: all 9 districts and the raised Simulation/Core hub.
        base.cam.setPos(-1160.0, -1220.0, 620.0)
        base.cam.lookAt(Vec3(0.0, 0.0, 54.0))
        base.camLens.setFov(54)
    elif view == "world_atlas_close":
        base.cam.setPos(-760.0, -820.0, 405.0)
        base.cam.lookAt(Vec3(0.0, 0.0, 64.0))
        base.camLens.setFov(46)
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


def _set_focus_camera(base, runtime, view: str) -> bool:
    """Dynamic camera framing for Pass 41 Watch Focus targets."""
    try:
        from panda3d.core import Point3, Vec3
        from holoutopia_watch_focus import build_watch_focus_state

        frame = getattr(runtime, "_last_citizen_frame", {}) if isinstance(getattr(runtime, "_last_citizen_frame", {}), dict) else {}
        clock = str(frame.get("clock") or getattr(runtime, "current_clock", lambda: "18:15")())
        focus = build_watch_focus_state(getattr(runtime, "holoverse_root", None), clock, frame=frame, node_index=getattr(runtime, "_node_index", {}))
        city_root = getattr(runtime, "city_root", None)
        if city_root is None:
            return False
        citizen = focus.get("focus_citizen") if isinstance(focus.get("focus_citizen"), dict) else {}
        cluster = focus.get("focus_cluster") if isinstance(focus.get("focus_cluster"), dict) else {}
        if view == "focus_cluster":
            lx = float(cluster.get("x") or citizen.get("x") or 0.0)
            ly = float(cluster.get("y") or citizen.get("y") or 0.0)
            lz = float(cluster.get("z") or 2.0)
            cam_local = Point3(lx - 80.0, ly - 96.0, lz + 54.0)
            target_local = Point3(lx, ly, lz + 13.0)
            fov = 38
        elif view == "director_overview":
            lx = float(cluster.get("x") or citizen.get("x") or 0.0)
            ly = float(cluster.get("y") or citizen.get("y") or 0.0)
            lz = float(cluster.get("z") or 2.0)
            cam_local = Point3(lx - 190.0, ly - 250.0, lz + 112.0)
            target_local = Point3(lx - 10.0, ly - 5.0, lz + 20.0)
            fov = 50
        else:
            lx = float(citizen.get("x") or cluster.get("x") or 0.0)
            ly = float(citizen.get("y") or cluster.get("y") or 0.0)
            lz = float(citizen.get("z") or 1.75)
            cam_local = Point3(lx - 32.0, ly - 46.0, lz + 25.0)
            target_local = Point3(lx, ly, lz + 5.2)
            fov = 26
        cam_world = base.render.getRelativePoint(city_root, cam_local)
        target_world = base.render.getRelativePoint(city_root, target_local)
        base.cam.setPos(cam_world)
        base.cam.lookAt(Vec3(target_world))
        base.camLens.setFov(fov)
        base.camLens.setNearFar(0.5, 5000.0)
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture HoloUtopia as integrated Panda3D world geometry.")
    parser.add_argument("--out", default="holoutopia_in_world_runtime_screenshot.png")
    parser.add_argument("--size", default="1600x900", help="Screenshot size, e.g. 1600x900")
    parser.add_argument("--view", choices=["ground", "wide", "world_atlas", "world_atlas_close", "central", "watch_mode", "watch_mode_close", "focus_follow", "focus_cluster", "director_overview", "simulation_hub_activity", "simulation_pathfinding", "simulation_activity_clusters", "adventure_hub", "adventure_watch", "commute_departure", "commute_return", "citizens", "robots", "residential_population", "residential_overview", "residential_people_close"], default="ground")
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
    if str(args.view) in {"world_atlas", "world_atlas_close", "adventure_hub"}:
        # These proof shots are city-composition/hub views, not UI-panel shots.
        for attr in ("watch_root", "focus_root", "status_root"):
            node = getattr(runtime, attr, None)
            if node is not None:
                try:
                    node.removeNode()
                except Exception:
                    pass
                try:
                    setattr(runtime, attr, None)
                except Exception:
                    pass
        try:
            for pattern in ("**/holoutopia_watch*", "**/holoutopia_runtime_status*", "**/holoutopia_watch_focus*"):
                matches = list(base.render.findAllMatches(pattern))
                for node in matches:
                    try:
                        node.removeNode()
                    except Exception:
                        pass
        except Exception:
            pass
    if str(args.view) in {"focus_follow", "focus_cluster", "director_overview"}:
        if not _set_focus_camera(base, runtime, str(args.view)):
            _set_camera(base, "watch_mode_close")
    else:
        _set_camera(base, args.view)

    selected_building = str(args.select_building or "").strip()
    if selected_building:
        try:
            runtime.select_building(selected_building)
            tab = str(args.building_tab or "").strip()
            panel_manager = getattr(runtime, "panel_manager", None)
            if tab and panel_manager is not None:
                panel_id = f"building:{getattr(runtime, 'selected_building_id', selected_building)}"
                panel_manager.set_panel_tab(panel_id, tab)
        except Exception as exc:
            print(f"Could not select building {selected_building!r}: {exc}")

    for _ in range(18):
        try:
            base.taskMgr.step()
        except Exception:
            pass
        if str(args.view) in {"world_atlas", "world_atlas_close", "adventure_hub"}:
            try:
                for pattern in ("**/holoutopia_watch*", "**/holoutopia_runtime_status*", "**/holoutopia_watch_focus*"):
                    for node in list(base.render.findAllMatches(pattern)):
                        try:
                            node.removeNode()
                        except Exception:
                            pass
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
