#!/usr/bin/env python3
"""Validate the merged-pass regression cleanup contract.

This catches the exact conflicts found in the Pass 76-88 combined stack:
missing Pass 78 lush-region validator, stale Vector Wars split-adapter source,
and cleaner blind spots for crash_reports/runtime junk.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


cleaner = (ROOT / "tools" / "clean_holoverse_source_export.py").read_text(encoding="utf-8", errors="replace")

require((ROOT / "tools" / "validate_lush_ring_regions_contract.py").exists(), "Pass 78 lush-region validator must be present")
require(not (ROOT / "Dimensions" / "Vector Wars" / "holoverse_native_adapter_base.py").exists(), "stale Vector Wars split-adapter base file must be removed")
require(not (ROOT / "Dimensions" / "Vector Wars" / "holoverse_native_adapter_wrapper.py").exists(), "stale Vector Wars wrapper file must be removed")
require("STALE_SOURCE_EXPORT_FILES" in cleaner, "source export cleaner must remove stale split-adapter files")

require(not (ROOT / "HoloCore" / "assets").exists(), "duplicate HoloCore/assets tree must stay removed; shared assets live under assets/holocore")
require("STALE_SOURCE_EXPORT_DIRS" in cleaner and "HoloCore/assets" in cleaner, "source export cleaner must remove stale duplicate HoloCore/assets tree")
require('"crash_reports"' in cleaner and "DIAGNOSTIC_DIR_NAMES" in cleaner, "source export cleaner must clean crash_reports as diagnostics")
require("empty-diagnostic-dir" in cleaner, "source export cleaner must remove empty diagnostic dirs")

gleebs_validator = (ROOT / "tools" / "validate_gleebs_red_lore_contract.py").read_text(encoding="utf-8", errors="replace")
require("DATABASE_DIALOGUE_CANDIDATES" in gleebs_validator, "Gleebs validator must support optional app-level database dialogue mirrors")
require("database-gleebs-dialogue-mirror-not-present-in-this-source-export" in gleebs_validator, "missing database dialogue mirror should warn for source exports, not fail")

if errors:
    print("pass89-regression-cleanup: FAIL")
    for error in errors:
        print(f" - {error}")
    raise SystemExit(1)
print("pass89-regression-cleanup: PASS")
