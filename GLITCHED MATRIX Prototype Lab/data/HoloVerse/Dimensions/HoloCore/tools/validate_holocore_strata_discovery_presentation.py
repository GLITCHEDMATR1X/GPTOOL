"""Validate uncluttered vertical-strata discovery/presentation polish."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "main.py").read_text(encoding="utf-8")
errors: list[str] = []

required_main_tokens = (
    "_setup_holocore_layer_notice",
    "_show_holocore_layer_notice",
    "_update_holocore_layer_notice",
    "_update_holocore_layer_discovery",
    "LAYER DISCOVERED",
    "LAYER SHIFT",
    "layer_notice_policy",
    "single temporary layer-discovery line only; no persistent HUD stack",
    "far_wake_shadow",
    "leviathan_expanse_far_wake_shadow",
)
for token in required_main_tokens:
    if token not in main:
        errors.append(f"missing-main-token:{token}")

if "self._update_holocore_layer_notice()" not in main:
    errors.append("layer-notice-not-updated-in-world-loop")
if "self._setup_holocore_layer_notice()" not in main:
    errors.append("layer-notice-not-created")
if main.count("OnscreenText(") > 5:
    errors.append("too-many-onscreen-text-widgets-for-uncluttered-pass")
if "layer_notice_visible" not in main or "layer_notice_text" not in main:
    errors.append("vertical-smoke-does-not-report-layer-notice-state")
if "discovered_layers" not in main:
    errors.append("vertical-smoke-does-not-report-discovered-layers")

ambient_section = main[main.find("def _setup_leviathan_expanse_ambient"):main.find("def _update_leviathan_expanse_ambient")]
if ambient_section.count("far_wake_shadow") < 2:
    errors.append("far-wake-shadow-ambient-not-added")
if "ParticleEffect" in ambient_section or "loader.loadParticleEffect" in ambient_section:
    errors.append("ambient-section-uses-particle-effects")
update_section = main[main.find("def _update_vertical_strata_effects"):main.find("def _ascent_entity_key_for_spec")]
if "sync_around" in update_section:
    errors.append("vertical-strata-effects-still-trigger-chunk-sync")
if "self._update_holocore_layer_discovery(state)" not in update_section:
    errors.append("vertical-strata-update-does-not-drive-layer-discovery")

if errors:
    print("FAIL validate_holocore_strata_discovery_presentation")
    for err in errors:
        print(err)
    raise SystemExit(1)
print("PASS validate_holocore_strata_discovery_presentation")
