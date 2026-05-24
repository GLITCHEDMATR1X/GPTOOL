#!/usr/bin/env python3
"""Anti-Heroes model/animation bridge for GPTOOL exported character assets.

This module is intentionally safe to add before editing the live Anti-Heroes
runtime. It can be imported by the game later, or run directly as a visual probe.

Primary source:
    assets/characters/humans/human_manifest.json

That manifest is written by GPTOOL's `import-human-assets` command. The bridge
prefers Panda3D Actor loading so rigged models and compatible animations survive,
then falls back to static loadModel without crashing the city route.

Direct proof command:
    python antiheroes_asset_bridge.py --visual-probe

Outputs:
    screenshots/progress/antiheroes_asset_probe_before.png
    screenshots/progress/antiheroes_asset_probe_after.png
    reports/antiheroes_asset_bridge_proof.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PROJECT_ROOT / "assets" / "characters" / "humans" / "human_manifest.json"
DEFAULT_SCREENSHOT_DIR = PROJECT_ROOT / "screenshots" / "progress"
DEFAULT_PROOF_PATH = PROJECT_ROOT / "reports" / "antiheroes_asset_bridge_proof.json"
BRIDGE_VERSION = "antiheroes_asset_bridge.v1"

ANIMATION_PRIORITY = (
    "idle",
    "walk",
    "run",
    "jump",
    "attack",
    "hit",
    "fall",
    "death",
    "get_up",
    "block",
)


@dataclass
class AssetLoadResult:
    ok: bool
    model_id: str = ""
    model_path: str = ""
    actor_loaded: bool = False
    static_loaded: bool = False
    available_animations: list[str] = field(default_factory=list)
    current_animation: str = ""
    fallback_reason: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "actor_loaded": self.actor_loaded,
            "static_loaded": self.static_loaded,
            "available_animations": self.available_animations,
            "current_animation": self.current_animation,
            "fallback_reason": self.fallback_reason,
            "notes": self.notes,
        }


class AntiHeroesAssetBridge:
    """Manifest-driven model loader for Anti-Heroes.

    The class has no dependency on ShowBase construction. Pass the active Panda3D
    `loader` and parent NodePath when you are ready to spawn a model.
    """

    def __init__(self, project_root: Path | str | None = None, manifest_path: Path | str | None = None) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.manifest_path = Path(manifest_path).resolve() if manifest_path else self._find_manifest()
        self.manifest: dict[str, Any] = self._load_manifest()

    def _find_manifest(self) -> Path:
        candidates = [
            DEFAULT_MANIFEST,
            self.project_root / "assets" / "characters" / "humans" / "human_manifest.json",
            self.project_root / "assets" / "characters" / "human_manifest.json",
            self.project_root / "characters" / "humans" / "human_manifest.json",
        ]
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return (self.project_root / "assets" / "characters" / "humans" / "human_manifest.json").resolve()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {
                "schema_version": "human_asset_manifest.missing",
                "base_assets": [],
                "animations": [],
                "notes": [f"Manifest not found: {self.manifest_path}"],
            }
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "schema_version": "human_asset_manifest.invalid",
                "base_assets": [],
                "animations": [],
                "notes": [f"Manifest failed to parse: {exc}"],
            }

    def _resolve_manifest_path(self, rel_path: str | None) -> Path | None:
        if not rel_path:
            return None
        raw = Path(str(rel_path))
        if raw.is_absolute():
            return raw
        return (self.project_root / raw).resolve()

    def base_assets(self) -> list[dict[str, Any]]:
        return [item for item in self.manifest.get("base_assets", []) if isinstance(item, dict)]

    def animation_assets(self) -> list[dict[str, Any]]:
        return [item for item in self.manifest.get("animations", []) if isinstance(item, dict)]

    def animation_library(self) -> dict[str, str]:
        library: dict[str, str] = {}
        used: set[str] = set()
        for item in self.animation_assets():
            rel_path = item.get("relative_path")
            path = self._resolve_manifest_path(rel_path)
            if not path or not path.exists():
                continue
            role = str(item.get("role") or item.get("id") or path.stem).strip().lower().replace(" ", "_")
            if not role:
                role = path.stem.lower()
            if role in used:
                role = f"{role}_{len(used) + 1}"
            used.add(role)
            library[role] = str(path)
        return library

    def select_base_asset(self, requested_id: str | None = None, index: int = 0) -> dict[str, Any] | None:
        assets = self.base_assets()
        if not assets:
            return None
        if requested_id:
            for item in assets:
                if str(item.get("id") or "") == requested_id:
                    return item
        return assets[index % len(assets)]

    @staticmethod
    def _safe_anim_names(actor: Any) -> list[str]:
        try:
            return sorted(str(name) for name in actor.getAnimNames())
        except Exception:
            return []

    @staticmethod
    def _choose_animation(names: list[str], preferred: tuple[str, ...] = ("idle", "walk", "run")) -> str:
        lower_pairs = [(name, name.lower()) for name in names]
        for token in preferred:
            for name, lower in lower_pairs:
                if token in lower:
                    return name
        return names[0] if names else ""

    def load_into_scene(
        self,
        *,
        loader: Any,
        parent: Any,
        requested_id: str | None = None,
        index: int = 0,
        pos: tuple[float, float, float] = (0.0, 0.0, 0.05),
        scale: float = 1.0,
        hpr: tuple[float, float, float] = (180.0, 0.0, 0.0),
    ) -> tuple[Any | None, AssetLoadResult]:
        asset = self.select_base_asset(requested_id=requested_id, index=index)
        if not asset:
            return None, AssetLoadResult(
                ok=False,
                fallback_reason="No base assets found in human_manifest.json.",
                notes=list(self.manifest.get("notes", [])),
            )

        model_id = str(asset.get("id") or asset.get("label") or "imported_human")
        model_path = self._resolve_manifest_path(asset.get("relative_path"))
        if not model_path or not model_path.exists():
            return None, AssetLoadResult(
                ok=False,
                model_id=model_id,
                model_path=str(model_path or ""),
                fallback_reason="Selected manifest asset path does not exist.",
            )

        animation_library = self.animation_library()
        actor_error = ""
        try:
            from direct.actor.Actor import Actor

            actor_args: tuple[Any, ...]
            if animation_library:
                actor_args = (str(model_path), animation_library)
            else:
                actor_args = (str(model_path),)
            node = Actor(*actor_args)
            node.reparentTo(parent)
            node.setPos(*pos)
            node.setHpr(*hpr)
            node.setScale(scale)
            try:
                node.setTwoSided(True)
            except Exception:
                pass
            names = self._safe_anim_names(node)
            chosen = self._choose_animation(names)
            if chosen:
                try:
                    node.loop(chosen)
                except Exception as exc:
                    actor_error = f"Actor loaded but animation loop failed: {exc}"
            return node, AssetLoadResult(
                ok=True,
                model_id=model_id,
                model_path=str(model_path),
                actor_loaded=True,
                available_animations=names,
                current_animation=chosen,
                fallback_reason=actor_error,
                notes=["Loaded with Panda3D Actor; rig/animation path preferred."],
            )
        except Exception as exc:
            actor_error = f"Actor load failed: {type(exc).__name__}: {exc}"

        try:
            node = loader.loadModel(str(model_path))
            node.reparentTo(parent)
            node.setPos(*pos)
            node.setHpr(*hpr)
            node.setScale(scale)
            try:
                node.setTwoSided(True)
            except Exception:
                pass
            return node, AssetLoadResult(
                ok=True,
                model_id=model_id,
                model_path=str(model_path),
                static_loaded=True,
                fallback_reason=actor_error,
                notes=["Static model fallback loaded; animation was not bound."],
            )
        except Exception as exc:
            return None, AssetLoadResult(
                ok=False,
                model_id=model_id,
                model_path=str(model_path),
                fallback_reason=f"{actor_error}; static fallback failed: {type(exc).__name__}: {exc}",
            )

    def proof_payload(self, result: AssetLoadResult | None = None, screenshot_paths: dict[str, str] | None = None) -> dict[str, Any]:
        assets = self.base_assets()
        animations = self.animation_assets()
        return {
            "schema_version": "antiheroes_asset_bridge_proof.v1",
            "bridge_version": BRIDGE_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(self.project_root),
            "manifest_path": str(self.manifest_path),
            "manifest_exists": self.manifest_path.exists(),
            "base_asset_count": len(assets),
            "animation_asset_count": len(animations),
            "base_asset_ids": [str(item.get("id") or item.get("label") or "") for item in assets],
            "animation_roles": [str(item.get("role") or item.get("id") or "") for item in animations],
            "load_result": result.to_dict() if result else None,
            "screenshots": screenshot_paths or {},
            "notes": list(self.manifest.get("notes", [])),
        }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def run_visual_probe(
    *,
    project_root: Path,
    manifest_path: Path | None = None,
    screenshot_dir: Path = DEFAULT_SCREENSHOT_DIR,
    proof_path: Path = DEFAULT_PROOF_PATH,
    width: int = 1600,
    height: int = 900,
    window_type: str = "offscreen",
) -> dict[str, Any]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    proof_path.parent.mkdir(parents=True, exist_ok=True)

    before_path = screenshot_dir / "antiheroes_asset_probe_before.png"
    after_path = screenshot_dir / "antiheroes_asset_probe_after.png"
    diff_note_path = screenshot_dir / "antiheroes_asset_probe_diff_notes.json"

    try:
        from panda3d.core import AmbientLight, CardMaker, DirectionalLight, LineSegs, TextNode, Vec3, loadPrcFileData
        from direct.showbase.ShowBase import ShowBase
    except Exception as exc:
        bridge = AntiHeroesAssetBridge(project_root=project_root, manifest_path=manifest_path)
        payload = bridge.proof_payload(
            AssetLoadResult(ok=False, fallback_reason=f"Panda3D import failed: {type(exc).__name__}: {exc}"),
            {},
        )
        payload["visual_probe"] = {"ok": False, "reason": "Panda3D is unavailable; screenshots were not captured."}
        _write_json(proof_path, payload)
        return payload

    loadPrcFileData("", f"win-size {int(width)} {int(height)}")
    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "window-title Anti-Heroes Asset Bridge Visual Probe")
    if window_type == "offscreen":
        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "load-display p3tinydisplay")

    class ProbeApp(ShowBase):
        def __init__(self) -> None:
            super().__init__(windowType=window_type if window_type in {"offscreen", "none"} else None)
            self.disableMouse()
            self.setBackgroundColor(0.025, 0.03, 0.045, 1)
            self.camera.setPos(0, -20, 8)
            self.camera.lookAt(0, 0, 2.2)
            self.bridge = AntiHeroesAssetBridge(project_root=project_root, manifest_path=manifest_path)
            self.load_result: AssetLoadResult | None = None
            self.screenshots: dict[str, str] = {}
            self._build_scene(label="BEFORE: city route reference grid", include_actor=False)
            self._step_frames(4)
            self._save_screenshot(before_path)
            self.render.getChildren().detach()
            self._build_scene(label="AFTER: GPTOOL manifest model probe", include_actor=True)
            self._step_frames(8)
            self._save_screenshot(after_path)

        def _step_frames(self, count: int) -> None:
            for _ in range(max(1, int(count))):
                self.taskMgr.step()

        def _save_screenshot(self, path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.win.saveScreenshot(str(path))
            except Exception:
                pass
            self.screenshots[path.stem] = str(path)

        def _add_label(self, text: str, pos: tuple[float, float, float], scale: float = 0.72) -> None:
            node = TextNode("probe_label")
            node.setText(text)
            node.setAlign(TextNode.ACenter)
            np = self.render.attachNewNode(node)
            np.setPos(*pos)
            np.setScale(scale)
            np.setHpr(0, -20, 0)
            np.setColor(0.0, 0.9, 1.0, 1.0)

        def _build_grid(self) -> None:
            cm = CardMaker("probe_ground")
            cm.setFrame(-14, 14, -14, 14)
            ground = self.render.attachNewNode(cm.generate())
            ground.setP(-90)
            ground.setColor(0.08, 0.09, 0.12, 1.0)
            lines = LineSegs()
            lines.setThickness(1.4)
            lines.setColor(0.0, 0.75, 1.0, 0.82)
            for i in range(-14, 15, 2):
                lines.moveTo(i, -14, 0.025)
                lines.drawTo(i, 14, 0.025)
                lines.moveTo(-14, i, 0.025)
                lines.drawTo(14, i, 0.025)
            self.render.attachNewNode(lines.create())

        def _build_district_markers(self) -> None:
            markers = [
                ("NORTH: CONTRACTS", (0, 10, 0.1), (0.9, 0.75, 0.2, 1)),
                ("EAST: VENDOR", (10, 0, 0.1), (0.2, 0.9, 0.55, 1)),
                ("SOUTH: SAFEHOUSE", (0, -10, 0.1), (0.8, 0.25, 0.95, 1)),
                ("WEST: REARM", (-10, 0, 0.1), (0.95, 0.25, 0.18, 1)),
            ]
            for label, pos, color in markers:
                box = self.loader.loadModel("models/box")
                box.reparentTo(self.render)
                box.setPos(*pos)
                box.setScale(0.55, 0.55, 1.4)
                box.setColor(*color)
                self._add_label(label, (pos[0], pos[1], 2.25), 0.45)

        def _build_lights(self) -> None:
            ambient = AmbientLight("probe_ambient")
            ambient.setColor((0.45, 0.48, 0.56, 1))
            self.render.setLight(self.render.attachNewNode(ambient))
            key = DirectionalLight("probe_key")
            key.setColor((1.0, 0.96, 0.88, 1))
            key_np = self.render.attachNewNode(key)
            key_np.setHpr(-38, -42, 0)
            self.render.setLight(key_np)

        def _spawn_placeholder(self) -> None:
            body = self.loader.loadModel("models/box")
            body.reparentTo(self.render)
            body.setPos(0, 0, 1.35)
            body.setScale(0.75, 0.9, 1.75)
            body.setColor(0.15, 0.75, 1.0, 1.0)
            head = self.loader.loadModel("models/smiley")
            head.reparentTo(self.render)
            head.setPos(0, 0, 3.35)
            head.setScale(0.62)
            head.setColor(0.9, 0.95, 1.0, 1.0)

        def _build_scene(self, label: str, include_actor: bool) -> None:
            self._build_lights()
            self._build_grid()
            self._build_district_markers()
            self._add_label(label, (0, -12.8, 3.2), 0.62)
            if include_actor:
                node, result = self.bridge.load_into_scene(
                    loader=self.loader,
                    parent=self.render,
                    pos=(0, 0, 0.05),
                    scale=1.0,
                )
                self.load_result = result
                if node is None:
                    self._spawn_placeholder()
                    self._add_label("No compatible manifest model loaded — placeholder only", (0, 0, 4.3), 0.43)
                else:
                    self._add_label(
                        f"Loaded: {result.model_id} | Actor: {result.actor_loaded} | Anim: {result.current_animation or 'none'}",
                        (0, 0, 4.2),
                        0.42,
                    )

    app = ProbeApp()
    screenshots = {
        "before": str(before_path),
        "after": str(after_path),
        "diff_notes": str(diff_note_path),
    }
    diff_notes = {
        "schema_version": "antiheroes_visual_progress_diff.v1",
        "before": str(before_path),
        "after": str(after_path),
        "meaning": "Before shows the city/district reference probe. After adds the selected GPTOOL manifest character or fallback placeholder.",
        "manual_review": [
            "Confirm a character appears near the center of the city grid.",
            "Confirm district/service markers remain visible after the model loads.",
            "Confirm Actor loading and current animation in the proof JSON when a compatible rig is present.",
        ],
    }
    _write_json(diff_note_path, diff_notes)
    payload = app.bridge.proof_payload(app.load_result, screenshots)
    payload["visual_probe"] = {"ok": True, "window_type": window_type, "width": width, "height": height}
    _write_json(proof_path, payload)
    try:
        app.destroy()
    except Exception:
        pass
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe GPTOOL-exported character assets for Anti-Heroes.")
    parser.add_argument("--visual-probe", action="store_true", help="Capture before/after screenshots into screenshots/progress.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Anti-Heroes project folder.")
    parser.add_argument("--manifest", default=None, help="Optional explicit human_manifest.json path.")
    parser.add_argument("--screenshot-dir", default=str(DEFAULT_SCREENSHOT_DIR), help="Screenshot/progress output folder.")
    parser.add_argument("--proof-path", default=str(DEFAULT_PROOF_PATH), help="Proof JSON output path.")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--window-type", default="offscreen", choices=["offscreen", "default", "none"])
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    screenshot_dir = Path(args.screenshot_dir).resolve()
    proof_path = Path(args.proof_path).resolve()

    if args.visual_probe:
        try:
            payload = run_visual_probe(
                project_root=project_root,
                manifest_path=manifest_path,
                screenshot_dir=screenshot_dir,
                proof_path=proof_path,
                width=args.width,
                height=args.height,
                window_type=args.window_type,
            )
            print(json.dumps(payload, indent=2, default=str))
            return 0 if payload.get("visual_probe", {}).get("ok") else 1
        except Exception as exc:
            crash_path = project_root / "reports" / "antiheroes_asset_bridge_crash.txt"
            crash_path.parent.mkdir(parents=True, exist_ok=True)
            crash_path.write_text(
                "Anti-Heroes asset bridge visual probe crashed\n\n"
                f"Exception: {type(exc).__name__}: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
                errors="replace",
            )
            print(f"Probe crashed; report written to {crash_path}", file=sys.stderr)
            return 1

    bridge = AntiHeroesAssetBridge(project_root=project_root, manifest_path=manifest_path)
    payload = bridge.proof_payload()
    _write_json(proof_path, payload)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("manifest_exists") else 1


if __name__ == "__main__":
    raise SystemExit(main())
