NIGHT_DARK_ALPHA_MAX = 145  # lower = brighter nights

# --- Subtle holographic screen look (orange tint + slight contrast pulse) ---
HOLO_ENABLED = True
HOLO_TINT_COLOR = (255, 150, 60)
HOLO_TINT_ALPHA = 18
HOLO_CONTRAST_BASE = 1.04
HOLO_CONTRAST_PULSE = 0.015
HOLO_PULSE_SPEED = 0.35


import os, sys, math, random, traceback
import glob

# Ensure this folder is importable when loaded by an external launcher (embedded hub).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

# --- Crash logging -----------------------------------------------------------
def _write_crash_log(exc: BaseException) -> None:
    try:
        with open("crash_log.txt", "w", encoding="utf-8") as f:
            f.write("Destruction Derby Artillery - crash log\n\n")
            f.write("Python: " + sys.version + "\n\n")
            f.write("Traceback:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass

try:
    import pygame
    from pygame.math import Vector2
except Exception as e:
    _write_crash_log(e)
    raise

# -----------------------------------------------------------------------------
# Embedded weapon system (merged from py)
# This file is now standalone; no external py is required.
# -----------------------------------------------------------------------------

LASER_COLORS = [
    (255, 72, 72), (255, 170, 60), (255, 240, 90),
    (80, 255, 120), (72, 220, 255), (120, 120, 255),
    (255, 90, 220), (255, 255, 255),
]

# Boss-special placeholder. We bind it to a real weapon id after building the table.
BOSS_SPECIAL = "boss_nuke"
# Pool placeholder. Filled on import after weapon table is built.
SPECIAL_POOL = []

@dataclass(frozen=True)
class WeaponDef:
    wid: str
    name: str
    archetype: str
    cooldown: float
    damage: float
    speed: float
    spread_deg: float = 0.0
    pellets: int = 1
    ttl: float = 1.5
    radius: float = 3.0
    on_hit: Optional[Dict[str, float]] = None
    params: Optional[Dict[str, float]] = None

_WEAPONS: Dict[str, WeaponDef] = {}
_WEAPON_LIST: List[WeaponDef] = []


def _build_weapon_table() -> None:
    global _WEAPONS, _WEAPON_LIST
    if _WEAPONS:
        return

    bases = [
        ("mg",        "Autocannon",        0.10,  7.0,  820.0,  4.0,  1),
        ("burst",     "Burst Rifle",       0.22, 10.0,  900.0,  3.0,  1),
        ("shotgun",   "Shotgun",           0.55,  5.2,  760.0, 11.0,  7),
        ("rail",      "Railgun",           0.75, 34.0, 1500.0,  0.8,  1),
        ("rocket",    "Rocket",            0.95, 42.0,  520.0,  2.0,  1),
        ("homing",    "Homing Missile",    1.15, 36.0,  460.0,  3.0,  1),
        ("cluster",   "Cluster Rocket",    1.25, 28.0,  480.0,  2.5,  1),
        ("mine",      "Mine Dropper",      0.95, 38.0,    0.0,  0.0,  1),
        ("spike",     "Spike Trap",        0.80, 26.0,    0.0,  0.0,  1),
        ("flame",     "Flamethrower",      0.16,  6.2,  520.0,  9.0,  1),
        ("laser",     "Laser Beam",        0.55, 22.0,    0.0,  0.0,  1),
        ("lightning", "Arc Lightning",     0.85, 18.0,    0.0,  0.0,  1),
        ("emp",       "EMP Pulse",         1.25,  0.0,    0.0,  0.0,  1),
        ("grav",      "Gravity Pulse",     1.10, 10.0,    0.0,  0.0,  1),
        ("water",     "Hydro Cannon",      0.18,  4.0,  680.0,  6.0,  1),
        ("harpoon",   "Harpoon",           1.05, 30.0,  860.0,  1.8,  1),
    ]

    mods = [
        ("Standard",     1.00, 1.00, {}),
        ("Incendiary",   1.05, 1.05, {"ignite": 1.0}),
        ("Cryo",         0.95, 0.95, {"slow": 1.25, "slow_mult": 0.60}),
        ("Toxic",        0.95, 1.00, {"poison": 2.25, "poison_dps": 7.5}),
        ("EMP",          0.90, 1.10, {"stun": 0.85}),
        ("Shredder",     1.00, 1.10, {"armor_break": 26.0}),
        ("Overcharged",  1.15, 0.92, {"knock": 120.0}),
        ("Micro",        0.78, 1.20, {}),
        ("Heavy",        1.30, 0.88, {"knock": 95.0}),
        ("Plasma",       1.10, 0.98, {}),
        ("Storm",        1.05, 0.95, {"stun": 0.45}),
        ("Acid",         1.00, 1.00, {"poison": 1.80, "poison_dps": 9.0, "armor_break": 18.0}),
    ]

    weapon_defs: List[WeaponDef] = []
    rng = random.Random(1337)
    combos = [(b, m) for b in bases for m in mods]
    rng.shuffle(combos)

    for i in range(50):
        (arch, base_name, cd, dmg, spd, spread, pellets), (mname, dmg_mul, cd_mul, eff) = combos[i]
        wid = f"{arch}_{mname.lower()}_{i:02d}"
        name = f"{mname} {base_name}"
        on_hit = dict(eff) if eff else None

        ttl = 1.45
        radius = 3.0
        params: Dict[str, float] = {}

        if arch in ("rocket", "homing", "cluster"):
            ttl = 2.4
            radius = 6.0
        if arch == "rail":
            ttl = 1.2
            radius = 2.2
        if arch == "flame":
            ttl = 0.55
            radius = 3.0
        if arch in ("mine", "spike"):
            ttl = 10.0
            radius = 10.0 if arch == "mine" else 8.0
        if arch == "laser":
            ttl = 0.0
            radius = 0.0
            params = {"range": 980.0}
        if arch == "lightning":
            ttl = 0.0
            radius = 0.0
            params = {"range": 720.0, "chains": 3.0}
        if arch == "emp":
            ttl = 0.0
            radius = 0.0
            params = {"radius": 360.0}
        if arch == "grav":
            ttl = 0.0
            radius = 0.0
            params = {"radius": 300.0, "pull": 420.0}
        if arch == "harpoon":
            ttl = 1.8
            radius = 4.0
            params = {"pull": 260.0}

        spd2 = float(spd)
        if mname == "Micro":
            spd2 *= 1.05
        elif mname == "Heavy":
            spd2 *= 0.92

        weapon_defs.append(
            WeaponDef(
                wid=wid,
                name=name,
                archetype=arch,
                cooldown=max(0.06, float(cd) * float(cd_mul)),
                damage=max(0.0, float(dmg) * float(dmg_mul)),
                speed=float(spd2),
                spread_deg=float(spread),
                pellets=int(pellets),
                ttl=float(ttl),
                radius=float(radius),
                on_hit=on_hit,
                params=params or None,
            )
        )

    _WEAPON_LIST = weapon_defs
    _WEAPONS = {w.wid: w for w in weapon_defs}


def weapon_by_id(wid: str) -> WeaponDef:
    _build_weapon_table()
    return _WEAPONS.get(wid) or _WEAPON_LIST[0]


def random_special(is_boss: bool = False) -> str:
    _build_weapon_table()
    if is_boss:
        return str(BOSS_SPECIAL)
    if SPECIAL_POOL:
        return str(random.choice(SPECIAL_POOL))
    return str(random.choice(_WEAPON_LIST).wid)


def roll_weapon_pair(is_boss: bool = False) -> Tuple[str, str]:
    _build_weapon_table()
    pool = list(_WEAPON_LIST)
    pool.sort(key=lambda w: (w.damage, -w.cooldown))
    if is_boss:
        pool = pool[len(pool)//2:]
    else:
        pool = [w for w in pool if w.archetype not in ("emp",) or random.random() < 0.55]

    w1 = random.choice(pool)
    w2 = random.choice(pool)
    for _ in range(30):
        if w2.wid != w1.wid:
            break
        w2 = random.choice(pool)
    return (w1.wid, w2.wid)


def _aim_dir(v, target_pos: Optional["Vector2"]) -> "Vector2":
    base_angle = float(getattr(v, "angle", 0.0))
    if target_pos is not None:
        aim = (target_pos - v.pos)
        if aim.length_squared() > 1e-6:
            base_angle = float(math.degrees(math.atan2(-aim.y, aim.x)))
    rad = math.radians(base_angle)
    return Vector2(math.cos(rad), -math.sin(rad))


def fire_weapon(game, v, slot: int, target_pos: Optional["Vector2"] = None) -> None:
    _build_weapon_table()

    wid = getattr(v, "weapon1", _WEAPON_LIST[0].wid) if slot == 0 else getattr(v, "weapon2", _WEAPON_LIST[1].wid)
    w = weapon_by_id(str(wid))

    if slot == 0:
        if getattr(v, "mg_cooldown", 0.0) > 0.0:
            return
        v.mg_cooldown = float(w.cooldown)
    else:
        if getattr(v, "special_cooldown", 0.0) > 0.0:
            return
        v.special_cooldown = float(w.cooldown)

    dirv = _aim_dir(v, target_pos)
    origin = v.pos + dirv * (float(getattr(v, "radius", 22.0)) + 10.0)

    # Resolve Projectile class from the main module (this file)
    pr_cls = getattr(__import__(game.__class__.__module__, fromlist=["Projectile"]), "Projectile")

    def spawn_proj(kind: str, pos: "Vector2", vel: "Vector2", damage: float, ttl: float, radius: float):
        p = pr_cls(kind, pos, vel, v.id, damage=damage * float(getattr(v, "dmg_mult", 1.0)), ttl=ttl, radius=radius)
        if w.on_hit:
            try:
                p.on_hit = dict(w.on_hit)
            except Exception:
                pass
        game.projectiles.append(p)

    arch = w.archetype

    if arch in ("mg", "burst", "shotgun", "rail", "flame", "water", "harpoon"):
        pellets = max(1, int(w.pellets))
        spread = float(w.spread_deg)
        burst_n = 3 if arch == "burst" else 1
        for _b in range(burst_n):
            for _ in range(pellets):
                spr = random.uniform(-spread, spread)
                ang = math.atan2(dirv.y, dirv.x) + math.radians(spr)
                d = Vector2(math.cos(ang), math.sin(ang))
                spd = float(w.speed) * random.uniform(0.92, 1.05)
                vel = d * spd + v.vel * 0.35
                kind = "bullet"
                rad = float(w.radius)
                ttl = float(w.ttl)
                dmg = float(w.damage)

                if arch == "rail":
                    kind = "bullet"; rad = 2.0; ttl = 1.25
                elif arch == "flame":
                    kind = "bullet"; ttl = 0.55; rad = 3.0
                elif arch == "water":
                    kind = "water"; ttl = 1.0; rad = 4.0
                elif arch == "harpoon":
                    kind = "bullet"; ttl = 1.35; rad = 4.0

                spawn_proj(kind, origin, vel, dmg, ttl, rad)

        try:
            game._spawn_sparks(origin, 2 + (2 if arch == "shotgun" else 0))
        except Exception:
            pass
        try:
            if getattr(game, "snd_mg", None):
                game.play_sfx(game.snd_mg, v.pos, base_vol=0.25 if arch != "shotgun" else 0.35)
        except Exception:
            pass
        return

    if arch in ("rocket", "homing", "cluster"):
        spr = random.uniform(-w.spread_deg, w.spread_deg)
        ang = math.atan2(dirv.y, dirv.x) + math.radians(spr)
        d = Vector2(math.cos(ang), math.sin(ang))
        vel = d * float(w.speed) + v.vel * 0.25

        kind = "rocket" if arch == "rocket" else ("homing" if arch == "homing" else "cluster")
        p = pr_cls(kind, origin, vel, v.id, damage=w.damage * float(getattr(v, "dmg_mult", 1.0)), ttl=float(w.ttl), radius=float(w.radius))
        if w.on_hit:
            p.on_hit = dict(w.on_hit)

        if kind == "homing":
            try:
                tgt = None
                best = 1e9
                for ov in game.vehicles:
                    if not ov.alive or ov.id == v.id:
                        continue
                    d2 = (ov.pos - v.pos).length_squared()
                    if d2 < best:
                        best = d2
                        tgt = ov
                if tgt is not None:
                    p.target_id = tgt.id
                    p.turn_rate = 7.0
            except Exception:
                pass

        if kind == "cluster":
            try:
                p.subcount = int(5 + random.randint(0, 4))
                p.subdamage = float(w.damage * 0.65)
            except Exception:
                pass

        game.projectiles.append(p)
        try:
            game._spawn_sparks(origin, 6)
        except Exception:
            pass
        try:
            if getattr(game, "snd_expl", None):
                game.play_sfx(game.snd_expl, v.pos, base_vol=0.22)
        except Exception:
            pass
        return

    if arch in ("mine", "spike"):
        back = -dirv
        pos = v.pos + back * (float(getattr(v, "radius", 22.0)) + 6.0)
        kind = "mine" if arch == "mine" else "spike"
        p = pr_cls(kind, pos, Vector2(0, 0), v.id, damage=w.damage * float(getattr(v, "dmg_mult", 1.0)), ttl=float(w.ttl), radius=float(w.radius))
        if w.on_hit:
            p.on_hit = dict(w.on_hit)
        game.projectiles.append(p)
        try:
            game._spawn_sparks(pos, 4)
        except Exception:
            pass
        return

    if arch == "laser":
        rng = float(w.params.get("range", 980.0)) if w.params else 980.0
        a = Vector2(origin)
        b = a + dirv * rng
        hit_pos = Vector2(b)
        hit_obj = None
        best_t = 1.0

        def seg_dist2(p: "Vector2", a: "Vector2", b: "Vector2") -> Tuple[float, float]:
            ab = b - a
            ab2 = ab.length_squared()
            if ab2 < 1e-9:
                return (p.distance_squared_to(a), 0.0)
            t = max(0.0, min(1.0, (p - a).dot(ab) / ab2))
            proj = a + ab * t
            return (p.distance_squared_to(proj), t)

        for ov in getattr(game, "vehicles", []):
            if not ov.alive or ov.id == v.id:
                continue
            d2, t = seg_dist2(ov.pos, a, b)
            if d2 <= (ov.radius + 6.0) ** 2 and t < best_t:
                best_t = t
                hit_obj = ov
                hit_pos = a.lerp(b, t)

        for pp in getattr(game, "props", []):
            if not getattr(pp, "alive", True):
                continue
            d2, t = seg_dist2(pp.pos, a, b)
            rr = float(getattr(pp, "r", 18.0))
            if d2 <= (rr + 4.0) ** 2 and t < best_t:
                best_t = t
                hit_obj = pp
                hit_pos = a.lerp(b, t)

        if hit_obj is not None:
            try:
                if hasattr(hit_obj, "take_damage"):
                    if hit_obj in getattr(game, "vehicles", []):
                        hit_obj.take_damage(w.damage * float(getattr(v, "dmg_mult", 1.0)), attacker_id=v.id)
                    else:
                        hit_obj.take_damage(w.damage * float(getattr(v, "dmg_mult", 1.0)))

                if w.on_hit and hit_obj in getattr(game, "vehicles", []):
                    eff = dict(w.on_hit)
                    if eff.get("stun", 0.0) > 0.0:
                        hit_obj.stun_timer = max(float(getattr(hit_obj, "stun_timer", 0.0)), float(eff["stun"]))
                    if eff.get("slow", 0.0) > 0.0:
                        hit_obj.slow_timer = max(float(getattr(hit_obj, "slow_timer", 0.0)), float(eff["slow"]))
                        hit_obj.slow_mult = float(eff.get("slow_mult", 0.65))
                    if eff.get("poison", 0.0) > 0.0:
                        hit_obj.poison_timer = max(float(getattr(hit_obj, "poison_timer", 0.0)), float(eff["poison"]))
                        hit_obj.poison_dps = max(float(getattr(hit_obj, "poison_dps", 0.0)), float(eff.get("poison_dps", 6.0)))
                    if eff.get("ignite", 0.0) > 0.0:
                        hit_obj.burning = True
                        hit_obj.burn_source_id = v.id
                    if eff.get("armor_break", 0.0) > 0.0 and getattr(hit_obj, "armor", 0.0) > 0.0:
                        hit_obj.armor = max(0.0, float(hit_obj.armor) - float(eff["armor_break"]))
            except Exception:
                pass

        try:
            col = getattr(v, "special_color", (255, 120, 80))
            game._spawn_tracer(a, hit_pos, color=col, ttl=0.14, steps=14)
            game._spawn_sparks(hit_pos, 8)
        except Exception:
            pass
        return

    if arch == "lightning":
        rng = float(w.params.get("range", 720.0)) if w.params else 720.0
        chains = int(w.params.get("chains", 3.0)) if w.params else 3
        cur_pos = Vector2(origin)
        struck = set([v.id])

        for _ in range(max(1, chains)):
            tgt = None
            best = 1e18
            for ov in getattr(game, "vehicles", []):
                if not ov.alive or ov.id in struck:
                    continue
                d2 = (ov.pos - cur_pos).length_squared()
                if d2 < best and d2 <= rng * rng:
                    best = d2
                    tgt = ov
            if tgt is None:
                break
            struck.add(tgt.id)
            try:
                tgt.take_damage(w.damage * float(getattr(v, "dmg_mult", 1.0)), attacker_id=v.id)
                if w.on_hit and "stun" in w.on_hit:
                    tgt.stun_timer = max(float(getattr(tgt, "stun_timer", 0.0)), float(w.on_hit["stun"]))
            except Exception:
                pass
            try:
                col = (120, 200, 255)
                game._spawn_tracer(cur_pos, tgt.pos, color=col, ttl=0.10, steps=10)
                game._spawn_emp(tgt.pos)
            except Exception:
                pass
            cur_pos = Vector2(tgt.pos)
        return

    if arch == "emp":
        rad = float(w.params.get("radius", 360.0)) if w.params else 360.0
        for ov in getattr(game, "vehicles", []):
            if not ov.alive or ov.id == v.id:
                continue
            if (ov.pos - v.pos).length_squared() <= rad * rad:
                ov.stun_timer = max(float(getattr(ov, "stun_timer", 0.0)), 1.05)
        try:
            game._spawn_emp(v.pos)
        except Exception:
            pass
        return

    if arch == "grav":
        rad = float(w.params.get("radius", 300.0)) if w.params else 300.0
        pull = float(w.params.get("pull", 420.0)) if w.params else 420.0
        center = target_pos if target_pos is not None else (v.pos + dirv * 180.0)
        for ov in getattr(game, "vehicles", []):
            if not ov.alive or ov.id == v.id:
                continue
            d = (center - ov.pos)
            d2 = d.length_squared()
            if d2 <= rad * rad and d2 > 1e-6:
                ov.vel += d.normalize() * (pull * 0.016)
                ov.take_damage(w.damage * float(getattr(v, "dmg_mult", 1.0)) * 0.35, attacker_id=v.id)
                ov.slow_timer = max(float(getattr(ov, "slow_timer", 0.0)), 0.9)
                ov.slow_mult = min(float(getattr(ov, "slow_mult", 0.65)), 0.75)
        try:
            game._spawn_sparks(center, 10)
        except Exception:
            pass
        return


def fire_special(game, v, target_pos: Optional["Vector2"] = None) -> None:
    """Fire the vehicle's special weapon.

    main.py stores selected weapon id in `v.special`; we mirror it into `v.weapon2`.
    """
    try:
        wid = getattr(v, "special", None)
        if not wid:
            wid = random_special(is_boss=bool(getattr(v, "is_boss", False)))
            setattr(v, "special", str(wid))
        setattr(v, "weapon2", str(wid))
    except Exception:
        pass
    fire_weapon(game, v, slot=1, target_pos=target_pos)


def _bind_special_pools() -> None:
    global SPECIAL_POOL, BOSS_SPECIAL
    _build_weapon_table()
    SPECIAL_POOL = [w.wid for w in _WEAPON_LIST]
    try:
        strongest = max(_WEAPON_LIST, key=lambda w: (w.damage, w.radius, -w.cooldown))
        BOSS_SPECIAL = strongest.wid
    except Exception:
        BOSS_SPECIAL = _WEAPON_LIST[-1].wid

_bind_special_pools()


# --- Constants ---------------------------------------------------------------
# Authoritative (virtual) resolution: all game logic/camera/UI live in this pixel space.
WIDTH, HEIGHT = 1280, 720
FPS = 60

WORLD_W, WORLD_H = 5200, 5200
VEHICLE_CAP_MIN = 12
VEHICLE_CAP_MAX = 16  # increased per request (more chaos)

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
IMG_DIR = os.path.join(ASSET_DIR, "images")
VEHICLES_DIR = os.path.join(ASSET_DIR, "vehicles")
ALT_IMG_DIR = os.path.join(os.path.dirname(__file__), "images")
SFX_DIR = os.path.join(ASSET_DIR, "sfx")
POWERUPS_DIR = os.path.join(ASSET_DIR, "powerups")
POWERUP_SPRITES_DIR = os.path.join(POWERUPS_DIR, "sprites")
POWERUP_SFX_DIR = os.path.join(POWERUPS_DIR, "sfx")
POWERUP_HEAL_ICON_PATH = os.path.join(POWERUP_SPRITES_DIR, "heal.png")
POWERUP_ARMOR_ICON_PATH = os.path.join(POWERUP_SPRITES_DIR, "armor.png")
POWERUP_PICKUP_WAV_PATH = os.path.join(POWERUP_SFX_DIR, "pickup.wav")
SHEET_PATH = os.path.join(IMG_DIR, "vehicles_sheet.png")

# Destructible environment folders (drop any images into these)
DESTRUCT_OBS_DIR = os.path.join(IMG_DIR, "destructible_obstacles")
DESTRUCT_OBJ_DIR = os.path.join(IMG_DIR, "destructible_objects")

# Boss vehicles (drop any images into this folder)
BOSS_IMG_DIR = os.path.join(IMG_DIR, "boss_vehicles")

# Enemy waves: 3, 6, 9, then boss, then repeat
WAVE_COUNTS = [6, 12, 18]

# Special power variants (randomized per vehicle spawn)
# Boss-exclusive special
# All non-boss specials (keep existing + add new)
# --- Map themes / biomes -----------------------------------------------------
@dataclass(frozen=True)
class MapTheme:
    name: str
    weight: float
    ground_base: Tuple[int, int, int]
    grit_boost: int
    track_color: Tuple[int, int, int]
    dust_tint: Tuple[int, int, int]
    obstacles: int
    objects: int
    legacy: int
    layout: str  # "uniform", "clusters", "ruins_grid", "canyon_walls", "ring"

# Keep the original "classic" wasteland in the mix, but add dystopian variants.
MAP_THEMES: List[MapTheme] = [
    MapTheme("classic_wasteland", 0.30, (66, 56, 44), 30, (58, 49, 38), (150, 120, 90), 70, 55, 45, "uniform"),
    MapTheme("scrapyard",        0.16, (60, 54, 46), 28, (52, 47, 40), (165, 135, 105), 85, 75, 30, "clusters"),
    MapTheme("ruined_city",      0.16, (50, 48, 46), 22, (44, 43, 42), (140, 140, 145), 95, 55, 20, "ruins_grid"),
    MapTheme("toxic_bog",        0.11, (40, 46, 38), 26, (34, 38, 32), (120, 170, 120), 70, 65, 25, "clusters"),
    MapTheme("canyon_badlands",  0.11, (72, 52, 38), 34, (60, 44, 32), (180, 125, 85), 60, 45, 35, "canyon_walls"),
    MapTheme("ashlands",         0.10, (46, 46, 48), 22, (38, 38, 40), (160, 160, 165), 75, 55, 25, "ring"),
    MapTheme("snow_dystopia",    0.06, (78, 82, 88), 18, (68, 72, 78), (205, 210, 220), 55, 40, 20, "uniform"),
]

# Day/night cycle (purely visual; gameplay remains unchanged).
DAY_LENGTH_SEC = 220.0  # full cycle duration
HEADLIGHTS_ON_NIGHT_FACTOR = 0.18  # start enabling headlights around dusk

# Arena boundary: circular fire ring (also used for collision)
ARENA_CENTER = Vector2(WORLD_W * 0.5, WORLD_H * 0.5)
# Keep this large so the arena still feels expansive. Vehicles are constrained inside this circle.
ARENA_RADIUS = float(min(WORLD_W, WORLD_H) * 0.5 - 140.0)

def constrain_to_arena(pos: Vector2, vel: Vector2, body_radius: float,
                       bounce: float = 0.20, damp: float = 0.86) -> Tuple[Vector2, Vector2]:
    """Constrain a moving body to the circular arena.

    - If outside, position is projected to the boundary.
    - Velocity component pointing outward is reflected with damping.
    """
    c = ARENA_CENTER
    rlim = ARENA_RADIUS - float(body_radius)
    if rlim <= 10.0:
        return pos, vel
    d = pos - c
    d2 = d.length_squared()
    if d2 <= rlim * rlim:
        return pos, vel
    dist = math.sqrt(d2) if d2 > 1e-9 else 1.0
    n = d / dist  # outward normal
    pos = c + n * rlim
    vout = vel.dot(n)
    if vout > 0.0:
        # reflect outward component, keep some tangential motion so it doesn't feel sticky
        vel = vel - n * (vout * (1.0 + bounce))
    vel *= damp
    return pos, vel

def warp_through_arena_ring(pos: Vector2, vel: Vector2, body_radius: float, inset: float = 2.0) -> Tuple[Vector2, Vector2, bool]:
    """Pacman-style wrap across the arena fire ring.

    If a body moves outside the arena radius, it is teleported to the diametrically opposite
    point on the *inner* edge of the ring (accounting for body radius), keeping velocity intact.
    """
    c = ARENA_CENTER
    rlim = ARENA_RADIUS - float(body_radius)
    if rlim <= 10.0:
        return pos, vel, False
    d = pos - c
    d2 = d.length_squared()
    if d2 <= rlim * rlim:
        return pos, vel, False
    dist = math.sqrt(d2) if d2 > 1e-9 else 1.0
    n = d / dist  # outward direction from center to body
    # place slightly inside the ring on the opposite side to avoid immediate re-wrap due to float error
    pos = c - n * max(10.0, (rlim - float(inset)))
    return pos, vel, True

# --- Utility ----------------------------------------------------------------
def clamp(x: float, a: float, b: float) -> float:
    return a if x < a else b if x > b else x

def angle_to(v: Vector2) -> float:
    # pygame uses y down; atan2 with -y gives standard CCW, but we'll keep "screen angle"
    return math.degrees(math.atan2(-v.y, v.x))

def wrap_angle_deg(a: float) -> float:
    a = (a + 180.0) % 360.0 - 180.0
    return a

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def line_circle_intersect(p1: Vector2, p2: Vector2, c: Vector2, r: float) -> bool:
    # segment-circle intersection
    d = p2 - p1
    f = p1 - c
    a = d.dot(d)
    if a <= 1e-9:
        return (p1 - c).length_squared() <= r*r
    t = -f.dot(d) / a
    t = clamp(t, 0.0, 1.0)
    closest = p1 + d * t
    return (closest - c).length_squared() <= r*r

def rand_warm_tint() -> Tuple[int,int,int]:
    # warm palette (post-apocalyptic): sand, rust, sun-bleached paint
    r = random.randint(210, 255)
    g = random.randint(120, 210)
    b = random.randint(70, 170)
    # bias toward warm: keep r >= g >= b-ish
    g = min(g, r)
    b = min(b, g)
    return r, g, b

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def ensure_powerup_pickup_wav(path: str, sr: int = 44100) -> None:
    """Create a short placeholder pickup SFX if missing."""
    try:
        if os.path.isfile(path):
            return
        # Simple rising chirp with a soft envelope.
        import wave
        import struct
        dur = 0.14
        n = int(sr * dur)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sr)
            for i in range(n):
                t = i / sr
                f = 650.0 + 900.0 * (t / max(1e-6, dur))
                env = math.sin(math.pi * (t / max(1e-6, dur)))  # 0..1..0
                amp = 0.45 * env
                s = int(32767 * amp * math.sin(2 * math.pi * f * t))
                wf.writeframes(struct.pack("<h", s))
    except Exception:
        # Silent failure is fine; we still have runtime-generated fallback.
        pass


# --- Asset loading -----------------------------------------------------------
def extract_vehicle_sprites(sheet: pygame.Surface, cols: int = 12, rows: int = 7, target_max: int = 96) -> List[pygame.Surface]:
    """Slice a uniform sheet. Uses colorkey (0,0,0) for transparency."""
    sprites: List[pygame.Surface] = []
    sw, sh = sheet.get_width(), sheet.get_height()
    cell_w = sw / cols
    cell_h = sh / rows

    for ry in range(rows):
        for cx in range(cols):
            x0 = int(round(cx * cell_w))
            y0 = int(round(ry * cell_h))
            x1 = int(round((cx + 1) * cell_w))
            y1 = int(round((ry + 1) * cell_h))
            cell = sheet.subsurface(pygame.Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))).copy()
            cell.set_colorkey((0, 0, 0))

            # quick reject: if mostly empty, skip
            # (Using mask count is fast enough at load time)
            m = pygame.mask.from_surface(cell)
            if m.count() < 400:  # too empty
                continue

            # trim to bounding rect
            rect = m.get_bounding_rects()
            if rect:
                bb = rect[0]
                trimmed = cell.subsurface(bb).copy()
                trimmed.set_colorkey((0, 0, 0))
            else:
                trimmed = cell

            # scale down consistently
            w, h = trimmed.get_size()
            scale = target_max / max(w, h)
            if scale < 1.0:
                trimmed = pygame.transform.smoothscale(trimmed, (max(8, int(w * scale)), max(8, int(h * scale))))

            sprites.append(trimmed.convert_alpha())

    # Deduplicate near-empty duplicates by size/pixel count (lightweight)
    unique: List[pygame.Surface] = []
    seen = set()
    for s in sprites:
        key = (s.get_width(), s.get_height(), pygame.mask.from_surface(s).count() // 25)
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique

def tint_surface(src: pygame.Surface, tint_rgb: Tuple[int,int,int]) -> pygame.Surface:
    """Apply a *light* warm tint.

    The user is providing pre-cut vehicle sprites; heavy BLEND_MULT can wash them out.
    We keep the effect subtle by mixing the tint toward white before multiplying.
    """
    strength = 0.30  # lower = lighter tint
    eff = (
        int(255 * (1.0 - strength) + tint_rgb[0] * strength),
        int(255 * (1.0 - strength) + tint_rgb[1] * strength),
        int(255 * (1.0 - strength) + tint_rgb[2] * strength),
    )

    s = src.copy().convert_alpha()
    s.fill(eff, special_flags=pygame.BLEND_RGB_MULT)
    # tiny additive lift to avoid dulling
    s.fill((6, 4, 0), special_flags=pygame.BLEND_RGB_ADD)
    return s

def load_vehicle_tiles(img_dir: str, target_max: int = 64) -> List[pygame.Surface]:
    """Load vehicle images from a directory (user-supplied).

    Behavior:
    - Uses *any* image file placed in the directory as a possible vehicle sprite.
    - Supported: .png, .jpg, .jpeg, .bmp, .webp
    - Skips obvious spritesheets (vehicles_sheet.png) and very-empty images.
    - Scales sprites down to a consistent maximum dimension (keeps aspect ratio).
    """
    sprites: List[pygame.Surface] = []
    if not os.path.isdir(img_dir):
        return sprites

    exts = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
    paths: List[str] = []
    # allow subfolders as well, without requiring them
    for root, _dirs, files in os.walk(img_dir):
        for fn in files:
            if not fn.lower().endswith(exts):
                continue
            low = fn.lower()
            if low in ("vehicles_sheet.png",):
                continue
            paths.append(os.path.join(root, fn))
    paths = sorted(paths)

    for p in paths:
        try:
            img = pygame.image.load(p).convert_alpha()
        except Exception:
            # Some images may lack alpha; retry with colorkey on black.
            try:
                img = pygame.image.load(p).convert()
                img.set_colorkey((0, 0, 0))
                img = img.convert_alpha()
            except Exception:
                continue

        # Scale down consistently (keep aspect).
        w, h = img.get_size()
        if max(w, h) > target_max:
            scale = target_max / max(1, max(w, h))
            img = pygame.transform.smoothscale(
                img, (max(8, int(w * scale)), max(8, int(h * scale)))
            )

        # Reject near-empty images (safety)
        try:
            if pygame.mask.from_surface(img).count() < 120:
                continue
        except Exception:
            pass

        sprites.append(img)

    # lightweight dedupe (helps if files are duplicates)
    unique: List[pygame.Surface] = []
    seen = set()
    for spr in sprites:
        try:
            key = (spr.get_width(), spr.get_height(), pygame.mask.from_surface(spr).count() // 25)
        except Exception:
            key = (spr.get_width(), spr.get_height(), 0)
        if key in seen:
            continue
        seen.add(key)
        unique.append(spr)

    return unique


def load_image_set(root_dir: str, target_max: int = 96) -> List[pygame.Surface]:
    """Load a set of arbitrary sprites from a folder (recursively).

    Intended for destructible obstacles/objects:
    - Loads any image files under `root_dir` (.png/.jpg/.jpeg/.bmp/.webp).
    - Keeps original colors (no tint applied).
    - Scales down to a consistent maximum dimension while preserving aspect ratio.
    """
    sprites: List[pygame.Surface] = []
    if not os.path.isdir(root_dir):
        return sprites

    exts = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
    paths: List[str] = []
    for r, _dirs, files in os.walk(root_dir):
        for fn in files:
            if fn.lower().endswith(exts):
                paths.append(os.path.join(r, fn))
    paths.sort()

    for p in paths:
        try:
            img = pygame.image.load(p).convert_alpha()
        except Exception:
            try:
                img = pygame.image.load(p).convert()
                img.set_colorkey((0, 0, 0))
                img = img.convert_alpha()
            except Exception:
                continue

        w, h = img.get_size()
        if max(w, h) > target_max:
            scale = target_max / max(1, max(w, h))
            img = pygame.transform.smoothscale(img, (max(8, int(w * scale)), max(8, int(h * scale))))

        # Reject near-empty images (safety)
        try:
            if pygame.mask.from_surface(img).count() < 140:
                continue
        except Exception:
            pass

        sprites.append(img)

    # lightweight dedupe
    unique: List[pygame.Surface] = []
    seen = set()
    for spr in sprites:
        try:
            key = (spr.get_width(), spr.get_height(), pygame.mask.from_surface(spr).count() // 50)
        except Exception:
            key = (spr.get_width(), spr.get_height(), 0)
        if key in seen:
            continue
        seen.add(key)
        unique.append(spr)

    return unique



def create_fallback_vehicle_sprites(count: int = 8, target_max: int = 64) -> list[pygame.Surface]:
    sprites: list[pygame.Surface] = []
    base_w, base_h = 56, 32
    for idx in range(max(1, count)):
        surf = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
        seed = 1000 + idx * 17
        rng = random.Random(seed)
        body = (rng.randint(70, 130), rng.randint(55, 95), rng.randint(40, 75))
        body2 = (min(255, body[0] + 25), min(255, body[1] + 18), min(255, body[2] + 12))
        steel = (100, 108, 116)
        dark = (18, 18, 20)
        # body
        pygame.draw.rect(surf, body, (4, 12, 44, 12), border_radius=3)
        pygame.draw.rect(surf, dark, (4, 12, 44, 12), 2, border_radius=3)
        # cab
        pygame.draw.polygon(surf, body2, [(16, 12), (38, 12), (46, 6), (20, 6)])
        pygame.draw.polygon(surf, dark, [(16, 12), (38, 12), (46, 6), (20, 6)], 2)
        # windows
        pygame.draw.rect(surf, (78, 96, 108), (22, 8, 10, 4), border_radius=1)
        pygame.draw.rect(surf, (40, 54, 62), (23, 9, 8, 2), border_radius=1)
        # turret/barrel variation
        if idx % 2 == 0:
            pygame.draw.rect(surf, steel, (36, 10, 12, 2))
        else:
            pygame.draw.rect(surf, steel, (8, 10, 10, 2))
        # wheels
        for wx in (16, 38):
            pygame.draw.circle(surf, dark, (wx, 27), 5)
            pygame.draw.circle(surf, steel, (wx, 27), 3)
        # hood accent
        pygame.draw.line(surf, body2, (10, 20), (22, 16), 2)
        sprites.append(surf)
    return sprites

def load_sound(path: str) -> Optional[pygame.mixer.Sound]:
    try:
        if os.path.exists(path):
            return pygame.mixer.Sound(path)
    except Exception:
        return None
    return None


def generate_tone_sound(freq: float = 220.0, duration: float = 0.25, volume: float = 0.40) -> Optional[pygame.mixer.Sound]:
    """Generate a simple horn-like tone (fallback if no horn.wav is present).

    Uses pygame.mixer's current output format (no numpy dependency).
    """
    try:
        init = pygame.mixer.get_init()
        if not init:
            return None
        rate, _fmt, chans = init
        n = max(1, int(rate * duration))
        import array
        buf = array.array("h")
        amp = int(32767 * clamp(volume, 0.0, 1.0))
        # Slight tremolo and mild clipping to read more like a "horn" than a pure sine.
        for i in range(n):
            t = i / float(rate)
            trem = 0.78 + 0.22 * math.sin(2.0 * math.pi * 6.0 * t)
            s = math.sin(2.0 * math.pi * float(freq) * t)
            sample = int(amp * trem * s)
            # mild nonlinearity
            sample = int(sample * (1.0 - 0.15 * abs(sample) / 32767.0))
            sample = max(-32768, min(32767, sample))
            for _ in range(chans):
                buf.append(sample)
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except Exception:
        return None

# --- Game objects ------------------------------------------------------------
@dataclass
class Explosion:
    pos: Vector2
    radius: float
    damage: float
    ttl: float
    owner_id: Optional[int] = None

@dataclass
class Particle:
    pos: Vector2
    vel: Vector2
    ttl: float
    size: float
    color: Tuple[int,int,int]
    life: float = 0.0
    layer: int = 1  # 0 = ground FX (dust), 1 = above (sparks/smoke)

@dataclass
class TireMark:
    a: Vector2
    b: Vector2
    width: int
    ttl: float
    life: float
    color: Tuple[int,int,int]


@dataclass
class SandCloud:
    pos: Vector2  # screen-space position
    vel: Vector2  # screen-space velocity
    surf: pygame.Surface
    alpha: int
    scale: float


@dataclass
class Powerup:
    kind: str  # 'heal' or 'armor'
    pos: Vector2
    r: float = 11.0
    alive: bool = True
    ttl: float = 45.0  # seconds

class Projectile:
    def __init__(self, kind: str, pos: Vector2, vel: Vector2, owner_id: int, damage: float, ttl: float, radius: float = 2.0):
        self.kind = kind
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.owner_id = owner_id
        self.damage = damage
        self.ttl = ttl
        self.radius = radius
        self.alive = True

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.ttl -= dt
        if self.ttl <= 0:
            self.alive = False

class Prop:
    def __init__(self, kind: str, pos: Vector2, sprite: Optional[pygame.Surface] = None, hp: Optional[float] = None):
        """Destructible world prop.

        - Legacy props: barrel/crate/concrete (drawn procedurally).
        - Sprite props: loaded from folders (destructible_obstacles / destructible_objects).
        """
        self.kind = kind
        self.pos = Vector2(pos)
        self.sprite: Optional[pygame.Surface] = sprite

        if self.sprite is not None:
            # radius based on sprite footprint (used for collisions)
            self.r = max(14, int(max(self.sprite.get_width(), self.sprite.get_height()) * 0.40))
            base_hp = 220.0 if kind == "obstacle" else 140.0
            jitter = random.uniform(0.90, 1.25)
            self.max_hp = float(hp if hp is not None else base_hp * jitter)
            self.hp = self.max_hp
        else:
            if kind == "barrel":
                self.r = 18
                self.hp = 40
                self.max_hp = 40
            elif kind == "crate":
                self.r = 22
                self.hp = 55
                self.max_hp = 55
            else:
                self.r = 26
                self.hp = 85
                self.max_hp = 85

        self.alive = True

    def take_damage(self, dmg: float):
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False

class Vehicle:
    def __init__(self, vid: int, sprite: pygame.Surface, pos: Vector2, angle_deg: float, special: str, strength: float, is_boss: bool = False, hp_mult: float = 1.0):
        self.id = vid
        self.base_sprite = sprite
        self.sprite = sprite
        self.pos = Vector2(pos)
        self.vel = Vector2(0, 0)
        self.angle = angle_deg
        self.turn_rate = 220.0  # deg/sec (tuned)
        self.accel = 740.0
        self.max_speed = 500.0
        self.friction = 0.95
        self.radius = max(18.0, max(sprite.get_width(), sprite.get_height()) * 0.36)

        self.is_boss = bool(is_boss)
        self.last_hit_by: Optional[int] = None
        self.last_hit_age: float = 999.0

        # visual: motion blur amount (0..1) when accelerating
        self.motion_blur = 0.0
        # Strength roll: affects durability and (slightly) damage output.
        # Keep the spread noticeable but not extreme so fights remain readable.
        self.strength = float(strength)

        base_hp = 320.0 * self.strength
        hp_mult = float(hp_mult)
        if self.is_boss:
            # Bosses are intended to be dramatically tougher.
            hp_mult = max(hp_mult, 10.0)

        self.max_hp = base_hp * hp_mult
        # Armor buffer: absorbs damage before HP (powerup-driven)
        self.armor = 0.0
        self.max_armor = 0.0
        self.hp = self.max_hp

        self.dmg_mult = clamp(0.9 + (self.strength - 1.0) * 0.35, 0.75, 1.10)
        if self.is_boss:
            # Slightly more threatening, without turning into an instant delete.
            self.dmg_mult = clamp(self.dmg_mult * 1.06, 0.75, 1.25)

        # Boss handling: heavier/steadier feel
        if self.is_boss:
            self.turn_rate *= 0.90
            self.accel *= 0.86
            self.max_speed *= 0.90
            self.friction = 0.965
            self.radius *= 1.10
        self.alive = True

        self.special = special
        self.mg_cooldown = 0.0
        self.special_cooldown = 0.0

        # Special variants / status
        self.special_color = random.choice(LASER_COLORS)
        self.stealth_timer = 0.0

        # Fire state: ignite at <=10% HP and burn until destruction
        self.burning = False
        self.burn_source_id = None
        self.burn_emit_accum = 0.0

        # Turbo boost (player uses Left Shift). Boost increases accel/max speed temporarily.
        self.turbo_energy = 1.0  # 0..1
        self.turbo_active = False
        self.turbo_cd = 0.0
        self.ram_cd = 0.0  # cooldown for boost-ram damage ticks
        self.turbo_speed_mult = 1.55
        self.turbo_accel_mult = 1.85
        self.turbo_drain_rate = 0.78      # per second
        self.turbo_recharge_rate = 0.34   # per second

        self.ai = True
        self.stun_timer = 0.0

        # AI memory
        self.target_id: Optional[int] = None


        # trails / track emitters
        self.dust_accum = 0.0
        wl, wr = self.wheel_points()
        self.last_wheel_l = Vector2(wl)
        self.last_wheel_r = Vector2(wr)

    def forward(self) -> Vector2:
        rad = math.radians(self.angle)
        return Vector2(math.cos(rad), -math.sin(rad))

    def right(self) -> Vector2:
        rad = math.radians(self.angle)
        return Vector2(math.sin(rad), math.cos(rad))

    def wheel_points(self) -> Tuple[Vector2, Vector2]:
        """Approximate rear wheel contact points in world space."""
        f = self.forward()
        r = self.right()
        sep = self.radius * 0.42
        rear = self.radius * 0.28
        base = self.pos - f * rear
        return (base - r * sep, base + r * sep)

    def take_damage(self, dmg: float, attacker_id: Optional[int] = None):
        if attacker_id is not None and attacker_id != self.id:
            self.last_hit_by = int(attacker_id)
            self.last_hit_age = 0.0

        # Armor absorbs first (if any)
        try:
            if getattr(self, "armor", 0.0) > 0.0 and dmg > 0.0:
                absorbed = min(float(self.armor), float(dmg))
                self.armor = float(self.armor) - absorbed
                dmg = float(dmg) - absorbed
        except Exception:
            pass

        if dmg > 0.0:
            self.hp -= float(dmg)

        if self.hp <= 0 and self.alive:
            self.alive = False

    def update_physics(self, dt: float, throttle: float, turn: float, braking: bool, turbo: bool = False):
        if self.stun_timer > 0:
            throttle *= 0.25
            turn *= 0.25
            self.stun_timer -= dt

        # turbo timers
        self.ram_cd = max(0.0, self.ram_cd - dt)
        self.turbo_cd = max(0.0, self.turbo_cd - dt)

        # turbo gating: active only while button held and energy is available
        if turbo and self.turbo_cd <= 0.0 and self.turbo_energy > 0.02:
            self.turbo_active = True
        else:
            self.turbo_active = False

        if self.turbo_active:
            self.turbo_energy = max(0.0, self.turbo_energy - dt * self.turbo_drain_rate)
            if self.turbo_energy <= 0.0:
                self.turbo_active = False
                self.turbo_cd = max(self.turbo_cd, 0.85)
        else:
            self.turbo_energy = min(1.0, self.turbo_energy + dt * self.turbo_recharge_rate)

        self.angle -= turn * self.turn_rate * dt
        self.angle = (self.angle + 360) % 360

        # acceleration
        eff_accel = self.accel * (self.turbo_accel_mult if self.turbo_active else 1.0)
        eff_max_speed = self.max_speed * (self.turbo_speed_mult if self.turbo_active else 1.0)

        if braking:
            self.vel *= 0.78
        if throttle != 0:
            self.vel += self.forward() * (throttle * eff_accel * dt)

        # clamp speed
        spd = self.vel.length()
        if spd > eff_max_speed:
            self.vel.scale_to_length(eff_max_speed)

        self.pos += self.vel * dt
        fric = self.friction
        if self.turbo_active:
            fric = min(0.99, fric + 0.02)  # slightly less damping during boost
        self.vel *= fric

        # arena circular bounds (fire ring)
        self.pos, self.vel, _wrapped = warp_through_arena_ring(self.pos, self.vel, self.radius)

        # motion blur target (only when actively accelerating)
        speed = self.vel.length()
        if (throttle > 0.15) and (not braking) and speed > 40:
            target_blur = clamp((throttle) * (speed / max(1.0, eff_max_speed)), 0.0, 1.0)
        else:
            target_blur = 0.0
        # smooth to avoid flicker
        blend = clamp(dt * 10.0, 0.0, 1.0)
        self.motion_blur = self.motion_blur + (target_blur - self.motion_blur) * blend

        # cooldowns
        self.mg_cooldown = max(0.0, self.mg_cooldown - dt)
        self.special_cooldown = max(0.0, self.special_cooldown - dt)

# --- Main game ---------------------------------------------------------------
class Game:
    def __init__(self, external_surface=None, doomsday_ctx=None):
        """Create a game instance.

        If `external_surface` is provided, the game runs in *embedded* mode and draws
        into that surface (no display.set_mode / no display.flip).
        """
        pygame.init()
        self.doomsday_ctx = doomsday_ctx or {}
        try:
            seed = self.doomsday_ctx.get('session_seed')
            if seed is not None:
                random.seed(int(seed))
        except Exception:
            pass
        pygame.display.set_caption("Destruction Derby: Artillery (Top-Down)")

        self.embedded = external_surface is not None

        # --- Virtual resolution + presentation layer -------------------------
        # Game logic/camera/UI are always in this virtual space (WIDTH x HEIGHT).
        self.virtual_w = int(WIDTH)
        self.virtual_h = int(HEIGHT)

        # Quit confirmation modal (pauses simulation while open)
        self._quit_modal = False
        self._request_quit = False

        # Presentation state (only used when not embedded)
        self.window = None
        self.window_flags = 0
        self._last_win_size = None
        self._view_rect = pygame.Rect(0, 0, self.virtual_w, self.virtual_h)
        self._scale = 1.0
        self._scaled_surf = None
        self._scaled_size = (0, 0)

        if self.embedded:
            # Match the hub-provided surface size.
            try:
                w, h = external_surface.get_size()
            except Exception:
                w, h = (self.virtual_w, self.virtual_h)

            globals()['WIDTH'], globals()['HEIGHT'] = int(w), int(h)
            self.virtual_w = int(w)
            self.virtual_h = int(h)
            self._view_rect = pygame.Rect(0, 0, self.virtual_w, self.virtual_h)

            # In embedded mode, we draw directly into the provided surface.
            self.screen = external_surface
        else:
            # Create a resizable, decorated window. The game's render target stays at virtual_w/h.
            self._init_window()
            self.screen = pygame.Surface((self.virtual_w, self.virtual_h)).convert()

        self.clock = pygame.time.Clock()


        # audio
        self.audio_ok = False
        try:
            pygame.mixer.init()
            self.audio_ok = True
        except Exception:
            self.audio_ok = False

        self.snd_mg = load_sound(os.path.join(SFX_DIR, "mg.wav")) if self.audio_ok else None
        self.snd_expl = load_sound(os.path.join(SFX_DIR, "explosion.wav")) if self.audio_ok else None
        self.snd_rocket = load_sound(os.path.join(SFX_DIR, "rocket.wav")) if self.audio_ok else None
        self.snd_switch = load_sound(os.path.join(SFX_DIR, "switch.wav")) if self.audio_ok else None

        # Powerup pickup sound (prefers assets/powerups/sfx/)
        self.snd_powerup = None
        if self.audio_ok:
            pu_sfx_candidates = [
                POWERUP_PICKUP_WAV_PATH,
                os.path.join(POWERUP_SFX_DIR, "powerup.wav"),
                os.path.join(SFX_DIR, "powerup.wav"),
            ]
            for _pth in pu_sfx_candidates:
                snd = load_sound(_pth)
                if snd is not None:
                    self.snd_powerup = snd
                    break
            if self.snd_powerup is None:
                # Runtime fallback (and keep a file on disk so you can replace it later).
                self.snd_powerup = generate_tone_sound(freq=880.0, duration=0.12, volume=0.45)
                ensure_powerup_pickup_wav(POWERUP_PICKUP_WAV_PATH)
        self.snd_horn = load_sound(os.path.join(SFX_DIR, "horn.wav")) if self.audio_ok else None
        if self.audio_ok and self.snd_horn is None:
            self.snd_horn = generate_tone_sound(freq=196.0, duration=0.28, volume=0.48)

                # load sprites
        # Preferred path: pre-cut images in assets/vehicles (user-supplied tiles)
        raw_sprites = load_vehicle_tiles(VEHICLES_DIR, target_max=64)
        if not raw_sprites:
            raw_sprites = load_vehicle_tiles(IMG_DIR, target_max=64)
        if not raw_sprites:
            raw_sprites = load_vehicle_tiles(ALT_IMG_DIR, target_max=64)

        # Fallback path: legacy spritesheet slicing
        if not raw_sprites and os.path.exists(SHEET_PATH):
            sheet = pygame.image.load(SHEET_PATH).convert()
            raw_sprites = extract_vehicle_sprites(sheet, cols=12, rows=7, target_max=64)

        if not raw_sprites:
            raw_sprites = create_fallback_vehicle_sprites(count=10, target_max=64)

        # prepare multiple tinted variants for quick instancing
        self.vehicle_sprites: List[pygame.Surface] = []
        for s in raw_sprites:
            for _ in range(2):
                self.vehicle_sprites.append(tint_surface(s, rand_warm_tint()))

        # world visuals
        self.world = pygame.Surface((1024, 1024)).convert()
        self.map_theme = self._choose_map_theme()
        self.dust_tint = tuple(self.map_theme.dust_tint)
        self._build_wasteland_tile(self.world, self.map_theme)

        # state
        self.vehicles: List[Vehicle] = []
        self.props: List[Prop] = []
        self.projectiles: List[Projectile] = []
        self.explosions: List[Explosion] = []
        self.particles: List[Particle] = []
        self.ProjectileClass = Projectile
        self.ParticleClass = Particle

        self.tire_marks: List[TireMark] = []
        self.spawn_queue: List[float] = []  # timers to spawn vehicles

        # Kill tracking (UI + stats)
        self.kill_counts: Dict[int, int] = {}

        # --- Day / night cycle (visual) ------------------------------------
        self.day_length = DAY_LENGTH_SEC
        self.day_time = random.random() * self.day_length
        self.night_factor = 0.0  # 0..1 (updated every frame)

        # --- Wave system ----------------------------------------------------
        # Waves: 3, 6, 9 enemies, then a boss, then repeat.
        self.wave_counts = list(WAVE_COUNTS)
        self.wave_stage = 0  # 0..len(wave_counts)-1
        self.wave_state = "wave"  # "wave" or "boss"
        self.wave_total = 0
        self.wave_pause = 0.0

        # --- Powerups -------------------------------------------------------
        self.powerups: List[Powerup] = []
        self.powerup_icons: Dict[str, pygame.Surface] = {}
        self._init_powerup_icons()
        self.wave_next_type: Optional[str] = None  # "wave" or "boss"
        self.wave_next_count: int = 0
        self.boss_cycle_index = 0  # cycles boss images if available
        self.active_boss_ids: list[int] = []
        self.boss_wave_level: int = 1

        # Legacy (unused with waves) – kept to avoid attribute errors if referenced later.
        self.boss_spawn_queue: List[float] = []
        self.boss_active_limit = 1

        # --- Sandstorm overlay (screen-space atmospheric FX) -----------------
        # Wind-driven transparent dust clouds + tiny pixel debris. This is intentionally
        # screen-space (not world-space) so it reads as a sandstorm sweeping the camera.
        self.t_sim = 0.0
        self.wind_angle = random.uniform(-0.35, 0.35)  # radians, around left->right
        self.wind_speed = random.uniform(140.0, 220.0)  # px/sec
        self.wind = Vector2(1, 0)
        self.sandstorm_clouds: List[SandCloud] = []
        self.sandstorm_debris: List[Tuple[float, float, float, int]] = []  # x,y,speed, size
        self._init_sandstorm()

        # --- Random environmental detonations -------------------------------
        # Once every 30 seconds, a random destructible prop (object/structure) detonates,
        # dealing area damage to nearby vehicles.
        self.env_boom_interval = 30.0
        self.env_boom_timer = self.env_boom_interval
        self.env_boom_radius_obj = 240.0
        self.env_boom_radius_obs = 290.0
        self.env_boom_damage_obj = 95.0
        self.env_boom_damage_obs = 125.0

        self.next_vehicle_id = 1
        self.controlled_id: Optional[int] = None
        self.mouse_select_cd = 0.0

        self.font = pygame.font.SysFont("consolas", 16)
        self.big = pygame.font.SysFont("consolas", 22, bold=True)

        # Destructible environment folders (created if missing).
        ensure_dir(DESTRUCT_OBS_DIR)
        ensure_dir(DESTRUCT_OBJ_DIR)
        ensure_dir(BOSS_IMG_DIR)
        ensure_dir(VEHICLES_DIR)
        ensure_dir(POWERUP_SPRITES_DIR)
        ensure_dir(POWERUP_SFX_DIR)
        ensure_powerup_pickup_wav(POWERUP_PICKUP_WAV_PATH)

        # Load destructible obstacle/object sprites (any images you put in these folders will be used).
        self.obstacle_sprites: List[pygame.Surface] = load_image_set(DESTRUCT_OBS_DIR, target_max=108)
        # Make obstacles chunkier / more imposing.
        OBSTACLE_SCALE = 1.45
        scaled_obs: List[pygame.Surface] = []
        for s in self.obstacle_sprites:
            try:
                w, h = s.get_size()
                nw, nh = int(w * OBSTACLE_SCALE), int(h * OBSTACLE_SCALE)
                # Clamp so huge sprites don't dominate the arena.
                cap = 180
                m = max(1, max(nw, nh))
                if m > cap:
                    sc = cap / m
                    nw, nh = max(10, int(nw * sc)), max(10, int(nh * sc))
                if (nw, nh) != (w, h):
                    s2 = pygame.transform.smoothscale(s, (nw, nh))
                else:
                    s2 = s
                scaled_obs.append(s2)
            except Exception:
                scaled_obs.append(s)
        self.obstacle_sprites = scaled_obs
        self.object_sprites: List[pygame.Surface] = load_image_set(DESTRUCT_OBJ_DIR, target_max=92)

        # Load boss vehicle sprites (optional). Put any images into assets/images/boss_vehicles.
        boss_raw = load_vehicle_tiles(BOSS_IMG_DIR, target_max=92)
        self.boss_sprite_pool: List[pygame.Surface] = list(boss_raw)
        self.boss_sprites: List[pygame.Surface] = []
        for s in boss_raw:
            # A couple subtle variants; keep readable.
            self.boss_sprites.append(s)
            self.boss_sprites.append(tint_surface(s, (245, 170, 90)))

        # Drop a small hint file the first time, so the folders are self-documenting.
        if not self.obstacle_sprites:
            hint = os.path.join(DESTRUCT_OBS_DIR, "PUT_OBSTACLE_IMAGES_HERE.txt")
            if not os.path.exists(hint):
                try:
                    with open(hint, "w", encoding="utf-8") as f:
                        f.write("Put any obstacle images in this folder (png/jpg/webp/bmp).\n")
                        f.write("They will be loaded and spawned as destructible obstacles automatically.\n")
                except Exception:
                    pass
        if not self.object_sprites:
            hint = os.path.join(DESTRUCT_OBJ_DIR, "PUT_OBJECT_IMAGES_HERE.txt")
            if not os.path.exists(hint):
                try:
                    with open(hint, "w", encoding="utf-8") as f:
                        f.write("Put any object images in this folder (png/jpg/webp/bmp).\n")
                        f.write("They will be loaded and spawned as destructible objects automatically.\n")
                except Exception:
                    pass

        # Boss folder hint
        if not getattr(self, "boss_sprites", []):
            hint = os.path.join(BOSS_IMG_DIR, "PUT_BOSS_VEHICLE_IMAGES_HERE.txt")
            if not os.path.exists(hint):
                try:
                    with open(hint, "w", encoding="utf-8") as f:
                        f.write("Put boss vehicle images in this folder (png/jpg/webp/bmp).\n")
                        f.write("Bosses spawn after Wave 3 (then repeat).\n")
                except Exception:
                    pass
        # spawn world objects
        self._apply_map_theme(self.map_theme, respawn_props=True)

        # spawn a single player-controlled vehicle, then run enemy waves
        self._spawn_player_vehicle()
        self._start_wave(self.wave_counts[self.wave_stage])

        self.fire_phase = 0.0
        self.show_help = False

    

    # --- Windowing / scaling ------------------------------------------------
    def _init_window(self) -> None:
        """Create the resizable decorated window.

        The game's authoritative render stays at (virtual_w, virtual_h).
        The OS window can be any size; we letterbox/pillarbox on present().
        """
        flags = 0
        try:
            flags |= pygame.RESIZABLE
        except Exception:
            pass
        try:
            flags |= pygame.DOUBLEBUF
        except Exception:
            pass

        # Start "fullscreen-looking" but with borders (maximized-like).
        try:
            info = pygame.display.Info()
            w = max(640, int(getattr(info, "current_w", self.virtual_w)) - 16)
            h = max(480, int(getattr(info, "current_h", self.virtual_h)) - 16)
        except Exception:
            w, h = (self.virtual_w, self.virtual_h)

        self.window_flags = flags

        # Best-effort vsync (never crash if unsupported).
        win = None
        try:
            win = pygame.display.set_mode((w, h), flags, vsync=1)
        except TypeError:
            try:
                win = pygame.display.set_mode((w, h), flags)
            except Exception:
                win = pygame.display.set_mode((self.virtual_w, self.virtual_h), flags)
        except Exception:
            win = pygame.display.set_mode((self.virtual_w, self.virtual_h), flags)

        self.window = win
        self._update_viewport(force=True)

        # Try SDL2 maximize if available.
        self._maximize_window_with_borders()

    def _maximize_window_with_borders(self) -> None:
        if getattr(self, "embedded", False):
            return
        try:
            from pygame._sdl2 import Window  # type: ignore
            Window.from_display_module().maximize()
        except Exception:
            # Fallback: nothing (user can maximize manually).
            pass

    def _recreate_window(self, w: int, h: int) -> None:
        """Recreate the window surface after a resize."""
        if getattr(self, "embedded", False):
            return
        w = max(320, int(w))
        h = max(240, int(h))
        try:
            self.window = pygame.display.set_mode((w, h), self.window_flags, vsync=1)
        except TypeError:
            self.window = pygame.display.set_mode((w, h), self.window_flags)
        except Exception:
            self.window = pygame.display.set_mode((w, h), self.window_flags)
        self._update_viewport(force=True)


    def _update_viewport(self, *, force: bool = False) -> None:
        """Recompute present/mouse-mapping transforms for the current OS window size.

        Two modes (set self.scale_mode):
          - "fit"  : aspect-preserving letterbox/pillarbox (may show bars)
          - "cover" : aspect-preserving fill (no bars) by cropping the virtual surface
        """
        if getattr(self, "embedded", False):
            return

        # Current OS window size
        try:
            win_w, win_h = self.window.get_size()
        except Exception:
            try:
                win_w, win_h = pygame.display.get_surface().get_size()
            except Exception:
                win_w, win_h = (self.virtual_w, self.virtual_h)

        win_w = max(1, int(win_w))
        win_h = max(1, int(win_h))

        if (not force) and self._last_win_size == (win_w, win_h):
            return
        self._last_win_size = (win_w, win_h)

        vw = float(self.virtual_w)
        vh = float(self.virtual_h)
        mode = str(getattr(self, "scale_mode", "cover")).lower()

        # Default: show full virtual surface
        src_crop = pygame.Rect(0, 0, int(self.virtual_w), int(self.virtual_h))
        dst_rect = pygame.Rect(0, 0, win_w, win_h)

        if vw > 0 and vh > 0:
            if mode in ("cover", "fill", "no_bars"):
                # Fill the window with the virtual surface (no bars) by cropping.
                scale = max(win_w / vw, win_h / vh)
                scale = max(0.0001, float(scale))

                crop_w = win_w / scale
                crop_h = win_h / scale

                # Convert crop size to ints and clamp inside virtual surface.
                cw = int(round(crop_w))
                ch = int(round(crop_h))
                cw = int(clamp(cw, 1, self.virtual_w))
                ch = int(clamp(ch, 1, self.virtual_h))

                cx = int(round((self.virtual_w - cw) * 0.5))
                cy = int(round((self.virtual_h - ch) * 0.5))
                cx = int(clamp(cx, 0, self.virtual_w - cw))
                cy = int(clamp(cy, 0, self.virtual_h - ch))

                src_crop = pygame.Rect(cx, cy, cw, ch)
                dst_rect = pygame.Rect(0, 0, win_w, win_h)
            else:
                # Fit inside window with letterbox/pillarbox.
                scale = min(win_w / vw, win_h / vh)
                scale = max(0.0001, float(scale))

                view_w = int(round(vw * scale))
                view_h = int(round(vh * scale))
                view_w = max(1, view_w)
                view_h = max(1, view_h)

                view_x = int((win_w - view_w) // 2)
                view_y = int((win_h - view_h) // 2)

                src_crop = pygame.Rect(0, 0, int(self.virtual_w), int(self.virtual_h))
                dst_rect = pygame.Rect(view_x, view_y, view_w, view_h)
        else:
            scale = 1.0

        self._scale = float(scale)
        self._src_crop = src_crop
        self._view_rect = dst_rect  # where we blit the scaled frame in the OS window

        # Cache a destination surface for scaling to avoid per-frame allocations.
        target_size = (dst_rect.width, dst_rect.height)
        if target_size != self._scaled_size:
            self._scaled_size = target_size
            w, h = target_size
            if w > 0 and h > 0:
                try:
                    self._scaled_surf = pygame.Surface((w, h)).convert()
                except Exception:
                    self._scaled_surf = pygame.Surface((w, h))
            else:
                self._scaled_surf = None


    def window_to_virtual(self, win_pos: Tuple[int, int]) -> Tuple[Tuple[int, int], bool]:
        """Map OS-window pixel coords -> virtual coords. Returns ((vx,vy), inside).

        - In "fit" mode: returns inside=False for clicks in the bars.
        - In "cover" mode: always inside=True (window is fully covered by the crop).
        """
        if getattr(self, "embedded", False):
            x, y = win_pos
            x = int(clamp(x, 0, self.virtual_w - 1))
            y = int(clamp(y, 0, self.virtual_h - 1))
            return (x, y), True

        self._update_viewport()
        mx, my = int(win_pos[0]), int(win_pos[1])

        vr = self._view_rect
        mode = str(getattr(self, "scale_mode", "cover")).lower()

        if mode not in ("cover", "fill", "no_bars"):
            # In fit mode, ignore clicks in the bars.
            if not vr.collidepoint(mx, my):
                return (0, 0), False

        s = float(self._scale) if float(self._scale) > 1e-9 else 1.0
        crop = getattr(self, "_src_crop", pygame.Rect(0, 0, self.virtual_w, self.virtual_h))

        # Convert window coords into virtual coords, taking crop + scale into account.
        vx = int((mx - vr.x) / s) + int(crop.x)
        vy = int((my - vr.y) / s) + int(crop.y)

        vx = int(clamp(vx, 0, self.virtual_w - 1))
        vy = int(clamp(vy, 0, self.virtual_h - 1))
        return (vx, vy), True


    def _present(self) -> None:
        """Present the virtual surface to the resizable OS window.

        - "fit"  : letterbox/pillarbox (bars)
        - "cover" : fill window (no bars) by cropping
        """
        if getattr(self, "embedded", False):
            return

        self._update_viewport()
        try:
            self.window.fill((0, 0, 0))
        except Exception:
            pass

        vr = self._view_rect
        if vr.width > 0 and vr.height > 0:
            # Source crop (virtual) and destination (window)
            crop = getattr(self, "_src_crop", pygame.Rect(0, 0, self.virtual_w, self.virtual_h))
            try:
                src = self.screen.subsurface(crop)
            except Exception:
                src = self.screen

            # One scale op per frame. Reuse a destination surface to reduce allocations.
            dst = self._scaled_surf
            if dst is not None:
                try:
                    pygame.transform.scale(src, self._scaled_size, dst)
                    scaled = dst
                except TypeError:
                    scaled = pygame.transform.scale(src, self._scaled_size)
                except Exception:
                    scaled = pygame.transform.scale(src, self._scaled_size)
            else:
                scaled = pygame.transform.scale(src, self._scaled_size)

            try:
                self.window.blit(scaled, vr.topleft)
            except Exception:
                pass

        pygame.display.flip()

    def _draw_quit_overlay(self) -> None:
        if not getattr(self, "_quit_modal", False):
            return
        try:
            overlay = pygame.Surface((self.virtual_w, self.virtual_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 170))
            self.screen.blit(overlay, (0, 0))

            msg = "Quit? (Y/Enter = Yes, N/Esc = No)"
            # Use big font if available; fallback to default font.
            try:
                font = getattr(self, "big", None) or pygame.font.SysFont("consolas", 22, bold=True)
                small = getattr(self, "font", None) or pygame.font.SysFont("consolas", 16)
            except Exception:
                font = pygame.font.Font(None, 32)
                small = pygame.font.Font(None, 22)

            t1 = font.render("Quit?", True, (255, 255, 255))
            t2 = small.render("(Y/Enter = Yes, N/Esc = No)", True, (235, 235, 235))

            box_w = max(t1.get_width(), t2.get_width()) + 48
            box_h = t1.get_height() + t2.get_height() + 42
            bx = (self.virtual_w - box_w) // 2
            by = (self.virtual_h - box_h) // 2
            box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
            box.fill((20, 20, 20, 210))
            pygame.draw.rect(box, (240, 240, 240, 160), box.get_rect(), 2)

            box.blit(t1, ((box_w - t1.get_width()) // 2, 14))
            box.blit(t2, ((box_w - t2.get_width()) // 2, 18 + t1.get_height()))

            self.screen.blit(box, (bx, by))
        except Exception:
            pass

    def _process_event(self, event) -> None:
        """Centralized event handler (run() + embedded step())."""
        try:
            etype = event.type
        except Exception:
            return

        if etype == pygame.QUIT:
            self._request_quit = True
            return

        # Resize handling (non-embedded only)
        if (not getattr(self, "embedded", False)) and etype == pygame.VIDEORESIZE:
            try:
                self._recreate_window(event.w, event.h)
            except Exception:
                pass
            return

        if etype == pygame.KEYDOWN:
            key = event.key

            # If quit modal is open, only accept confirm/cancel keys.
            if getattr(self, "_quit_modal", False):
                if key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._request_quit = True
                elif key in (pygame.K_n, pygame.K_ESCAPE):
                    self._quit_modal = False
                return

            # Normal controls
            if key == pygame.K_ESCAPE:
                self._quit_modal = True
                return
            if key == pygame.K_SPACE:
                self.honk()
                return
    def _build_wasteland_tile(self, surf: pygame.Surface, theme: Optional[MapTheme] = None):
        """Build a tiling ground texture for the current map theme."""
        if theme is None:
            theme = getattr(self, "map_theme", None)
        if theme is None:
            # safe defaults
            base = (66, 56, 44)
            grit_boost = 30
            track = (58, 49, 38)
            name = "classic_wasteland"
        else:
            base = tuple(theme.ground_base)
            grit_boost = int(theme.grit_boost)
            track = tuple(theme.track_color)
            name = str(theme.name)
    
        w, h = surf.get_size()
        surf.fill(base)
    
        # procedural grit / noise
        # Use a mix of speckle sizes so the ground reads as natural pixel/noise rather than flat fill.
        for _ in range(24000):
            x = random.randrange(w)
            y = random.randrange(h)
            c = random.randint(0, grit_boost)
            r = clamp(base[0] + c, 0, 255)
            g = clamp(base[1] + c // 2, 0, 255)
            b = clamp(base[2] + c // 3, 0, 255)
            surf.set_at((x, y), (r, g, b))
    
        # larger blotches (biome-specific)
        blotch = 340 if name in ("ruined_city", "ashlands") else 260
        for _ in range(blotch):
            x = random.randrange(w)
            y = random.randrange(h)
            rr = random.randint(3, 9)
            shade = random.randint(-18, 24)
            col = (clamp(base[0] + shade, 0, 255), clamp(base[1] + shade, 0, 255), clamp(base[2] + shade, 0, 255))
            pygame.draw.circle(surf, col, (x, y), rr)
    
        # faint tire tracks / drag marks
        tracks = 260 if name not in ("snow_dystopia",) else 160
        for _ in range(tracks):
            x0 = random.randrange(w)
            y0 = random.randrange(h)
            x1 = clamp(x0 + random.randint(-260, 260), 0, w - 1)
            y1 = clamp(y0 + random.randint(-260, 260), 0, h - 1)
            pygame.draw.line(surf, track, (x0, y0), (x1, y1), random.randint(1, 2))
    
        # cracks / plates for some biomes
        if name in ("canyon_badlands", "classic_wasteland", "scrapyard"):
            for _ in range(120):
                x0 = random.randrange(w)
                y0 = random.randrange(h)
                pts = [(x0, y0)]
                steps = random.randint(6, 14)
                for _s in range(steps):
                    x0 = clamp(x0 + random.randint(-38, 38), 0, w - 1)
                    y0 = clamp(y0 + random.randint(-28, 28), 0, h - 1)
                    pts.append((x0, y0))
                pygame.draw.lines(surf, (max(0, base[0] - 16), max(0, base[1] - 16), max(0, base[2] - 16)), False, pts, 1)
    
        # toxic sheen flecks
        if name == "toxic_bog":
            for _ in range(900):
                x = random.randrange(w)
                y = random.randrange(h)
                if random.random() < 0.85:
                    continue
                surf.set_at((x, y), (clamp(base[0] + 10, 0, 255), clamp(base[1] + 32, 0, 255), clamp(base[2] + 10, 0, 255)))
    
    
    def _choose_map_theme(self) -> MapTheme:
        # Weighted random choice.
        total = sum(max(0.0, t.weight) for t in MAP_THEMES) or 1.0
        r = random.random() * total
        acc = 0.0
        for t in MAP_THEMES:
            acc += max(0.0, t.weight)
            if r <= acc:
                return t
        return MAP_THEMES[0]

    def _apply_map_theme(self, theme: MapTheme, *, respawn_props: bool = True) -> None:
        """Apply a biome theme: ground texture, sandstorm tint, and prop layout."""
        self.map_theme = theme
        self.dust_tint = tuple(theme.dust_tint)

        # Rebuild the tiling ground texture.
        try:
            self._build_wasteland_tile(self.world, theme)
        except Exception:
            # Never let a theme failure crash the game.
            self._build_wasteland_tile(self.world, MAP_THEMES[0])

        # Refresh sandstorm visuals to match biome tint.
        try:
            self._init_sandstorm()
        except Exception:
            pass

        if respawn_props:
            # Clear existing props and respawn with themed layout.
            self.props.clear()
            self._spawn_props_themed(theme)

            # If a vehicle spawned overlapping a new prop, nudge it away.
            for v in self.vehicles:
                if not v.alive:
                    continue
                for _ in range(12):
                    bumped = False
                    for p in self.props:
                        if not p.alive:
                            continue
                        d = (v.pos - p.pos).length()
                        if d < (v.radius + p.r + 6):
                            # push outward from the prop
                            away = (v.pos - p.pos)
                            if away.length_squared() < 1e-6:
                                away = Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
                            away = away.normalize()
                            v.pos += away * (v.radius + p.r + 10 - d)
                            bumped = True
                    if not bumped:
                        break
                v.pos, v.vel = constrain_to_arena(v.pos, v.vel, v.radius, bounce=0.0, damp=1.0)

    def _spawn_props_themed(self, theme: MapTheme) -> None:
        """Spawn destructible props according to the chosen map theme and layout."""

        def sampler(kind: str) -> Vector2:
            layout = theme.layout
            # Base sampler: uniform in the arena.
            if layout == "uniform":
                return self._rand_in_arena(margin=260.0)

            # Clustered junk fields / bog pockets.
            if layout == "clusters":
                if not hasattr(self, "_theme_clusters") or self._theme_clusters is None:
                    self._theme_clusters = [self._rand_in_arena(margin=520.0) for _ in range(random.randint(4, 7))]
                c = random.choice(self._theme_clusters)
                # gaussian-ish offset
                off = Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
                if off.length_squared() < 1e-6:
                    off = Vector2(1, 0)
                off = off.normalize() * random.uniform(0.0, 420.0)
                return Vector2(c) + off

            # Ruined city: loose grid of streets/building clumps.
            if layout == "ruins_grid":
                step = 520.0
                gx = round(random.uniform(-ARENA_RADIUS * 0.65, ARENA_RADIUS * 0.65) / step) * step
                gy = round(random.uniform(-ARENA_RADIUS * 0.65, ARENA_RADIUS * 0.65) / step) * step
                base = ARENA_CENTER + Vector2(gx, gy)
                # jitter to avoid perfect squares
                base += Vector2(random.uniform(-180, 180), random.uniform(-180, 180))
                return base

            # Canyon walls: two sweeping rubble lines + scattered debris.
            if layout == "canyon_walls":
                if random.random() < 0.66:
                    # line-ish distribution
                    ang = random.choice([0.28, -0.28])
                    # offset from center
                    off = Vector2(0, 1).rotate_rad(ang) if hasattr(Vector2(0,1), "rotate_rad") else Vector2(-math.sin(ang), math.cos(ang))
                    base = ARENA_CENTER + off * random.uniform(-520, 520)
                    # along-line
                    along = Vector2(1, 0).rotate_rad(ang) if hasattr(Vector2(1,0), "rotate_rad") else Vector2(math.cos(ang), math.sin(ang))
                    return base + along * random.uniform(-ARENA_RADIUS * 0.72, ARENA_RADIUS * 0.72) + Vector2(random.uniform(-90, 90), random.uniform(-90, 90))
                return self._rand_in_arena(margin=260.0)

            # Ring of debris: heavier clutter near mid-radius.
            if layout == "ring":
                ang = random.random() * math.tau
                rr = random.uniform(ARENA_RADIUS * 0.38, ARENA_RADIUS * 0.70)
                pos = ARENA_CENTER + Vector2(math.cos(ang), math.sin(ang)) * rr
                pos += Vector2(random.uniform(-140, 140), random.uniform(-140, 140))
                return pos

            return self._rand_in_arena(margin=260.0)

        # reset per-theme helpers
        self._theme_clusters = None

        # Lower prop density vs earlier builds: fewer, larger, and more readable encounters.
        obstacles = max(0, int(theme.obstacles * 0.55))
        objects = max(0, int(theme.objects * 0.55))

        # Use existing _spawn_props logic, but override sampling to shape the map.
        def spawn_sprite_props(kind: str, sprites: List[pygame.Surface], n: int, min_spacing: float, hp_base: float) -> int:
            if not sprites or n <= 0:
                return 0
            spawned = 0
            for _ in range(n):
                for _attempt in range(160):
                    pos = sampler(kind)
                    # keep inside arena
                    pos, _v = constrain_to_arena(Vector2(pos), Vector2(0, 0), 0.0, bounce=0.0, damp=1.0)
                    if self._spot_ok(pos, min_spacing):
                        spr = random.choice(sprites)
                        hp = hp_base * random.uniform(0.85, 1.25)
                        self.props.append(Prop(kind, pos, sprite=spr, hp=hp))
                        spawned += 1
                        break
            return spawned

        spawned = 0
        spawned += spawn_sprite_props("obstacle", getattr(self, "obstacle_sprites", []), obstacles, min_spacing=230.0, hp_base=320.0)
        spawned += spawn_sprite_props("object", getattr(self, "object_sprites", []), objects, min_spacing=170.0, hp_base=175.0)
    def _rand_in_arena(self, margin: float = 220.0, body_radius: float = 0.0) -> Vector2:
        """Random point uniformly distributed in the arena disk, inset by `margin`."""
        rmax = max(10.0, ARENA_RADIUS - float(body_radius) - float(margin))
        ang = random.random() * math.tau
        # sqrt for uniform area distribution
        rr = math.sqrt(random.random()) * rmax
        return ARENA_CENTER + Vector2(math.cos(ang), math.sin(ang)) * rr

    def _enforce_arena_bounds(self):
        """Re-apply arena bounds after collision resolution / knockback."""
        for v in self.vehicles:
            if not v.alive:
                continue
            v.pos, v.vel, _wrapped = warp_through_arena_ring(v.pos, v.vel, v.radius)

    def _spawn_props(self, obstacles: int = 38, objects: int = 26, legacy: int = 26):
        """Spawn destructible environment props.

        - `assets/images/destructible_obstacles/` => larger, higher-HP obstacles
        - `assets/images/destructible_objects/`   => smaller, lower-HP objects

        Spawns are rejection-sampled to keep props spaced apart.
        """
        def spawn_sprite_props(kind: str, sprites: List[pygame.Surface], n: int, min_spacing: float, hp_base: float) -> int:
            if not sprites or n <= 0:
                return 0
            spawned = 0
            for _ in range(n):
                for _attempt in range(140):
                    pos = self._rand_in_arena(margin=260.0)
                    if self._spot_ok(pos, min_spacing):
                        spr = random.choice(sprites)
                        hp = hp_base * random.uniform(0.85, 1.25)
                        self.props.append(Prop(kind, pos, sprite=spr, hp=hp))
                        spawned += 1
                        break
            return spawned

        spawned = 0
        spawned += spawn_sprite_props("obstacle", getattr(self, "obstacle_sprites", []), obstacles, min_spacing=230.0, hp_base=320.0)
        spawned += spawn_sprite_props("object", getattr(self, "object_sprites", []), objects, min_spacing=170.0, hp_base=175.0)
    def _detonate_random_prop(self) -> None:
        """Force a random prop (object/structure) to explode.

        Environmental hazard: once per interval, pick a living prop and detonate it.
        The prop is removed immediately to avoid a second cleanup burst.
        """
        if not self.props:
            return
        alive = [p for p in self.props if getattr(p, "alive", False)]
        if not alive:
            return

        # Prefer larger sprite props (structures) but keep some randomness.
        struct = [p for p in alive if getattr(p, "kind", "") in ("obstacle", "object")]
        pick_pool = struct if struct and random.random() < 0.75 else alive
        p = random.choice(pick_pool)

        pos = Vector2(p.pos)
        if getattr(p, "kind", "") == "obstacle":
            radius = float(self.env_boom_radius_obs)
            dmg = float(self.env_boom_damage_obs)
        else:
            radius = float(self.env_boom_radius_obj)
            dmg = float(self.env_boom_damage_obj)

        self._spawn_explosion(pos, radius=radius, dmg=dmg, owner_id=None)
        self._spawn_sparks(pos, 22)

        # Remove immediately so the standard cleanup doesn't add a second effect burst.
        try:
            self.props.remove(p)
        except ValueError:
            pass


    def _random_special(self) -> str:
        return random_special(is_boss=False)

    def _spawn_vehicle(self, offscreen_from: Optional[Vector2] = None) -> Vehicle:
        sprite = random.choice(self.vehicle_sprites)
        special = self._random_special()
        strength = random.uniform(0.75, 1.35)


        # Preview radius so we can guarantee spawns stay inside the fire ring.
        preview_radius = max(18.0, max(sprite.get_width(), sprite.get_height()) * 0.36)
        # spawn position
        if offscreen_from is None:
            pos = self._rand_in_arena(margin=240.0, body_radius=preview_radius)
        else:
            center = Vector2(offscreen_from)
            min_offscreen = 900.0
            for _ in range(90):
                pos = self._rand_in_arena(margin=240.0, body_radius=preview_radius)
                if (pos - center).length() >= min_offscreen and self._spot_ok(pos, 60):
                    break
            else:
                pos = self._rand_in_arena(margin=240.0, body_radius=preview_radius)
        angle_deg = 90.0 if len(self.vehicles) == 0 else random.uniform(0, 360)
        v = Vehicle(self.next_vehicle_id, sprite, pos, angle_deg, special, strength)
        # Final safety clamp: never allow a vehicle to start outside the arena.
        v.pos, v.vel = constrain_to_arena(v.pos, v.vel, v.radius, bounce=0.0, damp=1.0)
        self.next_vehicle_id += 1
        self.vehicles.append(v)
        return v


    def _spawn_player_vehicle(self) -> Vehicle:
        """Spawn one controllable vehicle (the player's starting car)."""
        # Try center first, then random until we find a clear spot.
        pos = Vector2(ARENA_CENTER)
        for _ in range(140):
            if self._spot_ok(pos, 120.0):
                break
            pos = self._rand_in_arena(margin=360.0)

        v = self._spawn_vehicle(offscreen_from=None)
        v.pos = Vector2(pos)
        v.vel = Vector2(0, 0)
        v.pos, v.vel = constrain_to_arena(v.pos, v.vel, v.radius, bounce=0.0, damp=1.0)
        v.angle = 90.0
        setattr(v, "wave_enemy", False)

        # Set as the initial controlled vehicle.
        self.controlled_id = v.id
        self._set_controlled(v.id)
        return v

    def _alive_wave_enemy_count(self) -> int:
        return sum(1 for v in self.vehicles if v.alive and getattr(v, "wave_enemy", False) and not getattr(v, "is_boss", False))

    def _start_wave(self, count: int) -> None:
        self.wave_state = "wave"
        self.wave_total = int(count)
        self.active_boss_ids = []

        # Spawn enemies off-screen around the camera center.
        ref = self._camera_center()
        for _ in range(int(count)):
            vv = self._spawn_vehicle(offscreen_from=ref)
            setattr(vv, "wave_enemy", True)

    def _start_boss(self) -> None:
        self.wave_state = "boss"
        self.wave_total = 0
        self.active_boss_ids = []

        ref = self._camera_center()
        pool = getattr(self, "boss_sprite_pool", [])
        boss_count = max(1, int(getattr(self, "boss_wave_level", 1)))

        for _ in range(boss_count):
            sprite_override = None
            if pool:
                sprite_override = pool[self.boss_cycle_index % len(pool)]
                self.boss_cycle_index += 1

            boss = self._spawn_boss(offscreen_from=ref, sprite_override=sprite_override)
            if boss is None:
                continue

            self.active_boss_ids.append(boss.id)
            setattr(boss, "wave_enemy", False)
            setattr(boss, "wave_boss", True)
            setattr(boss, "is_boss", True)

    def _is_active_boss_alive(self) -> bool:
        return self._active_boss_count() > 0

    def _update_waves(self, dt: float) -> None:
        # If a timed transition is pending, count it down and execute when it reaches 0.
        if self.wave_pause > 0.0:
            self.wave_pause = max(0.0, self.wave_pause - dt)

        if self.wave_pause <= 0.0 and self.wave_next_type is not None:
            nxt = self.wave_next_type
            self.wave_next_type = None
            if nxt == "wave":
                self._start_wave(self.wave_next_count)
            elif nxt == "boss":
                self._start_boss()
            return

        # No pending transition; evaluate wave completion.
        if self.wave_state == "wave":
            if self._alive_wave_enemy_count() <= 0:
                # Advance to next wave or boss.
                self.wave_stage += 1
                if self.wave_stage >= len(self.wave_counts):
                    self.wave_stage = 0
                    self.wave_next_type = "boss"
                    self.wave_pause = 1.25
                else:
                    self.wave_next_type = "wave"
                    self.wave_next_count = int(self.wave_counts[self.wave_stage])
                    self.wave_pause = 0.95

        elif self.wave_state == "boss":
            if not self._is_active_boss_alive():
                # Boss defeated => next boss wave has +1 bosses.
                try:
                    self.boss_wave_level = int(getattr(self, "boss_wave_level", 1)) + 1
                except Exception:
                    self.boss_wave_level = 2

                # Boss defeated => restart cycle at wave 1 (new "generation" => new map design).
                self.wave_stage = 0

                try:
                    self.map_theme = self._choose_map_theme()
                    self._apply_map_theme(self.map_theme, respawn_props=True)
                except Exception:
                    # Never let map regen crash wave progression.
                    pass

                self.wave_next_type = "wave"
                self.wave_next_count = int(self.wave_counts[self.wave_stage])
                self.wave_pause = 1.15


    def _init_powerup_icons(self) -> None:



        """Load small, semi-transparent placeholder icons for powerups.



    



        Files (auto-created if missing):



          - assets/powerups/sprites/heal.png



          - assets/powerups/sprites/armor.png



        """



        try:



            ensure_dir(POWERUP_SPRITES_DIR)



    



            def make_icon(kind: str) -> pygame.Surface:



                # 18x18 icon, transparent background



                s = pygame.Surface((18, 18), pygame.SRCALPHA)



                if kind == "heal":



                    col = (120, 255, 160, 140)



                    # ring + plus



                    pygame.draw.circle(s, col, (9, 9), 7, 2)



                    pygame.draw.line(s, col, (9, 5), (9, 13), 2)



                    pygame.draw.line(s, col, (5, 9), (13, 9), 2)



                else:



                    col = (170, 210, 255, 140)



                    # shield-ish diamond



                    pts = [(9, 2), (15, 7), (12, 15), (6, 15), (3, 7)]



                    pygame.draw.polygon(s, col, pts, 2)



                    pygame.draw.line(s, col, (9, 6), (9, 13), 2)



                return s



    



            def load_or_create(path: str, kind: str) -> pygame.Surface:



                try:



                    if os.path.isfile(path):



                        img = pygame.image.load(path).convert_alpha()



                        # scale down if user drops in a larger icon



                        if max(img.get_width(), img.get_height()) > 28:



                            sc = 18 / max(1, max(img.get_width(), img.get_height()))



                            img = pygame.transform.smoothscale(img, (max(10, int(img.get_width()*sc)), max(10, int(img.get_height()*sc))))



                        return img



                except Exception:



                    pass



    



                img = make_icon(kind)



                try:



                    pygame.image.save(img, path)



                except Exception:



                    pass



                return img



    



            self.powerup_icons["heal"] = load_or_create(POWERUP_HEAL_ICON_PATH, "heal")



            self.powerup_icons["armor"] = load_or_create(POWERUP_ARMOR_ICON_PATH, "armor")



        except Exception:



            self.powerup_icons = {}

    def _spawn_wave_powerup(self) -> None:
        """Spawn ~1 powerup at the start of each wave/boss phase."""
        try:
            self.powerups = [p for p in self.powerups if getattr(p, "alive", False)]
        except Exception:
            self.powerups = []
        if any(getattr(p, "alive", False) for p in self.powerups):
            return

        kind = "heal" if random.random() < 0.55 else "armor"
        for _ in range(80):
            pos = self._rand_in_arena(margin=260.0, body_radius=14.0)
            if self._spot_ok(pos, 70.0):
                self.powerups.append(Powerup(kind=kind, pos=Vector2(pos)))
                return
        self.powerups.append(Powerup(kind=kind, pos=Vector2(self._rand_in_arena(margin=260.0))))

    def _update_powerups(self, dt: float) -> None:
        if not getattr(self, "powerups", None):
            return
        for pu in list(self.powerups):
            if not getattr(pu, "alive", False):
                continue
            try:
                pu.ttl = float(getattr(pu, "ttl", 45.0)) - dt
                if pu.ttl <= 0.0:
                    pu.alive = False
                    continue
            except Exception:
                pass

            for v in self.vehicles:
                if not getattr(v, "alive", False):
                    continue
                rr = float(getattr(v, "radius", 22.0)) + float(getattr(pu, "r", 11.0))
                if (v.pos - pu.pos).length_squared() <= rr * rr:
                    if pu.kind == "heal":
                        v.hp = float(getattr(v, "max_hp", v.hp))
                    elif pu.kind == "armor":
                        add = 240.0 if not getattr(v, "is_boss", False) else 520.0
                        try:
                            v.armor = float(getattr(v, "armor", 0.0)) + add
                            v.max_armor = max(float(getattr(v, "max_armor", 0.0)), float(v.armor))
                            cap = 780.0 if not getattr(v, "is_boss", False) else 1650.0
                            if v.armor > cap:
                                v.armor = cap
                                v.max_armor = max(float(getattr(v, "max_armor", 0.0)), cap)
                        except Exception:
                            pass

                    pu.alive = False
                    if getattr(self, "snd_powerup", None):
                        self.play_sfx(self.snd_powerup, pu.pos, base_vol=0.65)
                    break

        self.powerups = [p for p in self.powerups if getattr(p, "alive", False)]

    def _active_boss_count(self) -> int:
        return sum(1 for v in self.vehicles if v.alive and getattr(v, "is_boss", False))

    def _spawn_boss(self, offscreen_from: Optional[Vector2] = None, sprite_override: Optional[pygame.Surface] = None) -> Optional[Vehicle]:
        # Spawn a boss vehicle that is dramatically tougher and fights everyone.
        sprite: pygame.Surface
        if sprite_override is not None:
            sprite = sprite_override.convert_alpha() if hasattr(sprite_override, "convert_alpha") else sprite_override
        elif getattr(self, "boss_sprites", []):
            sprite = random.choice(self.boss_sprites)
        else:
            # Fallback: upscale a normal sprite so bosses still work without assets.
            base = random.choice(self.vehicle_sprites)
            sprite = pygame.transform.smoothscale(base, (int(base.get_width() * 1.18), int(base.get_height() * 1.18))).convert_alpha()

        special = BOSS_SPECIAL
        strength = random.uniform(1.00, 1.30)
        # Spawn position (prefer off-screen relative to the camera/actor)
        if offscreen_from is None:
            pos = self._rand_in_arena(margin=280.0)
        else:
            center = Vector2(offscreen_from)
            min_offscreen = 1050.0
            for _ in range(120):
                pos = self._rand_in_arena(margin=280.0)
                if (pos - center).length() >= min_offscreen and self._spot_ok(pos, 70):
                    break
            else:
                pos = self._rand_in_arena(margin=280.0)

        angle_deg = random.uniform(0, 360)
        boss = Vehicle(self.next_vehicle_id, sprite, pos, angle_deg, special, strength, is_boss=True, hp_mult=10.0)
        self.next_vehicle_id += 1
        self.vehicles.append(boss)
        return boss

    def _request_boss_spawn(self, ref_pos: Vector2):
        # Limit active bosses for performance/readability. Queue if we're already at limit.
        if self._active_boss_count() < int(getattr(self, "boss_active_limit", 2)):
            self._spawn_boss(offscreen_from=ref_pos)
        else:
            self.boss_spawn_queue.append(random.uniform(0.8, 1.6))
            self.boss_spawn_queue.sort()

    def _spot_ok(self, pos: Vector2, min_dist: float) -> bool:
        for p in self.props:
            if p.alive and (p.pos - pos).length_squared() < (p.r + min_dist)**2:
                return False
        for v in self.vehicles:
            if v.alive and (v.pos - pos).length_squared() < (v.radius + min_dist)**2:
                return False
        return True

    def _ensure_vehicle_cap(self, initial: bool = False):
        # Cap applies to "normal" vehicles. Bosses are additive encounters.
        desired = VEHICLE_CAP_MAX
        alive_norm = [v for v in self.vehicles if v.alive and not getattr(v, "is_boss", False)]
        while len(alive_norm) < desired:
            # spawn new (off-screen from controlled if possible)
            cam_center = self._camera_center()
            self._spawn_vehicle(offscreen_from=cam_center)
            alive_norm = [v for v in self.vehicles if v.alive and not getattr(v, "is_boss", False)]
            if initial and len(alive_norm) >= VEHICLE_CAP_MIN:
                break

    def _camera_center(self) -> Vector2:
        v = self._get_controlled()
        if v and v.alive:
            return Vector2(v.pos)
        # fallback: center of world
        return Vector2(WORLD_W/2, WORLD_H/2)

    def play_sfx(self, snd: Optional[pygame.mixer.Sound], pos: Optional[Vector2] = None, base_vol: float = 1.0):
        """Play a sound with simple positional attenuation.

        - If `pos` is off-screen relative to the current camera, volume is reduced.
        - Volume also falls off gently with distance from the camera center.
        """
        if (not snd) or (not self.audio_ok):
            return

        vol = float(base_vol)

        if pos is not None:
            cam = self._camera_center()
            dist = (Vector2(pos) - cam).length()

            # Gentle distance falloff: full volume near camera; fade out over ~2400px.
            vol *= clamp(1.0 - max(0.0, dist - 200.0) / 2400.0, 0.0, 1.0)

            # Off-screen penalty.
            sp = self.world_to_screen(Vector2(pos), cam)
            if sp.x < 0 or sp.x > WIDTH or sp.y < 0 or sp.y > HEIGHT:
                vol *= 0.18

        vol = clamp(vol, 0.0, 1.0)

        try:
            ch = snd.play()
            if ch is not None:
                ch.set_volume(vol)
        except Exception:
            pass

    def honk(self):
        v = self._get_controlled()
        if self.snd_horn:
            self.play_sfx(self.snd_horn, v.pos if v else None, base_vol=0.55)

    def _get_controlled(self) -> Optional[Vehicle]:
        if self.controlled_id is None:
            return None
        for v in self.vehicles:
            if v.id == self.controlled_id:
                return v
        return None

    def _set_controlled(self, vid: Optional[int]):
        # set AI flags
        for v in self.vehicles:
            v.ai = True
        self.controlled_id = vid
        v = self._get_controlled()
        if v:
            v.ai = False
        if self.snd_switch:
            self.play_sfx(self.snd_switch, None, base_vol=0.55)

    def _visible_vehicle_ids(self, cam: Vector2) -> List[int]:
        rect = pygame.Rect(0, 0, WIDTH, HEIGHT).inflate(220, 220)
        ids = []
        for v in self.vehicles:
            if not v.alive:
                continue
            sp = self.world_to_screen(v.pos, cam)
            if rect.collidepoint(int(sp.x), int(sp.y)):
                ids.append(v.id)
        return ids

    def cycle_control(self, backwards: bool = False):
        cam = self._camera_center()
        vis = self._visible_vehicle_ids(cam)
        if not vis:
            return
        if self.controlled_id not in vis:
            self._set_controlled(vis[0])
            return
        idx = vis.index(self.controlled_id)
        idx = (idx - 1) % len(vis) if backwards else (idx + 1) % len(vis)
        self._set_controlled(vis[idx])

    def pick_vehicle_at_mouse(self, mouse_pos: Tuple[int,int]) -> bool:
        """Pick a vehicle under the mouse and switch control.

        Returns True if control changed (used to avoid firing on the selection click).
        """
        cam = self._camera_center()
        mpos = Vector2(mouse_pos)
        best = None
        best_d2 = 1e18
        for v in self.vehicles:
            if not v.alive:
                continue
            sp = self.world_to_screen(v.pos, cam)
            d2 = (sp - mpos).length_squared()
            if d2 < (v.radius * 1.1)**2 and d2 < best_d2:
                best = v
                best_d2 = d2
        if best and best.id != self.controlled_id:
            self._set_controlled(best.id)
            return True
        return False

    # --- Combat --------------------------------------------------------------
    def _fire_mg(self, v: Vehicle, dt: float, target: Optional[Vector2] = None):
        if v.mg_cooldown > 0:
            return
        v.mg_cooldown = 0.09

        # Base aim direction (degrees). If a target is provided, bias shots toward it.
        base_angle = float(v.angle)
        if target is not None:
            aim = (target - v.pos)
            if aim.length_squared() > 1e-6:
                base_angle = float(angle_to(aim))

        spread = random.uniform(-4.0, 4.0)
        rad = math.radians(base_angle + spread)
        dirv = Vector2(math.cos(rad), -math.sin(rad))

        speed = 820
        pos = v.pos + dirv * (v.radius + 8)
        vel = dirv * speed + v.vel * 0.35
        self.projectiles.append(Projectile("bullet", pos, vel, v.id, damage=7.0 * v.dmg_mult, ttl=1.4, radius=2.0))

        # muzzle flash + sound
        self._spawn_sparks(pos, 2)
        self.play_sfx(self.snd_mg, v.pos, base_vol=0.35)

    def _fire_special(self, v: Vehicle, target_pos: Optional[Vector2] = None):
        fire_special(self, v, target_pos)

    # --- Effects

    # --- Effects -------------------------------------------------------------
    def _spawn_explosion(self, pos: Vector2, radius: float, dmg: float, owner_id: Optional[int] = None):
        self.explosions.append(Explosion(Vector2(pos), radius, dmg, ttl=0.12, owner_id=owner_id))
        self._spawn_smoke(pos, int(radius * 0.55))
        if self.snd_expl:
            self.play_sfx(self.snd_expl, pos, base_vol=0.75)

    def _spawn_smoke(self, pos: Vector2, count: int):
        for _ in range(count):
            ang = random.random() * math.tau
            spd = random.uniform(30, 220)
            vel = Vector2(math.cos(ang), math.sin(ang)) * spd
            ttl = random.uniform(0.4, 1.1)
            size = random.uniform(2.0, 5.0)
            col = (random.randint(70, 120), random.randint(60, 90), random.randint(50, 80))
            self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=1))

    def _spawn_black_smoke_light(self, pos: Vector2, count: int = 1):
        """Light, sooty smoke used for smoldering props (destructible_objects)."""
        for _ in range(max(1, int(count))):
            # gentle upward drift with a bit of horizontal wander
            vel = Vector2(random.uniform(-22, 22), random.uniform(-55, -18))
            ttl = random.uniform(0.9, 1.8)
            size = random.uniform(2.5, 6.5)
            g = random.randint(10, 30)
            col = (g, g, g)
            self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=1))

    def _spawn_sparks(self, pos: Vector2, count: int):
        for _ in range(count):
            ang = random.random() * math.tau
            spd = random.uniform(120, 520)
            vel = Vector2(math.cos(ang), math.sin(ang)) * spd
            ttl = random.uniform(0.15, 0.5)
            size = random.uniform(1.5, 3.2)
            col = (random.randint(190, 255), random.randint(120, 210), random.randint(10, 60))
            self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=1))

    def _spawn_tracer(self, a: Vector2, b: Vector2, color: Tuple[int, int, int] = (255, 220, 120), ttl: float = 0.18, steps: int = 12):
        # thin line of particles
        steps = max(4, int(steps))
        for i in range(steps):
            t = i / (steps - 1)
            p = a.lerp(b, t)
            vel = Vector2(random.uniform(-30, 30), random.uniform(-30, 30))
            self.particles.append(Particle(p, vel, ttl=ttl, size=1.6, color=color, life=ttl, layer=1))

    def _spawn_emp(self, pos: Vector2):
        for _ in range(80):
            ang = random.random() * math.tau
            spd = random.uniform(80, 360)
            vel = Vector2(math.cos(ang), math.sin(ang)) * spd
            ttl = random.uniform(0.25, 0.7)
            size = random.uniform(1.0, 2.6)
            col = (random.randint(90, 130), random.randint(160, 220), random.randint(210, 255))
            self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=1))


    def _spawn_flames(self, pos: Vector2, base_vel: Vector2, count: int):
        """Flame particles used for burning vehicles."""
        wind = Vector2(getattr(self, "wind_vec", Vector2(0, 0)))
        for _ in range(count):
            ang = random.random() * math.tau
            spd = random.uniform(40, 180)
            vel = Vector2(math.cos(ang), math.sin(ang)) * spd - base_vel * random.uniform(0.05, 0.18) + wind * random.uniform(0.08, 0.18)
            ttl = random.uniform(0.18, 0.45)
            size = random.uniform(2.0, 4.8)
            if random.random() < 0.55:
                col = (255, random.randint(150, 205), random.randint(40, 90))
            else:
                col = (255, random.randint(190, 240), random.randint(90, 140))
            self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=1))

    def _update_burning(self, v: Vehicle, dt: float):
        """Vehicles at <=10% HP ignite and continue burning until destroyed."""
        if (not getattr(v, "burning", False)) or (not v.alive):
            return
        burn_src = getattr(v, "burn_source_id", None)
        burn_dps = 0.008 * v.max_hp  # 0.8% max HP per second
        v.take_damage(burn_dps * dt, attacker_id=burn_src)

        frac = clamp(v.hp / max(1.0, v.max_hp), 0.0, 1.0)
        intensity = clamp(1.0 + (1.0 - frac) * 1.35, 1.0, 2.35)

        v.burn_emit_accum = float(getattr(v, "burn_emit_accum", 0.0)) + dt * (18.0 * intensity)
        while v.burn_emit_accum >= 1.0:
            v.burn_emit_accum -= 1.0
            jitter = Vector2(random.uniform(-6, 6), random.uniform(-6, 6))
            self._spawn_flames(v.pos + jitter, v.vel, count=1)

        if random.random() < dt * (2.8 * intensity):
            self._spawn_smoke(v.pos, count=1)


    def _add_tire_mark(self, a: Vector2, b: Vector2, width: int = 3):
        ttl = 4.2
        self.tire_marks.append(TireMark(Vector2(a), Vector2(b), int(width), ttl=ttl, life=ttl, color=(28, 22, 16)))
        # keep bounded for performance
        if len(self.tire_marks) > 2200:
            del self.tire_marks[:200]

    def _spawn_dust(self, v: Vehicle, wl: Vector2, wr: Vector2, speed: float):
        # Dust puffs kick up from rear wheels.
        base = (wl + wr) * 0.5
        # jitter around the wheels, slightly behind motion
        jitter = Vector2(random.uniform(-10, 10), random.uniform(-10, 10))
        pos = base + jitter
        # bias dust backward relative to current velocity
        back = (-v.vel * 0.22) if v.vel.length_squared() > 1.0 else (-v.forward() * 28.0)
        vel = back + Vector2(random.uniform(-40, 40), random.uniform(-40, 40))
        ttl = random.uniform(0.35, 0.75)
        size = random.uniform(2.0, 4.0)
        # warm dusty palette
        col = (random.randint(110, 150), random.randint(90, 125), random.randint(70, 105))
        self.particles.append(Particle(Vector2(pos), vel, ttl, size, col, life=ttl, layer=0))

    def _emit_dust_and_tracks(self, v: Vehicle, throttle: float, turn: float, braking: bool, dt: float):
        speed = v.vel.length()
        wl, wr = v.wheel_points()

        # Tire marks: mostly when turning hard, braking, or accelerating at speed.
        leaving = (speed > 155.0) and (abs(turn) > 0.28 or braking or abs(throttle) > 0.75)
        if leaving:
            if (wl - v.last_wheel_l).length_squared() > 6.0:
                self._add_tire_mark(v.last_wheel_l, wl, width=3)
            if (wr - v.last_wheel_r).length_squared() > 6.0:
                self._add_tire_mark(v.last_wheel_r, wr, width=3)

        # Always update wheel history to prevent long "teleport" lines later.
        v.last_wheel_l = Vector2(wl)
        v.last_wheel_r = Vector2(wr)

        # Dust trails: when moving at speed. Throttle/turn/brake increase emission.
        if speed > 85.0:
            rate = (speed / 150.0)
            if abs(throttle) > 0.15:
                rate *= 1.25
            if abs(turn) > 0.35 or braking:
                rate *= 1.55
            if getattr(v, "turbo_active", False):
                rate *= 2.05

            # particles per second
            v.dust_accum += dt * rate * 18.0
            v.dust_accum = min(v.dust_accum, 6.0)

            while v.dust_accum >= 1.0:
                v.dust_accum -= 1.0
                self._spawn_dust(v, wl, wr, speed)
        else:
            v.dust_accum = 0.0

    def _draw_particles(self, cam_center: Vector2, layer: int):
        if not self.particles:
            return
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for pa in self.particles:
            if pa.layer != layer:
                continue
            life = pa.life if pa.life > 0 else max(pa.ttl, 0.001)
            alpha = int(255 * clamp(pa.ttl / life, 0.0, 1.0))
            if layer == 0:
                alpha = int(alpha * 0.55)  # dust should be subtler
            if alpha <= 0:
                continue
            sp = self.world_to_screen(pa.pos, cam_center)
            pygame.draw.circle(surf, (*pa.color, alpha), (int(sp.x), int(sp.y)), max(1, int(pa.size)))
        self.screen.blit(surf, (0, 0))


    # --- Sandstorm FX --------------------------------------------------------
    def _make_dust_cloud_surface(self, size: int) -> pygame.Surface:
        """Procedurally generate a natural-looking, pixel-noise dust cloud.

        Goals:
        - No "square" overlay artifacts (keep per-pixel alpha; avoid Surface.set_alpha()).
        - Organic shapes (radial falloff + fractal/value noise).
        - Subtle pixel/noise texture so it reads as sand/dust, not smoke.
        """
        # Build at a smaller resolution then upscale for cheap softness.
        base = int(clamp(size * 0.32, 72, 190))
        s = pygame.Surface((base, base), pygame.SRCALPHA)

        # Small lattice for value noise (bilinear interpolation).
        grid_n = 17  # (grid_n x grid_n) random values
        grid = [[random.random() for _ in range(grid_n)] for _ in range(grid_n)]

        def lerp1(a: float, b: float, t: float) -> float:
            return a + (b - a) * t

        def smoothstep(t: float) -> float:
            return t * t * (3.0 - 2.0 * t)

        def vnoise(x: float, y: float) -> float:
            # x,y in [0,1]
            gx = x * (grid_n - 1)
            gy = y * (grid_n - 1)
            x0 = int(gx)
            y0 = int(gy)
            x1 = min(x0 + 1, grid_n - 1)
            y1 = min(y0 + 1, grid_n - 1)
            tx = smoothstep(gx - x0)
            ty = smoothstep(gy - y0)
            a = lerp1(grid[y0][x0], grid[y0][x1], tx)
            b = lerp1(grid[y1][x0], grid[y1][x1], tx)
            return lerp1(a, b, ty)

        def fbm(x: float, y: float) -> float:
            # 3-octave fractal noise
            f = 0.0
            amp = 0.60
            freq = 1.0
            for _ in range(3):
                f += vnoise((x * freq) % 1.0, (y * freq) % 1.0) * amp
                amp *= 0.55
                freq *= 2.05
            return f

        cx = (base - 1) * 0.5
        cy = (base - 1) * 0.5
        inv = 1.0 / max(1.0, cx)

        # Draw per-pixel alpha.
        for y in range(base):
            ny = (y - cy) * inv
            for x in range(base):
                nx = (x - cx) * inv
                r = math.sqrt(nx * nx + ny * ny)

                # Radial falloff gives us a true cloud footprint (no square bounds).
                if r > 1.05:
                    continue

                u = (x / (base - 1)) * 1.12
                v = (y / (base - 1)) * 1.00
                n = fbm(u, v)

                fall = clamp(1.0 - r, 0.0, 1.0)
                d = (n * 0.78) + (fall * 0.78) - 0.55
                if d <= 0.0:
                    continue

                a = clamp(d * 2.55, 0.0, 1.0)
                a = a ** 1.45
                alpha = int(255 * a)

                rr = 178 + int(26 * n) + random.randint(-4, 4)
                gg = 156 + int(22 * n) + random.randint(-4, 4)
                bb = 110 + int(18 * n) + random.randint(-4, 4)

                edge = clamp(0.55 + fall * 0.65, 0.0, 1.0)
                rr = int(rr * edge)
                gg = int(gg * edge)
                bb = int(bb * edge)

                # Gritty dither in denser regions.
                if alpha > 40 and random.random() < 0.06:
                    alpha = min(255, alpha + random.randint(18, 55))

                s.set_at((x, y), (clamp(rr, 0, 255), clamp(gg, 0, 255), clamp(bb, 0, 255), alpha))

        # Soft upscale, then sprinkle a few pixel specks to keep it "sandy".
        out = pygame.transform.smoothscale(s, (size, size))

        specks = max(28, size // 10)
        for _ in range(specks):
            px = random.randint(0, size - 1)
            py = random.randint(0, size - 1)
            a = random.randint(10, 55)
            out.fill((210, 190, 140, a), pygame.Rect(px, py, random.choice([1, 1, 2]), 1))

        return out

    def _init_sandstorm(self):
        self.sandstorm_clouds.clear()
        self.sandstorm_debris.clear()

        # Clouds: a few large, slow layers
        for i in range(7):
            sz = random.randint(240, 560)
            surf = self._make_dust_cloud_surface(sz)
            alpha = random.randint(22, 62) if i < 3 else random.randint(40, 92)
            # IMPORTANT: avoid Surface.set_alpha() here; it can force a uniform alpha over the whole rect
            # on some pygame backends, which reads as a "square" cloud. Multiply alpha into pixels instead.
            surf = surf.convert_alpha()
            dtc = getattr(self, 'dust_tint', (255, 255, 255))
            surf.fill((int(dtc[0]), int(dtc[1]), int(dtc[2]), alpha), special_flags=pygame.BLEND_RGBA_MULT)

            scale = random.uniform(0.85, 1.20)
            pos = Vector2(random.uniform(-sz * 0.3, WIDTH + sz * 0.3),
                          random.uniform(-sz * 0.3, HEIGHT + sz * 0.3))

            # Parallax: back layers move slower
            par = 0.10 + (i / 10.0)
            vel = Vector2(1, 0) * (self.wind_speed * par)

            self.sandstorm_clouds.append(SandCloud(pos=pos, vel=vel, surf=surf, alpha=alpha, scale=scale))

        # Debris: many tiny pixels streaking in the wind
        for _ in range(220):
            x = random.uniform(0, WIDTH)
            y = random.uniform(0, HEIGHT)
            sp = random.uniform(0.65, 1.65)
            size = 1 if random.random() < 0.78 else 2
            self.sandstorm_debris.append((x, y, sp, size))

    def _update_sandstorm(self, dt: float):
        self.t_sim += dt

        # Evolving wind (mostly left->right, with gusting)
        gust = 0.60 + 0.40 * math.sin(self.t_sim * 0.38) + 0.20 * math.sin(self.t_sim * 1.05 + 1.7)
        gust = clamp(gust, 0.25, 1.15)

        # slow drift in direction
        self.wind_angle += (math.sin(self.t_sim * 0.16) * 0.0015) + random.uniform(-0.010, 0.010) * dt
        self.wind_angle = clamp(self.wind_angle, -0.70, 0.70)

        base_speed = 175.0
        self.wind_speed = clamp(base_speed + 65.0 * gust, 110.0, 285.0)

        wdir = Vector2(math.cos(self.wind_angle), math.sin(self.wind_angle) * 0.55)
        if wdir.length_squared() > 1e-6:
            wdir = wdir.normalize()
        else:
            wdir = Vector2(1, 0)

        self.wind = wdir * self.wind_speed

        # Move clouds
        for i, c in enumerate(self.sandstorm_clouds):
            par = 0.10 + (i / 10.0)
            c.vel = self.wind * par
            c.pos += c.vel * dt

            sz = c.surf.get_width()
            m = sz * 0.40
            if c.pos.x > WIDTH + m:
                c.pos.x = -m
                c.pos.y = random.uniform(-m, HEIGHT + m)
            elif c.pos.x < -m:
                c.pos.x = WIDTH + m
                c.pos.y = random.uniform(-m, HEIGHT + m)

            if c.pos.y > HEIGHT + m:
                c.pos.y = -m
            elif c.pos.y < -m:
                c.pos.y = HEIGHT + m

        # Move debris (screen-space pixels)
        if self.sandstorm_debris:
            nx = []
            for (x, y, sp, size) in self.sandstorm_debris:
                x += self.wind.x * dt * sp
                y += self.wind.y * dt * sp
                # slight turbulence
                x += math.sin(self.t_sim * (1.4 + sp) + y * 0.01) * dt * 18.0
                y += math.cos(self.t_sim * (1.1 + sp) + x * 0.01) * dt * 10.0

                if x < -8:
                    x = WIDTH + 8
                    y = random.uniform(0, HEIGHT)
                elif x > WIDTH + 8:
                    x = -8
                    y = random.uniform(0, HEIGHT)

                if y < -8:
                    y = HEIGHT + 8
                elif y > HEIGHT + 8:
                    y = -8

                nx.append((x, y, sp, size))
            self.sandstorm_debris = nx

    def _draw_sandstorm(self, front: bool):
        # Back pass: lighter; Front pass: denser.
        if not self.sandstorm_clouds:
            return

        # Clouds
        if front:
            rng = range(3, len(self.sandstorm_clouds))
        else:
            rng = range(0, min(3, len(self.sandstorm_clouds)))

        for i in rng:
            c = self.sandstorm_clouds[i]
            r = c.surf.get_rect(center=(int(c.pos.x), int(c.pos.y)))
            self.screen.blit(c.surf, r.topleft)

        # Debris pixels (mostly in front so it reads as flying grit)
        if front and self.sandstorm_debris:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for (x, y, sp, size) in self.sandstorm_debris:
                # speed -> alpha; keep subtle
                a = int(clamp(55 + sp * 35, 55, 125))
                dtc = getattr(self, 'dust_tint', (210, 190, 140))
                col = (int(dtc[0]), int(dtc[1]), int(dtc[2]), a)
                overlay.fill(col, pygame.Rect(int(x), int(y), int(size), int(size)))
                # occasional trailing pixel
                if size == 1 and random.random() < 0.25:
                    overlay.fill((210, 190, 140, int(a * 0.55)), pygame.Rect(int(x - 1), int(y), 1, 1))
            self.screen.blit(overlay, (0, 0))

    def _spawn_shoot_dust(self, origin: Vector2, dirv: Vector2, amount: int = 8):
        # Directional dust plume that follows the firing direction, plus wind drift.
        if amount <= 0:
            return
        if len(self.particles) > 4600:
            return

        if dirv.length_squared() > 1e-6:
            d = dirv.normalize()
        else:
            d = Vector2(1, 0)

        # Use the sandstorm wind as a subtle bias in world-space.
        w = Vector2(getattr(self, "wind", Vector2(0, 0))) * 0.28

        # Perpendicular for spread
        p = Vector2(-d.y, d.x)

        for _ in range(amount):
            j = p * random.uniform(-10.0, 10.0) + d * random.uniform(-4.0, 10.0)
            pos = Vector2(origin) + j
            vel = d * random.uniform(90.0, 260.0) + w + Vector2(random.uniform(-55, 55), random.uniform(-55, 55))
            ttl = random.uniform(0.18, 0.42)
            size = random.uniform(1.4, 2.9)
            col = (random.randint(140, 185), random.randint(120, 160), random.randint(85, 120))
            self.particles.append(Particle(pos, vel, ttl, size, col, life=ttl, layer=0))


    # --- Simulation ----------------------------------------------------------
    def world_to_screen(self, world_pos: Vector2, cam: Vector2) -> Vector2:
        return Vector2(world_pos.x - cam.x + WIDTH / 2, world_pos.y - cam.y + HEIGHT / 2)

    def screen_to_world(self, screen_pos: Vector2, cam: Vector2) -> Vector2:
        return Vector2(screen_pos.x + cam.x - WIDTH / 2, screen_pos.y + cam.y - HEIGHT / 2)


    def _handle_projectile_hits(self, pr: Projectile):
        # arena bounds (circular fire ring)
        if (pr.pos - ARENA_CENTER).length_squared() > (ARENA_RADIUS + 80.0) ** 2:
            pr.alive = False
            return

        # stationary traps
        if pr.kind in ("mine", "spike"):
            # mines arm after a short delay via ttl check
            armed = True
            if pr.kind == "mine":
                armed = pr.ttl < 9.4
            if not armed:
                return
            for v in self.vehicles:
                if not v.alive or v.id == pr.owner_id:
                    continue
                if (v.pos - pr.pos).length_squared() <= (v.radius + pr.radius + 2) ** 2:
                    if pr.kind == "mine":
                        self._spawn_explosion(pr.pos, radius=140, dmg=pr.damage, owner_id=pr.owner_id)
                    else:
                        v.take_damage(pr.damage, attacker_id=pr.owner_id)
                        v.stun_timer = max(v.stun_timer, 0.65)
                        self._spawn_sparks(pr.pos, 12)
                    pr.alive = False
                    return
            return

        # markers / timed
        if pr.kind in ("mortar_marker", "nuke_marker"):
            return

        # collision with props
        for p in self.props:
            if not p.alive:
                continue
            if (p.pos - pr.pos).length_squared() <= (p.r + pr.radius) ** 2:
                p.take_damage(pr.damage)
                if pr.kind in ("rocket", "homing"):
                    self._spawn_explosion(pr.pos, radius=170, dmg=pr.damage, owner_id=pr.owner_id)
                elif pr.kind == "cluster":
                    # detonate into bomblets immediately
                    n = int(getattr(pr, "subcount", 6))
                    sd = float(getattr(pr, "subdamage", pr.damage * 0.7))
                    for _ in range(n):
                        ang = random.random() * math.tau
                        spd = random.uniform(220, 420)
                        vel = Vector2(math.cos(ang), math.sin(ang)) * spd + pr.vel * 0.25
                        b = Projectile("bomblet", Vector2(pr.pos), vel, pr.owner_id, damage=sd, ttl=random.uniform(0.55, 0.9), radius=3.0)
                        self.projectiles.append(b)
                    self._spawn_sparks(pr.pos, 18)
                elif pr.kind == "bomblet":
                    self._spawn_explosion(pr.pos, radius=120, dmg=pr.damage, owner_id=pr.owner_id)
                else:
                    self._spawn_sparks(pr.pos, 6)
                pr.alive = False
                return

        # collision with vehicles
        for v in self.vehicles:
            if not v.alive or v.id == pr.owner_id:
                continue
            if (v.pos - pr.pos).length_squared() <= (v.radius + pr.radius) ** 2:
                v.take_damage(pr.damage, attacker_id=pr.owner_id)
                if pr.kind in ("rocket", "homing"):
                    self._spawn_explosion(pr.pos, radius=190, dmg=pr.damage, owner_id=pr.owner_id)
                elif pr.kind == "cluster":
                    n = int(getattr(pr, "subcount", 6))
                    sd = float(getattr(pr, "subdamage", pr.damage * 0.7))
                    for _ in range(n):
                        ang = random.random() * math.tau
                        spd = random.uniform(220, 420)
                        vel = Vector2(math.cos(ang), math.sin(ang)) * spd + pr.vel * 0.25
                        b = Projectile("bomblet", Vector2(pr.pos), vel, pr.owner_id, damage=sd, ttl=random.uniform(0.55, 0.9), radius=3.0)
                        self.projectiles.append(b)
                    self._spawn_sparks(pr.pos, 18)
                elif pr.kind == "bomblet":
                    self._spawn_explosion(pr.pos, radius=120, dmg=pr.damage, owner_id=pr.owner_id)
                elif pr.kind == "water":
                    knock = float(getattr(pr, "knock", 115.0))
                    if pr.vel.length_squared() > 1e-6:
                        v.vel += pr.vel.normalize() * knock
                    self._spawn_sparks(pr.pos, 3)
                else:
                    self._spawn_sparks(pr.pos, 8)
                pr.alive = False
                return

    def _apply_explosions(self):
        if not self.explosions:
            return
        for ex in list(self.explosions):
            for v in self.vehicles:
                if not v.alive:
                    continue
                d = (v.pos - ex.pos).length()
                if d <= ex.radius:
                    dmg = ex.damage * (1.0 - d / ex.radius)
                    v.take_damage(dmg, attacker_id=ex.owner_id)
                    # knockback
                    if d > 0.5:
                        v.vel += (v.pos - ex.pos).normalize() * (220 * (1.0 - d / ex.radius))
            for p in self.props:
                if not p.alive:
                    continue
                d = (p.pos - ex.pos).length()
                if d <= ex.radius:
                    dmg = ex.damage * (1.0 - d / ex.radius)
                    p.take_damage(dmg)
            ex.ttl -= self.dt
            if ex.ttl <= 0:
                self.explosions.remove(ex)

    def _resolve_vehicle_prop_collisions(self):
        for v in self.vehicles:
            if not v.alive:
                continue
            for p in self.props:
                if not p.alive:
                    continue
                d = v.pos - p.pos
                dist = d.length()
                min_d = v.radius + p.r
                if dist < min_d and dist > 0.01:
                    push = (min_d - dist)
                    n = d / dist
                    v.pos += n * push
                    v.vel += n * (push * 6)
                    # mark as briefly blocked so AI can consider reversing to disengage
                    v._ai_blocked_timer = max(float(getattr(v, '_ai_blocked_timer', 0.0)), 0.45)
                    v._ai_blocked_normal = Vector2(n)

    def _resolve_vehicle_vehicle_collisions(self):
        alive = [v for v in self.vehicles if v.alive]
        for i in range(len(alive)):
            for j in range(i+1, len(alive)):
                a = alive[i]; b = alive[j]
                d = a.pos - b.pos
                dist = d.length()
                min_d = a.radius + b.radius
                if dist < min_d and dist > 0.01:
                    push = (min_d - dist) * 0.5
                    n = d / dist
                    a.pos += n * push
                    b.pos -= n * push
                    # bounce
                    a.vel += n * (push * 7)
                    b.vel -= n * (push * 7)


    def _ai_controls(self, v: Vehicle) -> Tuple[float, float, bool, bool, bool, Vector2]:
        """Arena-fighter AI.

        Design goals:
        - Drive primarily with forward + turning (minimal reversing).
        - Reverse only when a solid prop is blocking (recent collision) or explicit unstuck.
        - Fire using turret-like aiming (can shoot without facing the target).
        """
        dt = float(getattr(self, "dt", 0.016))

        # persistent per-vehicle AI memory
        if not hasattr(v, "_ai_orbit_dir"):
            v._ai_orbit_dir = random.choice([-1.0, 1.0])  # clockwise/counter-clockwise preference
        if not hasattr(v, "_ai_last_pos"):
            v._ai_last_pos = Vector2(v.pos)
        if not hasattr(v, "_ai_stuck_t"):
            v._ai_stuck_t = 0.0
        if not hasattr(v, "_ai_unstuck_t"):
            v._ai_unstuck_t = 0.0
            v._ai_unstuck_turn = 0.0

        # decay "blocked" timer (set by prop collisions)
        if getattr(v, "_ai_blocked_timer", 0.0) > 0.0:
            v._ai_blocked_timer = max(0.0, float(v._ai_blocked_timer) - dt)

        # --- Target selection (vehicles) ------------------------------------
        target_v: Optional[Vehicle] = None

        # if threatened, bias toward attacker
        tid = getattr(v, "threat_id", None)
        if tid is not None:
            for ov in self.vehicles:
                if ov.alive and ov.id == tid:
                    target_v = ov
                    break

        if target_v is None:
            best = 1e18
            for ov in self.vehicles:
                if (not ov.alive) or (ov.id == v.id):
                    continue
                d2 = (ov.pos - v.pos).length_squared()
                if d2 < best:
                    best = d2
                    target_v = ov

        # --- Target selection (props) ---------------------------------------
        # Opportunistically shoot destructible props if they're near / blocking.
        prop_target: Optional[Prop] = None
        prop_best = 1e18
        forward = v.forward()
        for p in self.props:
            if not p.alive:
                continue
            d2 = (p.pos - v.pos).length_squared()
            if d2 > 720.0 * 720.0:
                continue
            to_p = (p.pos - v.pos)
            distp = math.sqrt(max(1e-6, d2))
            in_front = (to_p / distp).dot(forward) > 0.35
            collide = distp < (v.radius + p.r + 10.0)
            score = d2 * (0.18 if collide else 1.0)
            if (in_front or collide) and score < prop_best:
                prop_best = score
                prop_target = p

        if target_v is None and prop_target is None:
            return 0.0, 0.0, False, False, False, Vector2(v.pos)

        # Choose an interest point. Vehicles are primary; props can override if very close/blocking.
        target_pos = Vector2(target_v.pos) if target_v is not None else Vector2(prop_target.pos)
        if prop_target is not None and target_v is not None:
            d_prop = (prop_target.pos - v.pos).length()
            d_veh = (target_v.pos - v.pos).length()
            if d_prop < 240.0 or (d_prop < 480.0 and d_prop < d_veh * 0.60):
                target_pos = Vector2(prop_target.pos)

        to_t = target_pos - v.pos
        dist = max(1.0, to_t.length())

        # --- Steering --------------------------------------------------------
        # Orbit slightly when very close to avoid face-planting and to keep motion fluid.
        desired_vec = Vector2(to_t)
        if dist < 220.0 and desired_vec.length_squared() > 1e-6:
            inward_to_target = desired_vec.normalize()
            tangent = Vector2(-inward_to_target.y, inward_to_target.x) * float(v._ai_orbit_dir)
            desired_vec = tangent * 1.0 + inward_to_target * 0.35

        desired_ang = angle_to(desired_vec)
        aerr = wrap_angle_deg(desired_ang - v.angle)

        # IMPORTANT: Vehicle.update_physics uses `angle -= turn * turn_rate * dt`,
        # so we invert the error sign to turn in the correct direction.
        turn = clamp((-aerr) / 30.0, -1.0, 1.0)

        # Throttle: prefer forward. Slow down when hard-turning or too close.
        throttle = 1.0
        braking = False
        aa = abs(aerr)

        if aa > 120.0:
            throttle = 0.45
        elif aa > 75.0:
            throttle = 0.65

        if dist < 220.0:
            throttle = min(throttle, 0.70)
        if dist < 140.0:
            throttle = min(throttle, 0.55)
            # only brake if we're about to smash at high speed
            if v.vel.length() > 160.0:
                braking = True
                throttle = min(throttle, 0.35)

        # --- Arena ring bias (keep battles inside) --------------------------
        radial = v.pos - ARENA_CENTER
        dc = radial.length()
        safe = ARENA_RADIUS - (v.radius + 260.0)
        warn = ARENA_RADIUS - (v.radius + 150.0)
        rim  = ARENA_RADIUS - (v.radius + 40.0)

        # Pull aim point inward if the target is too close to the rim (prevents edge-chasing).
        t_rad = target_pos - ARENA_CENTER
        t_dc = t_rad.length()
        if t_dc > warn:
            if t_dc > 1e-6:
                target_pos = ARENA_CENTER + (t_rad / t_dc) * warn
            else:
                target_pos = Vector2(ARENA_CENTER)

        if dc > safe and (ARENA_CENTER - v.pos).length_squared() > 1e-6:
            inward = (ARENA_CENTER - v.pos).normalize()
            tangent = Vector2(-inward.y, inward.x) * float(v._ai_orbit_dir)

            # Blend inward bias so bots naturally circulate inside the ring.
            ring_vec = desired_vec * 0.55 + inward * 1.10 + tangent * 0.55
            ring_ang = angle_to(ring_vec)
            ring_err = wrap_angle_deg(ring_ang - v.angle)
            ring_turn = clamp((-ring_err) / 20.0, -1.0, 1.0)

            w = clamp((dc - safe) / max(1.0, (warn - safe)), 0.0, 1.0)
            turn = clamp(turn * (1.0 - w) + ring_turn * w, -1.0, 1.0)

            throttle = min(throttle, 0.72 - 0.32 * w)

            # Extremely close to the rim: brake + steer inward (no auto-reverse here).
            if dc > rim:
                braking = True
                c_ang = angle_to(ARENA_CENTER - v.pos)
                c_err = wrap_angle_deg(c_ang - v.angle)
                turn = clamp((-c_err) / 18.0, -1.0, 1.0)
                throttle = min(throttle, 0.40)

        # --- Stuck detection + recovery -------------------------------------
        moved = (v.pos - v._ai_last_pos).length()
        v._ai_last_pos = Vector2(v.pos)
        speed = v.vel.length()

        trying = throttle > 0.55
        hugging_ring = dc > (ARENA_RADIUS - (v.radius + 36.0))
        if (speed < 18.0 and moved < 1.6 and trying) or hugging_ring:
            v._ai_stuck_t += dt
        else:
            v._ai_stuck_t = max(0.0, v._ai_stuck_t - dt * 0.65)

        if v._ai_unstuck_t <= 0.0 and v._ai_stuck_t > 0.95:
            v._ai_unstuck_t = 0.65
            v._ai_stuck_t = 0.0
            v._ai_unstuck_turn = random.choice([-1.0, 1.0]) * random.uniform(0.70, 1.0)

        if v._ai_unstuck_t > 0.0:
            v._ai_unstuck_t = max(0.0, v._ai_unstuck_t - dt)
            braking = False

            # Reverse ONLY if we recently collided with a prop (solid blocker).
            if getattr(v, "_ai_blocked_timer", 0.0) > 0.0:
                throttle = -0.70
            else:
                throttle = 0.55

            # Bias turn back toward center, but add randomness.
            if (ARENA_CENTER - v.pos).length_squared() > 1e-6:
                des_c = angle_to(ARENA_CENTER - v.pos)
                aerr_c = wrap_angle_deg(des_c - v.angle)
                turn = clamp((-aerr_c) / 22.0 + v._ai_unstuck_turn, -1.0, 1.0)
            else:
                turn = v._ai_unstuck_turn

        # --- Firing logic ----------------------------------------------------
        # Turret-like aiming: shooting does NOT require facing the target.
        fire_mg = dist < 820.0 and (random.random() < 0.80)

        # If a prop is directly in front / blocking, shoot it aggressively
        if prop_target is not None:
            to_p = prop_target.pos - v.pos
            dp = max(1.0, to_p.length())
            in_front = (to_p / dp).dot(v.forward()) > 0.35
            blocking = dp < (v.radius + prop_target.r + 26.0)
            if in_front or blocking:
                fire_mg = (random.random() < (0.92 if blocking else 0.70))
                target_pos = Vector2(prop_target.pos)

        # Specials: still frequent, but keep boss nuke rarer.
        fire_special = (dist < 720.0) and (random.random() < (0.10 if v.special == "nuke" else 0.24))

        # small random dodges for chaos (only if comfortably inside)
        if dc < safe - 140.0 and random.random() < 0.015:
            turn = clamp(turn + random.uniform(-0.50, 0.50), -1.0, 1.0)

        return throttle, turn, braking, fire_mg, fire_special, Vector2(target_pos)
    def update(self, dt: float):
        self.dt = dt
        self.fire_phase = float(getattr(self, 'fire_phase', 0.0)) + dt
        cam_center = self._camera_center()

        # day/night cycle progression (visual only)
        self.day_time = (self.day_time + dt) % max(1e-3, self.day_length)
        ph = self.day_time / max(1e-3, self.day_length)  # 0..1
        # daylight curve: 1 at noon, 0 at midnight, with smooth dawn/dusk
        daylight = 0.5 + 0.5 * math.sin(ph * math.tau)
        daylight = clamp((daylight - 0.05) / 0.95, 0.0, 1.0)
        self.night_factor = clamp(1.0 - daylight, 0.0, 1.0)

        self._update_sandstorm(dt)

        # enemy wave / boss progression
        self._update_waves(dt)
        self._update_powerups(dt)

        # environmental hazard: random prop detonation every 30 seconds
        self.env_boom_timer -= dt
        while self.env_boom_timer <= 0.0:
            self._detonate_random_prop()
            self.env_boom_timer += self.env_boom_interval

        # input for player
        keys = pygame.key.get_pressed()
        controlled = self._get_controlled()
        (mx, my), mouse_inside = self.window_to_virtual(pygame.mouse.get_pos())
        mouse = Vector2(mx, my)
        mouse_world = self.screen_to_world(mouse, cam_center)

        # Prevent accidental firing on the same click used to take control.
        self.mouse_select_cd = max(0.0, self.mouse_select_cd - dt)

        # Expire stale kill credit.
        for vv in self.vehicles:
            if vv.alive and getattr(vv, "last_hit_by", None) is not None:
                vv.last_hit_age = float(getattr(vv, "last_hit_age", 0.0)) + dt
                if vv.last_hit_age > 6.0:
                    vv.last_hit_by = None

        for v in self.vehicles:
            if not v.alive:
                continue

            # burning / stealth status
            self._update_burning(v, dt)
            if getattr(v, 'stealth_timer', 0.0) > 0.0:
                v.stealth_timer = max(0.0, v.stealth_timer - dt)

            # threat tracking (used for AI retargeting when someone shoots toward this vehicle)
            if getattr(v, 'threat_timer', 0.0) > 0.0:
                v.threat_timer = max(0.0, v.threat_timer - dt)
                if v.threat_timer <= 0.0:
                    v.threat_id = None

            if v.ai:
                throttle, turn, braking, fire_mg, fire_special, target_pos = self._ai_controls(v)
                v.update_physics(dt, throttle, turn, braking)
                self._emit_dust_and_tracks(v, throttle, turn, braking, dt)
                if fire_mg:
                    self._fire_mg(v, dt, target=target_pos)
                if fire_special:
                    self._fire_special(v, target_pos)
            else:
                throttle = 0.0
                if keys[pygame.K_w] or keys[pygame.K_UP]:
                    throttle += 1.0
                if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                    throttle -= 0.85
                turn = 0.0
                if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                    turn -= 1.0
                if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                    turn += 1.0
                braking = bool(keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL])
                turbo = bool(keys[pygame.K_LSHIFT])
                v.update_physics(dt, throttle, turn, braking, turbo=turbo)
                self._emit_dust_and_tracks(v, throttle, turn, braking, dt)

                # Fire (mouse): Left = machine gun, Right = special
                mb = pygame.mouse.get_pressed(3)
                if self.mouse_select_cd <= 0.0 and mouse_inside:
                    if mb[0]:
                        self._fire_mg(v, dt, target=mouse_world)
                    if mb[2]:
                        self._fire_special(v, mouse_world)

        # collisions
        self._resolve_vehicle_prop_collisions()
        self._resolve_vehicle_vehicle_collisions()
        self._enforce_arena_bounds()


        # projectiles update + hits
        for pr in list(self.projectiles):
            # homing steering
            if pr.kind == "homing" and getattr(pr, "target_id", None) is not None:
                tgt = next((x for x in self.vehicles if x.alive and x.id == pr.target_id), None)
                if tgt is not None:
                    to_t = (tgt.pos - pr.pos)
                    if to_t.length_squared() > 1e-6:
                        desired = to_t.normalize()
                        cur = pr.vel.normalize() if pr.vel.length_squared() > 1e-6 else desired
                        turn_rate = float(getattr(pr, "turn_rate", 6.0))
                        blend = clamp(turn_rate * dt, 0.0, 1.0)
                        new_dir = (cur.lerp(desired, blend)).normalize()
                        spd = max(180.0, pr.vel.length())
                        pr.vel = new_dir * spd

            pr.update(dt)

            # shoot-toward / near-miss detection: if someone fires toward a vehicle, it may retarget the shooter
            if pr.alive and pr.owner_id is not None and pr.kind in ("bullet", "rocket", "homing", "bomblet", "water", "cluster"):
                if pr.vel.length_squared() > 25.0:
                    ddir = pr.vel.normalize()
                    for vv in self.vehicles:
                        if (not vv.alive) or vv.id == pr.owner_id:
                            continue
                        rel = (vv.pos - pr.pos)
                        d2 = rel.length_squared()
                        if d2 > 650.0 * 650.0:
                            continue
                        if d2 < 1e-6:
                            continue
                        dist = math.sqrt(d2)
                        reln = rel / dist
                        # must be generally traveling toward the vehicle
                        if ddir.dot(reln) < 0.82:
                            continue
                        # perpendicular miss distance must be small (within a "lane" in front of the projectile)
                        miss = abs(rel.cross(ddir))
                        lane = max(26.0, vv.radius * 0.80)
                        if miss <= lane:
                            vv.threat_id = pr.owner_id
                            vv.threat_timer = max(float(getattr(vv, "threat_timer", 0.0)), 2.2)

            # timed detonations
            if pr.kind == "mortar_marker" and pr.ttl <= 0 and pr.alive:
                self._spawn_explosion(pr.pos, radius=210, dmg=pr.damage, owner_id=pr.owner_id)
                pr.alive = False

            if pr.kind == "nuke_marker" and pr.ttl <= 0 and pr.alive:
                self._spawn_explosion(pr.pos, radius=float(getattr(pr, "radius", 650.0)), dmg=pr.damage, owner_id=pr.owner_id)
                # extra smoke for spectacle
                self._spawn_smoke(pr.pos, 240)
                pr.alive = False

            if pr.kind == "cluster" and pr.ttl <= 0 and pr.alive:
                # burst into bomblets
                n = int(getattr(pr, "subcount", 6))
                sd = float(getattr(pr, "subdamage", pr.damage * 0.7))
                for _ in range(n):
                    ang = random.random() * math.tau
                    spd = random.uniform(220, 420)
                    vel = Vector2(math.cos(ang), math.sin(ang)) * spd + pr.vel * 0.25
                    b = Projectile("bomblet", Vector2(pr.pos), vel, pr.owner_id, damage=sd, ttl=random.uniform(0.55, 0.9), radius=3.0)
                    self.projectiles.append(b)
                self._spawn_sparks(pr.pos, 18)
                pr.alive = False

            if pr.kind == "bomblet" and pr.ttl <= 0 and pr.alive:
                self._spawn_explosion(pr.pos, radius=120, dmg=pr.damage, owner_id=pr.owner_id)
                pr.alive = False

            if pr.alive:
                self._handle_projectile_hits(pr)
            if not pr.alive:
                self.projectiles.remove(pr)

        # explosions
        self._apply_explosions()
        self._enforce_arena_bounds()

        # particles
        for pa in list(self.particles):
            pa.pos += pa.vel * dt
            pa.vel *= 0.92
            pa.ttl -= dt
            if pa.ttl <= 0:
                self.particles.remove(pa)

        # tire marks fade
        for tm in list(self.tire_marks):
            tm.ttl -= dt
            if tm.ttl <= 0:
                self.tire_marks.remove(tm)

                # cleanup destroyed props
        for p in list(self.props):
            if not p.alive:
                # Sprite props are the default. Avoid legacy geometric placeholders entirely.
                self._spawn_smoke(p.pos, 14)
                self._spawn_sparks(p.pos, 10)
                self.props.remove(p)

        # cleanup destroyed vehicles# cleanup destroyed vehicles
        for v in list(self.vehicles):
            if not v.alive:
                # Kill credit (UI/stat tracking only).
                if not getattr(v, "is_boss", False):
                    killer_id = getattr(v, "last_hit_by", None)
                    if killer_id is not None and killer_id != v.id:
                        self.kill_counts[killer_id] = int(self.kill_counts.get(killer_id, 0)) + 1

                self._spawn_explosion(v.pos, radius=240, dmg=95)
                self._spawn_sparks(v.pos, 26)

                # if controlled died, spawn a fresh player vehicle
                if self.controlled_id == v.id:
                    try:
                        self._spawn_player_vehicle()
                    except Exception:
                        self.controlled_id = None


                self.vehicles.remove(v)

    # --- Rendering -----------------------------------------------------------
    def _draw_fire_barrier(self, cam_center: Vector2):
        """Render a large fire ring around the arena (also the collision boundary)."""
        c = self.world_to_screen(ARENA_CENTER, cam_center)
        cx, cy = int(c.x), int(c.y)
        r = int(ARENA_RADIUS)

        # Glow pass (additive)
        glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flick = 0.5 + 0.5 * math.sin(self.fire_phase * 3.1)
        a1 = int(55 + 35 * flick)
        a2 = int(40 + 28 * (1.0 - flick))

        pygame.draw.circle(glow, (255, 90, 20, a1), (cx, cy), r, 34)
        pygame.draw.circle(glow, (255, 140, 40, a2), (cx, cy), r, 20)

        # Flame licks along the circumference (procedural waviness + flicker)
        step = 6  # degrees
        for deg in range(0, 360, step):
            ang = math.radians(deg)
            # two-frequency wave so it looks less uniform
            wv = (math.sin(self.fire_phase * 4.2 + ang * 7.0) * 10.0 +
                  math.sin(self.fire_phase * 2.3 + ang * 13.0) * 6.0)
            rr = r + int(wv)
            px = cx + int(math.cos(ang) * rr)
            py = cy + int(math.sin(ang) * rr)

            flick2 = 0.5 + 0.5 * math.sin(self.fire_phase * 7.0 + ang * 9.0)
            size = 4 + int(6 * flick2)
            aa = int(65 + 85 * flick2)
            # warm palette variation
            col = (255, int(120 + 80 * flick2), int(30 + 40 * flick2), aa)
            pygame.draw.circle(glow, col, (px, py), size)

            # outward little tongue
            out = Vector2(math.cos(ang), math.sin(ang))
            p2 = (px + int(out.x * (8 + size)), py + int(out.y * (8 + size)))
            pygame.draw.line(glow, (255, 170, 70, int(40 + 60 * flick2)), (px, py), p2, 2)

        self.screen.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # Core pass (non-additive so it stays readable)
        core = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(core, (255, 190, 90, 110), (cx, cy), r, 10)
        pygame.draw.circle(core, (255, 120, 40, 90), (cx, cy), r, 6)
        self.screen.blit(core, (0, 0))


    def _draw_day_night_and_headlights(self, cam_center: Vector2) -> None:
        """Apply dusk/night darkness overlay + vehicle headlights."""
        nf = float(getattr(self, "night_factor", 0.0))
        if nf <= 0.01:
            return

        # Darkness overlay (UI is drawn after this, so it stays readable).
        alpha_max = float(NIGHT_DARK_ALPHA_MAX)
        alpha = int(clamp(nf * alpha_max, 0.0, alpha_max))
        dark = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dark.fill((0, 0, 0, alpha))
        self.screen.blit(dark, (0, 0))

        if nf < HEADLIGHTS_ON_NIGHT_FACTOR:
            return

        # Headlights (additive).
        lights = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        def rot(v: Vector2, deg: float) -> Vector2:
            r = math.radians(deg)
            c = math.cos(r)
            s = math.sin(r)
            return Vector2(v.x * c - v.y * s, v.x * s + v.y * c)

        for v in self.vehicles:
            if not v.alive:
                continue
            # slightly dim/skip if stealth is active
            stealth_t = float(getattr(v, "stealth_timer", 0.0))
            if stealth_t > 0.05 and not v.is_boss:
                # stealth vehicles still have faint lights, but reduced
                inten_mul = 0.62
            else:
                inten_mul = 1.38

            sp = self.world_to_screen(v.pos, cam_center)
            f = v.forward()
            rvec = Vector2(-f.y, f.x)

            # Two dim, soft-edged cones (one per headlight), offset across the vehicle's front.
            front = v.radius * 0.72
            sep = max(6.0, v.radius * 0.30)

            base_len = 235.0 if not v.is_boss else 330.0
            base_spread = 9.0 if not v.is_boss else 10.5  # degrees (half-angle) per cone

            # Dimmer than previous version; night_factor still scales visibility.
            base_a = int(clamp(18 + nf * 62.0, 0, 120) * inten_mul)  # slightly brighter but still soft

            layers = 10
            for side in (-1.0, 1.0):
                origin = Vector2(sp) + f * front + rvec * (side * sep)
                for i in range(layers):
                    t = (i + 1) / layers
                    L = base_len * (0.55 + 0.45 * t)
                    spr = base_spread * (0.55 + 0.70 * t)
                    a = int(base_a * (1.0 - (i / max(1.0, layers - 1)) * 0.92))
                    if a <= 0:
                        continue
                    left = rot(f, spr)
                    right = rot(f, -spr)
                    p0 = (int(origin.x), int(origin.y))
                    p1 = (int(origin.x + left.x * L), int(origin.y + left.y * L))
                    p2 = (int(origin.x + right.x * L), int(origin.y + right.y * L))
                    inten = a / 255.0
                    # Scale RGB by alpha so additive blending stays soft (prevents solid white wedges)
                    col = (int(235 * inten), int(215 * inten), int(170 * inten), 255)
                    pygame.draw.polygon(lights, col, [p0, p1, p2])
        # Underlap vehicles: clear light where vehicle sprites sit so cones don't paint over cars.
        for v in self.vehicles:
            if not getattr(v, 'alive', False):
                continue
            if getattr(v, 'on_fire', False) or getattr(v, 'burning', False):
                continue
            sp = self.world_to_screen(v.pos, cam_center)
            try:
                rot = pygame.transform.rotozoom(v.base_sprite, v.angle - 90, 1.0)
                rect = rot.get_rect(center=(int(sp.x), int(sp.y)))
            except Exception:
                rect = pygame.Rect(int(sp.x - v.radius), int(sp.y - v.radius), int(v.radius*2), int(v.radius*2))
            # Slight shrink so the vehicle edge still feels illuminated.
            cut = rect.inflate(-14, -14)
            if cut.width > 2 and cut.height > 2:
                pygame.draw.ellipse(lights, (0, 0, 0, 0), cut)

        # Additive blend so headlights brighten the darkened world.
        self.screen.blit(lights, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)


    def draw(self):

        cam_center = self._camera_center()

        # tiled ground
        tw, th = self.world.get_size()
        ox = int((cam_center.x - WIDTH/2) // tw)
        oy = int((cam_center.y - HEIGHT/2) // th)
        for yy in range(oy, oy + 3):
            for xx in range(ox, ox + 3):
                sx = int(xx * tw - cam_center.x + WIDTH/2)
                sy = int(yy * th - cam_center.y + HEIGHT/2)
                self.screen.blit(self.world, (sx, sy))

        # sandstorm (behind ground objects)
        self._draw_sandstorm(front=False)

        # tire marks (fade out)
        if self.tire_marks:
            marks = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for tm in self.tire_marks:
                a = self.world_to_screen(tm.a, cam_center)
                b = self.world_to_screen(tm.b, cam_center)
                alpha = int(255 * clamp(tm.ttl / tm.life, 0.0, 1.0) * 0.55)
                if alpha <= 0:
                    continue
                pygame.draw.line(marks, (*tm.color, alpha), (int(a.x), int(a.y)), (int(b.x), int(b.y)), tm.width)
            self.screen.blit(marks, (0, 0))

        # ground-level particles (dust)
        self._draw_particles(cam_center, layer=0)

                # props (sprite-based only; no geometric placeholders)
        for p in self.props:
            if not p.alive or p.sprite is None:
                continue
            sp = self.world_to_screen(p.pos, cam_center)
            rr = p.sprite.get_rect(center=(int(sp.x), int(sp.y)))
            self.screen.blit(p.sprite, rr.topleft)

        # projectiles# projectiles
        # powerups
        for pu in getattr(self, 'powerups', []):
            if not getattr(pu, 'alive', False):
                continue
            sp = self.world_to_screen(pu.pos, cam_center)
            icon = getattr(self, 'powerup_icons', {}).get(getattr(pu, 'kind', ''), None)
            if icon is not None:
                rr = icon.get_rect(center=(int(sp.x), int(sp.y)))
                self.screen.blit(icon, rr.topleft)
            else:
                pygame.draw.circle(self.screen, (255, 170, 90), (int(sp.x), int(sp.y)), 6, 1)

        for pr in self.projectiles:
            sp = self.world_to_screen(pr.pos, cam_center)
            if pr.kind in ("bullet", "pellet"):
                pygame.draw.circle(self.screen, (255, 230, 170), (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "rocket":
                pygame.draw.circle(self.screen, (255, 180, 90), (int(sp.x), int(sp.y)), 4)
                pygame.draw.circle(self.screen, (255, 220, 150), (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "homing":
                pygame.draw.circle(self.screen, (255, 200, 110), (int(sp.x), int(sp.y)), 4)
                pygame.draw.circle(self.screen, (255, 240, 180), (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "cluster":
                pygame.draw.circle(self.screen, (255, 160, 90), (int(sp.x), int(sp.y)), 4)
                pygame.draw.circle(self.screen, (255, 210, 140), (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "bomblet":
                pygame.draw.circle(self.screen, (255, 210, 120), (int(sp.x), int(sp.y)), 3)
            elif pr.kind == "laser_bolt":
                col = getattr(pr, 'color', (200, 240, 255))
                pygame.draw.circle(self.screen, col, (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "water":
                pygame.draw.circle(self.screen, (120, 210, 255), (int(sp.x), int(sp.y)), 2)
            elif pr.kind == "mine":
                pygame.draw.circle(self.screen, (140, 120, 80), (int(sp.x), int(sp.y)), 10)
                pygame.draw.circle(self.screen, (220, 180, 120), (int(sp.x), int(sp.y)), 10, 2)
            elif pr.kind == "spike":
                pygame.draw.circle(self.screen, (95, 95, 95), (int(sp.x), int(sp.y)), 11)
                pygame.draw.circle(self.screen, (230, 230, 230), (int(sp.x), int(sp.y)), 11, 2)
            elif pr.kind == "mortar_marker":
                pygame.draw.circle(self.screen, (255, 200, 130), (int(sp.x), int(sp.y)), 12, 2)
            elif pr.kind == "nuke_marker":
                # warning ring
                rr = int(36 + 12 * (0.5 + 0.5 * math.sin(self.fire_phase * 4.0)))
                pygame.draw.circle(self.screen, (255, 120, 80), (int(sp.x), int(sp.y)), rr, 3)
                pygame.draw.circle(self.screen, (255, 70, 50), (int(sp.x), int(sp.y)), rr + 10, 1)

        # vehicles
        controlled = self._get_controlled()
        for v in self.vehicles:
            if not v.alive:
                continue
            sp = self.world_to_screen(v.pos, cam_center)
            rot = pygame.transform.rotozoom(v.base_sprite, v.angle - 90, 1.0)
            if getattr(v, 'stealth_timer', 0.0) > 0.0:
                rot = rot.copy()
                rot.set_alpha(120)
            rect = rot.get_rect(center=(int(sp.x), int(sp.y)))

            # motion blur when accelerating (simple sprite trail)
            blur = getattr(v, "motion_blur", 0.0)
            if blur > 0.06:
                speed = v.vel.length()
                speed_frac = clamp(speed / max(1.0, v.max_speed), 0.0, 1.0)
                if v.vel.length_squared() > 1.0:
                    dv = v.vel.normalize()
                else:
                    dv = v.forward()
                offset_mag = 22.0 * blur * (0.4 + 0.6 * speed_frac)
                trails = 3
                for i in range(trails, 0, -1):
                    t = i / trails
                    alpha = int(120 * blur * t)
                    if alpha > 0:
                        r2 = rot.copy()
                        r2.set_alpha(alpha)
                        off = (-dv) * (offset_mag * (1.0 + 1.2 * t))
                        self.screen.blit(r2, (rect.topleft[0] + int(off.x), rect.topleft[1] + int(off.y)))

            self.screen.blit(rot, rect.topleft)
        # particles (sparks / smoke)
        self._draw_particles(cam_center, layer=1)

        # arena fire barrier (map wall)
        if hasattr(self, '_draw_fire_barrier'):
            self._draw_fire_barrier(cam_center)

        # dusk/night overlay + headlights
        self._draw_day_night_and_headlights(cam_center)

        # sandstorm (front overlay)
        self._draw_sandstorm(front=True)

        # UI
        self._draw_ui()

        # Subtle holographic post-process (kept intentionally light)
        self._apply_holo_fx()

        # Quit confirmation modal overlay (drawn last; pauses simulation but keeps rendering)
        self._draw_quit_overlay()

        if not getattr(self, 'embedded', False):
            self._present()


    def _draw_radar(self) -> None:
        """Draw a small radar at top-right showing all vehicles within the arena."""
        size = 140
        margin = 14
        x = WIDTH - size - margin
        y = margin
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 90))

        cx = size // 2
        cy = size // 2
        rr = size // 2 - 10

        # Arena boundary
        pygame.draw.circle(surf, (255, 180, 90, 90), (cx, cy), rr, 2)
        pygame.draw.circle(surf, (230, 230, 230, 120), (cx, cy), rr, 1)

        controlled = self._get_controlled()
        scale = float(rr) / max(1.0, float(ARENA_RADIUS))

        # Vehicle dots
        for v in self.vehicles:
            if not getattr(v, "alive", False):
                continue
            d = v.pos - ARENA_CENTER
            px = cx + d.x * scale
            py = cy + d.y * scale
            if (px - cx) * (px - cx) + (py - cy) * (py - cy) > rr * rr:
                continue

            if v is controlled:
                col = (255, 255, 255, 220)
                rdot = 3
            elif getattr(v, "is_boss", False):
                col = (255, 90, 70, 210)
                rdot = 3
            else:
                col = (255, 210, 140, 180)
                rdot = 2

            pygame.draw.circle(surf, col, (int(px), int(py)), rdot)

            # Simple heading tick for controlled vehicle
            if v is controlled:
                f = v.forward()
                hx = px + f.x * 6.0
                hy = py + f.y * 6.0
                pygame.draw.line(surf, (255, 255, 255, 200), (int(px), int(py)), (int(hx), int(hy)), 1)

        # Subtle border
        pygame.draw.rect(surf, (230, 230, 230, 90), (0, 0, size, size), 1)

        self.screen.blit(surf, (x, y))

    def _apply_holo_fx(self) -> None:
        """Apply a very subtle orange holographic post-process.

        Design goals:
        - No scanlines/no noise.
        - Only a slight contrast modulation (gentle pulse).
        - Must never crash the game; disable itself on any error.
        """
        global HOLO_ENABLED
        if not HOLO_ENABLED:
            return
        try:
            w, h = self.screen.get_size()

            # (Re)build cached surfaces on first use or resize.
            cache_size = getattr(self, '_holo_cache_size', None)
            if cache_size != (w, h) or not hasattr(self, '_holo_tint_surf'):
                self._holo_cache_size = (w, h)
                # Tint uses per-pixel alpha; multiplier does not.
                self._holo_tint_surf = pygame.Surface((w, h), pygame.SRCALPHA)
                self._holo_tint_surf.fill((HOLO_TINT_COLOR[0], HOLO_TINT_COLOR[1], HOLO_TINT_COLOR[2], int(HOLO_TINT_ALPHA)))
                self._holo_mult_surf = pygame.Surface((w, h))

            # Slight contrast pulse (very subtle).
            t = pygame.time.get_ticks() / 1000.0
            contrast = HOLO_CONTRAST_BASE + (HOLO_CONTRAST_PULSE * math.sin(t * 2.0 * math.pi * HOLO_PULSE_SPEED))
            # Convert contrast into an RGB multiplier close to white.
            mult = int(255 / max(0.85, min(1.35, float(contrast))))
            mult = max(235, min(255, mult))
            self._holo_mult_surf.fill((mult, mult, mult))
            self.screen.blit(self._holo_mult_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

            # Warm tint overlay.
            self.screen.blit(self._holo_tint_surf, (0, 0))

        except Exception:
            # Hard-disable if anything goes wrong; never take down the game.
            HOLO_ENABLED = False
            return

    def _draw_ui(self):
        # Radar only
        self._draw_radar()


    def step(self, dt: float, events=None) -> bool:
        """Advance one simulation step in embedded mode.

        Returns False if the instance requested to quit.
        """
        if events is None:
            events = []
        if not self._handle_events(events):
            return False

        # Clamp dt for stability
        try:
            dt = float(dt)
        except Exception:
            dt = 1.0 / 60.0
        dt = min(max(dt, 0.0), 1/20)

        # Pause simulation while quit modal is open, but keep rendering.
        if not getattr(self, "_quit_modal", False):
            self.update(dt)

        self.draw()
        return not getattr(self, "_request_quit", False)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 1/20)

            for event in pygame.event.get():
                self._process_event(event)

            if getattr(self, "_request_quit", False):
                running = False
                break

            # Pause simulation while quit modal is open, but keep rendering.
            if not getattr(self, "_quit_modal", False):
                self.update(dt)

            self.draw()

        pygame.quit()

    # --- Embedded API ------------------------------------------------------------



def _handle_events(self, events):
    """Handle an iterable of pygame events (shared by run() and step())."""
    for event in events:
        self._process_event(event)
        if getattr(self, "_request_quit", False):
            return False
    return True


# Compatibility bridge for embedded mode: some builds call _handle_events from step().
# Keep it as a bound method alias to the centralized event pump.
def _events_step_bridge(self, events):
    try:
        for ev in events or []:
            self._process_event(ev)
        return not getattr(self, '_request_quit', False)
    except Exception:
        return False

Game._handle_events = _events_step_bridge

def create_embedded(external_surface, viewport_rect=None):
    """Factory for hub embedding.

    The hub should call obj.step(dt, events) every frame.
    """
    return Game(external_surface=external_surface)


def main():
    game = Game()
    game.run()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _write_crash_log(e)
        raise
