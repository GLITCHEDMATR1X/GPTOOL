#!/usr/bin/env python3
"""Runtime-facing character adapter for Anti-Heroes.

This module is the safe integration seam between the live Anti-Heroes runtime and
GPTOOL-exported character manifests.

It does not construct ShowBase and does not alter the existing game loop. Import
it from the Anti-Heroes runtime after the world/player scene exists, then call
`spawn_manifest_character(...)` with the active Panda3D loader and scene parent.

Example runtime usage:

    from antiheroes_character_runtime_adapter import AntiHeroesCharacterRuntime

    character_runtime = AntiHeroesCharacterRuntime(project_root=Path(__file__).parent)
    node, state = character_runtime.spawn_manifest_character(
        loader=base.loader,
        parent=render,
        role="player",
        pos=(0, 0, 0.05),
        scale=1.0,
    )

    # In your movement/update code:
    character_runtime.set_motion_state("walk", speed=4.0)

    # Before saving proof:
    proof_payload = character_runtime.snapshot_state()

This keeps Anti-Heroes dependent on GPTOOL only for asset export/import while the
live game gains its own manifest reader, animation-role controller, and proof
state. Once Anti-Heroes owns its asset UI, GPTOOL can remain only a helper.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = PROJECT_ROOT / "reports" / "antiheroes_character_runtime_state.json"

ROLE_PRIORITY = ("idle", "walk", "run", "jump", "attack", "hit", "fall", "death", "get_up", "block")
MOTION_STATE_TO_ROLE = {
    "idle": "idle",
    "stand": "idle",
    "walk": "walk",
    "move": "walk",
    "run": "run",
    "sprint": "run",
    "jump": "jump",
    "attack": "attack",
    "hit": "hit",
    "hurt": "hit",
    "fall": "fall",
    "death": "death",
    "dead": "death",
    "get_up": "get_up",
    "recover": "get_up",
    "block": "block",
    "guard": "block",
}


@dataclass
class RuntimeCharacterState:
    ok: bool = False
    role: str = "npc"
    model_id: str = ""
    actor_loaded: bool = False
    static_loaded: bool = False
    current_motion_state: str = "idle"
    current_animation_role: str = "idle"
    current_animation_name: str = ""
    available_animations: list[str] = field(default_factory=list)
    missing_roles: list[str] = field(default_factory=list)
    fallback_reason: str = ""
    last_error: str = ""
    spawned_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "role": self.role,
            "model_id": self.model_id,
            "actor_loaded": self.actor_loaded,
            "static_loaded": self.static_loaded,
            "current_motion_state": self.current_motion_state,
            "current_animation_role": self.current_animation_role,
            "current_animation_name": self.current_animation_name,
            "available_animations": self.available_animations,
            "missing_roles": self.missing_roles,
            "fallback_reason": self.fallback_reason,
            "last_error": self.last_error,
            "spawned_at": self.spawned_at,
        }


class AntiHeroesCharacterRuntime:
    """Small adapter the live Anti-Heroes runtime can call later.

    Responsibilities:
    - load the GPTOOL manifest through `AntiHeroesAssetBridge`;
    - keep a stable runtime state payload;
    - map movement/combat states to animation roles;
    - never crash the game when a clip is missing or incompatible.
    """

    def __init__(
        self,
        project_root: Path | str | None = None,
        manifest_path: Path | str | None = None,
        state_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.manifest_path = Path(manifest_path).resolve() if manifest_path else None
        self.state_path = Path(state_path).resolve() if state_path else (self.project_root / "reports" / "antiheroes_character_runtime_state.json")
        self.node: Any | None = None
        self.bridge: Any | None = None
        self.state = RuntimeCharacterState(spawned_at=datetime.now().isoformat(timespec="seconds"))

    def _import_bridge(self) -> tuple[Any | None, str]:
        try:
            from antiheroes_asset_bridge import AntiHeroesAssetBridge

            return AntiHeroesAssetBridge, ""
        except Exception as exc:
            return None, f"Failed to import antiheroes_asset_bridge: {type(exc).__name__}: {exc}"

    @staticmethod
    def _safe_anim_names(node: Any) -> list[str]:
        try:
            return sorted(str(name) for name in node.getAnimNames())
        except Exception:
            return []

    @staticmethod
    def _normalize_motion_state(motion_state: str) -> str:
        text = str(motion_state or "idle").strip().lower().replace("-", "_").replace(" ", "_")
        return text or "idle"

    @staticmethod
    def _role_for_motion(motion_state: str, speed: float = 0.0) -> str:
        text = AntiHeroesCharacterRuntime._normalize_motion_state(motion_state)
        if text in {"move", "walk", "locomotion"} and speed >= 6.0:
            return "run"
        return MOTION_STATE_TO_ROLE.get(text, "idle")

    @staticmethod
    def _choose_anim_for_role(names: list[str], role: str) -> str:
        if not names:
            return ""
        role = str(role or "idle").lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "idle": ("idle", "stand", "standing", "neutral", "breath"),
            "walk": ("walk", "walking", "move"),
            "run": ("run", "running", "sprint", "jog"),
            "jump": ("jump", "leap"),
            "attack": ("attack", "punch", "kick", "strike", "shoot", "fire"),
            "hit": ("hit", "hurt", "damage", "react"),
            "fall": ("fall", "knockdown"),
            "death": ("death", "die", "dead", "ko"),
            "get_up": ("get_up", "getup", "rise", "recover", "standup"),
            "block": ("block", "guard", "defend", "parry"),
        }.get(role, (role,))
        lowered = [(name, name.lower().replace("-", "_").replace(" ", "_")) for name in names]
        for alias in aliases:
            key = alias.lower().replace("-", "_").replace(" ", "_")
            for name, low in lowered:
                if key in low:
                    return name
        for name, low in lowered:
            if role in low:
                return name
        return ""

    def spawn_manifest_character(
        self,
        *,
        loader: Any,
        parent: Any,
        role: str = "npc",
        requested_id: str | None = None,
        index: int = 0,
        pos: tuple[float, float, float] = (0.0, 0.0, 0.05),
        scale: float = 1.0,
        hpr: tuple[float, float, float] = (180.0, 0.0, 0.0),
        initial_motion: str = "idle",
    ) -> tuple[Any | None, dict[str, Any]]:
        BridgeClass, error = self._import_bridge()
        if BridgeClass is None:
            self.state.last_error = error
            self.state.fallback_reason = error
            self.write_state()
            return None, self.snapshot_state()

        try:
            self.bridge = BridgeClass(project_root=self.project_root, manifest_path=self.manifest_path)
            node, result = self.bridge.load_into_scene(
                loader=loader,
                parent=parent,
                requested_id=requested_id,
                index=index,
                pos=pos,
                scale=scale,
                hpr=hpr,
            )
            self.node = node
            available = list(getattr(result, "available_animations", []) or self._safe_anim_names(node)) if node is not None else []
            missing_roles = [role_name for role_name in ROLE_PRIORITY if not self._choose_anim_for_role(available, role_name)]
            self.state = RuntimeCharacterState(
                ok=bool(result.ok),
                role=role,
                model_id=str(result.model_id or ""),
                actor_loaded=bool(result.actor_loaded),
                static_loaded=bool(result.static_loaded),
                current_motion_state="idle",
                current_animation_role="idle",
                current_animation_name="",
                available_animations=available,
                missing_roles=missing_roles,
                fallback_reason=str(result.fallback_reason or ""),
                spawned_at=datetime.now().isoformat(timespec="seconds"),
            )
            self.set_motion_state(initial_motion)
            self.write_state()
            return node, self.snapshot_state()
        except Exception as exc:
            self.state.last_error = f"spawn_manifest_character failed: {type(exc).__name__}: {exc}"
            self.state.fallback_reason = traceback.format_exc(limit=8)
            self.write_state()
            return None, self.snapshot_state()

    def set_motion_state(self, motion_state: str, *, speed: float = 0.0, force: bool = False) -> dict[str, Any]:
        role = self._role_for_motion(motion_state, speed=speed)
        self.state.current_motion_state = self._normalize_motion_state(motion_state)
        self.state.current_animation_role = role

        if self.node is None:
            self.state.current_animation_name = ""
            self.state.last_error = "No character node is loaded."
            self.write_state()
            return self.snapshot_state()

        if not self.state.actor_loaded:
            self.state.current_animation_name = ""
            self.state.last_error = "Static fallback node has no Actor animation controller."
            self.write_state()
            return self.snapshot_state()

        chosen = self._choose_anim_for_role(self.state.available_animations, role)
        if not chosen:
            self.state.current_animation_name = ""
            self.state.last_error = f"No animation clip matched role `{role}`."
            self.write_state()
            return self.snapshot_state()

        if not force and self.state.current_animation_name == chosen:
            self.write_state()
            return self.snapshot_state()

        try:
            self.node.loop(chosen)
            self.state.current_animation_name = chosen
            self.state.last_error = ""
        except Exception as exc:
            self.state.last_error = f"Animation `{chosen}` failed to loop: {type(exc).__name__}: {exc}"
        self.write_state()
        return self.snapshot_state()

    def detach(self) -> dict[str, Any]:
        if self.node is not None:
            try:
                self.node.detachNode()
            except Exception:
                pass
        self.node = None
        self.write_state()
        return self.snapshot_state()

    def snapshot_state(self) -> dict[str, Any]:
        return {
            "schema_version": "antiheroes_character_runtime_state.v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(self.project_root),
            "manifest_path": str(self.manifest_path or self.project_root / "assets" / "characters" / "humans" / "human_manifest.json"),
            "state": self.state.to_dict(),
            "integration_notes": [
                "Call spawn_manifest_character after the Panda3D scene exists.",
                "Call set_motion_state from movement/combat state changes.",
                "Missing animations are warnings; they should not crash the live route.",
                "Anti-Heroes can become independent by keeping this state shape and replacing GPTOOL as the exporter only.",
            ],
        }

    def write_state(self, path: Path | str | None = None) -> dict[str, Any]:
        payload = self.snapshot_state()
        out = Path(path).resolve() if path else self.state_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        return payload


def _demo_state_only(project_root: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    runtime = AntiHeroesCharacterRuntime(project_root=project_root, manifest_path=manifest_path)
    runtime.state.last_error = "State-only demo did not create a Panda3D scene. Use antiheroes_asset_bridge.py or the live runtime for model loading."
    runtime.write_state()
    return runtime.snapshot_state()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Anti-Heroes runtime-facing character adapter state helper.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--state-only", action="store_true", help="Write a state/proof file without constructing Panda3D.")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    manifest = Path(args.manifest).resolve() if args.manifest else None
    if args.state_only:
        runtime = AntiHeroesCharacterRuntime(project_root=root, manifest_path=manifest, state_path=Path(args.state_path).resolve())
        runtime.state.last_error = "State-only proof; no Panda3D scene was created."
        payload = runtime.write_state()
        print(json.dumps(payload, indent=2, default=str))
        return 0

    payload = _demo_state_only(root, manifest)
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
