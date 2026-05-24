#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ROOT / "Dimensions"

BAD_LITERAL_PATTERNS = [
    r"Path\(\s*['\"]generated_sfx['\"]\s*\)",
    r"Path\(\s*['\"]custom_sfx['\"]\s*\)",
    r"Path\(\s*['\"]sfx_overrides['\"]\s*\)",
    r"Path\(\s*['\"]generated_audio['\"]\s*\)",
    r"Path\(\s*['\"]crash_reports['\"]\s*\)",
]

ALLOWED_GUARDS = {
    "Dimensions/Holo Conquest/sitecustomize.py",
}


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits: list[str] = []
    for pattern in BAD_LITERAL_PATTERNS:
        if re.search(pattern, text):
            hits.append(pattern)
    return hits


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _validate_zonez(warnings: list[str]) -> None:
    manifest = _read_json(DIMENSIONS / "Zonez" / "holoverse_mode_manifest.json")
    if manifest.get("source_kind") != "panda3d_native_adapter_real_sandbox":
        warnings.append("Zonez manifest source_kind is not panda3d_native_adapter_real_sandbox")
    if not bool(manifest.get("pass77_zonez_real_sandbox_restore")):
        warnings.append("Zonez manifest does not mark pass77 real sandbox restore")


def _validate_vector_wars(errors: list[str], warnings: list[str]) -> None:
    manifest_path = DIMENSIONS / "Vector Wars" / "holoverse_mode_manifest.json"
    manifest = _read_json(manifest_path)
    policy = manifest.get("pass78_asset_audio_policy") if isinstance(manifest.get("pass78_asset_audio_policy"), dict) else {}
    if not policy:
        errors.append("Vector Wars manifest missing pass78_asset_audio_policy")
        return
    if not bool(policy.get("use_committed_assets_only")):
        errors.append("Vector Wars audio policy must require committed assets only")
    if bool(policy.get("allow_override_sfx")):
        errors.append("Vector Wars audio policy must not allow override SFX")
    if bool(policy.get("allow_generated_sfx_fallback")):
        errors.append("Vector Wars audio policy must not allow generated SFX fallback")
    forbidden = {str(item) for item in policy.get("forbidden_runtime_roots", []) if str(item).strip()}
    expected = {"custom_sfx", "sfx_overrides", "generated_sfx", "generated_audio"}
    missing = sorted(expected - forbidden)
    if missing:
        errors.append("Vector Wars audio policy missing forbidden roots: " + ", ".join(missing))
    if str(policy.get("profile") or "") != "audio_profile.json":
        warnings.append("Vector Wars audio policy does not point at audio_profile.json")
    if not bool(manifest.get("pass88_same_window_route_restored")):
        errors.append("Vector Wars manifest must mark pass88_same_window_route_restored")
    if str(manifest.get("launch_type") or "") != "native_panda":
        errors.append("Vector Wars must use native_panda so it stays inside HoloVerse")

    profile = _read_json(DIMENSIONS / "Vector Wars" / "audio_profile.json")
    profile_text = json.dumps(profile).lower()
    for forbidden_name in expected:
        if forbidden_name in profile_text:
            errors.append(f"Vector Wars audio_profile still references forbidden root: {forbidden_name}")


def main() -> int:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for path in sorted(DIMENSIONS.rglob("*.py")):
        rel = _rel(path)
        hits = _scan_file(path)
        if not hits:
            continue
        item = {"path": rel, "patterns": hits, "allowed_guard": rel in ALLOWED_GUARDS}
        findings.append(item)
        if rel in ALLOWED_GUARDS:
            continue
        errors.append(f"{rel}: cwd-relative generated asset folders: {', '.join(hits)}")

    _validate_zonez(warnings)
    _validate_vector_wars(errors, warnings)

    # Vector Wars must stay as one same-window adapter file.  Catch stale
    # wrapper/base sidecar regressions that previously broke packaging.
    vw_dir = DIMENSIONS / "Vector Wars"
    vw_adapter = vw_dir / "holoverse_native_adapter.py"
    vw_base = vw_dir / "holoverse_native_adapter_base.py"
    vw_wrapper = vw_dir / "holoverse_native_adapter_wrapper.py"
    try:
        adapter_text = vw_adapter.read_text(encoding="utf-8", errors="replace")
    except Exception:
        adapter_text = ""
    if vw_base.exists() or vw_wrapper.exists():
        errors.append("Vector Wars has stale wrapper/base adapter sidecar files")
    if "holoverse_native_adapter_base.py" in adapter_text:
        errors.append("Vector Wars adapter still references a sidecar base adapter")

    report = {
        "schema": 2,
        "kind": "generated_asset_path_validation",
        "root": _rel(ROOT),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
