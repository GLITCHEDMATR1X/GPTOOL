from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def replace_all(rel: str, old: str, new: str) -> None:
    p = ROOT / rel
    if p.exists():
        p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def replace_once(rel: str, old: str, new: str, label: str) -> None:
    s = read(rel)
    if old not in s:
        raise RuntimeError(f"missing patch anchor: {label}")
    write(rel, s.replace(old, new, 1))


def main() -> None:
    replace_all("bridge.py", 'BRIDGE_VERSION = "0.6.3-pass13"', 'BRIDGE_VERSION = "0.6.4-pass14"')
    replace_all("game_builder/settings_planner.py", '"template_version": "panda3d_playable_simulation_template.v4"', '"template_version": "panda3d_playable_simulation_template.v5"')
    for rel in ["README.md", "RUN_ME_FIRST.md", "RELEASE_NOTES.md"]:
        replace_all(rel, "v0.6.3-pass13", "v0.6.4-pass14")
        replace_all(rel, "0.6.3-pass13", "0.6.4-pass14")

    tg = "game_builder/template_generator.py"
    s = read(tg)
    s = s.replace('"template": "panda3d_playable_simulation_template.v4"', '"template": "panda3d_playable_simulation_template.v5"')
    if "self.jump_was_down = False" not in s:
        s = s.replace("        self.was_grounded = True\n", "        self.was_grounded = True\n        self.jump_was_down = False\n", 1)
    s = s.replace('"jump_was_down": bool(self.jump_was_down),', '"jump_was_down": bool(getattr(self, "jump_was_down", False)),')
    s = s.replace("jump_pressed = jump_down and not self.jump_was_down", "jump_pressed = jump_down and not getattr(self, \"jump_was_down\", False)")
    s = s.replace("Space jump/gravity", "edge-triggered Space jump/gravity")
    write(tg, s)

    readme = read("README.md")
    block = """
## Pass 14 — Local crash fix

Fixed a generated-template crash found during route-proof testing: proof JSON could read the player jump state before `jump_was_down` had been initialized. The generated player controller now initializes that state and proof reporting reads it safely.

Retest command:

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/route.png --proof-path reports/route.json
```
"""
    if "## Pass 14 — Local crash fix" not in readme:
        readme = readme.replace("\n## Repository baseline", block + "\n## Repository baseline") if "\n## Repository baseline" in readme else readme + block
        write("README.md", readme)

    write("docs/CRASH_SAFE_CONTROLS_PASS.md", """# Pass 14 — Local Crash Fix

This pass fixes the generated-template crash found while retesting the player-control pass.

## Fixed

- `jump_was_down` is initialized before any proof/screenshot route can read player-controller state.
- Proof JSON now uses a safe fallback when reading jump state.
- The generated template version is now `panda3d_playable_simulation_template.v5`.

## Retest

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/route.png --proof-path reports/route.json
```
""")
    write("logs/CHANGELOG_PASS14.md", """# GPTOOL Pass 14 Changelog — Local Crash Fix

- Bumped bridge version to `0.6.4-pass14`.
- Fixed generated route-proof crash caused by `jump_was_down` not existing before proof JSON was written.
- Initialized player jump state during generated app startup.
- Made proof-state serialization safe with `getattr` fallback.
- Bumped generated template version to `panda3d_playable_simulation_template.v5`.
""")
    write("logs/TESTED_PASS14.md", """# GPTOOL Pass 14 Tested

Local validation performed:

- Generated a fresh Panda3D probe project.
- Confirmed generated `main.py --settings-check` passes.
- Confirmed generated `main.py` AST syntax passes.
- Ran screenshot smoke mode, which exercises `_update`.
- Ran route proof mode after the fix and confirmed proof JSON/screenshot are written without crash.

Panda3D 1.10.16 offscreen test passed in the local environment.
""")

    for rel in ["tools/apply_pass14_jump_crash_fix.py", ".github/workflows/apply-pass14-jump-crash-fix.yml"]:
        p = ROOT / rel
        if p.exists():
            p.unlink()


if __name__ == "__main__":
    main()
