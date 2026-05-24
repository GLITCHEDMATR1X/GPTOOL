#!/usr/bin/env python3
"""Validate same-window dimension audio contracts without launching Panda3D.

This is a static, no-window check for the HoloVerse artifact audio path:
- every audio_profile.json event must resolve to at least one real SFX file;
- profile music must resolve when a profile declares a loop;
- Code Red must not be wired to a muted NullSound relay.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ROOT / "Dimensions"

import sys
sys.path.insert(0, str(ROOT))
import holoverse_mode_runtime as hv_runtime  # noqa: E402


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    checked: list[dict[str, Any]] = []

    for profile_path in sorted(DIMENSIONS.glob("*/audio_profile.json")):
        mode_dir = profile_path.parent
        profile = _read_json(profile_path)
        mode_name = str(profile.get("mode") or mode_dir.name)
        item: dict[str, Any] = {
            "mode": mode_name,
            "profile": _rel(profile_path),
            "events": {},
            "music": None,
            "ok": True,
            "issues": [],
        }
        music_name = str(profile.get("music_loop") or "").strip()
        if music_name:
            music_path = hv_runtime.profile_music_path(profile=profile, mode_dir=mode_dir)
            item["music"] = _rel(music_path) if music_path else None
            if music_path is None:
                item["issues"].append(f"music-missing:{music_name}")
        events = profile.get("events") if isinstance(profile.get("events"), dict) else {}
        for event in sorted(events):
            files = hv_runtime.profile_sfx_files(str(event), profile=profile, mode_dir=mode_dir)
            item["events"][str(event)] = [_rel(path) for path in files[:4]]
            if not files:
                item["issues"].append(f"event-sfx-missing:{event}")
        if item["issues"]:
            item["ok"] = False
            errors.append(f"{mode_name}: " + ", ".join(item["issues"]))
        checked.append(item)

    code_red_adapter = DIMENSIONS / "Code Red Vector" / "holoverse_native_adapter.py"
    if code_red_adapter.exists():
        text = code_red_adapter.read_text(encoding="utf-8", errors="replace")
        if "_NullSound" in text or "audio muted in HoloVerse native adapter" in text:
            errors.append("Code Red Vector: muted NullSound relay still present")
        if "_HostSoundRelay" not in text:
            warnings.append("Code Red Vector: host sound relay not detected")

    report = {
        "schema": 1,
        "kind": "dimension_audio_contract_validation",
        "profiles_checked": len(checked),
        "ok_count": sum(1 for item in checked if item["ok"]),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
        "profiles": checked,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
