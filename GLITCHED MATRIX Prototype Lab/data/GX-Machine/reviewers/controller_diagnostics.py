from __future__ import annotations

import argparse
import json
import math
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
WARN = (255, 210, 110, 255)
BAD = (255, 122, 110, 255)
GRID = (46, 56, 68, 255)
PATH_COLOR = (118, 214, 255, 255)
SPEED_COLOR = (110, 230, 166, 255)
JUMP_COLOR = (214, 160, 255, 255)
TURN_COLOR = (255, 210, 110, 255)


DEFAULT_DOOR_WIDTHS = [0.9, 1.2, 1.8]
DEFAULT_BUFFER = 0.08


def _load_json(path: str | None) -> Any:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding='utf-8'))


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if v is not None}


def _coerce_trace(raw: Any) -> list[dict[str, float]]:
    frames = raw.get('frames', raw) if isinstance(raw, dict) else raw
    if not isinstance(frames, list):
        raise ValueError('Trace JSON must be a list of frames or an object with a frames list.')
    cooked: list[dict[str, float]] = []
    for idx, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        t = float(frame.get('t', idx / 60.0))
        cooked.append({
            't': t,
            'x': float(frame.get('x', 0.0)),
            'y': float(frame.get('y', frame.get('height', 0.0))),
            'z': float(frame.get('z', 0.0)),
            'speed': float(frame.get('speed', 0.0)),
            'yaw': float(frame.get('yaw', 0.0)),
            'pitch': float(frame.get('pitch', 0.0)),
            'grounded': 1.0 if bool(frame.get('grounded', True)) else 0.0,
        })
    return cooked


