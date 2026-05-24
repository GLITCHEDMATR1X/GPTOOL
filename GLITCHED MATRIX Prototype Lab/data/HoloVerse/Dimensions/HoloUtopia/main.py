"""HoloUtopia standalone launcher.

Launches the authored 3x3 HoloUtopia city directly as a Panda3D scene.
This is the standalone entry point.  It intentionally keeps HoloUtopia separate
from the larger HoloVerse/GX runtime so the city can be tested without touching
artifact routes or HoloCore.

Run from this folder:
    python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = APP_ROOT / "data" / "HoloUtopia"

if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))


def _missing_panda3d_message(exc: BaseException) -> str:
    return (
        "Panda3D is required to launch HoloUtopia.\n"
        "Install it in your active Python environment, then run again:\n\n"
        "    py -3 -m pip install panda3d\n"
        "    py -3 main.py\n\n"
        f"Import error: {exc}"
    )


class _FallbackPrintApp:
    """Text fallback used only when Panda3D is not installed."""

    def __init__(self, error: BaseException) -> None:
        print(_missing_panda3d_message(error))

    def run(self) -> None:  # pragma: no cover - no-op fallback
        return


def build_app():
    try:
        from direct.showbase.ShowBase import ShowBase
        from direct.gui.OnscreenText import OnscreenText
        from panda3d.core import AmbientLight, DirectionalLight, TextNode, Vec3, WindowProperties
    except Exception as exc:  # pragma: no cover - environment-dependent
        return _FallbackPrintApp(exc)

    class HoloUtopiaStandalone(ShowBase):
        def __init__(self) -> None:
            super().__init__()
            self.disableMouse()
            self.setBackgroundColor(0.002, 0.006, 0.010, 1.0)
            try:
                props = WindowProperties()
                props.setTitle("HoloUtopia Live City")
                props.setSize(1600, 900)
                self.win.requestProperties(props)
            except Exception:
                pass

            self.root_3d = self.render.attachNewNode("root_3d")
            self.world_root = self.root_3d.attachNewNode("world_root")
            self._keys: dict[str, bool] = {}
            self._camera_speed = 155.0
            self._camera_fast = 340.0
            self._camera_slow = 58.0
            self._camera_yaw = 43.0
            self._camera_pitch = -17.0
            self._mouse_look_active = False
            self._mouse_last_xy: tuple[int, int] | None = None
            self._mouse_sensitivity = 0.16
            self._camera_orbit_enabled = True
            self._camera_orbit_target = Vec3(0.0, 0.0, 26.0)
            self._camera_orbit_distance = 640.0
            self._camera_min_distance = 58.0
            self._camera_max_distance = 1900.0
            self._camera_default_fov = 42.0
            self._camera_focus_fov = 38.0
            self._first_person_active = False
            self._first_person_bounds: dict[str, float] = {}
            self._first_person_walk_speed = 32.0
            self._first_person_jog_speed = 58.0
            self._first_person_last_state_save = 0.0
            self._controls_visible = True
            self._view_order = ["overview", "street", "core", "wide"]
            self._view_index = 0
            self._setup_lights(AmbientLight, DirectionalLight, Vec3)
            self._setup_camera(Vec3)
            self._setup_input()

            status = "HOLOUTOPIA // FULL CITY VIEW // CLICK A DISTRICT // ENTER/P WALKS FOCUSED TOWN"
            self.title_text = OnscreenText(
                text=status,
                pos=(-1.30, 0.91),
                scale=0.034,
                align=TextNode.ALeft,
                fg=(0.70, 1.00, 1.00, 0.92),
                shadow=(0, 0, 0, 0.72),
            )
            self.controls_text = OnscreenText(
                text=self._controls_text(),
                pos=(-1.30, -0.88),
                scale=0.031,
                align=TextNode.ALeft,
                fg=(0.76, 0.96, 1.00, 0.86),
                shadow=(0, 0, 0, 0.70),
            )

            try:
                from holoutopia_game_runtime import install_holoutopia_runtime
                self.holoutopia_runtime = install_holoutopia_runtime(self, MODULE_ROOT, enabled=True)
                if not getattr(self.holoutopia_runtime, "installed", False):
                    status = f"HOLOUTOPIA FAILED TO INSTALL: {getattr(self.holoutopia_runtime, 'error', 'unknown error')}"
                    print(status)
                    self.title_text.setText(status)
            except Exception as exc:
                status = f"HOLOUTOPIA RUNTIME ERROR: {exc.__class__.__name__}: {exc}"
                print(status)
                self.title_text.setText(status)

            self.taskMgr.add(self._camera_task, "holoutopia-standalone-camera")
            self.accept("escape", self._escape_action)

        def _setup_lights(self, AmbientLight, DirectionalLight, Vec3) -> None:
            ambient = AmbientLight("holoutopia_standalone_ambient")
            ambient.setColor((0.28, 0.36, 0.44, 1.0))
            self.render.setLight(self.render.attachNewNode(ambient))
            sun = DirectionalLight("holoutopia_standalone_key")
            sun.setColor((0.80, 0.92, 1.00, 1.0))
            sun_np = self.render.attachNewNode(sun)
            sun_np.setHpr(-42, -58, 0)
            self.render.setLight(sun_np)

        def _setup_camera(self, Vec3) -> None:
            self._set_camera_pose("overview")
            try:
                self.camLens.setFov(self._camera_default_fov)
                self.camLens.setNearFar(1.0, 5000.0)
            except Exception:
                pass
            self._store_camera_hpr_from_node()

        def _setup_input(self) -> None:
            for key in ("w", "a", "s", "d", "q", "e", "arrow_left", "arrow_right", "arrow_up", "arrow_down", "space", "shift"):
                self.accept(key, self._set_key, [key, True])
                self.accept(f"{key}-up", self._set_key, [key, False])
            for event in ("control", "lcontrol", "rcontrol"):
                self.accept(event, self._set_key, ["control", True])
                self.accept(f"{event}-up", self._set_key, ["control", False])
            self.accept("mouse3", self._set_mouse_look, [True])
            self.accept("mouse3-up", self._set_mouse_look, [False])
            self.accept("wheel_up", self._wheel_zoom, [1.0])
            self.accept("wheel_down", self._wheel_zoom, [-1.0])
            self.accept("r", self._reset_view)
            self.accept("v", self._cycle_view)
            self.accept("f", self._focus_selected)
            self.accept("x", self._close_focused_panel)
            self.accept("enter", self._toggle_first_person_mode)
            self.accept("p", self._toggle_first_person_mode)
            self.accept("e", self._first_person_interact)
            self.accept("backspace", self._exit_town_focus)
            self.accept("h", self._toggle_controls_text)

        def _controls_text(self) -> str:
            return "Orbit: RMB/Arrows rotate, Wheel zoom, WASD pans pivot   Town Focus: Enter/P first-person   Walk: WASD + RMB look + E interact   ESC return"

        def _set_key(self, key: str, value: bool) -> None:
            self._keys[key] = bool(value)

        def _set_mouse_look(self, value: bool) -> None:
            self._mouse_look_active = bool(value)
            self._mouse_last_xy = self._window_pointer_xy() if self._mouse_look_active else None

        def _window_pointer_xy(self) -> tuple[int, int] | None:
            try:
                pointer = self.win.getPointer(0)
                return int(pointer.getX()), int(pointer.getY())
            except Exception:
                return None

        def _reset_view(self) -> None:
            self._set_camera_pose("overview")

        def _cycle_view(self) -> None:
            self._view_index = (self._view_index + 1) % len(self._view_order)
            self._set_camera_pose(self._view_order[self._view_index])

        def _toggle_controls_text(self) -> None:
            self._controls_visible = not self._controls_visible
            try:
                if self._controls_visible:
                    self.controls_text.show()
                else:
                    self.controls_text.hide()
            except Exception:
                pass

        def _close_focused_panel(self) -> bool:
            try:
                runtime = getattr(self, "holoutopia_runtime", None)
                if runtime is not None and hasattr(runtime, "close_focused_panel"):
                    return bool(runtime.close_focused_panel())
            except Exception:
                pass
            return False

        def _exit_town_focus(self) -> bool:
            try:
                if self._first_person_active and self._exit_first_person_mode():
                    return True
                runtime = getattr(self, "holoutopia_runtime", None)
                if runtime is not None and hasattr(runtime, "exit_town_focus"):
                    return bool(runtime.exit_town_focus())
            except Exception:
                pass
            return False

        def _escape_action(self) -> None:
            # ESC closes inspectors first, then returns from Town Focus, then exits.
            if self._close_focused_panel():
                return
            if self._exit_town_focus():
                return
            self.userExit()

        def _wheel_zoom(self, direction: float) -> None:
            try:
                if self._first_person_active:
                    # Keep wheel useful in walk mode without moving through town geometry:
                    # it gently adjusts FOV instead of breaking the grounded camera.
                    current = float(self.camLens.getFov().getX())
                    self.camLens.setFov(max(48.0, min(62.0, current - (2.0 if float(direction) > 0 else -2.0))))
                    return
                step = 44.0 if float(direction) > 0 else -44.0
                if self._keys.get("shift"):
                    step *= 1.75
                if self._keys.get("control"):
                    step *= 0.42
                if self._camera_orbit_enabled:
                    # Wheel-up moves the camera closer to the current pivot.
                    self._camera_orbit_distance = max(
                        self._camera_min_distance,
                        min(self._camera_max_distance, self._camera_orbit_distance - step),
                    )
                    self._apply_orbit_camera()
                else:
                    self.camera.setPos(self.camera, 0.0, step, 0.0)
                    self._clamp_camera_position()
            except Exception:
                pass

        def _set_camera_orbit_target(self, x: float, y: float, z: float = 24.0, *, distance: float | None = None, yaw: float | None = None, pitch: float | None = None, fov: float | None = None, label: str = "") -> None:
            try:
                from panda3d.core import Vec3

                self._camera_orbit_enabled = True
                self._camera_orbit_target = Vec3(float(x), float(y), float(z))
                if distance is not None:
                    self._camera_orbit_distance = max(self._camera_min_distance, min(self._camera_max_distance, float(distance)))
                if yaw is not None:
                    self._camera_yaw = float(yaw)
                if pitch is not None:
                    self._camera_pitch = max(-76.0, min(-14.0, float(pitch)))
                if fov is not None:
                    self.camLens.setFov(max(30.0, min(50.0, float(fov))))
                    self.camLens.setNearFar(1.0, 5000.0)
                self._apply_orbit_camera()
            except Exception:
                pass

        def _apply_orbit_camera(self) -> None:
            try:
                import math
                from panda3d.core import Vec3

                target = self._camera_orbit_target
                distance = max(self._camera_min_distance, min(self._camera_max_distance, float(self._camera_orbit_distance)))
                elevation = math.radians(max(14.0, min(76.0, -float(self._camera_pitch))))
                yaw = math.radians(float(self._camera_yaw))
                horizontal = max(10.0, distance * math.cos(elevation))
                offset = Vec3(
                    -math.sin(yaw) * horizontal,
                    -math.cos(yaw) * horizontal,
                    distance * math.sin(elevation),
                )
                self.camera.setPos(self.render, target + offset)
                self.camera.lookAt(Vec3(float(target.getX()), float(target.getY()), float(target.getZ())))
                self._clamp_camera_position()
            except Exception:
                pass

        def _pan_orbit_target(self, strafe: float, move: float, rise: float, amount: float) -> None:
            try:
                import math
                from panda3d.core import Vec3

                yaw = math.radians(float(self._camera_yaw))
                forward = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
                right = Vec3(math.cos(yaw), -math.sin(yaw), 0.0)
                delta = right * float(strafe) * amount + forward * float(move) * amount + Vec3(0.0, 0.0, float(rise) * amount)
                self._camera_orbit_target = self._camera_orbit_target + delta
                self._clamp_orbit_target()
                self._apply_orbit_camera()
            except Exception:
                pass

        def _clamp_orbit_target(self) -> None:
            try:
                from panda3d.core import Vec3

                t = self._camera_orbit_target
                self._camera_orbit_target = Vec3(
                    max(-1300.0, min(1300.0, float(t.getX()))),
                    max(-1300.0, min(1300.0, float(t.getY()))),
                    max(2.0, min(220.0, float(t.getZ()))),
                )
            except Exception:
                pass

        def _set_camera_pose(self, pose: str) -> None:
            pose = str(pose or "overview").lower()
            if pose == "street":
                self._set_camera_orbit_target(-52.0, -86.0, 18.0, distance=260.0, yaw=36.0, pitch=-28.0, fov=38.0)
            elif pose == "core":
                self._set_camera_orbit_target(0.0, 0.0, 30.0, distance=360.0, yaw=39.0, pitch=-38.0, fov=38.0)
            elif pose == "wide":
                self._set_camera_orbit_target(0.0, 0.0, 34.0, distance=780.0, yaw=40.0, pitch=-42.0, fov=42.0)
            else:
                # Full-city default: the camera pivots around the center of the city.
                self._set_camera_orbit_target(0.0, 0.0, 30.0, distance=640.0, yaw=40.0, pitch=-38.0, fov=self._camera_default_fov)
                self._view_index = 0
            self._clamp_camera_position()

        def _toggle_first_person_mode(self) -> bool:
            if self._first_person_active:
                return self._exit_first_person_mode()
            return self._enter_first_person_mode()

        def _enter_first_person_mode(self) -> bool:
            try:
                runtime = getattr(self, "holoutopia_runtime", None)
                if runtime is None or not getattr(runtime, "town_focus_active", lambda: False)():
                    self.title_text.setText("HOLOUTOPIA // ENTER TOWN FOCUS FIRST, THEN PRESS ENTER/P FOR FIRST PERSON")
                    return False
                if hasattr(runtime, "enter_town_first_person") and not runtime.enter_town_first_person():
                    return False
                state = runtime.get_first_person_start_state() if hasattr(runtime, "get_first_person_start_state") else {}
                pos = state.get("pos") if isinstance(state.get("pos"), (tuple, list)) else (0.0, 0.0, 9.0)
                hpr = state.get("hpr") if isinstance(state.get("hpr"), (tuple, list)) else (self._camera_yaw, 0.0, 0.0)
                self._first_person_bounds = dict(state.get("bounds") or {}) if isinstance(state.get("bounds"), dict) else {}
                self._first_person_active = True
                self._camera_orbit_enabled = False
                self._camera_yaw = float(hpr[0]) if len(hpr) >= 1 else self._camera_yaw
                self._camera_pitch = max(-48.0, min(36.0, float(hpr[1]) if len(hpr) >= 2 else 0.0))
                self.camera.setPos(self.render, float(pos[0]), float(pos[1]), float(pos[2]))
                self.camera.setHpr(self._camera_yaw, self._camera_pitch, 0.0)
                self.camLens.setFov(float(state.get("fov") or 60.0))
                self.camLens.setNearFar(0.18, 5000.0)
                try:
                    self.controls_text.hide()
                except Exception:
                    pass
                town_name = str(state.get("display_name") or "Focused Town")
                self.title_text.setText(f"HOLOUTOPIA // FIRST PERSON: {town_name} // E INTERACT // ESC RETURNS TO TOWN FOCUS")
                return True
            except Exception as exc:
                try:
                    self.title_text.setText(f"HOLOUTOPIA // FIRST PERSON ERROR: {exc.__class__.__name__}")
                except Exception:
                    pass
                return False

        def _exit_first_person_mode(self) -> bool:
            if not self._first_person_active:
                return False
            try:
                runtime = getattr(self, "holoutopia_runtime", None)
                if runtime is not None and hasattr(runtime, "update_first_person_player_state"):
                    runtime.update_first_person_player_state(self.camera.getPos(self.render), self.camera.getHpr())
                self._first_person_active = False
                self._first_person_bounds = {}
                self._camera_orbit_enabled = True
                if runtime is not None and hasattr(runtime, "exit_town_first_person"):
                    runtime.exit_town_first_person()
                try:
                    if self._controls_visible:
                        self.controls_text.show()
                except Exception:
                    pass
                return True
            except Exception:
                self._first_person_active = False
                self._camera_orbit_enabled = True
                return True

        def _first_person_interact(self) -> bool:
            if not self._first_person_active:
                return False
            try:
                runtime = getattr(self, "holoutopia_runtime", None)
                if runtime is not None and hasattr(runtime, "interact_first_person"):
                    return bool(runtime.interact_first_person())
            except Exception:
                pass
            return False

        def _focus_selected(self) -> bool:
            try:
                runtime = getattr(self, "holoutopia_runtime", None)
                focus = runtime.get_selected_focus_point() if runtime is not None and hasattr(runtime, "get_selected_focus_point") else None
                if not isinstance(focus, dict):
                    self._set_camera_pose("core")
                    self.title_text.setText("HOLOUTOPIA // SELECT A BUILDING OR CITIZEN, THEN PRESS F TO FOCUS")
                    return False
                point = focus.get("point")
                if not isinstance(point, (tuple, list)) or len(point) < 3:
                    return False
                x, y, z = float(point[0]), float(point[1]), float(point[2])
                self._set_camera_orbit_target(x, y, max(8.0, z), distance=190.0, pitch=-42.0, fov=self._camera_focus_fov)
                label = str(focus.get("label") or "selected target")
                if len(label) > 44:
                    label = label[:41].rstrip() + "..."
                self.title_text.setText(f"HOLOUTOPIA // FOCUSED: {label} // ORBIT PIVOT LOCKED // RMB ROTATE // WHEEL ZOOM // X CLOSE")
                return True
            except Exception:
                return False

        def _store_camera_hpr_from_node(self) -> None:
            try:
                self._camera_yaw = float(self.camera.getH())
                self._camera_pitch = max(-76.0, min(-14.0, float(self.camera.getP())))
            except Exception:
                pass

        def _sync_camera_hpr(self) -> None:
            if self._camera_orbit_enabled:
                self._apply_orbit_camera()
            else:
                self.camera.setHpr(self._camera_yaw, self._camera_pitch, 0)

        def _clamp_camera_position(self) -> None:
            try:
                pos = self.camera.getPos(self.render)
                x = max(-1500.0, min(1500.0, float(pos.getX())))
                y = max(-1500.0, min(1500.0, float(pos.getY())))
                z = max(8.0, min(760.0, float(pos.getZ())))
                if (x, y, z) != (float(pos.getX()), float(pos.getY()), float(pos.getZ())):
                    self.camera.setPos(self.render, x, y, z)
            except Exception:
                pass

        def _update_mouse_look(self) -> None:
            if not self._mouse_look_active:
                return
            xy = self._window_pointer_xy()
            if xy is None:
                self._mouse_last_xy = None
                return
            if self._mouse_last_xy is None:
                self._mouse_last_xy = xy
                return
            dx = xy[0] - self._mouse_last_xy[0]
            dy = xy[1] - self._mouse_last_xy[1]
            self._mouse_last_xy = xy
            if dx or dy:
                self._camera_yaw -= float(dx) * self._mouse_sensitivity
                if self._first_person_active:
                    self._camera_pitch = max(-48.0, min(36.0, self._camera_pitch - float(dy) * self._mouse_sensitivity))
                else:
                    self._camera_pitch = max(-82.0, min(8.0, self._camera_pitch - float(dy) * self._mouse_sensitivity))

        def _first_person_camera_task(self, task, dt: float, speed: float):
            try:
                import math
                from panda3d.core import Vec3

                self._update_mouse_look()
                if self._keys.get("arrow_left"):
                    self._camera_yaw += 58.0 * dt
                if self._keys.get("arrow_right"):
                    self._camera_yaw -= 58.0 * dt
                if self._keys.get("arrow_up"):
                    self._camera_pitch = min(36.0, self._camera_pitch + 36.0 * dt)
                if self._keys.get("arrow_down"):
                    self._camera_pitch = max(-48.0, self._camera_pitch - 36.0 * dt)
                self.camera.setHpr(self._camera_yaw, self._camera_pitch, 0.0)

                move = 0.0
                strafe = 0.0
                if self._keys.get("w"):
                    move += 1.0
                if self._keys.get("s"):
                    move -= 1.0
                if self._keys.get("d"):
                    strafe += 1.0
                if self._keys.get("a"):
                    strafe -= 1.0
                if move or strafe:
                    walk_speed = self._first_person_jog_speed if self._keys.get("shift") else self._first_person_walk_speed
                    if self._keys.get("control"):
                        walk_speed *= 0.45
                    yaw = math.radians(float(self._camera_yaw))
                    forward = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
                    right = Vec3(math.cos(yaw), -math.sin(yaw), 0.0)
                    length = max(1.0, (move * move + strafe * strafe) ** 0.5)
                    delta = (forward * (move / length) + right * (strafe / length)) * walk_speed * dt
                    pos = self.camera.getPos(self.render) + delta
                    bounds = self._first_person_bounds if isinstance(self._first_person_bounds, dict) else {}
                    min_x = float(bounds.get("min_x", -1500.0))
                    max_x = float(bounds.get("max_x", 1500.0))
                    min_y = float(bounds.get("min_y", -1500.0))
                    max_y = float(bounds.get("max_y", 1500.0))
                    floor_z = float(bounds.get("floor_z", 8.0))
                    pos.setX(max(min_x, min(max_x, float(pos.getX()))))
                    pos.setY(max(min_y, min(max_y, float(pos.getY()))))
                    pos.setZ(max(5.8, floor_z))
                    self.camera.setPos(self.render, pos)

                # Keep a small runtime-state breadcrumb; debounced so it does not spam disk.
                try:
                    import time as _time
                    if _time.monotonic() - float(self._first_person_last_state_save or 0.0) > 0.75:
                        runtime = getattr(self, "holoutopia_runtime", None)
                        if runtime is not None and hasattr(runtime, "update_first_person_player_state"):
                            runtime.update_first_person_player_state(self.camera.getPos(self.render), self.camera.getHpr())
                        self._first_person_last_state_save = _time.monotonic()
                except Exception:
                    pass
            except Exception:
                pass
            return task.cont

        def _camera_task(self, task):
            try:
                dt = max(0.0, min(0.05, globalClock.getDt()))
            except Exception:
                dt = 1.0 / 60.0
            speed = self._camera_speed
            if self._keys.get("shift"):
                speed = self._camera_fast
            elif self._keys.get("control"):
                speed = self._camera_slow

            if self._first_person_active:
                return self._first_person_camera_task(task, dt, speed)

            self._update_mouse_look()
            if self._keys.get("arrow_left"):
                self._camera_yaw += 58.0 * dt
            if self._keys.get("arrow_right"):
                self._camera_yaw -= 58.0 * dt
            if self._keys.get("arrow_up"):
                self._camera_pitch = min(8.0, self._camera_pitch + 48.0 * dt)
            if self._keys.get("arrow_down"):
                self._camera_pitch = max(-82.0, self._camera_pitch - 48.0 * dt)
            self._sync_camera_hpr()

            move = 0.0
            strafe = 0.0
            rise = 0.0
            if self._keys.get("w"):
                move += 1.0
            if self._keys.get("s"):
                move -= 1.0
            if self._keys.get("d"):
                strafe += 1.0
            if self._keys.get("a"):
                strafe -= 1.0
            if self._keys.get("e") or self._keys.get("space"):
                rise += 1.0
            if self._keys.get("q"):
                rise -= 1.0
            length = max(1.0, (move * move + strafe * strafe + rise * rise) ** 0.5)
            if move or strafe or rise:
                if self._camera_orbit_enabled:
                    self._pan_orbit_target(strafe / length, move / length, rise / length, speed * dt)
                else:
                    self.camera.setPos(self.camera, (strafe / length) * speed * dt, (move / length) * speed * dt, (rise / length) * speed * dt)
                    self._clamp_camera_position()
            return task.cont

    return HoloUtopiaStandalone()


def main() -> int:
    app = build_app()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
