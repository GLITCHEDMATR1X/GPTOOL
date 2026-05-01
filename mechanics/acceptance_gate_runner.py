from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Dict, List, Any

def load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def normalize_checklist(items: List[dict]) -> List[dict]:
    normalized=[]
    for item in items:
        normalized.append({'text': item.get('text','').strip(), 'checked': bool(item.get('checked', False)), 'hard': bool(item.get('hard', False))})
    return normalized

def evaluate_mechanic(mechanic: Dict[str, Any]) -> Dict[str, Any]:
    acceptance = normalize_checklist(mechanic.get('acceptance_checklist', []))
    failed = [item['text'] for item in acceptance if not item['checked']]
    return {
        'name': mechanic.get('name','unknown'),
        'hard_standard_count': len(mechanic.get('hard_standards', [])),
        'acceptance_total': len(acceptance),
        'acceptance_passed': len(acceptance)-len(failed),
        'failed_acceptance': failed,
        'passed': not failed,
    }

def build_summary(manifest: Dict[str, Any]) -> Dict[str, Any]:
    results = [evaluate_mechanic(m) for m in manifest.get('mechanics', [])]
    failed = [r for r in results if not r['passed']]
    return {
        'mechanic_count': len(results),
        'passed_count': len(results)-len(failed),
        'failed_count': len(failed),
        'passed': not failed,
        'results': results,
    }

def main() -> int:
    ap=argparse.ArgumentParser(description='Run mechanic acceptance gates against a machine-readable manifest.')
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--output', required=True)
    args=ap.parse_args()
    summary = build_summary(load_manifest(Path(args.manifest)))
    out=Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if summary.get('passed') else 1

if __name__=='__main__':
    raise SystemExit(main())
