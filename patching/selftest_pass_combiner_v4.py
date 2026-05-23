#!/usr/bin/env python3
"""V4 regression tests for repo-aware patch outputs and review gates."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMBINER = HERE / "pass_combiner.py"


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return proc.returncode, proc.stdout


def write_zip(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)


def make_base(root: Path) -> Path:
    base_zip = root / "BaseProject.zip"
    write_zip(base_zip, {
        "BaseProject/main.py": "def keep_me():\n    return 'old'\n\ndef shared():\n    return 1\n",
        "BaseProject/data.json": '{"version": 1}\n',
    })
    return base_zip


def test_patch_zip_and_diff_outputs(tmp: Path) -> None:
    base = make_base(tmp)
    patch = tmp / "pass.zip"
    write_zip(patch, {
        "BaseProject/main.py": "def keep_me():\n    return 'old'\n\ndef shared():\n    return 2\n\ndef added():\n    return 'new'\n",
        "BaseProject/new_asset.txt": "signal\n",
    })
    out = tmp / "combined"
    patch_zip = tmp / "delta.zip"
    diff = tmp / "delta.diff"
    rc, output = run([
        sys.executable, str(COMBINER),
        "--base", str(base),
        "--patches", str(patch),
        "--project-root-name", "BaseProject",
        "--output-dir", str(out),
        "--output-patch-zip", str(patch_zip),
        "--output-diff", str(diff),
        "--report-dir", str(tmp / "reports"),
        "--allow-protected-overwrite",
    ])
    assert rc == 0, output
    assert patch_zip.exists(), output
    assert diff.exists(), output
    with zipfile.ZipFile(patch_zip) as zf:
        names = set(zf.namelist())
    assert "BaseProject/main.py" in names
    assert "BaseProject/new_asset.txt" in names
    assert "def added" in diff.read_text(encoding="utf-8")


def test_symbol_regression_blocks_final_zip(tmp: Path) -> None:
    base = make_base(tmp)
    patch = tmp / "bad.zip"
    write_zip(patch, {"BaseProject/main.py": "def shared():\n    return 9\n"})
    out_zip = tmp / "should_not_write.zip"
    rc, output = run([
        sys.executable, str(COMBINER),
        "--base", str(base),
        "--patches", str(patch),
        "--project-root-name", "BaseProject",
        "--output-dir", str(tmp / "combined_symbol"),
        "--output-zip", str(out_zip),
        "--report-dir", str(tmp / "reports_symbol"),
        "--allow-protected-overwrite",
        "--allow-shrink-overwrite",
        "--relaxed-protected",
        "--emit-symbol-manifest",
        "--fail-on-symbol-removal",
    ])
    assert rc != 0, output
    assert not out_zip.exists(), "final zip should be blocked by symbol regression"
    data = json.loads((tmp / "reports_symbol" / "symbol_regressions.json").read_text(encoding="utf-8"))
    assert "main.py" in data
    assert "keep_me" in data["main.py"].get("removed_functions", [])


def test_banned_text_blocks_final_zip(tmp: Path) -> None:
    base = make_base(tmp)
    patch = tmp / "bad_text.zip"
    write_zip(patch, {"BaseProject/data.json": "placeholder_mode\n"})
    out_zip = tmp / "should_not_write_banned.zip"
    rc, output = run([
        sys.executable, str(COMBINER),
        "--base", str(base),
        "--patches", str(patch),
        "--project-root-name", "BaseProject",
        "--output-dir", str(tmp / "combined_banned"),
        "--output-zip", str(out_zip),
        "--report-dir", str(tmp / "reports_banned"),
        "--banned-text", "placeholder_mode",
        "--fail-on-banned-text",
    ])
    assert rc != 0, output
    assert not out_zip.exists(), "final zip should be blocked by banned text"
    hits = json.loads((tmp / "reports_banned" / "banned_text_hits.json").read_text(encoding="utf-8"))
    assert hits and hits[0]["term"] == "placeholder_mode"


def main() -> int:
    tests = [
        test_patch_zip_and_diff_outputs,
        test_symbol_regression_blocks_final_zip,
        test_banned_text_blocks_final_zip,
    ]
    with tempfile.TemporaryDirectory(prefix="spc_v4_selftest_") as td:
        root = Path(td)
        for test in tests:
            work = root / test.__name__
            work.mkdir()
            print(f"running {test.__name__}")
            test(work)
            print(f"passed {test.__name__}")
    print("selftest v4 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
