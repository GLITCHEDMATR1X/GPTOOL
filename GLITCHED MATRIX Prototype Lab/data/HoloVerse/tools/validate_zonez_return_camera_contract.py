#!/usr/bin/env python3
"""Validate Zonez same-window return restores normal HoloVerse camera control.

Zonez uses a source drone avatar/chase camera internally.  This smoke ensures
that after leaving the same-window Zonez adapter the host is back in ground-foot
HoloVerse control, not still using Zonez's drone camera/mouse capture state.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "zonez_return_camera_contract_report.json"
SCREENSHOT = ROOT / "logs" / "zonez_return_camera_smoke.png"


def _vec3_tuple(value: Any) -> tuple[float, float, float]:
    return (round(float(value.x), 4), round(float(value.y), 4), round(float(value.z), 4))


def _camera_parent_name(app: Any) -> str:
    try:
        return str(app.camera.getParent().getName())
    except Exception:
        return ""


def _render_zonez_residue(app: Any) -> list[str]:
    found: list[str] = []
    for root_name in ("render", "aspect2d", "render2d", "camera"):
        root = getattr(app, root_name, None)
        if root is None:
            continue
        try:
            for node in root.findAllMatches("**/*"):
                name = str(node.getName() or "")
                lowered = name.lower()
                if lowered.startswith(("zonez_", "zonez-")) or lowered in {"zonez_world", "zonez_hud", "drone_rig", "player_root"}:
                    found.append(f"{root_name}:{name}")
        except Exception:
            pass
    return found[:20]


def _run_probe() -> dict[str, Any]:
    os.environ.setdefault("MATRIX_GAME_WIDTH", "960")
    os.environ.setdefault("MATRIX_GAME_HEIGHT", "540")
    os.environ.setdefault("MATRIX_GAME_BORDERED_FULLSCREEN", "0")
    os.environ.setdefault("MATRIX_GAME_BORDERLESS", "0")
    os.environ.setdefault("MATRIX_GAME_FULLSCREEN", "0")
    os.environ.setdefault("HOLOVERSE_NATIVE_ADAPTER_LOGS", "0")

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    # main.py reads SELF_TEST at import time.  Keep the route offscreen, then
    # remove its generic self-test tasks so this validator controls launch/exit.
    sys.argv = ["main.py", "--self-test", "--zonez-return-camera-contract"]
    import main as hv  # pylint: disable=import-error,import-outside-toplevel

    app = hv.CommandHubApp()
    app.taskMgr.remove("self-test-setup")
    app.taskMgr.remove("self-test-exit")
    for _ in range(4):
        app.taskMgr.step()

    mode_folder = ROOT / "Dimensions" / "Zonez"
    manifest = json.loads((mode_folder / "holoverse_mode_manifest.json").read_text(encoding="utf-8"))
    mode = {"name": "Zonez", "id": "zonez", "folder": mode_folder, "manifest": manifest}
    entry = mode_folder / "main.py"

    before = {
        "camera_parent": _camera_parent_name(app),
        "camera_pos": _vec3_tuple(app.camera.getPos(app.render)),
        "camera_hpr": _vec3_tuple(app.camera.getHpr(app.render)),
        "player_pos": _vec3_tuple(app.player_pos),
    }
    launch_ok = bool(app.launch_native_mode(mode, entry, "Zonez", source="zonez-return-camera-contract"))
    for _ in range(16):
        app.taskMgr.step()
    mode_obj = getattr(app, "active_native_mode", None)
    zonez_app = getattr(mode_obj, "app", None)
    during = {
        "launch_ok": launch_ok,
        "active_native_mode": type(mode_obj).__name__ if mode_obj is not None else "",
        "camera_parent": _camera_parent_name(app),
        "camera_pos": _vec3_tuple(app.camera.getPos(app.render)),
        "camera_hpr": _vec3_tuple(app.camera.getHpr(app.render)),
        "zonez_mouse_captured": bool(getattr(zonez_app, "mouse_captured", False)),
        "zonez_first_person": bool(getattr(zonez_app, "first_person", False)),
    }

    app.return_from_native_mode(reason="zonez-return-camera-contract")
    for _ in range(10):
        app.taskMgr.step()

    try:
        if getattr(app, "win", None) is not None:
            from panda3d.core import Filename  # pylint: disable=import-outside-toplevel
            app.win.saveScreenshot(Filename.fromOsSpecific(str(SCREENSHOT)))
    except Exception:
        pass

    after = {
        "active_native_mode": type(getattr(app, "active_native_mode", None)).__name__ if getattr(app, "active_native_mode", None) is not None else "",
        "native_mode_isolated": bool(getattr(app, "native_mode_isolated", False)),
        "camera_parent": _camera_parent_name(app),
        "camera_pos": _vec3_tuple(app.camera.getPos(app.render)),
        "camera_hpr": _vec3_tuple(app.camera.getHpr(app.render)),
        "player_pos": _vec3_tuple(app.player_pos),
        "player_yaw": round(float(getattr(app, "player_yaw", 999.0)), 4),
        "player_pitch": round(float(getattr(app, "player_pitch", 999.0)), 4),
        "holospace_active": bool(getattr(app, "holospace_active", False)),
        "flight_active": bool(getattr(app, "shell_flight_craft_active", False)),
        "world_signature": str(getattr(app, "runtime_world_signature", "")),
        "active_world_state": str(getattr(app, "active_world_runtime_state_label", "")),
        "root_3d_hidden": bool(app.root_3d.isHidden()) if getattr(app, "root_3d", None) is not None else True,
        "zonez_residue": _render_zonez_residue(app),
    }

    errors: list[str] = []
    if not launch_ok:
        errors.append("zonez-launch-failed")
    if during["active_native_mode"] != "HoloVerseNativeMode":
        errors.append("zonez-native-mode-not-active")
    if during["zonez_mouse_captured"] is not True:
        errors.append("zonez-mouse-not-captured-while-active")
    if after["active_native_mode"]:
        errors.append("active-native-mode-left-after-return")
    if after["native_mode_isolated"]:
        errors.append("native-mode-isolated-left-after-return")
    if after["camera_parent"] != "render":
        errors.append(f"camera-parent-not-render:{after['camera_parent']}")
    if after["camera_pos"] != after["player_pos"]:
        errors.append("camera-not-reset-to-player-foot-anchor")
    if abs(float(after["player_pitch"]) - (-6.0)) > 0.1:
        errors.append("player-pitch-not-ground-return-default")
    if after["holospace_active"]:
        errors.append("holospace-still-active-after-zonez-return")
    if after["flight_active"]:
        errors.append("flight-craft-still-active-after-zonez-return")
    if after["root_3d_hidden"]:
        errors.append("hub-root-hidden-after-zonez-return")
    if after["zonez_residue"]:
        errors.append("zonez-scene-residue-left-after-return")
    if "HOLOVERSE DEFAULT" not in after["world_signature"]:
        errors.append("default-world-signature-not-restored")

    report = {
        "schema": 1,
        "kind": "zonez_return_camera_contract",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "before": before,
        "during": during,
        "after": after,
        "screenshot": str(SCREENSHOT) if SCREENSHOT.exists() else "",
    }
    return report


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    try:
        if SCREENSHOT.exists():
            SCREENSHOT.unlink()
    except Exception:
        pass
    report = _run_probe()
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass
    os._exit(0 if report.get("status") == "PASS" else 2)


if __name__ == "__main__":
    main()
