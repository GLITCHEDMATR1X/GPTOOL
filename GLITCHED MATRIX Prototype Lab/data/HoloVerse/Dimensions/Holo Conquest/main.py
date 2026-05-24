
"""
HoloVerse RTS // isolated single-file prototype

This file intentionally replaces the oversized legacy HoloVerse main/world pair for
this RTS branch. It does not create assets, config, Dimensions, matrixcore,
progression, generated_audio, generated_textures, logs, or nested data folders.

Run:
    python world.py

Diagnostics:
    python world.py --self-test --auto-exit
    python world.py --self-test --auto-exit --overview --ui-mode clean --screenshot proof.png
"""

from __future__ import annotations

import math
import random
import sys
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SELF_TEST = "--self-test" in sys.argv
AUTO_EXIT = "--auto-exit" in sys.argv

def _arg_value(flag: str, default: str = "") -> str:
    try:
        idx = sys.argv.index(flag)
        return sys.argv[idx + 1]
    except Exception:
        return default

SCREENSHOT_PATH = _arg_value("--screenshot", "")
METROPOLIS_FOCUS = "--metropolis-focus" in sys.argv
OVERVIEW_SHOT = "--overview" in sys.argv
ENEMY_SHOWCASE = "--enemy-showcase" in sys.argv
ENEMY_FOCUS_SHOT = "--enemy-focus" in sys.argv
SOAK_TEST = "--soak-test" in sys.argv
NO_GLEEBS = "--no-gleebs" in sys.argv
PROGRESSION_TEST = "--progression-test" in sys.argv
INTELLIGENCE_TEST = "--intelligence-test" in sys.argv
PRIMARY_BOT_TEST = "--primary-bot-test" in sys.argv
ACTIVITY_LOG_TEST = "--activity-log-test" in sys.argv
CRASH_TEST = "--crash-test" in sys.argv
UI_START_MODE = _arg_value("--ui-mode", "clean").lower()

from panda3d.core import loadPrcFileData

prc = [
    "window-title HoloVerse RTS Isolated",
    "win-size 1600 900",
    "show-frame-rate-meter 0",
    "sync-video 1",
    "framebuffer-multisample 1",
    "multisamples 4",
    "textures-power-2 up",
    "notify-level-display warning",
    "notify-level-glgsg warning",
    "cursor-hidden 0",
    "audio-library-name null",
]
if SELF_TEST:
    prc += [
        "window-type offscreen",
        "load-display p3tinydisplay",
        "aux-display p3tinydisplay",
    ]
else:
    prc += ["window-type onscreen"]
loadPrcFileData("", "\n".join(prc))

from direct.gui.DirectGui import DirectLabel
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight,
    AntialiasAttrib,
    CardMaker,
    ClockObject,
    DirectionalLight,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    TextNode,
    TransparencyAttrib,
    Vec3,
    Vec4,
    WindowProperties,
)

VERSION = "0.48.0-rts-crash-guard"
GAME_NAME = "HoloVerse RTS // Core Defense"


CRASH_REPORT_PATH: Optional[Path] = None


def write_crash_report(exc: BaseException, context: str = "runtime", tb=None) -> Optional[Path]:
    """Best-effort crash report writer.

    The isolated RTS branch intentionally does not create logs or generated
    folders during normal play. This only creates crash_reports/ after an
    actual Python exception, so a crash is no longer silent for local testing.
    """
    global CRASH_REPORT_PATH
    try:
        root = Path.cwd() / "crash_reports"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = root / f"holoverse_rts_crash_{stamp}.txt"
        tb_text = "".join(traceback.format_exception(type(exc), exc, tb or getattr(exc, "__traceback__", None)))
        payload = (
            f"{GAME_NAME}\n"
            f"version={VERSION}\n"
            f"context={context}\n"
            f"argv={' '.join(sys.argv)}\n"
            f"cwd={Path.cwd()}\n\n"
            f"{tb_text}"
        )
        path.write_text(payload, encoding="utf-8")
        CRASH_REPORT_PATH = path
        print(f"crash_report={path}")
        return path
    except Exception as report_exc:
        print(f"crash_report_failed={report_exc}")
        return None


def install_crash_hook():
    def _hook(exc_type, exc, tb):
        write_crash_report(exc, "unhandled", tb)
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _hook

TAU = math.tau
WORLD_EXPANSION_SCALE = 3.10  # Pass 30: HoloVerse war table is 2x the pass 29 visual scale while sim math stays stable.
MAX_WORLD_BEAMS = 180
MAX_SPACE_BEAMS = 70
MAX_IMPACT_BURSTS = 70
MAX_AMBIENT_ACTIVITY_BEAMS = 36
GLEEBS_BACKDROP_DISTANCE = 1020.0
GLEEBS_BACKDROP_SCALE = 102.5  # Pass 30: half the pass 29 Gleebs backdrop size.
GLEEBS_BACKDROP_Z = 280.0  # Pass 34: raised high enough to stay visible above the enlarged war table.

# Pass 33: survival/RTS loop pacing. The board remains sandbox-readable, but
# the enemy pressure now arrives in waves with recovery windows and player
# command-energy decisions between pushes.
WAVE_ASSAULT_DURATION = 58.0
WAVE_RECOVERY_DURATION = 12.0
COMMAND_ENERGY_MAX = 100.0
COMMAND_REGEN_ASSAULT = 4.2
COMMAND_REGEN_RECOVERY = 7.5

# Pass 34: wave doctrines make the assault loop less generic. Each wave
# still obeys the same ring rules, but the enemy army now telegraphs a
# dominant tactic so player commands matter more.
WAVE_DOCTRINES = (
    ("Balanced Probe", "enemy_scout"),
    ("Sapper Fleet", "enemy_sapper"),
    ("Hacker Surge", "enemy_hacker"),
    ("Siege Push", "enemy_siege"),
    ("Commander Guard", "enemy_commander"),
    ("Brute Raid", "enemy_brute"),
    ("Shield Wall", "enemy_shield"),
    ("Carrier Swarm", "enemy_carrier"),
    ("Harvester Raid", "enemy_harvester"),
    ("Phantom Breach", "enemy_phantom"),
)

# Pass 35: readable RTS loop. Doctrines now expose simple player-facing
# objectives, and every helper command has a cooldown so command decisions
# matter instead of becoming constant button spam.
WAVE_OBJECTIVES = {
    "Balanced Probe": "hold Urban and watch the whole route",
    "Sapper Fleet": "stop vessel builders before Water",
    "Hacker Surge": "protect defenders from hack beams",
    "Siege Push": "shield Forest supply and artifacts",
    "Commander Guard": "break commander squads early",
    "Brute Raid": "slow the direct inward crush",
    "Shield Wall": "break shield escorts before Desert lasers are blunted",
    "Carrier Swarm": "destroy carriers before scouts multiply",
    "Harvester Raid": "protect Forest/Mushroom energy from harvesters",
    "Phantom Breach": "watch for fast bypass units slipping through traps",
}
COMMAND_COOLDOWNS = {
    "urban_rally": 18.0,
    "desert_overcharge": 24.0,
    "spore_bloom": 22.0,
    "forest_surge": 26.0,
    "core_repair": 32.0,
    "bot_overdrive": 42.0,
}
COMMAND_KEYS = {
    "urban_rally": "1",
    "desert_overcharge": "2",
    "spore_bloom": "3",
    "forest_surge": "4",
    "core_repair": "5",
    "bot_overdrive": "6",
}


# Pass 37: turn the simulation into a clearer survival game loop. Score,
# combo, run rank, and automatic region upgrades make each wave completion
# feel like progress while preserving the single-file RTS board.
SCORE_BY_ENEMY = {
    "enemy_scout": 8,
    "enemy_sapper": 13,
    "enemy_hacker": 17,
    "enemy_brute": 18,
    "enemy_siege": 26,
    "enemy_commander": 34,
    "enemy_shield": 22,
    "enemy_carrier": 30,
    "enemy_harvester": 24,
    "enemy_phantom": 28,
}
CORE_RANK_SCORE_STEP = 320
MAX_UPGRADE_LEVEL = 5
UPGRADE_ORDER = ("urban", "desert", "mushroom", "forest", "core")
UPGRADE_LABELS = {
    "urban": "Urban Armor Grid",
    "desert": "Desert Capacitors",
    "mushroom": "Spore Network",
    "forest": "Forest Root Supply",
    "core": "Core Shield Matrix",
}
DOCTRINE_COUNTER_UPGRADE = {
    "Balanced Probe": "urban",
    "Sapper Fleet": "desert",
    "Hacker Surge": "core",
    "Siege Push": "forest",
    "Commander Guard": "urban",
    "Brute Raid": "mushroom",
    "Shield Wall": "desert",
    "Carrier Swarm": "urban",
    "Harvester Raid": "forest",
    "Phantom Breach": "core",
}
COMMAND_UI = {
    "urban_rally": ("Urban Rally", 24.0),
    "desert_overcharge": ("Desert Lasers", 30.0),
    "spore_bloom": ("Spore Bloom", 26.0),
    "forest_surge": ("Forest Surge", 28.0),
    "core_repair": ("Core Repair", 34.0),
    "bot_overdrive": ("Bot Overdrive", 44.0),
}
UI_MODES = ("clean", "compact", "tactical", "minimal", "hidden")


def script_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def find_gleebs_texture() -> Optional[Path]:
    # Primary requested location plus common project/package fallbacks.
    bases = [Path.cwd(), script_dir()]
    candidates = []
    for base in bases:
        candidates.extend([
            base / "assets" / "textures" / "gleebs.png",
            base / "data" / "assets" / "textures" / "gleebs.png",
            base / "textures" / "gleebs.png",
        ])
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            return path
    return None

# Strategic ring layout, from core outward. These names are RTS gameplay roles,
# not old dimension launchers.
RINGS = {
    "CORE":       {"inner": 0.0,  "outer": 3.2,  "color": (0.06, 0.10, 0.14, 1.0), "purpose": "HUB"},
    "FLAT":       {"inner": 3.2,  "outer": 6.0,  "color": (0.78, 0.86, 0.92, 0.55), "purpose": "ARTIFACT DEFENSE"},
    "FOREST":     {"inner": 6.0,  "outer": 11.0, "color": (0.04, 0.42, 0.16, 0.62), "purpose": "SUPPLY"},
    "HILLS":      {"inner": 11.0, "outer": 16.0, "color": (0.48, 0.78, 0.12, 0.58), "purpose": "WILDLIFE"},
    "MUSHROOM":   {"inner": 16.0, "outer": 21.0, "color": (0.56, 0.11, 0.64, 0.60), "purpose": "CONFUSION"},
    "DESERT":     {"inner": 21.0, "outer": 26.0, "color": (0.86, 0.47, 0.12, 0.62), "purpose": "PYRAMID LASERS"},
    "WATER":      {"inner": 26.0, "outer": 31.0, "color": (0.06, 0.45, 0.82, 0.66), "purpose": "VESSEL BARRIER"},
    "URBAN":      {"inner": 31.0, "outer": 36.0, "color": (0.24, 0.27, 0.31, 0.70), "purpose": "ARMY FRONT"},
    "METROPOLIS": {"inner": 36.0, "outer": 42.0, "color": (0.60, 0.16, 0.86, 0.62), "purpose": "ENEMY SOURCE"},
}

# Pass 45/46: clicked-region activity log. This remains UI-only/session-only:
# no save files, no logs folder, and no old project shell. It summarizes what
# happened in the selected ring using player-facing language.
ACTIVITY_LOG_LIMIT = 7
REGION_ACTIVITY_ORDER = ("CORE", "FLAT", "FOREST", "HILLS", "MUSHROOM", "DESERT", "WATER", "URBAN", "METROPOLIS")
DAMAGE_SOURCE_LABELS = {
    "urban": "Urban robots",
    "desert": "Desert troops",
    "mushroom": "Mushroom troops",
    "hills": "Hills caretakers",
    "wildlife": "Wildlife",
    "laser": "Desert pyramids",
    "spore": "Mushroom spores",
    "core": "Primary bots",
    "reflect": "Mirror ward",
    "confused": "Confused fire",
    "direct": "Defenders",
}


BOT_NAMES = ["IO", "Vanta", "Nyx", "Solace", "Ember", "Mirror", "Sable", "Archivist"]
BOT_COLORS = {
    "IO": (0.78, 0.96, 1.00, 1), "Vanta": (0.10, 1.00, 0.34, 1),
    "Nyx": (0.80, 0.62, 1.00, 1), "Solace": (1.00, 0.25, 0.90, 1),
    "Ember": (1.00, 0.52, 0.14, 1), "Mirror": (0.62, 0.92, 1.00, 1),
    "Sable": (1.00, 0.14, 0.20, 1), "Archivist": (0.42, 0.68, 1.00, 1),
}

# Pass 42: primary bot role table. These named defenders now have clear
# strengths, abilities, and weaknesses against the adaptive Metropolis classes.
BOT_TRAITS = {
    "IO": {"role": "Hub orbit sentry", "ability": "Orbit Chain", "strength": "fast intercept chains", "weakness": "heavy shields", "range": 9.6, "damage": 0.150, "cooldown": 0.31, "speed": 1.18, "strong_vs": ("enemy_scout", "enemy_phantom"), "weak_vs": ("enemy_brute", "enemy_shield"), "effect": "intercept"},
    "Vanta": {"role": "Forest root guardian", "ability": "Root Grove", "strength": "harvest/sapper lockdown", "weakness": "siege range", "range": 6.7, "damage": 0.068, "cooldown": 0.88, "speed": 0.98, "strong_vs": ("enemy_harvester", "enemy_sapper"), "weak_vs": ("enemy_siege",), "effect": "root"},
    "Nyx": {"role": "Wildlife war-beast", "ability": "Pack Howl", "strength": "brutes/carriers", "weakness": "hacking", "range": 6.1, "damage": 0.116, "cooldown": 0.78, "speed": 1.10, "strong_vs": ("enemy_brute", "enemy_carrier"), "weak_vs": ("enemy_hacker",), "effect": "pounce"},
    "Solace": {"role": "Spore oracle", "ability": "Dream Spores", "strength": "command/hacker disruption", "weakness": "phantoms", "range": 7.0, "damage": 0.054, "cooldown": 1.06, "speed": 0.92, "strong_vs": ("enemy_hacker", "enemy_commander"), "weak_vs": ("enemy_phantom",), "effect": "daze"},
    "Ember": {"role": "Pyramid fire marshal", "ability": "Pyramid Overdrive", "strength": "shield/siege armor", "weakness": "water sappers", "range": 7.5, "damage": 0.122, "cooldown": 0.88, "speed": 0.96, "strong_vs": ("enemy_shield", "enemy_siege"), "weak_vs": ("enemy_sapper",), "effect": "lance"},
    "Mirror": {"role": "Artifact reflector", "ability": "Prism Ward", "strength": "siege/hack reflection", "weakness": "brute crush", "range": 6.9, "damage": 0.072, "cooldown": 0.92, "speed": 0.90, "strong_vs": ("enemy_siege", "enemy_hacker"), "weak_vs": ("enemy_brute",), "effect": "reflect"},
    "Sable": {"role": "Urban rail defender", "ability": "Killbox Rail", "strength": "brutes/commanders", "weakness": "phantom flanks", "range": 7.8, "damage": 0.130, "cooldown": 0.76, "speed": 0.94, "strong_vs": ("enemy_brute", "enemy_commander"), "weak_vs": ("enemy_phantom",), "effect": "rail"},
    "Archivist": {"role": "Tactical scanner", "ability": "Data Uplink", "strength": "revealing phantoms/carriers", "weakness": "heavy armor", "range": 8.4, "damage": 0.050, "cooldown": 0.70, "speed": 0.88, "strong_vs": ("enemy_phantom", "enemy_carrier"), "weak_vs": ("enemy_brute", "enemy_shield"), "effect": "mark"},
}


# Pass 44: paired primary-bot powers. These do not replace the individual
# powers from Pass 43; they reward close timing by forming readable defensive
# combos that connect named bots to actual regional tactics.
BOT_SYNERGIES = {
    "orbit_killbox": {"pair": ("IO", "Sable"), "label": "Orbit Killbox", "color": (0.78, 1.0, 1.0, 0.58), "cooldown": 8.0},
    "grove_pack": {"pair": ("Vanta", "Nyx"), "label": "Grove Pack", "color": (0.36, 1.0, 0.30, 0.52), "cooldown": 9.0},
    "dream_uplink": {"pair": ("Solace", "Archivist"), "label": "Dream Uplink", "color": (0.92, 0.38, 1.0, 0.54), "cooldown": 9.5},
    "sun_prism": {"pair": ("Ember", "Mirror"), "label": "Sun Prism", "color": (1.0, 0.80, 0.24, 0.54), "cooldown": 10.0},
}
BOT_SYNERGY_WINDOW = 7.5



