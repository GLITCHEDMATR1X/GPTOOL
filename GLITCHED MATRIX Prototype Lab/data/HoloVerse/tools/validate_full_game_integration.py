#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIM = ROOT / "Dimensions"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def j(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    vw = DIM / "Vector Wars"
    if (vw / "holoverse_native_adapter_base.py").exists():
        errors.append("Vector Wars still has holoverse_native_adapter_base.py; stale split adapter must not return")
    if (vw / "holoverse_native_adapter_wrapper.py").exists():
        errors.append("Vector Wars still has holoverse_native_adapter_wrapper.py; stale wrapper must not return")
    vw_manifest = j(vw / "holoverse_mode_manifest.json")
    if not bool(vw_manifest.get("pass88_same_window_route_restored")):
        errors.append("Vector Wars must use the pass88 same-window route to avoid separate tiny child windows")
    if str(vw_manifest.get("launch_type")) != "native_panda":
        errors.append("Vector Wars launch_type must be native_panda so it stays inside HoloVerse")
    if str(vw_manifest.get("native_adapter") or "") != "holoverse_native_adapter.py":
        errors.append("Vector Wars must route artifact slot 5 through the one-file same-window adapter")
    if str(vw_manifest.get("source_kind")) != "pygame_source_panda3d_native_port":
        errors.append("Vector Wars source_kind must identify the pygame source as a Panda3D native port, not an external child app")
    if bool(vw_manifest.get("pass87_real_main_py_route")):
        errors.append("Vector Wars pass87 external main.py route must remain disabled")

    main_py = read(ROOT / "main.py")
    if "def stop_external_panda_audio(self):" not in main_py:
        errors.append("SharedAudio missing stop_external_panda_audio")
    if "self.stop_external_panda_audio()" not in main_py:
        errors.append("SharedAudio.stop_all must stop unmanaged adapter audio")
    if "active_native_mode" not in main_py or "hub_music" not in main_py:
        errors.append("Root soundscape must stay gated while native/external modes own the scene")
    if "self._start_native_mode_audio(label)" not in main_py:
        errors.append("Root scene audio must start for native or embedded dimension routes")
    if "reload_default_holoverse_shell(reason=f\"native_return_" not in main_py:
        errors.append("Native returns must reload the default HoloVerse shell at a safe hub anchor")
    if "reload_default_holoverse_shell(reason=\"external_return\")" not in main_py:
        errors.append("External returns must reload the default HoloVerse shell at a safe hub anchor")
    if main_py.count('print(f"native_mode_begin label={label}")') > 1:
        errors.append("Duplicate native_mode_begin print remains")
    if main_py.count('self._append_mode_gateway_history("native_return"') > 1:
        warnings.append("Multiple native_return history appends detected")

    vw_main = read(vw / "main.py")
    if "def holoverse_root_owns_music()" not in vw_main:
        errors.append("Vector Wars main.py must honor HoloVerse root music ownership")
    if "NEON_DOGFIGHT_DISABLE_MUSIC" not in vw_main:
        errors.append("Vector Wars main.py missing child music disable guard")

    hc = DIM / "Holo Campaign"
    hc_main = read(hc / "main.py")
    if 'GAME_NAME = "Etchline: Noir City Assault"' in hc_main:
        errors.append("Holo Campaign still exposes Etchline GAME_NAME")
    if 'window-title Etchline: Noir City Assault' in hc_main:
        errors.append("Holo Campaign still exposes Etchline window title")
    hc_manifest = j(hc / "holoverse_mode_manifest.json")
    if not bool(hc_manifest.get("pass84_campaign_identity_contained")):
        errors.append("Holo Campaign manifest missing pass84 containment flag")

    report = {"schema": 2, "kind": "full_game_integration_validation", "ok": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
