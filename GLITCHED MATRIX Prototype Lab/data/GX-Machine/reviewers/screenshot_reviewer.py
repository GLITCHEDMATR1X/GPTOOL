from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reviewers.image_zone_analyzer import analyze


ISSUE_TEMPLATES = {
    'center_blocked': {
        'category': 'ui_layout',
        'problem': 'The primary center zone is too busy for the selected capture type.',
        'why': 'Important play or work space should remain readable instead of being buried by overlays or clutter.',
        'fix': 'Reduce obstruction in the center zone by moving UI outward, shrinking overlays, or recapturing at a cleaner moment.',
    },
    'too_dark': {
        'category': 'lighting_contrast',
        'problem': 'The screenshot is too dark for dependable review.',
        'why': 'Dark frames hide silhouette, spacing, and text quality.',
        'fix': 'Raise exposure or key lighting and recapture from a more readable state.',
    },
    'low_contrast': {
        'category': 'lighting_contrast',
        'problem': 'Contrast is too weak across the frame.',
        'why': 'Weak separation flattens forms and lowers readability.',
        'fix': 'Increase subject/background value separation or strengthen local contrast around focal areas.',
    },
    'edge_heavy': {
        'category': 'composition',
        'problem': 'The frame is carrying too much visual pressure at the edges.',
        'why': 'Edge-heavy composition tends to read as cramped, clipped, or messy.',
        'fix': 'Pull the focal subject inward or move panels farther from the edges before capture.',
    },
    'corner_heavy': {
        'category': 'composition',
        'problem': 'Corners are overloaded relative to the capture profile.',
        'why': 'Corner overload creates crowding and can imply off-screen spill or sloppy anchoring.',
        'fix': 'Reduce corner congestion or rebalance the interface across more of the frame.',
    },
    'off_center_subject': {
        'category': 'camera_framing',
        'problem': 'The strongest focal region is not centered where the capture profile expects it.',
        'why': 'Off-center focal weight can make the shot feel accidental instead of intentional.',
        'fix': 'Adjust camera framing or reposition the subject before recapturing.',
    },
    'zone_overload': {
        'category': 'layout_zones',
        'problem': 'One or more protected zones exceed their expected occupancy.',
        'why': 'Protected zones exist to preserve readability and hierarchy.',
        'fix': 'Reduce detail or overlay footprint in the overloaded zone and recapture.',
    },
}


def issue(key: str, evidence: str, severity: str, zone: str | None = None) -> Dict[str, Any]:
    tpl = ISSUE_TEMPLATES[key]
    payload = {
        'category': tpl['category'],
        'severity': severity,
        'problem': tpl['problem'],
        'evidence': evidence,
        'why_it_matters': tpl['why'],
        'fastest_fix': tpl['fix'],
    }
    if zone:
        payload['zone'] = zone
    return payload


def score_from_penalty(base: float, penalty: float) -> float:
    return max(1.0, min(10.0, round(base - penalty, 2)))


