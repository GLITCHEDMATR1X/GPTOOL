from __future__ import annotations

from pathlib import Path
from typing import Any


class BrainGenerationBridge:
    """Disabled bridge stub.

    Game/event generation, donor blending, salvage scanning, and generated runtime
    creation were isolated from this build. MXOS remains available separately as
    the only GX-Machine app lane in the main app.
    """

    disabled_reason = "Game generation and salvage lanes are isolated from this build; MXOS remains available."

    def __init__(self, host: Any, config: dict[str, Any] | None = None):
        self.host = host
        self.config = dict(config or {})
        self.source_profile_records: list[dict] = []

    def _set_status(self, note: str | None = None) -> None:
        note = note or self.disabled_reason
        for attr in ("generation_status_var", "generation_variant_note_var"):
            try:
                var = getattr(self.host, attr, None)
                if var is not None:
                    var.set(note)
            except Exception:
                pass

    def _load_source_profile_overrides(self) -> dict[str, dict]:
        return {}

    def _ensure_source_profile_override_template(self) -> None:
        return None

    def _load_cached_source_profiles(self) -> list[dict]:
        return []

    def _save_source_profiles_cache(self, records: list[dict]) -> None:
        return None

    def _generation_standards_snapshot(self) -> dict:
        return {
            "source": "disabled",
            "files": [],
            "required_baseline": [],
            "mechanics": [],
            "status": self.disabled_reason,
        }

    def _external_root_pool_name(self, root: Path) -> str:
        try:
            return Path(root).name.strip().lower().replace(" ", "_") or "unknown"
        except Exception:
            return "unknown"

    def _generation_source_pool_allowed(self, pool_name: str) -> bool:
        return False

    def _embedded_source_metadata(self, root: Path) -> dict:
        return {}

    def _profile_record_from_live_dir(self, root: Path, source_pool: str) -> dict | None:
        return None

    def _scan_live_arcade_profiles(self) -> list[dict]:
        return []

    def _scan_arcade_zip_profiles(self) -> list[dict]:
        return []

    def _scan_minigame_profiles(self) -> list[dict]:
        return []

    def refresh_generation_source_profiles(self, force: bool = False) -> list[dict]:
        try:
            self.host.source_profile_records = []
        except Exception:
            pass
        self._set_status("Generation source scanning disabled; MXOS remains available.")
        return []

    def _records_for_generation_filter(self) -> list[dict]:
        return []

    def _resolve_requested_generation_profile(self, prompt: str) -> str:
        return "disabled"

    def _choose_gamegen_variant(self, prompt: str, requested_profile: str | None = None) -> str:
        return "disabled"

    def _generation_standardization_law(self) -> str:
        return self.disabled_reason

    def _select_generation_source_blend(self, prompt: str, variant: str, requested_profile: str | None = None, limit: int = 4) -> list[dict]:
        return []

    def _select_generation_source_game(self, prompt: str, variant: str, requested_profile: str | None = None) -> dict:
        return {}

    def _derive_generation_blend_directives(self, variant: str, source_game: dict, source_blend: list[dict], standards_snapshot: dict) -> dict:
        return {"status": "disabled"}

    def _apply_blend_directives_to_spec(self, spec: dict, blend_directives: dict) -> dict:
        spec = dict(spec or {})
        spec["generation_status"] = "disabled"
        return spec

    def _build_gamegen_event_spec(self, prompt: str, creator: str, variant: str, title: str, palette: dict, source_game: dict, source_blend: list[dict], standards_snapshot: dict) -> dict:
        return {
            "title": title or "Generation Disabled",
            "prompt": prompt,
            "creator": creator,
            "variant": "disabled",
            "generation_status": "disabled",
            "note": self.disabled_reason,
        }

    def create_generated_game_event(self, prompt: str, creator: str = "AI", variant: str | None = None, requested_profile: str | None = None):
        self._set_status("Game generation is isolated from this build. Open MXOS or the isolated archive for tool work.")
        try:
            self.host._append_chat("System", "Game generation is isolated from this build. MXOS remains available.")
        except Exception:
            pass
        return None
