from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Protocol

CAPSULE_CONTRACT_VERSION = "app_capsule.v1"

class HostServices(Protocol):
    camera: Any
    audio: Any
    input: Any
    ui: Any
    assets: Any
    save: Any
    transition: Any
    logger: Any
    results: Any

class AppCapsule(Protocol):
    def prepare(self, host: HostServices) -> None: ...
    def enter(self, context: dict[str, Any] | None = None) -> None: ...
    def update(self, dt: float) -> None: ...
    def exit(self, reason: str = "return_to_host") -> None: ...
    def cleanup(self) -> None: ...
    def get_result(self) -> dict[str, Any]: ...

@dataclass(frozen=True)
class CapsuleResult:
    app_id: str
    exit_reason: str = "return_to_host"
    score_delta: int = 0
    discoveries: tuple[str, ...] = ()
    memory_fragments: tuple[str, ...] = ()
    unlocks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def validate_capsule_object(obj: Any) -> list[str]:
    return [name for name in ("prepare", "enter", "update", "exit", "cleanup", "get_result") if not callable(getattr(obj, name, None))]

def load_capsule_manifest(path: str | Path) -> dict[str, Any]:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))
