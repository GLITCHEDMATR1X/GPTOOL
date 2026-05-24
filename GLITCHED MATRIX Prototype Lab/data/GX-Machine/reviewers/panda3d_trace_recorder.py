from __future__ import annotations

import argparse
import json
import math
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (18, 22, 28, 255)
CARD_OUTLINE = (76, 88, 104, 255)
TEXT = (235, 240, 248, 255)
MUTED = (176, 186, 198, 255)
ACCENT = (118, 214, 255, 255)
GOOD = (110, 230, 166, 255)
BAD = (255, 122, 110, 255)
GRID = (46, 56, 68, 255)
PATH_COLOR = (118, 214, 255, 255)
SPEED_COLOR = (110, 230, 166, 255)
CAMERA_COLOR = (255, 210, 110, 255)
COLLISION_COLOR = (255, 122, 110, 255)


@dataclass
class RecorderConfig:
    duration: float = 3.5
    output_path: str = 'logs/panda3d_trace_recorder.json'
    debug_image: str | None = None
    target_pattern: str | None = None
    camera_pattern: str | None = None
    actor_pattern: str | None = None
    sample_hz: float = 60.0
    label: str = 'live_trace'
    discovery_timeout: float = 2.0


class TraceRecorder:
    def __init__(self, base, config: RecorderConfig):
        self.base = base
        self.config = config
        self.frames: list[dict[str, Any]] = []
        self._target = None
        self._camera = None
        self._actor = None
        self._prev_world = None
        self._prev_t = None
        self._finished = None
        self._attached = False
        self._found_notes: list[str] = []
        self._warmup_remaining = 2

    def attach(self) -> None:
        if self._attached:
            return
        self.base.taskMgr.add(self._sample_task, 'bridge-trace-recorder-sample', sort=90)
        self._attached = True

    def _discover_target(self) -> None:
        render = self.base.render
        camera = self.base.camera
        all_nodes = list(render.findAllMatches('**'))

        def _find_named(fragments: tuple[str, ...]):
            for node in all_nodes:
                if node.isEmpty() or node == render:
                    continue
                name = node.getName().lower()
                if any(fragment in name for fragment in fragments):
                    return node
            return None

        def _find_tagged(tag_name: str):
            for node in all_nodes:
                if node.isEmpty() or node == render:
                    continue
                try:
                    if node.hasPythonTag(tag_name) or node.hasTag(tag_name):
                        return node
                except Exception:
                    continue
            return None

        def _state_value(key: str):
            holder = self._target
            if holder is None or holder.isEmpty() or not holder.hasPythonTag('bridge_trace_state'):
                return None
            try:
                state = holder.getPythonTag('bridge_trace_state')
            except Exception:
                return None
            if isinstance(state, dict):
                return state.get(key)
            return None

        if self._target is None:
            if self.config.target_pattern:
                candidate = render.find(self.config.target_pattern)
                if not candidate.isEmpty():
                    self._target = candidate
            if self._target is None:
                self._target = _find_tagged('bridge_trace_target') or _find_tagged('current_anim') or _find_tagged('bridge_grounded')
            if self._target is None:
                self._target = _find_named(('player', 'hero', 'avatar', 'character', 'pawn', 'cameratarget', 'camera_target'))
            if self._target is None and not camera.isEmpty() and camera.getParent() != render:
                self._target = camera.getParent()
                self._found_notes.append(f'target_from_camera_parent={self._target.getName()}')
            if self._target is None:
                self._target = render
                self._found_notes.append('target_default=render')
            else:
                self._found_notes.append(f'target={self._target.getName()}')

        if self._camera is None:
            if self.config.camera_pattern:
                cam = render.find(self.config.camera_pattern)
                if not cam.isEmpty():
                    self._camera = cam
            if self._camera is None:
                self._camera = _find_tagged('bridge_trace_camera') or camera
            self._found_notes.append(f'camera={self._camera.getName()}')

        if self._actor is None:
            if self.config.actor_pattern:
                node = render.find(self.config.actor_pattern)
                if not node.isEmpty():
                    self._actor = node
            if self._actor is None:
                self._actor = _find_tagged('bridge_trace_actor') or _find_tagged('current_anim') or _find_named(('actor', 'rig', 'character'))
            if self._actor is not None and not self._actor.isEmpty():
                self._found_notes.append(f'actor={self._actor.getName()}')

    def _collision_count(self) -> int:
        target = self._target
        if target is not None and not target.isEmpty() and target.hasPythonTag('bridge_trace_state'):
            try:
                state = target.getPythonTag('bridge_trace_state')
                if isinstance(state, dict) and 'collision_count' in state:
                    return int(state.get('collision_count') or 0)
            except Exception:
                pass
        if target is not None and not target.isEmpty() and target.hasPythonTag('bridge_collision_count'):
            try:
                return int(target.getPythonTag('bridge_collision_count'))
            except Exception:
                pass
        for attr in ('cHandler', 'collision_handler', 'pusher', 'floor_handler', 'collisionHandler'):
            handler = getattr(self.base, attr, None)
            if handler is None:
                continue
            if hasattr(handler, 'getNumEntries'):
                try:
                    return int(handler.getNumEntries())
                except Exception:
                    continue
            if hasattr(handler, 'getEntries'):
                try:
                    return len(handler.getEntries())
                except Exception:
                    continue
        return 0

    def _active_anim(self) -> str | None:
        for holder in (self._target, self._actor):
            if holder is None or holder.isEmpty():
                continue
            if holder.hasPythonTag('bridge_trace_state'):
                try:
                    state = holder.getPythonTag('bridge_trace_state')
                    if isinstance(state, dict) and state.get('current_anim'):
                        return str(state.get('current_anim'))
                except Exception:
                    pass
            if holder.hasPythonTag('current_anim'):
                value = holder.getPythonTag('current_anim')
                if value:
                    return str(value)
            if holder.hasTag('current_anim'):
                value = holder.getTag('current_anim')
                if value:
                    return value
            if hasattr(holder, 'getCurrentAnim'):
                try:
                    value = holder.getCurrentAnim()
                    if value:
                        return str(value)
                except Exception:
                    pass
            node = holder.node()
            if hasattr(node, 'getCurrentAnim'):
                try:
                    value = node.getCurrentAnim()
                    if value:
                        return str(value)
                except Exception:
                    pass
        return None

    def _grounded(self, vertical_speed: float, collision_count: int) -> bool:
        target = self._target
        if target is not None and not target.isEmpty() and target.hasPythonTag('bridge_trace_state'):
            try:
                state = target.getPythonTag('bridge_trace_state')
                if isinstance(state, dict) and 'grounded' in state:
                    return bool(state.get('grounded'))
            except Exception:
                pass
        if target is not None and not target.isEmpty() and target.hasPythonTag('bridge_grounded'):
            try:
                return bool(target.getPythonTag('bridge_grounded'))
            except Exception:
                pass
        if collision_count > 0 and abs(vertical_speed) < 1.2:
            return True
        return abs(vertical_speed) < 0.12

    def _sample_task(self, task):
        from panda3d.core import ClockObject

        now = ClockObject.getGlobalClock().getFrameTime()
        if not self.frames or now <= self.config.discovery_timeout:
            self._discover_target()
        target = self._target or self.base.render
        camera = self._camera or self.base.camera

        world = target.getPos(self.base.render)
        hpr = target.getHpr(self.base.render)
        cam_world = camera.getPos(self.base.render)
        cam_hpr = camera.getHpr(self.base.render)
        if self._prev_t is not None and (now - self._prev_t) < (1.0 / max(1.0, self.config.sample_hz)):
            return task.cont
        if self._prev_world is None or self._prev_t is None:
            speed = 0.0
            vertical_speed = 0.0
        else:
            dt = max(1e-6, now - self._prev_t)
            dx = world.x - self._prev_world.x
            dy = world.y - self._prev_world.y
            dz = world.z - self._prev_world.z
            speed = math.sqrt(dx * dx + dy * dy) / dt
            vertical_speed = dz / dt
        recent_speeds = [float(f['speed']) for f in self.frames[-6:] if float(f['speed']) > 0.1]
        if recent_speeds:
            median_recent = sorted(recent_speeds)[len(recent_speeds) // 2]
            if median_recent > 0.25 and speed > median_recent * 1.8:
                speed = median_recent * 1.8
        collision_count = self._collision_count()
        grounded = self._grounded(vertical_speed, collision_count)
        camera_distance = math.sqrt((cam_world.x - world.x) ** 2 + (cam_world.y - world.y) ** 2 + (cam_world.z - world.z) ** 2)
        active_anim = self._active_anim()

        if self._warmup_remaining > 0:
            self._warmup_remaining -= 1
            self._prev_world = world
            self._prev_t = now
            return task.cont

        trace_state = None
        if target is not None and not target.isEmpty() and target.hasPythonTag('bridge_trace_state'):
            try:
                state = target.getPythonTag('bridge_trace_state')
                if isinstance(state, dict):
                    trace_state = state
            except Exception:
                trace_state = None

        speed_hint = None if not trace_state else trace_state.get('speed_hint')
        vertical_hint = None if not trace_state else trace_state.get('vertical_speed_hint')
        if speed_hint is not None:
            try:
                speed = float(speed_hint)
            except Exception:
                pass
        if vertical_hint is not None:
            try:
                vertical_speed = float(vertical_hint)
            except Exception:
                pass

        self.frames.append({
            't': round(now, 6),
            'x': round(world.x, 6),
            'y': round(world.z, 6),
            'z': round(world.y, 6),
            'speed': round(speed, 6),
            'yaw': round(hpr.x, 6),
            'pitch': round(hpr.y, 6),
            'roll': round(hpr.z, 6),
            'grounded': bool(grounded),
            'vertical_speed': round(vertical_speed, 6),
            'camera_x': round(cam_world.x, 6),
            'camera_y': round(cam_world.z, 6),
            'camera_z': round(cam_world.y, 6),
            'camera_yaw': round(cam_hpr.x, 6),
            'camera_pitch': round(cam_hpr.y, 6),
            'camera_roll': round(cam_hpr.z, 6),
            'camera_distance': round(camera_distance, 6),
            'collision_count': int(collision_count),
            'active_anim': active_anim,
            'helper_state': trace_state or {},
        })
        self._prev_world = world
        self._prev_t = now
        return task.cont

    def _infer_profile(self) -> dict[str, Any]:
        if len(self.frames) < 3:
            return {
                'walk_speed': 4.0,
                'sprint_speed': 6.2,
                'acceleration': 8.0,
                'deceleration': 9.0,
                'gravity': 20.0,
                'jump_speed': 7.0,
                'mouse_sensitivity': 0.12,
                'player_radius': 0.28,
                'eye_height': 1.68,
                'feel_class': 'derived_live_trace',
            }
        speeds = [max(0.0, float(f['speed'])) for f in self.frames]
        moving = [s for s in speeds if s > 0.1]
        peak_speed = _percentile(moving, 0.95) if moving else 0.0
        walk_speed = min(peak_speed, max(1.0, _percentile(moving, 0.45) if moving else peak_speed * 0.7))
        accel_samples = []
        decel_samples = []
        prev = self.frames[0]
        for cur in self.frames[1:]:
            dt = max(1e-6, float(cur['t']) - float(prev['t']))
            accel = (float(cur['speed']) - float(prev['speed'])) / dt
            if accel >= 0:
                accel_samples.append(accel)
            else:
                decel_samples.append(-accel)
            prev = cur
        vertical = [float(f.get('vertical_speed', 0.0)) for f in self.frames]
        positive_v = [v for v in vertical if v > 0.4]
        gravity_samples = []
        prev = self.frames[0]
        for cur in self.frames[1:]:
            dt = max(1e-6, float(cur['t']) - float(prev['t']))
            gravity_samples.append((float(prev.get('vertical_speed', 0.0)) - float(cur.get('vertical_speed', 0.0))) / dt)
            prev = cur
        cam_offsets = [abs(float(f.get('camera_y', 0.0)) - float(f['y'])) for f in self.frames]
        helper_states = [f.get('helper_state', {}) for f in self.frames if isinstance(f.get('helper_state'), dict)]
        radius_hints = [float(s.get('player_radius')) for s in helper_states if s.get('player_radius') is not None]
        eye_hints = [float(s.get('eye_height')) for s in helper_states if s.get('eye_height') is not None]
        controller_hints = {}
        for state in helper_states:
            hints = state.get('controller_hints') if isinstance(state, dict) else None
            if isinstance(hints, dict):
                controller_hints.update({k: v for k, v in hints.items() if v is not None})
        sensitivity = max(0.08, min(0.35, (max(float(f['camera_yaw']) for f in self.frames) - min(float(f['camera_yaw']) for f in self.frames) + 5.0) / 1400.0))
        sprint_speed = max(walk_speed, peak_speed)
        acceleration = max(2.0, _percentile(accel_samples, 0.6) if accel_samples else peak_speed * 2.0)
        acceleration = min(acceleration, max(8.0, sprint_speed * 4.0))
        deceleration = max(2.0, _percentile(decel_samples, 0.6) if decel_samples else peak_speed * 2.3)
        deceleration = min(deceleration, max(10.0, sprint_speed * 5.5))
        gravity = max(8.0, _percentile(gravity_samples, 0.5) if gravity_samples else 20.0)
        gravity = min(gravity, 32.0)
        jump_speed = max(4.8, _percentile(positive_v, 0.8) if positive_v else 6.8)
        jump_speed = min(jump_speed, 12.0)
        report = {
            'walk_speed': round(walk_speed or max(1.0, peak_speed * 0.7), 4),
            'sprint_speed': round(sprint_speed, 4),
            'acceleration': round(acceleration, 4),
            'deceleration': round(deceleration, 4),
            'gravity': round(gravity, 4),
            'jump_speed': round(jump_speed, 4),
            'mouse_sensitivity': round(sensitivity, 4),
            'player_radius': round(_percentile(radius_hints, 0.5), 4) if radius_hints else 0.32,
            'eye_height': round(_percentile(eye_hints, 0.5), 4) if eye_hints else round(max(1.45, _percentile(cam_offsets, 0.5) if cam_offsets else 1.68), 4),
            'feel_class': 'derived_live_trace',
        }
        for key in ('walk_speed', 'sprint_speed', 'acceleration', 'deceleration', 'gravity', 'jump_speed', 'mouse_sensitivity', 'player_radius', 'eye_height', 'feel_class'):
            if key in controller_hints:
                try:
                    report[key] = float(controller_hints[key]) if key != 'feel_class' else str(controller_hints[key])
                except Exception:
                    if key == 'feel_class':
                        report[key] = str(controller_hints[key])
        return report

    def finish(self) -> dict[str, Any]:
        if self._finished is not None:
            return self._finished
        summary = _summarize_frames(self.frames)
        helper_used = any(isinstance(f.get('helper_state'), dict) and f.get('helper_state') for f in self.frames)
        helper_labels = []
        for f in self.frames:
            state = f.get('helper_state') or {}
            label = state.get('label') if isinstance(state, dict) else None
            if label and label not in helper_labels:
                helper_labels.append(str(label))
        report = {
            'reviewer': 'panda3d_trace_recorder',
            'label': self.config.label,
            'duration_requested': self.config.duration,
            'frame_count': len(self.frames),
            'discovery_notes': self._found_notes,
            'target_name': None if self._target is None or self._target.isEmpty() else self._target.getName(),
            'camera_name': None if self._camera is None or self._camera.isEmpty() else self._camera.getName(),
            'controller_profile': self._infer_profile(),
            'summary': summary,
            'helper_used': helper_used,
            'helper_labels': helper_labels,
            'frames': self.frames,
            'unknowns': [
                'Auto-discovery is heuristic. Supply explicit target/camera patterns if a project uses unusual node names.',
                'Collision counts are best-effort unless a project exposes a handler or bridge_collision_count python tag.',
                'Animation names are best-effort unless a project exposes an Actor current animation or current_anim tag.',
            ],
        }
        output_path = Path(self.config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        if self.config.debug_image:
            build_debug_panel(report, Path(self.config.debug_image))
        self._finished = report
        return report


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * q))))
    return float(ordered[idx])


