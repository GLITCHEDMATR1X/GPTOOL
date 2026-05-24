from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List

CATEGORY_ACTIONS = {
    'lighting_contrast': [
        {'system': 'lighting', 'action': 'raise_exposure', 'priority': 'high'},
        {'system': 'lighting', 'action': 'increase_subject_background_separation', 'priority': 'high'},
        {'system': 'capture', 'action': 'recapture_brighter_frame', 'priority': 'medium'},
    ],
    'ui_layout': [
        {'system': 'ui_layout', 'action': 'push_ui_to_edges', 'priority': 'high'},
        {'system': 'ui_layout', 'action': 'reduce_overlay_footprint', 'priority': 'high'},
    ],
    'layout_zones': [
        {'system': 'ui_layout', 'action': 'clear_protected_zone', 'priority': 'high'},
        {'system': 'capture', 'action': 'recapture_cleaner_state', 'priority': 'medium'},
    ],
    'composition': [
        {'system': 'camera', 'action': 'rebalance_frame', 'priority': 'medium'},
        {'system': 'camera', 'action': 'reduce_edge_pressure', 'priority': 'medium'},
    ],
    'camera_framing': [
        {'system': 'camera', 'action': 'recenter_subject', 'priority': 'high'},
        {'system': 'camera', 'action': 'adjust_distance_or_pitch', 'priority': 'medium'},
    ],
}


def plan(report: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    seen = set()
    for issue in sorted(report.get('issues', []), key=lambda i: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(i.get('severity', 'low'), 3)):
        category = issue.get('category', '')
        for action in CATEGORY_ACTIONS.get(category, []):
            key = (action['system'], action['action'])
            if key in seen:
                continue
            seen.add(key)
            actions.append({
                **action,
                'trigger_category': category,
                'trigger_problem': issue.get('problem', ''),
            })
    urgent = [a for a in actions if a['priority'] == 'high']
    return {
        'apply_before_submit': bool(urgent) or report.get('scores', {}).get('overall', 0) < 7.7,
        'recommended_actions': actions or [{
            'system': 'capture',
            'action': 'keep_current_capture',
            'priority': 'low',
            'trigger_category': 'none',
            'trigger_problem': 'No material review issues detected.',
        }],
        'high_priority_action_count': len(urgent),
        'source_issue_count': len(report.get('issues', [])),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Plan screenshot corrections from a screenshot review report.')
    ap.add_argument('--review', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    report = json.loads(Path(args.review).read_text(encoding='utf-8'))
    result = plan(report)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
