"""Optional Panda3D smoke-test hook for GPT Game Generation Bridge.

Usage inside a Panda3D app, after ShowBase exists:

    from runtime_hooks.panda3d_smoke_hook import install_from_env
    install_from_env(base)

Then run through the bridge:

    python bridge.py panda3d-smoke . --entry main.py --require-screenshot

The hook only activates when GPT_BRIDGE_SMOKE=1 or GPT_BRIDGE_TEST_MODE=1 is in
the environment, so it is safe to leave imported in development builds.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _safe_float_tuple(value: Any) -> list[float] | None:
    try:
        return [round(float(value[i]), 4) for i in range(3)]
    except Exception:
        return None


def _child_count(node: Any) -> int | None:
    try:
        return int(node.getNumChildren())
    except Exception:
        try:
            return len(node.getChildren())
        except Exception:
            return None


def _write_scene_proof(base: Any, proof_path: str | None, screenshot_path: str | None, screenshot_exists: bool, status: str) -> None:
    if not proof_path:
        return
    path = Path(proof_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        panda_version = importlib.metadata.version("panda3d")
    except Exception:
        panda_version = None
    camera_pos = _safe_float_tuple(getattr(getattr(base, "camera", None), "getPos", lambda: None)())
    render = getattr(base, "render", None)
    aspect2d = getattr(base, "aspect2d", None)
    extra_state = None
    try:
        state_fn = getattr(base, "gpt_bridge_scene_state", None)
        if callable(state_fn):
            extra_state = state_fn()
    except Exception as exc:
        extra_state = {"error": f"{type(exc).__name__}: {exc}"}
    proof = {
        "schema_version": "panda3d_smoke_proof.v1",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "python_executable": sys.executable,
        "panda3d_version": panda_version,
        "window_type_hint": os.getenv("GPT_BRIDGE_WINDOW_TYPE", "default"),
        "has_window": bool(getattr(base, "win", None)),
        "scene": {
            "render_child_count": _child_count(render),
            "aspect2d_child_count": _child_count(aspect2d),
            "camera_position": camera_pos,
        },
        "screenshot": {
            "path": str(Path(screenshot_path).expanduser().resolve()) if screenshot_path else None,
            "exists": bool(screenshot_exists),
            "requested": bool(screenshot_path),
        },
        "environment": {
            "GPT_BRIDGE_SMOKE": os.getenv("GPT_BRIDGE_SMOKE"),
            "GPT_BRIDGE_TEST_MODE": os.getenv("GPT_BRIDGE_TEST_MODE"),
            "GPT_BRIDGE_RUNTIME_PROVIDER": os.getenv("GPT_BRIDGE_RUNTIME_PROVIDER"),
        },
    }
    if extra_state is not None:
        proof["app_state"] = extra_state
    path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"GPT_BRIDGE_SCENE_PROOF_WRITTEN: {path}", flush=True)


def install_smoke_test_hook(
    base: Any,
    *,
    screenshot_path: str | None = None,
    proof_path: str | None = None,
    frames: int = 4,
    exit_after_screenshot: bool = True,
    task_name: str = "gpt_bridge_smoke_capture",
) -> bool:
    """Install a tiny frame-delayed screenshot/exit hook on a ShowBase instance.

    Returns True when the hook was installed. Returns False if no usable task
    manager/window was found.
    """
    if base is None or not hasattr(base, "taskMgr"):
        return False

    state = {"frame_count": 0, "captured": False}

    def _capture(task: Any) -> Any:
        state["frame_count"] += 1
        if state["frame_count"] < max(1, int(frames)):
            return task.cont

        screenshot_exists = False
        if screenshot_path and not state["captured"]:
            try:
                from panda3d.core import Filename

                path = Path(screenshot_path).expanduser().resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    base.graphicsEngine.renderFrame()
                except Exception:
                    pass
                if getattr(base, "win", None):
                    base.win.saveScreenshot(Filename.fromOsSpecific(str(path)))
                screenshot_exists = path.exists()
                state["captured"] = True
            except Exception as exc:
                print(f"GPT_BRIDGE_SCREENSHOT_FAILED: {type(exc).__name__}: {exc}", flush=True)
        else:
            screenshot_exists = Path(screenshot_path).expanduser().resolve().exists() if screenshot_path else False

        _write_scene_proof(
            base,
            proof_path,
            screenshot_path,
            screenshot_exists,
            "screenshot_captured" if screenshot_exists else "headless_scene_built",
        )

        if exit_after_screenshot:
            # userExit() is not always enough in headless/offscreen containers;
            # raising SystemExit gives automated proof runs a deterministic stop.
            raise SystemExit(0)
        return task.done

    base.taskMgr.add(_capture, task_name, sort=-100)
    print("GPT_BRIDGE_SMOKE_HOOK_INSTALLED", flush=True)
    return True


def install_from_env(base: Any | None = None) -> bool:
    """Install the hook only when the bridge smoke environment is active."""
    if not (_truthy(os.getenv("GPT_BRIDGE_SMOKE")) or _truthy(os.getenv("GPT_BRIDGE_TEST_MODE"))):
        return False
    if base is None:
        try:
            from direct.showbase.ShowBaseGlobal import base as global_base
            base = global_base
        except Exception:
            base = None
    return install_smoke_test_hook(
        base,
        screenshot_path=os.getenv("GPT_BRIDGE_SCREENSHOT_PATH"),
        proof_path=os.getenv("GPT_BRIDGE_SMOKE_PROOF_PATH"),
        frames=int(os.getenv("GPT_BRIDGE_SMOKE_FRAMES") or "4"),
        exit_after_screenshot=_truthy(os.getenv("GPT_BRIDGE_EXIT_AFTER_SCREENSHOT", "1")),
    )
