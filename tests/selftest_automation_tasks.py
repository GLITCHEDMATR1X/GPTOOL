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

from automation_tasks.task_schema import validate_manifest, find_junk
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


def main():
    test_manifest_validation()
    test_dry_run_blocks_commands()
    test_apply_runs_commands()
    test_junk_detection()
    print("PASS: automation task selftests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
