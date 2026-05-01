from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.7.0-pass17-fauna-preview"

FAUNA = [
    ("hill_ridgeback_grazer", "Ridgeback Grazer", "GREEN HILLS", "Nyx", "quadruped", [0.34, 0.82, 0.24, 1], [0.96, 0.92, 0.32, 1], "arched ridge plates; grown herd animal; replaces egg-like hill placeholders"),
    ("forest_vanta_moss_stag", "Moss Stag", "FORESTS", "Vanta", "quadruped", [0.12, 0.58, 0.24, 1], [0.62, 1.0, 0.42, 1], "branch antlers; mossy back; slow forest forager"),
    ("mushroom_solace_glowback", "Glowback", "MUSHROOM", "Solace", "amphibian", [0.86, 0.18, 0.74, 1], [0.12, 1.0, 1.0, 1], "bioluminescent back nodes; low amphibian stance; spore-friendly"),
    ("desert_ember_sandrunner", "Sandrunner", "DESERT", "Ember", "lizard", [0.86, 0.52, 0.16, 1], [1.0, 0.2, 0.08, 1], "long tail; low dune runner; heat accent plates"),
    ("ice_mirror_crystal_fox", "Crystal Fox", "ICE", "Mirror", "fox", [0.58, 0.9, 1.0, 1], [0.95, 1.0, 1.0, 1], "angular ears; crystal tail; bright ice silhouette"),
    ("urban_sable_ash_raven", "Ash Raven", "URBAN", "Sable", "bird", [0.24, 0.25, 0.28, 1], [1.0, 0.18, 0.18, 1], "folded wings; red eye glint; non-robot urban scavenger"),
    ("water_solace_reef_glider", "Reef Glider", "WATER", "Solace", "manta", [0.08, 0.48, 0.92, 1], [0.0, 1.0, 0.82, 1], "wide fins; soft swim-wave motion; underwater tint target"),
    ("metro_archivist_sky_moth", "Sky Moth", "METROPOLIS", "Archivist", "flying_insect", [0.56, 0.24, 0.92, 1], [0.38, 0.88, 1.0, 1], "glass wings; city light pollinator; separate from robot selector"),
]


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def _fauna_items(region: str | None = None, species: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    wanted = {_slug(s) for s in (species or "").split(",") if s.strip()}
    out = []
    for fid, name, home, bot, body, color, accent, traits in FAUNA:
        if region and region.lower() not in home.lower():
            continue
        if wanted and _slug(fid) not in wanted and _slug(name) not in wanted:
            continue
        out.append({
            "id": fid,
            "name": name,
            "region": home,
            "bot": bot,
            "body": body,
            "color": color,
            "accent": accent,
            "traits": [t.strip() for t in traits.split(";")],
            "preview_status": "candidate",
        })
    return out[:limit] if limit and limit > 0 else out


def _write(path: Path, text: str, force: bool) -> dict[str, Any]:
    if path.exists() and not force:
        return {"path": str(path), "written": False, "reason": "exists"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "written": True}


def _write_json(path: Path, obj: Any, force: bool) -> dict[str, Any]:
    return _write(path, json.dumps(obj, indent=2) + "\n", force)


def _settings(command: str, fauna: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "holoverse_fauna_preview_settings.v1",
        "tool_version": TOOL_VERSION,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_command": command,
        "preview_policy": {
            "preview_only": True,
            "modifies_main_holoverse": False,
            "promotion_required": True,
            "protected_routes": ["Urban/Sable", "Metropolis/Archivist", "points-ui", "esc-exit", "screenshots"],
        },
        "art_direction": {
            "style": "procedural neon fauna maquette",
            "avoid": ["egg-like placeholders", "random clutter", "direct main-project edits"],
        },
        "fauna": fauna,
    }


def _main_py() -> str:
    return r'''from __future__ import annotations

import json, math, os, platform, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETTINGS = BASE / "settings" / "fauna_preview_settings.json"


def read_settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def arg_value(flag: str, default: str) -> str:
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else default


def settings_check() -> int:
    data = read_settings()
    fauna = data.get("fauna", [])
    print(f"Fauna preview settings OK: species={len(fauna)} preview_only={data.get('preview_policy', {}).get('preview_only')}")
    return 0 if fauna else 1


if "--settings-check" in sys.argv:
    raise SystemExit(settings_check())

SHOT = "--screenshot-mode" in sys.argv
SHOT_PATH = arg_value("--screenshot-path", str(BASE / "screenshots" / "fauna_preview.png"))
PROOF_PATH = arg_value("--proof-path", str(BASE / "reports" / "fauna_preview_scene_proof.json"))
if SHOT:
    os.environ.setdefault("GPT_BRIDGE_WINDOW_TYPE", "offscreen")

try:
    from direct.showbase.ShowBase import ShowBase
    from direct.task import Task
    from panda3d.core import AmbientLight, CardMaker, DirectionalLight, Filename, LineSegs, NodePath, TextNode, Vec3, loadPrcFileData
except Exception as exc:
    print("Panda3D is required: python -m pip install panda3d", file=sys.stderr)
    print(f"Import error: {exc}", file=sys.stderr)
    raise SystemExit(1)

if os.environ.get("GPT_BRIDGE_WINDOW_TYPE") == "offscreen":
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "load-display p3tinydisplay")
loadPrcFileData("", "audio-library-name null")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "window-title HoloVerse Fauna Preview")


class App(ShowBase):
    def __init__(self):
        super().__init__(windowType="offscreen" if os.environ.get("GPT_BRIDGE_WINDOW_TYPE") == "offscreen" else None)
        self.disableMouse()
        self.data = read_settings()
        self.fauna = self.data.get("fauna", [])
        self.nodes = []
        self.yaw, self.dist, self.target_dist = 0.0, 31.0, 31.0
        self.focus = Vec3(0, 0, 2)
        self.keys = {}
        self.setBackgroundColor(0.01, 0.02, 0.03, 1)
        self._controls(); self._lights(); self._grid(); self._lineup()
        self.taskMgr.add(self._tick, "fauna_preview_tick")
        if SHOT:
            self.taskMgr.doMethodLater(1.1, self._capture, "fauna_preview_capture")

    def _controls(self):
        for k in ["w", "a", "s", "d", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "q", "e"]:
            self.accept(k, self.keys.__setitem__, [k, True]); self.accept(k + "-up", self.keys.__setitem__, [k, False])
        self.accept("wheel_up", self._zoom, [-2]); self.accept("wheel_down", self._zoom, [2]); self.accept("escape", sys.exit)

    def _zoom(self, d): self.target_dist = max(13, min(55, self.target_dist + d))

    def _lights(self):
        a = AmbientLight("ambient"); a.setColor((0.45, 0.52, 0.58, 1)); self.render.setLight(self.render.attachNewNode(a))
        d = DirectionalLight("key"); d.setColor((1, .96, .82, 1)); n = self.render.attachNewNode(d); n.setHpr(-35, -42, 0); self.render.setLight(n)
        r = DirectionalLight("cyan_rim"); r.setColor((.18, .58, .78, 1)); rn = self.render.attachNewNode(r); rn.setHpr(135, -20, 0); self.render.setLight(rn)

    def _shape(self, name="models/smiley"):
        for model in [name, "models/smiley", "models/box"]:
            try:
                n = self.loader.loadModel(model); n.setTwoSided(True); return n
            except Exception: pass
        cm = CardMaker("fallback"); cm.setFrame(-.5, .5, -.5, .5); return NodePath(cm.generate())

    def _grid(self):
        cm = CardMaker("floor"); cm.setFrame(-45, 45, -28, 28); f = self.render.attachNewNode(cm.generate()); f.setP(-90); f.setColor(.04, .05, .07, 1)
        seg = LineSegs(); seg.setThickness(1.2); seg.setColor(0, .82, 1, .35)
        for x in range(-44, 45, 4): seg.moveTo(x, -28, .03); seg.drawTo(x, 28, .03)
        for y in range(-28, 29, 4): seg.moveTo(-44, y, .03); seg.drawTo(44, y, .03)
        self.render.attachNewNode(seg.create())

    def _label(self, parent, text, pos, scale, color):
        node = TextNode("label"); node.setText(text); node.setAlign(TextNode.ACenter)
        np = parent.attachNewNode(node); np.setPos(*pos); np.setScale(scale); np.setHpr(0, -32, 0); np.setColor(*color)

    def _part(self, parent, model, name, pos, scale, color):
        n = self._shape(model); n.setName(name); n.reparentTo(parent); n.setPos(*pos); n.setScale(*scale); n.setColor(*color); return n

    def _lineup(self):
        self._label(self.render, "HOLOVERSE FAUNA PREVIEW // ASSETS FIRST", (0, -25, 7.5), .75, (0, .92, 1, 1))
        cols = 4 if len(self.fauna) <= 8 else 5
        for i, spec in enumerate(self.fauna):
            root = self.render.attachNewNode("fauna_" + spec["id"]); root.setPos((i % cols - (cols - 1) / 2) * 16, 9 - (i // cols) * 17, 0)
            c, a = spec["color"], spec["accent"]; body = spec.get("body", "quadruped")
            self._part(root, "models/smiley", "body", (0, 0, 1.25), (1.25, .65, .55), c)
            self._part(root, "models/smiley", "head", (1.05, 0, 1.45), (.45, .38, .38), c)
            tail = self._part(root, "models/box", "tail", (-1.15, 0, 1.15), (.75, .1, .12), a)
            legs = 0 if body == "manta" else 2 if body in {"bird", "flying_insect"} else 4
            for j in range(legs): self._part(root, "models/box", f"leg_{j}", ((-.45 if j < 2 else .45), (-.32 if j % 2 else .32), .42), (.11, .11, .42), c)
            if body in {"bird", "flying_insect", "manta"}:
                for s in [-1, 1]: self._part(root, "models/box", f"wing_{s}", (0, s * .9, 1.35), (.95, .14, .08), a)
            if body in {"quadruped", "fox"}:
                for s in [-1, 1]: self._part(root, "models/box", f"ear_{s}", (1.25, s * .23, 1.95), (.08, .08, .34), a)
            self._label(root, spec["name"], (0, -4.6, 2.25), .38, a)
            self._label(root, spec["region"], (0, -4.6, 1.65), .25, (.85, .92, 1, 1))
            self.nodes.append({"root": root, "tail": tail, "spec": spec, "base": root.getPos(), "index": i})

    def _proof(self):
        return {"schema_version": "holoverse_fauna_preview_proof.v1", "generated_at": datetime.now().isoformat(timespec="seconds"), "platform": platform.platform(), "preview_only": True, "modifies_main_holoverse": False, "creature_count": len(self.nodes), "creatures": [{"id": n["spec"]["id"], "name": n["spec"]["name"], "region": n["spec"]["region"], "bot": n["spec"]["bot"], "body": n["spec"].get("body")} for n in self.nodes]}

    def _capture(self, task):
        Path(PROOF_PATH).parent.mkdir(parents=True, exist_ok=True); Path(PROOF_PATH).write_text(json.dumps(self._proof(), indent=2) + "\n", encoding="utf-8")
        Path(SHOT_PATH).parent.mkdir(parents=True, exist_ok=True); self.graphicsEngine.renderFrame(); self.graphicsEngine.renderFrame(); self.win.saveScreenshot(Filename.fromOsSpecific(str(Path(SHOT_PATH).resolve())))
        print(f"FAUNA_PREVIEW_PROOF: {PROOF_PATH}"); print(f"FAUNA_PREVIEW_SCREENSHOT: {SHOT_PATH}"); raise SystemExit(0)

    def _tick(self, task):
        dt = globalClock.getDt(); speed = 12 * dt
        if self.keys.get("w") or self.keys.get("arrow_up"): self.focus.y += speed
        if self.keys.get("s") or self.keys.get("arrow_down"): self.focus.y -= speed
        if self.keys.get("a") or self.keys.get("arrow_left"): self.focus.x -= speed
        if self.keys.get("d") or self.keys.get("arrow_right"): self.focus.x += speed
        if self.keys.get("q"): self.yaw += 55 * dt
        if self.keys.get("e"): self.yaw -= 55 * dt
        self.dist += (self.target_dist - self.dist) * min(1, dt * 5)
        for n in self.nodes:
            t = task.time + n["index"]; n["root"].setZ(n["base"].z + math.sin(t * 1.5) * .08); n["root"].setH(math.sin(t * .35) * 5); n["tail"].setH(math.sin(t * 3) * 15)
        r = math.radians(self.yaw); self.camera.setPos(self.focus.x + math.sin(r) * self.dist, self.focus.y - math.cos(r) * self.dist, 9.5); self.camera.lookAt(self.focus + Vec3(0, 0, 2.2)); return Task.cont


if __name__ == "__main__":
    App().run()
'''


def _readme(data: dict[str, Any]) -> str:
    rows = "\n".join(f"- **{f['name']}** (`{f['id']}`) — {f['region']}: {', '.join(f['traits'])}" for f in data["fauna"])
    return f"""# HoloVerse Fauna Preview

Generated by GPTOOL `{TOOL_VERSION}`.

This is an isolated Panda3D preview folder for testing fauna silhouettes before anything is merged into the real HoloVerse.

## Policy

- Preview only: `{data['preview_policy']['preview_only']}`
- Main HoloVerse modified: `{data['preview_policy']['modifies_main_holoverse']}`
- Promotion required: `{data['preview_policy']['promotion_required']}`

## Fauna lineup

{rows}

## Run

```bash
python main.py --settings-check
python main.py --screenshot-mode --screenshot-path screenshots/fauna_preview.png --proof-path reports/fauna_preview_scene_proof.json
```

Do not copy this whole folder into HoloVerse. Promote only approved species definitions or asset ideas after screenshot review.
"""


def generate(output_dir: str | Path, *, command: str, region: str | None = None, species: str | None = None, limit: int | None = None, force: bool = False) -> dict[str, Any]:
    out = Path(output_dir).resolve()
    if out.exists() and force:
        shutil.rmtree(out)
    fauna = _fauna_items(region=region, species=species, limit=limit)
    data = _settings(command, fauna)
    writes = [
        _write(out / "main.py", _main_py(), force),
        _write_json(out / "settings" / "fauna_preview_settings.json", data, force),
        _write_json(out / "assets" / "fauna" / "fauna_manifest.json", {"schema_version": "holoverse_fauna_manifest.v1", "fauna": fauna}, force),
        _write(out / "README.md", _readme(data), force),
        _write(out / "VALIDATION_COMMANDS.txt", "python main.py --settings-check\npython main.py --screenshot-mode --screenshot-path screenshots/fauna_preview.png --proof-path reports/fauna_preview_scene_proof.json\n", force),
    ]
    for folder in ["screenshots", "reports", "logs"]:
        (out / folder).mkdir(parents=True, exist_ok=True)
    result = {"schema_version": "holoverse_fauna_preview_generation_result.v1", "tool_version": TOOL_VERSION, "ok": bool(fauna) and all(w.get("written") or w.get("reason") == "exists" for w in writes), "output_dir": str(out), "species_count": len(fauna), "species": [f["id"] for f in fauna], "entry": str(out / "main.py"), "settings": str(out / "settings" / "fauna_preview_settings.json"), "writes": writes}
    _write_json(out / "reports" / "preview_generation_result.json", result, True)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate an isolated Panda3D HoloVerse fauna preview.")
    p.add_argument("output_dir")
    p.add_argument("--command", default="prototype better HoloVerse fauna assets before promotion")
    p.add_argument("--region")
    p.add_argument("--species")
    p.add_argument("--limit", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    r = generate(a.output_dir, command=a.command, region=a.region, species=a.species, limit=a.limit, force=a.force)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"HoloVerse fauna preview: {'PASS' if r['ok'] else 'FAIL'}")
        print(f"Output: {r['output_dir']}")
        print(f"Species: {r['species_count']}")
        print("Next:")
        print("  cd " + r["output_dir"])
        print("  python main.py --settings-check")
        print("  python main.py --screenshot-mode --screenshot-path screenshots/fauna_preview.png --proof-path reports/fauna_preview_scene_proof.json")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