def _extract_profile_from_libraries(examples_library: dict[str, Any] | None, editor_library: dict[str, Any] | None, modeling_library: dict[str, Any] | None, donor_slug: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    search_spaces = []
    if examples_library:
        search_spaces.append(examples_library.get('donors', []))
    if editor_library:
        search_spaces.append(editor_library.get('donors', []))
    if modeling_library:
        search_spaces.append(modeling_library.get('donors', []))
    if not donor_slug:
        return None, []
    for donors in search_spaces:
        for donor in donors:
            if donor.get('slug') == donor_slug:
                profile = donor.get('controller_profile') or donor.get('character_runtime_profile') or donor.get('surface_behavior_profile') or donor.get('object_structure_profile') or donor.get('image_structure_profile') or donor.get('editor_profile') or donor.get('loaded_model_profile')
                notes = [donor.get('label', donor_slug), donor.get('notes', '')]
                return profile, [n for n in notes if n]
    return None, []


def _derive_controller_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    base = profile or {}
    walk_speed = float(base.get('walk_speed', base.get('move_speed', 6.0)))
    sprint_speed = base.get('sprint_speed')
    if sprint_speed is None:
        if base.get('max_sprint_speed') is not None:
            sprint_speed = float(base['max_sprint_speed'])
        elif base.get('fast_speed') is not None:
            sprint_speed = float(base['fast_speed'])
        elif base.get('sprint_entry_speed') is not None:
            sprint_speed = float(base['sprint_entry_speed'])
        elif base.get('sprint_multiplier') is not None:
            sprint_speed = walk_speed * float(base['sprint_multiplier'])
        else:
            sprint_speed = walk_speed * 1.55
    acceleration = base.get('acceleration')
    if acceleration is None:
        feel = base.get('feel_class', 'stable_grounded')
        acceleration = {
            'fast_grounded': walk_speed * 2.0,
            'responsive': walk_speed * 2.2,
            'inertial': max(12.0, walk_speed * 0.9),
        }.get(feel, walk_speed * 1.6)
    deceleration = base.get('deceleration')
    if deceleration is None:
        deceleration = float(acceleration) * (0.75 if base.get('feel_class') == 'inertial' else 1.15)
    gravity = float(base.get('gravity', 20.0))
    jump_speed = float(base.get('jump_speed', max(6.4, math.sqrt(gravity * 2.1))))
    mouse_sensitivity = float(base.get('mouse_sensitivity', 0.12))
    yaw_rate = float(base.get('yaw_rate_deg_per_sec', max(90.0, mouse_sensitivity * 900.0)))
    yaw_accel = float(base.get('yaw_accel_deg_per_sec2', max(220.0, yaw_rate * 3.2)))
    player_radius = float(base.get('player_radius', 0.28))
    eye_height = float(base.get('eye_height', base.get('player_height', 1.68)))
    drag = float(base.get('drag', 0.94 if base.get('feel_class') == 'inertial' else 1.0))
    return _compact({
        'walk_speed': round(walk_speed, 4),
        'sprint_speed': round(float(sprint_speed), 4),
        'acceleration': round(float(acceleration), 4),
        'deceleration': round(float(deceleration), 4),
        'gravity': round(gravity, 4),
        'jump_speed': round(jump_speed, 4),
        'mouse_sensitivity': round(mouse_sensitivity, 4),
        'yaw_rate_deg_per_sec': round(yaw_rate, 4),
        'yaw_accel_deg_per_sec2': round(yaw_accel, 4),
        'player_radius': round(player_radius, 4),
        'eye_height': round(eye_height, 4),
        'drag': round(drag, 4),
        'feel_class': base.get('feel_class', 'derived'),
    })


def _simulate_trace(profile: dict[str, Any], dt: float = 1.0 / 60.0) -> dict[str, Any]:
    total_time = 5.8
    steps = int(total_time / dt) + 1
    speed = 0.0
    yaw = 0.0
    yaw_vel = 0.0
    x = 0.0
    z = 0.0
    frames: list[dict[str, float]] = []
    for idx in range(steps):
        t = idx * dt
        if t < 1.4:
            target_speed = profile['walk_speed']
            desired_yaw_vel = 0.0
        elif t < 2.9:
            target_speed = profile['sprint_speed']
            desired_yaw_vel = profile['yaw_rate_deg_per_sec'] * 0.8
        elif t < 4.4:
            target_speed = profile['sprint_speed']
            desired_yaw_vel = 0.0
        else:
            target_speed = 0.0
            desired_yaw_vel = 0.0

        accel = profile['acceleration'] if target_speed >= speed else profile['deceleration']
        if speed < target_speed:
            speed = min(target_speed, speed + accel * dt)
        else:
            speed = max(target_speed, speed - accel * dt)
        if profile['feel_class'] == 'inertial' and target_speed == 0.0:
            speed *= profile['drag']

        if yaw_vel < desired_yaw_vel:
            yaw_vel = min(desired_yaw_vel, yaw_vel + profile['yaw_accel_deg_per_sec2'] * dt)
        else:
            yaw_vel = max(desired_yaw_vel, yaw_vel - profile['yaw_accel_deg_per_sec2'] * dt)
        yaw += yaw_vel * dt
        heading = math.radians(yaw)
        x += math.sin(heading) * speed * dt
        z += math.cos(heading) * speed * dt
        frames.append({
            't': round(t, 6),
            'x': x,
            'y': 0.0,
            'z': z,
            'speed': speed,
            'yaw': yaw,
            'pitch': 0.0,
            'grounded': 1.0,
        })

    vertical_frames: list[dict[str, float]] = []
    vy = profile['jump_speed']
    y = 0.0
    t = 0.0
    while True:
        vertical_frames.append({'t': round(t, 6), 'y': y, 'vy': vy})
        t += dt
        vy -= profile['gravity'] * dt
        y += vy * dt
        if y <= 0.0 and t > dt:
            vertical_frames.append({'t': round(t, 6), 'y': 0.0, 'vy': vy})
            break
    return {'frames': frames, 'jump_frames': vertical_frames, 'mode': 'synthetic'}


def _analyze_frames(frames: list[dict[str, float]], jump_frames: list[dict[str, float]], profile: dict[str, Any]) -> dict[str, Any]:
    if len(frames) < 2:
        raise ValueError('Not enough frames to analyze controller diagnostics.')
    peak_speed = max(f['speed'] for f in frames)
    t_90_walk = next((f['t'] for f in frames if f['speed'] >= profile['walk_speed'] * 0.9), None)
    t_90_sprint = next((f['t'] for f in frames if f['speed'] >= profile['sprint_speed'] * 0.9), None)
    brake_start_idx = next((i for i, f in enumerate(frames) if f['t'] >= 4.4), len(frames) - 1)
    stop_time = None
    stop_distance = None
    base = frames[brake_start_idx]
    for f in frames[brake_start_idx:]:
        if f['speed'] <= max(0.2, profile['walk_speed'] * 0.05):
            stop_time = f['t'] - base['t']
            stop_distance = math.dist((base['x'], base['z']), (f['x'], f['z']))
            break
    if stop_time is None:
        stop_time = frames[-1]['t'] - base['t']
        stop_distance = math.dist((base['x'], base['z']), (frames[-1]['x'], frames[-1]['z']))

    turn_start = next((f for f in frames if f['t'] >= 1.4), frames[0])
    turn_target = turn_start['yaw'] + 90.0
    turn_90_time = None
    for f in frames:
        if f['t'] >= turn_start['t'] and f['yaw'] >= turn_target:
            turn_90_time = f['t'] - turn_start['t']
            break
    if turn_90_time is None:
        turn_90_time = frames[-1]['t'] - turn_start['t']

    jump_apex = max(j['y'] for j in jump_frames) if jump_frames else 0.0
    airtime = jump_frames[-1]['t'] if jump_frames else 0.0

    required_width = profile['player_radius'] * 2.0 + DEFAULT_BUFFER
    doorway_tests = []
    for width in DEFAULT_DOOR_WIDTHS:
        ratio = width / required_width if required_width else 99.0
        doorway_tests.append({
            'door_width': width,
            'required_width': round(required_width, 4),
            'ratio': round(ratio, 4),
            'status': 'pass' if ratio >= 1.2 else 'warn' if ratio >= 1.0 else 'fail',
        })

    movement_score = max(0.0, min(100.0, 100.0 - abs(peak_speed - profile['sprint_speed']) * 2.2 - max(0.0, stop_time - 1.0) * 14.0))
    turn_score = max(0.0, min(100.0, 100.0 - abs(turn_90_time - 0.8) * 32.0))
    jump_score = max(0.0, min(100.0, 100.0 - abs(jump_apex - 1.1) * 35.0 - abs(airtime - 0.9) * 18.0))
    clearance_score = 100.0 if all(test['status'] == 'pass' for test in doorway_tests) else 72.0 if any(test['status'] == 'warn' for test in doorway_tests) else 45.0
    overall = round((movement_score + turn_score + jump_score + clearance_score) / 4.0, 2)

    return {
        'summary': {
            'peak_speed': round(peak_speed, 4),
            'time_to_90_walk': round(t_90_walk or 0.0, 4),
            'time_to_90_sprint': round(t_90_sprint or 0.0, 4),
            'stop_time': round(stop_time, 4),
            'stop_distance': round(stop_distance, 4),
            'turn_90_time': round(turn_90_time, 4),
            'jump_apex': round(jump_apex, 4),
            'jump_airtime': round(airtime, 4),
            'clearance_required_width': round(required_width, 4),
            'overall_score': overall,
        },
        'scores': {
            'movement': round(movement_score, 2),
            'turning': round(turn_score, 2),
            'jump': round(jump_score, 2),
            'clearance': round(clearance_score, 2),
        },
        'doorway_tests': doorway_tests,
    }


def _nearest_donors(profile: dict[str, Any], examples_library: dict[str, Any] | None, limit: int = 3) -> list[dict[str, Any]]:
    donors = [] if not examples_library else examples_library.get('donors', [])
    rows = []
    for donor in donors:
        ctrl = donor.get('controller_profile')
        if not ctrl:
            continue
        distance = 0.0
        weights = {
            'walk_speed': 1.2,
            'sprint_speed': 1.0,
            'mouse_sensitivity': 0.8,
            'jump_speed': 0.9,
            'gravity': 0.6,
            'player_radius': 0.5,
        }
        donor_profile = _derive_controller_profile(ctrl)
        for key, weight in weights.items():
            if key in profile and key in donor_profile:
                distance += abs(float(profile[key]) - float(donor_profile[key])) * weight
        rows.append({
            'slug': donor.get('slug'),
            'label': donor.get('label'),
            'distance': round(distance, 4),
            'feel_class': donor_profile.get('feel_class'),
        })
    rows.sort(key=lambda item: item['distance'])
    return rows[:limit]


def analyze_controller(profile: dict[str, Any], examples_library: dict[str, Any] | None = None, trace: list[dict[str, float]] | None = None) -> dict[str, Any]:
    derived = _derive_controller_profile(profile)
    if trace:
        frames = trace
        jump_frames = []
        heights = [f['y'] for f in frames]
        if max(heights) - min(heights) > 0.05:
            jump_frames = [{'t': f['t'], 'y': max(0.0, f['y'] - min(heights)), 'vy': 0.0} for f in frames]
        else:
            jump_frames = _simulate_trace(derived)['jump_frames']
        mode = 'trace'
    else:
        sim = _simulate_trace(derived)
        frames = sim['frames']
        jump_frames = sim['jump_frames']
        mode = sim['mode']
    analysis = _analyze_frames(frames, jump_frames, derived)
    return {
        'reviewer': 'controller_diagnostics',
        'mode': mode,
        'controller_profile': derived,
        'trace': {
            'frame_count': len(frames),
            'duration': round(frames[-1]['t'] - frames[0]['t'], 4),
        },
        'analysis': analysis,
        'nearest_donors': _nearest_donors(derived, examples_library),
        'frames': frames,
        'jump_frames': jump_frames,
        'unknowns': [
            'Without a live instrumented game trace, this pass simulates controller behavior from extracted parameters.',
            'Collision heatmaps, stair-step probes, and camera lag traces still improve when a project exports actual per-frame controller logs or when reviewers/panda3d_trace_recorder.py is used to capture a live Panda3D session.',
        ],
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
    frames = report['frames']
    jump_frames = report['jump_frames']
    analysis = report['analysis']
    width, height = 1600, 1000
    canvas = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((26, 18), 'Controller Diagnostics v0.12', fill=TEXT)
    draw.text((26, 42), f"mode: {report['mode']}  |  feel: {report['controller_profile'].get('feel_class', 'derived')}  |  overall: {analysis['summary']['overall_score']}", fill=MUTED)

    path_box = (24, 80, 784, 520)
    speed_box = (816, 80, 1576, 520)
    jump_box = (24, 548, 784, 876)
    turn_box = (816, 548, 1576, 876)
    footer_box = (24, 892, 1576, 976)

    _draw_line_plot(draw, speed_box, [(f['t'], f['speed']) for f in frames], SPEED_COLOR, 'Speed over time', f"peak: {analysis['summary']['peak_speed']}  stop: {analysis['summary']['stop_time']}s / {analysis['summary']['stop_distance']}m")
    _draw_line_plot(draw, jump_box, [(f['t'], f['y']) for f in jump_frames], JUMP_COLOR, 'Jump arc', f"apex: {analysis['summary']['jump_apex']}m  airtime: {analysis['summary']['jump_airtime']}s")
    _draw_line_plot(draw, turn_box, [(f['t'], f['yaw']) for f in frames], TURN_COLOR, 'Yaw response', f"90° turn: {analysis['summary']['turn_90_time']}s  mouse sens: {report['controller_profile']['mouse_sensitivity']}")

    draw.rounded_rectangle(path_box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((path_box[0] + 16, path_box[1] + 14), 'Movement path trace', fill=TEXT)
    draw.text((path_box[0] + 16, path_box[1] + 34), 'Synthetic movement script unless a live trace JSON is supplied.', fill=MUTED)
    inner = (path_box[0] + 18, path_box[1] + 62, path_box[2] - 18, path_box[3] - 18)
    _draw_grid(draw, inner)
    pts = _fit_points([(f['x'], f['z']) for f in frames], inner)
    if len(pts) >= 2:
        draw.line(pts, fill=PATH_COLOR, width=4)
    for idx in range(0, len(pts), max(1, len(pts) // 12)):
        px, py = pts[idx]
        draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=ACCENT)
    if pts:
        draw.ellipse((pts[0][0] - 6, pts[0][1] - 6, pts[0][0] + 6, pts[0][1] + 6), fill=GOOD)
        draw.ellipse((pts[-1][0] - 6, pts[-1][1] - 6, pts[-1][0] + 6, pts[-1][1] + 6), fill=BAD)

    draw.rounded_rectangle(footer_box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    scores = analysis['scores']
    draw.text((footer_box[0] + 16, footer_box[1] + 14), 'Ratings / clearances / nearest donors', fill=TEXT)
    score_y = footer_box[1] + 38
    score_x = footer_box[0] + 16
    for label, value in [('movement', scores['movement']), ('turning', scores['turning']), ('jump', scores['jump']), ('clearance', scores['clearance'])]:
        bar_w = 180
        draw.text((score_x, score_y), f'{label}: {value}', fill=MUTED)
        bx0 = score_x + 90
        by0 = score_y + 2
        draw.rounded_rectangle((bx0, by0, bx0 + bar_w, by0 + 12), radius=6, fill=(36, 42, 50, 255))
        fill = GOOD if value >= 85 else WARN if value >= 65 else BAD
        draw.rounded_rectangle((bx0, by0, bx0 + bar_w * max(0.0, min(1.0, value / 100.0)), by0 + 12), radius=6, fill=fill)
        score_x += 310

    left_x = footer_box[0] + 18
    y = footer_box[1] + 60
    for test in analysis['doorway_tests']:
        fill = GOOD if test['status'] == 'pass' else WARN if test['status'] == 'warn' else BAD
        draw.rounded_rectangle((left_x, y, left_x + 180, y + 20), radius=10, fill=fill)
        draw.text((left_x + 10, y + 3), f"door {test['door_width']}m -> {test['status']} ({test['ratio']})", fill=(8, 10, 12, 255))
        left_x += 210

    donor_x = footer_box[0] + 760
    donor_y = footer_box[1] + 56
    for donor in report.get('nearest_donors', [])[:3]:
        draw.text((donor_x, donor_y), f"{donor['label']}  d={donor['distance']}  feel={donor.get('feel_class', 'n/a')}", fill=MUTED)
        donor_y += 18

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Build controller movement diagnostics from a live trace or a derived controller profile.')
    ap.add_argument('--controller-json', help='Path to a controller-profile JSON or a JSON object with controller_profile.')
    ap.add_argument('--examples-library', help='Examples-library JSON for donor comparisons or donor-profile loading.')
    ap.add_argument('--editor-library', help='Editor-library JSON for donor-profile loading.')
    ap.add_argument('--modeling-library', help='Modeling-library JSON for donor-profile loading.')
    ap.add_argument('--donor', help='Donor slug to load from the examples/editor library when no explicit controller JSON is provided.')
    ap.add_argument('--trace-json', help='Optional runtime trace JSON with frames[{t,x,y,z,speed,yaw,pitch,grounded}].')
    ap.add_argument('--output', required=True, help='Path to write the controller diagnostics JSON.')
    ap.add_argument('--debug-image', help='Optional PNG summary panel.')
    ap.add_argument('--trace-output', help='Optional path to write the normalized trace JSON used for analysis.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    examples_library = _load_json(args.examples_library)
    editor_library = _load_json(args.editor_library)
    modeling_library = _load_json(args.modeling_library)
    raw_controller = _load_json(args.controller_json)
    controller_profile = None
    controller_notes: list[str] = []
    if isinstance(raw_controller, dict):
        controller_profile = raw_controller.get('controller_profile', raw_controller)
    if controller_profile is None:
        controller_profile, controller_notes = _extract_profile_from_libraries(examples_library, editor_library, modeling_library, args.donor)
    if controller_profile is None:
        raise SystemExit('No controller profile provided. Use --controller-json or --donor with an examples/editor/modeling library.')

    trace = None
    if args.trace_json:
        trace = _coerce_trace(_load_json(args.trace_json))

    report = analyze_controller(controller_profile, examples_library=examples_library, trace=trace)
    if controller_notes:
        report['controller_notes'] = controller_notes
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        build_debug_panel(report, Path(args.debug_image))
    if args.trace_output:
        Path(args.trace_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.trace_output).write_text(json.dumps({'frames': report['frames'], 'jump_frames': report['jump_frames']}, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
