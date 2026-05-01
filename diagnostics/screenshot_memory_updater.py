from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Any


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def update_memory(memory: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    failures = memory.setdefault('screenshot_failures', {})
    projects = memory.setdefault('projects', {})
    project_key = review.get('layout_profile', 'unknown')
    project_entry = projects.setdefault(project_key, {'runs': 0, 'issues': {}})
    project_entry['runs'] += 1
    for issue in review.get('issues', []):
        problem_key = issue.get('problem', 'unknown_problem')
        failures[problem_key] = int(failures.get(problem_key, 0)) + 1
        project_entry['issues'][problem_key] = int(project_entry['issues'].get(problem_key, 0)) + 1
    ranked = sorted(failures.items(), key=lambda kv: (-kv[1], kv[0]))
    memory['priority_visual_failures'] = [{'problem': k, 'count': v} for k, v in ranked[:10]]
    return memory


def main() -> int:
    ap = argparse.ArgumentParser(description='Update screenshot failure memory using the latest screenshot review report.')
    ap.add_argument('--memory', required=True)
    ap.add_argument('--review', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    memory_path = Path(args.memory)
    review = load_json(Path(args.review), {})
    memory = load_json(memory_path, {'screenshot_failures': {}, 'projects': {}, 'priority_visual_failures': []})
    updated = update_memory(memory, review)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(updated, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