def _summarize_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    if not frames:
        return {'duration': 0.0, 'peak_speed': 0.0, 'avg_speed': 0.0, 'peak_camera_distance': 0.0, 'max_collision_count': 0, 'active_anims': [], 'peak_jump_height': 0.0}
    t0 = float(frames[0]['t'])
    t1 = float(frames[-1]['t'])
    speeds = [float(f['speed']) for f in frames]
    cam = [float(f.get('camera_distance', 0.0)) for f in frames]
    collisions = [int(f.get('collision_count', 0)) for f in frames]
    heights = [float(f['y']) for f in frames]
    anims = []
    for f in frames:
        anim = f.get('active_anim')
        if anim and anim not in anims:
            anims.append(anim)
    moving = [s for s in speeds if s > 0.1]
    return {
        'duration': round(max(0.0, t1 - t0), 4),
        'peak_speed': round(_percentile(moving, 0.95) if moving else 0.0, 4),
        'avg_speed': round(sum(moving) / len(moving), 4) if moving else 0.0,
        'peak_camera_distance': round(max(cam), 4),
        'max_collision_count': max(collisions),
        'active_anims': anims,
        'peak_jump_height': round(max(heights) - min(heights), 4),
    }


def _fit_points(values: list[tuple[float, float]], box: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = box
    if not values:
        return []
    min_x = min(v[0] for v in values)
    max_x = max(v[0] for v in values)
    min_y = min(v[1] for v in values)
    max_y = max(v[1] for v in values)
    if math.isclose(max_x, min_x):
        max_x = min_x + 1.0
    if math.isclose(max_y, min_y):
        max_y = min_y + 1.0
    pts = []
    for vx, vy in values:
        px = x0 + (vx - min_x) / (max_x - min_x) * (x1 - x0)
        py = y1 - (vy - min_y) / (max_y - min_y) * (y1 - y0)
        pts.append((px, py))
    return pts


def _draw_grid(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], vlines: int = 6, hlines: int = 4) -> None:
    x0, y0, x1, y1 = box
    for i in range(vlines + 1):
        x = x0 + (x1 - x0) * i / vlines
        draw.line((x, y0, x, y1), fill=GRID, width=1)
    for i in range(hlines + 1):
        y = y0 + (y1 - y0) * i / hlines
        draw.line((x0, y, x1, y), fill=GRID, width=1)


