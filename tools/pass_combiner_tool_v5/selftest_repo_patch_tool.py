#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
TOOL = ROOT / "repo_patch_tool.py"


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_zip(path: Path, files: dict[str, str | bytes]):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)


def run(args, cwd=None):
    cmd = [sys.executable, str(TOOL), *args]
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)


def load_plan(report_dir: Path):
    return json.loads((report_dir / "repo_patch_plan.json").read_text(encoding="utf-8"))


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_path_mapping_and_root_ban(tmp: Path):
    repo = tmp / "repo"
    repo.mkdir(parents=True)
    patch = tmp / "patch.zip"
    make_zip(patch, {"HoloCore/main.py": "print('hi')\n"})
    report = tmp / "r1"
    proc = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report)])
    assert_true(proc.returncode == 2, proc.stdout)
    plan = load_plan(report)
    assert_true(plan["errors"], "GX root ban should create errors without target prefix")

    report2 = tmp / "r2"
    proc2 = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--target-prefix", "data/HoloVerse/HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report2)])
    assert_true(proc2.returncode == 0, proc2.stdout)
    plan2 = load_plan(report2)
    assert_true(plan2["actions"][0]["target_path"] == "data/HoloVerse/HoloCore/main.py", "target prefix mapping failed")


def test_protected_partial_stage(tmp: Path):
    repo = tmp / "repo"
    write(repo / "data/HoloVerse/HoloCore/main.py", "\n".join(["def keep():", "    return 'important'", ""] + [f"x{i}= {i}" for i in range(700)]))
    patch = tmp / "partial.zip"
    make_zip(patch, {"HoloCore/main.py": "def new_small():\n    return 'partial'\n"})
    report = tmp / "r"
    proc = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--target-prefix", "data/HoloVerse/HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report), "--apply", "--fail-on-warning"])
    assert_true(proc.returncode == 0, proc.stdout)
    current = (repo / "data/HoloVerse/HoloCore/main.py").read_text(encoding="utf-8")
    assert_true("def keep" in current, "protected file lost existing code")
    assert_true("def new_small" in current, "safe additive definition was not merged")


def test_protected_stale_same_symbol_stage(tmp: Path):
    repo = tmp / "repo"
    write(repo / "data/HoloVerse/HoloCore/main.py", "\n".join(["def keep():", "    return 'important'", ""] + [f"x{i}= {i}" for i in range(700)]))
    patch = tmp / "stale.zip"
    make_zip(patch, {"HoloCore/main.py": "def keep():\n    return 'stale partial'\n"})
    report = tmp / "r"
    proc = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--target-prefix", "data/HoloVerse/HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report), "--apply", "--fail-on-warning"])
    assert_true(proc.returncode == 1, proc.stdout)
    current = (repo / "data/HoloVerse/HoloCore/main.py").read_text(encoding="utf-8")
    assert_true("important" in current and "stale partial" not in current, "stale same-symbol update replaced protected code")
    assert_true((repo / "_pass_overrides" / "stale" / "data/HoloVerse/HoloCore/main.py").exists(), "stale override was not staged")


def test_small_update_override(tmp: Path):
    repo = tmp / "repo"
    write(repo / "data/HoloVerse/HoloCore/ui/ui_manifest.json", '{"a":1}\n')
    patch = tmp / "small.zip"
    make_zip(patch, {"HoloCore/ui/ui_manifest.json": '{"a":2}\n'})
    report = tmp / "r"
    proc = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--target-prefix", "data/HoloVerse/HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report), "--apply", "--small-updates-to-overrides", "--fail-on-warning"])
    assert_true(proc.returncode == 1, proc.stdout)
    assert_true((repo / "data/HoloVerse/HoloCore/ui/ui_manifest.json").read_text() == '{"a":1}\n', "small update replaced live file")
    assert_true((repo / "_pass_overrides" / "small" / "data/HoloVerse/HoloCore/ui/ui_manifest.json").exists(), "small override missing")


def test_dry_run_no_write(tmp: Path):
    repo = tmp / "repo"
    repo.mkdir(parents=True)
    patch = tmp / "add.zip"
    make_zip(patch, {"HoloCore/dimensions/ocean_space.py": "REGION='deep'\n"})
    report = tmp / "r"
    proc = run(["--repo-root", str(repo), "--patch-zip", str(patch), "--strip-prefix", "HoloCore", "--target-prefix", "data/HoloVerse/HoloCore", "--profile", "gx-prototype-lab", "--report-dir", str(report)])
    assert_true(proc.returncode == 0, proc.stdout)
    assert_true(not (repo / "data/HoloVerse/HoloCore/dimensions/ocean_space.py").exists(), "dry-run wrote file")


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_path_mapping_and_root_ban(tmp / "a")
        test_protected_partial_stage(tmp / "b")
        test_protected_stale_same_symbol_stage(tmp / "c")
        test_small_update_override(tmp / "d")
        test_dry_run_no_write(tmp / "e")
    print("repo_patch_tool selftests passed")


if __name__ == "__main__":
    main()
