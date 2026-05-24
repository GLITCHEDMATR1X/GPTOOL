#!/usr/bin/env python3
"""Self-test suite for Safe Pass Combiner v3.

These tests intentionally try to trigger the failure modes that usually cause
pass-zip regressions: partial protected files, larger stale protected files,
small review-only updates, CRLF/LF patch drift, failed diffs, and validator
failures that should block final zips.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

TOOL = Path(__file__).with_name("pass_combiner.py").resolve()


def make_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def invoke(tmp: Path, base: Path, patches: list[Path], out_name: str, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    order = tmp / f"{out_name}_order.txt"
    order.write_text("\n".join(str(p) for p in patches) + "\n", encoding="utf-8")
    out = tmp / out_name
    reports = tmp / f"{out_name}_reports"
    cmd = [
        sys.executable, str(TOOL),
        "--base", str(base),
        "--order-file", str(order),
        "--project-root-name", "HoloCore",
        "--output-dir", str(out),
        "--report-dir", str(reports),
        "--emit-file-manifest",
    ]
    if extra:
        cmd.extend(extra)
    return run(cmd)


def test_protected_additive_override(tmp: Path) -> None:
    base = tmp / "base_partial.zip"
    patch = tmp / "patch_partial.zip"
    make_zip(base, {"HoloCore/main.py": "def keep():\n    return 'new-integrated'\n\ndef stable():\n    return 1\n"})
    make_zip(patch, {"HoloCore/main.py": "def keep():\n    return 'old-partial'\n\ndef added():\n    return 2\n"})
    proc = invoke(tmp, base, [patch], "out_partial")
    require(proc.returncode != 0, "protected unresolved overwrite should require review")
    text = (tmp / "out_partial" / "main.py").read_text(encoding="utf-8")
    require("return 'new-integrated'" in text, text)
    require("def added" in text, text)
    require((tmp / "out_partial" / "_pass_overrides" / "patch_partial" / "main.py").exists(), "override missing")


def test_larger_stale_protected_blocks(tmp: Path) -> None:
    base = tmp / "base_larger.zip"
    patch = tmp / "patch_larger.zip"
    base_text = "def vessel_update():\n    return 'vertical strata + ocean space'\n\ndef rescue():\n    return 'safe anchor'\n"
    stale = "# larger but stale\n" + ("# filler\n" * 80) + "def vessel_update():\n    return 'old vessel only'\n\ndef new_button():\n    return 'extra'\n"
    make_zip(base, {"HoloCore/main.py": base_text})
    make_zip(patch, {"HoloCore/main.py": stale})
    proc = invoke(tmp, base, [patch], "out_larger")
    require(proc.returncode != 0, "larger stale protected update should require review")
    text = (tmp / "out_larger" / "main.py").read_text(encoding="utf-8")
    require("vertical strata + ocean space" in text, text)
    require("old vessel only" not in text, text)
    require("def new_button" in text, text)
    require((tmp / "out_larger" / "_pass_overrides" / "patch_larger" / "main.py").exists(), "override missing for larger stale protected file")


def test_line_ending_diff_rescue(tmp: Path) -> None:
    base = tmp / "base_crlf.zip"
    patch = tmp / "patch_crlf.zip"
    diff = tmp / "patch_crlf.diff"
    make_zip(base, {"HoloCore/main.py": "VALUE = 1\r\ndef answer():\r\n    return VALUE\r\n"})
    make_zip(patch, {"HoloCore/main.py": "VALUE = 2\ndef answer():\n    return VALUE\n"})
    diff.write_text("""--- HoloCore/main.py\n+++ HoloCore/main.py\n@@ -1,3 +1,3 @@\n-VALUE = 1\n+VALUE = 2\n def answer():\n     return VALUE\n""", encoding="utf-8")
    proc = invoke(tmp, base, [patch], "out_crlf")
    require(proc.returncode == 0, proc.stdout)
    text = (tmp / "out_crlf" / "main.py").read_text(encoding="utf-8")
    require("VALUE = 2" in text, text)
    report = (tmp / "out_crlf_reports" / "pass_combiner_report.md").read_text(encoding="utf-8")
    require("line-ending-normalized" in report or "normal patch" in report, report)


def test_small_update_override_option(tmp: Path) -> None:
    base = tmp / "base_small.zip"
    patch = tmp / "patch_small.zip"
    make_zip(base, {"HoloCore/config/settings.json": "{\"mode\": \"integrated\", \"keep\": true}\n"})
    make_zip(patch, {"HoloCore/config/settings.json": "{\"mode\": \"candidate\"}\n"})
    proc = invoke(tmp, base, [patch], "out_small", ["--small-updates-to-overrides"])
    require(proc.returncode != 0, "small override should require review")
    text = (tmp / "out_small" / "config" / "settings.json").read_text(encoding="utf-8")
    require("integrated" in text and "candidate" not in text, text)
    require((tmp / "out_small" / "_pass_overrides" / "patch_small" / "config" / "settings.json").exists(), "small override missing")


def test_validator_failure_blocks_zip(tmp: Path) -> None:
    base = tmp / "base_val.zip"
    patch = tmp / "patch_val.zip"
    out_zip = tmp / "should_not_exist.zip"
    make_zip(base, {"HoloCore/main.py": "VALUE = 1\n"})
    make_zip(patch, {"HoloCore/assets/new_asset.txt": "ok\n"})
    proc = invoke(tmp, base, [patch], "out_val", ["--output-zip", str(out_zip), "--validate", f"{sys.executable} -c \"raise SystemExit(5)\""])
    require(proc.returncode != 0, "validator failure should fail")
    require(not out_zip.exists(), "zip should not be written on validator failure by default")
    report = (tmp / "out_val_reports" / "pass_combiner_report.md").read_text(encoding="utf-8")
    require("Final status: `failed`" in report, report)


def test_failed_diff_blocks_zip_when_requested(tmp: Path) -> None:
    base = tmp / "base_diff_fail.zip"
    patch = tmp / "patch_diff_fail.zip"
    diff = tmp / "patch_diff_fail.diff"
    out_zip = tmp / "bad_diff_output.zip"
    make_zip(base, {"HoloCore/main.py": "VALUE = 1\n"})
    make_zip(patch, {"HoloCore/assets/safe.txt": "new\n"})
    diff.write_text("""--- HoloCore/main.py\n+++ HoloCore/main.py\n@@ -10,1 +10,1 @@\n-DOES_NOT_EXIST\n+NOPE\n""", encoding="utf-8")
    proc = invoke(tmp, base, [patch], "out_diff_fail", ["--output-zip", str(out_zip), "--fail-on-diff-failure"])
    require(proc.returncode != 0, "failed diff should fail with --fail-on-diff-failure")
    require(not out_zip.exists(), "zip should not be written on failed diff with strict flag")
    require((tmp / "out_diff_fail" / "assets" / "safe.txt").exists(), "safe nonprotected overlay may still be present in work tree for review")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pass_combiner_v3_selftest_") as td:
        tmp = Path(td)
        tests = [
            test_protected_additive_override,
            test_larger_stale_protected_blocks,
            test_line_ending_diff_rescue,
            test_small_update_override_option,
            test_validator_failure_blocks_zip,
            test_failed_diff_blocks_zip_when_requested,
        ]
        for test in tests:
            print(f"running {test.__name__}", flush=True)
            test(tmp)
            print(f"passed {test.__name__}", flush=True)
    print("selftest v3 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
