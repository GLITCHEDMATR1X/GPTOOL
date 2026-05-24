from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)
WARN = (255, 191, 124, 255)
BAD = (255, 130, 130, 255)

SUPPORTED_RUNTIME_EXTS = {'.glb', '.gltf', '.bam', '.egg', '.fbx'}
SUPPORTED_CLIP_EXTS = {'.glb', '.gltf', '.bam', '.egg', '.fbx'}


def _fit_lines(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return ['']
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += ' ' + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def panda_path(path: Path):
    from panda3d.core import Filename
    return Filename.fromOsSpecific(str(path.resolve())).getFullpath()


def _safe_number(value: float | int | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _guess_role(name: str) -> str:
    lowered = name.lower().replace(' ', '_')
    checks = [
        ('idle', ('idle', 'rest', 'breath')),
        ('walk', ('walk', 'stroll')),
        ('run', ('run', 'jog', 'sprint')),
        ('attack', ('attack', 'punch', 'kick', 'hit', 'hook', 'strike')),
        ('jump', ('jump', 'leap', 'hop')),
        ('fall', ('fall', 'die', 'dying', 'knockdown', 'sweep')),
        ('get_up', ('get_up', 'getting_up', 'rise', 'recover')),
    ]
    for role, tokens in checks:
        if any(token in lowered for token in tokens):
            return role
    return 'unknown'


def _bounds_metrics(node) -> dict[str, Any]:
    tight = node.getTightBounds()
    if not tight:
        return {'available': False, 'extents': None, 'largest_dimension': None, 'center': None}
    lo, hi = tight
    extents = [float(hi[i] - lo[i]) for i in range(3)]
    center = [float((hi[i] + lo[i]) * 0.5) for i in range(3)]
    return {
        'available': True,
        'extents': [_safe_number(v) for v in extents],
        'largest_dimension': _safe_number(max(extents) if extents else 0.0),
        'center': [_safe_number(v) for v in center],
    }


class AnimationValidationApp:
    def __init__(self) -> None:
        from panda3d.core import AmbientLight, DirectionalLight, Vec3, loadPrcFileData
        loadPrcFileData('', 'window-type offscreen')
        loadPrcFileData('', 'audio-library-name null')
        loadPrcFileData('', 'win-size 1280 720')
        loadPrcFileData('', 'sync-video false')
        from direct.showbase.ShowBase import ShowBase

        self.base = ShowBase(windowType='offscreen')
        self.base.disableMouse()
        self.base.setBackgroundColor(0.05, 0.06, 0.08, 1.0)
        ambient = AmbientLight('ambient')
        ambient.setColor((0.55, 0.55, 0.62, 1.0))
        directional = DirectionalLight('key')
        directional.setColor((0.85, 0.88, 0.94, 1.0))
        key_np = self.base.render.attachNewNode(directional)
        key_np.setHpr(-35, -28, 0)
        self.base.render.setLight(self.base.render.attachNewNode(ambient))
        self.base.render.setLight(key_np)
        self._vec3 = Vec3
        try:
            import gltf  # noqa: F401
        except Exception:
            pass

    def step(self, frames: int = 2) -> None:
        for _ in range(frames):
            self.base.taskMgr.step()
            self.base.graphicsEngine.renderFrame()

    def load_actor(self, asset: Path, anims: dict[str, str] | None = None):
        from direct.actor.Actor import Actor
        actor = Actor(panda_path(asset), anims or None)
        actor.reparentTo(self.base.render)
        self.step(2)
        return actor

    def frame_actor(self, actor, center: list[float] | None, largest_dimension: float | None) -> None:
        largest = max(float(largest_dimension or 2.0), 2.0)
        cx, cy, cz = center or [0.0, 0.0, 0.0]
        self.base.camera.setPos(cx, cy - largest * 2.45, cz + largest * 0.58)
        self.base.camera.lookAt(cx, cy, cz + largest * 0.28)
        self.step(2)

    def capture(self, output_path: Path) -> str | None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.base.screenshot(namePrefix=str(output_path.with_suffix('')), defaultFilename=False)
            if output_path.exists():
                return str(output_path)
        except Exception:
            pass
        try:
            if self.base.win:
                self.base.win.saveScreenshot(panda_path(output_path))
                if output_path.exists():
                    return str(output_path)
        except Exception:
            pass
        return None

    def close(self) -> None:
        try:
            self.base.destroy()
        except Exception:
            pass


def collect_clip_paths(clips: list[str], clips_dir: str | None) -> list[Path]:
    gathered: list[Path] = []
    seen: set[Path] = set()
    for raw in clips:
        path = Path(raw).resolve()
        if path.exists() and path.suffix.lower() in SUPPORTED_CLIP_EXTS and path not in seen:
            gathered.append(path)
            seen.add(path)
    if clips_dir:
        root = Path(clips_dir).resolve()
        if root.exists():
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.suffix.lower() in SUPPORTED_CLIP_EXTS and path not in seen:
                    gathered.append(path)
                    seen.add(path)
    return gathered


def validate_animation_asset(asset: Path, clips: list[Path], screenshot_path: Path | None = None) -> dict[str, Any]:
    app = AnimationValidationApp()
    report: dict[str, Any] = {
        'validator': 'animation_asset_validator',
        'asset': str(asset),
        'asset_suffix': asset.suffix.lower(),
        'base_runtime': {},
        'clips': [],
        'summary': {},
        'recommendations': [],
    }
    try:
        base_actor = app.load_actor(asset)
        base_anim_names = sorted(base_actor.getAnimNames())
        base_bounds = _bounds_metrics(base_actor)
        report['base_runtime'] = {
            'load_ok': True,
            'embedded_anim_names': base_anim_names,
            'embedded_anim_count': len(base_anim_names),
            'bounds': base_bounds,
            'preferred_runtime_format': 'glb' if asset.suffix.lower() in {'.glb', '.gltf'} else asset.suffix.lower().lstrip('.'),
        }
        app.frame_actor(base_actor, base_bounds.get('center'), base_bounds.get('largest_dimension'))
        if screenshot_path is not None:
            shot = app.capture(screenshot_path)
            if shot:
                report['base_runtime']['screenshot'] = shot
        base_largest = float(base_bounds.get('largest_dimension') or 0.0)
        valid_count = 0
        invalid_count = 0
        valid_fbx_count = 0
        tested_fbx_count = 0
        suffix_counts: dict[str, int] = {}
        for clip_path in clips:
            suffix_counts[clip_path.suffix.lower()] = suffix_counts.get(clip_path.suffix.lower(), 0) + 1
            if clip_path.suffix.lower() == '.fbx':
                tested_fbx_count += 1
            alias = clip_path.stem.lower().replace(' ', '_').replace('-', '_')
            clip_report: dict[str, Any] = {
                'alias': alias,
                'path': str(clip_path),
                'suffix': clip_path.suffix.lower(),
                'role_guess': _guess_role(clip_path.stem),
                'load_ok': False,
                'reason': None,
            }
            actor = None
            try:
                actor = app.load_actor(asset, {alias: panda_path(clip_path)})
                anim_names = sorted(actor.getAnimNames())
                clip_report['runtime_anim_names'] = anim_names
                control = actor.getAnimControl(alias)
                clip_report['load_ok'] = control is not None and alias in anim_names
                if not clip_report['load_ok']:
                    clip_report['reason'] = 'clip alias did not bind into the Actor runtime set'
                    invalid_count += 1
                else:
                    frame_count = max(1, int(control.getNumFrames()))
                    sample_frames = sorted({0, max(0, frame_count // 2), max(0, frame_count - 1)})
                    sample_metrics = []
                    nondegenerate_hits = 0
                    for frame in sample_frames:
                        actor.pose(alias, frame)
                        app.step(2)
                        bounds = _bounds_metrics(actor)
                        largest = float(bounds.get('largest_dimension') or 0.0)
                        ratio = largest / max(base_largest, 1e-6) if base_largest > 0 else None
                        sample_metrics.append({'frame': int(frame), 'largest_dimension': _safe_number(largest), 'ratio_vs_base': _safe_number(ratio)})
                        if largest > max(1.0, base_largest * 0.2):
                            nondegenerate_hits += 1
                    clip_report['frame_count'] = frame_count
                    clip_report['sample_metrics'] = sample_metrics
                    clip_report['nondegenerate_sample_count'] = nondegenerate_hits
                    collapsed = nondegenerate_hits == 0
                    clip_report['bind_status'] = 'valid_runtime_clip' if not collapsed else 'collapsed_or_degenerate'
                    if collapsed:
                        clip_report['reason'] = 'clip bound but posed extents collapsed below runtime-safe thresholds'
                        invalid_count += 1
                    else:
                        valid_count += 1
                        if clip_path.suffix.lower() == '.fbx':
                            valid_fbx_count += 1
            except Exception as exc:
                clip_report['reason'] = f'{type(exc).__name__}: {exc}'
                invalid_count += 1
            finally:
                if actor is not None:
                    try:
                        actor.cleanup()
                    except Exception:
                        pass
                    actor.removeNode()
                    app.step(1)
            report['clips'].append(clip_report)
        preferred_export_path = 'animated_glb_runtime' if asset.suffix.lower() in {'.glb', '.gltf'} else 'convert_or_reexport_to_glb'
        report['summary'] = {
            'clip_count': len(clips),
            'valid_clip_count': valid_count,
            'invalid_clip_count': invalid_count,
            'clip_suffix_counts': suffix_counts,
            'preferred_export_path': preferred_export_path,
            'external_fbx_status': ('usable_with_validation' if tested_fbx_count and valid_fbx_count else ('unsupported_or_unproven' if tested_fbx_count else 'not_tested')),
            'bridge_readiness': 'pass' if report['base_runtime'].get('load_ok') and (not clips or valid_count > 0) else 'fail',
        }
        recs = [
            'Prefer GLB or glTF as the Panda3D runtime target for rigged characters and preserved embedded animations.',
        ]
        if any(item.get('suffix') == '.fbx' and item.get('bind_status') == 'collapsed_or_degenerate' for item in report['clips']):
            recs.append('One or more FBX clips collapsed after binding; re-export the clips against the exact runtime skeleton or convert the proven clip set to GLB before shipping.')
        elif any(item.get('suffix') == '.fbx' and item.get('bind_status') == 'valid_runtime_clip' for item in report['clips']):
            recs.append('FBX source clips are present. Keep them as source assets, but only trust them for runtime after this validator shows nondegenerate posed bounds.')
        elif any(item.get('suffix') == '.fbx' for item in report['clips']):
            recs.append('FBX source clips were detected, but none produced a proven runtime-safe bind in this pass. Prefer exporting the validated set to GLB for Panda3D delivery.')
        if report['summary']['preferred_export_path'] != 'animated_glb_runtime':
            recs.append('The base asset is not GLB-first. For Panda3D runtime delivery, add a GLB export step and rerun this validator on the exported asset.')
        report['recommendations'] = recs
    except Exception as exc:
        report['base_runtime'] = {'load_ok': False, 'reason': f'{type(exc).__name__}: {exc}'}
        report['summary'] = {'clip_count': len(clips), 'valid_clip_count': 0, 'invalid_clip_count': len(clips), 'bridge_readiness': 'fail'}
        report['recommendations'] = ['Base asset failed to load in Panda3D. Confirm the file exists, uses a supported runtime format, and has a compatible skeleton before testing clips.']
    finally:
        app.close()
    return report


def render_debug_panel(report: dict[str, Any], output_path: Path) -> None:
    width = 1700
    base_card_h = 240
    clip_h = 144
    margin = 24
    spacing = 16
    clips = report.get('clips', [])
    screenshot_exists = False
    screenshot_path = None
    base_runtime = report.get('base_runtime', {})
    if base_runtime.get('screenshot'):
        screenshot_path = Path(base_runtime['screenshot'])
        screenshot_exists = screenshot_path.exists()
    right_col_w = 560 if screenshot_exists else 0
    height = 150 + base_card_h + 18 + max(1, len(clips)) * (clip_h + spacing) + 32
    img = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(img)
    draw.text((margin, 18), 'Animation Asset Validator v0.16', fill=TEXT)
    draw.text((margin, 50), str(report.get('asset', '')), fill=MUTED)
    summary = report.get('summary', {})
    draw.text((margin, 78), f"readiness: {summary.get('bridge_readiness', 'unknown')} | valid clips: {summary.get('valid_clip_count', 0)} / {summary.get('clip_count', 0)}", fill=ACCENT)

    left_x = margin
    card_w = width - margin * 2 - right_col_w - (18 if right_col_w else 0)
    draw.rounded_rectangle((left_x, 112, left_x + card_w, 112 + base_card_h), radius=22, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((left_x + 24, 132), 'Base Runtime', fill=TEXT)
    draw.text((left_x + 24, 162), f"load_ok: {base_runtime.get('load_ok', False)} | preferred runtime format: {base_runtime.get('preferred_runtime_format', 'unknown')}", fill=MUTED)
    bounds = base_runtime.get('bounds', {})
    draw.text((left_x + 24, 192), f"embedded animations: {base_runtime.get('embedded_anim_count', 0)} | extents: {bounds.get('extents', [])}", fill=MUTED)
    anim_names = ', '.join(base_runtime.get('embedded_anim_names', [])[:6]) or 'None'
    for i, line in enumerate(_fit_lines(f"embedded names: {anim_names}", 86)[:3]):
        draw.text((left_x + 24, 220 + i * 24), line, fill=TEXT)
    recs = report.get('recommendations', [])
    for i, line in enumerate(recs[:3]):
        for j, sub in enumerate(_fit_lines(line, 88)[:2]):
            draw.text((left_x + 24, 300 + (i * 2 + j) * 22), sub, fill=ACCENT if i == 0 else MUTED)

    if screenshot_exists and screenshot_path is not None:
        panel_x = left_x + card_w + 18
        draw.rounded_rectangle((panel_x, 112, width - margin, 112 + base_card_h), radius=22, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.text((panel_x + 20, 132), 'Runtime Screenshot', fill=TEXT)
        shot = Image.open(screenshot_path).convert('RGBA')
        shot.thumbnail((right_col_w - 40, base_card_h - 60))
        img.alpha_composite(shot, (panel_x + (right_col_w - shot.width) // 2, 162 + (base_card_h - 60 - shot.height) // 2))

    y = 112 + base_card_h + 18
    for clip in clips:
        status = clip.get('bind_status') or ('load_failed' if not clip.get('load_ok') else 'runtime_loaded')
        tint = GOOD if status == 'valid_runtime_clip' else (WARN if clip.get('load_ok') else BAD)
        draw.rounded_rectangle((margin, y, width - margin, y + clip_h), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.rounded_rectangle((margin + 10, y + 10, margin + 26, y + clip_h - 10), radius=8, fill=tint)
        draw.text((margin + 40, y + 16), f"{clip.get('alias')} [{clip.get('suffix')}]", fill=TEXT)
        draw.text((margin + 40, y + 44), f"role: {clip.get('role_guess')} | status: {status}", fill=MUTED)
        reason = clip.get('reason') or 'No blocking issue detected.'
        for i, line in enumerate(_fit_lines(reason, 118)[:2]):
            draw.text((margin + 40, y + 72 + i * 20), line, fill=tint if 'collapsed' in reason else MUTED)
        sample_metrics = clip.get('sample_metrics', [])
        if sample_metrics:
            snippet = ', '.join(f"f{m['frame']} ratio={m['ratio_vs_base']}" for m in sample_metrics[:3])
            draw.text((margin + 40, y + 112), snippet, fill=TEXT)
        y += clip_h + spacing
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate Panda3D runtime compatibility for a rigged base asset and optional external animation clips.')
    ap.add_argument('--asset', required=True, help='Base runtime asset to test (.glb/.gltf/.bam/.egg/.fbx).')
    ap.add_argument('--clips', nargs='*', default=[], help='Optional external clips to test against the base runtime asset.')
    ap.add_argument('--clips-dir', help='Optional directory of external clips to test.')
    ap.add_argument('--output', required=True, help='Path to write the validation JSON.')
    ap.add_argument('--debug-image', help='Optional summary PNG.')
    ap.add_argument('--screenshot', help='Optional runtime screenshot PNG path for the base asset.')
    ap.add_argument('--json', action='store_true', help='Print the final validation JSON to stdout.')
    args = ap.parse_args()

    asset = Path(args.asset).resolve()
    if not asset.exists() or asset.suffix.lower() not in SUPPORTED_RUNTIME_EXTS:
        raise SystemExit(f'Unsupported or missing asset: {asset}')
    clips = collect_clip_paths(args.clips, args.clips_dir)
    report = validate_animation_asset(asset, clips, screenshot_path=Path(args.screenshot).resolve() if args.screenshot else None)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        render_debug_panel(report, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report.get('summary', {}).get('bridge_readiness') == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
