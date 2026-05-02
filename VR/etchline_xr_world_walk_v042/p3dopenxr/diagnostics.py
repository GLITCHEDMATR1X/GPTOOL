from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import time
from typing import Any


@dataclass
class XRActionSnapshot:
    action_name: str
    hand: str | None = None
    state_type: str = 'unknown'
    is_active: bool = False
    changed_since_last_sync: bool = False
    current_state: Any = None
    pose_valid: bool = False
    tracked: bool = False


@dataclass
class XRPoseSnapshot:
    name: str
    valid: bool = False
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


@dataclass
class XRRuntimeDiagnostics:
    application_name: str = 'unknown'
    runtime_name: str = 'unknown'
    runtime_version: str = 'unknown'
    system_name: str = 'unknown'
    session_state: str = 'unknown'
    tracking_space: str = 'unknown'
    session_active: bool = False
    should_render: bool = False
    frame_index: int = 0
    headset_tracked: bool = False
    left_controller_tracked: bool = False
    right_controller_tracked: bool = False
    poses: list[XRPoseSnapshot] = field(default_factory=list)
    actions: list[XRActionSnapshot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    timestamp_utc: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