def review_image(image_path: Path, layout_profile: str = 'gameplay') -> Dict[str, Any]:
    metrics = analyze(image_path, layout_profile)
    target = metrics['target']
    issues: List[Dict[str, Any]] = []

    mean_lum = metrics['global_luminance']['mean']
    contrast_std = metrics['global_luminance']['std']
    center_clearance = metrics['center_clearance']
    edge_pressure = metrics['edge_pressure']
    corner_pressure = metrics['corner_pressure']
    focal_centered = metrics['focal_cell']['centered']

    if center_clearance < target['center_clearance_min']:
        severity = 'high' if center_clearance < (target['center_clearance_min'] - 0.12) else 'medium'
        issues.append(issue(
            'center_blocked',
            f'Center clearance is {center_clearance:.2f}; target minimum is {target["center_clearance_min"]:.2f}.',
            severity,
        ))

    if mean_lum < target['mean_luminance_min']:
        severity = 'high' if mean_lum < (target['mean_luminance_min'] - 0.06) else 'medium'
        issues.append(issue(
            'too_dark',
            f'Frame mean luminance is {mean_lum:.2f}; target minimum is {target["mean_luminance_min"]:.2f}.',
            severity,
        ))

    if contrast_std < target['contrast_std_min']:
        issues.append(issue(
            'low_contrast',
            f'Frame luminance standard deviation is {contrast_std:.2f}; target minimum is {target["contrast_std_min"]:.2f}.',
            'medium',
        ))

    if edge_pressure > target['edge_pressure_max']:
        severity = 'high' if edge_pressure > (target['edge_pressure_max'] + 0.12) else 'medium'
        issues.append(issue(
            'edge_heavy',
            f'Edge pressure is {edge_pressure:.2f}; target maximum is {target["edge_pressure_max"]:.2f}.',
            severity,
        ))

    if corner_pressure > target['corner_pressure_max']:
        issues.append(issue(
            'corner_heavy',
            f'Corner pressure is {corner_pressure:.2f}; target maximum is {target["corner_pressure_max"]:.2f}.',
            'medium',
        ))

    if target.get('center_subject_preferred', False) and not focal_centered:
        issues.append(issue(
            'off_center_subject',
            f'Highest-focus cell is ({metrics["focal_cell"]["row"]}, {metrics["focal_cell"]["col"]}) instead of the center cell.',
            'medium',
        ))

    for zone in metrics['zones']:
        if (not zone['ui_allowed']) and zone['occupancy_score'] > 0.68:
            sev = 'high' if zone['occupancy_score'] > 0.82 else 'medium'
            issues.append(issue(
                'zone_overload',
                f'Protected zone occupancy is {zone["occupancy_score"]:.2f}, which is too high for {zone["name"]}.',
                sev,
                zone=zone['name'],
            ))

    penalty = sum({'low': 0.35, 'medium': 1.0, 'high': 2.0, 'critical': 3.0}[i['severity']] for i in issues)
    scores = {
        'ui_neatness': score_from_penalty(8.7, penalty * 0.45 + max(0.0, edge_pressure - target['edge_pressure_max']) * 5.0),
        'composition': score_from_penalty(8.6, penalty * 0.40 + max(0.0, corner_pressure - target['corner_pressure_max']) * 6.0),
        'lighting_contrast': score_from_penalty(8.5, penalty * 0.35 + max(0.0, target['mean_luminance_min'] - mean_lum) * 8.0 + max(0.0, target['contrast_std_min'] - contrast_std) * 8.0),
        'center_clearance': score_from_penalty(8.9, penalty * 0.55 + max(0.0, target['center_clearance_min'] - center_clearance) * 9.0),
        'subject_framing': score_from_penalty(8.4, penalty * 0.30 + (1.1 if target.get('center_subject_preferred', False) and not focal_centered else 0.0)),
    }
    scores['overall'] = round(sum(scores.values()) / len(scores), 2)

    summary = {
        'quick_verdict': 'Readable enough to submit.' if scores['overall'] >= 7.7 and not any(i['severity'] in {'high', 'critical'} for i in issues) else 'Needs revision before submission.',
        'layout_profile': layout_profile,
        'high_severity_issue_count': sum(1 for i in issues if i['severity'] in {'high', 'critical'}),
        'medium_issue_count': sum(1 for i in issues if i['severity'] == 'medium'),
        'review_confidence': 'medium',
        'review_limits': [
            'This reviewer measures image zones, pressure, brightness, contrast, and focal distribution; it does not truly identify objects or read every line of text semantically.',
            'Use a stronger vision layer or manual review for exact object identity, deep art direction, and guaranteed text comprehension.',
        ],
    }

    fix_order = [
        i['fastest_fix']
        for i in sorted(
            issues,
            key=lambda x: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x['severity'], 3),
        )
    ] or ['No material screenshot issues were detected by the current reviewer.']

    return {
        'image_path': str(image_path),
        'layout_profile': layout_profile,
        'metrics': metrics,
        'issues': issues,
        'scores': scores,
        'summary': summary,
        'fix_order': fix_order,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Run a structured screenshot review using layout expectations and frame heuristics.')
    ap.add_argument('--image', required=True)
    ap.add_argument('--layout-profile', default='gameplay')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    result = review_image(Path(args.image), args.layout_profile)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
