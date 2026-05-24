#!/usr/bin/env python3
"""Animation registry and progress probe for Anti-Heroes character manifests.

This module is the next layer after `antiheroes_asset_bridge.py`.

GPTOOL exports rigged models and optional animation clips into:

    assets/characters/humans/human_manifest.json

This registry normalizes animation roles, checks whether model/animation files
exist, writes proof JSON, and can capture per-role progress screenshots when a
Panda3D runtime is available.

Direct commands from the Anti-Heroes folder:

    python antiheroes_animation_registry.py --write-registry
    python antiheroes_animation_registry.py --role-probe

Outputs:

    reports/antiheroes_animation_registry.json
    reports/antiheroes_animation_role_probe.json
    screenshots/progress/animation_roles/*.png
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PROJECT_ROOT / "assets" / "characters" / "humans" / "human_manifest.json"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "reports" / "antiheroes_animation_registry.json"
DEFAULT_ROLE_PROBE_PATH = PROJECT_ROOT / "reports" / "antiheroes_animation_role_probe.json"
DEFAULT_ROLE_SCREENSHOT_DIR = PROJECT_ROOT / "screenshots" / "progress" / "animation_roles"

ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "idle": ("idle", "stand", "standing", "breath", "breathe", "neutral"),
    "walk": ("walk", "walking", "move", "locomotion"),
    "run": ("run", "running", "sprint", "jog"),
    "jump": ("jump", "jumping", "leap"),
    "attack": ("attack", "punch", "kick", "strike", "melee", "combo", "shoot", "fire"),
    "hit": ("hit", "hurt", "damage", "impact", "react"),
    "fall": ("fall", "falling", "knockdown", "ragdoll"),
    "death": ("death", "die", "dying", "dead", "ko"),
    "get_up": ("get_up", "get up", "rise", "recover", "standup"),
    "block": ("block", "guard", "defend", "parry"),
}
ROLE_ORDER = tuple(ROLE_ALIASES.keys())


@dataclass
class RegistryBuildResult:
    ok: bool
    manifest_path: str
    manifest_exists: bool
    base_asset_count: int = 0
    animation_asset_count: int = 0
    role_map: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    missing_files: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "antiheroes_animation_registry.v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "ok": self.ok,
            "manifest_path": self.manifest_path,
            "manifest_exists": self.manifest_exists,
            "base_asset_count": self.base_asset_count,
            "animation_asset_count": self.animation_asset_count,
            "roles": list(ROLE_ORDER),
            "role_map": self.role_map,
            "missing_files": self.missing_files,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(project_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def normalize_role(text: str | None) -> str:
    raw = str(text or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return "unknown"
    collapsed = raw.replace("_", " ")
    for role, aliases in ROLE_ALIASES.items():
        if raw == role:
            return role
        for alias in aliases:
            alias_key = alias.lower().replace("-", "_").replace(" ", "_")
            if alias_key in raw or alias.lower() in collapsed:
                return role
    return raw


def _animation_record(project_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    rel = str(item.get("relative_path") or "")
    resolved = _resolve(project_root, rel)
    role = normalize_role(str(item.get("role") or item.get("id") or Path(rel).stem))
    return {
        "id": str(item.get("id") or Path(rel).stem or role),
        "role": role,
        "manifest_role": str(item.get("role") or ""),
        "relative_path": rel,
        "resolved_path": str(resolved) if resolved else "",
        "exists": bool(resolved and resolved.exists()),
        "summary": item.get("summary") or {},
    }


def _base_record(project_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    rel = str(item.get("relative_path") or "")
    resolved = _resolve(project_root, rel)
    summary = item.get("summary") or {}
    return {
        "id": str(item.get("id") or item.get("label") or Path(rel).stem or "base_asset"),
        "relative_path": rel,
        "resolved_path": str(resolved) if resolved else "",
        "exists": bool(resolved and resolved.exists()),
        "runtime_role": str(item.get("runtime_role") or ""),
        "has_skin": bool(summary.get("has_skin")),
        "has_animation": bool(summary.get("has_animation")),
        "animation_names": list(summary.get("animation_names") or []),
        "summary": summary,
    }


def build_animation_registry(project_root: Path | str = PROJECT_ROOT, manifest_path: Path | str | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest = Path(manifest_path).resolve() if manifest_path else (root / "assets" / "characters" / "humans" / "human_manifest.json").resolve()
    if not manifest.exists():
        result = RegistryBuildResult(
            ok=False,
            manifest_path=str(manifest),
            manifest_exists=False,
            warnings=["human_manifest.json was not found; run GPTOOL import-human-assets first."],
            notes=["Registry can still be generated as a missing-manifest proof report."],
        )
        return result.to_dict()

    try:
        data = _load_json(manifest)
    except Exception as exc:
        result = RegistryBuildResult(
            ok=False,
            manifest_path=str(manifest),
            manifest_exists=True,
            warnings=[f"Manifest parse failed: {type(exc).__name__}: {exc}"],
        )
        return result.to_dict()

    base_assets = [_base_record(root, item) for item in data.get("base_assets", []) if isinstance(item, dict)]
    animation_assets = [_animation_record(root, item) for item in data.get("animations", []) if isinstance(item, dict)]
    role_map: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLE_ORDER}
    role_map["unknown"] = []
    for item in animation_assets:
        role = item.get("role") or "unknown"
        role_map.setdefault(str(role), []).append(item)

    missing: list[dict[str, str]] = []
    for item in base_assets:
        if not item.get("exists"):
            missing.append({"kind": "base_asset", "id": item.get("id", ""), "path": item.get("resolved_path", "")})
    for item in animation_assets:
        if not item.get("exists"):
            missing.append({"kind": "animation", "id": item.get("id", ""), "path": item.get("resolved_path", "")})

    warnings: list[str] = []
    if not base_assets:
        warnings.append("Manifest has no base assets.")
    if not any(item.get("exists") for item in base_assets):
        warnings.append("No base model file exists at the resolved manifest paths.")
    if not animation_assets:
        warnings.append("Manifest has no external animation clips; embedded model animations may still exist.")
    if missing:
        warnings.append("One or more manifest asset paths are missing on disk.")

    covered_roles = [role for role, items in role_map.items() if role != "unknown" and items]
    missing_core_roles = [role for role in ("idle", "walk", "run") if role not in covered_roles]
    if missing_core_roles:
        warnings.append("Missing external animation role coverage: " + ", ".join(missing_core_roles))

    result = RegistryBuildResult(
        ok=bool(base_assets) and any(item.get("exists") for item in base_assets),
        manifest_path=str(manifest),
        manifest_exists=True,
        base_asset_count=len(base_assets),
        animation_asset_count=len(animation_assets),
        role_map=role_map,
        missing_files=missing,
        warnings=warnings,
        notes=[
            "External clips only bind when their skeleton matches the loaded base Actor.",
            "Embedded GLB/GLTF animations are discovered by Panda3D Actor at runtime and reported by the role probe.",
            "Anti-Heroes should treat missing role clips as warnings, not launch blockers.",
        ],
    )
    payload = result.to_dict()
    payload["base_assets"] = base_assets
    payload["animation_assets"] = animation_assets
    payload["covered_roles"] = covered_roles
    payload["missing_core_roles"] = missing_core_roles
    return payload


def choose_actor_animation(actor: Any, role: str) -> str:
    try:
        names = sorted(str(name) for name in actor.getAnimNames())
    except Exception:
        return ""
    if not names:
        return ""
    target = normalize_role(role)
    aliases = ROLE_ALIASES.get(target, (target,))
    lowered = [(name, name.lower().replace("-", "_").replace(" ", "_")) for name in names]
    for alias in aliases:
        alias_key = alias.lower().replace("-", "_").replace(" ", "_")
        for name, low in lowered:
            if alias_key in low:
                return name
    for name, low in lowered:
        if target in low:
            return name
    return ""


def loop_actor_role(actor: Any, role: str) -> tuple[bool, str, str]:
    chosen = choose_actor_animation(actor, role)
    if not chosen:
        return False, "", f"No Actor animation matched role `{role}`."
    try:
        actor.loop(chosen)
        return True, chosen, ""
    except Exception as exc:
        return False, chosen, f"Animation `{chosen}` matched role `{role}` but failed to loop: {type(exc).__name__}: {exc}"


def run_role_probe(
    *,
    project_root: Path | str = PROJECT_ROOT,
    manifest_path: Path | str | None = None,
    screenshot_dir: Path | str = DEFAULT_ROLE_SCREENSHOT_DIR,
    proof_path: Path | str = DEFAULT_ROLE_PROBE_PATH,
    width: int = 1600,
    height: int = 900,
    window_type: str = "offscreen",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    screenshot_root = Path(screenshot_dir).resolve()
    proof = Path(proof_path).resolve()
    screenshot_root.mkdir(parents=True, exist_ok=True)
    proof.parent.mkdir(parents=True, exist_ok=True)

    registry = build_animation_registry(root, manifest_path)
    try:
        from panda3d.core import AmbientLight, CardMaker, DirectionalLight, LineSegs, TextNode, loadPrcFileData
        from direct.showbase.ShowBase import ShowBase
        from antiheroes_asset_bridge import AntiHeroesAssetBridge
    except Exception as exc:
        payload = {
            "schema_version": "antiheroes_animation_role_probe.v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "ok": False,
            "reason": f"Panda3D or asset bridge import failed: {type(exc).__name__}: {exc}",
            "registry": registry,
            "screenshots": {},
        }
        _write_json(proof, payload)
        return payload

    loadPrcFileData("", f"win-size {int(width)} {int(height)}")
    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "window-title Anti-Heroes Animation Role Probe")
    if window_type == "offscreen":
        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "load-display p3tinydisplay")

    class RoleProbeApp(ShowBase):
        def __init__(self) -> None:
            super().__init__(windowType=window_type if window_type in {"offscreen", "none"} else None)
            self.disableMouse()
            self.setBackgroundColor(0.02, 0.025, 0.035, 1)
            self.camera.setPos(0, -18, 7)
            self.camera.lookAt(0, 0, 2.2)
            self.screenshots: dict[str, str] = {}
            self.role_results: list[dict[str, Any]] = []
            self.bridge = AntiHeroesAssetBridge(project_root=root, manifest_path=Path(manifest_path).resolve() if manifest_path else None)
            self.actor_node = None
            self.load_result = None
            self._build_scene_shell()
            self.actor_node, self.load_result = self.bridge.load_into_scene(loader=self.loader, parent=self.render, pos=(0, 0, 0.05), scale=1.0)
            self._capture_roles()

        def _step_frames(self, count: int) -> None:
            for _ in range(max(1, int(count))):
                self.taskMgr.step()

        def _save(self, role: str) -> str:
            path = screenshot_root / f"antiheroes_anim_role_{role}.png"
            try:
                self.win.saveScreenshot(str(path))
            except Exception:
                pass
            self.screenshots[role] = str(path)
            return str(path)

        def _label(self, text: str, z: float = 4.2) -> None:
            node = TextNode("role_probe_label")
            node.setText(text)
            node.setAlign(TextNode.ACenter)
            np = self.render.attachNewNode(node)
            np.setPos(0, -2.7, z)
            np.setScale(0.42)
            np.setHpr(0, -18, 0)
            np.setColor(0.0, 0.9, 1.0, 1.0)
            self._last_label = np

        def _build_scene_shell(self) -> None:
            ambient = AmbientLight("role_probe_ambient")
            ambient.setColor((0.46, 0.48, 0.58, 1))
            self.render.setLight(self.render.attachNewNode(ambient))
            key = DirectionalLight("role_probe_key")
            key.setColor((1.0, 0.95, 0.86, 1))
            key_np = self.render.attachNewNode(key)
            key_np.setHpr(-32, -45, 0)
            self.render.setLight(key_np)

            cm = CardMaker("role_probe_ground")
            cm.setFrame(-10, 10, -10, 10)
            ground = self.render.attachNewNode(cm.generate())
            ground.setP(-90)
            ground.setColor(0.08, 0.085, 0.11, 1)

            lines = LineSegs()
            lines.setThickness(1.2)
            lines.setColor(0.0, 0.75, 1.0, 0.8)
            for i in range(-10, 11, 2):
                lines.moveTo(i, -10, 0.03)
                lines.drawTo(i, 10, 0.03)
                lines.moveTo(-10, i, 0.03)
                lines.drawTo(10, i, 0.03)
            self.render.attachNewNode(lines.create())

        def _capture_roles(self) -> None:
            if self.actor_node is None:
                self._label("No Actor/static model loaded for role probe", 3.5)
                self._step_frames(4)
                self._save("no_model")
                self.role_results.append({"role": "no_model", "ok": False, "reason": "No node loaded."})
                return

            is_actor = bool(getattr(self.load_result, "actor_loaded", False))
            for role in ROLE_ORDER:
                chosen = ""
                reason = ""
                ok = False
                if is_actor:
                    ok, chosen, reason = loop_actor_role(self.actor_node, role)
                else:
                    reason = "Static fallback loaded; role animation cannot be played."

                label = f"Role: {role} | {'OK' if ok else 'missing'} | {chosen or 'no clip'}"
                old = getattr(self, "_last_label", None)
                if old is not None:
                    try:
                        old.removeNode()
                    except Exception:
                        pass
                self._label(label)
                self._step_frames(12 if ok else 4)
                shot = self._save(role)
                self.role_results.append({
                    "role": role,
                    "ok": ok,
                    "selected_animation": chosen,
                    "reason": reason,
                    "screenshot": shot,
                })

    app = RoleProbeApp()
    payload = {
        "schema_version": "antiheroes_animation_role_probe.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": bool(app.load_result and app.load_result.ok),
        "window_type": window_type,
        "width": width,
        "height": height,
        "registry": registry,
        "load_result": app.load_result.to_dict() if app.load_result else None,
        "role_results": app.role_results,
        "screenshots": app.screenshots,
        "notes": [
            "Screenshots show progress by requested animation role, not guaranteed distinct motion frames.",
            "A role can be missing even when the Actor loads successfully; this should not crash Anti-Heroes.",
        ],
    }
    _write_json(proof, payload)
    try:
        app.destroy()
    except Exception:
        pass
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/probe Anti-Heroes animation registry from GPTOOL manifests.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Anti-Heroes project folder.")
    parser.add_argument("--manifest", default=None, help="Optional explicit human_manifest.json path.")
    parser.add_argument("--write-registry", action="store_true", help="Write reports/antiheroes_animation_registry.json.")
    parser.add_argument("--role-probe", action="store_true", help="Capture per-role screenshots with Panda3D when available.")
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--proof-path", default=str(DEFAULT_ROLE_PROBE_PATH))
    parser.add_argument("--screenshot-dir", default=str(DEFAULT_ROLE_SCREENSHOT_DIR))
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--window-type", default="offscreen", choices=["offscreen", "default", "none"])
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    manifest = Path(args.manifest).resolve() if args.manifest else None

    if args.role_probe:
        try:
            payload = run_role_probe(
                project_root=root,
                manifest_path=manifest,
                screenshot_dir=Path(args.screenshot_dir).resolve(),
                proof_path=Path(args.proof_path).resolve(),
                width=args.width,
                height=args.height,
                window_type=args.window_type,
            )
            print(json.dumps(payload, indent=2, default=str))
            return 0 if payload.get("ok") else 1
        except Exception as exc:
            crash = root / "reports" / "antiheroes_animation_role_probe_crash.txt"
            crash.parent.mkdir(parents=True, exist_ok=True)
            crash.write_text(
                "Anti-Heroes animation role probe crashed\n\n"
                f"Exception: {type(exc).__name__}: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
                errors="replace",
            )
            print(f"Role probe crashed; report written to {crash}", file=sys.stderr)
            return 1

    payload = build_animation_registry(root, manifest)
    if args.write_registry or not args.role_probe:
        _write_json(Path(args.registry_path).resolve(), payload)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
