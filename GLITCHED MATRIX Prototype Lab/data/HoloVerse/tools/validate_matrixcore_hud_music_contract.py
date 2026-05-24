#!/usr/bin/env python3
"""Validate MatrixCore hover text and click-to-retune music behavior."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "matrixcore_hud_music_contract_report.json"
MAIN = ROOT / "main.py"


class FakeAudio:
    def __init__(self) -> None:
        self.enabled = True
        self.backend = "fake"
        self.looping: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    def _resolve_audio_path(self, filename: str, *, allow_vector_wars_fallback: bool = False) -> Path | None:
        # The contract validates routing/ownership; fake availability keeps it
        # deterministic on slim or generated-audio builds.
        return ROOT / "assets" / "audio" / str(filename or "fake.wav")

    def play(self, filename: str, bus: str = "sfx", volume: float = 1.0) -> None:
        self.events.append({"kind": "play", "filename": str(filename), "bus": str(bus), "volume": float(volume)})

    def play_loop(self, slot: str, filename: str, bus: str = "ambience", volume: float = 1.0) -> None:
        self.looping[str(slot)] = {"filename": str(filename), "bus": str(bus), "volume": float(volume)}
        self.events.append({"kind": "play_loop", "slot": str(slot), "filename": str(filename), "bus": str(bus), "volume": float(volume)})

    def stop_loop(self, slot: str) -> None:
        existed = str(slot) in self.looping
        self.looping.pop(str(slot), None)
        self.events.append({"kind": "stop_loop", "slot": str(slot), "existed": existed})

    def stop_all(self, *, stop_oneshots: bool = True) -> None:
        before = sorted(self.looping.keys())
        self.looping.clear()
        self.events.append({"kind": "stop_all", "before": before, "stop_oneshots": bool(stop_oneshots)})

    def refresh_mix(self) -> None:
        self.events.append({"kind": "refresh_mix"})


def _step(app: Any, frames: int = 1) -> None:
    for _ in range(max(0, int(frames))):
        app.taskMgr.step()


def _source_static_checks(errors: list[str], report: dict[str, Any]) -> None:
    text = MAIN.read_text(encoding="utf-8")
    report["static"] = {
        "retune_method": "def retune_matrixcore_music_on_dialogue" in text,
        "trigger_calls_retune": "self.retune_matrixcore_music_on_dialogue(source)" in text,
        "old_core_options_hint": "E // CORE OPTIONS" in text,
        "matrixcore_hint": 'self.center_hint["text"] = "MatrixCore"' in text,
    }
    if not report["static"]["retune_method"]:
        errors.append("MatrixCore retune method missing")
    if not report["static"]["trigger_calls_retune"]:
        errors.append("MatrixCore dialogue does not retune music")
    if report["static"]["old_core_options_hint"]:
        errors.append("old 'E // CORE OPTIONS' hint is still present")
    if not report["static"]["matrixcore_hint"]:
        errors.append("MatrixCore hover hint is not exactly 'MatrixCore'")


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
    report: dict[str, Any] = {"schema": 1, "kind": "matrixcore_hud_music_contract", "errors": errors, "checks": {}}
    try:
        _source_static_checks(errors, report)
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        sys.argv = ["main.py", "--self-test", "--matrixcore-hud-music-contract"]
        hv_main = importlib.import_module("main")
        app = hv_main.CommandHubApp()
        for task_name in ("self-test-setup", "self-test-exit", "matrixcore-gleebs-first-contact"):
            try:
                app.taskMgr.remove(task_name)
            except Exception:
                pass
        _step(app, 8)

        fake = FakeAudio()
        app.audio = fake
        app.soundscape_key = None
        app.player_pos.set(0.0, 0.0, getattr(app.player_pos, "z", 1.7))
        app.menu_open = False
        app.core_console_open = False
        app.active_native_mode = None
        app.external_process = None
        app.update_soundscape(0.0, force=True)
        before = dict(fake.looping.get("hub_music", {}))
        report["checks"]["before_hub_music"] = before

        app.animate_accents(0.016)
        hint = str(app.center_hint["text"])
        report["checks"]["near_core_hint"] = hint
        if hint != "MatrixCore":
            errors.append(f"near-Core HUD hint should be 'MatrixCore', got {hint!r}")

        chosen: list[str] = []
        for idx in range(3):
            ok = bool(app.trigger_matrixcore_dialogue(f"mouse1_contract_{idx}"))
            _step(app, 2)
            slot = dict(fake.looping.get("hub_music", {}) or {})
            chosen.append(str(slot.get("filename", "")))
            report["checks"][f"click_{idx}_shown"] = ok
            report["checks"][f"click_{idx}_hub_music"] = slot
            forbidden = sorted(set(fake.looping.keys()) & {"native_dimension_music", "native_dimension_air", "holocore_dimension_music", "holocore_dimension_air"})
            if forbidden:
                errors.append("MatrixCore click left dimension audio loops active: " + ",".join(forbidden))
            center_hint = str(app.center_hint["text"])
            if "MUSIC" in center_hint.upper() or "RETUNE" in center_hint.upper():
                errors.append("MatrixCore click displayed music/retune explanation in center hint")

        report["checks"]["music_choices"] = chosen
        report["checks"]["unique_music_choices"] = sorted(set(chosen))
        if len(set(chosen)) < 2:
            errors.append("MatrixCore clicks did not rotate to distinct hub music loops")
        if "hub_air" not in fake.looping:
            errors.append("MatrixCore click retune did not keep hub ambience owned by hub_air")
        report["checks"]["events_tail"] = fake.events[-60:]
    except Exception as exc:  # pragma: no cover
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
