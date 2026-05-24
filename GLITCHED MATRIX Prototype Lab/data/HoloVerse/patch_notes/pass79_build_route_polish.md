# Pass 79 build route polish

- Installed Vector Wars audio wrapper: `holoverse_native_adapter.py` now subclasses preserved base adapter and resolves committed Vector Wars assets.
- Preserved old Vector Wars adapter as `holoverse_native_adapter_base.py`.
- Updated Vector Wars audio profile to prefer dropped MP3 assets (`fire.mp3`, `rocketfire.mp3`, `hit.mp3`).
- Removed Holo Conquest root-level `generated_sfx`, `custom_sfx`, and `sfx_overrides` folders; generated fallback SFX now live under `assets/audio/sfx/generated`.
- Patched Holo Conquest `main.py` to stop creating cwd-relative SFX/override folders.
- Patched Gleebs dialogue rendering to one red visible text surface; cyan/blue glow text no longer duplicates the line.
- Updated stale Gleebs seed text from cyan/suspicious signal to red signal.
- Updated dimension index router to include native/same-window/in-world transition routes.
- Kept Etch-Line ESC/0 return behavior through the host native return path.
- Patched Holo Campaign custom/override SFX roots to stay under `assets/audio/sfx/...` instead of root-level folders.
- Moved native-mode ESC handling before Gleebs/bot dialogue dismissal so Etch-Line ESC can always return to HoloVerse.
- Seeded Zonez embedded SandboxApp with host `graphicsEngine`/`pipe` so its real loading/preload path can render inside the HoloVerse window.
- Updated Vector Wars wrapper status/toggle markers so presentation validator recognizes the installed adapter.
- Updated Zonez status to explicitly say GAME UI ALWAYS VISIBLE.
- Moved Holo Conquest crash reports under `logs/crash_reports` instead of cwd-relative `crash_reports`.
- Added `database/MatrixCore/gleebs_dialogue.json` copy so bundled and database dialogue lanes match.
- Repointed MatrixCore dialogue/progression/database lanes into the HoloVerse game folder to stop sibling `holoverse/` data duplication.
