#!/usr/bin/env python3
"""Validate same-window HoloCore owns exactly one music bed.

HoloCore used to start the generic native-dimension music layer, then start its
own reversed dimension music layer on top.  This contract uses an instrumented
fake audio bus so the check is deterministic even on CI machines without a real
sound device.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_audio_ownership_contract_report.json"


class FakeAudio:
    def __init__(self) -> None:
        self.enabled = True
        self.backend = "fake"
        self.looping: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []


    def _resolve_audio_path(self, filename: str, *, allow_vector_wars_fallback: bool = False) -> Path | None:
        return ROOT / "assets" / "audio" / str(filename or "fake.wav")

    def reversed_clip_for(self, filename: str) -> str:
        text = str(filename or "")
        if text.endswith(".wav"):
            return text[:-4] + "_reversed.wav"
        return text

    def play(self, filename: str, bus: str = "sfx", volume: float = 1.0) -> None:
        self.events.append({"kind": "play", "filename": str(filename), "bus": str(bus), "volume": float(volume)})

    def play_loop(self, slot: str, filename: str, bus: str = "ambience", volume: float = 1.0) -> None:
        slot = str(slot)
        self.looping[slot] = {"filename": str(filename), "bus": str(bus), "volume": float(volume)}
        self.events.append({"kind": "play_loop", "slot": slot, "filename": str(filename), "bus": str(bus), "volume": float(volume)})

    def stop_loop(self, slot: str) -> None:
        slot = str(slot)
        existed = slot in self.looping
        self.looping.pop(slot, None)
        self.events.append({"kind": "stop_loop", "slot": slot, "existed": existed})

    def stop_all(self, *, stop_oneshots: bool = True) -> None:
        before = sorted(self.looping.keys())
        self.looping.clear()
        self.events.append({"kind": "stop_all", "before": before, "stop_oneshots": bool(stop_oneshots)})

    def refresh_mix(self) -> None:
        self.events.append({"kind": "refresh_mix"})


def _step(app: Any, frames: int) -> None:
    for _ in range(max(0, int(frames))):
        app.taskMgr.step()


def _holocore_mode(hv_main: Any) -> dict[str, Any]:
    record = hv_main.dimension_record_from_index("holocore")
    if not isinstance(record, dict):
        raise RuntimeError("holocore dimension index record missing")
    mode = hv_main.mode_from_dimension_record(record)
    if not isinstance(mode, dict):
        raise RuntimeError("holocore mode conversion failed")
    return mode


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MATRIX_GAME_WIDTH", "960")
    os.environ.setdefault("MATRIX_GAME_HEIGHT", "540")
    os.environ.setdefault("MATRIX_GAME_BORDERED_FULLSCREEN", "0")
    os.environ.setdefault("MATRIX_GAME_BORDERLESS", "0")
    os.environ.setdefault("MATRIX_GAME_FULLSCREEN", "0")
    os.environ.setdefault("HOLOVERSE_NATIVE_ADAPTER_LOGS", "0")

    old_cwd = Path.cwd()
    old_argv = list(sys.argv)
    app = None
    errors: list[str] = []
    report: dict[str, Any] = {"schema": 1, "kind": "holocore_audio_ownership_contract", "errors": errors, "checks": {}}
    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        sys.argv = ["main.py", "--self-test", "--holocore-audio-ownership-contract"]
        hv_main = importlib.import_module("main")
        app = hv_main.CommandHubApp()
        for task_name in ("self-test-setup", "self-test-exit"):
            try:
                app.taskMgr.remove(task_name)
            except Exception:
                pass
        _step(app, 8)

        fake = FakeAudio()
        app.audio = fake
        app.soundscape_key = None
        app.update_soundscape(0.0, force=True)
        report["checks"]["before_hub_slots"] = sorted(fake.looping.keys())
        if "hub_music" not in fake.looping or "hub_air" not in fake.looping:
            errors.append("hub soundscape did not start before HoloCore launch")

        mode = _holocore_mode(hv_main)
        ok = bool(app.launch_holocore_same_window(mode, source="holocore-audio-contract"))
        _step(app, 20)
        report["checks"]["launch_ok"] = ok
        if not ok:
            errors.append("holocore same-window launch failed")
        during_slots = sorted(fake.looping.keys())
        report["checks"]["during_slots"] = during_slots
        report["checks"]["during_loops"] = dict(fake.looping)
        forbidden_during = sorted(set(during_slots) & {"hub_music", "hub_air", "native_dimension_music", "native_dimension_air"})
        if forbidden_during:
            errors.append("forbidden HoloCore overlap slots active during same-window play: " + ",".join(forbidden_during))
        required_during = {"holocore_dimension_music", "holocore_dimension_air"}
        missing_during = sorted(required_during - set(during_slots))
        if missing_during:
            errors.append("HoloCore dimension loops missing during play: " + ",".join(missing_during))

        mode_obj = getattr(app, "active_native_mode", None)
        if mode_obj is not None:
            handled = bool(getattr(mode_obj, "on_host_action")("tab"))
            _step(app, 8)
            report["checks"]["tab_cycle_handled"] = handled
            report["checks"]["after_tab_slots"] = sorted(fake.looping.keys())
            forbidden_after_tab = sorted(set(fake.looping.keys()) & {"hub_music", "hub_air", "native_dimension_music", "native_dimension_air"})
            if forbidden_after_tab:
                errors.append("forbidden overlap slots after HoloCore tab cycle: " + ",".join(forbidden_after_tab))

        app.return_from_native_mode(reason="holocore-audio-contract")
        _step(app, 14)
        after_slots = sorted(fake.looping.keys())
        report["checks"]["after_return_slots"] = after_slots
        report["checks"]["after_return_loops"] = dict(fake.looping)
        forbidden_after = sorted(set(after_slots) & {"holocore_dimension_music", "holocore_dimension_air", "native_dimension_music", "native_dimension_air"})
        if forbidden_after:
            errors.append("dimension audio still active after HoloCore return: " + ",".join(forbidden_after))
        if "hub_music" not in fake.looping or "hub_air" not in fake.looping:
            errors.append("hub soundscape was not restored after HoloCore return")
        report["checks"]["events"] = fake.events[-80:]
    except Exception as exc:  # pragma: no cover - validator output is the failure report
        errors.append(f"validator exception: {exc.__class__.__name__}:{exc}")
    finally:
        try:
            if app is not None and hasattr(app, "destroy"):
                app.destroy()
        except Exception:
            pass
        sys.argv = old_argv
        try:
            os.chdir(old_cwd)
        except Exception:
            pass

    report["status"] = "PASS" if not errors else "FAIL"
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
