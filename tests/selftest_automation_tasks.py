#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation_tasks.task_schema import validate_manifest, find_junk, load_manifest
from automation_tasks.task_runner import TaskRunner


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def test_manifest_validation():
    data = {"schema": "gptool.task.v1", "id": "selftest", "steps": [{"action": "note", "message": "ok"}]}
    report = validate_manifest(data)
    assert_true(report["ok"], report)
    bad = {"schema": "gptool.task.v1", "id": "bad", "steps": [{"action": "missing"}]}
    report = validate_manifest(bad)
    assert_true(not report["ok"], "bad action should fail")


def test_dry_run_blocks_commands():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "created.txt"
        manifest = {"id": "dry", "title": "dry", "steps": [{"action": "command", "label": "write", "cmd": f"{sys.executable} -c \"open(r'{out}','w').write('x')\""}]}
        report = TaskRunner(manifest, apply=False, report_dir=Path(td)/"reports").run()
        assert_true(report["ok"], report)
        assert_true(not out.exists(), "dry-run command should not create file")


def test_apply_runs_commands():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "created.txt"
        manifest = {"id": "apply", "title": "apply", "steps": [{"action": "command", "label": "write", "cmd": [sys.executable, "-c", f"open(r'{out}','w').write('x')"]}]}
        report = TaskRunner(manifest, apply=True, report_dir=Path(td)/"reports").run()
        assert_true(report["ok"], report)
        assert_true(out.exists(), "apply command should create file")


def test_junk_detection():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "x.pyc").write_bytes(b"x")
        junk = find_junk(root)
        assert_true(junk, "junk should be detected")


def test_root_variable_expansion():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        config = root / "roots.json"
        config.write_text(json.dumps({"schema": "gptool.local_project_roots.v1", "roots": {"project": str(root)}}), encoding="utf-8")
        manifest_path = root / "task.json"
        manifest_path.write_text(json.dumps({
            "schema": "gptool.task.v1",
            "id": "roots",
            "steps": [{"action": "assert_dir_exists", "path": "${project}"}],
        }), encoding="utf-8")
        data = load_manifest(manifest_path, root_config=config)
        assert_true(data["steps"][0]["path"] == str(root), data)
        report = validate_manifest(data)
        assert_true(report["ok"], report)



def test_nonblocking_failure_is_warning():
    with tempfile.TemporaryDirectory() as td:
        manifest = {
            "id": "warn",
            "title": "warn",
            "steps": [
                {"action": "command", "label": "fail but continue", "cmd": [sys.executable, "-c", "raise SystemExit(7)"], "block_on_fail": False},
                {"action": "note", "label": "after", "message": "continued"},
            ],
        }
        report = TaskRunner(manifest, apply=True, report_dir=Path(td)/"reports").run()
        assert_true(report["ok"], report)
        assert_true(report.get("warning_count") == 1, report)
        assert_true(report.get("blocking_failure_count") == 0, report)
        assert_true(report.get("completed_steps") == 2, report)


def main():
    test_manifest_validation()
    test_dry_run_blocks_commands()
    test_apply_runs_commands()
    test_junk_detection()
    test_root_variable_expansion()
    test_nonblocking_failure_is_warning()
    print("PASS: automation task selftests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
