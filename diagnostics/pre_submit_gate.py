from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Any


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def gate(review: Dict[str, Any], planner: Dict[str, Any] | None = None, memory: Dict[str, Any] | None = None) -> Dict[str, Any]:
    failures = []
    warnings = []
    scores = review.get('scores', {})
    summary = review.get('summary', {})
    overall = float(scores.get('overall', 0.0))
    center = float(scores.get('center_clearance', 0.0))
    framing = float(scores.get('subject_framing', 0.0))
    high_count = int(summary.get('high_severity_issue_count', 0))

    if overall < 7.3:
        failures.append(f'Screenshot review overall score too low: {overall:.2f} < 7.30')
    if center < 7.0:
        failures.append(f'Center clearance too weak: {center:.2f} < 7.00')
    if framing < 6.7:
        failures.append(f'Subject framing too weak: {framing:.2f} < 6.70')
    if high_count > 0:
        failures.append(f'Screenshot review reported {high_count} high-severity issues.')

    if planner:
        if planner.get('apply_before_submit'):
            failures.append('Correction planner indicates screenshot fixes should be applied before submission.')
        elif planner.get('high_priority_action_count', 0) > 0:
            failures.append(f'Correction planner produced {planner.get("high_priority_action_count", 0)} high-priority actions.')

    if memory:
        repeated = memory.get('priority_visual_failures', [])
        if repeated:
            top = repeated[0]
            if int(top.get('count', 0)) >= 3:
                warnings.append(f'Repeated visual failure pattern detected: "{top.get("problem", "unknown")}" x{top.get("count", 0)}.')

    if overall < 7.8:
        warnings.append('Screenshot is passable at best; consider another capture or cleanup pass.')

    return {
        'passed': not failures,
        'failures': failures,
        'warnings': warnings,
        'checked_scores': {
            'overall': overall,
            'center_clearance': center,
            'subject_framing': framing,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Apply a pre-submit gate to screenshot review and correction state.')
    ap.add_argument('--review', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--planner')
    ap.add_argument('--memory')
    args = ap.parse_args()
    review = load_json(Path(args.review))
    planner = load_json(Path(args.planner)) if args.planner else None
    memory = load_json(Path(args.memory)) if args.memory else None
    result = gate(review, planner, memory)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
