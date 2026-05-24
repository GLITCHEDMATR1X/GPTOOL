# Deprecated in v0.4. Prefer screenshot_correction_planner.py for correction planning.
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Dict, Any, List

ADJUSTMENT_MAP = {
    'lighting_contrast': [
        'Increase exposure or brighten the key-lit subject area before recapturing.',
        'Separate subject and background values more clearly.',
    ],
    'ui_layout': [
        'Move blocking panels toward the screen edges.',
        'Shrink nonessential overlay footprint before capture.',
    ],
    'composition': [
        'Recenter the focal subject and reduce edge crowding.',
        'Recapture from a cleaner angle with more balanced negative space.',
    ],
    '3d_clarity': [
        'Choose a camera angle with stronger front-to-back overlap.',
        'Increase depth separation with lighting or clearer silhouette staging.',
    ],
}


def route(report: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[str] = []
    for issue in report.get('issues', []):
        category = issue.get('category', '')
        for action in ADJUSTMENT_MAP.get(category, []):
            if action not in actions:
                actions.append(action)
    if not actions:
        actions.append('No automatic screenshot adjustment actions required.')
    return {
        'recommended_actions': actions,
        'action_count': len(actions),
        'source_issue_count': len(report.get('issues', [])),
    }


def main() -> int:
    ap=argparse.ArgumentParser(description='Translate screenshot review issues into concrete adjustment actions.')
    ap.add_argument('--review', required=True)
    ap.add_argument('--output', required=True)
    args=ap.parse_args()
    report=json.loads(Path(args.review).read_text(encoding='utf-8'))
    result=route(report)
    out=Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