# Pass 17: every named defender and enemy class gets a distinct generated
# miniature silhouette. These are still geometry-only, with no asset folders.
BOT_MARKER_KIND = {
    "IO": "bot_io",
    "Vanta": "bot_vanta",
    "Nyx": "bot_nyx",
    "Solace": "bot_solace",
    "Ember": "bot_ember",
    "Mirror": "bot_mirror",
    "Sable": "bot_sable",
    "Archivist": "bot_archivist",
}
ENEMY_VARIANTS = (
    "enemy_scout", "enemy_brute", "enemy_hacker", "enemy_sapper", "enemy_siege", "enemy_commander",
    "enemy_shield", "enemy_carrier", "enemy_harvester", "enemy_phantom",
)
ENEMY_TRAITS = {
    "enemy_scout": {"hp": 0.82, "speed": 1.52, "size": 0.25, "color": (1.0, 0.14, 0.18, 0.96), "damage": 0.85, "label": "SCOUT"},
    "enemy_brute": {"hp": 1.68, "speed": 0.92, "size": 0.34, "color": (1.0, 0.08, 0.05, 0.98), "damage": 1.42, "label": "BRUTE"},
    "enemy_hacker": {"hp": 1.02, "speed": 1.18, "size": 0.30, "color": (1.0, 0.06, 0.62, 0.96), "damage": 0.75, "label": "HACKER"},
    "enemy_sapper": {"hp": 0.94, "speed": 1.33, "size": 0.28, "color": (1.0, 0.42, 0.10, 0.96), "damage": 1.15, "label": "SAPPER"},
    "enemy_siege": {"hp": 1.42, "speed": 0.82, "size": 0.36, "color": (0.86, 0.12, 1.0, 0.96), "damage": 1.30, "label": "SIEGE"},
    "enemy_commander": {"hp": 1.24, "speed": 1.05, "size": 0.32, "color": (1.0, 0.78, 0.18, 0.98), "damage": 0.92, "label": "COMMAND"},
    "enemy_shield": {"hp": 1.55, "speed": 0.98, "size": 0.33, "color": (0.42, 0.72, 1.0, 0.97), "damage": 0.78, "label": "SHIELD"},
    "enemy_carrier": {"hp": 1.35, "speed": 0.88, "size": 0.38, "color": (1.0, 0.34, 0.70, 0.96), "damage": 0.62, "label": "CARRIER"},
    "enemy_harvester": {"hp": 1.12, "speed": 1.14, "size": 0.31, "color": (0.64, 1.0, 0.16, 0.96), "damage": 1.05, "label": "HARVEST"},
    "enemy_phantom": {"hp": 0.86, "speed": 1.66, "size": 0.27, "color": (0.52, 0.18, 1.0, 0.78), "damage": 0.92, "label": "PHANTOM"},
}
ENEMY_SQUADS = {
    "enemy_scout": ("enemy_scout", "enemy_scout", "enemy_sapper"),
    "enemy_brute": ("enemy_brute", "enemy_scout", "enemy_scout"),
    "enemy_hacker": ("enemy_hacker", "enemy_scout", "enemy_sapper"),
    "enemy_sapper": ("enemy_sapper", "enemy_sapper", "enemy_scout"),
    "enemy_siege": ("enemy_siege", "enemy_brute", "enemy_hacker", "enemy_scout"),
    "enemy_commander": ("enemy_commander", "enemy_brute", "enemy_hacker", "enemy_sapper"),
    "enemy_shield": ("enemy_shield", "enemy_brute", "enemy_sapper", "enemy_scout"),
    "enemy_carrier": ("enemy_carrier", "enemy_scout", "enemy_scout", "enemy_hacker"),
    "enemy_harvester": ("enemy_harvester", "enemy_sapper", "enemy_hacker", "enemy_scout"),
    "enemy_phantom": ("enemy_phantom", "enemy_phantom", "enemy_hacker"),
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def angle_to_pos(angle: float, radius: float, z: float = 0.05) -> Vec3:
    return Vec3(math.cos(angle) * radius, math.sin(angle) * radius, z)


def pos_angle(pos: Vec3) -> float:
    return math.atan2(pos.y, pos.x)


def pos_radius(pos: Vec3) -> float:
    return math.sqrt(pos.x * pos.x + pos.y * pos.y)


def set_radius(pos: Vec3, radius: float) -> Vec3:
    a = pos_angle(pos)
    return angle_to_pos(a, radius, pos.z)


def distance(a: Vec3, b: Vec3) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def flat_direction(a: Vec3, b: Vec3) -> Vec3:
    d = Vec3(b.x - a.x, b.y - a.y, 0.0)
    if d.lengthSquared() > 0.0001:
        d.normalize()
    return d


def make_disc(name: str, radius: float, segments: int = 96) -> NodePath:
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    vw.addData3f(0, 0, 0)
    for i in range(segments):
        a = TAU * i / segments
        vw.addData3f(math.cos(a) * radius, math.sin(a) * radius, 0)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        tris.addVertices(0, i + 1, 1 + ((i + 1) % segments))
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_annulus(name: str, inner: float, outer: float, segments: int = 144) -> NodePath:
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    for i in range(segments):
        a = TAU * i / segments
        vw.addData3f(math.cos(a) * inner, math.sin(a) * inner, 0)
        vw.addData3f(math.cos(a) * outer, math.sin(a) * outer, 0)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        ni = (i + 1) % segments
        a0, a1 = i * 2, i * 2 + 1
        b0, b1 = ni * 2, ni * 2 + 1
        tris.addVertices(a0, a1, b1)
        tris.addVertices(a0, b1, b0)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_triangle(name: str, size: float = 1.0) -> NodePath:
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    for a in (math.pi / 2, math.pi / 2 + TAU / 3, math.pi / 2 + 2 * TAU / 3):
        vw.addData3f(math.cos(a) * size, math.sin(a) * size, 0)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_box(name: str, sx: float = 1.0, sy: float = 1.0, sz: float = 1.0) -> NodePath:
    """Create a small dependency-free box centered on XY and standing on Z=0."""
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    x, y, z = sx * 0.5, sy * 0.5, sz
    verts = [
        (-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0),
        (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z),
    ]
    for v in verts:
        vw.addData3f(*v)
    tris = GeomTriangles(Geom.UHStatic)
    for a, b, c in (
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ):
        tris.addVertices(a, b, c)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_cylinder(name: str, radius: float = 1.0, height: float = 0.3, segments: int = 32) -> NodePath:
    """Create a capped cylinder standing on Z=0."""
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    vw.addData3f(0, 0, height)
    vw.addData3f(0, 0, 0)
    for i in range(segments):
        a = TAU * i / segments
        vw.addData3f(math.cos(a) * radius, math.sin(a) * radius, height)
        vw.addData3f(math.cos(a) * radius, math.sin(a) * radius, 0)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        ni = (i + 1) % segments
        top0, bot0 = 2 + i * 2, 3 + i * 2
        top1, bot1 = 2 + ni * 2, 3 + ni * 2
        tris.addVertices(0, top0, top1)      # top cap
        tris.addVertices(1, bot1, bot0)      # bottom cap
        tris.addVertices(top0, bot0, bot1)   # wall
        tris.addVertices(top0, bot1, top1)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_pyramid_3d(name: str, size: float = 1.0, height: float = 1.0, sides: int = 4) -> NodePath:
    """Create a low-poly cone/pyramid standing on Z=0."""
    sides = max(3, int(sides))
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    vw.addData3f(0, 0, height)
    vw.addData3f(0, 0, 0)
    for i in range(sides):
        a = TAU * i / sides + (math.pi / 4 if sides == 4 else 0)
        vw.addData3f(math.cos(a) * size, math.sin(a) * size, 0)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(sides):
        ni = (i + 1) % sides
        tris.addVertices(0, 2 + i, 2 + ni)
        tris.addVertices(1, 2 + ni, 2 + i)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


TERRACE_SLAB_THICKNESS = 0.34


def make_annulus_3d(name: str, inner: float, outer: float, height: float, segments: int = 144) -> NodePath:
    """Create a thin terraced ring slab whose top surface is at `height`.

    Earlier passes extruded every ring from Z=0 to the ring height. Once some
    outer rings went below zero, those Z=0 caps became a dark platform above
    Water/Urban/Metropolis and visually covered the lower world. This slab
    version keeps each ring local to its own terrace level.
    """
    bottom = height - TERRACE_SLAB_THICKNESS
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    for i in range(segments):
        a = TAU * i / segments
        ca, sa = math.cos(a), math.sin(a)
        # inner top, outer top, inner bottom, outer bottom
        vw.addData3f(ca * inner, sa * inner, height)
        vw.addData3f(ca * outer, sa * outer, height)
        vw.addData3f(ca * inner, sa * inner, bottom)
        vw.addData3f(ca * outer, sa * outer, bottom)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        ni = (i + 1) % segments
        it0, ot0, ib0, ob0 = i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 3
        it1, ot1, ib1, ob1 = ni * 4, ni * 4 + 1, ni * 4 + 2, ni * 4 + 3
        tris.addVertices(it0, ot0, ot1); tris.addVertices(it0, ot1, it1)
        tris.addVertices(ib0, ob1, ob0); tris.addVertices(ib0, ib1, ob1)
        tris.addVertices(ot0, ob0, ob1); tris.addVertices(ot0, ob1, ot1)
        tris.addVertices(it0, ib1, ib0); tris.addVertices(it0, it1, ib1)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_disc_3d(name: str, radius: float, height: float, segments: int = 96) -> NodePath:
    """Create a thin disc slab whose top surface is at `height`."""
    bottom = height - TERRACE_SLAB_THICKNESS
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    vw.addData3f(0, 0, height)
    vw.addData3f(0, 0, bottom)
    for i in range(segments):
        a = TAU * i / segments
        ca, sa = math.cos(a), math.sin(a)
        vw.addData3f(ca * radius, sa * radius, height)
        vw.addData3f(ca * radius, sa * radius, bottom)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        ni = (i + 1) % segments
        top0, bot0 = 2 + i * 2, 3 + i * 2
        top1, bot1 = 2 + ni * 2, 3 + ni * 2
        tris.addVertices(0, top0, top1)
        tris.addVertices(1, bot1, bot0)
        tris.addVertices(top0, bot0, bot1)
        tris.addVertices(top0, bot1, top1)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def add_wireframe_copy(node: NodePath, color=(0.9, 1.0, 1.0, 0.26), scale: float = 1.018) -> NodePath:
    wire = node.copyTo(node.getParent())
    wire.setScale(node.getScale() * scale)
    wire.setPos(node.getPos())
    wire.setHpr(node.getHpr())
    wire.setRenderModeWireframe()
    wire.setLightOff(1)
    wire.setTransparency(TransparencyAttrib.MAlpha)
    wire.setColor(*color)
    return wire


# Pass 15: terraced-mountain layout. Core/Flat form the high plateau;
# every outward region after FLAT drops one clear level so the battlefield
# reads like a stepped mountain from the RTS orbit camera.
RING_HEIGHTS = {
    # Pass 19: dramatically deeper mountain terraces. Every outer region sits
    # much lower, so attackers visibly climb step by step toward the hub.
    "CORE": 8.80,
    "FLAT": 7.55,
    "FOREST": 5.90,
    "HILLS": 4.15,
    "MUSHROOM": 2.35,
    "DESERT": 0.45,
    "WATER": -1.05,
    "URBAN": -3.35,
    "METROPOLIS": -6.10,
}
RING_TOP_ORDER = ("CORE", "FLAT", "FOREST", "HILLS", "MUSHROOM", "DESERT", "WATER", "URBAN", "METROPOLIS")


def add_circle_line(parent: NodePath, name: str, radius: float, color, thickness: float = 1.0, z: float = 0.08, segments: int = 144) -> NodePath:
    segs = LineSegs(name)
    segs.setThickness(thickness)
    segs.setColor(*color)
    for i in range(segments + 1):
        a = TAU * i / segments
        p = Vec3(math.cos(a) * radius, math.sin(a) * radius, z)
        if i == 0:
            segs.moveTo(p)
        else:
            segs.drawTo(p)
    return parent.attachNewNode(segs.create())


def add_line(parent: NodePath, name: str, a: Vec3, b: Vec3, color, thickness: float = 1.4) -> NodePath:
    segs = LineSegs(name)
    segs.setThickness(thickness)
    segs.setColor(*color)
    segs.moveTo(a)
    segs.drawTo(b)
    return parent.attachNewNode(segs.create())


def ring_index(name: str) -> int:
    try:
        return list(RING_TOP_ORDER).index(name)
    except ValueError:
        return len(RING_TOP_ORDER)


def inner_ring(name: str) -> Optional[str]:
    idx = ring_index(name)
    if idx <= 0:
        return None
    return RING_TOP_ORDER[idx - 1]


def outer_ring(name: str) -> Optional[str]:
    idx = ring_index(name)
    if idx >= len(RING_TOP_ORDER) - 1:
        return None
    return RING_TOP_ORDER[idx + 1]


@dataclass
class Entity:
    kind: str
    pos: Vec3
    hp: float = 1.0
    max_hp: float = 1.0
    angle: float = 0.0
    speed: float = 1.0
    state: str = "active"
    timer: float = 0.0
    cooldown: float = 0.0
    growth: float = 0.0
    target: Optional[Vec3] = None
    node: Optional[NodePath] = None
    extra: dict = field(default_factory=dict)


class HoloVerseRTS(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.clock = ClockObject.getGlobalClock()
        self.clock.setMode(ClockObject.MNormal)
        self.rng = random.Random(10457)
        self.elapsed = 0.0
        self.keys: set[str] = set()
        self.camera_center = Vec3(0, 0, 0)
        self.camera_zoom = 352.0
        self.camera_pitch = 62.0
        self.camera_yaw = -55.0
        self.order_target: Optional[Vec3] = None
        self.command_count = 0
        self.reset_count = 0
        self.hub_integrity = 1.0
        self.forest_attack_timer = 0.0
        self.forest_supply_safe = True
        self.last_region = "CORE"
        self.selected_region = ""
        self.activity_panel_visible = False
        self.activity_status_timer = 0.0
        self.region_activity_log = {name: [] for name in REGION_ACTIVITY_ORDER}
        self.region_records = {
            name: {"defender_wins": 0, "enemy_wins": 0, "enemy_losses": 0, "structure_losses": 0, "last_state": "SECURE"}
            for name in REGION_ACTIVITY_ORDER
        }
        self.stats = {
            "enemies_spawned": 0, "enemies_destroyed": 0, "water_vessels": 0,
            "laser_hits": 0, "spore_explosions": 0, "confused": 0,
            "bot_blasts": 0, "artifact_resets": 0, "forest_destroyed": 0,
            "enemy_squads": 0, "enemy_support_links": 0, "enemy_hacks": 0,
            "enemy_siege_shots": 0, "frontline_skirmishes": 0,
            "beam_culls": 0, "space_beam_culls": 0, "peak_enemies": 0,
            "peak_world_beams": 0, "peak_space_beams": 0, "enemy_regroups": 0,
            "region_pressure_updates": 0, "gleebs_pulses": 0, "impact_bursts": 0, "metro_variant_structures": 0,
            "waves_completed": 0, "wave_spawns": 0, "recovery_windows": 0,
            "wave_doctrine_changes": 0, "command_energy_rewards": 0,
            "command_uses": 0, "command_denied": 0, "command_cooldown_denied": 0,
            "defense_vectors": 0, "attack_vectors": 0, "alert_pulses": 0, "repairs_called": 0,
            "rallies_called": 0, "desert_overcharges": 0, "forest_surges": 0, "spore_blooms": 0,
            "score_events": 0, "wave_score_bonus": 0, "run_failures": 0,
            "upgrade_points": 0, "auto_upgrades": 0, "milestone_bonuses": 0,
            "best_wave": 1, "best_rank": 1,
            "enemy_veterans": 0, "enemy_adaptations": 0, "enemy_memory_marks": 0,
            "enemy_carrier_deploys": 0, "enemy_harvests": 0, "enemy_shield_blocks": 0,
            "enemy_phantom_bypasses": 0, "enemy_persistent_squads": 0,
            "ambient_activity_units": 0, "ambient_activity_pulses": 0,
            "primary_bot_abilities": 0, "primary_bot_matchups": 0,
            "bot_root_binds": 0, "bot_spore_dazes": 0, "bot_marks": 0,
            "bot_reflect_wards": 0, "io_intercepts": 0,
            "bot_unique_powers": 0, "io_chain_hits": 0,
            "vanta_root_groves": 0, "nyx_pack_howls": 0,
            "solace_spore_novas": 0, "ember_pyramid_links": 0,
            "mirror_prism_wards": 0, "sable_killbox_hits": 0,
            "archivist_uplinks": 0, "bot_synergies": 0,
            "orbit_killboxes": 0, "grove_pack_triggers": 0,
            "dream_uplinks": 0, "sun_prisms": 0,
            "bot_overdrive_commands": 0, "bot_overdrive_hits": 0,
            "activity_log_events": 0, "activity_region_clicks": 0, "activity_status_changes": 0,
            "activity_defender_wins": 0, "activity_enemy_wins": 0, "activity_structure_losses": 0,
        }
        self.region_pressure = {name: 0.0 for name in RINGS}
        self.wave_index = 1
        self.wave_phase = "assault"
        self.wave_phase_time = 0.0
        self.current_doctrine = self.wave_doctrine_name(self.wave_index)
        self.enemy_spawn_timer = 1.2
        self.command_energy = 55.0
        self.command_flash = 0.0
        self.command_buffs = {
            "urban_rally": 0.0,
            "desert_overcharge": 0.0,
            "forest_surge": 0.0,
            "spore_bloom": 0.0,
            "core_repair": 0.0,
            "bot_overdrive": 0.0,
        }
        self.command_cooldowns = {name: 0.0 for name in COMMAND_COOLDOWNS}
        self.score = 0
        self.best_score = 0
        self.last_run_score = 0
        self.core_rank = 1
        self.combo = 1.0
        self.combo_timer = 0.0
        self.run_time = 0.0
        self.run_number = 1
        self.run_message = "HUB DEFENSE ONLINE"
        self.run_message_timer = 6.0
        self.upgrade_levels = {name: 0 for name in UPGRADE_ORDER}
        self.upgrade_points = 0
        # Pass 39: enemy intelligence is session-persistent only. It does not
        # write save files, but Metropolis remembers which squads survived,
        # where attackers died, and which counter-classes to bias into later waves.
        self.enemy_squad_memory: dict[int, dict] = {}
        self.enemy_learning = {
            "deaths_by_region": {}, "deaths_by_class": {}, "best_region_reached": {},
            "survived_by_class": {}, "damage_marks": {},
        }
        self.adaptive_bias: dict[str, float] = {}
        self.adaptation_message = "Metropolis learning net idle"
        self.adaptation_message_timer = 0.0
        self.bot_power_message = "Primary bot powers online"
        self.bot_power_message_timer = 0.0
        self.bot_power_recent = {name: -999.0 for name in BOT_NAMES}
        self.bot_synergy_cooldowns = {name: 0.0 for name in BOT_SYNERGIES}
        self.bot_overdrive_flash = 0.0
        self.last_adapt_wave = 0
        self.ui_mode = UI_START_MODE if (UI_START_MODE in UI_MODES or UI_START_MODE == "debug") else "clean"
        self.ui_flash = 0.0
        if PROGRESSION_TEST:
            # Start near the first recovery window so automated tests can
            # verify score/upgrade progression without a full minute wait.
            self.elapsed = WAVE_ASSAULT_DURATION - 1.4
            self.run_time = self.elapsed
            self.enemy_spawn_timer = 0.25

        self.sky_root = self.render.attachNewNode("sky")
        self.sky_fx_root = self.render.attachNewNode("sky-fx")
        self.gleebs_root = self.camera.attachNewNode("gleebs-backdrop")
        self.ring_root = self.render.attachNewNode("rings")
        self.marker_root = self.render.attachNewNode("markers")
        self.unit_root = self.render.attachNewNode("units")
        self.fx_root = self.render.attachNewNode("fx")
        # Pass 16: cache generated miniature meshes under a hidden template root.
        # Repeated units now copy tiny templates instead of rebuilding geometry
        # every time enemies/support packets respawn.
        self.template_root = self.render.attachNewNode("marker-templates")
        self.template_root.hide()
        self.marker_template_cache = {}
        for root in (self.sky_root, self.sky_fx_root, self.gleebs_root, self.ring_root, self.marker_root, self.unit_root, self.fx_root):
            root.setTransparency(TransparencyAttrib.MAlpha)
        # Pass 27 keeps the single-file sim math stable while presenting each
        # ring as a much larger battlefield. Geometry, actors, FX, and labels
        # share this same visual expansion root.
        for root in (self.ring_root, self.marker_root, self.unit_root, self.fx_root):
            root.setScale(WORLD_EXPANSION_SCALE, WORLD_EXPANSION_SCALE, 1.0)
        self.sky_root.setLightOff(1)
        self.sky_fx_root.setLightOff(1)
        self.gleebs_root.setLightOff(1)
        self.gleebs_card: Optional[NodePath] = None
        self.gleebs_texture_path: Optional[Path] = None
        self.gleebs_texture_loaded = False
        self.gleebs_enabled = not NO_GLEEBS
        self.gleebs_alpha = 0.30
        self.gleebs_aura_nodes: list[NodePath] = []

        self.enemies: list[Entity] = []
        self.urban_troops: list[Entity] = []
        self.desert_troops: list[Entity] = []
        self.mushroom_troops: list[Entity] = []
        self.hills_caretakers: list[Entity] = []
        self.wildlife: list[Entity] = []
        self.forest_plants: list[Entity] = []
        self.pyramids: list[Entity] = []
        self.mushrooms: list[Entity] = []
        self.artifacts: list[Entity] = []
        self.bots: list[Entity] = []
        self.beams: list[tuple[NodePath, float]] = []
        self.space_beams: list[tuple[NodePath, float]] = []
        self.smokes: list[Entity] = []
        self.packets: list[Entity] = []
        self.space_fronts: list[dict] = []
        self.metro_spawn_pulses: list[dict] = []
        self.logic_pulses: list[dict] = []
        self.region_status_pulses: list[dict] = []
        self.battlefront_pulses: list[dict] = []
        self.command_pulses: list[dict] = []
        self.region_alert_pulses: list[dict] = []
        self.attack_vector_pulses: list[dict] = []
        self.defense_vector_pulses: list[dict] = []
        self.impact_bursts: list[dict] = []
        # Pass 41: visible region life. These are lightweight visual actors
        # that patrol, ferry supplies, stage at defenses, and pulse regional
        # activity so the widened board feels alive even before enemies reach
        # every ring. They are gameplay-readable but do not add new folders or
        # alter combat math.
        self.region_activity_units: list[Entity] = []
        self.region_activity_beams: list[tuple[NodePath, float]] = []
        self.activity_pulse_timer = 0.0

        self.setup_window()
        self.setup_scene()
        self.setup_ui()
        self.setup_inputs()
        self.reset_board(full=True)
        if ENEMY_SHOWCASE:
            self.seed_enemy_showcase()
        if INTELLIGENCE_TEST:
            self.seed_enemy_intelligence_test()
        if PRIMARY_BOT_TEST:
            self.seed_primary_bot_test()
        if ACTIVITY_LOG_TEST:
            self.seed_activity_log_test()
        if OVERVIEW_SHOT:
            self.focus_overview_camera()
        elif ENEMY_FOCUS_SHOT:
            self.focus_enemy_camera()
        elif METROPOLIS_FOCUS:
            self.focus_metropolis_camera()
        self.taskMgr.add(self.update, "rts-update")
        if AUTO_EXIT:
            self.taskMgr.doMethodLater(9.0 if SOAK_TEST else 3.0, self.auto_exit, "auto-exit")
        if SCREENSHOT_PATH:
            self.taskMgr.doMethodLater(1.4, self.capture_screenshot, "capture-screenshot")

    def setup_window(self):
        props = WindowProperties()
        props.setTitle(f"{GAME_NAME} {VERSION}")
        props.setCursorHidden(False)
        if self.win and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self.setBackgroundColor(0.002, 0.003, 0.010, 1)

    def setup_scene(self):
        self.render.setAntialias(AntialiasAttrib.MAuto)
        self.render.setTransparency(TransparencyAttrib.MAlpha)
        self.camLens.setNearFar(0.1, 1500.0)
        self.camLens.setFov(63.0)
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.60, 0.62, 0.68, 1.0))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.62, 0.66, 0.72, 1.0))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-35, -52, 0)
        self.render.setLight(sun_np)
        self.build_skybox()
        self.build_gleebs_backdrop()
        self.build_board()
        self.update_camera(0)

    def setup_ui(self):
        # Pass 47: 16:9 corner-safe HUD layout. The battlefield stays clear in
        # the center while important game information lives in the screen
        # corners: core/score, commands, selected activity log, and region state.
        panel_frame = (0.00, 0.00, 0.00, 0.30)
        bright = (0.90, 0.98, 1.0, 1.0)
        muted = (0.70, 0.80, 0.88, 0.92)
        self.hud_core = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.022,
            text_fg=bright,
            frameColor=panel_frame,
            frameSize=(-0.018, 0.690, -0.116, 0.034),
            textMayChange=True,
        )
        self.hud_wave = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ACenter,
            text_scale=0.025,
            text_fg=(1.0, 0.86, 0.54, 1.0),
            frameColor=(0.02, 0.00, 0.02, 0.28),
            frameSize=(-0.610, 0.610, -0.100, 0.036),
            textMayChange=True,
        )
        self.hud_commands = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ARight,
            text_scale=0.021,
            text_fg=(0.86, 1.0, 0.98, 1.0),
            frameColor=(0.00, 0.02, 0.03, 0.34),
            frameSize=(-0.880, 0.018, -0.168, 0.038),
            textMayChange=True,
        )
        self.hud_regions = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ARight,
            text_scale=0.019,
            text_fg=muted,
            frameColor=(0.00, 0.00, 0.00, 0.28),
            frameSize=(-0.840, 0.018, -0.146, 0.040),
            textMayChange=True,
        )
        self.hud_fx = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ARight,
            text_scale=0.018,
            text_fg=(0.64, 0.75, 0.84, 0.88),
            frameColor=(0.00, 0.00, 0.00, 0.18),
            frameSize=(-0.720, 0.018, -0.126, 0.040),
            textMayChange=True,
        )
        self.hud_activity = DirectLabel(
            parent=self.aspect2d,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.0152,
            text_fg=(0.82, 0.94, 1.0, 0.96),
            frameColor=(0.00, 0.015, 0.025, 0.39),
            frameSize=(-0.016, 0.535, -0.218, 0.036),
            textMayChange=True,
        )
        # Backward-compatible handle for older helpers that expect self.hud.
        self.hud = self.hud_core
        self.ui_panels = [self.hud_core, self.hud_wave, self.hud_commands, self.hud_regions, self.hud_fx, self.hud_activity]
        self.banner = DirectLabel(
            parent=self.aspect2d,
            text="HUB PROTECTED AT ALL COSTS",
            text_align=TextNode.ACenter,
            text_scale=0.023,
            text_fg=(1.0, 0.44, 0.46, 1),
            frameColor=(0.00, 0.00, 0.00, 0.20),
            frameSize=(-0.900, 0.900, -0.034, 0.032),
            textMayChange=True,
        )
        self.help = DirectLabel(
            parent=self.aspect2d,
            text="O overview  M Metro  E enemies  G Gleebs  U UI  F3 diagnostics  1-6 commands  RMB cancel  R reset",
            text_align=TextNode.ARight,
            text_scale=0.018,
            text_fg=(0.62, 0.73, 0.82, 0.78),
            frameColor=(0, 0, 0, 0),
            textMayChange=True,
        )
        # 16:9 safe corners. These positions assume Panda3D's aspect2d width
        # on a 16:9 window (~1.777) and leave a small safe margin.
        self.hud_core.setPos(-1.705, 0, 0.955)       # top-left
        self.hud_wave.setPos(0.0, 0, 0.955)          # slim top-center objective
        self.hud_commands.setPos(1.705, 0, 0.955)    # top-right
        self.hud_activity.setPos(-1.705, 0, 0.790)   # top-left selected-region log under core
        self.hud_regions.setPos(1.705, 0, 0.745)     # top-right region/threat summary under commands
        self.hud_fx.setPos(1.705, 0, -0.515)         # bottom-right diagnostics only
        self.hud_activity.hide()
        self.banner.setPos(0, 0, -0.945)
        self.help.setPos(1.70, 0, -0.982)

    def setup_inputs(self):
        for key in ["w", "a", "s", "d", "control"]:
            self.accept(key, self.key_down, [key])
            self.accept(key + "-up", self.key_up, [key])
        self.accept("wheel_up", self.zoom_camera, [-4.0])
        self.accept("wheel_down", self.zoom_camera, [4.0])
        self.accept("z", self.adjust_pitch, [-4.0])
        self.accept("x", self.adjust_pitch, [4.0])
        self.accept("r", self.reset_camera)
        self.accept("o", self.focus_overview_camera)
        self.accept("m", self.focus_metropolis_camera)
        self.accept("e", self.focus_enemy_camera)
        self.accept("g", self.toggle_gleebs)
        self.accept("l", self.pulse_logic_layer)
        self.accept("u", self.cycle_ui_mode)
        self.accept("f3", self.toggle_debug_ui)
        self.accept("1", self.command_rally_urban)
        self.accept("2", self.command_overcharge_desert)
        self.accept("3", self.command_spore_bloom)
        self.accept("4", self.command_forest_surge)
        self.accept("5", self.command_core_repair)
        self.accept("6", self.command_bot_overdrive)
        self.accept("mouse1", self.issue_mouse_order)
        self.accept("mouse3", self.cancel_order)
        self.accept("escape", self.userExit)

    def key_down(self, key: str):
        self.keys.add(key)

    def key_up(self, key: str):
        self.keys.discard(key)

    def build_skybox(self):
        self.sky_root.node().removeAllChildren()
        self.sky_fx_root.node().removeAllChildren()
        self.space_fronts.clear()
        self.space_beams.clear()
        sky_rng = random.Random(20020)

        # Expanded outer-space shell: large holo-orbits and tilted sky arcs
        # make the world feel embedded in a much larger battlefield.
        shell_specs = [
            # Pass 30: sky shell expanded so the 2x HoloVerse table still sits
            # inside a large outer-space battlefield instead of swallowing it.
            (165.0, (0.08, 0.22, 0.50, 0.14), 0.9),
            (235.0, (0.10, 0.30, 0.62, 0.11), 0.8),
            (315.0, (0.12, 0.18, 0.38, 0.10), 0.8),
            (405.0, (0.30, 0.10, 0.46, 0.08), 0.7),
            (525.0, (0.12, 0.24, 0.52, 0.06), 0.7),
        ]
        rotations = [(0, 0, 0), (90, 0, 0), (0, 90, 0), (40, 68, 0), (-32, 58, 0)]
        for radius, color, thick in shell_specs:
            for h, p, r in rotations:
                arc = add_circle_line(self.sky_root, f"sky-arc-{radius}", radius, color, thick, 0.0, 160)
                arc.setHpr(h, p, r)
                arc.setLightOff(1)

        # Nebula clouds.
        nebula_colors = [
            (0.16, 0.46, 1.0, 0.05),
            (0.92, 0.18, 1.0, 0.05),
            (0.18, 1.0, 0.86, 0.04),
            (1.0, 0.48, 0.18, 0.04),
        ]
        for i in range(18):
            cloud = make_disc(f"nebula-{i}", 8.0 + (i % 4) * 3.8, 40)
            cloud.reparentTo(self.sky_root)
            rr = 185.0 + (i % 6) * 28.0
            ang = TAU * i / 18 + 0.17
            zz = -60.0 + (i % 5) * 32.0
            cloud.setPos(math.cos(ang) * rr, math.sin(ang) * rr, zz)
            cloud.setHpr((i * 29) % 360, 68 + (i % 3) * 9, (i * 17) % 360)
            cloud.setScale(1.0, 1.0, 1.0)
            cloud.setColor(*nebula_colors[i % len(nebula_colors)])
            cloud.setTransparency(TransparencyAttrib.MAlpha)
            cloud.setLightOff(1)

        # Star field.
        for i in range(360):
            radius = sky_rng.uniform(180.0, 560.0)
            ang = sky_rng.uniform(0.0, TAU)
            zf = sky_rng.uniform(-0.34, 0.82)
            xy = math.sqrt(max(0.0, 1.0 - zf * zf)) * radius
            pos = Vec3(math.cos(ang) * xy, math.sin(ang) * xy, zf * radius)
            size = 0.06 + sky_rng.random() * 0.18
            star = make_box(f"star-{i}", size, size, size)
            star.reparentTo(self.sky_root)
            star.setPos(pos)
            bright = sky_rng.random()
            if bright > 0.93:
                col = (1.0, 0.86 + sky_rng.random() * 0.12, 0.72 + sky_rng.random() * 0.24, 0.92)
                star.setScale(1.9)
            elif bright > 0.72:
                col = (0.72 + sky_rng.random() * 0.28, 0.88, 1.0, 0.72)
            else:
                tint = 0.65 + sky_rng.random() * 0.35
                col = (tint, tint, tint + 0.08, 0.46)
            star.setColor(*col)
            star.setTransparency(TransparencyAttrib.MAlpha)
            star.setLightOff(1)

        # Outer-space battles outside the worlds.
        for i in range(7):
            front = self.sky_root.attachNewNode(f"space-front-{i}")
            a = TAU * i / 7 + 0.18
            radius = 190.0 + (i % 4) * 34.0
            z = 46.0 + (i % 3) * 20.0
            front.setPos(math.cos(a) * radius, math.sin(a) * radius, z)
            bubble = add_circle_line(front, f"battle-bubble-{i}", 7.2 + (i % 3) * 1.1, (0.20, 0.56, 1.0, 0.12), 1.0, 0.0, 64)
            bubble.setLightOff(1)
            danger = add_circle_line(front, f"battle-danger-{i}", 4.8 + (i % 2) * 1.1, (1.0, 0.18, 0.34, 0.10), 0.8, 0.0, 48)
            danger.setHpr(90, 0, 0)
            danger.setLightOff(1)
            fighters = []
            for j in range(8):
                side = "ally" if j < 4 else "enemy"
                kind = "space_ally" if side == "ally" else "space_enemy"
                color = (0.20, 0.94, 1.0, 0.92) if side == "ally" else (1.0, 0.22, 0.42, 0.92)
                node = self.make_marker(kind, color, 0.13 + (j % 2) * 0.02)
                node.reparentTo(front)
                node.setScale(0.88)
                fighters.append({"node": node, "side": side, "phase": sky_rng.uniform(0.0, TAU), "loop": 2.2 + sky_rng.random() * 2.4, "speed": 0.8 + sky_rng.random() * 1.6, "pitch": sky_rng.uniform(-0.9, 0.9)})
            for cap_side, cap_x in (("ally", -3.8), ("enemy", 3.8)):
                kind = "space_ally" if cap_side == "ally" else "space_enemy"
                color = (0.20, 0.94, 1.0, 0.80) if cap_side == "ally" else (1.0, 0.22, 0.42, 0.80)
                capital = self.make_marker(kind, color, 0.32)
                capital.reparentTo(front)
                capital.setPos(cap_x, 0, 0.7 if cap_side == "ally" else -0.7)
                capital.setScale(1.55)
            self.space_fronts.append({"node": front, "angle": a, "radius": radius, "z": z, "drift": (-1 if i % 2 else 1) * (0.05 + (i % 3) * 0.018), "fighters": fighters, "beam_timer": 0.02 + sky_rng.random() * 0.10, "pulse": sky_rng.uniform(0.0, TAU)})

        try:
            self.sky_root.flattenStrong()
        except Exception:
            pass

    def build_gleebs_backdrop(self):
        self.gleebs_root.node().removeAllChildren()
        self.gleebs_card = None
        self.gleebs_aura_nodes.clear()
        self.gleebs_texture_loaded = False
        self.gleebs_texture_path = find_gleebs_texture()
        if not self.gleebs_enabled:
            return
        if self.gleebs_texture_path is None:
            # Missing texture must never block the isolated single-file branch.
            # The drop-in zip includes assets/textures/gleebs.png, but this
            # fallback keeps bare-world.py smoke tests clean.
            return
        tex = self.loader.loadTexture(str(self.gleebs_texture_path))
        if tex is None:
            return
        sx = max(1, tex.getXSize())
        sy = max(1, tex.getYSize())
        aspect = sy / sx
        card_maker = CardMaker("gleebs-ghost-card")
        card_maker.setFrame(-0.5, 0.5, -0.5 * aspect, 0.5 * aspect)
        card = self.gleebs_root.attachNewNode(card_maker.generate())
        card.setTexture(tex, 1)
        card.setTransparency(TransparencyAttrib.MAlpha)
        card.setColor(1.25, 1.45, 1.20, 1.0)
        card.setAlphaScale(0.30)
        card.setPos(0, GLEEBS_BACKDROP_DISTANCE, GLEEBS_BACKDROP_Z)
        card.setScale(GLEEBS_BACKDROP_SCALE)
        card.setBin("background", 18)
        card.setDepthWrite(False)
        card.setLightOff(1)
        self.gleebs_card = card
        # Pass 31: faint, camera-attached aura rings make Gleebs feel like a
        # holographic presence behind the whole strategy board without blocking
        # region readability.
        for idx, radius in enumerate((42.0, 57.0, 74.0)):
            ring = add_circle_line(self.gleebs_root, f"gleebs-aura-{idx}", radius, (0.42, 1.0, 0.18, 0.19 - idx * 0.028), 1.25 - idx * 0.14, 0.0, 128)
            ring.setP(90)
            ring.setPos(0, GLEEBS_BACKDROP_DISTANCE + 1.5 + idx * 0.2, GLEEBS_BACKDROP_Z - 2.5 + idx * 3.0)
            ring.setTransparency(TransparencyAttrib.MAlpha)
            ring.setDepthWrite(False)
            ring.setLightOff(1)
            ring.setBin("background", 17)
            self.gleebs_aura_nodes.append(ring)
        self.gleebs_texture_loaded = True

    def toggle_gleebs(self):
        self.gleebs_enabled = not self.gleebs_enabled
        if self.gleebs_enabled and (self.gleebs_card is None or self.gleebs_card.isEmpty()):
            self.build_gleebs_backdrop()
        if self.gleebs_card is not None and not self.gleebs_card.isEmpty():
            if self.gleebs_enabled:
                self.gleebs_card.show()
            else:
                self.gleebs_card.hide()

    def update_gleebs_backdrop(self, dt: float):
        if self.gleebs_card is None or self.gleebs_card.isEmpty():
            return
        if not self.gleebs_enabled:
            self.gleebs_alpha += (0.0 - self.gleebs_alpha) * clamp(dt * 6.0, 0.0, 1.0)
            self.gleebs_card.setAlphaScale(self.gleebs_alpha)
            return
        metro_pressure = self.region_pressure.get("METROPOLIS", 0.0)
        core_pressure = max(self.region_pressure.get("CORE", 0.0), self.region_pressure.get("FLAT", 0.0))
        enemy_pressure = clamp(len(self.enemies) / 120.0, 0.0, 1.0)
        hub_danger = clamp(1.0 - self.hub_integrity, 0.0, 1.0)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * (0.55 + enemy_pressure * 0.65))
        target_alpha = 0.32 + pulse * 0.060 + metro_pressure * 0.055 + core_pressure * 0.090 + hub_danger * 0.16
        self.gleebs_alpha += (target_alpha - self.gleebs_alpha) * clamp(dt * 2.4, 0.0, 1.0)
        scale_pulse = 1.0 + 0.018 * pulse + 0.025 * hub_danger
        self.gleebs_card.setAlphaScale(clamp(self.gleebs_alpha, 0.0, 0.58))
        self.gleebs_card.setScale(GLEEBS_BACKDROP_SCALE * scale_pulse)
        self.gleebs_card.setZ(GLEEBS_BACKDROP_Z + math.sin(self.elapsed * 0.32) * 2.8)
        for idx, aura in enumerate(self.gleebs_aura_nodes):
            if aura is None or aura.isEmpty():
                continue
            aura_wave = 0.5 + 0.5 * math.sin(self.elapsed * (0.38 + idx * 0.13) + idx * 1.7)
            aura.setZ(GLEEBS_BACKDROP_Z - 2.5 + idx * 3.0 + math.sin(self.elapsed * 0.24 + idx) * 1.8)
            aura.setScale(1.0 + aura_wave * 0.09 + hub_danger * 0.10)
            aura.setAlphaScale(clamp(0.10 + aura_wave * 0.10 + core_pressure * 0.12 + hub_danger * 0.18, 0.0, 0.42))
        self.stats["gleebs_pulses"] = self.stats.get("gleebs_pulses", 0) + 1

    def build_board(self):
        self.ring_root.node().removeAllChildren()
        # Pass 24: move the table/base below the lowest Metropolis slab. The
        # old base sat near Z=0, while Water/Urban/Metropolis are below Z=0,
        # which looked like a black platform covering the lower regions.
        base_z = min(RING_HEIGHTS.values()) - TERRACE_SLAB_THICKNESS - 0.42
        base = make_cylinder("rts-mountain-underframe", RINGS["METROPOLIS"]["outer"] + 1.8, 0.16, 144)
        base.reparentTo(self.ring_root)
        base.setPos(0, 0, base_z)
        base.setColor(0.010, 0.014, 0.026, 0.34)
        base.setTransparency(TransparencyAttrib.MAlpha)
        # Pass 15: terraced mountain board. Core/Flat form the high plateau and
        # each outward ring is one level lower, so enemies climb toward the hub.
        for name, spec in RINGS.items():
            h = RING_HEIGHTS.get(name, 0.5)
            node = make_disc_3d(name, spec["outer"], h) if spec["inner"] <= 0 else make_annulus_3d(name, spec["inner"], spec["outer"], h)
            node.reparentTo(self.ring_root)
            node.setColor(*spec["color"])
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setTwoSided(False)
            # Top lip lines and step-wall highlights make the elevation ladder readable.
            add_circle_line(self.ring_root, f"{name}-outer-top", spec["outer"], (0.72, 0.92, 1.0, 0.30), 1.15, h + 0.045)
            add_circle_line(self.ring_root, f"{name}-outer-step-glow", spec["outer"], (0.10, 0.18, 0.24, 0.34), 1.35, h - TERRACE_SLAB_THICKNESS * 0.50)
            if spec["inner"] > 0:
                add_circle_line(self.ring_root, f"{name}-inner-top", spec["inner"], (0.78, 0.96, 1.0, 0.18), 0.85, h + 0.05)
            # Low shadow at the ring base improves the tabletop / miniature feel.
            add_circle_line(self.ring_root, f"{name}-base-shadow", spec["outer"], (0.0, 0.0, 0.0, 0.18), 1.1, h - TERRACE_SLAB_THICKNESS - 0.012)
            # Stronger terraced drop marker: a mid-wall neon shelf makes the
            # height step visible from oblique orbit views without adding
            # gameplay collision or old terrain systems.
            if name not in {"CORE", "FLAT"}:
                shelf_z = h - TERRACE_SLAB_THICKNESS * 0.35
                add_circle_line(self.ring_root, f"{name}-deep-step-shelf", spec["inner"], (0.06, 0.12, 0.18, 0.38), 1.75, shelf_z, 144)
            if name != "CORE":
                mid = (spec["inner"] + spec["outer"]) * 0.5
                label_angle = math.radians(-72)
                level = max(0, (RING_TOP_ORDER.index(name) - 1)) if name in RING_TOP_ORDER else 0
                self.add_label(name, f"{name}  L-{level}\n{spec['purpose']}", angle_to_pos(label_angle, mid, h + 0.76), 0.62, (0.88, 0.96, 1.0, 0.88))
        # Pass 19: explicit climb shelves and ascent lanes between terrace levels.
        for outer_name in RING_TOP_ORDER[1:]:
            inner_name = inner_ring(outer_name)
            if not inner_name:
                continue
            outer_spec = RINGS[outer_name]
            inner_spec = RINGS[inner_name]
            inner_r = outer_spec["inner"]
            z0 = RING_HEIGHTS[outer_name] + 0.12
            z1 = RING_HEIGHTS[inner_name] + 0.30
            add_circle_line(self.ring_root, f"{outer_name}-cliff-holo", inner_r, (0.12, 0.72, 1.0, 0.12), 0.75, z0 + max(0.12, (z1-z0)*0.45), 96)
            lane_count = 8 if outer_name in {"FOREST", "HILLS", "MUSHROOM", "DESERT"} else 10
            for i in range(lane_count):
                a = TAU * i / lane_count + ring_index(outer_name) * 0.07
                start = angle_to_pos(a, inner_r + 0.84, z0)
                mid = angle_to_pos(a, inner_r + 0.24, z0 + (z1 - z0) * 0.55)
                end = angle_to_pos(a, max(0.18, inner_spec["outer"] - 0.58), z1)
                add_line(self.ring_root, f"{outer_name}-climb-lane-a", start, mid, (0.18, 0.92, 1.0, 0.20), 1.05)
                add_line(self.ring_root, f"{outer_name}-climb-lane-b", mid, end, (0.18, 0.92, 1.0, 0.12), 0.95)

        # Water rule rings and hub shield, lifted above the new 3D channel.
        add_circle_line(self.ring_root, "water-no-cross-outer", RINGS["WATER"]["outer"], (0.12, 0.78, 1.0, 0.76), 2.2, RING_HEIGHTS["WATER"] + 0.20)
        add_circle_line(self.ring_root, "water-no-cross-inner", RINGS["WATER"]["inner"], (0.12, 0.78, 1.0, 0.52), 1.55, RING_HEIGHTS["WATER"] + 0.22)
        add_circle_line(self.ring_root, "hub-shield", RINGS["CORE"]["outer"] + 0.35, (0.22, 0.98, 1.0, 0.92), 2.8, RING_HEIGHTS["CORE"] + 0.34)
        add_circle_line(self.ring_root, "hub-shield-high", RINGS["CORE"]["outer"] + 0.92, (0.22, 0.98, 1.0, 0.36), 1.25, RING_HEIGHTS["CORE"] + 0.86)
        # Metropolis attack gates and Urban defense gates now float like holographic rails.
        for i in range(8):
            a = TAU * i / 8 + 0.22
            add_line(self.ring_root, "metro-threat-lane", angle_to_pos(a, 42.0, RING_HEIGHTS["METROPOLIS"] + 0.18), angle_to_pos(a, 36.0, RING_HEIGHTS["URBAN"] + 0.22), (1.0, 0.12, 0.16, 0.50), 1.35)
            add_line(self.ring_root, "urban-defense-lane", angle_to_pos(a, 36.0, RING_HEIGHTS["URBAN"] + 0.27), angle_to_pos(a, 31.0, RING_HEIGHTS["URBAN"] + 0.27), (0.15, 0.90, 1.0, 0.44), 1.2)
        # Pass 21: extra warfare conduits from Metropolis into Urban so the
        # enemy origin and frontline read more aggressively.
        for i in range(16):
            a = TAU * i / 16 + 0.08
            add_line(self.ring_root, "metro-war-grid", angle_to_pos(a, 43.0, RING_HEIGHTS["METROPOLIS"] + 0.42), angle_to_pos(a + 0.04, 38.0, RING_HEIGHTS["METROPOLIS"] + 1.10), (0.92, 0.12, 0.38, 0.20), 0.88)
            add_line(self.ring_root, "urban-front-grid", angle_to_pos(a, 35.6, RING_HEIGHTS["URBAN"] + 0.30), angle_to_pos(a + 0.03, 31.2, RING_HEIGHTS["URBAN"] + 0.56), (0.18, 0.90, 1.0, 0.16), 0.82)

        self.build_holo_grid()
        self.build_region_props()
        self.build_logic_model_links()
        self.build_region_status_pulses()
        self.build_battlefront_pulses()
        self.build_command_pulses()
        self.build_combat_readability_overlays()
        # Static board geometry is finalized once. Dynamic units/effects live in
        # separate roots, so flattening the terrain/props improves draw cost
        # without affecting gameplay state.
        try:
            self.ring_root.flattenStrong()
        except Exception:
            pass

    def build_holo_grid(self):
        """Draw dense holographic grid lines over the terraced regions.

        This intentionally uses line geometry only and is flattened with the
        static board, so the denser strategy-board look does not add runtime
        update cost.
        """
        grid_alpha = {
            "FOREST": 0.25, "HILLS": 0.24, "MUSHROOM": 0.27, "DESERT": 0.25,
            "WATER": 0.32, "URBAN": 0.28, "METROPOLIS": 0.30, "FLAT": 0.22,
        }
        for name, spec in RINGS.items():
            if name == "CORE":
                continue
            h = RING_HEIGHTS.get(name, 0.0) + 0.075
            inner = spec["inner"]
            outer = spec["outer"]
            alpha = grid_alpha.get(name, 0.22)
            # Inner subdivision rings create the command-table grid feel.
            for t in (0.25, 0.50, 0.75):
                rr = inner + (outer - inner) * t
                add_circle_line(self.ring_root, f"{name}-holo-grid-ring-{t:.2f}", rr, (0.38, 1.0, 0.96, alpha), 0.58, h, 128)
            # Radial ribs are staggered between regions so the board looks
            # denser without turning into a single unreadable spider web.
            ribs = 12 if name in {"FOREST", "URBAN", "METROPOLIS"} else 10
            phase = (RING_TOP_ORDER.index(name) if name in RING_TOP_ORDER else 0) * 0.037
            for i in range(ribs):
                a = TAU * i / ribs + phase
                add_line(
                    self.ring_root,
                    f"{name}-holo-rib",
                    angle_to_pos(a, inner + 0.10, h),
                    angle_to_pos(a, outer - 0.10, h),
                    (0.32, 0.92, 1.0, alpha * 0.92),
                    0.52,
                )
        # A faint global command lattice ties all rings together from the core.
        for i in range(16):
            a = TAU * i / 16 + 0.05
            add_line(
                self.ring_root,
                "global-command-lattice",
                angle_to_pos(a, RINGS["FLAT"]["inner"], RING_HEIGHTS["FLAT"] + 0.22),
                angle_to_pos(a, RINGS["METROPOLIS"]["outer"], RING_HEIGHTS["METROPOLIS"] + 0.24),
                (0.16, 0.58, 1.0, 0.13),
                0.42,
            )

    def build_region_props(self):
        """Static 3D set dressing for each strategic ring."""
        # Core pedestal / protected hub tower.
        hub = make_cylinder("core-hub-tower", 1.05, 1.85, 24)
        hub.reparentTo(self.ring_root)
        hub.setPos(0, 0, RING_HEIGHTS["CORE"] + 0.02)
        hub.setColor(0.12, 0.42, 0.58, 0.88)
        hub.setTransparency(TransparencyAttrib.MAlpha)
        add_wireframe_copy(hub, (0.30, 1.0, 1.0, 0.22))
        crown = make_pyramid_3d("core-hub-crown", 0.82, 0.92, 6)
        crown.reparentTo(self.ring_root)
        crown.setPos(0, 0, RING_HEIGHTS["CORE"] + 1.72)
        crown.setColor(0.62, 0.96, 1.0, 0.72)

        # Urban factories / barracks.
        for i in range(8):
            a = TAU * i / 8 + 0.05
            pos = angle_to_pos(a, 33.7 + (i % 2) * 0.95, RING_HEIGHTS["URBAN"] + 0.02)
            b = make_box("urban-factory", 1.18, 0.72, 0.74 + (i % 3) * 0.16)
            b.reparentTo(self.ring_root)
            b.setPos(pos)
            b.setH(math.degrees(a) + 90)
            b.setColor(0.18, 0.28, 0.34, 0.72)
            b.setTransparency(TransparencyAttrib.MAlpha)

        # Metropolis hostile skyline / gates.
        for i in range(12):
            a = TAU * i / 12 + 0.11
            height = 1.2 + (i % 4) * 0.55
            pos = angle_to_pos(a, 39.0 + (i % 3) * 0.82, RING_HEIGHTS["METROPOLIS"] + 0.01)
            tower = make_box("metro-tower", 0.62, 0.62, height)
            tower.reparentTo(self.ring_root)
            tower.setPos(pos)
            tower.setH(math.degrees(a))
            tower.setColor(0.48, 0.10, 0.72, 0.74)
            tower.setTransparency(TransparencyAttrib.MAlpha)

        # Water surface wave strips.
        for i in range(16):
            a0 = TAU * i / 16
            add_line(self.ring_root, "water-wave", angle_to_pos(a0, 26.55, RING_HEIGHTS["WATER"] + 0.08), angle_to_pos(a0 + 0.055, 30.25, RING_HEIGHTS["WATER"] + 0.08), (0.45, 0.92, 1.0, 0.26), 0.95)

        # Forest supply structures: stronger tree silhouettes and nursery shelves.
        for i in range(10):
            a = TAU * i / 10 + 0.08
            trunk = make_cylinder("forest-static-trunk", 0.13 + (i % 2) * 0.035, 0.62 + (i % 3) * 0.12, 8)
            trunk.reparentTo(self.ring_root)
            trunk.setPos(angle_to_pos(a, 7.1 + (i % 4) * 0.82, RING_HEIGHTS["FOREST"] + 0.02))
            trunk.setColor(0.28, 0.18, 0.08, 0.68)
            trunk.setTransparency(TransparencyAttrib.MAlpha)
            canopy = make_pyramid_3d("forest-static-canopy", 0.38 + (i % 3) * 0.08, 0.82 + (i % 2) * 0.20, 6)
            canopy.reparentTo(self.ring_root)
            canopy.setPos(angle_to_pos(a, 7.1 + (i % 4) * 0.82, RING_HEIGHTS["FOREST"] + 0.54))
            canopy.setColor(0.06, 0.72, 0.18, 0.42)
            canopy.setTransparency(TransparencyAttrib.MAlpha)

        # Desert now has small charging obelisks between pyramids so the laser
        # ring feels engineered without closing every path.
        for i in range(5):
            a = TAU * i / 5 + 0.96
            ob = make_pyramid_3d("desert-charge-obelisk", 0.22, 0.92, 4)
            ob.reparentTo(self.ring_root)
            ob.setPos(angle_to_pos(a, 24.9, RING_HEIGHTS["DESERT"] + 0.02))
            ob.setH(math.degrees(a) + 45)
            ob.setColor(1.0, 0.64, 0.16, 0.44)
            ob.setTransparency(TransparencyAttrib.MAlpha)
            add_circle_line(ob, "obelisk-charge-ring", 0.36, (1.0, 0.78, 0.18, 0.20), 0.55, 0.50, 24)

        # Urban shoreline barricades reinforce that robots defend but do not
        # cross the Water barrier.
        for i in range(12):
            a = TAU * i / 12 + 0.12
            wall = make_box("urban-barricade", 0.92, 0.18, 0.30)
            wall.reparentTo(self.ring_root)
            wall.setPos(angle_to_pos(a, 31.25, RING_HEIGHTS["URBAN"] + 0.02))
            wall.setH(math.degrees(a) + 90)
            wall.setColor(0.14, 0.44, 0.54, 0.48)
            wall.setTransparency(TransparencyAttrib.MAlpha)

        # Metropolis crown spires make the hostile source taller and easier to
        # identify from oblique orbit angles.
        for i in range(8):
            a = TAU * i / 8 + 0.31
            spire = make_pyramid_3d("metro-red-spire", 0.38, 1.75 + (i % 3) * 0.32, 5)
            spire.reparentTo(self.ring_root)
            spire.setPos(angle_to_pos(a, 41.0, RING_HEIGHTS["METROPOLIS"] + 0.02))
            spire.setColor(0.86, 0.04, 0.22, 0.56)
            spire.setTransparency(TransparencyAttrib.MAlpha)

        # Core receives layered hologram ribs so the protected hub reads in 3D.
        for i in range(6):
            a = TAU * i / 6
            add_line(self.ring_root, "core-shield-rib", angle_to_pos(a, 1.15, RING_HEIGHTS["CORE"] + 0.32), angle_to_pos(a + 0.20, 2.95, RING_HEIGHTS["CORE"] + 1.16), (0.24, 1.0, 1.0, 0.23), 0.82)

        # Hills ridges and mushroom low mounds make the mid-rings feel vertical.
        for i in range(10):
            a = TAU * i / 10 + 0.20
            ridge = make_pyramid_3d("hills-ridge", 0.72, 0.46 + (i % 2) * 0.22, 5)
            ridge.reparentTo(self.ring_root)
            ridge.setPos(angle_to_pos(a, 13.3 + (i % 3) * 0.75, RING_HEIGHTS["HILLS"] + 0.02))
            ridge.setColor(0.42, 0.72, 0.15, 0.42)
            ridge.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(8):
            a = TAU * i / 8 + 0.39
            mound = make_cylinder("mushroom-mound", 0.62, 0.24 + (i % 2) * 0.10, 16)
            mound.reparentTo(self.ring_root)
            mound.setPos(angle_to_pos(a, 18.7 + (i % 2) * 1.1, RING_HEIGHTS["MUSHROOM"] + 0.02))
            mound.setColor(0.44, 0.08, 0.52, 0.36)
            mound.setTransparency(TransparencyAttrib.MAlpha)

        # Pass 17 density: extra static silhouettes per ring. They are
        # flattened into the board after construction for lower runtime cost.
        for i in range(18):
            a = TAU * i / 18 + 0.07
            r = 7.0 + (i % 5) * 0.78
            trunk = make_cylinder("forest-extra-trunk", 0.08, 0.50 + (i % 3) * 0.08, 8)
            trunk.reparentTo(self.ring_root)
            trunk.setPos(angle_to_pos(a, r, RING_HEIGHTS["FOREST"] + 0.02))
            trunk.setColor(0.34, 0.18, 0.08, 0.68)
            crown = make_pyramid_3d("forest-extra-crown", 0.34 + (i % 2) * 0.07, 0.82, 5)
            crown.reparentTo(self.ring_root)
            crown.setPos(angle_to_pos(a, r, RING_HEIGHTS["FOREST"] + 0.42))
            crown.setColor(0.06, 0.86, 0.26, 0.42)
        for i in range(14):
            a = TAU * i / 14 + 0.20
            r = 12.0 + (i % 4) * 0.92
            ridge = make_box("hills-extra-ridge", 0.75, 0.20, 0.18 + (i % 3) * 0.07)
            ridge.reparentTo(self.ring_root)
            ridge.setPos(angle_to_pos(a, r, RING_HEIGHTS["HILLS"] + 0.03))
            ridge.setH(math.degrees(a) + 90)
            ridge.setColor(0.58, 0.95, 0.18, 0.34)
        for i in range(18):
            a = TAU * i / 18 + 0.28
            r = 16.8 + (i % 4) * 0.92
            stalk = make_cylinder("mushroom-extra-stalk", 0.12, 0.46, 10)
            stalk.reparentTo(self.ring_root)
            stalk.setPos(angle_to_pos(a, r, RING_HEIGHTS["MUSHROOM"] + 0.02))
            stalk.setColor(0.78, 0.42, 0.86, 0.40)
            cap = make_cylinder("mushroom-extra-cap", 0.32, 0.10, 14)
            cap.reparentTo(self.ring_root)
            cap.setPos(angle_to_pos(a, r, RING_HEIGHTS["MUSHROOM"] + 0.48))
            cap.setColor(1.0, 0.20, 0.86, 0.42)
        for i in range(14):
            a = TAU * i / 14 + 0.13
            r = 21.8 + (i % 5) * 0.76
            shard = make_pyramid_3d("desert-energy-shard", 0.22, 0.68 + (i % 3) * 0.10, 4)
            shard.reparentTo(self.ring_root)
            shard.setPos(angle_to_pos(a, r, RING_HEIGHTS["DESERT"] + 0.03))
            shard.setH(45 + math.degrees(a))
            shard.setColor(1.0, 0.58, 0.12, 0.34)
        for i in range(18):
            a = TAU * i / 18 + 0.04
            r0 = 26.4 + (i % 4) * 1.05
            add_line(
                self.ring_root,
                "water-extra-current",
                angle_to_pos(a - 0.018, r0, RING_HEIGHTS["WATER"] + 0.16),
                angle_to_pos(a + 0.018, r0 + 0.55, RING_HEIGHTS["WATER"] + 0.16),
                (0.25, 0.88, 1.0, 0.22),
                0.62,
            )
        for i in range(16):
            a = TAU * i / 16 + 0.16
            r = 31.6 + (i % 5) * 0.72
            barricade = make_box("urban-extra-barricade", 0.62, 0.16, 0.36)
            barricade.reparentTo(self.ring_root)
            barricade.setPos(angle_to_pos(a, r, RING_HEIGHTS["URBAN"] + 0.03))
            barricade.setH(math.degrees(a) + 90)
            barricade.setColor(0.16, 0.74, 0.92, 0.30)
        for i in range(18):
            a = TAU * i / 18 + 0.09
            r = 36.7 + (i % 6) * 0.78
            spire = make_box("metro-extra-spire", 0.24, 0.24, 0.82 + (i % 5) * 0.22)
            spire.reparentTo(self.ring_root)
            spire.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.02))
            spire.setH(math.degrees(a))
            spire.setColor(0.70, 0.10, 0.98, 0.36)

        # Pass 18: extra region-specific 3D set dressing. These are static,
        # low-poly generated meshes that flatten with the board. They add
        # density without adding per-frame update work.
        # Flat/Core artifact plaza pedestals.
        for i in range(8):
            a = TAU * i / 8 + 0.16
            pad = make_cylinder("flat-artifact-pad", 0.46, 0.16, 18)
            pad.reparentTo(self.ring_root)
            pad.setPos(angle_to_pos(a, 4.55, RING_HEIGHTS["FLAT"] + 0.02))
            pad.setColor(0.62, 0.88, 1.0, 0.34)
            pad.setTransparency(TransparencyAttrib.MAlpha)
            add_circle_line(pad, "flat-pad-ring", 0.58, (0.35, 1.0, 1.0, 0.18), 0.55, 0.19, 32)

        # Forest has denser nurseries and supply towers.
        for i in range(12):
            a = TAU * i / 12 + 0.19
            r = 6.75 + (i % 4) * 1.02
            nursery = make_box("forest-nursery-shelf", 0.72, 0.22, 0.16 + (i % 2) * 0.08)
            nursery.reparentTo(self.ring_root)
            nursery.setPos(angle_to_pos(a, r, RING_HEIGHTS["FOREST"] + 0.04))
            nursery.setH(math.degrees(a) + 90)
            nursery.setColor(0.08, 0.82, 0.24, 0.28)
            nursery.setTransparency(TransparencyAttrib.MAlpha)

        # Hills wildlife dens and caretaker posts.
        for i in range(10):
            a = TAU * i / 10 + 0.06
            r = 11.9 + (i % 4) * 1.0
            den = make_cylinder("hills-wildlife-den", 0.36 + (i % 2) * 0.08, 0.18, 12)
            den.reparentTo(self.ring_root)
            den.setPos(angle_to_pos(a, r, RING_HEIGHTS["HILLS"] + 0.03))
            den.setColor(0.58, 0.94, 0.18, 0.32)
            den.setTransparency(TransparencyAttrib.MAlpha)
            post = make_pyramid_3d("hills-caretaker-totem", 0.16, 0.58, 4)
            post.reparentTo(self.ring_root)
            post.setPos(angle_to_pos(a + 0.055, r + 0.38, RING_HEIGHTS["HILLS"] + 0.04))
            post.setColor(0.76, 1.0, 0.28, 0.34)
            post.setTransparency(TransparencyAttrib.MAlpha)

        # Mushroom warning vents show where confusion traps can regrow.
        for i in range(10):
            a = TAU * i / 10 + 0.24
            r = 16.6 + (i % 5) * 0.82
            vent = make_cylinder("mushroom-spore-vent", 0.18, 0.42 + (i % 2) * 0.12, 10)
            vent.reparentTo(self.ring_root)
            vent.setPos(angle_to_pos(a, r, RING_HEIGHTS["MUSHROOM"] + 0.03))
            vent.setColor(0.82, 0.22, 1.0, 0.30)
            vent.setTransparency(TransparencyAttrib.MAlpha)

        # Desert laser relay stones between pyramid lanes; still leaves gaps.
        for i in range(10):
            a = TAU * i / 10 + 0.04
            r = 21.6 + (i % 4) * 1.0
            relay = make_pyramid_3d("desert-laser-relay", 0.18, 0.82, 4)
            relay.reparentTo(self.ring_root)
            relay.setPos(angle_to_pos(a, r, RING_HEIGHTS["DESERT"] + 0.04))
            relay.setH(45 + math.degrees(a))
            relay.setColor(1.0, 0.70, 0.18, 0.30)
            relay.setTransparency(TransparencyAttrib.MAlpha)

        # Water docks/vessel-build silhouettes where enemies pause to cross.
        for i in range(8):
            a = TAU * i / 8 + 0.22
            dock = make_box("water-vessel-dock", 0.84, 0.16, 0.10)
            dock.reparentTo(self.ring_root)
            dock.setPos(angle_to_pos(a, RINGS["WATER"]["outer"] - 0.48, RING_HEIGHTS["WATER"] + 0.10))
            dock.setH(math.degrees(a) + 90)
            dock.setColor(0.22, 0.82, 1.0, 0.28)
            dock.setTransparency(TransparencyAttrib.MAlpha)

        # Urban hangars and repair gantries behind the shoreline barricades.
        for i in range(10):
            a = TAU * i / 10 + 0.28
            r = 32.1 + (i % 3) * 1.15
            hangar = make_box("urban-robot-hangar", 0.84, 0.46, 0.46 + (i % 2) * 0.16)
            hangar.reparentTo(self.ring_root)
            hangar.setPos(angle_to_pos(a, r, RING_HEIGHTS["URBAN"] + 0.04))
            hangar.setH(math.degrees(a) + 90)
            hangar.setColor(0.12, 0.58, 0.72, 0.28)
            hangar.setTransparency(TransparencyAttrib.MAlpha)

        # Metropolis foundries: more vertical hostile source markers.
        for i in range(12):
            a = TAU * i / 12 + 0.02
            r = 37.2 + (i % 5) * 0.9
            foundry = make_box("metro-enemy-foundry", 0.36, 0.36, 0.92 + (i % 4) * 0.30)
            foundry.reparentTo(self.ring_root)
            foundry.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.03))
            foundry.setH(math.degrees(a))
            foundry.setColor(0.82, 0.08, 0.46, 0.30)
            foundry.setTransparency(TransparencyAttrib.MAlpha)

        # Pass 19: more dense static structures for each outer ring.
        for i in range(14):
            a = TAU * i / 14 + 0.11
            arbor = make_box("forest-arbor", 0.32, 0.32, 0.88 + (i % 3) * 0.16)
            arbor.reparentTo(self.ring_root)
            arbor.setPos(angle_to_pos(a, 7.2 + (i % 4) * 0.92, RING_HEIGHTS["FOREST"] + 0.04))
            arbor.setColor(0.10, 1.0, 0.36, 0.18)
            arbor.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(12):
            a = TAU * i / 12 + 0.24
            post = make_pyramid_3d("hills-watch-stone", 0.18, 0.74 + (i % 2) * 0.12, 4)
            post.reparentTo(self.ring_root)
            post.setPos(angle_to_pos(a, 12.3 + (i % 3) * 1.05, RING_HEIGHTS["HILLS"] + 0.04))
            post.setColor(0.78, 1.0, 0.28, 0.22)
            post.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(12):
            a = TAU * i / 12 + 0.34
            arch = make_pyramid_3d("mushroom-arch", 0.28, 0.98, 5)
            arch.reparentTo(self.ring_root)
            arch.setPos(angle_to_pos(a, 17.1 + (i % 4) * 0.84, RING_HEIGHTS["MUSHROOM"] + 0.04))
            arch.setColor(0.98, 0.24, 1.0, 0.18)
            arch.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(12):
            a = TAU * i / 12 + 0.10
            pylon = make_box("desert-pylon", 0.18, 0.18, 0.96 + (i % 3) * 0.18)
            pylon.reparentTo(self.ring_root)
            pylon.setPos(angle_to_pos(a, 22.2 + (i % 4) * 0.82, RING_HEIGHTS["DESERT"] + 0.04))
            pylon.setColor(1.0, 0.72, 0.22, 0.18)
            pylon.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(10):
            a = TAU * i / 10 + 0.03
            buoy = make_cylinder("water-buoy", 0.14, 0.38 + (i % 2) * 0.08, 10)
            buoy.reparentTo(self.ring_root)
            buoy.setPos(angle_to_pos(a, 28.0 + (i % 3) * 0.9, RING_HEIGHTS["WATER"] + 0.04))
            buoy.setColor(0.32, 0.94, 1.0, 0.20)
            buoy.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(12):
            a = TAU * i / 12 + 0.17
            gantry = make_box("urban-turret-block", 0.26, 0.26, 0.82 + (i % 2) * 0.14)
            gantry.reparentTo(self.ring_root)
            gantry.setPos(angle_to_pos(a, 33.0 + (i % 4) * 0.68, RING_HEIGHTS["URBAN"] + 0.04))
            gantry.setColor(0.16, 0.92, 1.0, 0.18)
            gantry.setTransparency(TransparencyAttrib.MAlpha)
        for i in range(14):
            a = TAU * i / 14 + 0.14
            gate = make_pyramid_3d("metro-gateway", 0.26, 1.18 + (i % 3) * 0.22, 4)
            gate.reparentTo(self.ring_root)
            gate.setPos(angle_to_pos(a, 38.2 + (i % 4) * 0.86, RING_HEIGHTS["METROPOLIS"] + 0.04))
            gate.setColor(0.82, 0.14, 1.0, 0.18)
            gate.setTransparency(TransparencyAttrib.MAlpha)

        # Pass 21: Metropolis becomes a dense enemy city with skyscraper walls,
        # stacked spawn pads, skyline bridges, and Urban frontline war clutter.
        for i in range(32):
            a = TAU * i / 32 + 0.03
            r = 37.6 + (i % 6) * 0.95
            height = 1.30 + (i % 7) * 0.34
            tower = make_box("metro-mega-scraper", 0.42 + (i % 2) * 0.08, 0.42 + (i % 3) * 0.06, height)
            tower.reparentTo(self.ring_root)
            tower.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.05))
            tower.setH(math.degrees(a) + (i % 2) * 14)
            tower.setColor(0.66, 0.10, 0.96, 0.24)
            tower.setTransparency(TransparencyAttrib.MAlpha)
            if i % 3 == 0:
                crown = make_box("metro-crown-light", 0.20, 0.20, 0.12)
                crown.reparentTo(self.ring_root)
                crown.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.05 + height + 0.08))
                crown.setColor(1.0, 0.18, 0.38, 0.32)
                crown.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(18):
            a = TAU * i / 18 + 0.18
            r0 = 37.2 + (i % 4) * 1.08
            r1 = r0 + 1.35
            z = RING_HEIGHTS["METROPOLIS"] + 1.05 + (i % 3) * 0.42
            add_line(self.ring_root, "metro-skybridge", angle_to_pos(a, r0, z), angle_to_pos(a + 0.05, r1, z + 0.10), (0.90, 0.16, 0.44, 0.18), 0.72)

        for i in range(14):
            a = TAU * i / 14 + 0.12
            pad = make_cylinder("metro-spawn-pad", 0.44 + (i % 2) * 0.06, 0.14, 16)
            pad.reparentTo(self.ring_root)
            pad.setPos(angle_to_pos(a, 41.4 + (i % 3) * 0.55, RING_HEIGHTS["METROPOLIS"] + 0.04))
            pad.setColor(0.92, 0.10, 0.30, 0.24)
            pad.setTransparency(TransparencyAttrib.MAlpha)
            add_circle_line(pad, "metro-spawn-ring", 0.60, (1.0, 0.20, 0.42, 0.22), 0.55, 0.16, 28)

        for i in range(18):
            a = TAU * i / 18 + 0.16
            bunker = make_box("urban-war-bunker", 0.66, 0.26, 0.42 + (i % 2) * 0.08)
            bunker.reparentTo(self.ring_root)
            bunker.setPos(angle_to_pos(a, 32.0 + (i % 5) * 0.64, RING_HEIGHTS["URBAN"] + 0.05))
            bunker.setH(math.degrees(a) + 90)
            bunker.setColor(0.14, 0.76, 0.96, 0.24)
            bunker.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(12):
            a = TAU * i / 12 + 0.04
            tower = make_box("urban-watch-tower", 0.24, 0.24, 0.92 + (i % 3) * 0.18)
            tower.reparentTo(self.ring_root)
            tower.setPos(angle_to_pos(a, 34.6 + (i % 3) * 0.54, RING_HEIGHTS["URBAN"] + 0.05))
            tower.setColor(0.18, 0.92, 1.0, 0.22)
            tower.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(10):
            a = TAU * i / 10 + 0.10
            add_line(self.ring_root, "urban-crossfire", angle_to_pos(a, 30.8, RING_HEIGHTS["URBAN"] + 0.48), angle_to_pos(a + 0.18, 34.2, RING_HEIGHTS["URBAN"] + 0.72), (0.18, 0.92, 1.0, 0.14), 0.72)

        # Pass 22: Metropolis focused polish. Dense low-poly city blocks, mega towers,
        # factory stacks, spawn beacons, and Urban edge cover make this area read as
        # the enemy production city pushing into a defensive warfront.
        for i in range(48):
            a = TAU * i / 48 + 0.025
            r = 36.65 + (i % 8) * 0.70
            height = 0.72 + (i % 9) * 0.32
            width = 0.18 + (i % 4) * 0.055
            block = make_box("metro-dense-block", width, width * 1.18, height)
            block.reparentTo(self.ring_root)
            block.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.055))
            block.setH(math.degrees(a) + (i % 5) * 8)
            block.setColor(0.70, 0.12, 1.0, 0.36 + (i % 3) * 0.04)
            block.setTransparency(TransparencyAttrib.MAlpha)
            if i % 4 == 0:
                antenna = make_pyramid_3d("metro-rooftop-antenna", 0.055, 0.52 + (i % 3) * 0.18, 4)
                antenna.reparentTo(self.ring_root)
                antenna.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + height + 0.13))
                antenna.setColor(1.0, 0.22, 0.44, 0.58)
                antenna.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(9):
            a = TAU * i / 9 + 0.18
            r = 39.0 + (i % 3) * 1.05
            height = 3.15 + (i % 4) * 0.62
            mega = make_box("metro-landmark-skyscraper", 0.58, 0.58, height)
            mega.reparentTo(self.ring_root)
            mega.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.08))
            mega.setH(math.degrees(a) + 22)
            mega.setColor(0.88, 0.12, 1.0, 0.54)
            mega.setTransparency(TransparencyAttrib.MAlpha)
            crown = make_pyramid_3d("metro-landmark-crown", 0.38, 0.72, 5)
            crown.reparentTo(self.ring_root)
            crown.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + height + 0.16))
            crown.setColor(1.0, 0.18, 0.46, 0.64)
            crown.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(18):
            a = TAU * i / 18 + 0.08
            r = 40.3 + (i % 4) * 0.62
            stack = make_cylinder("metro-factory-stack", 0.12 + (i % 2) * 0.025, 1.20 + (i % 4) * 0.24, 10)
            stack.reparentTo(self.ring_root)
            stack.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.06))
            stack.setColor(1.0, 0.10, 0.32, 0.46)
            stack.setTransparency(TransparencyAttrib.MAlpha)
            if i % 2 == 0:
                cap = make_cylinder("metro-stack-glow", 0.18, 0.08, 12)
                cap.reparentTo(self.ring_root)
                cap.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 1.38 + (i % 4) * 0.24))
                cap.setColor(1.0, 0.24, 0.38, 0.62)
                cap.setTransparency(TransparencyAttrib.MAlpha)

        # Dynamic spawn pulses stay outside the flattened board so they can animate.
        for i in range(12):
            a = TAU * i / 12 + 0.10
            r = 41.2 + (i % 3) * 0.42
            pos = angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.22)
            pulse = add_circle_line(self.fx_root, "metro-spawn-pulse", 0.48 + (i % 2) * 0.16, (1.0, 0.12, 0.38, 0.26), 0.7, 0.0, 32)
            pulse.setPos(pos)
            pulse.setLightOff(1)
            self.metro_spawn_pulses.append({"node": pulse, "sim_pos": pos, "phase": i * 0.47, "base": 0.48 + (i % 2) * 0.16})

        for i in range(20):
            a = TAU * i / 20 + 0.04
            cover = make_box("urban-front-cover-line", 0.92, 0.18, 0.36 + (i % 3) * 0.08)
            cover.reparentTo(self.ring_root)
            cover.setPos(angle_to_pos(a, 35.2 + (i % 2) * 0.42, RING_HEIGHTS["URBAN"] + 0.06))
            cover.setH(math.degrees(a) + 90)
            cover.setColor(0.10, 0.84, 1.0, 0.36)
            cover.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(12):
            a = TAU * i / 12 + 0.02
            add_line(self.ring_root, "metro-invasion-arc", angle_to_pos(a, 42.3, RING_HEIGHTS["METROPOLIS"] + 1.26), angle_to_pos(a + 0.075, 35.9, RING_HEIGHTS["URBAN"] + 0.92), (1.0, 0.12, 0.36, 0.22), 0.92)

        # Pass 32: more Metropolis structure variants. These are still low-poly
        # and flattened with the static board, but they break up the skyline into
        # identifiable hostile districts: factories, data shrines, claw towers,
        # war silos, and launch arches tied back to enemy spawning logic.
        metro_variant_count = 0
        for i in range(24):
            a = TAU * i / 24 + 0.055
            r = 37.05 + (i % 6) * 0.88
            base_h = 0.34 + (i % 3) * 0.06
            hub = make_cylinder("metro-reactor-hub", 0.28 + (i % 3) * 0.035, base_h, 12)
            hub.reparentTo(self.ring_root)
            hub.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.05))
            hub.setColor(0.82, 0.08, 1.0, 0.32)
            hub.setTransparency(TransparencyAttrib.MAlpha)
            core = make_pyramid_3d("metro-reactor-core", 0.18 + (i % 2) * 0.035, 0.90 + (i % 4) * 0.18, 5)
            core.reparentTo(self.ring_root)
            core.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + base_h + 0.08))
            core.setH(math.degrees(a) + 36)
            core.setColor(1.0, 0.18, 0.48, 0.46)
            core.setTransparency(TransparencyAttrib.MAlpha)
            metro_variant_count += 2

        for i in range(18):
            a = TAU * i / 18 + 0.095
            r = 38.2 + (i % 5) * 0.82
            height = 1.55 + (i % 5) * 0.44
            shrine = make_box("metro-data-shrine", 0.22 + (i % 2) * 0.05, 0.46 + (i % 3) * 0.06, height)
            shrine.reparentTo(self.ring_root)
            shrine.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.07))
            shrine.setH(math.degrees(a) + 12 + (i % 4) * 9)
            shrine.setColor(0.52, 0.16, 1.0, 0.42)
            shrine.setTransparency(TransparencyAttrib.MAlpha)
            z0 = RING_HEIGHTS["METROPOLIS"] + 0.36
            z1 = RING_HEIGHTS["METROPOLIS"] + height + 0.28
            add_line(self.ring_root, "metro-data-window", angle_to_pos(a, r, z0), angle_to_pos(a, r, z1), (0.18, 1.0, 0.48, 0.26), 0.54)
            metro_variant_count += 2

        for i in range(14):
            a = TAU * i / 14 + 0.135
            r = 40.2 + (i % 4) * 0.58
            mast_h = 1.60 + (i % 4) * 0.34
            mast = make_box("metro-claw-mast", 0.18, 0.18, mast_h)
            mast.reparentTo(self.ring_root)
            mast.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.06))
            mast.setColor(0.94, 0.12, 0.36, 0.38)
            mast.setTransparency(TransparencyAttrib.MAlpha)
            for side in (-1, 1):
                claw = make_box("metro-claw-arm", 0.12, 0.62, 0.14)
                claw.reparentTo(self.ring_root)
                claw.setPos(angle_to_pos(a + side * 0.010, r + side * 0.10, RING_HEIGHTS["METROPOLIS"] + mast_h + 0.18))
                claw.setH(math.degrees(a) + 90 + side * 22)
                claw.setColor(1.0, 0.20, 0.46, 0.42)
                claw.setTransparency(TransparencyAttrib.MAlpha)
                metro_variant_count += 1
            metro_variant_count += 1

        for i in range(12):
            a = TAU * i / 12 + 0.075
            r0 = 39.6 + (i % 3) * 0.84
            r1 = r0 + 1.35
            z = RING_HEIGHTS["METROPOLIS"] + 2.15 + (i % 3) * 0.30
            arch_a = angle_to_pos(a - 0.018, r0, z - 0.34)
            arch_b = angle_to_pos(a + 0.018, r1, z + 0.28)
            add_line(self.ring_root, "metro-launch-arch", arch_a, arch_b, (1.0, 0.22, 0.42, 0.28), 1.08)
            add_line(self.ring_root, "metro-launch-arch-cross", angle_to_pos(a + 0.030, r0, z + 0.10), angle_to_pos(a - 0.030, r1, z - 0.16), (0.66, 0.16, 1.0, 0.22), 0.82)
            metro_variant_count += 2

        for i in range(10):
            a = TAU * i / 10 + 0.19
            r = 41.0 + (i % 3) * 0.44
            silo = make_cylinder("metro-war-silo", 0.20 + (i % 2) * 0.03, 1.18 + (i % 3) * 0.20, 10)
            silo.reparentTo(self.ring_root)
            silo.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.07))
            silo.setColor(1.0, 0.12, 0.28, 0.34)
            silo.setTransparency(TransparencyAttrib.MAlpha)
            cap = make_pyramid_3d("metro-war-silo-cap", 0.24, 0.40, 5)
            cap.reparentTo(self.ring_root)
            cap.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 1.34 + (i % 3) * 0.20))
            cap.setColor(1.0, 0.36, 0.18, 0.48)
            cap.setTransparency(TransparencyAttrib.MAlpha)
            metro_variant_count += 2

        # Extra live model-link pulses connect the new factories and silos to
        # the existing enemy squad spawn logic. They reuse the existing spawn
        # pulse updater, so no new per-frame system is needed.
        for i in range(8):
            a = TAU * i / 8 + 0.06
            r = 40.8 + (i % 2) * 0.74
            pos = angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.42)
            pulse = add_circle_line(self.fx_root, "metro-factory-pulse", 0.36 + (i % 2) * 0.10, (1.0, 0.18, 0.42, 0.22), 0.62, 0.0, 32)
            pulse.setPos(pos)
            pulse.setLightOff(1)
            self.metro_spawn_pulses.append({"node": pulse, "sim_pos": pos, "phase": i * 0.58 + 1.7, "base": 0.36 + (i % 2) * 0.10})
            metro_variant_count += 1

        self.stats["metro_variant_structures"] = metro_variant_count

    def build_logic_model_links(self):
        """Static/dynamic visual links that make the model layer match the RTS rules.

        This keeps the isolated branch readable: every major gameplay rule has a
        visible connection between the regions that participate in it.
        """
        self.logic_pulses.clear()
        link_specs = [
            ("METROPOLIS", "URBAN", 5.18, 41.6, 34.6, "ENEMY SPAWN -> URBAN WAR", (1.0, 0.14, 0.34, 0.34)),
            ("URBAN", "WATER", 4.72, 34.2, 29.0, "ROBOTS HOLD SHORE", (0.18, 0.92, 1.0, 0.28)),
            ("WATER", "DESERT", 4.23, 28.6, 24.0, "VESSELS SLOW", (0.34, 0.92, 1.0, 0.22)),
            ("DESERT", "MUSHROOM", 3.72, 24.0, 18.6, "LASERS SCREEN", (1.0, 0.70, 0.18, 0.28)),
            ("MUSHROOM", "HILLS", 3.20, 18.5, 13.3, "SPORES CONFUSE", (1.0, 0.24, 0.92, 0.25)),
            ("FOREST", "HILLS", 2.52, 8.0, 13.1, "SUPPLY GROWS WILDLIFE", (0.18, 1.0, 0.34, 0.34)),
            ("FLAT", "CORE", 1.92, 4.9, 2.6, "ARTIFACTS DEFEND HUB", (0.48, 1.0, 1.0, 0.32)),
        ]
        for idx, (src, dst, angle, r0, r1, label, color) in enumerate(link_specs):
            z0 = RING_HEIGHTS[src] + 0.82
            z1 = RING_HEIGHTS[dst] + 0.82
            a0 = angle
            a1 = angle + 0.045
            p0 = angle_to_pos(a0, r0, z0)
            p1 = angle_to_pos((a0 + a1) * 0.5, (r0 + r1) * 0.5, (z0 + z1) * 0.5 + 0.54)
            p2 = angle_to_pos(a1, r1, z1)
            add_line(self.ring_root, f"logic-link-{src}-{dst}-a", p0, p1, color, 1.05)
            add_line(self.ring_root, f"logic-link-{src}-{dst}-b", p1, p2, color, 1.05)
            # A small status beacon at each connection endpoint stays animated so
            # the logic layer reads even after the board geometry is flattened.
            beacon = add_circle_line(self.fx_root, f"logic-pulse-{src}-{dst}", 0.42, color, 0.65, 0.0, 28)
            beacon.setPos(p1)
            beacon.setLightOff(1)
            self.logic_pulses.append({"node": beacon, "phase": idx * 0.64, "alpha": max(0.10, color[3])})
            self.add_label(f"logic-label-{src}-{dst}", label, Vec3(p1.x, p1.y, p1.z + 0.58), 0.34, (color[0], color[1], color[2], 0.76))

        # Extra generated detail connected to the rules in the inner regions.
        # Forest supply roots point to Hills wildlife growth.
        for i in range(9):
            a = TAU * i / 9 + 0.18
            add_line(self.ring_root, "forest-hills-rootlink", angle_to_pos(a, 8.0 + (i % 2) * 0.8, RING_HEIGHTS["FOREST"] + 0.46), angle_to_pos(a + 0.035, 12.0 + (i % 3) * 0.65, RING_HEIGHTS["HILLS"] + 0.48), (0.18, 1.0, 0.28, 0.14), 0.72)
        # Desert targeting rails aim pyramid logic toward the path enemies use after Water.
        for i in range(9):
            a = TAU * i / 9 + 0.34
            add_line(self.ring_root, "desert-pyramid-target-rail", angle_to_pos(a, 23.55, RING_HEIGHTS["DESERT"] + 0.86), angle_to_pos(a + 0.06, 21.1, RING_HEIGHTS["DESERT"] + 0.72), (1.0, 0.80, 0.20, 0.16), 0.72)
        # Water docks now visually connect to the slow vessel corridor.
        for i in range(8):
            a = TAU * i / 8 + 0.22
            add_line(self.ring_root, "water-vessel-corridor", angle_to_pos(a, 30.6, RING_HEIGHTS["WATER"] + 0.34), angle_to_pos(a + 0.04, 26.4, RING_HEIGHTS["WATER"] + 0.36), (0.26, 0.86, 1.0, 0.16), 0.78)

    def build_region_status_pulses(self):
        """Animated status rings that bind current logic to region models."""
        self.region_status_pulses.clear()
        status_specs = [
            ("METROPOLIS", 41.0, 5.02, (1.0, 0.14, 0.34, 0.28), "SPAWN"),
            ("URBAN", 33.4, 5.42, (0.18, 0.92, 1.0, 0.24), "FRONT"),
            ("WATER", 28.5, 4.86, (0.32, 0.90, 1.0, 0.22), "VESSELS"),
            ("DESERT", 23.5, 4.36, (1.0, 0.72, 0.20, 0.24), "LASERS"),
            ("MUSHROOM", 18.7, 3.72, (1.0, 0.24, 0.92, 0.22), "SPORES"),
            ("HILLS", 13.5, 3.12, (0.78, 1.0, 0.24, 0.22), "WILDLIFE"),
            ("FOREST", 8.2, 2.54, (0.18, 1.0, 0.34, 0.24), "SUPPLY"),
            ("FLAT", 4.8, 2.02, (0.52, 1.0, 1.0, 0.24), "ARTIFACTS"),
        ]
        for idx, (region, radius, angle, color, label) in enumerate(status_specs):
            pos = angle_to_pos(angle, radius, RING_HEIGHTS[region] + 0.28)
            ring = add_circle_line(self.fx_root, f"region-status-{region}", 0.64, color, 0.78, 0.0, 32)
            ring.setPos(pos)
            ring.setLightOff(1)
            self.region_status_pulses.append({"region": region, "node": ring, "phase": idx * 0.55, "base_alpha": color[3]})
            self.add_label(f"status-label-{region}", label, Vec3(pos.x, pos.y, pos.z + 0.44), 0.28, (color[0], color[1], color[2], 0.70))

    def build_battlefront_pulses(self):
        """Readable battlefield beacons at the important conflict seams.

        These are visual-only and animate from current simulation pressure so
        the large overview still communicates where the RTS logic is active.
        """
        self.battlefront_pulses.clear()
        specs = [
            ("METROPOLIS", "URBAN", 5.16, 36.2, (1.0, 0.18, 0.34, 0.24), "METRO FRONT"),
            ("URBAN", "WATER", 4.72, 31.2, (0.18, 0.94, 1.0, 0.22), "SHORE HOLD"),
            ("WATER", "DESERT", 4.25, 26.1, (0.34, 0.92, 1.0, 0.20), "VESSEL CROSS"),
            ("DESERT", "MUSHROOM", 3.76, 21.0, (1.0, 0.72, 0.20, 0.22), "LASER SCREEN"),
            ("MUSHROOM", "HILLS", 3.22, 16.0, (1.0, 0.26, 0.94, 0.20), "SPORE BREAK"),
            ("FOREST", "HILLS", 2.68, 10.9, (0.22, 1.0, 0.34, 0.24), "WILDLIFE SUPPLY"),
            ("FLAT", "CORE", 1.96, 3.25, (0.54, 1.0, 1.0, 0.24), "CORE LAST STAND"),
        ]
        for idx, (a_region, b_region, angle, radius, color, label) in enumerate(specs):
            z = max(RING_HEIGHTS[a_region], RING_HEIGHTS[b_region]) + 0.72
            pos = angle_to_pos(angle, radius, z)
            ring = add_circle_line(self.fx_root, f"battlefront-{label}", 0.88, color, 0.82, 0.0, 36)
            ring.setPos(pos)
            ring.setLightOff(1)
            self.battlefront_pulses.append({"node": ring, "regions": (a_region, b_region), "phase": idx * 0.42, "label": label})
            self.add_label(f"battlefront-label-{idx}", label, Vec3(pos.x, pos.y, pos.z + 0.54), 0.26, (color[0], color[1], color[2], 0.72))

    def build_command_pulses(self):
        """Player command relays: visible RTS control anchors for the active loop."""
        self.command_pulses.clear()
        specs = [
            ("URBAN", 34.8, 4.92, "1 RALLY", (0.18, 0.94, 1.0, 0.28)),
            ("DESERT", 23.8, 4.08, "2 LASERS", (1.0, 0.72, 0.18, 0.28)),
            ("MUSHROOM", 18.8, 3.52, "3 SPORES", (1.0, 0.22, 0.92, 0.24)),
            ("FOREST", 8.6, 2.42, "4 SUPPLY", (0.18, 1.0, 0.34, 0.28)),
            ("FLAT", 5.2, 1.68, "5 REPAIR", (0.52, 1.0, 1.0, 0.30)),
        ]
        for idx, (region, radius, angle, label, color) in enumerate(specs):
            pos = angle_to_pos(angle, radius, RING_HEIGHTS[region] + 1.06)
            ring = add_circle_line(self.fx_root, f"command-relay-{region}", 0.78, color, 0.92, 0.0, 36)
            ring.setPos(pos)
            ring.setLightOff(1)
            self.command_pulses.append({"region": region, "node": ring, "phase": idx * 0.71, "label": label, "base_color": color})
            self.add_label(f"command-label-{region}", label, Vec3(pos.x, pos.y, pos.z + 0.56), 0.28, (color[0], color[1], color[2], 0.76))

    def build_combat_readability_overlays(self):
        """Pass 35 combat readability layer.

        These animated overlays are separate from the static geometry: red alert
        rings show regions under pressure, red arrows show invasion direction,
        and cyan arrows show which defense layer answers that pressure.
        """
        self.region_alert_pulses.clear()
        self.attack_vector_pulses.clear()
        self.defense_vector_pulses.clear()
        alert_specs = [
            ("METROPOLIS", 39.2, 0.05, (1.0, 0.12, 0.34, 0.22)),
            ("URBAN", 33.8, 0.36, (0.18, 0.94, 1.0, 0.20)),
            ("WATER", 28.6, 0.78, (0.20, 0.84, 1.0, 0.20)),
            ("DESERT", 23.8, 1.22, (1.0, 0.68, 0.18, 0.20)),
            ("MUSHROOM", 18.8, 1.72, (1.0, 0.22, 0.92, 0.18)),
            ("HILLS", 13.8, 2.22, (0.72, 1.0, 0.22, 0.18)),
            ("FOREST", 8.6, 2.78, (0.18, 1.0, 0.34, 0.18)),
            ("FLAT", 4.8, 3.32, (0.52, 1.0, 1.0, 0.22)),
        ]
        for idx, (region, radius, angle, color) in enumerate(alert_specs):
            pos = angle_to_pos(angle, radius, RING_HEIGHTS[region] + 1.28)
            ring = add_circle_line(self.fx_root, f"alert-ring-{region}", 1.15, color, 1.02, 0.0, 44)
            ring.setPos(pos)
            ring.setLightOff(1)
            ring.setTransparency(TransparencyAttrib.MAlpha)
            self.region_alert_pulses.append({"region": region, "node": ring, "phase": idx * 0.43, "base_alpha": color[3]})

        def make_arrow_group(name: str, a: Vec3, b: Vec3, color, phase: float, role: str, regions: tuple[str, str]):
            group = self.fx_root.attachNewNode(name)
            main = add_line(group, f"{name}-main", a, b, color, 1.25)
            direction = b - a
            if direction.lengthSquared() > 0.001:
                direction.normalize()
            side = Vec3(-direction.y, direction.x, 0.0)
            head_center = b - direction * 0.72
            add_line(group, f"{name}-head-a", b, head_center + side * 0.42, color, 1.10)
            add_line(group, f"{name}-head-b", b, head_center - side * 0.42, color, 1.10)
            group.setLightOff(1)
            group.setTransparency(TransparencyAttrib.MAlpha)
            payload = {"node": group, "phase": phase, "regions": regions, "role": role, "base_alpha": color[3]}
            if role == "attack":
                self.attack_vector_pulses.append(payload)
            else:
                self.defense_vector_pulses.append(payload)

        # Invasion route: enemy pressure from Metropolis down toward the Core.
        attack_route = [
            ("METROPOLIS", "URBAN", 40.6, 34.0, 0.16),
            ("URBAN", "WATER", 33.8, 29.0, 0.42),
            ("WATER", "DESERT", 28.8, 24.0, 0.70),
            ("DESERT", "MUSHROOM", 24.0, 19.0, 0.98),
            ("MUSHROOM", "HILLS", 19.0, 14.0, 1.26),
            ("HILLS", "FOREST", 14.0, 8.8, 1.54),
            ("FOREST", "FLAT", 8.8, 4.6, 1.82),
        ]
        for idx, (src, dst, r0, r1, angle) in enumerate(attack_route):
            make_arrow_group(
                f"attack-vector-{src}-{dst}",
                angle_to_pos(angle, r0, RING_HEIGHTS[src] + 1.52),
                angle_to_pos(angle, r1, RING_HEIGHTS[dst] + 1.70),
                (1.0, 0.16, 0.34, 0.32),
                idx * 0.38,
                "attack",
                (src, dst),
            )

        # Defensive responses: readable counterflow from each defending region.
        defense_route = [
            ("URBAN", "METROPOLIS", 32.2, 36.6, 3.36),
            ("DESERT", "WATER", 22.6, 26.8, 3.78),
            ("MUSHROOM", "DESERT", 17.8, 21.8, 4.18),
            ("HILLS", "MUSHROOM", 12.8, 16.8, 4.58),
            ("FOREST", "HILLS", 7.6, 11.8, 4.96),
            ("FLAT", "CORE", 4.8, 2.6, 5.32),
        ]
        for idx, (src, dst, r0, r1, angle) in enumerate(defense_route):
            make_arrow_group(
                f"defense-vector-{src}-{dst}",
                angle_to_pos(angle, r0, RING_HEIGHTS[src] + 1.42),
                angle_to_pos(angle, r1, RING_HEIGHTS[dst] + 1.62),
                (0.20, 1.0, 0.92, 0.28),
                idx * 0.51,
                "defense",
                (src, dst),
            )

    def region_activity_level(self, region: str) -> float:
        if region == "METROPOLIS":
            return clamp(len(self.enemies) / 64.0 + float(self.stats.get("enemies_spawned", 0) % 8) * 0.015, 0.12, 1.0)
        if region == "URBAN":
            nearby = sum(1 for e in self.enemies if self.region_for_radius(pos_radius(e.pos)) == "URBAN")
            return clamp(nearby / 8.0 + len(self.urban_troops) / 56.0, 0.10, 1.0)
        if region == "WATER":
            building = sum(1 for e in self.enemies if e.state == "building_vessel" or e.state == "crossing_water")
            return clamp(building / 6.0 + self.stats.get("water_vessels", 0) % 5 * 0.04, 0.10, 1.0)
        if region == "DESERT":
            return clamp((self.stats.get("laser_hits", 0) % 18) / 18.0 + len(self.pyramids) / 18.0, 0.12, 1.0)
        if region == "MUSHROOM":
            confused = sum(1 for e in self.enemies if e.state == "confused")
            return clamp(confused / 6.0 + (self.stats.get("spore_explosions", 0) % 10) * 0.04, 0.10, 1.0)
        if region == "HILLS":
            avg = sum(w.growth for w in self.wildlife) / max(1, len(self.wildlife))
            return clamp(avg + (0.25 if self.forest_attack_timer > 0 else 0.0), 0.12, 1.0)
        if region == "FOREST":
            damaged = sum(1 for p in self.forest_plants if p.state == "regrowing")
            return clamp(0.18 + damaged / max(1, len(self.forest_plants)) + (0.35 if self.forest_attack_timer > 0 else 0.0), 0.12, 1.0)
        if region == "FLAT":
            active = sum(1 for a in self.artifacts if a.hp > 0)
            return clamp(1.0 - active / 8.0 + 0.18, 0.12, 1.0)
        return 0.12

        # Pass 25: dedicated enemy troop assembly details, tied to the actual
        # squad-spawn logic below. These stay static/low-poly but make the
        # Metropolis source read as a military production ring.
        for i in range(12):
            a = TAU * i / 12 + 0.06
            r = 40.1 + (i % 4) * 0.72
            rack = make_box("metro-troop-rack", 0.30, 0.92, 0.26)
            rack.reparentTo(self.ring_root)
            rack.setPos(angle_to_pos(a, r, RING_HEIGHTS["METROPOLIS"] + 0.10))
            rack.setH(math.degrees(a) + 90)
            rack.setColor(1.0, 0.16, 0.36, 0.18)
            rack.setTransparency(TransparencyAttrib.MAlpha)
            for j in range(3):
                pod = make_cylinder("metro-troop-pod", 0.12 + 0.02 * (j % 2), 0.34, 8)
                pod.reparentTo(self.ring_root)
                off = (j - 1) * 0.28
                pos = angle_to_pos(a + off / max(1.0, r), r + (j - 1) * 0.12, RING_HEIGHTS["METROPOLIS"] + 0.34)
                pod.setPos(pos)
                pod.setColor(1.0, 0.12, 0.26 + j * 0.12, 0.24)
                pod.setTransparency(TransparencyAttrib.MAlpha)

        for i in range(8):
            a = TAU * i / 8 + 0.20
            # visible squad lane markers match the eight active spawn gates.
            add_line(self.ring_root, "metro-squad-rail", angle_to_pos(a - 0.035, 42.3, RING_HEIGHTS["METROPOLIS"] + 0.34), angle_to_pos(a + 0.035, 38.2, RING_HEIGHTS["METROPOLIS"] + 0.86), (1.0, 0.22, 0.34, 0.30), 1.05)
            add_line(self.ring_root, "metro-squad-rail-side", angle_to_pos(a + 0.055, 42.0, RING_HEIGHTS["METROPOLIS"] + 0.18), angle_to_pos(a + 0.10, 38.8, RING_HEIGHTS["METROPOLIS"] + 0.58), (1.0, 0.48, 0.12, 0.16), 0.75)

        # Pass 26: expansion-fill set dressing on every ring. These pieces are
        # intentionally static/low-poly and flatten with the board so the larger
        # battlefield does not look empty.
        for idx, name in enumerate(["FOREST", "HILLS", "MUSHROOM", "DESERT", "WATER", "URBAN", "METROPOLIS"]):
            spec = RINGS[name]
            mid = (spec["inner"] + spec["outer"]) * 0.5
            color = spec["color"]
            count = 10 if name not in {"URBAN", "METROPOLIS"} else 16
            for j in range(count):
                a = TAU * j / count + 0.05 * idx
                r = spec["inner"] + 0.62 + (j % 5) * max(0.45, (spec["outer"] - spec["inner"] - 1.2) / 5.0)
                if name == "WATER":
                    add_line(self.ring_root, "expanded-water-motion", angle_to_pos(a - 0.025, r, RING_HEIGHTS[name] + 0.21), angle_to_pos(a + 0.025, r + 0.65, RING_HEIGHTS[name] + 0.21), (0.28, 0.90, 1.0, 0.18), 0.52)
                    continue
                if name == "METROPOLIS":
                    node = make_box("expanded-metro-tower", 0.18 + (j % 3) * 0.05, 0.20, 0.70 + (j % 6) * 0.22)
                elif name == "URBAN":
                    node = make_box("expanded-urban-war-cover", 0.52, 0.14, 0.32 + (j % 3) * 0.06)
                elif name == "DESERT":
                    node = make_pyramid_3d("expanded-desert-crystal", 0.18, 0.60 + (j % 3) * 0.12, 4)
                elif name == "MUSHROOM":
                    node = make_cylinder("expanded-mushroom-colony", 0.18 + (j % 2) * 0.06, 0.28 + (j % 3) * 0.09, 10)
                elif name == "HILLS":
                    node = make_pyramid_3d("expanded-hills-rise", 0.28, 0.36 + (j % 3) * 0.08, 5)
                else:
                    node = make_pyramid_3d("expanded-forest-growth", 0.20, 0.56 + (j % 3) * 0.12, 5)
                node.reparentTo(self.ring_root)
                node.setPos(angle_to_pos(a, r, RING_HEIGHTS[name] + 0.05))
                node.setH(math.degrees(a) + 90)
                node.setColor(color[0], color[1], color[2], min(0.42, color[3] + 0.06))
                node.setTransparency(TransparencyAttrib.MAlpha)

        # Pass 27: wider region read. Add broad internal action roads and
        # low-poly field pieces in every band so each region feels like a large
        # battlefield, not a narrow decorative ring. These are static and flattenable.
        region_fill = [
            ("FOREST", 18, (0.10, 1.00, 0.34, 0.16), "forest-field-node"),
            ("HILLS", 18, (0.70, 1.00, 0.22, 0.14), "hills-field-node"),
            ("MUSHROOM", 20, (1.00, 0.22, 0.92, 0.16), "mushroom-field-node"),
            ("DESERT", 22, (1.00, 0.68, 0.18, 0.15), "desert-field-node"),
            ("WATER", 18, (0.20, 0.88, 1.00, 0.16), "water-field-node"),
            ("URBAN", 24, (0.14, 0.84, 1.00, 0.17), "urban-field-node"),
            ("METROPOLIS", 26, (1.00, 0.16, 0.42, 0.17), "metro-field-node"),
        ]
        for region, count, color, label in region_fill:
            spec = RINGS[region]
            span = max(0.1, spec["outer"] - spec["inner"] - 1.0)
            for i in range(count):
                a = TAU * i / count + ring_index(region) * 0.13
                lane = (i % 5) / 4.0
                r = spec["inner"] + 0.55 + span * lane
                if region == "WATER":
                    node = make_box(label, 0.58, 0.08, 0.07)
                    node.setH(math.degrees(a) + 90)
                elif region in {"METROPOLIS", "URBAN"}:
                    node = make_box(label, 0.22 + (i % 3) * 0.05, 0.22, 0.42 + (i % 4) * 0.16)
                    node.setH(math.degrees(a) + (i % 4) * 11)
                elif region == "DESERT":
                    node = make_pyramid_3d(label, 0.22 + (i % 2) * 0.05, 0.48 + (i % 3) * 0.10, 4)
                elif region == "MUSHROOM":
                    node = make_cylinder(label, 0.15 + (i % 3) * 0.03, 0.42 + (i % 2) * 0.12, 10)
                elif region == "HILLS":
                    node = make_pyramid_3d(label, 0.20 + (i % 3) * 0.04, 0.36 + (i % 2) * 0.12, 5)
                else:
                    node = make_cylinder(label, 0.16 + (i % 3) * 0.035, 0.55 + (i % 4) * 0.10, 8)
                node.reparentTo(self.ring_root)
                node.setPos(angle_to_pos(a, r, RING_HEIGHTS[region] + 0.06))
                node.setColor(*color)
                node.setTransparency(TransparencyAttrib.MAlpha)

        # Large-region traversal lanes: these make the widened rings read as
        # active territories with roads/currents/animal paths instead of empty width.
        for region in RING_TOP_ORDER[2:]:
            spec = RINGS[region]
            for lane in (0.28, 0.58, 0.84):
                rr = spec["inner"] + (spec["outer"] - spec["inner"]) * lane
                color = (0.18, 0.94, 1.0, 0.10) if region in {"WATER", "URBAN"} else (1.0, 0.94, 0.22, 0.08)
                if region == "METROPOLIS":
                    color = (1.0, 0.16, 0.42, 0.12)
                add_circle_line(self.ring_root, f"{region}-large-internal-lane", rr, color, 0.52, RING_HEIGHTS[region] + 0.24, 160)

    def add_label(self, name: str, text: str, pos: Vec3, scale: float, color) -> NodePath:
        t = TextNode(name)
        t.setText(text)
        t.setAlign(TextNode.ACenter)
        t.setTextColor(*color)
        np = self.marker_root.attachNewNode(t)
        np.setPos(pos)
        np.setScale(scale)
        np.setBillboardPointEye()
        return np

    def make_marker(self, kind: str, color, size: float = 0.45, triangle: bool = False) -> NodePath:
        """Create a 3D miniature marker for the isolated RTS branch.

        These are generated meshes only: no old HoloVerse models/assets/folders.
        The root stays at the entity position so existing gameplay code and
        setScale/setColor calls continue to work.
        """
        cache_key = (kind, round(float(size), 3), bool(triangle), tuple(round(float(c), 3) for c in color))
        cached = getattr(self, "marker_template_cache", {}).get(cache_key)
        if cached is not None and not cached.isEmpty():
            clone = cached.copyTo(self.unit_root)
            clone.show()
            return clone

        root = self.unit_root.attachNewNode(f"{kind}-3d")
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setColor(*color)

        def child(node: NodePath, pos=(0, 0, 0), scale=1.0, tint=None, wire=False):
            node.reparentTo(root)
            node.setPos(*pos)
            node.setScale(scale)
            node.setTransparency(TransparencyAttrib.MAlpha)
            if tint is not None:
                node.setColor(*tint)
            if wire:
                wf = node.copyTo(root)
                wf.setPos(*pos)
                wf.setScale(scale * 1.045 if isinstance(scale, (int, float)) else scale)
                wf.setRenderModeWireframe()
                wf.setLightOff(1)
                wf.setColor(0.90, 1.0, 1.0, 0.24)
            return node

        if kind == "artifact":
            child(make_cylinder("artifact-pedestal", size * 0.72, size * 0.18, 16), tint=(0.25, 0.34, 0.42, 0.82), wire=True)
            crystal = child(make_pyramid_3d("artifact-crystal", size * 0.55, size * 1.35, 4), pos=(0, 0, size * 0.18), tint=color, wire=True)
            crystal.setH(45)
        elif kind == "space_ally":
            child(make_box("space-ally-core", size * 1.40, size * 0.30, size * 0.16), pos=(0, 0, size * 0.08), tint=color, wire=True)
            child(make_box("space-ally-wing", size * 0.22, size * 1.10, size * 0.06), pos=(0, 0, size * 0.10), tint=(0.72, 1.0, 1.0, 0.94))
            child(make_pyramid_3d("space-ally-nose", size * 0.22, size * 0.28, 3), pos=(0, size * 0.70, size * 0.08), tint=(1.0, 1.0, 1.0, 0.90))
        elif kind == "space_enemy":
            body = child(make_pyramid_3d("space-enemy-dart", size * 0.82, size * 0.34, 4), pos=(0, 0, size * 0.06), tint=color, wire=True)
            body.setH(45)
            child(make_box("space-enemy-blade", size * 1.00, size * 0.16, size * 0.08), pos=(0, 0, size * 0.10), tint=(1.0, 0.62, 0.74, 0.90))
        elif kind.startswith("bot_") or kind == "bot":
            # Named main bots use distinct silhouettes while sharing the same
            # runtime role logic. IO is the orbiting sentry; the others guard artifacts.
            bot_id = kind[4:] if kind.startswith("bot_") else "generic"
            child(make_cylinder("bot-base", size * 0.58, size * 0.18, 18), tint=(0.06, 0.10, 0.14, 0.70), wire=True)
            if bot_id == "io":
                child(make_cylinder("io-orbit-ring", size * 0.82, size * 0.10, 24), pos=(0, 0, size * 0.30), tint=(0.35, 1.0, 1.0, 0.38), wire=True)
                child(make_box("io-sentry-core", size * 0.62, size * 0.62, size * 0.62), pos=(0, 0, size * 0.34), tint=color, wire=True)
                child(make_box("io-blaster", size * 0.15, size * 1.10, size * 0.12), pos=(0, size * 0.58, size * 0.76), tint=(0.78, 1.0, 1.0, 0.95))
            elif bot_id == "vanta":
                child(make_cylinder("vanta-trunk-body", size * 0.28, size * 0.94, 10), pos=(0, 0, size * 0.12), tint=(0.10, 0.54, 0.18, 0.82), wire=True)
                child(make_pyramid_3d("vanta-canopy-head", size * 0.66, size * 0.72, 6), pos=(0, 0, size * 0.90), tint=color, wire=True)
            elif bot_id == "nyx":
                body = child(make_pyramid_3d("nyx-beast-core", size * 0.72, size * 0.92, 3), pos=(0, 0, size * 0.22), tint=color, wire=True)
                body.setH(30)
                child(make_box("nyx-ears", size * 1.05, size * 0.12, size * 0.16), pos=(0, 0, size * 1.04), tint=(0.94, 0.76, 1.0, 0.82))
            elif bot_id == "solace":
                child(make_cylinder("solace-stem", size * 0.30, size * 0.78, 14), pos=(0, 0, size * 0.10), tint=(0.55, 0.20, 0.62, 0.82), wire=True)
                child(make_cylinder("solace-spore-cap", size * 0.78, size * 0.20, 18), pos=(0, 0, size * 0.86), tint=color, wire=True)
            elif bot_id == "ember":
                core = child(make_pyramid_3d("ember-pyramid-core", size * 0.70, size * 1.08, 4), pos=(0, 0, size * 0.12), tint=color, wire=True)
                core.setH(45)
                child(make_cylinder("ember-flame", size * 0.22, size * 0.26, 10), pos=(0, 0, size * 1.08), tint=(1.0, 0.95, 0.20, 0.92))
            elif bot_id == "mirror":
                shard = child(make_pyramid_3d("mirror-crystal", size * 0.56, size * 1.22, 4), pos=(0, 0, size * 0.18), tint=color, wire=True)
                shard.setH(45)
                child(make_cylinder("mirror-halo", size * 0.62, size * 0.06, 24), pos=(0, 0, size * 0.90), tint=(0.85, 1.0, 1.0, 0.32), wire=True)
            elif bot_id == "sable":
                child(make_box("sable-heavy-body", size * 0.88, size * 0.70, size * 0.76), pos=(0, 0, size * 0.18), tint=color, wire=True)
                child(make_box("sable-railgun", size * 0.18, size * 1.28, size * 0.16), pos=(0, size * 0.60, size * 0.72), tint=(1.0, 0.28, 0.24, 0.92))
            elif bot_id == "archivist":
                child(make_box("archivist-spire", size * 0.44, size * 0.44, size * 1.12), pos=(0, 0, size * 0.16), tint=color, wire=True)
                child(make_cylinder("archivist-data-ring", size * 0.72, size * 0.06, 22), pos=(0, 0, size * 0.88), tint=(0.62, 0.88, 1.0, 0.40), wire=True)
            else:
                child(make_box("bot-core", size * 0.76, size * 0.56, size * 0.72), pos=(0, 0, size * 0.22), tint=color, wire=True)
                child(make_cylinder("bot-head", size * 0.36, size * 0.26, 16), pos=(0, 0, size * 1.02), tint=(1.0, 1.0, 1.0, 0.54))
        elif kind == "pyramid":
            base = child(make_pyramid_3d("desert-defense-pyramid", size * 1.25, size * 1.65, 4), tint=color, wire=True)
            base.setH(45)
            child(make_cylinder("pyramid-emitter", size * 0.22, size * 0.22, 12), pos=(0, 0, size * 1.54), tint=(1.0, 0.95, 0.35, 0.98))
        elif kind == "mushroom":
            child(make_cylinder("mushroom-stem", size * 0.24, size * 0.72, 12), tint=(0.78, 0.58, 0.86, 0.70))
            child(make_cylinder("mushroom-cap", size * 0.78, size * 0.28, 24), pos=(0, 0, size * 0.68), tint=color, wire=True)
        elif kind == "tree":
            child(make_cylinder("tree-trunk", size * 0.18, size * 0.85, 10), tint=(0.42, 0.24, 0.10, 0.88))
            child(make_pyramid_3d("tree-canopy", size * 0.62, size * 1.25, 6), pos=(0, 0, size * 0.62), tint=color, wire=True)
        elif kind == "bush":
            child(make_cylinder("bush-body", size * 0.82, size * 0.44, 18), tint=color, wire=True)
            child(make_cylinder("bush-top", size * 0.52, size * 0.30, 18), pos=(0, 0, size * 0.35), tint=(0.62, 1.0, 0.28, 0.72))
        elif kind == "urban":
            child(make_box("urban-robot-body", size * 0.78, size * 0.64, size * 0.86), tint=color, wire=True)
            child(make_box("urban-robot-shoulders", size * 1.20, size * 0.28, size * 0.22), pos=(0, 0, size * 0.72), tint=(0.10, 0.54, 0.68, 0.84))
            child(make_box("urban-robot-gun", size * 0.16, size * 1.15, size * 0.12), pos=(0, size * 0.52, size * 0.78), tint=(0.74, 1.0, 1.0, 0.88))
        elif kind == "desert":
            child(make_cylinder("desert-troop-base", size * 0.46, size * 0.26, 12), tint=(0.52, 0.28, 0.08, 0.72))
            child(make_pyramid_3d("desert-troop", size * 0.52, size * 1.10, 4), pos=(0, 0, size * 0.22), tint=color, wire=True)
        elif kind == "mushroom_troop":
            child(make_cylinder("mushroom-troop", size * 0.44, size * 0.78, 14), tint=color, wire=True)
            child(make_cylinder("mushroom-troop-cap", size * 0.66, size * 0.20, 16), pos=(0, 0, size * 0.74), tint=(1.0, 0.32, 0.92, 0.74))
        elif kind == "caretaker":
            child(make_cylinder("caretaker-body", size * 0.38, size * 0.72, 14), tint=color, wire=True)
            child(make_box("caretaker-tool", size * 0.12, size * 0.86, size * 0.11), pos=(size * 0.35, 0, size * 0.46), tint=(0.86, 1.0, 0.55, 0.78))
        elif kind == "wildlife":
            child(make_box("wildlife-body", size * 1.16, size * 0.58, size * 0.42), tint=color, wire=True)
            child(make_pyramid_3d("wildlife-head", size * 0.32, size * 0.40, 3), pos=(0, size * 0.52, size * 0.25), tint=(0.92, 1.0, 0.38, 0.88))
        elif kind.startswith("enemy"):
            trait = ENEMY_TRAITS.get(kind, ENEMY_TRAITS["enemy_scout"])
            glow = trait.get("color", color)
            if kind == "enemy_brute":
                child(make_box("enemy-brute-body", size * 1.25, size * 0.92, size * 1.02), tint=(1.0, 0.08, 0.05, 0.96), wire=True)
                child(make_box("enemy-brute-shoulders", size * 1.62, size * 0.28, size * 0.24), pos=(0, 0, size * 0.88), tint=(1.0, 0.30, 0.10, 0.86))
                child(make_box("enemy-brute-claws", size * 1.72, size * 0.18, size * 0.16), pos=(0, size * 0.62, size * 0.66), tint=(1.0, 0.46, 0.12, 0.86))
            elif kind == "enemy_hacker":
                child(make_cylinder("enemy-hacker-core", size * 0.62, size * 0.74, 5), tint=(1.0, 0.05, 0.58, 0.94), wire=True)
                child(make_cylinder("enemy-hacker-ring", size * 0.92, size * 0.08, 24), pos=(0, 0, size * 0.62), tint=(1.0, 0.22, 0.82, 0.36), wire=True)
                child(make_box("enemy-hacker-antenna", size * 0.10, size * 0.10, size * 0.82), pos=(0, 0, size * 1.04), tint=(1.0, 0.52, 0.95, 0.82))
            elif kind == "enemy_sapper":
                child(make_box("enemy-sapper-crawler", size * 1.02, size * 0.56, size * 0.34), pos=(0, 0, size * 0.06), tint=glow, wire=True)
                child(make_cylinder("enemy-sapper-charge", size * 0.34, size * 0.24, 10), pos=(0, size * 0.38, size * 0.34), tint=(1.0, 0.62, 0.10, 0.92), wire=True)
                child(make_box("enemy-sapper-legs", size * 1.40, size * 0.12, size * 0.08), pos=(0, 0, size * 0.18), tint=(1.0, 0.36, 0.10, 0.76))
            elif kind == "enemy_siege":
                child(make_cylinder("enemy-siege-tripod", size * 0.48, size * 0.72, 6), pos=(0, 0, size * 0.12), tint=glow, wire=True)
                child(make_box("enemy-siege-cannon", size * 0.22, size * 1.44, size * 0.16), pos=(0, size * 0.62, size * 0.78), tint=(1.0, 0.34, 0.88, 0.92))
                child(make_pyramid_3d("enemy-siege-sensor", size * 0.38, size * 0.46, 4), pos=(0, 0, size * 1.00), tint=(0.96, 0.52, 1.0, 0.82), wire=True)
            elif kind == "enemy_commander":
                child(make_cylinder("enemy-command-base", size * 0.56, size * 0.26, 16), tint=(0.38, 0.08, 0.10, 0.86), wire=True)
                child(make_pyramid_3d("enemy-command-spire", size * 0.56, size * 1.35, 5), pos=(0, 0, size * 0.16), tint=glow, wire=True)
                child(make_cylinder("enemy-command-aura", size * 1.02, size * 0.06, 28), pos=(0, 0, size * 0.92), tint=(1.0, 0.72, 0.18, 0.34), wire=True)
            elif kind == "enemy_shield":
                child(make_cylinder("enemy-shield-core", size * 0.54, size * 0.82, 10), tint=glow, wire=True)
                child(make_cylinder("enemy-shield-dome", size * 1.08, size * 0.10, 30), pos=(0, 0, size * 0.72), tint=(0.38, 0.80, 1.0, 0.34), wire=True)
                child(make_box("enemy-shield-bar", size * 1.30, size * 0.14, size * 0.12), pos=(0, size * 0.42, size * 0.44), tint=(0.74, 1.0, 1.0, 0.72))
            elif kind == "enemy_carrier":
                child(make_box("enemy-carrier-hull", size * 1.55, size * 0.72, size * 0.38), tint=glow, wire=True)
                child(make_cylinder("enemy-carrier-bay", size * 0.54, size * 0.22, 12), pos=(0, size * 0.34, size * 0.34), tint=(1.0, 0.36, 0.82, 0.72), wire=True)
                child(make_box("enemy-carrier-wing", size * 1.95, size * 0.12, size * 0.10), pos=(0, 0, size * 0.42), tint=(1.0, 0.58, 0.90, 0.55))
            elif kind == "enemy_harvester":
                child(make_cylinder("enemy-harvester-core", size * 0.52, size * 0.66, 7), tint=glow, wire=True)
                child(make_box("enemy-harvester-arm-a", size * 1.24, size * 0.12, size * 0.10), pos=(0, size * 0.38, size * 0.42), tint=(0.78, 1.0, 0.22, 0.76))
                child(make_box("enemy-harvester-arm-b", size * 0.12, size * 1.10, size * 0.10), pos=(0, 0, size * 0.28), tint=(0.42, 1.0, 0.24, 0.62))
            elif kind == "enemy_phantom":
                child(make_pyramid_3d("enemy-phantom-cloak", size * 0.80, size * 1.20, 5), tint=glow, wire=True)
                child(make_cylinder("enemy-phantom-ring", size * 0.82, size * 0.05, 22), pos=(0, 0, size * 0.80), tint=(0.72, 0.36, 1.0, 0.28), wire=True)
                child(make_box("enemy-phantom-blade", size * 0.16, size * 1.30, size * 0.10), pos=(0, size * 0.42, size * 0.36), tint=(0.74, 0.52, 1.0, 0.56))
            else:
                child(make_box("enemy-scout-body", size * 0.82, size * 0.52, size * 0.48), tint=glow, wire=True)
                blade = child(make_pyramid_3d("enemy-scout-nose", size * 0.62, size * 0.68, 3), pos=(0, size * 0.48, size * 0.34), tint=(1.0, 0.06, 0.10, 0.95))
                blade.setP(90)
                child(make_box("enemy-scout-wings", size * 1.20, size * 0.10, size * 0.08), pos=(0, 0, size * 0.44), tint=(1.0, 0.42, 0.42, 0.72))
        elif kind == "packet":
            child(make_cylinder("packet-core", size * 0.72, size * 0.30, 14), tint=color, wire=True)
            child(make_box("packet-fin", size * 1.10, size * 0.16, size * 0.16), pos=(0, 0, size * 0.16), tint=(0.55, 1.0, 0.96, 0.42))
        else:
            node = make_pyramid_3d(kind, size, size * 0.8, 3) if triangle else make_cylinder(kind, size, size * 0.35, 24)
            child(node, tint=color, wire=True)
        # Keep one hidden copy for this marker shape/color. Later respawns clone
        # the prebuilt mesh tree, cutting generated geometry churn during play.
        try:
            template = root.copyTo(self.template_root)
            template.hide()
            self.marker_template_cache[cache_key] = template
        except Exception:
            pass
        return root

    def reset_board(self, full: bool = False):
        for e_list in [
            self.enemies, self.urban_troops, self.desert_troops, self.mushroom_troops,
            self.hills_caretakers, self.wildlife, self.forest_plants, self.pyramids,
            self.mushrooms, self.artifacts, self.bots, self.smokes, self.packets,
            self.region_activity_units,
        ]:
            for ent in e_list:
                if ent.node:
                    ent.node.removeNode()
            e_list.clear()
        for beam, _ttl in self.beams:
            beam.removeNode()
        self.beams.clear()
        for beam, _ttl in self.region_activity_beams:
            beam.removeNode()
        self.region_activity_beams.clear()
        self.hub_integrity = 1.0
        self.forest_attack_timer = 0.0
        self.forest_supply_safe = True
        for name in self.region_pressure:
            self.region_pressure[name] = 0.0
        self.order_target = None
        if not full:
            self.reset_count += 1
            self.stats["artifact_resets"] += 1
        self.spawn_static_defenses()
        self.spawn_armies()
        self.spawn_support_packets()
        self.spawn_region_activity()

    def spawn_static_defenses(self):
        # Hub artifacts and primary bots. Each bot now has its own
        # matchup role, ability, strength, and weakness while still guarding
        # one artifact from the flat/core ring.
        for i, bot_name in enumerate(BOT_NAMES):
            a = TAU * i / len(BOT_NAMES) + 0.16
            trait = BOT_TRAITS.get(bot_name, {})
            art = Entity("artifact", angle_to_pos(a, 4.55, 0.45), hp=1.0, max_hp=1.0, angle=a, extra={"bot": bot_name})
            art.node = self.make_marker("artifact", (0.92, 0.96, 1.0, 0.86), 0.38, triangle=True)
            self.artifacts.append(art)
            bot = Entity("bot", angle_to_pos(a, 5.15, 0.72), hp=1.0, max_hp=1.0, angle=a, cooldown=0.0, extra={
                "name": bot_name, "artifact": i,
                "role": trait.get("role", "artifact guardian"),
                "ability": trait.get("ability", "blast"),
                "strength": trait.get("strength", "balanced"),
                "weakness": trait.get("weakness", "none"),
                "ability_fx": 0.0,
            })
            bot.node = self.make_marker(BOT_MARKER_KIND.get(bot_name, "bot"), BOT_COLORS.get(bot_name, (0.8, 0.9, 1.0, 1.0)), 0.34 if bot_name == "IO" else 0.31)
            self.bots.append(bot)
            role_short = str(trait.get("ability", "guard")).upper()
            self.add_label(f"bot-label-{bot_name}", f"{bot_name} // {role_short}", angle_to_pos(a, 5.95, 0.9), 0.31, BOT_COLORS.get(bot_name, (1, 1, 1, 1)))
        # Desert pyramids with x2 range.
        for i in range(12):
            a = TAU * i / 12 + 0.34
            size = 1.55
            p = Entity("pyramid", angle_to_pos(a, 22.5 + (i % 3) * 1.05, 0.55), hp=1.0, max_hp=1.0, angle=a, cooldown=self.rng.random() * 1.2, extra={"size": size, "range": size * 2.0})
            p.node = self.make_marker("pyramid", (1.0, 0.72, 0.22, 0.92), size * 0.42, triangle=True)
            add_circle_line(p.node, "pyramid-proximity", size * 2.0, (1.0, 0.82, 0.20, 0.22), 0.6, 0.05, 48)
            self.pyramids.append(p)
        # Mushroom traps.
        for i in range(14):
            a = TAU * i / 14 + 0.68
            m = Entity("spore_mushroom", angle_to_pos(a, 17.1 + (i % 4) * 0.85, 0.42), hp=1.0, max_hp=1.0, angle=a, extra={"trigger": 1.8, "regrow": 60.0})
            m.node = self.make_marker("mushroom", (1.0, 0.18, 0.88, 0.78), 0.42)
            add_circle_line(m.node, "spore-trigger", 1.8, (1.0, 0.30, 0.90, 0.20), 0.5, 0.04, 40)
            self.mushrooms.append(m)
        # Forest ecosystem: trees drive strength, bushes drive growth speed.
        plant_specs = [
            ("tree", 8.4, 0.22), ("bush", 9.4, 0.95), ("tree", 10.0, 1.74),
            ("bush", 7.8, 2.66), ("tree", 9.7, 3.42), ("bush", 8.9, 4.35),
            ("tree", 10.4, 5.21), ("bush", 6.9, 5.78), ("tree", 7.5, 3.96),
            ("bush", 10.2, 2.20), ("tree", 8.7, 4.86), ("bush", 9.9, 0.42),
            ("tree", 6.8, 1.34), ("bush", 8.0, 5.55), ("tree", 10.6, 2.88),
            ("bush", 7.2, 3.18),
            ("tree", 9.1, 1.02), ("bush", 6.6, 4.72),
            ("tree", 10.8, 0.62), ("bush", 7.1, 2.44), ("tree", 9.6, 5.88),
            ("bush", 8.3, 1.72), ("tree", 7.6, 5.12), ("bush", 10.5, 4.10),
            ("tree", 6.4, 0.08), ("bush", 10.7, 0.88), ("tree", 8.9, 1.48),
            ("bush", 6.5, 2.08), ("tree", 9.8, 2.74), ("bush", 10.9, 3.32),
            ("tree", 7.0, 3.84), ("bush", 8.6, 4.54), ("tree", 10.1, 5.55),
            ("bush", 6.3, 5.98),
        ]
        for kind, radius, angle in plant_specs:
            color = (0.12, 0.95, 0.28, 0.86) if kind == "tree" else (0.44, 1.0, 0.20, 0.78)
            size = 0.54 if kind == "tree" else 0.40
            plant = Entity(kind, angle_to_pos(angle, radius, 0.48), hp=1.0, max_hp=1.0, angle=angle, growth=1.0, extra={"regrow": 300.0})
            plant.node = self.make_marker(kind, color, size, triangle=(kind == "tree"))
            self.forest_plants.append(plant)

    def spawn_armies(self):
        # Urban army: cannot cross Water outer boundary inward.
        for i in range(54):
            a = TAU * i / 54 + 0.10
            e = Entity("urban_robot", angle_to_pos(a, 31.8 + (i % 5) * 0.78, 0.58), hp=1.25, max_hp=1.25, angle=a, speed=2.45, cooldown=self.rng.random())
            e.node = self.make_marker("urban", (0.18, 0.92, 1.0, 0.92), 0.27)
            self.urban_troops.append(e)
        for i in range(34):
            a = TAU * i / 34 + 0.28
            e = Entity("desert_troop", angle_to_pos(a, 21.8 + (i % 5) * 0.78, 0.52), hp=0.9, max_hp=0.9, angle=a, speed=1.65, cooldown=self.rng.random())
            e.node = self.make_marker("desert", (1.0, 0.62, 0.12, 0.86), 0.22)
            self.desert_troops.append(e)
        for i in range(32):
            a = TAU * i / 32 + 0.44
            e = Entity("mushroom_troop", angle_to_pos(a, 16.9 + (i % 5) * 0.78, 0.5), hp=0.62, max_hp=0.62, angle=a, speed=1.25, cooldown=self.rng.random())
            e.node = self.make_marker("mushroom_troop", (0.92, 0.22, 1.0, 0.78), 0.20)
            self.mushroom_troops.append(e)
        for i in range(30):
            a = TAU * i / 30 + 0.34
            e = Entity("caretaker", angle_to_pos(a, 11.9 + (i % 5) * 0.84, 0.48), hp=0.56, max_hp=0.56, angle=a, speed=1.18, cooldown=self.rng.random())
            e.node = self.make_marker("caretaker", (0.72, 1.0, 0.20, 0.78), 0.18)
            self.hills_caretakers.append(e)
        for i in range(28):
            a = TAU * i / 28 + 0.58
            e = Entity("wildlife", angle_to_pos(a, 11.7 + (i % 6) * 0.68, 0.5), hp=0.38, max_hp=0.38, angle=a, speed=1.45, cooldown=self.rng.random(), growth=0.05)
            e.node = self.make_marker("wildlife", (0.88, 1.0, 0.32, 0.86), 0.19, triangle=True)
            self.wildlife.append(e)

    def spawn_support_packets(self):
        rings = ["FLAT", "FOREST", "HILLS", "MUSHROOM", "DESERT", "WATER", "URBAN", "METROPOLIS"]
        for i, name in enumerate(rings):
            for lane in range(4):
                a = TAU * (i + lane * 0.23) / len(rings) + 0.18
                p = Entity("packet", angle_to_pos(a, max(RINGS[name]["inner"] + 0.35, RINGS[name]["outer"] - lane * 0.92), 0.74), angle=a, speed=0.46 + lane * 0.10, extra={"ring": name, "lane": lane})
                p.node = self.make_marker("packet", (0.12, 1.0, 0.95, 0.52), 0.13)
                self.packets.append(p)

    def spawn_region_activity(self):
        """Spawn non-combat regional motion so every ring visibly does work.

        The actual troop/enemy logic is still handled by the existing combat
        systems. These actors make the macro board legible: Forest feeds Hills,
        Water runs vessels, Desert charges pylons, Urban patrols the shoreline,
        and Metropolis musters attackers at the outer edge.
        """
        specs = [
            ("FLAT", 10, "bot_io", (0.58, 1.00, 1.00, 0.52), 0.23, 1.08, 0.02),
            ("FOREST", 20, "packet", (0.18, 1.00, 0.36, 0.58), 0.20, 0.72, 0.11),
            ("HILLS", 18, "wildlife", (0.86, 1.00, 0.28, 0.56), 0.24, 0.86, -0.09),
            ("MUSHROOM", 18, "mushroom_troop", (0.98, 0.24, 1.00, 0.56), 0.22, 0.66, 0.16),
            ("DESERT", 18, "desert", (1.00, 0.66, 0.16, 0.56), 0.24, 0.74, -0.13),
            ("WATER", 16, "packet", (0.22, 0.92, 1.00, 0.56), 0.23, 0.58, 0.20),
            ("URBAN", 24, "urban", (0.18, 0.92, 1.00, 0.60), 0.27, 0.88, -0.18),
            ("METROPOLIS", 28, "enemy_scout", (1.00, 0.14, 0.42, 0.58), 0.24, 0.92, 0.24),
        ]
        for region, count, marker_kind, color, size, speed, phase_offset in specs:
            spec = RINGS[region]
            span = max(0.6, spec["outer"] - spec["inner"] - 0.8)
            for i in range(count):
                lane = (i % 4) / 3.0
                base_r = spec["inner"] + 0.44 + span * (0.16 + lane * 0.76)
                # Keep the Flat/Core activity away from the actual artifacts.
                if region == "FLAT":
                    base_r = 3.2 + (i % 3) * 0.72
                a = TAU * i / count + ring_index(region) * 0.19 + phase_offset
                speed_dir = -1.0 if (i + ring_index(region)) % 2 else 1.0
                ent = Entity(
                    f"activity_{region.lower()}",
                    angle_to_pos(a, base_r, 0.72),
                    hp=1.0, max_hp=1.0, angle=a, speed=speed * speed_dir, cooldown=self.rng.uniform(0.2, 2.0),
                    extra={
                        "region": region, "base_radius": base_r, "lane": lane,
                        "phase": self.rng.uniform(0.0, TAU), "kind": marker_kind,
                        "pulse_rate": self.rng.uniform(1.6, 3.4),
                    },
                )
                ent.node = self.make_marker(marker_kind, color, size, triangle=marker_kind.startswith("enemy"))
                ent.node.setAlphaScale(0.82)
                self.region_activity_units.append(ent)
        self.stats["ambient_activity_units"] = len(self.region_activity_units)

    def spawn_enemy_unit(self, variant: str, gate: int, angle: float, radius: float, squad_id: int, slot: int, squad_size: int):
        if len(self.enemies) >= 120:
            return None
        trait = ENEMY_TRAITS.get(variant, ENEMY_TRAITS["enemy_scout"])
        record = self.enemy_squad_memory.get(squad_id, {})
        smart = self.rng.random()
        veteran = bool(record.get("veteran", False))
        hp = float(trait["hp"]) * (1.0 + 0.05 * smart) * (1.18 if veteran else 1.0)
        speed = (float(trait["speed"]) + smart * 0.24) * (1.06 if veteran else 1.0)
        spread = (slot - (squad_size - 1) * 0.5) * 0.055
        route_shift = float(record.get("route_shift", 0.0))
        lane_angle = angle + spread + route_shift
        enemy = Entity(variant, angle_to_pos(lane_angle, radius, 0.68), hp=hp, max_hp=hp, angle=lane_angle, speed=speed, cooldown=self.rng.random(), extra={
            "smart": smart, "vessel": False, "confused": 0.0, "variant": variant,
            "squad": squad_id, "slot": slot, "gate": gate, "lane_angle": lane_angle,
            "damage": float(trait.get("damage", 1.0)) * (1.10 if veteran else 1.0), "support_fx": 0.0, "hack_fx": 0.0,
            "siege_fx": 0.0, "carrier_fx": 0.0, "harvest_fx": 0.0, "shield_fx": 0.0,
            "carrier_deployed": 0, "label": trait.get("label", variant),
            "spawned_at": self.elapsed, "born_wave": self.wave_index,
            "objective": record.get("objective", self.enemy_objective_label(variant)), "veteran": veteran,
        })
        enemy.node = self.make_marker(variant, trait.get("color", (1.0, 0.12, 0.16, 0.96)), float(trait["size"]), triangle=True)
        enemy.node.setH(math.degrees(lane_angle) - 90)
        if veteran:
            enemy.node.setScale(1.18)
            self.add_impact_burst(enemy.pos, (1.0, 0.78, 0.18, 0.32), 0.58, 0.58, 1.1)
        self.enemies.append(enemy)
        return enemy

    def spawn_enemy(self):
        if len(self.enemies) >= 120:
            return
        squad_id = int(self.stats.get("enemy_squads", 0))
        gate = squad_id % 8
        a = TAU * gate / 8 + self.rng.uniform(-0.08, 0.08)
        lead_variant = self.wave_doctrine_lead_variant(squad_id)
        squad = ENEMY_SQUADS.get(lead_variant, (lead_variant,))
        # Session-persistent squad identity. These records survive board/run
        # resets during this play session and feed the adaptive wave director.
        self.enemy_squad_memory[squad_id] = {
            "id": squad_id,
            "doctrine": self.current_doctrine,
            "lead": lead_variant,
            "spawn_wave": self.wave_index,
            "spawn_time": self.elapsed,
            "survival": 0.0,
            "min_radius": 999.0,
            "best_region": "METROPOLIS",
            "death_region": "",
            "kills": 0,
            "damage_caused": 0.0,
            "objective": self.enemy_objective_label(lead_variant),
            "route_shift": self.rng.uniform(-0.030, 0.030),
            "veteran": False,
            "members": list(squad),
        }
        self.stats["enemy_persistent_squads"] = len(self.enemy_squad_memory)
        spawned = []
        for slot, variant in enumerate(squad):
            radius = 41.9 + (slot % 2) * 0.42 + (slot // 2) * 0.22
            enemy = self.spawn_enemy_unit(variant, gate, a, radius, squad_id, slot, len(squad))
            if enemy is not None:
                spawned.append(enemy)
        if spawned and self.metro_spawn_pulses:
            pulse = self.metro_spawn_pulses[gate % len(self.metro_spawn_pulses)]
            pulse["burst"] = 1.0
            node = pulse.get("node")
            if node is not None and not node.isEmpty():
                for enemy in spawned:
                    origin = pulse.get("sim_pos", enemy.pos)
                    self.add_beam(origin + Vec3(0, 0, 0.18), enemy.pos + Vec3(0, 0, 0.45), (1.0, 0.18, 0.40, 0.46), 0.24, 1.25)
                self.add_impact_burst(origin, (1.0, 0.12, 0.38, 0.34), 0.48, 0.70, 0.92)
        self.stats["enemy_squads"] += 1
        self.stats["enemies_spawned"] += len(spawned)
        if spawned:
            lead_label = ENEMY_TRAITS.get(lead_variant, {}).get("label", str(lead_variant).split("_")[-1].upper())
            self.log_region_event("METROPOLIS", "Metropolis", "launched", f"{lead_label} squad {squad_id}", "enemy_action")

    def seed_enemy_showcase(self):
        # Deterministic proof/debug setup: visible squad groups on the
        # Metropolis/Urban edge without waiting for the normal timer.
        for _ in range(16):
            self.spawn_enemy()
        for idx, enemy in enumerate(self.enemies):
            # Pull some troops just inside Metropolis/Urban so the upgraded
            # models and formation paths are visible in an overview screenshot.
            r = 40.4 - (idx % 5) * 1.05
            a = enemy.extra.get("lane_angle", enemy.angle) + (idx % 3 - 1) * 0.025
            enemy.pos = angle_to_pos(a, r, 0.68)
            enemy.angle = a
            if enemy.node:
                enemy.node.setH(math.degrees(a) - 90)
            self.update_node(enemy)

    def seed_enemy_intelligence_test(self):
        """Deterministic proof setup for the learning/adaptation layer."""
        self.enemy_learning.setdefault("deaths_by_region", {})["DESERT"] = 7
        self.enemy_learning.setdefault("deaths_by_region", {})["WATER"] = 3
        self.enemy_learning.setdefault("deaths_by_class", {})["enemy_scout"] = 4
        self.refresh_enemy_adaptation(1)
        # Spawn adapted squads, then age and promote one so veteran/persistent
        # behavior is visible in screenshots and self-test output.
        for _ in range(8):
            self.spawn_enemy()
        if self.enemies:
            first_squad = int(self.enemies[0].extra.get("squad", 0))
            rec = self.enemy_squad_memory.get(first_squad)
            if rec is not None:
                rec["spawn_time"] = self.elapsed - 38.0
                rec["min_radius"] = RINGS["DESERT"]["inner"] + 0.3
                rec["best_region"] = "DESERT"
            for e in self.enemies:
                if e.extra.get("squad") == first_squad:
                    e.extra["spawned_at"] = self.elapsed - 38.0
                    e.pos = angle_to_pos(e.angle, RINGS["DESERT"]["outer"] - 0.6, 0.68)
            self.promote_enemy_squad(first_squad)
        self.adaptation_message_timer = 8.0

    def seed_activity_log_test(self):
        # Deterministic proof setup for the left-side region activity panel.
        self.selected_region = "FOREST"
        self.activity_panel_visible = True
        self.log_region_event("FOREST", "Metropolis", "damaged", "tree supply", "enemy_win")
        self.log_region_event("FOREST", "Vanta", "rooted", "HARVESTER squad", "defense_win")
        self.log_region_event("FOREST", "Player", "deployed", "Forest Supply Surge", "support")
        self.log_region_event("WATER", "Metropolis", "built", "SAPPER vessels", "enemy_action")
        self.log_region_event("DESERT", "Desert pyramids", "defeated", "SHIELD walker", "defense_win")
        self.region_pressure["FOREST"] = max(self.region_pressure.get("FOREST", 0.0), 0.54)
        self.update_activity_panel()

    def seed_primary_bot_test(self):
        """Deterministic setup that pulls mixed enemy classes into primary bot range."""
        self.enemies.clear()
        variants = [
            "enemy_scout", "enemy_phantom", "enemy_harvester", "enemy_sapper",
            "enemy_brute", "enemy_carrier", "enemy_hacker", "enemy_commander",
            "enemy_shield", "enemy_siege", "enemy_phantom", "enemy_brute",
        ]
        for idx, variant in enumerate(variants):
            a = TAU * idx / len(variants) + 0.06 * math.sin(idx)
            r = 6.0 + (idx % 3) * 0.42
            enemy = self.spawn_enemy_unit(variant, idx % 8, a, r, 900 + idx, idx, 1)
            if enemy is not None:
                enemy.pos = angle_to_pos(a, r, 0.70)
                enemy.extra["vessel"] = True
                enemy.extra["objective"] = "primary bot proof target"
                if idx % 5 == 0:
                    enemy.extra["veteran"] = True
                self.update_node(enemy)
        # Pass 43: one readable proof target per named primary bot, positioned
        # close enough to guarantee all unique powers fire during regression tests.
        bot_proofs = [
            ("IO", "enemy_scout"), ("Vanta", "enemy_harvester"), ("Nyx", "enemy_brute"),
            ("Solace", "enemy_hacker"), ("Ember", "enemy_shield"), ("Mirror", "enemy_siege"),
            ("Sable", "enemy_commander"), ("Archivist", "enemy_phantom"),
        ]
        for idx, (_bot_name, variant) in enumerate(bot_proofs):
            a = TAU * idx / len(bot_proofs) + 0.16
            r = 5.95 + (idx % 2) * 0.22
            enemy = self.spawn_enemy_unit(variant, idx, a, r, 980 + idx, 30 + idx, 1)
            if enemy is not None:
                enemy.pos = angle_to_pos(a, r, 0.72)
                enemy.extra["vessel"] = True
                enemy.extra["objective"] = "unique primary power proof target"
                enemy.extra["proof_target"] = _bot_name
                if variant in {"enemy_shield", "enemy_siege", "enemy_commander"}:
                    enemy.extra["veteran"] = True
                self.update_node(enemy)
        self.adaptation_message = "Primary bots online: unique powers armed"
        self.adaptation_message_timer = 9.0
        self.command_energy = COMMAND_ENERGY_MAX
        self.command_bot_overdrive()
        self.command_buffs["bot_overdrive"] = max(self.command_buffs.get("bot_overdrive", 0.0), 12.0)
        self.bot_overdrive_flash = 1.0
        self.focus_overview_camera()

    def update(self, task):
        try:
            if CRASH_TEST and not getattr(self, "_crash_test_triggered", False):
                self._crash_test_triggered = True
                raise RuntimeError("intentional crash-test from --crash-test")
            dt = min(0.05, self.clock.getDt())
            self.elapsed += dt
            self.update_camera(dt)
            self.update_game_loop(dt)
            self.bot_power_message_timer = max(0.0, self.bot_power_message_timer - dt)
            self.update_enemies(dt)
            self.update_defenses(dt)
            self.update_ecosystem(dt)
            self.update_region_pressure(dt)
            self.update_region_activity_status(dt)
            self.update_region_activity(dt)
            self.update_gleebs_backdrop(dt)
            self.update_frontline_action_fx(dt)
            self.update_space_battles(dt)
            self.update_fx(dt)
            self.update_hud()
            return Task.cont
        except Exception as exc:
            write_crash_report(exc, "update-task")
            try:
                self.userExit()
            except Exception:
                pass
            return Task.done

    def wave_doctrine_name(self, wave: int) -> str:
        return WAVE_DOCTRINES[(max(1, wave) - 1) % len(WAVE_DOCTRINES)][0]

    def enemy_objective_label(self, variant: str) -> str:
        return {
            "enemy_scout": "mark weak route",
            "enemy_brute": "break frontline",
            "enemy_hacker": "disable defenders",
            "enemy_sapper": "build crossings",
            "enemy_siege": "bombard supply/core",
            "enemy_commander": "organize squad",
            "enemy_shield": "protect push",
            "enemy_carrier": "deploy drones",
            "enemy_harvester": "drain supply",
            "enemy_phantom": "bypass traps",
        }.get(variant, "push inward")

    def adaptive_enemy_variant(self, squad_id: int) -> Optional[str]:
        if not self.adaptive_bias:
            return None
        ordered = sorted(self.adaptive_bias.items(), key=lambda item: (-item[1], item[0]))
        if not ordered:
            return None
        # Keep adaptation readable and intermittent instead of overriding every wave.
        if squad_id % 4 not in (1, 2):
            return None
        return ordered[squad_id % len(ordered)][0]

    def refresh_enemy_adaptation(self, completed_wave: int):
        if completed_wave <= self.last_adapt_wave:
            return
        self.last_adapt_wave = completed_wave
        deaths = self.enemy_learning.get("deaths_by_region", {})
        if not deaths:
            return
        blocked_region = max(deaths.items(), key=lambda item: item[1])[0]
        counter_map = {
            "URBAN": ("enemy_brute", "enemy_commander"),
            "WATER": ("enemy_sapper", "enemy_phantom"),
            "DESERT": ("enemy_shield", "enemy_siege"),
            "MUSHROOM": ("enemy_hacker", "enemy_phantom"),
            "HILLS": ("enemy_carrier", "enemy_brute"),
            "FOREST": ("enemy_harvester", "enemy_siege"),
            "FLAT": ("enemy_commander", "enemy_siege"),
            "CORE": ("enemy_commander", "enemy_phantom"),
        }
        picks = counter_map.get(blocked_region, ("enemy_scout", "enemy_sapper"))
        self.adaptive_bias = {name: 1.0 + i * 0.35 for i, name in enumerate(picks)}
        self.adaptation_message = f"Metropolis learned: {blocked_region} resistance -> {', '.join(p.split('_')[-1].upper() for p in picks)}"
        self.adaptation_message_timer = 8.0
        self.stats["enemy_adaptations"] = self.stats.get("enemy_adaptations", 0) + 1
        self.add_impact_burst(angle_to_pos(-math.pi / 2, 40.8, 1.2), (1.0, 0.12, 0.52, 0.42), 1.5, 1.4, 2.2)

    def update_enemy_squad_record(self, enemy: Entity, region: str, dt: float):
        squad_id = enemy.extra.get("squad")
        if squad_id is None:
            return
        rec = self.enemy_squad_memory.setdefault(int(squad_id), {"id": int(squad_id), "spawn_time": self.elapsed, "survival": 0.0})
        rec["survival"] = max(float(rec.get("survival", 0.0)), self.elapsed - float(rec.get("spawn_time", self.elapsed)))
        r = pos_radius(enemy.pos)
        if r < float(rec.get("min_radius", 999.0)):
            rec["min_radius"] = r
            rec["best_region"] = region
            self.enemy_learning.setdefault("best_region_reached", {})[region] = self.enemy_learning.setdefault("best_region_reached", {}).get(region, 0) + 1
        if (not rec.get("veteran")) and rec.get("survival", 0.0) >= 32.0 and r < RINGS["DESERT"]["outer"]:
            rec["veteran"] = True
            self.promote_enemy_squad(int(squad_id))

    def promote_enemy_squad(self, squad_id: int):
        self.stats["enemy_veterans"] = self.stats.get("enemy_veterans", 0) + 1
        rec = self.enemy_squad_memory.get(squad_id, {})
        lead = rec.get("lead", "enemy")
        self.enemy_learning.setdefault("survived_by_class", {})[lead] = self.enemy_learning.setdefault("survived_by_class", {}).get(lead, 0) + 1
        for enemy in self.enemies:
            if enemy.extra.get("squad") == squad_id:
                enemy.extra["veteran"] = True
                enemy.max_hp *= 1.16
                enemy.hp = min(enemy.max_hp, enemy.hp + 0.28)
                enemy.speed *= 1.04
                if enemy.node:
                    enemy.node.setScale(enemy.node.getScale() * 1.12)
                    self.flash_entity(enemy, (1.0, 0.82, 0.22, 0.96))
        self.adaptation_message = f"Veteran squad {squad_id} survived: {str(lead).split('_')[-1].upper()} tactics reinforced"
        self.adaptation_message_timer = 5.0
        self.add_impact_burst(angle_to_pos(0.25 + squad_id * 0.13, 24.0, 1.0), (1.0, 0.82, 0.18, 0.42), 1.2, 0.90, 1.7)

    def record_enemy_death(self, enemy: Entity):
        region = self.region_for_radius(pos_radius(enemy.pos))
        variant = enemy.extra.get("variant", enemy.kind)
        source_region = str(enemy.extra.get("last_damage_region", region))
        damage_type = str(enemy.extra.get("last_damage_type", "direct"))
        source_label = DAMAGE_SOURCE_LABELS.get(damage_type, DAMAGE_SOURCE_LABELS.get("direct", "Defenders"))
        enemy_label = ENEMY_TRAITS.get(variant, {}).get("label", str(variant).split("_")[-1].upper())
        self.log_region_event(source_region if source_region in self.region_activity_log else region, source_label, "defeated", enemy_label, "defense_win")
        self.enemy_learning.setdefault("deaths_by_region", {})[region] = self.enemy_learning.setdefault("deaths_by_region", {}).get(region, 0) + 1
        self.enemy_learning.setdefault("deaths_by_class", {})[variant] = self.enemy_learning.setdefault("deaths_by_class", {}).get(variant, 0) + 1
        squad_id = enemy.extra.get("squad")
        if squad_id is not None:
            rec = self.enemy_squad_memory.setdefault(int(squad_id), {"id": int(squad_id)})
            rec["death_region"] = region
            rec["survival"] = max(float(rec.get("survival", 0.0)), self.elapsed - float(rec.get("spawn_time", self.elapsed)))
        self.stats["enemy_memory_marks"] = self.stats.get("enemy_memory_marks", 0) + 1

    def nearby_enemy_shield(self, target: Entity, max_dist: float = 4.8) -> Optional[Entity]:
        target_squad = target.extra.get("squad")
        for other in self.enemies:
            if other is target or other.hp <= 0:
                continue
            if other.extra.get("variant") == "enemy_shield" and (target_squad is None or other.extra.get("squad") == target_squad):
                if distance(other.pos, target.pos) <= max_dist:
                    return other
        return None

    def apply_enemy_damage(self, target: Entity, amount: float, damage_type: str = "direct", source_pos: Optional[Vec3] = None):
        if target is None or target.hp <= 0:
            return
        if source_pos is not None:
            try:
                source_region = self.region_for_radius(pos_radius(source_pos))
            except Exception:
                source_region = self.region_for_radius(pos_radius(target.pos))
        else:
            source_region = self.region_for_radius(pos_radius(target.pos))
        target.extra["last_damage_type"] = damage_type
        target.extra["last_damage_region"] = source_region
        target.extra["last_damage_time"] = self.elapsed
        scale = 1.0
        if target.extra.get("veteran"):
            scale *= 0.88
        shield = self.nearby_enemy_shield(target, 5.2 if damage_type == "laser" else 4.2)
        if shield is not None:
            scale *= 0.54 if damage_type == "laser" else 0.78
            shield.extra["shield_fx"] = max(0.0, float(shield.extra.get("shield_fx", 0.0)) - 0.2)
            if shield.extra.get("shield_fx", 0.0) <= 0.0:
                self.add_beam(self.visual_point(shield.pos, 0.62), self.visual_point(target.pos, 0.50), (0.42, 0.86, 1.0, 0.36), 0.16, 1.2)
                shield.extra["shield_fx"] = 0.55
            self.stats["enemy_shield_blocks"] = self.stats.get("enemy_shield_blocks", 0) + 1
        if target.extra.get("variant") == "enemy_phantom" and damage_type in {"spore", "direct"}:
            scale *= 0.82
        if target.extra.get("marked_until", 0.0) > self.elapsed:
            scale *= 1.16
        if target.extra.get("vulnerable_until", 0.0) > self.elapsed:
            scale *= 1.18
        if target.extra.get("prism_shredded_until", 0.0) > self.elapsed:
            scale *= 1.10
        dealt = amount * scale
        target.hp -= dealt
        target.extra["damage_taken"] = float(target.extra.get("damage_taken", 0.0)) + dealt

    def wave_doctrine_lead_variant(self, squad_id: int) -> str:
        adaptive = self.adaptive_enemy_variant(squad_id)
        if adaptive:
            return adaptive
        doctrine_name, primary = WAVE_DOCTRINES[(max(1, self.wave_index) - 1) % len(WAVE_DOCTRINES)]
        # Keep variety inside every wave, but bias toward the doctrine
        # strongly enough that the player can read and counter the pressure.
        if doctrine_name == "Balanced Probe":
            return ENEMY_VARIANTS[squad_id % len(ENEMY_VARIANTS)]
        if squad_id % 3 in (0, 1):
            return primary
        support = {
            "enemy_sapper": "enemy_scout",
            "enemy_hacker": "enemy_sapper",
            "enemy_siege": "enemy_brute",
            "enemy_commander": "enemy_hacker",
            "enemy_brute": "enemy_scout",
            "enemy_shield": "enemy_brute",
            "enemy_carrier": "enemy_scout",
            "enemy_harvester": "enemy_sapper",
            "enemy_phantom": "enemy_hacker",
        }.get(primary, "enemy_scout")
        return support

    def reward_command_energy_for_kill(self, enemy: Entity):
        variant = enemy.extra.get("variant", enemy.kind)
        reward = {
            "enemy_scout": 0.55,
            "enemy_sapper": 0.80,
            "enemy_hacker": 1.05,
            "enemy_brute": 1.10,
            "enemy_siege": 1.55,
            "enemy_commander": 2.00,
            "enemy_shield": 1.35,
            "enemy_carrier": 1.80,
            "enemy_harvester": 1.45,
            "enemy_phantom": 1.65,
        }.get(variant, 0.70)
        self.command_energy = clamp(self.command_energy + reward, 0.0, COMMAND_ENERGY_MAX)
        self.stats["command_energy_rewards"] = self.stats.get("command_energy_rewards", 0) + 1
        score_reward = SCORE_BY_ENEMY.get(variant, 9)
        self.add_score(score_reward, f"DESTROYED {variant.split('_')[-1].upper()} +{score_reward}")

    def update_game_loop(self, dt: float):
        self.run_time += dt
        self.combo_timer = max(0.0, self.combo_timer - dt)
        if self.combo_timer <= 0.0:
            self.combo = max(1.0, self.combo - dt * 0.18)
        self.core_rank = 1 + int(self.score // CORE_RANK_SCORE_STEP)
        self.stats["best_rank"] = max(int(self.stats.get("best_rank", 1)), self.core_rank)
        cycle = WAVE_ASSAULT_DURATION + WAVE_RECOVERY_DURATION
        previous_wave = self.wave_index
        previous_phase = self.wave_phase
        self.wave_index = int(self.elapsed // cycle) + 1
        t = self.elapsed % cycle
        self.wave_phase_time = t
        self.wave_phase = "assault" if t < WAVE_ASSAULT_DURATION else "recovery"
        if self.wave_index != previous_wave:
            self.stats["waves_completed"] += 1
            self.refresh_enemy_adaptation(previous_wave)
            self.current_doctrine = self.wave_doctrine_name(self.wave_index)
            self.stats["wave_doctrine_changes"] = self.stats.get("wave_doctrine_changes", 0) + 1
            self.enemy_spawn_timer = min(self.enemy_spawn_timer, 0.72)
            self.add_impact_burst(Vec3(0, 0, 1.2), (0.30, 1.0, 1.0, 0.40), 1.4, 1.2, 2.0)
            self.add_impact_burst(angle_to_pos(-math.pi / 2, 39.8, 1.1), (1.0, 0.18, 0.44, 0.36), 1.1, 1.9, 2.2)
        if self.wave_phase != previous_phase and self.wave_phase == "recovery":
            self.stats["recovery_windows"] += 1
            self.complete_wave_rewards(previous_wave)
            self.apply_recovery_window()

        regen = COMMAND_REGEN_RECOVERY if self.wave_phase == "recovery" else COMMAND_REGEN_ASSAULT
        self.command_energy = clamp(self.command_energy + regen * dt, 0.0, COMMAND_ENERGY_MAX)
        self.command_flash = max(0.0, self.command_flash - dt)
        self.run_message_timer = max(0.0, self.run_message_timer - dt)
        self.adaptation_message_timer = max(0.0, self.adaptation_message_timer - dt)
        for name in list(self.command_buffs.keys()):
            self.command_buffs[name] = max(0.0, self.command_buffs[name] - dt)
        for name in list(self.command_cooldowns.keys()):
            self.command_cooldowns[name] = max(0.0, self.command_cooldowns[name] - dt)
        for name in list(self.bot_synergy_cooldowns.keys()):
            self.bot_synergy_cooldowns[name] = max(0.0, self.bot_synergy_cooldowns[name] - dt)
        self.bot_overdrive_flash = max(0.0, self.bot_overdrive_flash - dt)

        if self.wave_phase == "assault":
            self.enemy_spawn_timer -= dt
            if self.enemy_spawn_timer <= 0.0:
                squads = min(4, 1 + (self.wave_index - 1) // 3)
                for _ in range(squads):
                    self.spawn_enemy()
                self.stats["wave_spawns"] += squads
                self.enemy_spawn_timer = self.enemy_spawn_interval()
        else:
            self.enemy_spawn_timer = min(self.enemy_spawn_timer, 1.4)

    def add_score(self, amount: int, reason: str = ""):
        if amount <= 0:
            return
        scaled = int(round(amount * self.combo))
        self.score += max(1, scaled)
        self.best_score = max(self.best_score, self.score)
        self.combo = clamp(self.combo + 0.045, 1.0, 3.5)
        self.combo_timer = 5.0
        self.stats["score_events"] = self.stats.get("score_events", 0) + 1
        if reason:
            self.run_message = reason
            self.run_message_timer = 3.2

    def complete_wave_rewards(self, completed_wave: int):
        # Recovery means the player survived the assault. Award score and one
        # automatic upgrade so each wave pushes the defense board forward.
        bonus = int(90 + completed_wave * 24 + self.active_count(self.artifacts) * 5 + self.hub_integrity * 65)
        self.add_score(bonus, f"WAVE {completed_wave} HELD  +{bonus}")
        self.log_region_event("CORE", "Defenders", "held", f"Wave {completed_wave}", "defense_win")
        self.stats["wave_score_bonus"] = self.stats.get("wave_score_bonus", 0) + bonus
        self.stats["best_wave"] = max(int(self.stats.get("best_wave", 1)), completed_wave)
        self.upgrade_points += 1
        self.stats["upgrade_points"] = self.stats.get("upgrade_points", 0) + 1
        self.award_auto_upgrade(completed_wave)
        if completed_wave > 0 and completed_wave % 5 == 0:
            milestone = 350 + completed_wave * 20
            self.add_score(milestone, f"MILESTONE WAVE {completed_wave}  +{milestone}")
            self.command_energy = min(COMMAND_ENERGY_MAX, self.command_energy + 25.0)
            self.stats["milestone_bonuses"] = self.stats.get("milestone_bonuses", 0) + 1
            self.add_impact_burst(Vec3(0, 0, 1.7), (0.70, 1.0, 1.0, 0.52), 2.2, 1.4, 2.8)

    def choose_upgrade_track(self) -> str:
        preferred = DOCTRINE_COUNTER_UPGRADE.get(self.current_doctrine, "urban")
        if self.upgrade_levels.get(preferred, 0) < MAX_UPGRADE_LEVEL:
            return preferred
        return min(UPGRADE_ORDER, key=lambda name: self.upgrade_levels.get(name, 0))

    def award_auto_upgrade(self, completed_wave: int):
        track = self.choose_upgrade_track()
        if self.upgrade_levels.get(track, 0) >= MAX_UPGRADE_LEVEL:
            return
        self.upgrade_levels[track] += 1
        level = self.upgrade_levels[track]
        self.stats["auto_upgrades"] = self.stats.get("auto_upgrades", 0) + 1
        self.run_message = f"UPGRADE: {UPGRADE_LABELS.get(track, track)} LVL {level}"
        self.run_message_timer = 5.2
        self.log_region_event({"urban": "URBAN", "desert": "DESERT", "mushroom": "MUSHROOM", "forest": "FOREST", "core": "FLAT"}.get(track, "CORE"), "Defenders", "upgraded", f"{UPGRADE_LABELS.get(track, track)} L{level}", "support")
        region = {
            "urban": "URBAN", "desert": "DESERT", "mushroom": "MUSHROOM", "forest": "FOREST", "core": "FLAT",
        }.get(track, "CORE")
        spec = RINGS.get(region, RINGS["CORE"])
        pos = angle_to_pos(completed_wave * 0.72, (spec["inner"] + spec["outer"]) * 0.5, RING_HEIGHTS[region] + 1.25)
        color = {
            "urban": (0.18, 0.95, 1.0, 0.48), "desert": (1.0, 0.76, 0.16, 0.48),
            "mushroom": (1.0, 0.22, 0.96, 0.48), "forest": (0.20, 1.0, 0.36, 0.48),
            "core": (0.70, 1.0, 1.0, 0.54),
        }.get(track, (0.7, 1.0, 1.0, 0.46))
        self.add_impact_burst(pos, color, 1.35, 1.35, 2.1)
        self.add_beam(Vec3(0, 0, 1.3), pos + Vec3(0, 0, 0.55), color, 0.62, 2.1)
        if track == "core":
            self.hub_integrity = min(1.0, self.hub_integrity + 0.04 + level * 0.012)
            for art in self.artifacts:
                if art.hp > 0:
                    art.hp = min(art.max_hp, art.hp + 0.05 + level * 0.02)
        elif track == "forest":
            for plant in self.forest_plants:
                if plant.state != "regrowing":
                    plant.hp = min(plant.max_hp, plant.hp + 0.04 + level * 0.012)
        elif track == "urban":
            for troop in self.urban_troops:
                troop.max_hp = max(troop.max_hp, 1.25 + level * 0.045)
                troop.hp = min(troop.max_hp, troop.hp + 0.08)

    def upgrade_level(self, name: str) -> int:
        return int(self.upgrade_levels.get(name, 0))

    def active_count(self, ents: list[Entity]) -> int:
        return sum(1 for ent in ents if getattr(ent, "hp", 0) > 0)

    def fail_run(self, reason: str):
        self.log_region_event("CORE", "Metropolis", "overtook", reason, "enemy_win")
        self.last_run_score = self.score
        self.best_score = max(self.best_score, self.score)
        self.stats["run_failures"] = self.stats.get("run_failures", 0) + 1
        self.run_number += 1
        self.run_message = f"RUN RESET: {reason}  SCORE {self.last_run_score}"
        self.run_message_timer = 7.0
        self.score = 0
        self.combo = 1.0
        self.combo_timer = 0.0
        self.run_time = 0.0
        self.elapsed = 0.0
        self.wave_index = 1
        self.wave_phase = "assault"
        self.wave_phase_time = 0.0
        self.current_doctrine = self.wave_doctrine_name(self.wave_index)
        self.enemy_spawn_timer = 1.2
        self.command_energy = 55.0
        self.command_buffs = {name: 0.0 for name in self.command_buffs}
        self.command_cooldowns = {name: 0.0 for name in COMMAND_COOLDOWNS}
        self.upgrade_levels = {name: 0 for name in UPGRADE_ORDER}
        self.upgrade_points = 0
        self.reset_board(full=False)

    def enemy_spawn_interval(self) -> float:
        pressure_penalty = 0.42 if len(self.enemies) > 90 else 0.0
        base = 2.35 - min(1.35, (self.wave_index - 1) * 0.13)
        return max(0.58, base + pressure_penalty + self.rng.uniform(-0.12, 0.18))

    def apply_recovery_window(self):
        # The player gets a short breath between waves: modest passive repairs
        # and a visible core pulse, but no full reset.
        core_bonus = 0.012 * self.upgrade_level("core")
        self.hub_integrity = min(1.0, self.hub_integrity + 0.08 + core_bonus)
        self.command_energy = min(COMMAND_ENERGY_MAX, self.command_energy + 10.0 + self.core_rank * 0.8)
        for art in self.artifacts:
            if art.hp > 0:
                art.hp = min(art.max_hp, art.hp + 0.20)
        for troop_list in (self.urban_troops, self.desert_troops, self.mushroom_troops, self.hills_caretakers):
            for troop in troop_list:
                troop.hp = min(troop.max_hp, troop.hp + 0.18)
        self.add_impact_burst(Vec3(0, 0, 1.5), (0.40, 1.0, 1.0, 0.42), 1.7, 1.0, 2.2)

    def has_buff(self, name: str) -> bool:
        return self.command_buffs.get(name, 0.0) > 0.0

    def try_command(self, name: str, cost: float, region: str, color, label: str) -> bool:
        cooldown = float(self.command_cooldowns.get(name, 0.0))
        if cooldown > 0.0:
            self.stats["command_cooldown_denied"] = self.stats.get("command_cooldown_denied", 0) + 1
            self.command_flash = 1.1
            self.banner["text"] = f"COMMAND COOLING DOWN  //  {label} ready in {cooldown:0.1f}s"
            return False
        if self.command_energy < cost:
            self.stats["command_denied"] += 1
            self.command_flash = 1.2
            self.banner["text"] = f"COMMAND ENERGY LOW  //  {label} needs {cost:.0f}"
            return False
        self.command_energy -= cost
        self.command_cooldowns[name] = COMMAND_COOLDOWNS.get(name, 18.0)
        self.command_flash = 1.0
        self.stats["command_uses"] += 1
        self.add_score(10, f"COMMAND: {label} +10")
        spec = RINGS.get(region, RINGS["CORE"])
        pos = angle_to_pos(pos_angle(self.order_target) if self.order_target else 0.0, (spec["inner"] + spec["outer"]) * 0.5, RING_HEIGHTS[region] + 1.0)
        self.add_impact_burst(pos, color, 1.15, 1.25, 1.8)
        self.add_impact_burst(Vec3(0, 0, 1.3), (0.52, 1.0, 1.0, 0.36), 0.95, 1.1, 1.5)
        self.add_beam(Vec3(0, 0, 1.2), pos + Vec3(0, 0, 0.45), (color[0], color[1], color[2], 0.48), 0.55, 2.0)
        for pulse in self.command_pulses:
            if pulse.get("region") == region:
                pulse["burst"] = 1.0
        self.stats["defense_vectors"] = self.stats.get("defense_vectors", 0) + 1
        self.banner["text"] = f"COMMAND DEPLOYED  //  {label}"
        self.log_region_event(region, "Player", "deployed", label, "support")
        return True

    def command_rally_urban(self):
        if not self.try_command("urban_rally", 24.0, "URBAN", (0.18, 0.94, 1.0, 0.52), "URBAN RALLY"):
            return
        self.command_buffs["urban_rally"] = 22.0
        self.stats["rallies_called"] += 1
        for troop in self.urban_troops:
            troop.cooldown = min(troop.cooldown, 0.12)

    def command_overcharge_desert(self):
        if not self.try_command("desert_overcharge", 30.0, "DESERT", (1.0, 0.74, 0.16, 0.54), "DESERT LASER OVERCHARGE"):
            return
        self.command_buffs["desert_overcharge"] = 20.0
        self.stats["desert_overcharges"] += 1
        for p in self.pyramids:
            p.cooldown = min(p.cooldown, 0.16)

    def command_spore_bloom(self):
        if not self.try_command("spore_bloom", 26.0, "MUSHROOM", (1.0, 0.22, 0.94, 0.48), "SPORE BLOOM"):
            return
        self.command_buffs["spore_bloom"] = 18.0
        self.stats["spore_blooms"] += 1
        for m in self.mushrooms:
            if m.state == "regrowing":
                m.timer = min(m.timer, 10.0)

    def command_forest_surge(self):
        if not self.try_command("forest_surge", 28.0, "FOREST", (0.18, 1.0, 0.34, 0.50), "FOREST SUPPLY SURGE"):
            return
        self.command_buffs["forest_surge"] = 28.0
        self.stats["forest_surges"] += 1
        repaired = 0
        for plant in self.forest_plants:
            if plant.state == "regrowing" and repaired < 6:
                plant.timer = min(plant.timer, 22.0)
                repaired += 1
            elif plant.state != "regrowing":
                plant.hp = min(plant.max_hp, plant.hp + 0.22)

    def command_core_repair(self):
        if not self.try_command("core_repair", 34.0, "FLAT", (0.52, 1.0, 1.0, 0.54), "CORE ARTIFACT REPAIR"):
            return
        self.stats["repairs_called"] += 1
        self.hub_integrity = min(1.0, self.hub_integrity + 0.16)
        for art in self.artifacts:
            if art.hp > 0:
                art.hp = min(art.max_hp, art.hp + 0.34)

    def command_bot_overdrive(self):
        if not self.try_command("bot_overdrive", 44.0, "FLAT", (0.82, 1.0, 1.0, 0.58), "PRIMARY BOT OVERDRIVE"):
            return
        self.command_buffs["bot_overdrive"] = 16.0
        self.bot_overdrive_flash = 1.0
        self.stats["bot_overdrive_commands"] = self.stats.get("bot_overdrive_commands", 0) + 1
        for bot in self.bots:
            bot.cooldown = min(bot.cooldown, 0.06)
            bot.extra["ability_fx"] = max(float(bot.extra.get("ability_fx", 0.0)), 0.85)
            bot.extra["overdrive_until"] = max(float(bot.extra.get("overdrive_until", 0.0)), self.elapsed + 16.0)
        self.bot_power_message = "Primary bots: Overdrive armed"
        self.bot_power_message_timer = 4.2

    def update_space_battles(self, dt: float):
        for front in self.space_fronts:
            front["angle"] += front["drift"] * dt
            center = Vec3(
                math.cos(front["angle"]) * front["radius"],
                math.sin(front["angle"]) * front["radius"],
                front["z"] + math.sin(self.elapsed * 0.55 + front["pulse"]) * 4.8,
            )
            front["node"].setPos(center)
            for idx, fighter in enumerate(front["fighters"]):
                phase = fighter["phase"] + self.elapsed * fighter["speed"] * (1.0 if fighter["side"] == "ally" else -1.0)
                r = fighter["loop"] + math.sin(self.elapsed * 1.7 + fighter["phase"]) * 0.45
                x = math.cos(phase) * r
                y = math.sin(phase * 1.35) * (r * 0.72)
                z = math.sin(phase * 2.2 + fighter["pitch"]) * 0.95 + fighter["pitch"]
                fighter["node"].setPos(x, y, z)
                fighter["node"].setH(math.degrees(phase) + (90 if fighter["side"] == "ally" else -90))
            front["beam_timer"] -= dt
            if front["beam_timer"] <= 0.0:
                allies = [f for f in front["fighters"] if f["side"] == "ally"]
                enemies = [f for f in front["fighters"] if f["side"] == "enemy"]
                if allies and enemies:
                    a = self.rng.choice(allies)["node"].getPos(self.render)
                    b = self.rng.choice(enemies)["node"].getPos(self.render)
                    color = (0.22, 0.96, 1.0, 0.64) if self.rng.random() < 0.5 else (1.0, 0.24, 0.42, 0.64)
                    self.add_space_beam(a, b, color, 0.42 + self.rng.random() * 0.18, 1.8 + self.rng.random() * 1.0)
                front["beam_timer"] = 0.04 + self.rng.random() * 0.16

    def add_region_activity_beam(self, a: Vec3, b: Vec3, color, ttl: float = 0.16, thickness: float = 0.82):
        while len(self.region_activity_beams) >= MAX_AMBIENT_ACTIVITY_BEAMS:
            old_beam, _old_ttl = self.region_activity_beams.pop(0)
            old_beam.removeNode()
        av = Vec3(a.x, a.y, self.surface_z_at(a) + a.z)
        bv = Vec3(b.x, b.y, self.surface_z_at(b) + b.z)
        beam = add_line(self.fx_root, "region-activity-beam", av, bv, color, thickness)
        beam.setLightOff(1)
        self.region_activity_beams.append((beam, ttl))

    def update_region_activity(self, dt: float):
        # Moving activity layer: patrols, workers, water craft, wildlife trails,
        # and Metropolis mustering all stay visible from the clean overview.
        by_region: dict[str, list[Entity]] = {}
        for ent in self.region_activity_units:
            region = ent.extra.get("region", "")
            if region not in RINGS:
                continue
            spec = RINGS[region]
            pressure = self.region_pressure.get(region, 0.0)
            phase = float(ent.extra.get("phase", 0.0))
            base_r = float(ent.extra.get("base_radius", pos_radius(ent.pos)))
            # Pressure makes local traffic visibly scramble. Region activity is
            # also doctrine-aware through the pressure system, so an attacked
            # region becomes easier to spot even with the clean HUD.
            patrol_speed = ent.speed * (1.0 + pressure * 0.45)
            ent.angle += dt * patrol_speed * 0.115
            wobble = math.sin(self.elapsed * 0.84 + phase) * (0.30 + pressure * 0.45)
            radius = clamp(base_r + wobble, spec["inner"] + 0.28, spec["outer"] - 0.28)
            if region == "FLAT":
                radius = clamp(base_r + wobble * 0.45, 2.8, 5.8)
            ent.pos = angle_to_pos(ent.angle, radius, 0.72 + 0.10 * math.sin(self.elapsed * 1.3 + phase))
            if ent.node:
                ent.node.setH(math.degrees(ent.angle) + (90 if ent.speed >= 0 else -90))
                pulse = 0.5 + 0.5 * math.sin(self.elapsed * float(ent.extra.get("pulse_rate", 2.0)) + phase)
                ent.node.setAlphaScale(0.56 + pulse * 0.34 + pressure * 0.16)
            self.update_node(ent)
            by_region.setdefault(region, []).append(ent)

        self.activity_pulse_timer -= dt
        if self.activity_pulse_timer <= 0.0:
            # A small number of readable lane pulses per tick is better than a
            # constant snowstorm. Bias pulses toward threatened regions.
            ordered_regions = sorted(RINGS.keys(), key=lambda r: self.region_pressure.get(r, 0.0), reverse=True)
            for region in ordered_regions[:4]:
                units = by_region.get(region, [])
                if len(units) < 2:
                    continue
                a = self.rng.choice(units)
                b = self.rng.choice(units)
                if a is b:
                    continue
                color = (0.20, 0.95, 1.0, 0.18)
                if region == "METROPOLIS": color = (1.0, 0.16, 0.42, 0.24)
                elif region == "DESERT": color = (1.0, 0.68, 0.14, 0.20)
                elif region == "MUSHROOM": color = (1.0, 0.24, 1.0, 0.20)
                elif region in {"FOREST", "HILLS"}: color = (0.56, 1.0, 0.20, 0.18)
                self.add_region_activity_beam(a.pos + Vec3(0, 0, 0.26), b.pos + Vec3(0, 0, 0.26), color, 0.22, 0.74)
                self.stats["ambient_activity_pulses"] = self.stats.get("ambient_activity_pulses", 0) + 1
            self.activity_pulse_timer = 0.22

    def update_region_pressure(self, dt: float):
        # Low-pass filter tactical pressure by region for readable, stable pulses.
        for name in list(self.region_pressure.keys()):
            target = self.region_activity_level(name)
            self.region_pressure[name] += (target - self.region_pressure[name]) * clamp(dt * 2.2, 0.0, 1.0)
        self.stats["region_pressure_updates"] += 1
        self.stats["peak_enemies"] = max(self.stats.get("peak_enemies", 0), len(self.enemies))
        self.stats["peak_world_beams"] = max(self.stats.get("peak_world_beams", 0), len(self.beams))
        self.stats["peak_space_beams"] = max(self.stats.get("peak_space_beams", 0), len(self.space_beams))

    def update_frontline_action_fx(self, dt: float):
        # Pass 26: denser expanded world needs visible fighting even before
        # enemies reach every inner ring. These are lightweight, state-aware FX
        # bursts; they do not change damage math, only make active fronts read.
        if not self.enemies:
            return
        self.stats["frontline_skirmishes"] = int(self.stats.get("frontline_skirmishes", 0))
        # staggered low-cost pulses across the main combat seams
        if int((self.elapsed - dt) / 0.58) == int(self.elapsed / 0.58):
            return
        seam_options = [
            ("URBAN", self.urban_troops, (0.16, 0.94, 1.0, 0.36)),
            ("DESERT", self.desert_troops, (1.0, 0.62, 0.16, 0.32)),
            ("MUSHROOM", self.mushroom_troops, (1.0, 0.22, 0.92, 0.30)),
            ("HILLS", self.hills_caretakers + self.wildlife, (0.72, 1.0, 0.22, 0.26)),
        ]
        active = []
        for region, defenders, color in seam_options:
            enemies = [e for e in self.enemies if e.hp > 0 and self.region_for_radius(pos_radius(e.pos)) == region]
            live_defenders = [d for d in defenders if d.hp > 0]
            if enemies and live_defenders:
                active.append((self.rng.choice(live_defenders), self.rng.choice(enemies), color))
        # Always show outer Metro/Urban pressure once enough enemy squads exist.
        if not active and self.enemies and self.urban_troops:
            outer_enemies = [e for e in self.enemies if e.hp > 0 and self.region_for_radius(pos_radius(e.pos)) in {"METROPOLIS", "URBAN"}]
            live_urban = [u for u in self.urban_troops if u.hp > 0]
            if outer_enemies and live_urban:
                active.append((self.rng.choice(live_urban), self.rng.choice(outer_enemies), (0.18, 0.94, 1.0, 0.30)))
        for defender, enemy, color in active[:6]:
            self.add_beam(self.visual_point(defender.pos, 0.50), self.visual_point(enemy.pos, 0.54), color, 0.16, 1.0)
            self.add_beam(self.visual_point(enemy.pos, 0.46), self.visual_point(defender.pos, 0.44), (1.0, 0.16, 0.32, 0.22), 0.12, 0.78)
            # Pass 31: small expanding rings make impacts readable in the
            # larger overview without increasing damage or simulation load.
            self.add_impact_burst(enemy.pos, (color[0], color[1], color[2], 0.34), 0.36, 0.42, 0.70)
            if self.rng.random() < 0.45:
                self.add_impact_burst(defender.pos, (1.0, 0.16, 0.32, 0.22), 0.30, 0.32, 0.58)
            self.stats["frontline_skirmishes"] += 1

    def update_camera(self, dt: float):
        if OVERVIEW_SHOT and SCREENSHOT_PATH:
            # Fixed proof shot: all regions visible, including Core through Metropolis.
            self.camera.setPos(0, -188.0, 118.0)
            self.camera.lookAt(Vec3(0, 0, 1.0))
            return
        if ENEMY_FOCUS_SHOT and SCREENSHOT_PATH:
            # Fixed proof shot for enemy troop silhouettes on the Metropolis mustering deck.
            self.camera.setPos(-24.0, -76.0, -0.8)
            self.camera.lookAt(Vec3(-1.9, -50.2, -5.4))
            return
        if METROPOLIS_FOCUS and SCREENSHOT_PATH:
            # Fixed inspection shot used only for proof screenshots of the Metropolis/Urban war edge.
            # Pass 32 retunes this for the 3.10x visual board scale.
            self.camera.setPos(0, -244.0, 38.0)
            self.camera.lookAt(Vec3(0, -130.0, -4.4))
            return
        # Pass 15 camera: default WASD controls orbit/tilt around the terraced
        # mountain. Hold Ctrl for the old precision pan across the board.
        yaw_rad = math.radians(self.camera_yaw)
        radial = Vec3(math.cos(yaw_rad), math.sin(yaw_rad), 0.0)
        right = Vec3(-radial.y, radial.x, 0.0)
        if "control" in self.keys:
            speed = 16.0 * max(0.25, self.camera_zoom / 70.0)
            if "w" in self.keys:
                self.camera_center -= radial * speed * dt
            if "s" in self.keys:
                self.camera_center += radial * speed * dt
            if "a" in self.keys:
                self.camera_center -= right * speed * dt
            if "d" in self.keys:
                self.camera_center += right * speed * dt
        else:
            orbit_speed = 58.0
            tilt_speed = 42.0
            if "a" in self.keys:
                self.camera_yaw += orbit_speed * dt
            if "d" in self.keys:
                self.camera_yaw -= orbit_speed * dt
            if "w" in self.keys:
                self.camera_pitch += tilt_speed * dt
            if "s" in self.keys:
                self.camera_pitch -= tilt_speed * dt
        limit = 96.0 * WORLD_EXPANSION_SCALE
        self.camera_center.x = clamp(self.camera_center.x, -limit, limit)
        self.camera_center.y = clamp(self.camera_center.y, -limit, limit)
        self.camera_pitch = clamp(self.camera_pitch, 30.0, 84.0)
        self.camera_yaw = (self.camera_yaw + 360.0) % 360.0
        pitch_rad = math.radians(self.camera_pitch)
        height = math.sin(pitch_rad) * self.camera_zoom
        back = math.cos(pitch_rad) * self.camera_zoom
        yaw_rad = math.radians(self.camera_yaw)
        cam_pos = Vec3(
            self.camera_center.x + math.cos(yaw_rad) * back,
            self.camera_center.y + math.sin(yaw_rad) * back,
            height,
        )
        look_at = Vec3(self.camera_center.x, self.camera_center.y, 1.65)
        self.camera.setPos(cam_pos)
        self.camera.lookAt(look_at)

    def zoom_camera(self, amount: float):
        self.camera_zoom = clamp(self.camera_zoom + amount * 1.6, 70.0, 520.0)

    def adjust_pitch(self, amount: float):
        self.camera_pitch = clamp(self.camera_pitch + amount, 30.0, 84.0)

    def reset_camera(self):
        self.focus_overview_camera()

    def focus_overview_camera(self):
        # Pass 23 default/readability view: all rings visible from Core through Metropolis.
        self.camera_center = Vec3(0, 0, 0)
        self.camera_zoom = 352.0
        self.camera_pitch = 64.0
        self.camera_yaw = -55.0
        self.update_camera(0.0)

    def focus_metropolis_camera(self):
        # Pass 32 inspection view: orbit in close on the enlarged Metropolis and Urban warfare edge.
        self.camera_center = Vec3(0, -40.8 * WORLD_EXPANSION_SCALE, -1.8)
        self.camera_zoom = 188.0
        self.camera_pitch = 52.0
        self.camera_yaw = -90.0
        self.update_camera(0.0)

    def focus_enemy_camera(self):
        # Pass 25 inspection view: closer to the enemy troop mustering area.
        self.camera_center = Vec3(-1.5 * WORLD_EXPANSION_SCALE, -39.2 * WORLD_EXPANSION_SCALE, -5.2)
        self.camera_zoom = 112.0
        self.camera_pitch = 52.0
        self.camera_yaw = -112.0
        self.update_camera(0.0)

    def mouse_world_point(self) -> Optional[Vec3]:
        if not self.mouseWatcherNode.hasMouse():
            return None
        m = self.mouseWatcherNode.getMouse()
        near = Vec3()
        far = Vec3()
        if not self.camLens.extrude(m, near, far):
            return None
        near_w = self.render.getRelativePoint(self.camera, near)
        far_w = self.render.getRelativePoint(self.camera, far)
        direction = far_w - near_w
        if abs(direction.z) < 1e-5:
            return None
        t = -near_w.z / direction.z
        if t < 0:
            return None
        p = near_w + direction * t
        # Board roots are visually expanded in XY. Convert mouse hits back to
        # simulation units so orders still land in the correct strategic ring.
        return Vec3(p.x / WORLD_EXPANSION_SCALE, p.y / WORLD_EXPANSION_SCALE, 0.5)

    def issue_mouse_order(self):
        p = self.mouse_world_point()
        if p is None:
            return
        r = pos_radius(p)
        if r > RINGS["METROPOLIS"]["outer"] + 2.0:
            return
        self.order_target = p
        self.command_count += 1
        self.last_region = self.region_for_radius(r)
        self.selected_region = self.last_region
        self.activity_panel_visible = True
        self.stats["activity_region_clicks"] = self.stats.get("activity_region_clicks", 0) + 1
        self.log_region_event(self.last_region, "Player", "ordered", RINGS.get(self.last_region, {}).get("purpose", "region"), "support")
        self.add_beam(Vec3(p.x - 0.8, p.y, 1.0), Vec3(p.x + 0.8, p.y, 1.0), (0.2, 1.0, 0.92, 0.92), 0.55, 2.5)
        self.add_beam(Vec3(p.x, p.y - 0.8, 1.0), Vec3(p.x, p.y + 0.8, 1.0), (0.2, 1.0, 0.92, 0.92), 0.55, 2.5)
        self.add_impact_burst(p, (0.20, 1.0, 0.92, 0.62), 0.70, 0.85, 1.20)

    def cancel_order(self):
        self.order_target = None
        self.activity_panel_visible = False
        self.selected_region = ""
        if hasattr(self, "hud_activity"):
            self.hud_activity.hide()

    def pulse_logic_layer(self):
        """Manual readability pulse for reviewing how models connect to logic."""
        for pulse in self.logic_pulses + self.region_status_pulses + self.battlefront_pulses + self.command_pulses:
            node = pulse.get("node")
            if node is not None and not node.isEmpty():
                node.setScale(1.85)
                node.setAlphaScale(0.95)
        self.banner["text"] = "LOGIC LAYER PULSE  //  region systems and model links highlighted"

    def region_for_radius(self, radius: float) -> str:
        for name, spec in RINGS.items():
            if spec["inner"] <= radius <= spec["outer"]:
                return name
        return "OUTER"

    def move_towards(self, ent: Entity, target: Vec3, dt: float, speed_mult: float = 1.0):
        d = flat_direction(ent.pos, target)
        ent.pos += d * ent.speed * speed_mult * dt

    def nearest_enemy(self, pos: Vec3, max_dist: float = 999.0) -> Optional[Entity]:
        best = None
        best_d = max_dist
        for e in self.enemies:
            if e.hp <= 0:
                continue
            d = distance(pos, e.pos)
            if d < best_d:
                best = e
                best_d = d
        return best

    def nearest_alive_artifact(self, pos: Vec3) -> Optional[Entity]:
        best = None
        best_d = 999.0
        for a in self.artifacts:
            if a.hp <= 0:
                continue
            d = distance(pos, a.pos)
            if d < best_d:
                best = a
                best_d = d
        return best

    def enemy_squad_cohesion(self, enemy: Entity, dt: float) -> float:
        """Keep large-region enemy squads readable instead of scattered dots."""
        squad_id = enemy.extra.get("squad")
        if squad_id is None:
            return 1.0
        mates = [e for e in self.enemies if e is not enemy and e.hp > 0 and e.extra.get("squad") == squad_id]
        if not mates:
            return 1.0
        cx = sum(e.pos.x for e in mates + [enemy]) / (len(mates) + 1)
        cy = sum(e.pos.y for e in mates + [enemy]) / (len(mates) + 1)
        center = Vec3(cx, cy, enemy.pos.z)
        spread = distance(enemy.pos, center)
        # Commanders are the anchor; other squad members regain formation if
        # they drift too far apart in the enlarged rings.
        if spread > 3.25 and enemy.extra.get("variant") != "enemy_commander":
            self.move_towards(enemy, center, dt, 0.62)
            enemy.extra["regroup_fx"] = max(0.0, float(enemy.extra.get("regroup_fx", 0.0)) - dt)
            if enemy.extra.get("regroup_fx", 0.0) <= 0.0:
                self.add_beam(self.visual_point(enemy.pos, 0.36), self.visual_point(center, 0.42), (1.0, 0.42, 0.18, 0.16), 0.12, 0.62)
                enemy.extra["regroup_fx"] = 1.35
                self.stats["enemy_regroups"] += 1
            return 0.84
        return 1.0

    def enemy_commander_support(self, enemy: Entity, dt: float) -> float:
        squad_id = enemy.extra.get("squad")
        variant = enemy.extra.get("variant", enemy.kind)
        has_commander = False
        commander_pos = None
        for other in self.enemies:
            if other is enemy or other.hp <= 0:
                continue
            if other.extra.get("squad") == squad_id and other.extra.get("variant") == "enemy_commander":
                if distance(other.pos, enemy.pos) < 5.4:
                    has_commander = True
                    commander_pos = other.pos
                    break
        if has_commander:
            enemy.extra["support_fx"] = max(0.0, float(enemy.extra.get("support_fx", 0.0)) - dt)
            if commander_pos is not None and enemy.extra.get("support_fx", 0.0) <= 0.0 and variant != "enemy_commander":
                self.add_beam(self.visual_point(commander_pos, 0.74), self.visual_point(enemy.pos, 0.48), (1.0, 0.74, 0.18, 0.22), 0.14, 0.88)
                enemy.extra["support_fx"] = 1.25
                self.stats["enemy_support_links"] += 1
            return 1.10
        return 1.0

    def enemy_special_actions(self, enemy: Entity, region: str, dt: float) -> bool:
        variant = enemy.extra.get("variant", enemy.kind)
        if enemy.extra.get("jammed_until", 0.0) > self.elapsed:
            # Solace and Archivist can temporarily shut down special enemy tools
            # without freezing movement, so the squad still advances but loses its trick.
            enemy.extra["jam_fx"] = max(0.0, float(enemy.extra.get("jam_fx", 0.0)) - dt)
            if enemy.extra.get("jam_fx", 0.0) <= 0.0:
                self.add_impact_burst(enemy.pos, (0.42, 0.70, 1.0, 0.22), 0.30, 0.40, 0.70)
                enemy.extra["jam_fx"] = 1.4
            return False
        # Hackers disrupt nearby defenders instead of simply charging forward.
        if variant == "enemy_hacker":
            enemy.extra["hack_fx"] = max(0.0, float(enemy.extra.get("hack_fx", 0.0)) - dt)
            targets = [t for t in (self.urban_troops + self.desert_troops + self.mushroom_troops + self.hills_caretakers + self.bots) if t.hp > 0 and distance(t.pos, enemy.pos) < 3.6]
            if targets and enemy.extra.get("hack_fx", 0.0) <= 0.0:
                target = min(targets, key=lambda t: distance(t.pos, enemy.pos))
                target.cooldown = max(target.cooldown, 0.62)
                self.add_beam(self.visual_point(enemy.pos, 0.58), self.visual_point(target.pos, 0.50), (1.0, 0.08, 0.92, 0.50), 0.22, 1.7)
                enemy.extra["hack_fx"] = 1.2
                self.stats["enemy_hacks"] += 1
                return True
        # Siege walkers fire at important targets from farther out.
        if variant == "enemy_siege":
            enemy.extra["siege_fx"] = max(0.0, float(enemy.extra.get("siege_fx", 0.0)) - dt)
            if enemy.extra.get("siege_fx", 0.0) <= 0.0:
                target = None
                if region == "FOREST":
                    target = self.nearest_forest_plant(enemy.pos, active_only=True)
                    if target and distance(enemy.pos, target.pos) > 4.2:
                        target = None
                elif region in {"FLAT", "CORE"}:
                    target = self.nearest_alive_artifact(enemy.pos)
                    if target and distance(enemy.pos, target.pos) > 5.6:
                        target = None
                if target is not None:
                    target.hp -= 0.055
                    self.flash_entity(target, (1.0, 0.10, 0.62, 0.92))
                    self.add_beam(self.visual_point(enemy.pos, 0.78), self.visual_point(target.pos, 0.58), (1.0, 0.22, 0.92, 0.62), 0.25, 2.1)
                    enemy.extra["siege_fx"] = 1.05
                    self.stats["enemy_siege_shots"] += 1
                    if getattr(target, "kind", "") in {"tree", "bush"} and target.hp <= 0:
                        self.destroy_plant(target)
                    return True
        if variant == "enemy_carrier":
            enemy.extra["carrier_fx"] = max(0.0, float(enemy.extra.get("carrier_fx", 0.0)) - dt)
            deployed = int(enemy.extra.get("carrier_deployed", 0))
            if deployed < 3 and enemy.extra.get("carrier_fx", 0.0) <= 0.0 and len(self.enemies) < 120:
                a = pos_angle(enemy.pos) + self.rng.uniform(-0.035, 0.035)
                r = pos_radius(enemy.pos) + self.rng.uniform(-0.24, 0.34)
                child = self.spawn_enemy_unit("enemy_scout", int(enemy.extra.get("gate", 0)), a, r, int(enemy.extra.get("squad", 0)), 20 + deployed, 24)
                if child is not None:
                    child.extra["carrier_child"] = True
                    child.speed *= 1.10
                    enemy.extra["carrier_deployed"] = deployed + 1
                    self.stats["enemy_carrier_deploys"] = self.stats.get("enemy_carrier_deploys", 0) + 1
                    self.stats["enemies_spawned"] += 1
                    self.add_beam(self.visual_point(enemy.pos, 0.66), self.visual_point(child.pos, 0.44), (1.0, 0.34, 0.82, 0.42), 0.20, 1.1)
                enemy.extra["carrier_fx"] = 5.8
        if variant == "enemy_harvester" and region in {"FOREST", "MUSHROOM", "FLAT"}:
            enemy.extra["harvest_fx"] = max(0.0, float(enemy.extra.get("harvest_fx", 0.0)) - dt)
            if enemy.extra.get("harvest_fx", 0.0) <= 0.0:
                target = self.nearest_forest_plant(enemy.pos, active_only=True) if region == "FOREST" else None
                if target is not None and distance(enemy.pos, target.pos) < 4.8:
                    target.hp -= 0.035
                    self.command_energy = max(0.0, self.command_energy - 1.4)
                    self.add_beam(self.visual_point(enemy.pos, 0.54), self.visual_point(target.pos, 0.44), (0.56, 1.0, 0.18, 0.44), 0.28, 1.5)
                    if target.hp <= 0:
                        self.destroy_plant(target)
                else:
                    self.command_energy = max(0.0, self.command_energy - 0.7)
                    self.add_impact_burst(enemy.pos, (0.56, 1.0, 0.18, 0.24), 0.34, 0.46, 0.7)
                enemy.extra["harvest_fx"] = 2.8
                self.stats["enemy_harvests"] = self.stats.get("enemy_harvests", 0) + 1
                return True
        return False

    def update_enemies(self, dt: float):
        water_outer = RINGS["WATER"]["outer"]
        water_inner = RINGS["WATER"]["inner"]
        for enemy in list(self.enemies):
            if enemy.hp <= 0:
                self.record_enemy_death(enemy)
                self.reward_command_energy_for_kill(enemy)
                self.remove_entity(enemy, self.enemies)
                self.stats["enemies_destroyed"] += 1
                continue
            confused = float(enemy.extra.get("confused", 0.0))
            if confused > 0:
                enemy.extra["confused"] = max(0.0, confused - dt)
                enemy.angle += math.sin(self.elapsed * 2.0 + enemy.angle) * dt * 1.7
                tangent = Vec3(-math.sin(enemy.angle), math.cos(enemy.angle), 0)
                enemy.pos += tangent * enemy.speed * dt * 1.25
                if enemy.cooldown <= 0:
                    self.confused_fire(enemy)
                    enemy.cooldown = 0.72
                enemy.cooldown -= dt
                self.clamp_enemy_radius(enemy)
                self.update_node(enemy)
                continue

            r = pos_radius(enemy.pos)
            region = self.region_for_radius(r)
            self.update_enemy_squad_record(enemy, region, dt)
            if enemy.state == "building_vessel":
                enemy.timer -= dt
                enemy.node.setColor(1.0, 0.44, 0.18, 0.96)
                if enemy.timer <= 0:
                    enemy.state = "crossing_water"
                    enemy.extra["vessel"] = True
                    enemy.node.setColor(0.65, 0.20, 1.0, 0.96)
                    self.stats["water_vessels"] += 1
                self.update_node(enemy)
                continue
            if (not enemy.extra.get("vessel")) and r <= water_outer + 0.08 and r > water_inner:
                enemy.state = "building_vessel"
                # Sappers are naval engineers, so enemy vessel construction is
                # faster when this class reaches Water. Other troops still use
                # the original 5-second build window.
                enemy.timer = 3.5 if enemy.extra.get("variant") == "enemy_sapper" else (2.8 if enemy.extra.get("variant") == "enemy_phantom" else 5.0)
                self.update_node(enemy)
                continue

            speed_mult = 0.34 if enemy.state == "crossing_water" and r > water_inner else 1.0
            if enemy.extra.get("slow_until", 0.0) > self.elapsed:
                speed_mult *= 0.48
            if enemy.extra.get("panic_until", 0.0) > self.elapsed:
                speed_mult *= 0.72
            if enemy.extra.get("jammed_until", 0.0) > self.elapsed:
                speed_mult *= 0.88
            if enemy.state == "crossing_water" and r <= water_inner:
                enemy.state = "active"
            climb_mult = self.climb_speed_multiplier(enemy)
            speed_mult *= climb_mult
            speed_mult *= self.enemy_commander_support(enemy, dt)
            speed_mult *= self.enemy_squad_cohesion(enemy, dt)
            enemy.extra["climb_fx"] = max(0.0, float(enemy.extra.get("climb_fx", 0.0)) - dt)
            if climb_mult < 0.99 and enemy.extra.get("climb_fx", 0.0) <= 0.0:
                inward = set_radius(enemy.pos, max(0.55, r - 0.95))
                self.add_beam(self.visual_point(enemy.pos, 0.26), self.visual_point(inward, 0.44), (1.0, 0.62, 0.20, 0.24), 0.14, 1.8)
                enemy.extra["climb_fx"] = 0.26
            lane_angle = float(enemy.extra.get("lane_angle", pos_angle(enemy.pos)))
            lane_wobble = math.sin(self.elapsed * 0.55 + float(enemy.extra.get("slot", 0))) * 0.025
            variant = enemy.extra.get("variant", enemy.kind)
            step = 8.5
            if variant in {"enemy_scout", "enemy_phantom"}:
                step = 10.4
            elif variant in {"enemy_commander", "enemy_siege", "enemy_carrier"}:
                step = 5.8
            elif variant == "enemy_harvester":
                step = 7.2
            target_radius = max(0.0, r - step)
            target = angle_to_pos(lane_angle + lane_wobble, target_radius, enemy.pos.z)
            if variant == "enemy_harvester" and region == "FOREST":
                plant_target = self.nearest_forest_plant(enemy.pos, active_only=True)
                if plant_target is not None:
                    target = plant_target.pos

            # Forest plants and core artifacts are priority targets.
            if self.enemy_special_actions(enemy, region, dt):
                self.update_node(enemy)
                continue
            if region == "FOREST":
                plant = self.nearest_forest_plant(enemy.pos, active_only=True)
                if plant and distance(enemy.pos, plant.pos) < 1.55:
                    plant.hp -= dt * 0.12 * float(enemy.extra.get("damage", 1.0)) * max(0.55, 1.0 - self.upgrade_level("forest") * 0.055)
                    self.forest_attack_timer = 9.0
                    enemy.cooldown -= dt
                    if enemy.cooldown <= 0.0:
                        self.add_impact_burst(plant.pos, (0.18, 1.0, 0.34, 0.26), 0.32, 0.42, 0.72)
                        enemy.cooldown = 0.46
                    if plant.hp <= 0:
                        self.destroy_plant(plant)
                    self.update_node(enemy)
                    continue
            if region in {"FLAT", "CORE"}:
                artifact = self.nearest_alive_artifact(enemy.pos)
                if artifact and distance(enemy.pos, artifact.pos) < 1.45:
                    incoming = dt * 0.11 * float(enemy.extra.get("damage", 1.0)) * max(0.52, 1.0 - self.upgrade_level("core") * 0.065)
                    if artifact.extra.get("mirror_ward_until", 0.0) > self.elapsed:
                        reflected = incoming * 0.38
                        incoming *= 0.42
                        self.apply_enemy_damage(enemy, reflected, "reflect", artifact.pos)
                        if enemy.cooldown <= 0.0:
                            self.add_beam(self.visual_point(artifact.pos, 0.72), self.visual_point(enemy.pos, 0.56), (0.72, 1.0, 1.0, 0.46), 0.18, 1.2)
                        self.stats["mirror_prism_wards"] = self.stats.get("mirror_prism_wards", 0) + 1
                    old_artifact_hp = artifact.hp
                    artifact.hp = max(0.0, artifact.hp - incoming)
                    if old_artifact_hp > 0.0 and artifact.hp <= 0.0:
                        self.log_region_event("FLAT", "Metropolis", "destroyed", f"{artifact.extra.get('bot', 'Core')} artifact", "enemy_win")
                    self.flash_entity(artifact, (1.0, 0.12, 0.16, 0.94))
                    if enemy.cooldown <= 0.0:
                        self.add_impact_burst(artifact.pos, (1.0, 0.16, 0.24, 0.34), 0.36, 0.52, 0.90)
                        enemy.cooldown = 0.52
                    else:
                        enemy.cooldown -= dt
                    self.update_node(enemy)
                    continue
                elif not artifact:
                    self.hub_integrity = max(0.0, self.hub_integrity - dt * 0.08 * max(0.50, 1.0 - self.upgrade_level("core") * 0.075))

            self.move_towards(enemy, target, dt, speed_mult)
            enemy.node.setH(math.degrees(pos_angle(enemy.pos)) + 90)
            if enemy.extra.get("marked_until", 0.0) > self.elapsed and enemy.node:
                enemy.node.setAlphaScale(0.82 + 0.18 * math.sin(self.elapsed * 8.0))
            elif enemy.node:
                enemy.node.setAlphaScale(1.0)
            self.clamp_enemy_radius(enemy)
            self.update_node(enemy)

        if self.hub_integrity <= 0.0:
            self.fail_run("HUB COLLAPSED")
            return
        if self.artifacts and all(a.hp <= 0 for a in self.artifacts):
            self.fail_run("ARTIFACTS DESTROYED")
            return

    def clamp_enemy_radius(self, enemy: Entity):
        r = pos_radius(enemy.pos)
        if r < 0.5:
            enemy.pos = set_radius(enemy.pos, 0.5)
        if r > 43.5:
            enemy.pos = set_radius(enemy.pos, 43.5)

    def climb_speed_multiplier(self, enemy: Entity) -> float:
        """Slow enemies while they traverse uphill terrace transitions."""
        r = pos_radius(enemy.pos)
        region = self.region_for_radius(r)
        spec = RINGS.get(region)
        if not spec or region in {"CORE", "OUTER"}:
            enemy.extra["climbing"] = 0.0
            return 1.0
        edge_dist = abs(r - spec["inner"])
        if edge_dist > 0.85:
            enemy.extra["climbing"] = max(0.0, float(enemy.extra.get("climbing", 0.0)) - 0.8)
            return 1.0
        next_inner = inner_ring(region)
        if not next_inner:
            enemy.extra["climbing"] = 0.0
            return 1.0
        height_delta = max(0.0, RING_HEIGHTS[next_inner] - RING_HEIGHTS[region])
        enemy.extra["climbing"] = height_delta
        return clamp(1.0 - 0.11 * height_delta, 0.33, 0.86)

    def nearest_forest_plant(self, pos: Vec3, active_only: bool = True) -> Optional[Entity]:
        best = None
        best_d = 999.0
        for plant in self.forest_plants:
            if active_only and plant.state == "regrowing":
                continue
            d = distance(pos, plant.pos)
            if d < best_d:
                best = plant
                best_d = d
        return best

    def update_defenses(self, dt: float):
        self.update_urban_troops(dt)
        self.update_ring_troops(self.desert_troops, dt, ring="DESERT", damage=0.09, attack_range=1.7, defend_radius=5.4)
        self.update_ring_troops(self.mushroom_troops, dt, ring="MUSHROOM", damage=0.045, attack_range=1.35, defend_radius=4.1)
        self.update_hills_caretakers(dt)
        self.update_wildlife(dt)
        self.update_pyramids(dt)
        self.update_mushrooms(dt)
        self.update_artifact_bots(dt)

    def update_urban_troops(self, dt: float):
        water_outer = RINGS["WATER"]["outer"]
        for troop in self.urban_troops:
            target = self.nearest_enemy(troop.pos, 7.2)
            if self.order_target and self.region_for_radius(pos_radius(self.order_target)) in {"URBAN", "METROPOLIS"}:
                target_point = set_radius(self.order_target, max(water_outer + 0.35, pos_radius(self.order_target)))
            elif target:
                target_point = Vec3(target.pos)
                if pos_radius(target_point) < water_outer + 0.35:
                    target_point = set_radius(target_point, water_outer + 0.35)
            else:
                troop.angle += dt * 0.18
                target_point = angle_to_pos(troop.angle, 33.4 + math.sin(self.elapsed + troop.angle) * 0.9, troop.pos.z)
            urban_lvl = self.upgrade_level("urban")
            rally_mult = (1.38 if self.has_buff("urban_rally") else 1.0) * (1.0 + urban_lvl * 0.035)
            troop.max_hp = max(troop.max_hp, 1.25 + urban_lvl * 0.045)
            troop.hp = min(troop.max_hp, troop.hp + dt * urban_lvl * 0.004)
            self.move_towards(troop, target_point, dt, rally_mult)
            if pos_radius(troop.pos) < water_outer + 0.22:
                troop.pos = set_radius(troop.pos, water_outer + 0.22)
            if target and distance(troop.pos, target.pos) < 2.0 and troop.cooldown <= 0:
                dmg = 0.075 * (1.45 if self.has_buff("urban_rally") else 1.0) * (1.0 + urban_lvl * 0.09)
                self.apply_enemy_damage(target, dmg, "urban", troop.pos)
                self.add_beam(troop.pos + Vec3(0, 0, 0.2), target.pos + Vec3(0, 0, 0.2), (0.12, 0.95, 1.0, 0.92), 0.22)
                troop.cooldown = 0.26 if self.has_buff("urban_rally") else 0.38
            troop.cooldown = max(0.0, troop.cooldown - dt)
            self.update_node(troop)

    def update_ring_troops(self, troops: list[Entity], dt: float, *, ring: str, damage: float, attack_range: float, defend_radius: float):
        spec = RINGS[ring]
        mid = (spec["inner"] + spec["outer"]) * 0.5
        for troop in troops:
            target = self.nearest_enemy(troop.pos, defend_radius)
            if self.order_target and self.region_for_radius(pos_radius(self.order_target)) == ring:
                target_point = self.order_target
            elif target:
                target_point = target.pos
            else:
                troop.angle += dt * 0.14
                target_point = angle_to_pos(troop.angle, mid + math.sin(self.elapsed * 0.7 + troop.angle) * 0.9, troop.pos.z)
            self.move_towards(troop, target_point, dt)
            r = pos_radius(troop.pos)
            if r < spec["inner"] + 0.2:
                troop.pos = set_radius(troop.pos, spec["inner"] + 0.2)
            if r > spec["outer"] - 0.2:
                troop.pos = set_radius(troop.pos, spec["outer"] - 0.2)
            if target and distance(troop.pos, target.pos) < attack_range and troop.cooldown <= 0:
                level_bonus = 1.0
                if ring == "DESERT":
                    level_bonus += self.upgrade_level("desert") * 0.075
                elif ring == "MUSHROOM":
                    level_bonus += self.upgrade_level("mushroom") * 0.065
                self.apply_enemy_damage(target, damage * level_bonus, "direct", troop.pos)
                beam_color = (1.0, 0.62, 0.18, 0.84) if ring == "DESERT" else (0.90, 0.18, 1.0, 0.72)
                self.add_beam(troop.pos + Vec3(0, 0, 0.16), target.pos + Vec3(0, 0, 0.16), beam_color, 0.16)
                troop.cooldown = 0.75
            troop.cooldown = max(0.0, troop.cooldown - dt)
            self.update_node(troop)

    def update_hills_caretakers(self, dt: float):
        spec = RINGS["HILLS"]
        mid = (spec["inner"] + spec["outer"]) * 0.5
        for caretaker in self.hills_caretakers:
            hurt_animal = next((w for w in self.wildlife if w.hp < w.max_hp), None)
            target = self.nearest_enemy(caretaker.pos, 3.7)
            if hurt_animal:
                target_point = hurt_animal.pos
                if distance(caretaker.pos, hurt_animal.pos) < 1.0:
                    hurt_animal.hp = min(hurt_animal.max_hp, hurt_animal.hp + dt * 0.08)
            elif target:
                target_point = target.pos
            else:
                caretaker.angle += dt * 0.11
                target_point = angle_to_pos(caretaker.angle, mid, caretaker.pos.z)
            self.move_towards(caretaker, target_point, dt)
            r = pos_radius(caretaker.pos)
            if r < spec["inner"] + 0.2:
                caretaker.pos = set_radius(caretaker.pos, spec["inner"] + 0.2)
            if r > spec["outer"] - 0.2:
                caretaker.pos = set_radius(caretaker.pos, spec["outer"] - 0.2)
            if target and distance(caretaker.pos, target.pos) < 1.2 and caretaker.cooldown <= 0:
                self.apply_enemy_damage(target, 0.03, "direct", caretaker.pos)
                caretaker.cooldown = 1.0
            caretaker.cooldown = max(0.0, caretaker.cooldown - dt)
            self.update_node(caretaker)

    def update_wildlife(self, dt: float):
        forest_lvl = self.upgrade_level("forest")
        bush_bonus = self.bush_growth_bonus() * (1.0 + forest_lvl * 0.06)
        tree_bonus = self.tree_strength_bonus() * (1.0 + forest_lvl * 0.05)
        aggressive = self.forest_attack_timer > 0.0
        for animal in self.wildlife:
            if self.forest_supply_safe:
                animal.growth = min(1.0, animal.growth + dt / 180.0 * bush_bonus)
            pack_boost = animal.extra.get("pack_boost_until", 0.0) > self.elapsed
            animal.max_hp = 0.30 + animal.growth * 1.05 + (0.10 if pack_boost else 0.0)
            animal.hp = min(animal.max_hp, animal.hp + dt * (0.052 if pack_boost else 0.035))
            size = 0.16 + animal.growth * 0.22 + (0.04 if pack_boost else 0.0)
            animal.node.setScale(size)
            animal.node.setColor(1.0 if aggressive or pack_boost else 0.88, 0.44 if pack_boost else (0.36 if aggressive else 1.0), 0.82 if pack_boost else (0.22 if aggressive else 0.32), 0.92)
            target = self.nearest_enemy(animal.pos, 5.3 if (aggressive or pack_boost) else 2.1)
            if target and (aggressive or self.region_for_radius(pos_radius(target.pos)) == "HILLS"):
                self.move_towards(animal, target.pos, dt, (1.18 if pack_boost else 1.0) + animal.growth)
                if distance(animal.pos, target.pos) < 1.05 and animal.cooldown <= 0:
                    target.hp -= (0.025 + animal.growth * (0.16 if pack_boost else 0.12)) * tree_bonus
                    animal.hp -= 0.012 if animal.growth > 0.45 else 0.045
                    animal.cooldown = 0.82
            else:
                animal.angle += dt * 0.16
                mid = 13.2 + math.sin(self.elapsed * 0.5 + animal.angle) * 1.1
                self.move_towards(animal, angle_to_pos(animal.angle, mid, animal.pos.z), dt, 0.65)
            animal.cooldown = max(0.0, animal.cooldown - dt)
            if animal.hp <= 0:
                animal.hp = 0.18
                animal.growth = max(0.0, animal.growth - 0.25)
                animal.pos = angle_to_pos(animal.angle, 13.4, animal.pos.z)
            self.update_node(animal)

    def update_pyramids(self, dt: float):
        for p in self.pyramids:
            p.cooldown = max(0.0, p.cooldown - dt)
            overcharged = self.has_buff("desert_overcharge")
            desert_lvl = self.upgrade_level("desert")
            ember_link = p.extra.get("ember_link_until", 0.0) > self.elapsed
            target = self.nearest_enemy(p.pos, p.extra["range"] * (1.45 if ember_link else 1.0) * (1.32 if overcharged else 1.0) * (1.0 + desert_lvl * 0.045))
            if target and p.cooldown <= 0:
                self.apply_enemy_damage(target, 0.18 * (1.30 if ember_link else 1.0) * (1.65 if overcharged else 1.0) * (1.0 + desert_lvl * 0.09), "laser", p.pos)
                self.stats["laser_hits"] += 1
                self.add_beam(p.pos + Vec3(0, 0, 0.4), target.pos + Vec3(0, 0, 0.25), (1.0, 0.82, 0.14, 1.0), 0.32, 3.5)
                p.cooldown = (0.62 if ember_link else (0.82 if overcharged else 1.25)) * max(0.72, 1.0 - desert_lvl * 0.045)
            pulse = 0.72 + 0.24 * math.sin(self.elapsed * (6.2 if ember_link else (5.6 if self.has_buff("desert_overcharge") else 4.0)) + p.angle)
            p.node.setColor(1.0, 0.62 + pulse * 0.24, 0.12, 0.82 + pulse * 0.14)
            self.update_node(p)

    def update_mushrooms(self, dt: float):
        for m in self.mushrooms:
            if m.state == "regrowing":
                m.timer -= dt
                if m.node:
                    m.node.setAlphaScale(0.18 + 0.28 * (1.0 - clamp(m.timer / 60.0, 0.0, 1.0)))
                if m.timer <= 0:
                    m.state = "active"
                    m.hp = 1.0
                    if m.node:
                        m.node.setAlphaScale(1.0)
                continue
            trigger_range = m.extra.get("trigger", 1.8) * (1.45 if self.has_buff("spore_bloom") else 1.0) * (1.0 + self.upgrade_level("mushroom") * 0.045)
            target = self.nearest_enemy(m.pos, trigger_range)
            if target:
                self.explode_mushroom(m, target)
            else:
                m.node.setColor(0.88 + 0.12 * math.sin(self.elapsed * 3.0 + m.angle), 0.12, 0.86, 0.78)
            self.update_node(m)

    def explode_mushroom(self, m: Entity, target: Entity):
        m.state = "regrowing"
        m.timer = float(m.extra.get("regrow", 60.0))
        m.hp = 0.0
        m.node.setAlphaScale(0.16)
        self.stats["spore_explosions"] += 1
        for enemy in self.enemies:
            if distance(enemy.pos, m.pos) < 2.8:
                if enemy.extra.get("variant") == "enemy_phantom":
                    enemy.extra["confused"] = 1.35
                    self.stats["enemy_phantom_bypasses"] = self.stats.get("enemy_phantom_bypasses", 0) + 1
                else:
                    enemy.extra["confused"] = 6.5 if self.has_buff("spore_bloom") else 5.0
                self.stats["confused"] += 1
                # The smoke confuses only; it does not kill directly.
                enemy.hp = max(enemy.hp, 0.05)
        smoke = Entity("smoke", Vec3(m.pos), timer=5.0, angle=m.angle)
        smoke.node = make_cylinder("spore-smoke-plume", 1.0, 1.35, 28)
        smoke.node.reparentTo(self.fx_root)
        smoke.node.setPos(self.visual_point(m.pos, m.pos.z + 0.15))
        smoke.node.setColor(0.62, 0.54, 0.72, 0.26)
        smoke.node.setTransparency(TransparencyAttrib.MAlpha)
        add_wireframe_copy(smoke.node, (1.0, 0.75, 1.0, 0.12), 1.06)
        self.smokes.append(smoke)

    def announce_bot_power(self, bot_name: str, detail: str):
        trait = BOT_TRAITS.get(bot_name, {})
        self.bot_power_message = f"{bot_name}: {trait.get('ability', 'Power')} - {detail}"
        self.bot_power_message_timer = 3.6
        self.stats["bot_unique_powers"] = self.stats.get("bot_unique_powers", 0) + 1

    def prime_bot_synergy(self, bot_name: str, target: Entity):
        self.bot_power_recent[bot_name] = self.elapsed
        for key, spec in BOT_SYNERGIES.items():
            pair = spec["pair"]
            if bot_name not in pair:
                continue
            other = pair[0] if pair[1] == bot_name else pair[1]
            if self.elapsed - float(self.bot_power_recent.get(other, -999.0)) > BOT_SYNERGY_WINDOW:
                continue
            if float(self.bot_synergy_cooldowns.get(key, 0.0)) > 0.0:
                continue
            self.trigger_bot_synergy(key, bot_name, other, target)
            self.bot_synergy_cooldowns[key] = float(spec.get("cooldown", 8.0))
            break

    def trigger_bot_synergy(self, key: str, bot_name: str, other_name: str, target: Entity):
        spec = BOT_SYNERGIES.get(key, {})
        label = spec.get("label", key.replace("_", " ").title())
        color = spec.get("color", (0.8, 1.0, 1.0, 0.48))
        self.stats["bot_synergies"] = self.stats.get("bot_synergies", 0) + 1
        self.bot_power_message = f"Bot Synergy: {label}"
        self.bot_power_message_timer = 4.8
        self.run_message = f"{label.upper()} ONLINE"
        self.run_message_timer = 3.5
        self.add_score(18, f"BOT SYNERGY: {label} +18")
        center = Vec3(target.pos) if target is not None else Vec3(0, 0, 1.0)
        self.add_impact_burst(center, color, 1.15, 1.25, 1.8)

        if key == "orbit_killbox":
            lane = pos_angle(center)
            hits = 0
            for enemy in list(self.enemies):
                if enemy.hp <= 0:
                    continue
                lane_gap = abs(math.atan2(math.sin(pos_angle(enemy.pos) - lane), math.cos(pos_angle(enemy.pos) - lane)))
                if lane_gap < 0.095 or distance(enemy.pos, center) < 4.6:
                    self.apply_enemy_damage(enemy, 0.135, "core", center)
                    enemy.extra["slow_until"] = max(float(enemy.extra.get("slow_until", 0.0)), self.elapsed + 1.3)
                    enemy.extra["vulnerable_until"] = max(float(enemy.extra.get("vulnerable_until", 0.0)), self.elapsed + 1.8)
                    self.add_beam(self.visual_point(center, 0.88), self.visual_point(enemy.pos, 0.58), (0.78, 1.0, 1.0, 0.38), 0.16, 1.2)
                    hits += 1
                    if hits >= 8:
                        break
            self.stats["orbit_killboxes"] = self.stats.get("orbit_killboxes", 0) + 1
            self.stats["bot_overdrive_hits"] = self.stats.get("bot_overdrive_hits", 0) + hits
        elif key == "grove_pack":
            rooted = 0
            for enemy in self.nearby_enemies(center, 5.8, limit=9):
                enemy.extra["slow_until"] = max(float(enemy.extra.get("slow_until", 0.0)), self.elapsed + 2.8)
                enemy.extra["panic_until"] = max(float(enemy.extra.get("panic_until", 0.0)), self.elapsed + 1.8)
                rooted += 1
            for animal in self.wildlife:
                if distance(animal.pos, center) < 12.0:
                    animal.extra["pack_boost_until"] = max(float(animal.extra.get("pack_boost_until", 0.0)), self.elapsed + 7.0)
            for plant in self.forest_plants[:]:
                if plant.state != "regrowing" and distance(plant.pos, center) < 13.5:
                    plant.hp = min(plant.max_hp, plant.hp + 0.030)
            self.stats["grove_pack_triggers"] = self.stats.get("grove_pack_triggers", 0) + 1
            self.stats["bot_root_binds"] = self.stats.get("bot_root_binds", 0) + rooted
        elif key == "dream_uplink":
            marked = 0
            squad = target.extra.get("squad") if target else None
            for enemy in self.enemies:
                if enemy.hp <= 0:
                    continue
                if (squad is not None and enemy.extra.get("squad") == squad) or distance(enemy.pos, center) < 5.2:
                    enemy.extra["marked_until"] = max(float(enemy.extra.get("marked_until", 0.0)), self.elapsed + 7.2)
                    enemy.extra["jammed_until"] = max(float(enemy.extra.get("jammed_until", 0.0)), self.elapsed + 4.8)
                    if enemy.extra.get("variant") != "enemy_phantom":
                        enemy.extra["confused"] = max(float(enemy.extra.get("confused", 0.0)), 2.5)
                    marked += 1
            self.stats["dream_uplinks"] = self.stats.get("dream_uplinks", 0) + 1
            self.stats["bot_marks"] = self.stats.get("bot_marks", 0) + marked
        elif key == "sun_prism":
            warded = 0
            for art in self.artifacts:
                if art.hp > 0:
                    art.extra["mirror_ward_until"] = max(float(art.extra.get("mirror_ward_until", 0.0)), self.elapsed + 5.8)
                    art.hp = min(art.max_hp, art.hp + 0.018)
                    warded += 1
            linked = 0
            for p in self.pyramids:
                if linked >= 7:
                    break
                p.extra["ember_link_until"] = max(float(p.extra.get("ember_link_until", 0.0)), self.elapsed + 6.8)
                p.cooldown = min(p.cooldown, 0.04)
                self.add_beam(self.visual_point(center, 0.82), self.visual_point(p.pos, 0.78), (1.0, 0.84, 0.26, 0.22), 0.16, 0.9)
                linked += 1
            self.stats["sun_prisms"] = self.stats.get("sun_prisms", 0) + 1
            self.stats["mirror_prism_wards"] = self.stats.get("mirror_prism_wards", 0) + warded
            self.stats["ember_pyramid_links"] = self.stats.get("ember_pyramid_links", 0) + linked

    def nearby_enemies(self, pos: Vec3, radius: float, *, exclude: Optional[Entity] = None, limit: Optional[int] = None) -> list[Entity]:
        found = []
        for enemy in self.enemies:
            if enemy is exclude or enemy.hp <= 0:
                continue
            d = distance(pos, enemy.pos)
            if d <= radius:
                found.append((d, enemy))
        found.sort(key=lambda item: item[0])
        enemies = [enemy for _d, enemy in found]
        return enemies if limit is None else enemies[:limit]

    def primary_bot_target_score(self, bot_name: str, enemy: Entity, dist: float) -> float:
        trait = BOT_TRAITS.get(bot_name, {})
        variant = enemy.extra.get("variant", enemy.kind)
        score = dist
        if variant in trait.get("strong_vs", ()): 
            score -= 2.2
        if variant in trait.get("weak_vs", ()): 
            score += 1.45
        if enemy.extra.get("veteran"):
            score -= 0.80
        if enemy.extra.get("marked_until", 0.0) > self.elapsed:
            score += 0.55
        if bot_name == "IO" and pos_radius(enemy.pos) < RINGS["FOREST"]["inner"]:
            score -= 1.65
        return score

    def nearest_enemy_for_bot(self, bot: Entity, max_dist: float) -> Optional[Entity]:
        bot_name = bot.extra.get("name", "")
        best = None
        best_score = 999.0
        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue
            d = distance(bot.pos, enemy.pos)
            if d > max_dist:
                continue
            score = self.primary_bot_target_score(bot_name, enemy, d)
            if score < best_score:
                best = enemy
                best_score = score
        return best

    def primary_bot_damage_multiplier(self, bot_name: str, enemy: Entity) -> float:
        trait = BOT_TRAITS.get(bot_name, {})
        variant = enemy.extra.get("variant", enemy.kind)
        mult = 1.0
        if variant in trait.get("strong_vs", ()): 
            mult *= 1.42
            self.stats["primary_bot_matchups"] = self.stats.get("primary_bot_matchups", 0) + 1
        if variant in trait.get("weak_vs", ()): 
            mult *= 0.62
        if enemy.extra.get("marked_until", 0.0) > self.elapsed:
            mult *= 1.18
        if enemy.extra.get("vulnerable_until", 0.0) > self.elapsed:
            mult *= 1.22
        if enemy.extra.get("prism_shredded_until", 0.0) > self.elapsed:
            mult *= 1.16
        return mult

    def fire_primary_bot_ability(self, bot: Entity, target: Entity, dt: float):
        name = bot.extra.get("name", "")
        trait = BOT_TRAITS.get(name, BOT_TRAITS.get("IO", {}))
        color = BOT_COLORS.get(name, (0.8, 0.9, 1.0, 1.0))
        effect = trait.get("effect", "blast")
        core_lvl = self.upgrade_level("core")
        overdrive = self.has_buff("bot_overdrive") or float(bot.extra.get("overdrive_until", 0.0)) > self.elapsed
        dmg = float(trait.get("damage", 0.08)) * (1.0 + core_lvl * 0.07) * self.primary_bot_damage_multiplier(name, target)
        if overdrive:
            dmg *= 1.34
            self.stats["bot_overdrive_hits"] = self.stats.get("bot_overdrive_hits", 0) + 1
        self.apply_enemy_damage(target, dmg, "core", bot.pos)
        self.stats["bot_blasts"] += 1
        self.stats["primary_bot_abilities"] = self.stats.get("primary_bot_abilities", 0) + 1
        beam_alpha = 0.95 if effect in {"intercept", "rail", "lance"} else 0.66
        self.add_beam(self.visual_point(bot.pos, 0.55), self.visual_point(target.pos, 0.48), (color[0], color[1], color[2], beam_alpha), 0.26 if name == "IO" else 0.19, 1.45)

        if effect == "intercept":
            # IO: Orbit Chain. Fast sentry hits jump through nearby light enemies.
            target.extra["slow_until"] = max(float(target.extra.get("slow_until", 0.0)), self.elapsed + 0.75)
            self.stats["io_intercepts"] = self.stats.get("io_intercepts", 0) + 1
            self.add_impact_burst(target.pos, (0.70, 1.0, 1.0, 0.28), 0.42, 0.50, 0.8)
            previous = target
            for chained in self.nearby_enemies(target.pos, 3.7, exclude=target, limit=3):
                chain_dmg = dmg * (0.36 if chained.extra.get("variant") not in {"enemy_scout", "enemy_phantom"} else 0.52)
                self.apply_enemy_damage(chained, chain_dmg, "core", bot.pos)
                chained.extra["slow_until"] = max(float(chained.extra.get("slow_until", 0.0)), self.elapsed + 0.55)
                self.add_beam(self.visual_point(previous.pos, 0.50), self.visual_point(chained.pos, 0.46), (0.72, 1.0, 1.0, 0.42), 0.15, 0.85)
                previous = chained
                self.stats["io_chain_hits"] = self.stats.get("io_chain_hits", 0) + 1
            self.announce_bot_power("IO", "chain intercept")
        elif effect == "root":
            # Vanta: Root Grove. Locks a small cluster and repairs Forest supply.
            root_targets = [target] + self.nearby_enemies(target.pos, 2.9, exclude=target, limit=3)
            for rooted in root_targets:
                rooted.extra["slow_until"] = max(float(rooted.extra.get("slow_until", 0.0)), self.elapsed + 3.3)
                rooted.extra["vulnerable_until"] = max(float(rooted.extra.get("vulnerable_until", 0.0)), self.elapsed + 2.3)
                self.add_beam(self.visual_point(bot.pos, 0.35), self.visual_point(rooted.pos, 0.18), (0.14, 1.0, 0.30, 0.34), 0.16, 1.7)
                self.stats["bot_root_binds"] = self.stats.get("bot_root_binds", 0) + 1
            healed = 0
            for plant in sorted([p for p in self.forest_plants if p.state != "regrowing"], key=lambda p: distance(p.pos, bot.pos))[:4]:
                plant.hp = min(plant.max_hp, plant.hp + 0.055)
                plant.extra["vanta_grove_until"] = max(float(plant.extra.get("vanta_grove_until", 0.0)), self.elapsed + 5.5)
                healed += 1
            self.stats["vanta_root_groves"] = self.stats.get("vanta_root_groves", 0) + 1
            self.add_impact_burst(target.pos, (0.12, 1.0, 0.30, 0.30), 0.70, 0.74, 1.05)
            self.announce_bot_power("Vanta", f"rooted {len(root_targets)} / healed {healed}")
        elif effect == "pounce":
            # Nyx: Pack Howl. A pounce that makes nearby wildlife surge and scares heavy squads.
            bot.pos += flat_direction(bot.pos, target.pos) * min(0.32, distance(bot.pos, target.pos) * 0.08)
            target.extra["panic_until"] = max(float(target.extra.get("panic_until", 0.0)), self.elapsed + 1.7)
            for enemy in self.nearby_enemies(target.pos, 3.2, exclude=target, limit=4):
                if enemy.extra.get("variant") in {"enemy_brute", "enemy_carrier", "enemy_commander"}:
                    enemy.extra["panic_until"] = max(float(enemy.extra.get("panic_until", 0.0)), self.elapsed + 2.0)
                enemy.extra["slow_until"] = max(float(enemy.extra.get("slow_until", 0.0)), self.elapsed + 0.6)
            for animal in self.wildlife:
                if distance(animal.pos, target.pos) < 8.8 or distance(animal.pos, bot.pos) < 7.5:
                    animal.extra["pack_boost_until"] = max(float(animal.extra.get("pack_boost_until", 0.0)), self.elapsed + 6.0)
            self.stats["nyx_pack_howls"] = self.stats.get("nyx_pack_howls", 0) + 1
            self.add_impact_burst(target.pos, (0.86, 0.58, 1.0, 0.34), 0.62, 0.70, 0.88)
            self.announce_bot_power("Nyx", "pack howl")
        elif effect == "daze":
            # Solace: Dream Spores. Disrupts abilities in a small cloud.
            dazed = 0
            for enemy in [target] + self.nearby_enemies(target.pos, 3.3, exclude=target, limit=5):
                if enemy.extra.get("variant") != "enemy_phantom":
                    enemy.extra["confused"] = max(float(enemy.extra.get("confused", 0.0)), 3.1)
                    enemy.extra["jammed_until"] = max(float(enemy.extra.get("jammed_until", 0.0)), self.elapsed + 3.4)
                else:
                    enemy.extra["slow_until"] = max(float(enemy.extra.get("slow_until", 0.0)), self.elapsed + 1.2)
                    enemy.extra["jammed_until"] = max(float(enemy.extra.get("jammed_until", 0.0)), self.elapsed + 1.4)
                dazed += 1
            self.stats["bot_spore_dazes"] = self.stats.get("bot_spore_dazes", 0) + 1
            self.stats["solace_spore_novas"] = self.stats.get("solace_spore_novas", 0) + 1
            self.add_impact_burst(target.pos, (1.0, 0.22, 0.92, 0.30), 0.74, 0.86, 1.08)
            self.announce_bot_power("Solace", f"dream spored {dazed}")
        elif effect == "lance":
            # Ember: Pyramid Overdrive. Links nearby pyramids and burns shield/siege armor.
            target.extra["prism_shredded_until"] = max(float(target.extra.get("prism_shredded_until", 0.0)), self.elapsed + 2.6)
            self.add_beam(self.visual_point(bot.pos, 0.72), self.visual_point(target.pos, 0.70), (1.0, 0.72, 0.12, 0.82), 0.30, 1.15)
            linked = 0
            target_angle = pos_angle(target.pos)
            def _angle_gap(ent: Entity) -> float:
                return abs(math.atan2(math.sin(pos_angle(ent.pos) - target_angle), math.cos(pos_angle(ent.pos) - target_angle)))
            for p in sorted(self.pyramids, key=_angle_gap)[:5]:
                p.extra["ember_link_until"] = max(float(p.extra.get("ember_link_until", 0.0)), self.elapsed + 5.4)
                p.cooldown = min(p.cooldown, 0.10)
                self.add_beam(self.visual_point(bot.pos, 0.62), self.visual_point(p.pos, 0.80), (1.0, 0.55, 0.08, 0.24), 0.18, 0.8)
                linked += 1
            if target.extra.get("variant") in {"enemy_shield", "enemy_siege"}:
                self.add_impact_burst(target.pos, (1.0, 0.58, 0.08, 0.34), 0.62, 0.68, 0.9)
            self.stats["ember_pyramid_links"] = self.stats.get("ember_pyramid_links", 0) + linked
            self.announce_bot_power("Ember", f"overdrove {linked} pyramids")
        elif effect == "reflect":
            # Mirror: Prism Ward. Shield assigned artifact, then spread to weak artifacts.
            warded = 0
            idx = int(bot.extra.get("artifact", 0))
            candidate_arts = []
            if 0 <= idx < len(self.artifacts):
                candidate_arts.append(self.artifacts[idx])
            candidate_arts += sorted([a for a in self.artifacts if a.hp > 0 and a not in candidate_arts], key=lambda a: a.hp)[:2]
            for art in candidate_arts:
                if art.hp > 0:
                    art.hp = min(art.max_hp, art.hp + 0.026 + core_lvl * 0.006)
                    art.extra["mirror_ward_until"] = max(float(art.extra.get("mirror_ward_until", 0.0)), self.elapsed + 5.0)
                    self.add_beam(self.visual_point(bot.pos, 0.46), self.visual_point(art.pos, 0.52), (0.74, 1.0, 1.0, 0.30), 0.16, 1.1)
                    warded += 1
            target.extra["prism_shredded_until"] = max(float(target.extra.get("prism_shredded_until", 0.0)), self.elapsed + 2.1)
            self.stats["bot_reflect_wards"] = self.stats.get("bot_reflect_wards", 0) + 1
            self.stats["mirror_prism_wards"] = self.stats.get("mirror_prism_wards", 0) + warded
            self.announce_bot_power("Mirror", f"warded {warded} artifacts")
        elif effect == "rail":
            # Sable: Killbox Rail. Pierce a lane and suppress the target squad.
            lane = pos_angle(target.pos)
            killbox_hits = 0
            squad_id = target.extra.get("squad")
            for other in self.enemies:
                if other is target or other.hp <= 0:
                    continue
                same_lane = abs(math.atan2(math.sin(pos_angle(other.pos) - lane), math.cos(pos_angle(other.pos) - lane))) < 0.070
                same_squad = squad_id is not None and other.extra.get("squad") == squad_id
                if (same_lane and distance(other.pos, target.pos) < 4.0) or same_squad:
                    self.apply_enemy_damage(other, dmg * (0.46 if same_squad else 0.34), "core", bot.pos)
                    other.extra["slow_until"] = max(float(other.extra.get("slow_until", 0.0)), self.elapsed + 0.75)
                    killbox_hits += 1
            target.extra["slow_until"] = max(float(target.extra.get("slow_until", 0.0)), self.elapsed + 1.0)
            self.stats["sable_killbox_hits"] = self.stats.get("sable_killbox_hits", 0) + killbox_hits + 1
            self.add_impact_burst(target.pos, (1.0, 0.12, 0.14, 0.30), 0.52, 0.72, 0.82)
            self.announce_bot_power("Sable", f"killbox hit {killbox_hits + 1}")
        elif effect == "mark":
            # Archivist: Data Uplink. Mark a full squad and jam special tools.
            squad_id = target.extra.get("squad")
            marked = 0
            for enemy in self.enemies:
                if enemy.hp <= 0:
                    continue
                if enemy is target or (squad_id is not None and enemy.extra.get("squad") == squad_id) or distance(enemy.pos, target.pos) < 2.8:
                    enemy.extra["marked_until"] = max(float(enemy.extra.get("marked_until", 0.0)), self.elapsed + 6.0)
                    enemy.extra["vulnerable_until"] = max(float(enemy.extra.get("vulnerable_until", 0.0)), self.elapsed + 4.0)
                    enemy.extra["jammed_until"] = max(float(enemy.extra.get("jammed_until", 0.0)), self.elapsed + 1.8)
                    marked += 1
            self.stats["bot_marks"] = self.stats.get("bot_marks", 0) + marked
            self.stats["archivist_uplinks"] = self.stats.get("archivist_uplinks", 0) + 1
            self.add_beam(self.visual_point(bot.pos, 0.90), self.visual_point(target.pos, 0.84), (0.55, 0.82, 1.0, 0.48), 0.16, 2.3)
            self.add_impact_burst(target.pos, (0.42, 0.70, 1.0, 0.26), 0.58, 0.80, 0.92)
            self.announce_bot_power("Archivist", f"uplink marked {marked}")

        bot.extra["ability_fx"] = 0.82 if overdrive else 0.65
        self.prime_bot_synergy(name, target)
        cooldown_mult = max(0.56 if overdrive else 0.72, 1.0 - core_lvl * 0.035 - (0.16 if overdrive else 0.0))
        bot.cooldown = float(trait.get("cooldown", 0.72)) * cooldown_mult

    def update_artifact_bots(self, dt: float):
        for i, art in enumerate(self.artifacts):
            if art.hp > 0:
                recently_hit = False
                for e in self.enemies:
                    if distance(e.pos, art.pos) < 1.65:
                        recently_hit = True
                        break
                if not recently_hit:
                    art.hp = min(art.max_hp, art.hp + dt * (0.018 + self.upgrade_level("core") * 0.004))
                alpha = 0.22 + art.hp * 0.72
                if art.extra.get("mirror_ward_until", 0.0) > self.elapsed:
                    art.node.setColor(0.70, 1.0, 1.0, min(1.0, alpha + 0.12))
                    if self.rng.random() < dt * 0.45:
                        self.add_impact_burst(art.pos, (0.70, 1.0, 1.0, 0.18), 0.28, 0.44, 0.55)
                else:
                    art.node.setColor(0.92, 0.96, 1.0, alpha)
            else:
                art.node.setColor(0.36, 0.08, 0.09, 0.25)
            self.update_node(art)

        for bot in self.bots:
            name = bot.extra.get("name", "")
            trait = BOT_TRAITS.get(name, BOT_TRAITS.get("IO", {}))
            color = BOT_COLORS.get(name, (0.8, 0.9, 1, 1))
            ability_fx = max(0.0, float(bot.extra.get("ability_fx", 0.0)) - dt)
            bot.extra["ability_fx"] = ability_fx
            if name == "IO":
                bot.angle += dt * 0.95 * float(trait.get("speed", 1.0))
                orbit = 5.75 + math.sin(self.elapsed * 1.3) * 0.08
                bot.pos = angle_to_pos(bot.angle, orbit, 0.82)
            else:
                idx = int(bot.extra.get("artifact", 0))
                if 0 <= idx < len(self.artifacts):
                    art = self.artifacts[idx]
                    bot.angle = art.angle + math.sin(self.elapsed * 0.7 + idx) * 0.012
                    guard_radius = 5.25 + 0.15 * math.sin(self.elapsed * 1.7 + idx)
                    bot.pos = angle_to_pos(bot.angle, guard_radius, 0.78)
                    if name == "Mirror" and art.hp > 0 and art.hp < art.max_hp:
                        art.hp = min(art.max_hp, art.hp + dt * 0.006)
                    if name == "Vanta" and self.forest_attack_timer > 0.0:
                        bot.extra["ability_fx"] = max(bot.extra.get("ability_fx", 0.0), 0.18)
                else:
                    bot.angle += dt * 0.10
            bot_overdrive = self.has_buff("bot_overdrive") or float(bot.extra.get("overdrive_until", 0.0)) > self.elapsed
            scan_range = float(trait.get("range", 5.2)) * (1.0 + self.upgrade_level("core") * 0.025 + (0.18 if bot_overdrive else 0.0))
            target = self.nearest_enemy_for_bot(bot, scan_range)
            bot.cooldown = max(0.0, bot.cooldown - dt)
            if bot.node:
                base_scale = 1.12 if name == "IO" else 1.0
                bot.node.setScale(base_scale * (1.0 + ability_fx * 0.18 + (0.08 if bot_overdrive else 0.0)))
                alpha_boost = 0.08 if bot_overdrive else 0.0
                bot.node.setColor(color[0], color[1], color[2], min(1.0, 0.88 + alpha_boost + 0.10 * math.sin(self.elapsed * 2.5 + bot.angle)))
            if target and bot.cooldown <= 0:
                self.fire_primary_bot_ability(bot, target, dt)
            elif target and ability_fx <= 0.02 and self.rng.random() < dt * 0.08:
                self.add_beam(self.visual_point(bot.pos, 0.45), self.visual_point(target.pos, 0.44), (color[0], color[1], color[2], 0.18), 0.08, 0.55)
            self.update_node(bot)

    def update_ecosystem(self, dt: float):
        self.forest_attack_timer = max(0.0, self.forest_attack_timer - dt)
        active_plants = sum(1 for p in self.forest_plants if p.state != "regrowing")
        self.forest_supply_safe = bool(active_plants >= 5 and self.forest_attack_timer <= 0.0)
        for plant in self.forest_plants:
            if plant.state == "regrowing":
                plant.timer -= dt * (3.5 if self.has_buff("forest_surge") else 1.0)
                plant.growth = 1.0 - clamp(plant.timer / 300.0, 0.0, 1.0)
                plant.node.setAlphaScale(0.16 + plant.growth * 0.62)
                plant.node.setScale((0.45 if plant.kind == "tree" else 0.33) * max(0.35, plant.growth))
                if plant.timer <= 0:
                    plant.state = "active"
                    plant.hp = plant.max_hp
                    plant.growth = 1.0
                    plant.node.setAlphaScale(1.0)
            elif plant.hp < plant.max_hp:
                plant.hp = min(plant.max_hp, plant.hp + dt * (0.04 if self.has_buff("forest_surge") else 0.01))
            self.update_node(plant)
        # Support packets pulse inward to show ecosystem resources feeding core.
        for p in self.packets:
            spec = RINGS[p.extra["ring"]]
            r = pos_radius(p.pos) - dt * (0.75 + 0.4 * math.sin(self.elapsed + p.angle))
            if r < spec["inner"]:
                r = spec["outer"]
            p.pos = angle_to_pos(p.angle, r, 0.74)
            self.update_node(p)

    def destroy_plant(self, plant: Entity):
        if plant.state == "regrowing":
            return
        plant.state = "regrowing"
        plant.timer = 300.0
        plant.hp = 0.0
        plant.growth = 0.0
        plant.node.setAlphaScale(0.16)
        self.forest_attack_timer = 12.0
        self.stats["forest_destroyed"] += 1

    def bush_growth_bonus(self) -> float:
        bushes = sum(1 for p in self.forest_plants if p.kind == "bush" and p.state != "regrowing")
        return 0.45 + bushes * 0.24

    def tree_strength_bonus(self) -> float:
        trees = sum(1 for p in self.forest_plants if p.kind == "tree" and p.state != "regrowing")
        return 0.55 + trees * 0.18

    def confused_fire(self, enemy: Entity):
        candidates: list[Entity] = []
        for group in [self.enemies, self.urban_troops, self.desert_troops, self.mushroom_troops, self.hills_caretakers, self.wildlife]:
            for ent in group:
                if ent is enemy or ent.hp <= 0:
                    continue
                if distance(enemy.pos, ent.pos) < 2.1:
                    candidates.append(ent)
        if not candidates:
            return
        target = self.rng.choice(candidates)
        self.apply_enemy_damage(target, 0.035, "confused", enemy.pos)
        self.add_beam(enemy.pos + Vec3(0, 0, 0.22), target.pos + Vec3(0, 0, 0.22), (1.0, 0.25, 0.55, 0.64), 0.12)

    def update_fx(self, dt: float):
        alive_beams = []
        for beam, ttl in self.beams:
            ttl -= dt
            if ttl <= 0:
                beam.removeNode()
            else:
                alive_beams.append((beam, ttl))
        self.beams = alive_beams
        alive_region_beams = []
        for beam, ttl in self.region_activity_beams:
            ttl -= dt
            if ttl <= 0:
                beam.removeNode()
            else:
                alive_region_beams.append((beam, ttl))
        self.region_activity_beams = alive_region_beams
        for smoke in list(self.smokes):
            smoke.timer -= dt
            scale = 1.0 + (5.0 - smoke.timer) * 0.32
            if smoke.node:
                smoke.node.setScale(scale)
                smoke.node.setAlphaScale(max(0.0, smoke.timer / 5.0) * 0.36)
            if smoke.timer <= 0:
                self.remove_entity(smoke, self.smokes)
        alive_space_beams = []
        for beam, ttl in self.space_beams:
            ttl -= dt
            if ttl <= 0:
                beam.removeNode()
            else:
                alive_space_beams.append((beam, ttl))
        self.space_beams = alive_space_beams
        for pulse in self.metro_spawn_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            burst = max(0.0, float(pulse.get("burst", 0.0)) - dt * 2.2)
            pulse["burst"] = burst
            wave = 0.5 + 0.5 * math.sin(self.elapsed * 2.6 + pulse.get("phase", 0.0))
            scale = 0.72 + wave * 0.58 + burst * 0.86
            node.setScale(scale)
            node.setAlphaScale(0.20 + wave * 0.46 + burst * 0.38)
        for pulse in self.logic_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            wave = 0.5 + 0.5 * math.sin(self.elapsed * 1.7 + pulse.get("phase", 0.0))
            node.setScale(0.92 + wave * 0.30)
            node.setAlphaScale(0.22 + wave * 0.30)
        for pulse in self.region_status_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            activity = self.region_pressure.get(pulse.get("region", ""), self.region_activity_level(pulse.get("region", "")))
            wave = 0.5 + 0.5 * math.sin(self.elapsed * (1.2 + activity * 2.4) + pulse.get("phase", 0.0))
            node.setScale(0.82 + activity * 0.70 + wave * 0.18)
            node.setAlphaScale(0.16 + activity * 0.55 + wave * 0.16)
        for pulse in self.battlefront_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            a_region, b_region = pulse.get("regions", ("", ""))
            pressure = max(self.region_pressure.get(a_region, 0.0), self.region_pressure.get(b_region, 0.0))
            wave = 0.5 + 0.5 * math.sin(self.elapsed * (1.8 + pressure * 2.8) + pulse.get("phase", 0.0))
            node.setScale(1.00 + pressure * 0.82 + wave * 0.20)
            node.setAlphaScale(0.14 + pressure * 0.62 + wave * 0.14)
        for pulse in self.command_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            region = pulse.get("region", "")
            command_name = {"URBAN": "urban_rally", "DESERT": "desert_overcharge", "MUSHROOM": "spore_bloom", "FOREST": "forest_surge", "FLAT": "core_repair"}.get(region, "")
            cooldown = self.command_cooldowns.get(command_name, 0.0)
            active = 1.0 if self.command_buffs.get(command_name, 0.0) > 0.0 else 0.0
            burst = max(0.0, float(pulse.get("burst", 0.0)) - dt * 1.9)
            pulse["burst"] = burst
            wave = 0.5 + 0.5 * math.sin(self.elapsed * 2.0 + pulse.get("phase", 0.0))
            ready = 0.35 if cooldown > 0 else 1.0
            node.setScale(0.82 + wave * 0.20 + active * 0.48 + burst * 0.72)
            node.setAlphaScale((0.18 + wave * 0.18 + active * 0.42 + burst * 0.42) * ready)
        for pulse in self.region_alert_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            region = pulse.get("region", "")
            pressure = self.region_pressure.get(region, 0.0)
            danger = 1.0 if region in {"FOREST", "FLAT"} and (self.forest_attack_timer > 0 or self.hub_integrity < 0.82) else 0.0
            wave = 0.5 + 0.5 * math.sin(self.elapsed * (2.0 + pressure * 2.2) + pulse.get("phase", 0.0))
            node.setScale(0.82 + pressure * 1.15 + danger * 0.30 + wave * 0.22)
            node.setAlphaScale(0.05 + pressure * 0.70 + danger * 0.22 + wave * 0.12)
        for pulse in self.attack_vector_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            src, dst = pulse.get("regions", ("", ""))
            pressure = max(self.region_pressure.get(src, 0.0), self.region_pressure.get(dst, 0.0))
            doctrine_boost = 0.18 if self.wave_phase == "assault" else 0.0
            wave = 0.5 + 0.5 * math.sin(self.elapsed * (1.5 + pressure * 2.6) + pulse.get("phase", 0.0))
            node.setScale(0.90 + pressure * 0.45 + wave * 0.12)
            node.setAlphaScale(0.08 + pressure * 0.48 + doctrine_boost + wave * 0.08)
            if pressure > 0.55:
                self.stats["attack_vectors"] = self.stats.get("attack_vectors", 0) + 1
        for pulse in self.defense_vector_pulses:
            node = pulse.get("node")
            if node is None or node.isEmpty():
                continue
            src, dst = pulse.get("regions", ("", ""))
            pressure = max(self.region_pressure.get(src, 0.0), self.region_pressure.get(dst, 0.0))
            # Commands briefly make the defense route flare so the player can
            # see where their helper order is taking effect.
            command_bonus = 0.0
            if src == "URBAN" and self.has_buff("urban_rally"):
                command_bonus = 0.38
            elif src == "DESERT" and self.has_buff("desert_overcharge"):
                command_bonus = 0.38
            elif src == "MUSHROOM" and self.has_buff("spore_bloom"):
                command_bonus = 0.38
            elif src == "FOREST" and self.has_buff("forest_surge"):
                command_bonus = 0.38
            elif src == "FLAT" and self.has_buff("core_repair"):
                command_bonus = 0.38
            wave = 0.5 + 0.5 * math.sin(self.elapsed * (1.3 + pressure * 2.0) + pulse.get("phase", 0.0))
            node.setScale(0.88 + pressure * 0.36 + command_bonus * 0.70 + wave * 0.10)
            node.setAlphaScale(0.06 + pressure * 0.34 + command_bonus + wave * 0.08)
        alive_bursts = []
        for burst in self.impact_bursts:
            node = burst.get("node")
            if node is None or node.isEmpty():
                continue
            ttl = float(burst.get("ttl", 0.0)) - dt
            start = max(0.001, float(burst.get("start", 0.45)))
            age = 1.0 - clamp(ttl / start, 0.0, 1.0)
            if ttl <= 0.0:
                node.removeNode()
                continue
            node.setScale(1.0 + age * 2.1)
            node.setAlphaScale(max(0.0, 1.0 - age) * float(burst.get("alpha", 0.55)))
            burst["ttl"] = ttl
            alive_bursts.append(burst)
        self.impact_bursts = alive_bursts

    def add_impact_burst(self, pos: Vec3, color, ttl: float = 0.42, size: float = 0.62, thickness: float = 1.0):
        while len(self.impact_bursts) >= MAX_IMPACT_BURSTS:
            old = self.impact_bursts.pop(0)
            node = old.get("node")
            if node is not None and not node.isEmpty():
                node.removeNode()
        center = self.visual_point(pos, 0.16)
        ring = add_circle_line(self.fx_root, "impact-burst", size, color, thickness, 0.0, 28)
        ring.setPos(center)
        ring.setLightOff(1)
        ring.setTransparency(TransparencyAttrib.MAlpha)
        self.impact_bursts.append({"node": ring, "ttl": ttl, "start": ttl, "alpha": color[3] if len(color) > 3 else 0.5})
        self.stats["impact_bursts"] = self.stats.get("impact_bursts", 0) + 1

    def add_beam(self, a: Vec3, b: Vec3, color, ttl: float = 0.18, thickness: float = 1.6):
        # Runtime FX budget: action stays busy, but beam nodes cannot grow
        # without bound during long battles or soak tests.
        while len(self.beams) >= MAX_WORLD_BEAMS:
            old_beam, _old_ttl = self.beams.pop(0)
            old_beam.removeNode()
            self.stats["beam_culls"] += 1
        av = Vec3(a.x, a.y, self.surface_z_at(a) + a.z)
        bv = Vec3(b.x, b.y, self.surface_z_at(b) + b.z)
        beam = add_line(self.fx_root, "beam", av, bv, color, thickness)
        self.beams.append((beam, ttl))

    def add_space_beam(self, a: Vec3, b: Vec3, color, ttl: float = 0.18, thickness: float = 1.2):
        while len(self.space_beams) >= MAX_SPACE_BEAMS:
            old_beam, _old_ttl = self.space_beams.pop(0)
            old_beam.removeNode()
            self.stats["space_beam_culls"] += 1
        beam = add_line(self.sky_fx_root, "space-beam", a, b, color, thickness)
        self.space_beams.append((beam, ttl))

    def flash_entity(self, ent: Entity, color):
        if ent.node:
            ent.node.setColor(*color)

    def remove_entity(self, ent: Entity, group: list[Entity]):
        if ent.node:
            ent.node.removeNode()
        try:
            group.remove(ent)
        except ValueError:
            pass

    def surface_z_at(self, pos: Vec3) -> float:
        ring = self.region_for_radius(pos_radius(pos))
        return RING_HEIGHTS.get(ring, 0.0)

    def visual_point(self, pos: Vec3, lift: float = 0.0) -> Vec3:
        return Vec3(pos.x, pos.y, self.surface_z_at(pos) + lift)

    def render_pos_for(self, ent: Entity) -> Vec3:
        # Simulation keeps local ring coordinates, while rendering lifts the
        # miniature to the active terrace surface plus the entity's own local offset.
        surface = self.surface_z_at(ent.pos)
        return Vec3(ent.pos.x, ent.pos.y, surface + ent.pos.z)

    def update_node(self, ent: Entity):
        if ent.node:
            ent.node.setPos(self.render_pos_for(ent))

    def ui_bar(self, value: float, max_value: float, width: int = 12) -> str:
        if max_value <= 0:
            ratio = 0.0
        else:
            ratio = clamp(value / max_value, 0.0, 1.0)
        filled = int(round(ratio * width))
        return "[" + "#" * filled + "." * (width - filled) + "]"

    def command_state_text(self, name: str) -> str:
        label, cost = COMMAND_UI[name]
        key = COMMAND_KEYS.get(name, "?")
        active = self.command_buffs.get(name, 0.0)
        cooldown = self.command_cooldowns.get(name, 0.0)
        if active > 0.0:
            status = f"ACTIVE {active:02.0f}s"
        elif cooldown > 0.0:
            status = f"COOL {cooldown:02.0f}s"
        elif self.command_energy >= cost:
            status = "READY"
        else:
            status = f"NEED {max(0.0, cost - self.command_energy):02.0f}"
        return f"{key} {label:<13} {status}"

    def command_state_short(self, name: str) -> str:
        label, cost = COMMAND_UI[name]
        key = COMMAND_KEYS.get(name, "?")
        active = self.command_buffs.get(name, 0.0)
        cooldown = self.command_cooldowns.get(name, 0.0)
        short = {
            "urban_rally": "URB",
            "desert_overcharge": "DES",
            "spore_bloom": "SPR",
            "forest_surge": "FOR",
            "core_repair": "COR",
            "bot_overdrive": "BOT",
        }.get(name, label[:3].upper())
        if active > 0.0:
            status = f"A{int(active):02d}"
        elif cooldown > 0.0:
            status = f"C{int(cooldown):02d}"
        elif self.command_energy >= cost:
            status = "RDY"
        else:
            status = f"-{int(max(0.0, cost - self.command_energy)):02d}"
        return f"{key}{short}:{status}"

    def command_status_row(self) -> str:
        names = ("urban_rally", "desert_overcharge", "spore_bloom", "forest_surge", "core_repair", "bot_overdrive")
        return "  ".join(self.command_state_short(name) for name in names)

    def pressure_chip(self, name: str) -> str:
        val = clamp(self.region_pressure.get(name, 0.0), 0.0, 1.0)
        bars = min(3, int(round(val * 3.0)))
        return f"{name[:3]}:{'!' * bars}{'.' * (3 - bars)}"

    def upgrade_summary(self) -> str:
        return " ".join(f"{name[0].upper()}{self.upgrade_level(name)}" for name in UPGRADE_ORDER)

    def cycle_ui_mode(self):
        visible_modes = ("clean", "compact", "tactical", "minimal", "hidden")
        idx = visible_modes.index(self.ui_mode) if self.ui_mode in visible_modes else 0
        self.ui_mode = visible_modes[(idx + 1) % len(visible_modes)]
        self.ui_flash = 1.2
        if self.ui_mode == "hidden":
            self.banner["text"] = "UI HIDDEN  //  press U to restore"
        else:
            self.banner["text"] = f"UI MODE  //  {self.ui_mode.upper()}"
        self.apply_ui_visibility()

    def toggle_debug_ui(self):
        self.ui_flash = 1.2
        self.ui_mode = "debug" if self.ui_mode != "debug" else "clean"
        self.banner["text"] = "DIAGNOSTICS ON" if self.ui_mode == "debug" else "PLAYER HUD"
        self.apply_ui_visibility()

    def apply_ui_visibility(self):
        if not hasattr(self, "ui_panels"):
            return
        if self.ui_mode == "hidden":
            for panel in self.ui_panels:
                panel.hide()
            self.help.hide()
            self.banner.show()
            return
        self.banner.show()
        if self.ui_mode == "minimal":
            self.hud_core.hide()
            self.hud_commands.hide()
            self.hud_regions.hide()
            self.hud_fx.hide()
            self.hud_wave.show()
            self.help.hide()
        elif self.ui_mode == "clean":
            self.hud_core.show()
            self.hud_wave.show()
            self.hud_commands.show()
            self.hud_regions.show()
            self.hud_fx.hide()
            self.help.hide()
        elif self.ui_mode == "compact":
            self.hud_core.show()
            self.hud_wave.show()
            self.hud_commands.show()
            self.hud_regions.show()
            self.hud_fx.hide()
            self.help.hide()
        elif self.ui_mode == "tactical":
            self.hud_core.show()
            self.hud_wave.show()
            self.hud_commands.show()
            self.hud_regions.show()
            self.hud_fx.hide()
            self.help.show()
        elif self.ui_mode == "debug":
            for panel in self.ui_panels:
                panel.show()
            self.help.show()
        else:
            self.ui_mode = "clean"
            self.apply_ui_visibility()
            return
        if hasattr(self, "hud_activity"):
            if self.activity_panel_visible and self.selected_region and self.ui_mode not in {"hidden", "minimal"}:
                self.hud_activity.show()
            else:
                self.hud_activity.hide()

    def region_display_name(self, region: str) -> str:
        if region == "FLAT":
            return "FLAT / ARTIFACTS"
        return region

    def short_activity_text(self, value: str, limit: int = 34) -> str:
        value = str(value).replace("enemy_", "").replace("_", " ").strip()
        return value if len(value) <= limit else value[:max(0, limit - 1)] + "…"

    def log_region_event(self, region: str, actor: str, action: str, target: str = "", result: str = "info"):
        region = region if region in self.region_activity_log else self.region_for_radius(pos_radius(Vec3(0, 0, 0)))
        rec = self.region_records.setdefault(region, {"defender_wins": 0, "enemy_wins": 0, "enemy_losses": 0, "structure_losses": 0, "last_state": "SECURE"})
        if result == "defense_win":
            rec["defender_wins"] = int(rec.get("defender_wins", 0)) + 1
            rec["enemy_losses"] = int(rec.get("enemy_losses", 0)) + 1
            self.stats["activity_defender_wins"] = self.stats.get("activity_defender_wins", 0) + 1
        elif result == "enemy_win":
            rec["enemy_wins"] = int(rec.get("enemy_wins", 0)) + 1
            rec["structure_losses"] = int(rec.get("structure_losses", 0)) + 1
            self.stats["activity_enemy_wins"] = self.stats.get("activity_enemy_wins", 0) + 1
            self.stats["activity_structure_losses"] = self.stats.get("activity_structure_losses", 0) + 1
        minute = int(self.elapsed // 60)
        second = int(self.elapsed % 60)
        target = self.short_activity_text(target, 30)
        line = f"{minute:02d}:{second:02d} {actor} {action}" + (f" {target}" if target else "")
        entries = self.region_activity_log.setdefault(region, [])
        if not entries or entries[-1] != line:
            entries.append(line)
            del entries[:-ACTIVITY_LOG_LIMIT]
            self.stats["activity_log_events"] = self.stats.get("activity_log_events", 0) + 1

    def region_control_state(self, region: str) -> tuple[str, float, str]:
        pressure = clamp(self.region_pressure.get(region, 0.0), 0.0, 1.0)
        if region == "CORE":
            integrity = self.hub_integrity
            pressure = max(pressure, 1.0 - integrity)
            detail = f"Hub {integrity*100:03.0f}%"
        elif region == "FLAT":
            active = sum(1 for a in self.artifacts if a.hp > 0)
            pressure = max(pressure, 1.0 - active / max(1, len(self.artifacts)))
            detail = f"Artifacts {active}/8"
        elif region == "FOREST":
            active = sum(1 for p in self.forest_plants if p.state != "regrowing")
            total = max(1, len(self.forest_plants))
            pressure = max(pressure, 1.0 - active / total)
            detail = f"Supply {active}/{total}"
        elif region == "WATER":
            vessels = sum(1 for e in self.enemies if e.state in {"building_vessel", "crossing_water"})
            pressure = max(pressure, clamp(vessels / 8.0, 0.0, 1.0))
            detail = f"Vessels {vessels}"
        elif region == "URBAN":
            detail = f"Army {len(self.urban_troops)}"
        elif region == "DESERT":
            detail = f"Pyramids {len(self.pyramids)}"
        elif region == "MUSHROOM":
            active = sum(1 for m in self.mushrooms if m.state == "active")
            detail = f"Spores {active}/{len(self.mushrooms)}"
        elif region == "HILLS":
            detail = f"Wildlife {len(self.wildlife)}"
        elif region == "METROPOLIS":
            pressure = max(pressure, clamp(len(self.enemies) / 120.0, 0.0, 1.0))
            detail = f"Enemy {len(self.enemies)}"
        else:
            detail = "Stable"
        if pressure >= 0.78:
            state = "OVERTAKEN RISK"
        elif pressure >= 0.44:
            state = "CONTESTED"
        else:
            state = "SECURE"
        return state, pressure, detail

    def update_region_activity_status(self, dt: float):
        self.activity_status_timer -= dt
        if self.activity_status_timer > 0.0:
            return
        self.activity_status_timer = 1.25
        for region in REGION_ACTIVITY_ORDER:
            state, pressure, detail = self.region_control_state(region)
            rec = self.region_records.setdefault(region, {"defender_wins": 0, "enemy_wins": 0, "enemy_losses": 0, "structure_losses": 0, "last_state": "SECURE"})
            old = rec.get("last_state", "SECURE")
            if state != old:
                rec["last_state"] = state
                self.stats["activity_status_changes"] = self.stats.get("activity_status_changes", 0) + 1
                if state != "SECURE":
                    self.log_region_event(region, "Region", "status", f"{state} {detail}", "info")

    def update_activity_panel(self):
        if not hasattr(self, "hud_activity"):
            return
        region = self.selected_region if self.selected_region in self.region_activity_log else ""
        if not region or not self.activity_panel_visible or self.ui_mode in {"hidden", "minimal"}:
            self.hud_activity.hide()
            return
        state, pressure, detail = self.region_control_state(region)
        rec = self.region_records.get(region, {})
        purpose = RINGS.get(region, {}).get("purpose", "STATUS")
        entries = self.region_activity_log.get(region, [])[-3:]
        if not entries:
            entries = ["No major events yet", "Click orders or survive pressure"]
        pressure_bar = self.ui_bar(pressure, 1.0, 7)
        # Pass 46: compact, docked player-facing log. Keep it useful without
        # covering the center of the battlefield or duplicating the main HUD.
        lines = [
            f"{self.region_display_name(region)}  |  {state}",
            f"{purpose} {pressure_bar}",
            f"D{int(rec.get('defender_wins', 0))}  E{int(rec.get('enemy_wins', 0))}  Loss {int(rec.get('enemy_losses', 0))}/{int(rec.get('structure_losses', 0))}",
        ]
        lines.extend(f"• {self.short_activity_text(e, 31)}" for e in entries[-3:])
        self.hud_activity["text"] = "\n".join(lines)
        if state == "OVERTAKEN RISK":
            self.hud_activity["frameColor"] = (0.18, 0.00, 0.02, 0.48)
            self.hud_activity["text_fg"] = (1.0, 0.76, 0.70, 1.0)
        elif state == "CONTESTED":
            self.hud_activity["frameColor"] = (0.12, 0.06, 0.00, 0.46)
            self.hud_activity["text_fg"] = (1.0, 0.90, 0.64, 1.0)
        else:
            self.hud_activity["frameColor"] = (0.00, 0.015, 0.025, 0.42)
            self.hud_activity["text_fg"] = (0.82, 0.94, 1.0, 0.96)
        self.hud_activity.show()

    def update_hud(self):
        active_artifacts = sum(1 for a in self.artifacts if a.hp > 0)
        active_plants = sum(1 for p in self.forest_plants if p.state != "regrowing")
        trees = sum(1 for p in self.forest_plants if p.kind == "tree" and p.state != "regrowing")
        bushes = sum(1 for p in self.forest_plants if p.kind == "bush" and p.state != "regrowing")
        vessels_building = sum(1 for e in self.enemies if e.state == "building_vessel")
        confused = sum(1 for e in self.enemies if e.extra.get("confused", 0) > 0)
        climbing = sum(1 for e in self.enemies if e.extra.get("climbing", 0.0) > 0.0)
        enemy_counts = {name: sum(1 for e in self.enemies if e.extra.get("variant") == name) for name in ENEMY_VARIANTS}
        enemy_classes = " ".join(f"{name.split('_')[-1][0].upper()}{count}" for name, count in enemy_counts.items() if count)
        if not enemy_classes:
            enemy_classes = "none"
        avg_growth = sum(w.growth for w in self.wildlife) / max(1, len(self.wildlife))
        objective = WAVE_OBJECTIVES.get(self.current_doctrine, "protect the hub")
        if self.bot_power_message_timer > 0:
            player_adapt_line = self.bot_power_message
        else:
            player_adapt_line = self.adaptation_message if self.adaptation_message_timer > 0 else "Metropolis is adapting"
        veteran_count = sum(1 for e in self.enemies if e.extra.get("veteran"))
        adapt_classes = "/".join(k.split("_")[-1][:4].upper() for k in self.adaptive_bias) if self.adaptive_bias else "none"
        phase_label = "RECOVERY" if self.wave_phase == "recovery" else "ASSAULT"
        phase_total = WAVE_RECOVERY_DURATION if self.wave_phase == "recovery" else WAVE_ASSAULT_DURATION
        phase_left = max(0.0, phase_total - self.wave_phase_time)
        order = "none" if self.order_target is None else f"{self.last_region} {self.order_target.x:.1f},{self.order_target.y:.1f}"
        ready_count = sum(1 for name, cd in self.command_cooldowns.items() if cd <= 0.0 and self.command_energy >= COMMAND_UI[name][1])
        pressure_regions = ("METROPOLIS", "URBAN", "WATER", "DESERT", "MUSHROOM", "HILLS", "FOREST", "FLAT")
        pressure_line = " ".join(self.pressure_chip(name) for name in pressure_regions)
        hot_region = max(((name, self.region_pressure.get(name, 0.0)) for name in pressure_regions), key=lambda item: item[1])

        core_line = (
            f"CORE {self.ui_bar(self.hub_integrity, 1.0, 10)} {self.hub_integrity*100:04.0f}%  "
            f"ART {active_artifacts}/8  R{self.core_rank}"
        )
        score_line = f"SCORE {self.score:06d}  BEST {self.best_score:06d}  COMBO x{self.combo:0.1f}"
        wave_line = f"W{self.wave_index} {phase_label} {phase_left:04.1f}s  {self.current_doctrine.upper()}"
        command_row = self.command_status_row()
        active_bot_fx = sum(1 for b in self.bots if float(b.extra.get("ability_fx", 0.0)) > 0.0)
        active_synergy = sum(1 for cd in self.bot_synergy_cooldowns.values() if cd > 0.0)
        bot_mode = "OVERDRIVE" if self.has_buff("bot_overdrive") else ("SYNERGY" if active_synergy else "READY")
        threat_line = f"THREAT {hot_region[0][:4]} {hot_region[1]:0.2f}  ENEMY {len(self.enemies)}/120  VET {veteran_count}  BOTS {bot_mode} {active_bot_fx}/8"

        # Stable 16:9 corner-HUD sizing. Keep the center of the battlefield open.
        self.hud_core["text_scale"] = 0.0215 if self.ui_mode in {"clean", "compact"} else 0.0225
        self.hud_wave["text_scale"] = 0.0235 if self.ui_mode == "clean" else 0.025
        self.hud_commands["text_scale"] = 0.0195 if self.ui_mode == "clean" else 0.0205
        self.hud_regions["text_scale"] = 0.0185 if self.ui_mode in {"clean", "compact"} else 0.0195
        self.hud_activity["text_scale"] = 0.0148 if self.ui_mode in {"clean", "compact"} else 0.0155
        self.hud_wave["frameSize"] = (-0.610, 0.610, -0.100, 0.036)
        self.hud_wave.setPos(0.0, 0, 0.955)

        if self.ui_mode == "minimal":
            self.hud_wave["text_scale"] = 0.029
            self.hud_wave["frameSize"] = (-0.820, 0.820, -0.084, 0.034)
            self.hud_wave.setPos(0.0, 0, 0.958)
            self.hud_wave["text"] = f"{core_line}  //  {wave_line}\n{score_line}  //  CMD {self.command_energy:03.0f}/{COMMAND_ENERGY_MAX:.0f}  READY {ready_count}/{len(COMMAND_UI)}"
        elif self.ui_mode == "clean":
            self.hud_core["text"] = f"{core_line}\n{score_line}\nUPG {self.upgrade_summary()}"
            self.hud_wave["text"] = f"{wave_line}\n{objective}\n{player_adapt_line if self.adaptation_message_timer > 0 else 'Hold the line'}"
            self.hud_commands["text"] = (
                f"CMD {self.ui_bar(self.command_energy, COMMAND_ENERGY_MAX, 10)} {self.command_energy:03.0f}/{COMMAND_ENERGY_MAX:.0f}  READY {ready_count}/{len(COMMAND_UI)}\n"
                f"{command_row}\n"
                f"{threat_line}"
            )
        elif self.ui_mode == "compact":
            self.hud_core["text"] = f"{core_line}\n{score_line}\nUPG {self.upgrade_summary()}  UI COMPACT"
            self.hud_wave["text"] = f"{wave_line}\nOBJ: {objective}\n{player_adapt_line}"
            self.hud_commands["text"] = (
                f"CMD {self.ui_bar(self.command_energy, COMMAND_ENERGY_MAX, 10)} {self.command_energy:03.0f}/{COMMAND_ENERGY_MAX:.0f}\n"
                f"{command_row}\n"
                f"{threat_line}  COUNTER {adapt_classes}"
            )
        elif self.ui_mode == "tactical":
            self.hud_core["text"] = (
                f"CORE DEFENSE\n"
                f"{core_line}\n"
                f"Bots {len(self.bots)} role defenders  IO orbit sentry  Gleebs {'ON' if self.gleebs_enabled and self.gleebs_texture_loaded else 'OFF'}\n"
                f"{score_line}\n"
                f"UPGRADES {self.upgrade_summary()}"
            )
            self.hud_wave["text"] = f"{wave_line}\nOBJ: {objective}\n{player_adapt_line}\nRun {self.run_number}  Time {self.run_time:05.1f}s"
            self.hud_commands["text"] = (
                f"COMMANDS  Energy {self.ui_bar(self.command_energy, COMMAND_ENERGY_MAX, 10)} {self.command_energy:03.0f}/{COMMAND_ENERGY_MAX:.0f}\n"
                f"{self.command_state_text('urban_rally')}\n"
                f"{self.command_state_text('desert_overcharge')}\n"
                f"{self.command_state_text('spore_bloom')}\n"
                f"{self.command_state_text('forest_surge')}\n"
                f"{self.command_state_text('core_repair')}"
            )
        elif self.ui_mode == "debug":
            self.hud_core["text"] = (
                f"DIAGNOSTICS  {VERSION}\n"
                f"{core_line}\n"
                f"Bots {len(self.bots)} + IO sentry  Gleebs {'ON' if self.gleebs_enabled and self.gleebs_texture_loaded else 'missing/off'}\n"
                f"{score_line}\n"
                f"UPGRADES {self.upgrade_summary()}  UI DEBUG"
            )
            self.hud_wave["text"] = (
                f"{wave_line}\n"
                f"OBJ: {objective}\n"
                f"{player_adapt_line}\n"
                f"Run {self.run_number}  Time {self.run_time:05.1f}s  Adapt {adapt_classes}"
            )
            self.hud_commands["text"] = (
                f"COMMANDS  Energy {self.ui_bar(self.command_energy, COMMAND_ENERGY_MAX, 10)} {self.command_energy:03.0f}/{COMMAND_ENERGY_MAX:.0f}\n"
                f"{self.command_state_text('urban_rally')}\n"
                f"{self.command_state_text('desert_overcharge')}\n"
                f"{self.command_state_text('spore_bloom')}\n"
                f"{self.command_state_text('forest_surge')}\n"
                f"{self.command_state_text('core_repair')}"
            )

        core_danger = 1.0 - self.hub_integrity
        self.hud_core["frameColor"] = (0.08 + core_danger * 0.34, 0.00, 0.02, 0.30 + core_danger * 0.20)
        self.hud_wave["text_fg"] = (0.55, 1.0, 0.92, 1.0) if self.wave_phase == "recovery" else (1.0, 0.78, 0.34, 1.0)
        if self.command_flash > 0.0:
            self.hud_commands["frameColor"] = (0.04, 0.10, 0.12, 0.50)
        else:
            self.hud_commands["frameColor"] = (0.00, 0.02, 0.03, 0.34)

        if self.ui_mode in {"clean", "compact"}:
            self.hud_regions["text"] = (
                f"REGION PRESSURE  {pressure_line}\n"
                f"THREAT {hot_region[0][:4]} {hot_region[1]:0.2f}  ENEMY {len(self.enemies)}/120  VET {veteran_count}\n"
                f"SUPPLY F{active_plants}/{len(self.forest_plants)}  WILD {len(self.wildlife)} {avg_growth*100:02.0f}%  PYR {len(self.pyramids)}  TRAP {len(self.mushrooms)}"
            )
        else:
            self.hud_regions["text"] = (
                f"REGIONS  {pressure_line}\n"
                f"ENEMY  Metro {len(self.enemies)}/120  squads {self.stats.get('enemy_squads', 0)}  veterans {veteran_count}  counter {adapt_classes}\n"
                f"FRONT  Urban {len(self.urban_troops)}  Water vessels {vessels_building}  Desert {len(self.desert_troops)} / Pyramids {len(self.pyramids)}\n"
                f"CONTROL  Mushroom {len(self.mushroom_troops)} traps {len(self.mushrooms)} confused {confused}  climbing {climbing}\n"
                f"SUPPLY  Forest {active_plants}/{len(self.forest_plants)} T{trees} B{bushes} safe {self.forest_supply_safe}  Wildlife {len(self.wildlife)} grow {avg_growth*100:04.0f}%"
            )

        self.hud_fx["text"] = (
            f"DEBUG  beams {len(self.beams)}/{MAX_WORLD_BEAMS}  impacts {len(self.impact_bursts)}/{MAX_IMPACT_BURSTS}\n"
            f"space {len(self.space_beams)}/{MAX_SPACE_BEAMS}  culls {self.stats.get('beam_culls', 0)}/{self.stats.get('space_beam_culls', 0)}\n"
            f"peak {self.stats.get('peak_enemies', 0)}  regroup {self.stats.get('enemy_regroups', 0)}  vets {self.stats.get('enemy_veterans', 0)}  adapt {self.stats.get('enemy_adaptations', 0)}\n"
            f"classes {enemy_classes}  order {order}"
        )

        self.update_activity_panel()

        if self.ui_mode == "debug":
            self.banner["text"] = (
                f"DEBUG // {phase_label} WAVE {self.wave_index} // {objective} // "
                f"SCORE {self.score:06d} // CMD READY {ready_count}/{len(COMMAND_UI)} // F3 CLEAN"
            )
        else:
            self.banner["text"] = (
                f"{phase_label} WAVE {self.wave_index}  //  {objective}  //  "
                f"SCORE {self.score:06d}  //  READY {ready_count}/{len(COMMAND_UI)}"
            )

        # Corner HUD mode keeps the board center clear. The banner is only
        # shown for tactical/debug/minimal views or short UI flashes. Clean and
        # compact already show objective/score in the top HUD.
        if self.ui_mode in {"clean", "compact"} and self.ui_flash <= 0.0:
            self.banner.hide()
        elif self.ui_mode != "hidden":
            self.banner.show()
        self.apply_ui_visibility()

    def capture_screenshot(self, task):
        try:
            if OVERVIEW_SHOT:
                self.focus_overview_camera()
            elif ENEMY_FOCUS_SHOT:
                self.focus_enemy_camera()
            elif METROPOLIS_FOCUS:
                self.focus_metropolis_camera()
            path = Path(SCREENSHOT_PATH)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            self.win.saveScreenshot(str(path))
            print(f"screenshot={path}")
        except Exception as exc:
            print(f"screenshot_failed={exc}")
        return Task.done

    def auto_exit(self, task):
        print(
            "SELF_TEST_OK "
            f"version={VERSION} enemies={len(self.enemies)} squads={self.stats.get('enemy_squads', 0)} artifacts={len(self.artifacts)} "
            f"pyramids={len(self.pyramids)} mushrooms={len(self.mushrooms)} plants={len(self.forest_plants)} "
            f"wildlife={len(self.wildlife)} activity_units={len(self.region_activity_units)} peak_enemies={self.stats.get('peak_enemies', 0)} "
            f"beams={len(self.beams)}/{MAX_WORLD_BEAMS} space_beams={len(self.space_beams)}/{MAX_SPACE_BEAMS} "
            f"culls={self.stats.get('beam_culls', 0)}/{self.stats.get('space_beam_culls', 0)} impacts={self.stats.get('impact_bursts', 0)} wave={self.wave_index} phase={self.wave_phase} doctrine={self.current_doctrine.replace(' ', '_')} objective={WAVE_OBJECTIVES.get(self.current_doctrine, 'protect').replace(' ', '_')} energy={self.command_energy:.1f} commands={self.stats.get('command_uses', 0)} denied={self.stats.get('command_denied', 0)} cooldown_denied={self.stats.get('command_cooldown_denied', 0)} alerts={len(self.region_alert_pulses)} attack_vectors={len(self.attack_vector_pulses)} defense_vectors={len(self.defense_vector_pulses)} rewards={self.stats.get('command_energy_rewards', 0)} score={self.score} best={self.best_score} rank={self.core_rank} combo={self.combo:.2f} run_time={self.run_time:.1f} upgrades={self.stats.get('auto_upgrades', 0)} upgrade_levels={'-'.join(str(self.upgrade_level(n)) for n in UPGRADE_ORDER)} failures={self.stats.get('run_failures', 0)} gleebs_texture={int(self.gleebs_texture_loaded)} dirs_generated=0 world_scale={WORLD_EXPANSION_SCALE:.2f} gleebs_scale={GLEEBS_BACKDROP_SCALE:.1f} gleebs_z={GLEEBS_BACKDROP_Z:.1f} gleebs_distance={GLEEBS_BACKDROP_DISTANCE:.1f} metro_variants={self.stats.get('metro_variant_structures', 0)} ui_mode={self.ui_mode} enemy_memory={len(self.enemy_squad_memory)} veterans={self.stats.get('enemy_veterans', 0)} adaptations={self.stats.get('enemy_adaptations', 0)} shield_blocks={self.stats.get('enemy_shield_blocks', 0)} carriers={self.stats.get('enemy_carrier_deploys', 0)} harvests={self.stats.get('enemy_harvests', 0)} phantoms={self.stats.get('enemy_phantom_bypasses', 0)} primary_bot_abilities={self.stats.get('primary_bot_abilities', 0)} unique_powers={self.stats.get('bot_unique_powers', 0)} io_chains={self.stats.get('io_chain_hits', 0)} vanta_groves={self.stats.get('vanta_root_groves', 0)} nyx_howls={self.stats.get('nyx_pack_howls', 0)} solace_novas={self.stats.get('solace_spore_novas', 0)} ember_links={self.stats.get('ember_pyramid_links', 0)} mirror_wards={self.stats.get('mirror_prism_wards', 0)} sable_hits={self.stats.get('sable_killbox_hits', 0)} archivist_uplinks={self.stats.get('archivist_uplinks', 0)} bot_matchups={self.stats.get('primary_bot_matchups', 0)} io_intercepts={self.stats.get('io_intercepts', 0)} root_binds={self.stats.get('bot_root_binds', 0)} bot_marks={self.stats.get('bot_marks', 0)} bot_synergies={self.stats.get('bot_synergies', 0)} orbit_killboxes={self.stats.get('orbit_killboxes', 0)} grove_packs={self.stats.get('grove_pack_triggers', 0)} dream_uplinks={self.stats.get('dream_uplinks', 0)} sun_prisms={self.stats.get('sun_prisms', 0)} bot_overdrives={self.stats.get('bot_overdrive_commands', 0)} overdrive_hits={self.stats.get('bot_overdrive_hits', 0)} activity_logs={self.stats.get('activity_log_events', 0)} activity_clicks={self.stats.get('activity_region_clicks', 0)} activity_status={self.stats.get('activity_status_changes', 0)} activity_def_wins={self.stats.get('activity_defender_wins', 0)} activity_enemy_wins={self.stats.get('activity_enemy_wins', 0)} selected_region={self.selected_region or 'none'} activity_dock=top_left hud_layout=corner_safe adapt_bias={'-'.join(k.split('_')[-1] for k in self.adaptive_bias) if self.adaptive_bias else 'none'}"
        )
        self.userExit()
        return Task.done


def main():
    install_crash_hook()
    try:
        app = HoloVerseRTS()
        app.run()
    except SystemExit:
        raise
    except Exception as exc:
        write_crash_report(exc, "startup-main")
        raise


if __name__ == "__main__":
    main()
