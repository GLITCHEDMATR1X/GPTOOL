from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from automation_tasks.input_script import load_input_plan, render_input_plan_markdown, validate_input_plan, write_input_plan
from automation_tasks.task_runner import TaskRunner


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan = {
            "id": "sample_vector_journey",
            "title": "Sample Vector Journey",
            "steps": [
                {"action": "enter_artifact", "slot": 1},
                {"action": "hold_key", "key": "w", "seconds": 0.5},
                {"action": "mouse_click", "button": "left"},
                {"action": "screenshot", "name": "proof"},
                {"action": "exit_to_hub"},
            ],
        }
        result = write_input_plan(root / "plan.json", plan)
        assert result["ok"], result
        loaded = load_input_plan(root / "plan.json")
        validation = validate_input_plan(loaded)
        assert validation["ok"], validation
        assert validation["screenshot_count"] == 1, validation
        assert validation["artifact_slots"] == [1], validation
        md = render_input_plan_markdown(loaded, validation)
        assert "Sample Vector Journey" in md

        manifest = {
            "id": "selftest_task_bot",
            "title": "Selftest Task Bot",
            "steps": [
                {
                    "action": "write_input_plan",
                    "label": "write inline plan",
                    "output": "plans/inline.json",
                    "steps": plan["steps"],
                },
                {
                    "action": "validate_input_plan",
                    "label": "validate inline plan",
                    "steps": plan["steps"],
                },
                {
                    "action": "screenshot_checkpoint",
                    "label": "optional missing screenshot",
                    "path": str(root / "missing.png"),
                    "required": False,
                },
            ],
        }
        runner = TaskRunner(manifest, report_dir=root / "reports")
        report = runner.run()
        assert report["ok"], json.dumps(report, indent=2)
        assert (root / "reports" / "plans" / "inline.json").is_file()
    print("selftest_test_run_bot passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
