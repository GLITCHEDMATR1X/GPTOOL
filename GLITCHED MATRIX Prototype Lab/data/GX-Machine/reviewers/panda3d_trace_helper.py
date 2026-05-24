from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class BridgeTraceState:
    grounded: bool | None = None
    collision_count: int | None = None
    current_anim: str | None = None
    label: str | None = None
    player_radius: float | None = None
    eye_height: float | None = None
    speed_hint: float | None = None
    vertical_speed_hint: float | None = None
    controller_hints: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = {
            'grounded': self.grounded,
            'collision_count': self.collision_count,
            'current_anim': self.current_anim,
            'label': self.label,
            'player_radius': self.player_radius,
            'eye_height': self.eye_height,
            'speed_hint': self.speed_hint,
            'vertical_speed_hint': self.vertical_speed_hint,
            'controller_hints': dict(self.controller_hints) if self.controller_hints else None,
            'notes': list(self.notes),
        }
        return {k: v for k, v in data.items() if v is not None and v != []}


class Panda3DTraceHelper:
    def __init__(
        self,
        base,
        target,
        camera=None,
        actor=None,
        *,
        label: str | None = None,
        player_radius: float | None = None,
        eye_height: float | None = None,
        grounded_getter: Callable[[], bool] | None = None,
        collision_getter: Callable[[], int] | None = None,
        anim_getter: Callable[[], str | None] | None = None,
        auto_task: bool = True,
        task_name: str = 'bridge-trace-helper-poll',
    ):
        self.base = base
        self.target = target
        self.camera = camera or getattr(base, 'camera', None)
        self.actor = actor or target
        self.grounded_getter = grounded_getter
        self.collision_getter = collision_getter
        self.anim_getter = anim_getter
        self.task_name = task_name
        self.state = BridgeTraceState(
            label=label,
            player_radius=player_radius,
            eye_height=eye_height,
        )
        self._last_pos = None
        self._last_t = None
        self._task_attached = False
        self._tag_nodes()
        self.publish()
        if auto_task:
            self.attach()

    def _tag_nodes(self) -> None:
        if self.target is not None and not self.target.isEmpty():
            self.target.setPythonTag('bridge_trace_target', True)
            if self.state.label:
                self.target.setPythonTag('bridge_trace_label', self.state.label)
            if self.state.player_radius is not None:
                self.target.setPythonTag('bridge_player_radius', float(self.state.player_radius))
            if self.state.eye_height is not None:
                self.target.setPythonTag('bridge_eye_height', float(self.state.eye_height))
        if self.camera is not None and not self.camera.isEmpty():
            self.camera.setPythonTag('bridge_trace_camera', True)
        if self.actor is not None and not self.actor.isEmpty():
            self.actor.setPythonTag('bridge_trace_actor', True)

    def attach(self) -> None:
        if self._task_attached:
            return
        self.base.taskMgr.add(self._poll_task, self.task_name, sort=84)
        self._task_attached = True

    def add_note(self, note: str) -> None:
        if note and note not in self.state.notes:
            self.state.notes.append(note)
            self.publish()

    def set_grounded(self, grounded: bool) -> None:
        self.state.grounded = bool(grounded)
        self.publish()

    def set_collision_count(self, count: int) -> None:
        self.state.collision_count = int(max(0, count))
        self.publish()

    def set_current_anim(self, anim: str | None) -> None:
        self.state.current_anim = None if anim is None else str(anim)
        self.publish()

    def set_metrics(
        self,
        *,
        grounded: bool | None = None,
        collision_count: int | None = None,
        current_anim: str | None = None,
        player_radius: float | None = None,
        eye_height: float | None = None,
        speed_hint: float | None = None,
        vertical_speed_hint: float | None = None,
        controller_hints: dict[str, Any] | None = None,
    ) -> None:
        if grounded is not None:
            self.state.grounded = bool(grounded)
        if collision_count is not None:
            self.state.collision_count = int(max(0, collision_count))
        if current_anim is not None:
            self.state.current_anim = str(current_anim)
        if player_radius is not None:
            self.state.player_radius = float(player_radius)
        if eye_height is not None:
            self.state.eye_height = float(eye_height)
        if speed_hint is not None:
            self.state.speed_hint = float(speed_hint)
        if vertical_speed_hint is not None:
            self.state.vertical_speed_hint = float(vertical_speed_hint)
        if controller_hints:
            self.state.controller_hints = dict(controller_hints)
        self.publish()

    def publish(self) -> None:
        if self.target is None or self.target.isEmpty():
            return
        payload = self.state.as_dict()
        self.target.setPythonTag('bridge_trace_state', payload)
        if 'grounded' in payload:
            self.target.setPythonTag('bridge_grounded', bool(payload['grounded']))
        if 'collision_count' in payload:
            self.target.setPythonTag('bridge_collision_count', int(payload['collision_count']))
        if 'current_anim' in payload:
            self.target.setPythonTag('current_anim', payload['current_anim'])
        if 'label' in payload:
            self.target.setPythonTag('bridge_trace_label', payload['label'])
        if 'player_radius' in payload:
            self.target.setPythonTag('bridge_player_radius', float(payload['player_radius']))
        if 'eye_height' in payload:
            self.target.setPythonTag('bridge_eye_height', float(payload['eye_height']))

    def _poll_task(self, task):
        from panda3d.core import ClockObject

        now = ClockObject.getGlobalClock().getFrameTime()
        if self.target is None or self.target.isEmpty():
            return task.done
        pos = self.target.getPos(self.base.render)
        if self._last_pos is not None and self._last_t is not None:
            dt = max(1e-6, now - self._last_t)
            dx = pos.x - self._last_pos.x
            dy = pos.y - self._last_pos.y
            dz = pos.z - self._last_pos.z
            planar_speed = ((dx * dx) + (dy * dy)) ** 0.5 / dt
            vertical_speed = dz / dt
            self.state.speed_hint = round(planar_speed, 6)
            self.state.vertical_speed_hint = round(vertical_speed, 6)
        self._last_pos = pos
        self._last_t = now
        if self.grounded_getter is not None:
            try:
                self.state.grounded = bool(self.grounded_getter())
            except Exception as exc:
                self.add_note(f'grounded_getter_error={exc.__class__.__name__}')
        if self.collision_getter is not None:
            try:
                self.state.collision_count = int(max(0, self.collision_getter()))
            except Exception as exc:
                self.add_note(f'collision_getter_error={exc.__class__.__name__}')
        if self.anim_getter is not None:
            try:
                anim = self.anim_getter()
                self.state.current_anim = None if anim is None else str(anim)
            except Exception as exc:
                self.add_note(f'anim_getter_error={exc.__class__.__name__}')
        self.publish()
        return task.cont


def install_trace_helper(
    base,
    target,
    camera=None,
    actor=None,
    **kwargs,
) -> Panda3DTraceHelper:
    return Panda3DTraceHelper(base, target, camera=camera, actor=actor, **kwargs)