def _draw_line_plot(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], values: list[tuple[float, float]], color: tuple[int, int, int, int], title: str, subtitle: str | None = None) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((x0 + 16, y0 + 14), title, fill=TEXT)
    if subtitle:
        draw.text((x0 + 16, y0 + 34), subtitle, fill=MUTED)
    inner = (x0 + 18, y0 + 62, x1 - 18, y1 - 18)
    _draw_grid(draw, inner)
    pts = _fit_points(values, inner)
    if len(pts) >= 2:
        draw.line(pts, fill=color, width=3)


def build_debug_panel(report: dict[str, Any], output_path: Path) -> None:
    frames = report.get('frames', [])
    summary = report.get('summary', {})
    width, height = 1600, 1000
    canvas = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(canvas)
    helper = 'helper:on' if report.get('helper_used') else 'helper:off'
    draw.text((26, 18), 'Panda3D Trace Recorder v0.12', fill=TEXT)
    draw.text((26, 42), f"label: {report.get('label', 'live_trace')}  |  target: {report.get('target_name', 'unknown')}  |  frames: {report.get('frame_count', 0)}  |  {helper}", fill=MUTED)

    path_box = (24, 80, 784, 520)
    speed_box = (816, 80, 1576, 520)
    camera_box = (24, 548, 784, 876)
    collision_box = (816, 548, 1576, 876)
    footer_box = (24, 892, 1576, 976)

    _draw_line_plot(draw, speed_box, [(float(f['t']), float(f['speed'])) for f in frames], SPEED_COLOR, 'Live speed trace', f"peak: {summary.get('peak_speed', 0.0)}  avg: {summary.get('avg_speed', 0.0)}")
    _draw_line_plot(draw, camera_box, [(float(f['t']), float(f.get('camera_distance', 0.0))) for f in frames], CAMERA_COLOR, 'Camera distance', f"peak: {summary.get('peak_camera_distance', 0.0)}")
    _draw_line_plot(draw, collision_box, [(float(f['t']), float(f.get('collision_count', 0))) for f in frames], COLLISION_COLOR, 'Collision / contact count', f"max collisions: {summary.get('max_collision_count', 0)}")

    draw.rounded_rectangle(path_box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((path_box[0] + 16, path_box[1] + 14), 'Live movement path trace', fill=TEXT)
    draw.text((path_box[0] + 16, path_box[1] + 34), 'Path uses Panda X/Z plane normalization (Z-up mapped to height).', fill=MUTED)
    inner = (path_box[0] + 18, path_box[1] + 62, path_box[2] - 18, path_box[3] - 18)
    _draw_grid(draw, inner)
    pts = _fit_points([(float(f['x']), float(f['z'])) for f in frames], inner)
    if len(pts) >= 2:
        draw.line(pts, fill=PATH_COLOR, width=4)
    if pts:
        draw.ellipse((pts[0][0] - 6, pts[0][1] - 6, pts[0][0] + 6, pts[0][1] + 6), fill=GOOD)
        draw.ellipse((pts[-1][0] - 6, pts[-1][1] - 6, pts[-1][0] + 6, pts[-1][1] + 6), fill=BAD)

    draw.rounded_rectangle(footer_box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((footer_box[0] + 16, footer_box[1] + 14), 'Discovery / inferred controller / active animations', fill=TEXT)
    notes = ', '.join(report.get('discovery_notes', [])[:4]) or 'heuristic discovery used'
    draw.text((footer_box[0] + 16, footer_box[1] + 38), notes[:150], fill=MUTED)
    profile = report.get('controller_profile', {})
    profile_text = f"walk={profile.get('walk_speed', '?')} sprint={profile.get('sprint_speed', '?')} accel={profile.get('acceleration', '?')} jump={profile.get('jump_speed', '?')} grav={profile.get('gravity', '?')}"
    draw.text((footer_box[0] + 16, footer_box[1] + 58), profile_text[:170], fill=MUTED)
    anims = summary.get('active_anims', [])
    anim_text = 'active anims: ' + (', '.join(anims[:6]) if anims else 'none detected')
    draw.text((footer_box[0] + 16, footer_box[1] + 78), anim_text[:170], fill=MUTED)
    helper_text = 'helper labels: ' + (', '.join(report.get('helper_labels', [])[:4]) if report.get('helper_labels') else 'none')
    draw.text((footer_box[0] + 16, footer_box[1] + 98), helper_text[:170], fill=MUTED)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(output_path)


def _install_headless_prc() -> None:
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type offscreen')
    loadPrcFileData('', 'audio-library-name null')
    loadPrcFileData('', 'notify-level-glgsg fatal')
    loadPrcFileData('', 'sync-video false')


def _run_target(module_name: str | None, script_path: str | None) -> None:
    if module_name:
        runpy.run_module(module_name, run_name='__main__')
        return
    if script_path:
        runpy.run_path(script_path, run_name='__main__')
        return
    raise RuntimeError('No target module or script provided for trace capture.')


def capture_live_trace(module_name: str | None, script_path: str | None, config: RecorderConfig) -> dict[str, Any]:
    from direct.showbase import ShowBase as ShowBaseModule

    holder: dict[str, Any] = {'recorder': None}
    original_run = ShowBaseModule.ShowBase.run
    original_init = ShowBaseModule.ShowBase.__init__

    def patched_init(self, *args, **kwargs):
        result = original_init(self, *args, **kwargs)
        recorder = TraceRecorder(self, config)
        recorder.attach()
        holder['recorder'] = recorder
        return result

    def patched_run(self):
        recorder = holder.get('recorder')
        def _stop(task):
            if recorder is not None:
                recorder.finish()
            self.taskMgr.stop()
            return task.done
        self.taskMgr.doMethodLater(float(config.duration), _stop, 'bridge-trace-recorder-stop')
        try:
            return original_run(self)
        finally:
            if recorder is not None:
                recorder.finish()
            try:
                self.destroy()
            except Exception:
                pass

    ShowBaseModule.ShowBase.__init__ = patched_init
    ShowBaseModule.ShowBase.run = patched_run
    try:
        _run_target(module_name, script_path)
    finally:
        ShowBaseModule.ShowBase.__init__ = original_init
        ShowBaseModule.ShowBase.run = original_run
    recorder = holder.get('recorder')
    if recorder is None:
        raise RuntimeError('No Panda3D ShowBase instance was created by the target during trace capture.')
    return recorder.finish()


def main() -> int:
    ap = argparse.ArgumentParser(description='Inject a live Panda3D trace recorder into a target module or script and capture normalized controller/camera/collision/animation data, including optional helper-tag exports.')
    ap.add_argument('--module', help='Python module to run as __main__.')
    ap.add_argument('--script', help='Python script path to run as __main__.')
    ap.add_argument('--duration', type=float, default=3.5, help='Capture duration in seconds before stopping the Panda3D task loop.')
    ap.add_argument('--output', required=True, help='Path to write the recorded trace JSON.')
    ap.add_argument('--debug-image', help='Optional PNG summary panel.')
    ap.add_argument('--target-pattern', help='Optional Panda3D scene graph pattern to target instead of auto-discovery.')
    ap.add_argument('--camera-pattern', help='Optional scene graph pattern for the camera node.')
    ap.add_argument('--actor-pattern', help='Optional scene graph pattern for the animated actor node.')
    ap.add_argument('--headless', action='store_true', help='Force an offscreen Panda3D window for validation environments.')
    ap.add_argument('--json', action='store_true', help='Print the resulting JSON report to stdout.')
    args = ap.parse_args()

    if not args.module and not args.script:
        raise SystemExit('Provide either --module or --script for live trace capture.')
    if args.headless:
        _install_headless_prc()

    config = RecorderConfig(
        duration=float(args.duration),
        output_path=args.output,
        debug_image=args.debug_image,
        target_pattern=args.target_pattern,
        camera_pattern=args.camera_pattern,
        actor_pattern=args.actor_pattern,
        label=Path(args.script).stem if args.script else str(args.module),
    )
    report = capture_live_trace(args.module, args.script, config)
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
