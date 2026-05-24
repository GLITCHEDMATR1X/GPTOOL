import colorsys
import math
import random
import os
import json
import traceback
from array import array
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pygame

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60
TILE_SIZE = 24
MAP_WIDTH = 180
MAP_HEIGHT = 180
NUM_TEAMS = 20
ROBOTS_PER_TEAM = 7
SCRAP_CLUSTERS = 260
TECH_CLUSTERS = 160
RESOURCE_ATTRACT_RADIUS = 140
RESOURCE_LURE_BONUS = 0.8
LASER_RANGE = 180
LASER_SPEED = 360
LASER_COOLDOWN = 1.4
ALIEN_SPAWN_INTERVAL = 18.0
ALIEN_MAX_PER_TEAM = 6
DINO_SPAWN_INTERVAL = 12.0
LOG_PANEL_WIDTH = 320
MAX_TRIBES = 12
TRIBE_SPAWN_DISTANCE = 1000 * TILE_SIZE
REGION_SIZE = 1200
DAY_LENGTH = 120.0
GLOW_ALPHA = 80
SHAKE_DECAY = 4.0
STUCK_TIME = 6.0
PICKUP_RADIUS = 18
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

EMBEDDED = os.environ.get("ARCADE_EMBEDDED", "") == "1"

Color = Tuple[int, int, int]
Point = pygame.Vector2

BIOME_ID = {
    "waste": 0,
    "ridge": 1,
    "dune": 2,
    "bog": 3,
    "oasis": 4,
    "glacier": 5,
}

BIOME_SHIFT: Dict[str, Tuple[int, int, int]] = {
    "ridge": (15, 10, 5),
    "dune": (25, 18, 6),
    "bog": (-10, 15, 12),
    "oasis": (5, 25, 10),
    "glacier": (-5, -5, 20),
    "waste": (0, 0, 0),
}


@dataclass
class Tile:
    height: float
    scrap: int = 0
    alloy: int = 0
    crystal: int = 0
    capacitor: int = 0
    clutter: float = 0.0
    rock: bool = False
    biome: str = "waste"
    foliage: float = 0.0
    river: bool = False
    tx: int = 0
    ty: int = 0
    version: int = 0
    static_sig: int = 0
    cached_color: Tuple[int, int, int] = (0, 0, 0)
    cached_stamp: int = -1
    micro: Tuple[Tuple[int, int], Tuple[int, int]] = field(default_factory=lambda: ((4, 0), (4, 0)))


@dataclass
class Structure:
    kind: str
    pos: Point
    size: float
    team: "Team"
    hp: float
    max_hp: float
    cooldown: float = 0.0


@dataclass
class Team:
    name: str
    color: Color
    base_pos: Point
    resources: int = 0
    structures: List[Structure] = field(default_factory=list)
    robots: List["Robot"] = field(default_factory=list)
    explored: float = 0.0
    maze_extent: int = 0
    room_level: int = 0
    defense_level: int = 0
    aggression: float = 0.25
    vehicles: List["Vehicle"] = field(default_factory=list)
    mechs: List["Mech"] = field(default_factory=list)
    ships: List["Ship"] = field(default_factory=list)
    tech_level: int = 1
    stance: str = "neutral"
    resource_pressure: float = 0.0
    patrols: List["PatrolPlatoon"] = field(default_factory=list)
    personality: str = ""
    troops: List["Troop"] = field(default_factory=list)
    generals: List["General"] = field(default_factory=list)
    snipers: List["Sniper"] = field(default_factory=list)
    drones: List["Drone"] = field(default_factory=list)
    sprites: List["Sprite"] = field(default_factory=list)
    civilians: List["Civilian"] = field(default_factory=list)
    repair_bots: List["RepairBot"] = field(default_factory=list)
    spawn_queue: List[str] = field(default_factory=list)
    spawn_timer: float = 0.0
    spawn_wave_timer: float = 0.0
    style_seed: int = 0
    epoch: int = 1
    extinct: bool = False
    threatened: bool = False


@dataclass
class Projectile:
    pos: Point
    vel: Point
    team: Team
    ttl: float = 1.4
    kind: str = "laser"


@dataclass
class Alien:
    pos: Point
    team: Team
    kind: str
    hp: float = 120.0
    target: Optional[Point] = None


@dataclass
class Dino:
    pos: Point
    kind: str = "reef"
    hp: float = 200.0
    target: Optional[Point] = None


@dataclass
class NativeHive:
    pos: Point
    kind: str = "lumen"
    hp: float = 100.0
    max_hp: float = 100.0


@dataclass
class NativeQueen:
    pos: Point
    kind: str = "lumen"
    hp: float = 400.0
    target: Optional[Point] = None


@dataclass
class Civilian:
    pos: Point
    team: Team
    hp: float = 55.0
    carry: int = 0
    target: Optional[Point] = None
    state: str = "gather"
    cooldown: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class WaterMonster:
    pos: Point
    hp: float = 120.0
    target: Optional[Point] = None


@dataclass
class WaterNest:
    pos: Point
    hp: float = 140.0


@dataclass
class RepairBot:
    pos: Point
    team: Team
    hp: float = 80.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class SandWorm:
    pos: Point
    target: Optional[Point] = None
    hp: float = 260.0
    emerge_timer: float = 0.0
    active: bool = False


@dataclass
class Disaster:
    pos: Point
    radius: float
    ttl: float


@dataclass
class DeathMarker:
    pos: Point
    team: Optional[Team]
    story: str
    ttl: float = 60.0


@dataclass
class Explosion:
    pos: Point
    radius: float
    color: Tuple[int, int, int]
    ttl: float = 0.6


@dataclass
class PatrolPlatoon:
    members: List[object]
    anchor: Point
    formation: List[Point]
    target: Point
    role: str
    cooldown: float = 0.0


@dataclass
class Vehicle:
    pos: Point
    team: Team
    role: str
    hp: float = 160.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Mech:
    pos: Point
    team: Team
    role: str
    hp: float = 260.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Ship:
    pos: Point
    team: Team
    role: str
    hp: float = 420.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Robot:
    pos: Point
    team: Team
    hp: float = 100.0
    carry: int = 0
    target: Optional[Point] = None
    state: str = "explore"
    scan_radius: float = 160.0
    id_tag: int = 0
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))

    def distance_to(self, point: Point) -> float:
        return self.pos.distance_to(point)


@dataclass
class Troop:
    pos: Point
    team: Team
    role: str
    hp: float = 90.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class General:
    pos: Point
    team: Team
    hp: float = 160.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Sniper:
    pos: Point
    team: Team
    hp: float = 80.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Drone:
    pos: Point
    team: Team
    hp: float = 70.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class Sprite:
    pos: Point
    team: Team
    hp: float = 60.0
    target: Optional[Point] = None
    cooldown: float = 0.0
    stuck_timer: float = 0.0
    last_pos: Point = field(default_factory=lambda: Point(0, 0))

    def distance_to(self, point: Point) -> float:
        return self.pos.distance_to(point)


class Wasteland:
    def __init__(self) -> None:
        self.tiles: Dict[Tuple[int, int], Tile] = {}
        self._seed = RANDOM_SEED

    def ensure_region(self, center: Point, radius_tiles: int) -> None:
        cx = int(center.x // TILE_SIZE)
        cy = int(center.y // TILE_SIZE)
        for ty in range(cy - radius_tiles, cy + radius_tiles + 1):
            for tx in range(cx - radius_tiles, cx + radius_tiles + 1):
                if (tx, ty) not in self.tiles:
                    self.tiles[(tx, ty)] = self._generate_tile(tx, ty)

    def tile_at(self, world_pos: Point) -> Optional[Tile]:
        tx = int(world_pos.x // TILE_SIZE)
        ty = int(world_pos.y // TILE_SIZE)
        return self.tile_at_grid(tx, ty)

    def tile_at_grid(self, tx: int, ty: int) -> Optional[Tile]:
        tile = self.tiles.get((tx, ty))
        if tile is None:
            tile = self._generate_tile(tx, ty)
            self.tiles[(tx, ty)] = tile
        return tile

    def _generate_tile(self, tx: int, ty: int) -> Tile:
        noise = self._height_noise(tx, ty)
        heat = self._heat_noise(tx, ty)
        moisture = self._moisture_noise(tx, ty)
        rng = random.Random((tx * 73856093) ^ (ty * 19349663) ^ self._seed)
        biome = self._pick_biome(noise, heat, moisture)
        tile = Tile(
            height=noise,
            clutter=rng.random(),
            rock=noise > 0.75 and rng.random() > 0.4,
            biome=biome,
        )
        tile.foliage = max(0.0, (moisture - 0.5) * 1.4) if biome in ("bog", "oasis") else max(0.0, moisture - 0.7)
        tile.river = moisture > 0.78 and noise < 0.45
        resource_roll = rng.random()
        spread = 0.975 if biome in ("oasis", "bog") else 0.985
        if resource_roll > spread:
            tile.scrap = rng.randint(1, 3)
        if resource_roll > spread + 0.01:
            tile.alloy = rng.randint(0, 2)
        if resource_roll > spread + 0.02:
            tile.crystal = rng.randint(0, 2)
        if resource_roll > spread + 0.03:
            tile.capacitor = rng.randint(0, 2)
        tile.tx = tx
        tile.ty = ty
        biome_id = BIOME_ID.get(tile.biome, 0)
        hq = int(max(0, min(255, tile.height * 255)))
        tile.static_sig = hq | (biome_id << 8) | ((1 if tile.rock else 0) << 15) | ((1 if tile.river else 0) << 16)
        rng_micro = random.Random((tx * 1009) ^ (ty * 9176) ^ (self._seed << 1))
        micro0 = (rng_micro.randint(3, 5), rng_micro.randint(-8, 8))
        micro1 = (rng_micro.randint(3, 5), rng_micro.randint(-8, 8))
        tile.micro = (micro0, micro1)
        return tile

    def _height_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.08) + math.cos(y * 0.06)
        l = math.sin((x + y) * 0.03)
        r = self._coord_random(x, y, 0.3)
        return max(0.0, min(1.0, (s + l) * 0.3 + 0.5 + r))

    def _heat_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.05) + math.cos(y * 0.04)
        r = self._coord_random(x + 99, y - 37, 0.4)
        return max(0.0, min(1.0, 0.5 + s * 0.2 + r))

    def _moisture_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.04 + y * 0.02)
        r = self._coord_random(x - 43, y + 58, 0.35)
        return max(0.0, min(1.0, 0.5 + s * 0.25 + r))

    def _coord_random(self, x: int, y: int, scale: float) -> float:
        rng = random.Random((x * 83492791) ^ (y * 1640531513) ^ self._seed)
        return rng.random() * scale

    def _pick_biome(self, height: float, heat: float, moisture: float) -> str:
        if height > 0.8:
            return "ridge"
        if heat > 0.7 and moisture < 0.35:
            return "dune"
        if moisture > 0.65 and heat < 0.5:
            return "bog"
        if moisture > 0.6 and heat > 0.6:
            return "oasis"
        if heat < 0.35:
            return "glacier"
        return "waste"

    def region_key(self, world_pos: Point) -> Tuple[int, int]:
        return (int(world_pos.x // REGION_SIZE), int(world_pos.y // REGION_SIZE))


class Camera:
    def __init__(self) -> None:
        self.pos = Point(0, 0)
        self.follow: Optional[Robot] = None
        self.pan_vel = Point(0, 0)

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper, view_size: Point) -> None:
        # Clamp dt to reduce hitches when the window is dragged / focus changes.
        dt = max(0.0, min(0.05, dt))

        if self.follow:
            target = self.follow.pos - Point(view_size.x / 2, view_size.y / 2)
            # Critically damped exponential smoothing (frame-rate independent).
            tau = 0.18
            alpha = 1.0 - math.exp(-dt / max(1e-6, tau))
            self.pos += (target - self.pos) * alpha
            self.pan_vel *= 0
            return

        direction = Point(0, 0)
        if keys[pygame.K_w]:
            direction.y -= 1
        if keys[pygame.K_s]:
            direction.y += 1
        if keys[pygame.K_a]:
            direction.x -= 1
        if keys[pygame.K_d]:
            direction.x += 1

        accel = 2600.0
        max_speed = 900.0
        drag = 10.0

        # Apply drag smoothly.
        self.pan_vel *= math.exp(-drag * dt)

        if direction.length_squared() > 0:
            direction = direction.normalize()
            self.pan_vel += direction * accel * dt
            if self.pan_vel.length_squared() > max_speed * max_speed:
                self.pan_vel.scale_to_length(max_speed)

        self.pos += self.pan_vel * dt

    def world_to_screen(self, world: Point) -> Point:
        return world - self.pos


    def screen_to_world(self, screen: Point) -> Point:
        return screen + self.pos


class SpatialHash:
    """Simple spatial hash for broadphase queries (AI targeting + collisions)."""

    def __init__(self, cell_size: float = 120.0) -> None:
        self.cell_size = float(max(32.0, cell_size))
        self.cells: Dict[Tuple[int, int], List[object]] = {}
        self.pos: Dict[int, Point] = {}
        self.team: Dict[int, Optional[Team]] = {}
        self.kind: Dict[int, str] = {}

    def clear(self) -> None:
        self.cells.clear()
        self.pos.clear()
        self.team.clear()
        self.kind.clear()

    def _key(self, p: Point) -> Tuple[int, int]:
        return (int(p.x // self.cell_size), int(p.y // self.cell_size))

    def add(self, obj: object, p: Point, team: Optional[Team], kind: str) -> None:
        oid = id(obj)
        self.pos[oid] = p
        self.team[oid] = team
        self.kind[oid] = kind
        k = self._key(p)
        bucket = self.cells.get(k)
        if bucket is None:
            self.cells[k] = [obj]
        else:
            bucket.append(obj)

    def query(self, center: Point, radius: float) -> List[object]:
        r = max(0.0, radius)
        cs = self.cell_size
        min_x = int((center.x - r) // cs)
        max_x = int((center.x + r) // cs)
        min_y = int((center.y - r) // cs)
        max_y = int((center.y + r) // cs)
        out: List[object] = []
        for cy in range(min_y, max_y + 1):
            for cx in range(min_x, max_x + 1):
                bucket = self.cells.get((cx, cy))
                if bucket:
                    out.extend(bucket)
        return out


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Wasteland Foundries")
        try:
            if not EMBEDDED:
                pygame.mixer.init()
        except Exception:
            pass
        self.view_size = Point(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.screen_size = Point(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.windowed_size = self.screen_size.copy()
        self.fullscreen = False
        self.resizable = True
        self.vsync_enabled = True
        self.high_detail = True
        self.show_logs = True
        self.render_distance_scale = 1.0
        self.quit_armed = False  # ESC twice to quit
        self._settings_cache = None
        self._spatial = SpatialHash(cell_size=160.0)

        # Load persisted settings before creating the display.
        self._load_settings()

        self._recreate_display()
        # If embedded inside the Arcade hub, the display surface is owned by the hub.
        # Sync our screen_size to the host surface so presentation scaling fills the window.
        try:
            dw, dh = self.display.get_size()
            self.screen_size = Point(int(dw), int(dh))
            if not self.fullscreen:
                self.windowed_size = self.screen_size.copy()
        except Exception:
            pass
        if not EMBEDDED:
            try:
                from pygame._sdl2 import Window  # type: ignore
                Window.from_display_module().maximize()
            except Exception:
                pass
        self.screen = pygame.Surface((int(self.view_size.x), int(self.view_size.y)))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.big_font = pygame.font.SysFont("consolas", 20, bold=True)
        self.wasteland = Wasteland()
        self.camera = Camera()
        self.teams = self._create_teams()
        self._center_camera_on_random_core()
        self.selected: Optional[Robot] = None
        self.team_focus_index = -1
        self.windowed_size = self.screen_size.copy()
        self.projectiles: List[Projectile] = []
        self.aliens: List[Alien] = []
        self.alien_spawn_timer = ALIEN_SPAWN_INTERVAL
        self.dino_spawn_timer = DINO_SPAWN_INTERVAL
        self.dinosaurs: List[Dino] = []
        self.native_hives: List[NativeHive] = []
        self.native_queens: List[NativeQueen] = []
        self.water_monsters: List[WaterMonster] = []
        self.water_nests: List[WaterNest] = []
        self.sand_worms: List[SandWorm] = []
        self.disasters: List[Disaster] = []
        self.logs: List[Tuple[str, str]] = []
        self.show_help = False
        self.show_settings = False
        self.region_names: Dict[Tuple[int, int], str] = {}
        self.current_region_name = ""
        self.region_timer = 0.0
        self.day_timer = 0.0
        self.sfx = self._generate_sfx_pack()
        self.death_markers: List[DeathMarker] = []
        self.explosions: List[Explosion] = []
        self.shake_offset = Point(0, 0)
        self.shake_intensity = 0.0
        # Cache for small glow sprites (reduces per-frame allocations).
        self._glow_cache: Dict[Tuple[Tuple[int,int,int], int, int], pygame.Surface] = {}
        self.radiation_timer = 0.0
        self.radiation_center = Point(0, 0)
        self.selected_info: str = ""
        self.native_hive_timer = random.uniform(12.0, 20.0)
        self.tribe_spawn_timer = random.uniform(6.0, 12.0)
        self.worm_spawn_timer = random.uniform(28.0, 48.0)
        self.disaster_timer = random.uniform(40.0, 70.0)
        self.mouse_pos = Point(0, 0)
        self.audio_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
        self.running = True
        pygame.mouse.set_visible(False)

    def _create_display(self) -> pygame.Surface:
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        if self.resizable and not self.fullscreen:
            flags |= pygame.RESIZABLE

        try:
            return pygame.display.set_mode(
                (int(self.screen_size.x), int(self.screen_size.y)),
                flags=flags,
                vsync=1 if self.vsync_enabled else 0,
            )
        except TypeError:
            # Older pygame builds (or host shims) may not support the vsync keyword.
            return pygame.display.set_mode((int(self.screen_size.x), int(self.screen_size.y)), flags=flags)


    def _recreate_display(self) -> None:
        """Recreate the display safely after a settings change.
        Avoids crashes from unsupported flag/vsync combinations by falling back.
        """
        if EMBEDDED:
            # Embedded: Arcade hub owns the real window and monkey-patches pygame.display.set_mode().
            # Two modes:
            # - Holo widget mode: always call set_mode so we get the widget render surface from the hub shim.
            # - Normal embedded mode: bind to the hub's existing display surface.
            try:
                if os.environ.get("ARCADE_HOLO_WIDGET", "0") == "1":
                    self.display = pygame.display.set_mode((int(self.screen_size.x), int(self.screen_size.y)))
                else:
                    host = pygame.display.get_surface()
                    if host is None:
                        host = pygame.display.set_mode((int(self.screen_size.x), int(self.screen_size.y)))
                    self.display = host

                dw, dh = self.display.get_size()
                self.screen_size = Point(int(dw), int(dh))
                self.windowed_size = self.screen_size.copy()
            except Exception:
                # Last resort fallback
                self.display = pygame.display.set_mode((int(self.view_size.x), int(self.view_size.y)))
                dw, dh = self.display.get_size()
                self.screen_size = Point(int(dw), int(dh))
                self.windowed_size = self.screen_size.copy()
            return
        # Try the normal path first.
        try:
            self.display = self._create_display()
        except Exception:
            # Fallback 1: no vsync keyword and conservative flags.
            try:
                flags = pygame.FULLSCREEN if self.fullscreen else 0
                if self.resizable and not self.fullscreen:
                    flags |= pygame.RESIZABLE
                self.display = pygame.display.set_mode((int(self.screen_size.x), int(self.screen_size.y)), flags=flags)
            except Exception:
                # Fallback 2: windowed, resizable off.
                try:
                    self.fullscreen = False
                    self.resizable = True
                    self.display = pygame.display.set_mode((int(self.screen_size.x), int(self.screen_size.y)), flags=pygame.RESIZABLE)
                except Exception:
                    # Fallback 3: absolute minimum.
                    self.fullscreen = False
                    self.resizable = False
                    self.display = pygame.display.set_mode((int(self.view_size.x), int(self.view_size.y)))
        # Sync screen_size to the actual display size and clear present cache.
        try:
            dw, dh = self.display.get_size()
            self.screen_size = Point(int(dw), int(dh))
            if not self.fullscreen:
                self.windowed_size = self.screen_size.copy()
        except Exception:
            pass
        if hasattr(self, "_scaled_present_cache"):
            self._scaled_present_cache = None

    def _apply_aspect_ratio(self, width: int, height: int) -> Tuple[int, int]:
        target_ratio = 16 / 9
        if height == 0:
            return int(self.view_size.x), int(self.view_size.y)
        current_ratio = width / height
        if current_ratio > target_ratio:
            width = int(height * target_ratio)
        else:
            height = int(width / target_ratio)
        return max(640, width), max(360, height)

    def _center_camera_on_random_core(self) -> None:
        if not self.teams:
            return
        team = random.choice(self.teams)
        target = team.base_pos - Point(self.view_size.x / 2, self.view_size.y / 2)
        self.camera.pos = target

    def _generate_team_colors(self, count: int) -> List[Color]:
        base_colors = [(120, 200, 255), (255, 150, 150), (190, 255, 160), (255, 220, 120)]
        colors = list(base_colors)
        if len(colors) >= count:
            return colors[:count]
        for idx in range(len(colors), count):
            hue = idx / count
            red, green, blue = colorsys.hsv_to_rgb(hue, 0.45, 0.95)
            colors.append((int(red * 255), int(green * 255), int(blue * 255)))
        return colors

    def _create_teams(self) -> List[Team]:
        colors = self._generate_team_colors(NUM_TEAMS)
        names = self._generate_team_names(NUM_TEAMS)
        bases = self._generate_base_positions(NUM_TEAMS)
        teams: List[Team] = []
        for idx in range(NUM_TEAMS):
            team = Team(name=names[idx], color=colors[idx], base_pos=bases[idx], style_seed=random.randint(0, 9999))
            team.structures.append(self._make_structure(team, "core", team.base_pos, 28))
            team.structures.append(self._make_structure(team, "generator", team.base_pos + Point(26, -18), 18))
            team.structures.append(self._make_structure(team, "relay", team.base_pos + Point(-28, 18), 16))
            team.tech_level = random.randint(1, 3)
            team.stance = random.choice(["passive", "neutral", "tyrannic", "explorer", "colonizer"])
            team.personality = self._stance_personality(team.stance)
            self._queue_initial_spawns(team)
            teams.append(team)
        return teams

    def _generate_base_positions(self, count: int) -> List[Point]:
        center = Point(MAP_WIDTH * TILE_SIZE / 2, MAP_HEIGHT * TILE_SIZE / 2)
        positions: List[Point] = []
        min_distance = max(1000 * TILE_SIZE, max(self.view_size.x, self.view_size.y) * 1.6)
        golden_angle = math.tau * 0.61803398875
        for idx in range(count):
            radius = min_distance * (1 + idx)
            angle = idx * golden_angle
            candidate = center + Point(math.cos(angle), math.sin(angle)) * radius
            positions.append(candidate)
        return positions

    def _stance_personality(self, stance: str) -> str:
        return {
            "passive": "Gentle caretakers that avoid conflict and focus on survival.",
            "neutral": "Balanced planners that defend when threatened.",
            "tyrannic": "Aggressive raiders that seize resources relentlessly.",
            "explorer": "Curious scouts that spread far to map new regions.",
            "colonizer": "Builders that push new outposts and fortify rapidly.",
        }.get(stance, "Adaptable survivors of the wasteland.")

    def _spawn_support_units(self, team: Team) -> None:
        for _ in range(2):
            offset = Point(random.randint(-90, 90), random.randint(-90, 90))
            vehicle = Vehicle(pos=team.base_pos + offset, team=team, role=random.choice(["scout", "carrier"]))
            team.vehicles.append(vehicle)
        for _ in range(1):
            offset = Point(random.randint(-120, 120), random.randint(-120, 120))
            mech = Mech(pos=team.base_pos + offset, team=team, role=random.choice(["brawler", "artillery"]))
            team.mechs.append(mech)
        if team.tech_level >= 3:
            team.structures.append(self._make_structure(team, "mech_bay", team.base_pos + Point(40, 28), 18))
        if team.tech_level >= 3:
            ship = Ship(pos=team.base_pos + Point(0, -160), team=team, role="gunship")
            team.ships.append(ship)
        for _ in range(4):
            offset = Point(random.randint(-80, 80), random.randint(-80, 80))
            team.troops.append(Troop(pos=team.base_pos + offset, team=team, role="rifle"))
        team.generals.append(General(pos=team.base_pos + Point(20, 60), team=team))
        team.snipers.append(Sniper(pos=team.base_pos + Point(-60, -40), team=team))
        for _ in range(2):
            offset = Point(random.randint(-100, 100), random.randint(-100, 100))
            team.drones.append(Drone(pos=team.base_pos + offset, team=team))
        for _ in range(2):
            offset = Point(random.randint(-90, 90), random.randint(-90, 90))
            team.sprites.append(Sprite(pos=team.base_pos + offset, team=team))
        self._create_patrol(team)

    def _spawn_civilians(self, team: Team, count: int = 1) -> None:
        cap = 4 + team.epoch * 2
        available = max(0, cap - len(team.civilians))
        for _ in range(min(count, available)):
            offset = Point(random.randint(-60, 60), random.randint(-60, 60))
            civilian = Civilian(pos=team.base_pos + offset, team=team)
            team.civilians.append(civilian)

    def _queue_initial_spawns(self, team: Team) -> None:
        team.spawn_queue.clear()
        team.spawn_queue.extend(["civilian"] * 4)
        team.spawn_timer = random.uniform(1.6, 2.8)
        team.spawn_wave_timer = random.uniform(6.0, 10.0)

    def _queue_peace_spawns(self, team: Team) -> None:
        team.spawn_queue.extend(["civilian"] * 2)

    def _queue_combat_wave(self, team: Team) -> None:
        team.spawn_queue.extend(["robot"] * 2)
        team.spawn_queue.append("vehicle")
        team.spawn_queue.extend(["troop"] * 2)
        team.spawn_queue.append("drone")
        if team.tech_level >= 2:
            team.spawn_queue.append("mech")
        team.spawn_queue.append("sniper")
        team.spawn_queue.append("general")
        team.spawn_queue.append("repair_bot")
        team.spawn_queue.append("sprite")
        if team.tech_level >= 3:
            team.spawn_queue.append("ship")

    def _process_spawn_queue(self, team: Team, dt: float) -> None:
        team.spawn_timer = max(0.0, team.spawn_timer - dt)
        team.spawn_wave_timer = max(0.0, team.spawn_wave_timer - dt)
        if not team.spawn_queue:
            if team.spawn_wave_timer > 0:
                return
            if team.threatened:
                self._queue_combat_wave(team)
                team.spawn_wave_timer = random.uniform(10.0, 16.0)
            else:
                self._queue_peace_spawns(team)
                team.spawn_wave_timer = random.uniform(6.0, 10.0)
        if team.spawn_timer > 0:
            return
        kind = team.spawn_queue.pop(0)
        self._spawn_from_queue(team, kind)
        if team.threatened:
            team.spawn_timer = random.uniform(1.4, 2.6)
        else:
            team.spawn_timer = random.uniform(1.8, 3.0)

    def _spawn_from_queue(self, team: Team, kind: str) -> None:
        offset = Point(random.randint(-80, 80), random.randint(-80, 80))
        if kind == "robot":
            robot = Robot(pos=team.base_pos + offset, team=team, id_tag=len(team.robots))
            team.robots.append(robot)
            self._maybe_expand_patrols(team)
            return
        if kind == "civilian":
            self._spawn_civilians(team, count=1)
            return
        if kind == "vehicle":
            team.vehicles.append(Vehicle(pos=team.base_pos + offset, team=team, role=random.choice(["scout", "carrier"])))
            return
        if kind == "mech":
            team.mechs.append(Mech(pos=team.base_pos + offset, team=team, role=random.choice(["brawler", "artillery"])))
            return
        if kind == "troop":
            team.troops.append(Troop(pos=team.base_pos + offset, team=team, role="rifle"))
            return
        if kind == "general":
            team.generals.append(General(pos=team.base_pos + offset, team=team))
            return
        if kind == "sniper":
            team.snipers.append(Sniper(pos=team.base_pos + offset, team=team))
            return
        if kind == "drone":
            team.drones.append(Drone(pos=team.base_pos + offset, team=team))
            return
        if kind == "sprite":
            team.sprites.append(Sprite(pos=team.base_pos + offset, team=team))
            return
        if kind == "repair_bot":
            team.repair_bots.append(RepairBot(pos=team.base_pos + offset, team=team))
            return
        if kind == "ship":
            team.ships.append(Ship(pos=team.base_pos + Point(0, -160), team=team, role="gunship"))

    def _maybe_expand_patrols(self, team: Team) -> None:
        if not team.patrols and len(team.robots) >= 3:
            self._create_patrol(team)
            return
        if team.stance in ("tyrannic", "colonizer") and len(team.robots) >= 6 and len(team.patrols) == 1:
            second_members = team.robots[3:6]
            formation = self._formation_offsets(team.stance, len(second_members))
            platoon = PatrolPlatoon(
                members=second_members,
                anchor=team.base_pos.copy(),
                formation=formation,
                target=team.base_pos + Point(-140, 40),
                role="guard",
            )
            team.patrols.append(platoon)

    def _create_patrol(self, team: Team) -> None:
        squad_size = 3 if team.stance in ("neutral", "passive") else 4
        members = team.robots[:squad_size]
        if len(members) < 2:
            return
        formation = self._formation_offsets(team.stance, len(members))
        platoon = PatrolPlatoon(
            members=members,
            anchor=team.base_pos.copy(),
            formation=formation,
            target=team.base_pos + Point(120, 0),
            role="patrol",
        )
        team.patrols.append(platoon)
        if team.stance in ("tyrannic", "colonizer") and len(team.robots) >= 6:
            second_members = team.robots[3:6]
            formation = self._formation_offsets(team.stance, len(second_members))
            platoon = PatrolPlatoon(
                members=second_members,
                anchor=team.base_pos.copy(),
                formation=formation,
                target=team.base_pos + Point(-140, 40),
                role="guard",
            )
            team.patrols.append(platoon)

    def _generate_team_names(self, count: int) -> List[str]:
        prefixes = ["Astra", "Nyx", "Voru", "Kael", "Xylo", "Umbra", "Orin", "Zyra"]
        cores = ["quar", "syn", "thal", "vex", "drax", "ion", "mire", "vox"]
        suffixes = ["ion", "spire", "forge", "veil", "nexus", "drift", "bastion", "reach"]
        names: List[str] = []
        used = set()
        attempts = 0
        while len(names) < count and attempts < 200:
            attempts += 1
            name = f"{random.choice(prefixes)}{random.choice(cores)} {random.choice(suffixes)}"
            if name not in used:
                used.add(name)
                names.append(name)
        return names

    def _spawn_new_tribe_if_needed(self, view_center: Point) -> None:
        if len(self.teams) >= MAX_TRIBES:
            return
        min_distance = TRIBE_SPAWN_DISTANCE + len(self.teams) * 120
        if any(team.base_pos.distance_to(view_center) < min_distance for team in self.teams):
            return
        if not self._spawn_tribe_near(view_center):
            ring_offset = self._distant_spawn_point(view_center, min_distance * 0.9)
            self._spawn_tribe_near(ring_offset)

    def _spawn_tribe_near(self, view_center: Point) -> bool:
        name = self._generate_team_names(1)[0]
        color = (
            random.randint(80, 230),
            random.randint(80, 230),
            random.randint(80, 230),
        )
        view_rect = pygame.Rect(
            view_center.x - self.view_size.x / 2,
            view_center.y - self.view_size.y / 2,
            self.view_size.x,
            self.view_size.y,
        )
        base_pos = view_center
        for _ in range(12):
            distance = random.randint(int(TRIBE_SPAWN_DISTANCE * 0.9), int(TRIBE_SPAWN_DISTANCE * 1.3))
            angle = random.random() * math.tau
            candidate = view_center + Point(math.cos(angle), math.sin(angle)) * distance
            if not view_rect.inflate(400, 400).collidepoint(candidate):
                base_pos = candidate
                break
        if base_pos == view_center:
            return False
        team = Team(name=name, color=color, base_pos=base_pos, style_seed=random.randint(0, 9999))
        team.structures.append(self._make_structure(team, "core", team.base_pos, 28))
        team.structures.append(self._make_structure(team, "generator", team.base_pos + Point(26, -18), 18))
        team.structures.append(self._make_structure(team, "relay", team.base_pos + Point(-28, 18), 16))
        team.stance = random.choice(["passive", "neutral", "tyrannic", "explorer", "colonizer"])
        team.personality = self._stance_personality(team.stance)
        team.maze_extent = random.randint(0, 4)
        team.room_level = random.randint(0, 3)
        team.defense_level = random.randint(0, 2)
        self._queue_initial_spawns(team)
        self.teams.append(team)
        self._log(f"New tribe established: {team.name}.", team=team)
        return True

    def _distant_spawn_point(self, view_center: Point, distance: float) -> Point:
        angle = random.random() * math.tau
        return view_center + Point(math.cos(angle), math.sin(angle)) * distance

    def run(self) -> None:
        while self.running:
            target_fps = 0 if self.vsync_enabled else FPS
            dt = self.clock.tick(target_fps) / 1000
            dt = min(0.05, dt)
            # Embedded mode: follow host window size changes (Arcade hub resizes the shared surface).
            if EMBEDDED:
                try:
                    dw, dh = self.display.get_size()
                    if int(dw) != int(self.screen_size.x) or int(dh) != int(self.screen_size.y):
                        self.screen_size = Point(int(dw), int(dh))
                        self.windowed_size = self.screen_size.copy()
                        # Drop cached scaled surface so we rebuild at the new size.
                        if hasattr(self, "_scaled_present_cache"):
                            self._scaled_present_cache = None
                except Exception:
                    pass
            self._handle_events()
            self._update(dt)
            self._draw()
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)
            elif event.type == pygame.VIDEORESIZE and self.resizable and not self.fullscreen:
                self.screen_size = Point(max(320, event.w), max(180, event.h))
                self.windowed_size = self.screen_size.copy()
                self._recreate_display()
                self._save_settings()
            elif event.type == pygame.KEYDOWN:
                # ESC twice to quit (first press arms quit prompt; second confirms).
                if self.quit_armed:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        # Any other key cancels the quit prompt.
                        self.quit_armed = False
                    continue

                if event.key == pygame.K_ESCAPE:
                    self.quit_armed = True
                    continue

                if event.key == pygame.K_SPACE:
                    self.camera.follow = None
                    self.selected = None
                elif event.key == pygame.K_h:
                    self.show_help = not self.show_help
                elif event.key == pygame.K_t:
                    self._focus_next_team_core()
                elif event.key == pygame.K_TAB:
                    self.show_settings = not self.show_settings
                elif event.key == pygame.K_l:
                    self.show_logs = not self.show_logs
                elif event.key == pygame.K_f:
                    self._toggle_fullscreen()
                elif self.show_settings:
                    self._handle_settings_key(event.key)

    def _toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self.fullscreen = False
            self.screen_size = self.windowed_size.copy()
        else:
            self.fullscreen = True
            display_info = pygame.display.Info()
            self.screen_size = Point(display_info.current_w, display_info.current_h)
        self._recreate_display()
        self._log(f"Fullscreen {'on' if self.fullscreen else 'off'}." )
        self._save_settings()

    def _handle_settings_key(self, key: int) -> None:
        if key == pygame.K_v:
            self.vsync_enabled = not self.vsync_enabled
            self._recreate_display()
            self._log(f"VSync {'on' if self.vsync_enabled else 'off'}.")
        elif key == pygame.K_f:
            self._toggle_fullscreen()
        elif key == pygame.K_r:
            self.resizable = not self.resizable
            self._recreate_display()
            self._log(f"Resizable {'on' if self.resizable else 'off'}.")
        elif key == pygame.K_g:
            self.high_detail = not self.high_detail
            self._log(f"Graphics detail {'high' if self.high_detail else 'low'}.")
        elif key == pygame.K_l:
            self.show_logs = not self.show_logs
            self._log(f"Activity log {'shown' if self.show_logs else 'hidden'}.")
        elif key == pygame.K_MINUS:
            self.render_distance_scale = max(0.6, self.render_distance_scale - 0.1)
            self._log(f"Render distance {self.render_distance_scale:.1f}x.")
        elif key == pygame.K_EQUALS:
            self.render_distance_scale = min(1.6, self.render_distance_scale + 0.1)
            self._log(f"Render distance {self.render_distance_scale:.1f}x.")
        self._save_settings()


    def _handle_click(self, mouse_pos: Tuple[int, int]) -> None:
        view_pos = self._display_to_view(mouse_pos)
        if not (0 <= view_pos.x <= self.view_size.x and 0 <= view_pos.y <= self.view_size.y):
            return
        world = self.camera.screen_to_world(view_pos)
        closest: Optional[Robot] = None
        closest_dist = 999999.0
        for team in self.teams:
            if team.extinct:
                continue
            for robot in team.robots:
                dist = robot.distance_to(world)
                if dist < 24 and dist < closest_dist:
                    closest = robot
                    closest_dist = dist
        if closest:
            self.selected = closest
            self.camera.follow = closest
        else:
            self.selected = None
            self.camera.follow = None

    def _focus_next_team_core(self) -> None:
        active_teams = [team for team in self.teams if not team.extinct]
        if not active_teams:
            return
        self.team_focus_index = (self.team_focus_index + 1) % len(active_teams)
        team = active_teams[self.team_focus_index]
        self.camera.follow = None
        self.selected = None
        self.camera.pos = team.base_pos - Point(self.view_size.x / 2, self.view_size.y / 2)
        self._log(f"Camera focused on {team.name} core.", team=team)

    def _update_hover_info(self) -> None:
        world = self.camera.screen_to_world(self.mouse_pos)
        self.selected_info = ""
        for marker in self.death_markers:
            if marker.pos.distance_to(world) < 20:
                memorial_team = marker.team.name if marker.team else "Wilderness"
                self.selected_info = f"{memorial_team} memorial: {marker.story}"
                return
        for hive in self.native_hives:
            if hive.pos.distance_to(world) < 30:
                self.selected_info = f"Native hive ({int(hive.hp)}/{int(hive.max_hp)})"
                return
        for queen in self.native_queens:
            if queen.pos.distance_to(world) < 36:
                self.selected_info = f"Native queen ({int(queen.hp)})"
                return
        for dino in self.dinosaurs:
            if dino.pos.distance_to(world) < 26:
                self.selected_info = "Roaming native"
                return
        for nest in self.water_nests:
            if nest.pos.distance_to(world) < 28:
                self.selected_info = "Water nest"
                return
        for monster in self.water_monsters:
            if monster.pos.distance_to(world) < 26:
                self.selected_info = "Water native"
                return
        for worm in self.sand_worms:
            if worm.pos.distance_to(world) < 30:
                self.selected_info = "Sand worm"
                return
        for disaster in self.disasters:
            if disaster.pos.distance_to(world) < disaster.radius:
                self.selected_info = "Natural disaster"
                return
        for team in self.teams:
            if team.extinct:
                continue
            for structure in team.structures:
                if structure.pos.distance_to(world) < structure.size + 10:
                    if structure.kind == "core":
                        self.selected_info = f"{team.name} ({team.stance}) | Epoch {team.epoch}"
                    else:
                        self.selected_info = f"{team.name} {structure.kind} ({int(structure.hp)}/{int(structure.max_hp)})"
                    return
            for civilian in team.civilians:
                if civilian.pos.distance_to(world) < 16:
                    self.selected_info = f"{team.name} civilian"
                    return
            for repair_bot in team.repair_bots:
                if repair_bot.pos.distance_to(world) < 16:
                    self.selected_info = f"{team.name} repair bot"
                    return
            for vehicle in team.vehicles:
                if vehicle.pos.distance_to(world) < 24:
                    self.selected_info = f"{team.name} vehicle ({vehicle.role})"
                    return
            for mech in team.mechs:
                if mech.pos.distance_to(world) < 24:
                    self.selected_info = f"{team.name} mech ({mech.role})"
                    return
            for ship in team.ships:
                if ship.pos.distance_to(world) < 28:
                    self.selected_info = f"{team.name} ship ({ship.role})"
                    return
            for troop in team.troops:
                if troop.pos.distance_to(world) < 20:
                    self.selected_info = f"{team.name} troop"
                    return
            for general in team.generals:
                if general.pos.distance_to(world) < 22:
                    self.selected_info = f"{team.name} general"
                    return
            for sniper in team.snipers:
                if sniper.pos.distance_to(world) < 20:
                    self.selected_info = f"{team.name} sniper"
                    return
            for drone in team.drones:
                if drone.pos.distance_to(world) < 18:
                    self.selected_info = f"{team.name} drone"
                    return
            for sprite in team.sprites:
                if sprite.pos.distance_to(world) < 18:
                    self.selected_info = f"{team.name} sprite"
                    return

    def _update(self, dt: float) -> None:
        # Always update mouse position for UI/prompt interactions.
        self.mouse_pos = self._display_to_view(pygame.mouse.get_pos())

        # Pause simulation while quit prompt is armed.
        if self.quit_armed:
            return

        keys = pygame.key.get_pressed()
        if any(keys[key] for key in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d)):
            self.camera.follow = None
        self.camera.update(dt, keys, self.view_size)
        view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
        if view_center.distance_to(self.audio_center) > max(self.view_size.x, self.view_size.y) * 1.4:
            pygame.mixer.stop()
            self.audio_center = view_center
        radius_tiles = int(max(self.view_size.x, self.view_size.y) / TILE_SIZE) + 6
        self.wasteland.ensure_region(view_center, radius_tiles)
        self._update_region(view_center, dt)
        self.day_timer = (self.day_timer + dt) % DAY_LENGTH
        self._update_hover_info()
        self._rebuild_spatial()

        for team in self.teams:
            if team.extinct:
                continue
            self._update_team_state(team, dt)
            self._process_spawn_queue(team, dt)
            team.aggression = max(0.1, team.aggression - dt * 0.02)
            self._update_patrols(team, dt)
            for robot in team.robots:
                self._update_robot(robot, dt)
            for civilian in team.civilians:
                self._update_civilian(civilian, dt)
            for repair_bot in team.repair_bots:
                self._update_repair_bot(repair_bot, dt)
            for vehicle in team.vehicles:
                self._update_vehicle(vehicle, dt)
            for mech in team.mechs:
                self._update_mech(mech, dt)
            for ship in team.ships:
                self._update_ship(ship, dt)
            for troop in team.troops:
                self._update_troop(troop, dt)
            for general in team.generals:
                self._update_general(general, dt)
            for sniper in team.snipers:
                self._update_sniper(sniper, dt)
            for drone in team.drones:
                self._update_drone(drone, dt)
            for sprite in team.sprites:
                self._update_sprite(sprite, dt)
        self._update_aliens(dt)
        self._update_dinosaurs(dt)
        self._update_native_queens(dt)
        self._update_water_natives(dt)
        self._update_sand_worms(dt)
        self._update_disasters(dt)
        self._update_radiation(dt)
        self._update_defenses(dt)
        self._update_projectiles(dt)
        self._update_death_markers(dt)
        self._update_explosions(dt)
        self._resolve_collisions()
        self._update_screen_shake(dt)

    def _update_robot(self, robot: Robot, dt: float) -> None:
        robot.cooldown = max(0.0, robot.cooldown - dt)
        enemy = self._nearest_enemy_unit(
            robot.team,
            robot.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if enemy and robot.distance_to(enemy.pos) < 60:
            robot.state = "fight"
            robot.target = enemy.pos
            self._apply_damage(enemy, 12 * dt, robot.team, action="defending the perimeter")
            robot.hp -= 5 * dt
            robot.team.aggression = min(1.0, robot.team.aggression + dt * 0.4)
            if random.random() < 0.03:
                self._play_sfx("laser", robot.team, robot.pos)
        elif enemy and robot.cooldown <= 0 and self._can_fire_at(robot.pos, enemy.pos, 120):
            robot.state = "fight"
            robot.target = enemy.pos
            direction = (enemy.pos - robot.pos).normalize()
            self.projectiles.append(
                Projectile(pos=robot.pos.copy(), vel=direction * (LASER_SPEED - 20), team=robot.team, kind="pulse")
            )
            robot.cooldown = 2.2
            self._play_sfx("pulse", robot.team, robot.pos)
        if robot.state == "fight" and enemy and robot.distance_to(enemy.pos) >= 60:
            robot.state = "explore"

        if robot.carry >= 5:
            robot.state = "return"
            robot.target = robot.team.base_pos
        elif robot.state != "fight":
            if robot.state == "return" and robot.distance_to(robot.team.base_pos) < 30:
                robot.team.resources += robot.carry
                robot.carry = 0
                robot.state = "build" if robot.team.resources > 10 else "explore"
                robot.target = None
            if robot.state == "build" and robot.team.resources > 10:
                self._build_structure(robot.team)
                robot.team.resources -= 8
                robot.state = "explore"
            if robot.state == "explore":
                self._explore(robot)
        if robot.state not in ("fight", "return"):
            robot.state = "explore"

        self._apply_structure_effects(robot, dt)
        self._move_robot(robot, dt)
        self._check_stuck(robot, dt, robot.team)

    def _update_civilian(self, civilian: Civilian, dt: float) -> None:
        civilian.cooldown = max(0.0, civilian.cooldown - dt)
        if civilian.carry >= 3:
            civilian.state = "return"
            civilian.target = civilian.team.base_pos
        elif civilian.state != "return":
            civilian.state = "gather"
            if civilian.target is None or civilian.pos.distance_to(civilian.target) < 12:
                civilian.target = self._wander_target(civilian.team, civilian.pos)

        if civilian.state == "return" and civilian.pos.distance_to(civilian.team.base_pos) < 26:
            civilian.team.resources += civilian.carry
            civilian.carry = 0
            civilian.state = "build"
            civilian.target = None

        if civilian.state == "build" and civilian.cooldown <= 0:
            if self._civilian_build(civilian.team):
                civilian.cooldown = 6.0
            else:
                self._repair_nearby(civilian.team, civilian.pos, dt, rate=8)
            civilian.state = "gather"

        tile = self._tile_in_pickup_range(civilian.pos)
        if tile and civilian.state == "gather":
            collected = False
            if tile.scrap > 0:
                tile.scrap -= 1
                civilian.carry += 1
                collected = True
            if tile.alloy > 0:
                tile.alloy -= 1
                civilian.carry += 1
                collected = True
            if tile.crystal > 0:
                tile.crystal -= 1
                civilian.carry += 1
                collected = True
            if collected:
                tile.version += 1
            if collected and civilian.carry >= 3:
                civilian.state = "return"
                civilian.target = civilian.team.base_pos

        self._move_mobile(civilian, dt, speed=70)
        if civilian.pos.distance_to(civilian.last_pos) < 2:
            civilian.last_pos = civilian.pos.copy()

    def _update_repair_bot(self, bot: RepairBot, dt: float) -> None:
        bot.cooldown = max(0.0, bot.cooldown - dt)
        target = self._nearest_damaged_structure(bot.team, bot.pos)
        if target:
            bot.target = target.pos
            if bot.pos.distance_to(target.pos) < 26:
                self._repair_nearby(bot.team, bot.pos, dt, rate=14)
        elif bot.target is None or bot.pos.distance_to(bot.target) < 12:
            bot.target = self._wander_target(bot.team, bot.pos)
        self._move_mobile(bot, dt, speed=80)
        if bot.pos.distance_to(bot.last_pos) < 2:
            bot.last_pos = bot.pos.copy()

    def _civilian_build(self, team: Team) -> bool:
        if team.resources < 3:
            return False
        gun_tower_cap = 1 + team.epoch
        if self._count_structures(team, "gun_tower") < gun_tower_cap and team.resources >= 6:
            team.resources -= 6
            pos = self._ring_position(team, 6, 120, 22)
            team.structures.append(self._make_structure(team, "gun_tower", pos, 12))
            return True
        if self._count_structures(team, "forcefield") < 2 + team.epoch // 2 and team.resources >= 8:
            team.resources -= 8
            pos = self._ring_position(team, 4, 90, 28)
            team.structures.append(self._make_structure(team, "forcefield", pos, 20))
            return True
        if self._count_structures(team, "town") < 3 + team.epoch and team.resources >= 5:
            team.resources -= 5
            pos = self._ring_position(team, 6, 80, 20)
            team.structures.append(self._make_structure(team, "town", pos, 18))
            return True
        if team.resources >= 3:
            team.resources -= 3
            pos = self._ring_position(team, 8, 60, 16, kind="road")
            team.structures.append(self._make_structure(team, "road", pos, 10))
            return True
        return False

    def _count_structures(self, team: Team, kind: str) -> int:
        return sum(1 for structure in team.structures if structure.kind == kind)

    def _ring_position(self, team: Team, slots: int, base_radius: float, spacing: float, kind: str = "town") -> Point:
        existing = self._count_structures(team, kind)
        ring = existing // slots + 1
        angle = (existing % slots) * (math.tau / slots)
        radius = base_radius + ring * spacing
        return team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius

    def _nearest_damaged_structure(self, team: Team, pos: Point) -> Optional[Structure]:
        damaged = [structure for structure in team.structures if structure.hp < structure.max_hp]
        if not damaged:
            return None
        return min(damaged, key=lambda structure: structure.pos.distance_to(pos))

    def _repair_nearby(self, team: Team, pos: Point, dt: float, rate: float) -> None:
        target = self._nearest_damaged_structure(team, pos)
        if not target:
            return
        if target.pos.distance_to(pos) > 32:
            return
        if team.resources > 0:
            team.resources = max(0, team.resources - dt * 0.4)
            target.hp = min(target.max_hp, target.hp + rate * dt)

    def _update_troop(self, troop: Troop, dt: float) -> None:
        troop.cooldown = max(0.0, troop.cooldown - dt)
        target = self._nearest_enemy_unit(
            troop.team,
            troop.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            troop.target = target.pos
        if target and troop.cooldown <= 0 and self._can_fire_at(troop.pos, target.pos, 140):
            direction = (target.pos - troop.pos).normalize()
            self.projectiles.append(
                Projectile(pos=troop.pos.copy(), vel=direction * (LASER_SPEED - 30), team=troop.team, kind="pulse")
            )
            troop.cooldown = 2.0
        elif troop.target is None or troop.pos.distance_to(troop.target) < 8:
            troop.target = self._wander_target(troop.team, troop.pos)
        self._move_mobile(troop, dt, speed=70)
        self._check_stuck(troop, dt, troop.team)

    def _update_general(self, general: General, dt: float) -> None:
        general.cooldown = max(0.0, general.cooldown - dt)
        target = self._nearest_enemy_unit(
            general.team,
            general.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            general.target = target.pos
        if target and general.cooldown <= 0 and self._can_fire_at(general.pos, target.pos, 180):
            direction = (target.pos - general.pos).normalize()
            self.projectiles.append(
                Projectile(pos=general.pos.copy(), vel=direction * LASER_SPEED, team=general.team, kind="laser")
            )
            general.cooldown = 1.5
        elif general.target is None or general.pos.distance_to(general.target) < 10:
            general.target = general.team.base_pos
        self._move_mobile(general, dt, speed=60)
        self._check_stuck(general, dt, general.team)

    def _update_sniper(self, sniper: Sniper, dt: float) -> None:
        sniper.cooldown = max(0.0, sniper.cooldown - dt)
        target = self._nearest_enemy_unit(
            sniper.team,
            sniper.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            sniper.target = target.pos
        if target and sniper.cooldown <= 0 and self._can_fire_at(sniper.pos, target.pos, 260):
            direction = (target.pos - sniper.pos).normalize()
            self.projectiles.append(
                Projectile(pos=sniper.pos.copy(), vel=direction * (LASER_SPEED + 80), team=sniper.team, kind="laser")
            )
            sniper.cooldown = 3.0
        elif sniper.target is None or sniper.pos.distance_to(sniper.target) < 10:
            sniper.target = self._wander_target(sniper.team, sniper.pos)
        self._move_mobile(sniper, dt, speed=55)
        self._check_stuck(sniper, dt, sniper.team)

    def _update_drone(self, drone: Drone, dt: float) -> None:
        drone.cooldown = max(0.0, drone.cooldown - dt)
        target = self._nearest_enemy_unit(
            drone.team,
            drone.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            drone.target = target.pos
        if target and drone.cooldown <= 0 and self._can_fire_at(drone.pos, target.pos, 160):
            direction = (target.pos - drone.pos).normalize()
            self.projectiles.append(
                Projectile(pos=drone.pos.copy(), vel=direction * (LASER_SPEED + 20), team=drone.team, kind="pulse")
            )
            drone.cooldown = 1.4
        elif drone.target is None or drone.pos.distance_to(drone.target) < 12:
            drone.target = self._wander_target(drone.team, drone.pos)
        self._move_mobile(drone, dt, speed=95)
        self._check_stuck(drone, dt, drone.team)

    def _update_sprite(self, sprite: Sprite, dt: float) -> None:
        sprite.cooldown = max(0.0, sprite.cooldown - dt)
        target = self._nearest_enemy_unit(
            sprite.team,
            sprite.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            sprite.target = target.pos
        if target and sprite.cooldown <= 0 and self._can_fire_at(sprite.pos, target.pos, 130):
            direction = (target.pos - sprite.pos).normalize()
            self.projectiles.append(
                Projectile(pos=sprite.pos.copy(), vel=direction * (LASER_SPEED - 10), team=sprite.team, kind="pulse")
            )
            sprite.cooldown = 2.6
        elif sprite.target is None or sprite.pos.distance_to(sprite.target) < 12:
            sprite.target = self._wander_target(sprite.team, sprite.pos)
        self._move_mobile(sprite, dt, speed=75)
        self._check_stuck(sprite, dt, sprite.team)

    def _explore(self, robot: Robot) -> None:
        tile = self._tile_in_pickup_range(robot.pos)
        if tile:
            collected = False
            if tile.scrap > 0:
                tile.scrap -= 1
                robot.carry += 1
                robot.team.explored += 0.2
                self._log("Scavenged scrap.", team=robot.team)
                collected = True
            if tile.alloy > 0:
                tile.alloy -= 1
                robot.team.resources += 1
                robot.team.maze_extent += 1
                self._expand_maze(robot.team)
                self._log("Forged a maze hall.", team=robot.team)
                collected = True
            if tile.crystal > 0:
                tile.crystal -= 1
                robot.team.resources += 2
                robot.team.room_level += 1
                self._expand_rooms(robot.team)
                self._log("Added a room module.", team=robot.team)
                collected = True
            if tile.capacitor > 0:
                tile.capacitor -= 1
                robot.team.resources += 3
                robot.team.defense_level += 1
                self._add_defense(robot.team)
                self._log("Powered defenses.", team=robot.team)
                collected = True
            if collected:
                tile.version += 1
                robot.state = "return" if robot.carry >= 4 else "explore"
                return

        if robot.target is None or robot.distance_to(robot.target) < 12:
            lure = self._resource_lure(robot)
            if lure is not None and random.random() < RESOURCE_LURE_BONUS:
                robot.target = lure
            elif robot.team.aggression > 0.6 and random.random() < robot.team.aggression * 0.15:
                robot.target = self._enemy_base_hint(robot.team, robot.pos)
            else:
                angle = random.random() * math.tau
                distance = random.randint(80, 180)
                robot.target = robot.pos + Point(math.cos(angle), math.sin(angle)) * distance

    def _move_robot(self, robot: Robot, dt: float) -> None:
        if robot.target is None:
            return
        direction = robot.target - robot.pos
        if direction.length() < 1:
            return
        direction = direction.normalize()
        speed = 80
        if robot.state == "return":
            speed = 110
        if robot.state == "fight":
            speed = 130
        speed += self._relay_speed_bonus(robot)
        robot.pos += direction * speed * dt


    def _nearest_enemy_unit(
        self,
        team: Optional[Team],
        pos: Point,
        *,
        include_dinosaurs: bool = True,
        include_structures: bool = False,
        include_queens: bool = True,
        include_hives: bool = True,
    ) -> Optional[object]:
        # Fast broadphase query using spatial hash (avoids O(N^2) scans).
        search_radius = max(900.0, self._render_range() * 1.35)
        closest: Optional[object] = None
        best = 9e18

        # If spatial isn't populated yet, fall back to the old behavior.
        spatial = getattr(self, "_spatial", None)
        if spatial is None or not spatial.cells:
            # Fallback: (rare) linear scan
            for other_team in self.teams:
                if team is not None and other_team is team:
                    continue
                if team is not None and not self._teams_hostile(team, other_team):
                    continue
                for u in (
                    other_team.robots
                    + other_team.civilians
                    + other_team.repair_bots
                    + other_team.vehicles
                    + other_team.mechs
                    + other_team.ships
                    + other_team.troops
                    + other_team.generals
                    + other_team.snipers
                    + other_team.drones
                    + other_team.sprites
                ):
                    d2 = (pos.x - u.pos.x) ** 2 + (pos.y - u.pos.y) ** 2
                    if d2 < best:
                        best = d2
                        closest = u
                if include_structures:
                    for s in other_team.structures:
                        d2 = (pos.x - s.pos.x) ** 2 + (pos.y - s.pos.y) ** 2
                        if d2 < best:
                            best = d2
                            closest = s
            if include_dinosaurs:
                for dino in self.dinosaurs:
                    d2 = (pos.x - dino.pos.x) ** 2 + (pos.y - dino.pos.y) ** 2
                    if d2 < best:
                        best = d2
                        closest = dino
            if include_queens:
                for q in self.native_queens:
                    d2 = (pos.x - q.pos.x) ** 2 + (pos.y - q.pos.y) ** 2
                    if d2 < best:
                        best = d2
                        closest = q
            if include_hives:
                for h in self.native_hives:
                    d2 = (pos.x - h.pos.x) ** 2 + (pos.y - h.pos.y) ** 2
                    if d2 < best:
                        best = d2
                        closest = h
            return closest

        candidates = spatial.query(pos, search_radius)
        for obj in candidates:
            if obj is None:
                continue

            # Team + hostility filtering
            obj_team = getattr(obj, "team", None)
            if isinstance(obj, Alien):
                obj_team = obj.team
            if team is not None and obj_team is team:
                continue
            if team is not None and isinstance(obj_team, Team):
                if not self._teams_hostile(team, obj_team):
                    continue

            # Type inclusion filtering
            if isinstance(obj, Dino) and not include_dinosaurs:
                continue
            if isinstance(obj, (NativeHive,)) and not include_hives:
                continue
            if isinstance(obj, (NativeQueen,)) and not include_queens:
                continue
            if isinstance(obj, Structure) and not include_structures:
                continue

            # Distance (squared)
            p = getattr(obj, "pos", None)
            if p is None:
                continue
            d2 = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
            if d2 < best:
                best = d2
                closest = obj

        return closest

    def _teams_hostile(self, team: Team, other: Team) -> bool:
        if team is other:
            return False
        hostile_stances = ("tyrannic", "colonizer")
        return (
            team.stance in hostile_stances
            or other.stance in hostile_stances
            or team.aggression > 0.65
            or other.aggression > 0.65
        )

    def _structure_max_hp(self, kind: str) -> float:
        return {
            "core": 100.0,
            "gun_tower": 70.0,
            "forcefield": 80.0,
            "defense": 60.0,
            "mech_bay": 50.0,
            "town": 48.0,
            "generator": 45.0,
            "relay": 40.0,
            "room": 35.0,
            "road": 28.0,
            "maze": 30.0,
            "wall": 25.0,
        }.get(kind, 30.0)

    def _make_structure(
        self, team: Team, kind: str, pos: Point, size: float, cooldown: float = 0.0
    ) -> Structure:
        max_hp = self._structure_max_hp(kind)
        return Structure(kind=kind, pos=pos, size=size, team=team, hp=max_hp, max_hp=max_hp, cooldown=cooldown)

    def _build_structure(self, team: Team) -> None:
        ring = len(team.structures) // 6 + 1
        angle = random.random() * math.tau
        radius = 50 + ring * 16
        pos = team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius
        team.structures.append(self._make_structure(team, "wall", pos, 16))
        if team.resources % 4 == 0:
            self._add_generator(team)
        elif team.resources % 3 == 0:
            self._add_relay(team)
        self._log("Expanded fortifications.", team=team)

    def _draw(self) -> None:
        self.screen.fill((12, 12, 18))
        original_cam = self.camera.pos.copy()
        self.camera.pos += self.shake_offset
        # Snap camera to whole pixels for rendering (reduces jitter from float->int truncation).
        snapped_cam = Point(round(self.camera.pos.x), round(self.camera.pos.y))
        self.camera.pos = snapped_cam
        self._draw_tiles()
        self._draw_structures()
        self._draw_projectiles()
        self._draw_explosions()
        self._draw_disasters()
        self._draw_aliens()
        self._draw_native_hives()
        self._draw_native_queens()
        self._draw_water_nests()
        self._draw_water_monsters()
        self._draw_sand_worms()
        self._draw_dinosaurs()
        self._draw_vehicles()
        self._draw_mechs()
        self._draw_ships()
        self._draw_robots()
        self._draw_death_markers()
        self.camera.pos = original_cam
        self._draw_overlays()
        if self.show_help:
            self._draw_help()
        if self.show_settings:
            self._draw_settings()
        self._draw_region_banner()
        self._draw_day_night_overlay()
        if self.quit_armed:
            self._draw_quit_overlay()
        self._present()

    def _present(self) -> None:
        scale, offset = self._render_scale_and_offset()
        target_width = max(1, int(self.view_size.x * scale))
        target_height = max(1, int(self.view_size.y * scale))

        # Clear in case rounding leaves uncovered pixels.
        self.display.fill((0, 0, 0))

        if target_width == int(self.view_size.x) and target_height == int(self.view_size.y):
            self.display.blit(self.screen, offset)
        else:
            # Cache the scaled surface to avoid per-frame allocations (critical for 1440p/4K windows).
            cache = getattr(self, "_scaled_present_cache", None)
            if cache is None or cache.get_width() != target_width or cache.get_height() != target_height:
                self._scaled_present_cache = pygame.Surface((target_width, target_height)).convert()
                cache = self._scaled_present_cache

            try:
                pygame.transform.scale(self.screen, (target_width, target_height), cache)
            except TypeError:
                # Older pygame builds may not support the dest argument.
                cache = pygame.transform.scale(self.screen, (target_width, target_height))
                self._scaled_present_cache = cache

            self.display.blit(cache, offset)

        pygame.display.flip()


    def _render_scale_and_offset(self) -> Tuple[float, Tuple[int, int]]:
        # Cover scaling: fill the window (no bars) while preserving aspect ratio; crop overflow.
        scale = max(self.screen_size.x / self.view_size.x, self.screen_size.y / self.view_size.y)
        target_width = int(self.view_size.x * scale)
        target_height = int(self.view_size.y * scale)
        offset = (
            int((self.screen_size.x - target_width) / 2),
            int((self.screen_size.y - target_height) / 2),
        )
        return scale, offset


    def _ui_safe_rect(self) -> pygame.Rect:
        """Visible portion of the virtual view in view-space pixels (cover scaling crops)."""
        scale, offset = self._render_scale_and_offset()
        if scale <= 0:
            return pygame.Rect(0, 0, int(self.view_size.x), int(self.view_size.y))

        left = (0 - offset[0]) / scale
        top = (0 - offset[1]) / scale
        right = (self.screen_size.x - offset[0]) / scale
        bottom = (self.screen_size.y - offset[1]) / scale

        left = max(0.0, min(self.view_size.x, left))
        top = max(0.0, min(self.view_size.y, top))
        right = max(0.0, min(self.view_size.x, right))
        bottom = max(0.0, min(self.view_size.y, bottom))

        l_i = int(math.ceil(left))
        t_i = int(math.ceil(top))
        r_i = int(math.floor(right))
        b_i = int(math.floor(bottom))

        if r_i <= l_i or b_i <= t_i:
            return pygame.Rect(0, 0, int(self.view_size.x), int(self.view_size.y))

        return pygame.Rect(l_i, t_i, r_i - l_i, b_i - t_i)


    def _display_to_view(self, pos: Tuple[int, int]) -> Point:
        scale, offset = self._render_scale_and_offset()
        if scale <= 0:
            return Point(pos)
        x = (pos[0] - offset[0]) / scale
        y = (pos[1] - offset[1]) / scale
        x = max(0.0, min(self.view_size.x - 1, x))
        y = max(0.0, min(self.view_size.y - 1, y))
        return Point(x, y)


    def _draw_tiles(self) -> None:
        start_x = int(self.camera.pos.x // TILE_SIZE)
        start_y = int(self.camera.pos.y // TILE_SIZE)
        end_x = start_x + int(self.view_size.x) // TILE_SIZE + 2
        end_y = start_y + int(self.view_size.y) // TILE_SIZE + 2
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                tile = self.wasteland.tile_at_grid(x, y)
                if not tile:
                    continue
                color = self._blended_tile_color(x, y, tile)
                rect = pygame.Rect(
                    x * TILE_SIZE - self.camera.pos.x,
                    y * TILE_SIZE - self.camera.pos.y,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                pygame.draw.rect(self.screen, color, rect)
                if self.high_detail:
                    self._draw_micro_detail(rect, color, tile)
                if tile.scrap > 0:
                    pygame.draw.circle(
                        self.screen,
                        (120, 200, 220),
                        rect.center,
                        2 + tile.scrap,
                    )
                if tile.alloy > 0:
                    pygame.draw.circle(
                        self.screen,
                        (200, 170, 120),
                        rect.center + Point(-4, 3),
                        2 + tile.alloy,
                    )
                if tile.crystal > 0:
                    pygame.draw.circle(
                        self.screen,
                        (150, 220, 255),
                        rect.center + Point(4, -3),
                        2 + tile.crystal,
                    )
                if tile.capacitor > 0:
                    pygame.draw.circle(
                        self.screen,
                        (255, 120, 160),
                        rect.center + Point(0, -6),
                        2 + tile.capacitor,
                    )
                if tile.river:
                    pygame.draw.rect(self.screen, (60, 90, 140), rect, 0)
                if tile.foliage > 0.4:
                    pygame.draw.circle(self.screen, (70, 120, 70), rect.center, 3)

    def _blended_tile_color(self, x: int, y: int, tile: Tile) -> Tuple[int, int, int]:
        # Cache tile color blending; recompute only when the 3x3 neighborhood changes.
        stamp = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbor = self.wasteland.tile_at_grid(x + dx, y + dy)
                if neighbor is None:
                    continue
                stamp = (stamp * 1315423911 + (neighbor.static_sig ^ (neighbor.version * 2654435761))) & 0xFFFFFFFF

        if tile.cached_stamp == stamp:
            return tile.cached_color

        h_sum = 0.0
        n_count = 0
        scrap = 0
        alloy = 0
        crystal = 0
        capacitor = 0
        rock_count = 0
        c_ridge = c_dune = c_bog = c_oasis = c_glacier = c_waste = 0

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbor = self.wasteland.tile_at_grid(x + dx, y + dy)
                if neighbor is None:
                    continue
                n_count += 1
                h_sum += neighbor.height
                scrap += neighbor.scrap
                alloy += neighbor.alloy
                crystal += neighbor.crystal
                capacitor += neighbor.capacitor
                rock_count += 1 if neighbor.rock else 0
                b = neighbor.biome
                if b == 'ridge':
                    c_ridge += 1
                elif b == 'dune':
                    c_dune += 1
                elif b == 'bog':
                    c_bog += 1
                elif b == 'oasis':
                    c_oasis += 1
                elif b == 'glacier':
                    c_glacier += 1
                else:
                    c_waste += 1

        if n_count <= 0:
            tile.cached_color = (60, 60, 60)
            tile.cached_stamp = stamp
            return tile.cached_color

        avg_height = h_sum / n_count
        base = 60 + int(avg_height * 70)
        tint = 35 if rock_count >= 4 else 0
        scrap_glow = 40 if scrap * 2 > 40 else scrap * 2
        crystal_glow = 30 if crystal * 3 > 30 else crystal * 3
        capacitor_glow = 25 if capacitor * 3 > 25 else capacitor * 3

        dominant = tile.biome
        best = -1
        for name, count in (('ridge', c_ridge), ('dune', c_dune), ('bog', c_bog), ('oasis', c_oasis), ('glacier', c_glacier), ('waste', c_waste)):
            if count > best:
                dominant = name
                best = count

        shift = BIOME_SHIFT.get(dominant, (0, 0, 0))
        r = base + tint + shift[0]
        g = base - 10 + scrap_glow + (crystal_glow // 2) + shift[1]
        b = base - 25 + tint + (capacitor_glow // 2) + shift[2]
        color = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

        tile.cached_color = color
        tile.cached_stamp = stamp
        return color


    def _draw_micro_detail(self, rect: pygame.Rect, color: Tuple[int, int, int], tile: Tile) -> None:
        # Precomputed deterministic micro-details per tile for performance.
        for inset, tone in tile.micro:
            micro_color = (
                max(0, min(255, color[0] + tone)),
                max(0, min(255, color[1] + tone)),
                max(0, min(255, color[2] + tone)),
            )
            micro_rect = pygame.Rect(
                rect.x + inset,
                rect.y + inset,
                TILE_SIZE - inset * 2,
                TILE_SIZE - inset * 2,
            )
            pygame.draw.rect(self.screen, micro_color, micro_rect)


    def _draw_structures(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for team in self.teams:
            if team.extinct:
                continue
            base_color, accent, panel = self._team_style_colors(team)
            for structure in team.structures:
                if not render_rect.collidepoint(structure.pos):
                    continue
                screen_pos = self.camera.world_to_screen(structure.pos)
                if structure.kind == "core":
                    pygame.draw.circle(self.screen, base_color, screen_pos, structure.size)
                    pygame.draw.circle(self.screen, panel, screen_pos, structure.size - 6)
                    pygame.draw.circle(self.screen, accent, screen_pos, structure.size - 12)
                    core_rng = random.Random(int(structure.pos.x * 7 + structure.pos.y * 13))
                    for _ in range(4):
                        angle = core_rng.random() * math.tau
                        ring = structure.size - 10
                        dot = Point(
                            screen_pos.x + math.cos(angle) * ring,
                            screen_pos.y + math.sin(angle) * ring,
                        )
                        pygame.draw.circle(self.screen, (200, 200, 210), dot, 2)
                    name_text = self.font.render(team.name, True, (230, 230, 240))
                    name_pos = (screen_pos.x - name_text.get_width() // 2, screen_pos.y - structure.size - 18)
                    self.screen.blit(name_text, name_pos)
                elif structure.kind == "maze":
                    rect = pygame.Rect(screen_pos.x - 12, screen_pos.y - 4, 24, 8)
                    pygame.draw.rect(self.screen, base_color, rect, border_radius=3)
                    pygame.draw.rect(self.screen, (20, 20, 25), rect.inflate(-6, -2), border_radius=2)
                    pygame.draw.line(self.screen, (180, 180, 200), rect.midleft, rect.midright, 1)
                elif structure.kind == "room":
                    size = structure.size
                    rect = pygame.Rect(screen_pos.x - size / 2, screen_pos.y - size / 2, size, size)
                    pygame.draw.rect(self.screen, base_color, rect, border_radius=6)
                    pygame.draw.rect(self.screen, (25, 25, 30), rect.inflate(-8, -8), border_radius=4)
                    pygame.draw.rect(self.screen, (180, 180, 200), rect.inflate(-12, -12), 1, border_radius=3)
                    self._draw_debris(rect, accent, int(structure.pos.x + structure.pos.y))
                elif structure.kind == "defense":
                    pygame.draw.circle(self.screen, base_color, screen_pos, 10, 2)
                    pygame.draw.circle(self.screen, (20, 20, 30), screen_pos, 6)
                    pygame.draw.line(
                        self.screen,
                        (220, 120, 140),
                        screen_pos + Point(-6, 0),
                        screen_pos + Point(6, 0),
                        2,
                    )
                elif structure.kind == "gun_tower":
                    pygame.draw.circle(self.screen, (200, 160, 120), screen_pos, 9)
                    pygame.draw.circle(self.screen, (20, 20, 30), screen_pos, 5)
                    pygame.draw.line(
                        self.screen,
                        (240, 180, 120),
                        screen_pos + Point(-5, -2),
                        screen_pos + Point(5, 2),
                        2,
                    )
                    self._draw_glow(screen_pos, (220, 170, 120))
                elif structure.kind == "generator":
                    pygame.draw.circle(self.screen, accent, screen_pos, 9)
                    pygame.draw.circle(self.screen, panel, screen_pos, 5)
                    pygame.draw.circle(self.screen, (255, 240, 200), screen_pos, 2)
                elif structure.kind == "relay":
                    rect = pygame.Rect(screen_pos.x - 8, screen_pos.y - 12, 16, 24)
                    pygame.draw.rect(self.screen, accent, rect, border_radius=3)
                    pygame.draw.rect(self.screen, (25, 25, 30), rect.inflate(-6, -6), border_radius=2)
                    pygame.draw.line(self.screen, (200, 220, 230), rect.midtop, rect.midbottom, 1)
                elif structure.kind == "forcefield":
                    ring = pygame.Rect(screen_pos.x - 18, screen_pos.y - 18, 36, 36)
                    pygame.draw.ellipse(self.screen, accent, ring, 2)
                    self._draw_glow(screen_pos, accent)
                elif structure.kind == "town":
                    rect = pygame.Rect(screen_pos.x - 10, screen_pos.y - 10, 20, 20)
                    pygame.draw.rect(self.screen, accent, rect, border_radius=4)
                    pygame.draw.rect(self.screen, panel, rect.inflate(-6, -6), border_radius=3)
                    self._draw_debris(rect, base_color, int(structure.pos.x * 2 + structure.pos.y))
                elif structure.kind == "road":
                    rect = pygame.Rect(screen_pos.x - 10, screen_pos.y - 3, 20, 6)
                    pygame.draw.rect(self.screen, (90, 90, 100), rect, border_radius=2)
                    pygame.draw.line(self.screen, (140, 140, 150), rect.midleft, rect.midright, 1)
                elif structure.kind == "mech_bay":
                    rect = pygame.Rect(screen_pos.x - 12, screen_pos.y - 8, 24, 16)
                    pygame.draw.rect(self.screen, accent, rect, border_radius=3)
                    pygame.draw.rect(self.screen, panel, rect.inflate(-6, -6), border_radius=2)
                    pygame.draw.line(self.screen, (220, 200, 255), rect.midleft, rect.midright, 1)
                else:
                    size = structure.size
                    rect = pygame.Rect(screen_pos.x - size / 2, screen_pos.y - size / 2, size, size)
                    pygame.draw.rect(self.screen, base_color, rect, border_radius=4)
                    pygame.draw.rect(self.screen, panel, rect.inflate(-6, -6), border_radius=3)

    def _draw_robots(self) -> None:
        render_rect = self._render_rect().inflate(120, 120)
        for team in self.teams:
            if team.extinct:
                continue
            for robot in team.robots:
                if not render_rect.collidepoint(robot.pos):
                    continue
                self._draw_robot_sprite(robot, team)
            for civilian in team.civilians:
                if not render_rect.collidepoint(civilian.pos):
                    continue
                self._draw_civilian_sprite(civilian, team)
            for repair_bot in team.repair_bots:
                if not render_rect.collidepoint(repair_bot.pos):
                    continue
                self._draw_repair_bot_sprite(repair_bot, team)
            for troop in team.troops:
                if not render_rect.collidepoint(troop.pos):
                    continue
                self._draw_troop_sprite(troop, team)
            for general in team.generals:
                if not render_rect.collidepoint(general.pos):
                    continue
                self._draw_general_sprite(general, team)
            for sniper in team.snipers:
                if not render_rect.collidepoint(sniper.pos):
                    continue
                self._draw_sniper_sprite(sniper, team)
            for drone in team.drones:
                if not render_rect.collidepoint(drone.pos):
                    continue
                self._draw_drone_sprite(drone, team)
            for sprite in team.sprites:
                if not render_rect.collidepoint(sprite.pos):
                    continue
                self._draw_sprite_sprite(sprite, team)

    def _draw_projectiles(self) -> None:
        render_rect = self._render_rect().inflate(40, 40)
        for projectile in self.projectiles:
            if not render_rect.collidepoint(projectile.pos):
                continue
            screen_pos = self.camera.world_to_screen(projectile.pos)
            color = (255, 90, 140) if projectile.kind == "laser" else (120, 200, 255)
            pygame.draw.circle(self.screen, color, screen_pos, 2)
            if self._night_glow_strength() > 0:
                glow = self._get_glow_sprite(color, 4, self._night_glow_strength())
                self.screen.blit(glow, (screen_pos.x - 4, screen_pos.y - 4))

    def _draw_explosions(self) -> None:
        render_rect = self._render_rect().inflate(80, 80)
        for explosion in self.explosions:
            if not render_rect.collidepoint(explosion.pos):
                continue
            screen_pos = self.camera.world_to_screen(explosion.pos)
            radius = max(2, int(explosion.radius))
            ring = pygame.Rect(screen_pos.x - radius, screen_pos.y - radius, radius * 2, radius * 2)
            pygame.draw.ellipse(self.screen, explosion.color, ring, 2)
            if self._night_glow_strength() > 0:
                glow = self._get_glow_sprite(explosion.color, radius, self._night_glow_strength())
                self.screen.blit(glow, (screen_pos.x - radius, screen_pos.y - radius))

    def _draw_disasters(self) -> None:
        render_rect = self._render_rect().inflate(200, 200)
        for disaster in self.disasters:
            if not render_rect.collidepoint(disaster.pos):
                continue
            screen_pos = self.camera.world_to_screen(disaster.pos)
            ring = pygame.Rect(
                screen_pos.x - disaster.radius,
                screen_pos.y - disaster.radius,
                disaster.radius * 2,
                disaster.radius * 2,
            )
            pygame.draw.ellipse(self.screen, (120, 80, 60), ring, 2)
            if self._night_glow_strength() > 0:
                if self.high_detail:
                    glow = pygame.Surface((int(disaster.radius * 2), int(disaster.radius * 2)), pygame.SRCALPHA)
                    glow.fill((140, 90, 70, int(self._night_glow_strength() * 0.6)))
                    self.screen.blit(glow, (screen_pos.x - disaster.radius, screen_pos.y - disaster.radius))

    def _night_glow_strength(self) -> int:
        cycle = (self.day_timer / DAY_LENGTH) * math.tau
        return int(max(0, math.sin(cycle)) * GLOW_ALPHA)

    def _get_glow_sprite(self, color: Tuple[int, int, int], radius: int, alpha: int) -> pygame.Surface:
            key = (tuple(color), int(radius), int(alpha))
            surf = self._glow_cache.get(key)
            if surf is not None:
                return surf
            r = max(1, int(radius))
            a = max(0, min(255, int(alpha)))
            size = r * 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (color[0], color[1], color[2], a), (r, r), r)
            self._glow_cache[key] = surf
            return surf

    def _draw_glow(self, position: Point, color: Tuple[int, int, int]) -> None:
        strength = self._night_glow_strength()
        if strength <= 0:
            return
        glow = self._get_glow_sprite(color, 7, strength)
        self.screen.blit(glow, (position.x - 7, position.y - 7))
    def _update_explosions(self, dt: float) -> None:
        survivors: List[Explosion] = []
        for explosion in self.explosions:
            explosion.ttl -= dt
            explosion.radius += dt * 40
            if explosion.ttl > 0:
                survivors.append(explosion)
        self.explosions = survivors

    def _add_explosion(self, pos: Point, color: Tuple[int, int, int], intensity: float) -> None:
        self.explosions.append(Explosion(pos=pos.copy(), radius=6 + intensity * 6, color=color, ttl=0.5))
        view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
        if pos.distance_to(view_center) < 420:
            self.shake_intensity = min(1.0, self.shake_intensity + intensity * 0.6)

    def _update_screen_shake(self, dt: float) -> None:
        if self.shake_intensity <= 0:
            self.shake_offset = Point(0, 0)
            return
        jitter = Point(random.uniform(-1, 1), random.uniform(-1, 1))
        self.shake_offset = jitter * (6 * self.shake_intensity)
        self.shake_intensity = max(0.0, self.shake_intensity - dt * SHAKE_DECAY)

    def _draw_aliens(self) -> None:
        render_rect = self._render_rect().inflate(120, 120)
        for alien in self.aliens:
            if not render_rect.collidepoint(alien.pos):
                continue
            self._draw_alien_sprite(alien)

    def _draw_native_hives(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for hive in self.native_hives:
            if not render_rect.collidepoint(hive.pos):
                continue
            screen_pos = self.camera.world_to_screen(hive.pos)
            palette = {
                "lumen": ((110, 70, 160), (160, 120, 200)),
                "brine": ((70, 140, 120), (120, 200, 170)),
                "ember": ((160, 90, 70), (220, 140, 120)),
            }
            outer_color, ring_color = palette.get(hive.kind, ((110, 70, 160), (160, 120, 200)))
            outer = pygame.Rect(screen_pos.x - 16, screen_pos.y - 16, 32, 32)
            pygame.draw.ellipse(self.screen, outer_color, outer)
            pygame.draw.ellipse(self.screen, (40, 20, 60), outer.inflate(-8, -8))
            for i in range(6):
                angle = (i / 6) * math.tau
                pulse = 2 + math.sin(self.day_timer * 3 + i) * 2
                ring = pygame.Rect(
                    screen_pos.x + math.cos(angle) * 12 - pulse,
                    screen_pos.y + math.sin(angle) * 12 - pulse,
                    pulse * 2,
                    pulse * 2,
                )
                pygame.draw.ellipse(self.screen, ring_color, ring)
            self._draw_glow(screen_pos, ring_color)

    def _draw_native_queens(self) -> None:
        render_rect = self._render_rect().inflate(200, 200)
        for queen in self.native_queens:
            if not render_rect.collidepoint(queen.pos):
                continue
            screen_pos = self.camera.world_to_screen(queen.pos)
            palette = {
                "lumen": ((200, 120, 220), (160, 90, 210)),
                "brine": ((140, 220, 180), (90, 170, 140)),
                "ember": ((230, 140, 120), (180, 90, 60)),
            }
            body_color, tendril_color = palette.get(queen.kind, ((200, 120, 220), (160, 90, 210)))
            body_radius = 18 + int(math.sin(self.day_timer * 2.2) * 2)
            body = pygame.Rect(
                screen_pos.x - body_radius,
                screen_pos.y - body_radius,
                body_radius * 2,
                body_radius * 2,
            )
            pygame.draw.ellipse(self.screen, body_color, body)
            eye_offset = Point(6, -6)
            pygame.draw.circle(self.screen, (40, 10, 60), screen_pos + eye_offset, 4)
            for i in range(5):
                sway = math.sin(self.day_timer * 3 + i) * 4
                start = screen_pos + Point(-10 + i * 5, 10)
                end = screen_pos + Point(-14 + i * 6, 26 + sway)
                pygame.draw.line(self.screen, tendril_color, start, end, 2)
            self._draw_glow(screen_pos, body_color)

    def _draw_water_nests(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for nest in self.water_nests:
            if not render_rect.collidepoint(nest.pos):
                continue
            screen_pos = self.camera.world_to_screen(nest.pos)
            base = pygame.Rect(screen_pos.x - 14, screen_pos.y - 10, 28, 20)
            pygame.draw.ellipse(self.screen, (60, 120, 160), base)
            pygame.draw.ellipse(self.screen, (20, 40, 60), base.inflate(-8, -8))
            self._draw_glow(screen_pos, (80, 140, 200))

    def _draw_water_monsters(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for monster in self.water_monsters:
            if not render_rect.collidepoint(monster.pos):
                continue
            screen_pos = self.camera.world_to_screen(monster.pos)
            body = pygame.Rect(screen_pos.x - 10, screen_pos.y - 8, 20, 16)
            pygame.draw.ellipse(self.screen, (80, 140, 200), body)
            fin = pygame.Rect(screen_pos.x - 2, screen_pos.y - 14, 4, 8)
            pygame.draw.rect(self.screen, (120, 200, 230), fin, border_radius=2)
            self._draw_glow(screen_pos, (120, 200, 230))

    def _draw_sand_worms(self) -> None:
        render_rect = self._render_rect().inflate(200, 200)
        for worm in self.sand_worms:
            if not render_rect.collidepoint(worm.pos):
                continue
            screen_pos = self.camera.world_to_screen(worm.pos)
            head = pygame.Rect(screen_pos.x - 12, screen_pos.y - 8, 24, 16)
            pygame.draw.ellipse(self.screen, (180, 120, 80), head)
            for idx in range(4):
                offset = Point(0, 10 + idx * 6)
                segment = pygame.Rect(screen_pos.x - 10, screen_pos.y - 4 + offset.y, 20, 10)
                pygame.draw.ellipse(self.screen, (150, 90, 60), segment)
            self._draw_glow(screen_pos, (200, 140, 100))

    def _draw_dinosaurs(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for dino in self.dinosaurs:
            if not render_rect.collidepoint(dino.pos):
                continue
            screen_pos = self.camera.world_to_screen(dino.pos)
            pulse = 2 + math.sin(self.day_timer * 4 + dino.pos.x * 0.01) * 2
            palette = {
                "reef": ((120, 200, 220), (80, 140, 180)),
                "ember": ((220, 160, 120), (180, 90, 60)),
                "brine": ((120, 220, 180), (70, 160, 120)),
            }
            body_color, cap_color = palette.get(dino.kind, ((120, 200, 220), (80, 140, 180)))
            bell = pygame.Rect(screen_pos.x - 12, screen_pos.y - 10, 24, 18)
            pygame.draw.ellipse(self.screen, body_color, bell.inflate(pulse, pulse))
            cap = pygame.Rect(screen_pos.x - 8, screen_pos.y - 14, 16, 10)
            pygame.draw.ellipse(self.screen, cap_color, cap)
            for i in range(4):
                sway = math.sin(self.day_timer * 3 + i + dino.pos.y * 0.02) * 4
                start = screen_pos + Point(-6 + i * 4, 6)
                end = screen_pos + Point(-8 + i * 5, 18 + sway)
                pygame.draw.line(self.screen, body_color, start, end, 2)
            self._draw_glow(screen_pos, body_color)

    def _draw_vehicles(self) -> None:
        render_rect = self._render_rect().inflate(140, 140)
        for team in self.teams:
            if team.extinct:
                continue
            base_color, accent, panel = self._team_style_colors(team)
            for vehicle in team.vehicles:
                if not render_rect.collidepoint(vehicle.pos):
                    continue
                screen_pos = self.camera.world_to_screen(vehicle.pos)
                body = pygame.Rect(screen_pos.x - 10, screen_pos.y - 6, 20, 12)
                pygame.draw.rect(self.screen, base_color, body, border_radius=3)
                pygame.draw.rect(self.screen, panel, body.inflate(-6, -4), border_radius=2)
                turret = pygame.Rect(screen_pos.x - 4, screen_pos.y - 10, 8, 6)
                pygame.draw.rect(self.screen, accent, turret, border_radius=2)
                if vehicle.role == "carrier":
                    pygame.draw.circle(self.screen, accent, screen_pos + Point(0, 6), 3)
                self._draw_glow(screen_pos, accent)

    def _draw_mechs(self) -> None:
        render_rect = self._render_rect().inflate(160, 160)
        for team in self.teams:
            if team.extinct:
                continue
            base_color, accent, panel = self._team_style_colors(team)
            for mech in team.mechs:
                if not render_rect.collidepoint(mech.pos):
                    continue
                screen_pos = self.camera.world_to_screen(mech.pos)
                torso = pygame.Rect(screen_pos.x - 8, screen_pos.y - 12, 16, 18)
                pygame.draw.rect(self.screen, base_color, torso, border_radius=4)
                pygame.draw.rect(self.screen, panel, torso.inflate(-6, -6), border_radius=3)
                head = pygame.Rect(screen_pos.x - 4, screen_pos.y - 18, 8, 6)
                pygame.draw.rect(self.screen, (200, 200, 230), head, border_radius=2)
                pygame.draw.line(
                    self.screen,
                    (220, 120, 140),
                    (screen_pos.x - 10, screen_pos.y),
                    (screen_pos.x + 10, screen_pos.y),
                    2,
                )
                phase = math.sin(self.day_timer * 3 + mech.pos.x * 0.01)
                for offset in (-6, 6):
                    orb = Point(screen_pos.x + offset, screen_pos.y + 12 + phase * 2)
                    pygame.draw.circle(self.screen, accent, orb, 3)
                    self._draw_glow(orb, accent)
                self._draw_glow(screen_pos, accent)

    def _draw_ships(self) -> None:
        render_rect = self._render_rect().inflate(200, 200)
        for team in self.teams:
            if team.extinct:
                continue
            base_color, accent, panel = self._team_style_colors(team)
            for ship in team.ships:
                if not render_rect.collidepoint(ship.pos):
                    continue
                screen_pos = self.camera.world_to_screen(ship.pos)
                hull = pygame.Rect(screen_pos.x - 16, screen_pos.y - 6, 32, 12)
                pygame.draw.rect(self.screen, base_color, hull, border_radius=5)
                pygame.draw.rect(self.screen, panel, hull.inflate(-8, -4), border_radius=4)
                wing_left = pygame.Rect(screen_pos.x - 22, screen_pos.y - 2, 6, 8)
                wing_right = pygame.Rect(screen_pos.x + 16, screen_pos.y - 2, 6, 8)
                pygame.draw.rect(self.screen, accent, wing_left, border_radius=2)
                pygame.draw.rect(self.screen, accent, wing_right, border_radius=2)
                self._draw_glow(screen_pos, accent)

    def _draw_robot_sprite(self, robot: Robot, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(robot.pos)
        rng = random.Random((robot.id_tag * 97) ^ team.style_seed)
        body_w = rng.randint(10, 14)
        body_h = rng.randint(12, 16)
        head_size = rng.randint(4, 6)
        limb = rng.randint(4, 7)
        base_color, accent, panel = self._team_style_colors(team)
        torso = pygame.Rect(
            screen_pos.x - body_w / 2,
            screen_pos.y - body_h / 2,
            body_w,
            body_h,
        )
        pygame.draw.rect(self.screen, base_color, torso, border_radius=3)
        pygame.draw.rect(self.screen, panel, torso.inflate(-4, -4), border_radius=2)
        head_center = Point(screen_pos.x, screen_pos.y - body_h / 2 - head_size / 2 + 2)
        pygame.draw.circle(self.screen, accent, head_center, head_size)
        pygame.draw.circle(self.screen, panel, head_center, max(1, head_size - 2))
        eye = head_center + Point(head_size / 2 - 1, -1)
        pygame.draw.circle(self.screen, (200, 240, 255), eye, 2)
        pygame.draw.line(
            self.screen,
            accent,
            (screen_pos.x - body_w / 2 - limb, screen_pos.y - 2),
            (screen_pos.x - body_w / 2, screen_pos.y + 2),
            2,
        )
        pygame.draw.line(
            self.screen,
            accent,
            (screen_pos.x + body_w / 2, screen_pos.y + 2),
            (screen_pos.x + body_w / 2 + limb, screen_pos.y - 2),
            2,
        )
        pygame.draw.line(
            self.screen,
            accent,
            (screen_pos.x - body_w / 3, screen_pos.y + body_h / 2),
            (screen_pos.x - body_w / 2, screen_pos.y + body_h / 2 + limb),
            2,
        )
        pygame.draw.line(
            self.screen,
            accent,
            (screen_pos.x + body_w / 3, screen_pos.y + body_h / 2),
            (screen_pos.x + body_w / 2, screen_pos.y + body_h / 2 + limb),
            2,
        )
        if robot is self.selected:
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, body_w + 8, 1)
        self._draw_glow(screen_pos, accent)

    def _draw_civilian_sprite(self, civilian: Civilian, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(civilian.pos)
        base_color, accent, panel = self._team_style_colors(team)
        body = pygame.Rect(screen_pos.x - 5, screen_pos.y - 6, 10, 12)
        pygame.draw.rect(self.screen, accent, body, border_radius=3)
        pygame.draw.rect(self.screen, panel, body.inflate(-6, -6), border_radius=2)
        pygame.draw.circle(self.screen, (230, 230, 210), screen_pos + Point(0, -8), 3)

    def _draw_repair_bot_sprite(self, bot: RepairBot, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(bot.pos)
        base_color, accent, panel = self._team_style_colors(team)
        body = pygame.Rect(screen_pos.x - 6, screen_pos.y - 6, 12, 12)
        pygame.draw.rect(self.screen, (160, 210, 220), body, border_radius=3)
        pygame.draw.rect(self.screen, base_color, body.inflate(-6, -6), border_radius=2)
        pygame.draw.line(self.screen, (240, 240, 255), body.midleft, body.midright, 1)

    def _team_style_colors(self, team: Team) -> Tuple[Color, Color, Color]:
        rng = random.Random(team.style_seed)
        shift = rng.randint(-25, 25)
        base = (
            max(40, min(255, team.color[0] + shift)),
            max(40, min(255, team.color[1] + shift)),
            max(40, min(255, team.color[2] + shift)),
        )
        accent = (
            min(255, base[0] + rng.randint(30, 60)),
            min(255, base[1] + rng.randint(20, 50)),
            min(255, base[2] + rng.randint(20, 50)),
        )
        panel = (
            max(20, base[0] - rng.randint(40, 70)),
            max(20, base[1] - rng.randint(40, 70)),
            max(20, base[2] - rng.randint(40, 70)),
        )
        return base, accent, panel

    def _draw_troop_sprite(self, troop: Troop, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(troop.pos)
        base_color, accent, panel = self._team_style_colors(team)
        body = pygame.Rect(screen_pos.x - 5, screen_pos.y - 5, 10, 10)
        pygame.draw.rect(self.screen, base_color, body, border_radius=2)
        pygame.draw.rect(self.screen, panel, body.inflate(-4, -4), border_radius=2)
        self._draw_glow(screen_pos, accent)

    def _draw_general_sprite(self, general: General, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(general.pos)
        base_color, accent, panel = self._team_style_colors(team)
        body = pygame.Rect(screen_pos.x - 6, screen_pos.y - 7, 12, 14)
        pygame.draw.rect(self.screen, accent, body, border_radius=3)
        pygame.draw.rect(self.screen, base_color, body.inflate(-4, -4), border_radius=2)
        self._draw_glow(screen_pos, accent)

    def _draw_sniper_sprite(self, sniper: Sniper, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(sniper.pos)
        base_color, accent, panel = self._team_style_colors(team)
        body = pygame.Rect(screen_pos.x - 4, screen_pos.y - 6, 8, 12)
        pygame.draw.rect(self.screen, base_color, body, border_radius=2)
        pygame.draw.line(self.screen, accent, body.midleft, body.midright, 1)
        self._draw_glow(screen_pos, accent)

    def _draw_drone_sprite(self, drone: Drone, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(drone.pos)
        base_color, accent, panel = self._team_style_colors(team)
        pygame.draw.circle(self.screen, accent, screen_pos, 5)
        pygame.draw.circle(self.screen, panel, screen_pos, 3)
        self._draw_glow(screen_pos, accent)

    def _draw_sprite_sprite(self, sprite: Sprite, team: Team) -> None:
        screen_pos = self.camera.world_to_screen(sprite.pos)
        base_color, accent, panel = self._team_style_colors(team)
        pygame.draw.circle(self.screen, accent, screen_pos, 4)
        self._draw_glow(screen_pos, accent)

    def _draw_alien_sprite(self, alien: Alien) -> None:
        screen_pos = self.camera.world_to_screen(alien.pos)
        rng = random.Random(hash((alien.kind, alien.team.name)))
        base = rng.randint(8, 12)
        color = (160, 255, 200) if alien.kind == "sentinel" else (255, 120, 120)
        if alien.kind == "warden":
            color = (180, 140, 255)
        pygame.draw.circle(self.screen, color, screen_pos, base)
        pygame.draw.circle(self.screen, (20, 20, 25), screen_pos, base - 4)
        for idx in range(3):
            angle = idx * (math.tau / 3) + rng.random() * 0.4
            tip = Point(screen_pos.x + math.cos(angle) * (base + 6), screen_pos.y + math.sin(angle) * (base + 6))
            pygame.draw.line(self.screen, color, screen_pos, tip, 2)
        self._draw_glow(screen_pos, color)

    def _draw_overlays(self) -> None:
        if self.selected:
            detail = (
                f"Selected: {self.selected.team.name} #{self.selected.id_tag} "
                f"state: {self.selected.state} carry: {self.selected.carry}"
            )
            surf = self.big_font.render(detail, True, (230, 230, 230))
            self.screen.blit(surf, (24, 24))
        if self.selected_info:
            info = self.font.render(self.selected_info, True, (200, 200, 210))
            self.screen.blit(info, (24, 48))
        note = self.font.render(
            "WASD move camera, hover for info, click robot to follow, SPACE reset (T cycles cores, H for help, TAB settings, L logs)",
            True,
            (180, 180, 180),
        )
        safe = self._ui_safe_rect()
        self.screen.blit(note, (safe.left + 24, safe.bottom - 32))
        if self.show_logs:
            self._draw_log_panel()
        coords = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
        coord_text = self.font.render(f"Cam: {coords.x:.0f}, {coords.y:.0f}", True, (180, 180, 200))
        safe = self._ui_safe_rect()
        self.screen.blit(coord_text, (safe.right - coord_text.get_width() - 16, safe.bottom - 28))
        self._draw_crosshair()

    def _draw_debris(self, rect: pygame.Rect, color: Color, seed: int) -> None:
        rng = random.Random(seed)
        for _ in range(3):
            offset = Point(rng.randint(-6, 6), rng.randint(-6, 6))
            spot = pygame.Rect(rect.centerx + offset.x - 2, rect.centery + offset.y - 2, 4, 4)
            tone = (
                max(0, min(255, color[0] + rng.randint(-20, 20))),
                max(0, min(255, color[1] + rng.randint(-20, 20))),
                max(0, min(255, color[2] + rng.randint(-20, 20))),
            )
            pygame.draw.rect(self.screen, tone, spot, border_radius=2)

    def _draw_crosshair(self) -> None:
        center = self.mouse_pos
        if not (0 <= center.x <= self.view_size.x and 0 <= center.y <= self.view_size.y):
            return
        color = (220, 180, 200)
        pygame.draw.line(self.screen, color, (center.x - 8, center.y), (center.x - 2, center.y), 2)
        pygame.draw.line(self.screen, color, (center.x + 2, center.y), (center.x + 8, center.y), 2)
        pygame.draw.line(self.screen, color, (center.x, center.y - 8), (center.x, center.y - 2), 2)
        pygame.draw.line(self.screen, color, (center.x, center.y + 2), (center.x, center.y + 8), 2)

    def _draw_death_markers(self) -> None:
        render_rect = self._render_rect().inflate(120, 120)
        for marker in self.death_markers:
            if not render_rect.collidepoint(marker.pos):
                continue
            screen_pos = self.camera.world_to_screen(marker.pos)
            ring = pygame.Rect(screen_pos.x - 6, screen_pos.y - 6, 12, 12)
            pygame.draw.ellipse(self.screen, (80, 80, 110), ring, 2)
            pygame.draw.line(
                self.screen,
                (100, 100, 130),
                (screen_pos.x - 4, screen_pos.y + 4),
                (screen_pos.x + 4, screen_pos.y - 4),
                1,
            )

    def _draw_region_banner(self) -> None:
        if not self.current_region_name:
            return
        label = self.font.render(f"Region: {self.current_region_name}", True, (180, 180, 200))
        safe = self._ui_safe_rect()
        self.screen.blit(label, (safe.left + 24, safe.bottom - 56))

    def _draw_day_night_overlay(self) -> None:
        cycle = (self.day_timer / DAY_LENGTH) * math.tau
        darkness = (1 - math.cos(cycle)) * 0.35
        if darkness <= 0.05:
            return
        overlay = pygame.Surface((int(self.view_size.x), int(self.view_size.y)), pygame.SRCALPHA)
        overlay.fill((10, 12, 18, int(180 * darkness)))
        self.screen.blit(overlay, (0, 0))
        if self.radiation_timer > 0 and self.radiation_timer < 8:
            storm = pygame.Surface((int(self.view_size.x), int(self.view_size.y)), pygame.SRCALPHA)
            storm.fill((40, 120, 80, 40))
            self.screen.blit(storm, (0, 0))


    def _draw_quit_overlay(self) -> None:
        safe = self._ui_safe_rect()

        # Dim only the visible area (cover scaling crops edges).
        dim = pygame.Surface((safe.w, safe.h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        self.screen.blit(dim, (safe.x, safe.y))

        title = self.big_font.render("Press ESC again to quit", True, (245, 245, 250))
        sub = self.font.render("Any other key cancels", True, (210, 210, 220))

        pad_x = 22
        pad_y = 16
        panel_w = max(title.get_width(), sub.get_width()) + pad_x * 2
        panel_h = title.get_height() + sub.get_height() + pad_y * 2 + 8

        cx, cy = safe.centerx, safe.centery
        rect = pygame.Rect(0, 0, panel_w, panel_h)
        rect.center = (cx, cy)

        # Clamp to visible safe area.
        rect.x = max(safe.x, min(safe.right - rect.w, rect.x))
        rect.y = max(safe.y, min(safe.bottom - rect.h, rect.y))

        pygame.draw.rect(self.screen, (18, 18, 26), rect, border_radius=10)
        pygame.draw.rect(self.screen, (230, 230, 240), rect, width=2, border_radius=10)

        self.screen.blit(title, (rect.x + pad_x, rect.y + pad_y))
        self.screen.blit(sub, (rect.x + pad_x, rect.y + pad_y + title.get_height() + 8))

    def _draw_log_panel(self) -> None:
        panel = pygame.Rect(
            int(self.view_size.x) - LOG_PANEL_WIDTH - 16,
            16,
            LOG_PANEL_WIDTH,
            int(self.view_size.y) - 32,
        )
        y = panel.top + 12
        header = self.font.render("Activity Log", True, (200, 200, 220))
        self.screen.blit(header, (panel.left + 12, y))
        y += 22
        visible_teams = self._teams_in_view()
        visible_names = {team.name for team in visible_teams}
        entries = []
        for tag, message in reversed(self.logs):
            if tag == "System" or tag in visible_names:
                entries.append((tag, message))
            if len(entries) >= 16:
                break
        for tag, message in reversed(entries):
            text = self.font.render(f"{tag}: {message}", True, (180, 180, 200))
            self.screen.blit(text, (panel.left + 12, y))
            y += 18

    def _teams_in_view(self) -> List[Team]:
        view_rect = pygame.Rect(
            self.camera.pos.x,
            self.camera.pos.y,
            self.view_size.x,
            self.view_size.y,
        ).inflate(400, 400)
        return [team for team in self.teams if not team.extinct and view_rect.collidepoint(team.base_pos)]

    def _draw_help(self) -> None:
        panel = pygame.Rect(80, 80, int(self.view_size.x) - 160, int(self.view_size.y) - 160)
        pygame.draw.rect(self.screen, (18, 18, 26), panel)
        pygame.draw.rect(self.screen, (90, 90, 110), panel, 2)
        lines = [
            "Help Menu",
            "WASD: move camera",
            "Mouse Click: follow robot",
            "SPACE: reset camera follow",
            "H: toggle this help menu",
            "T: cycle through tribe cores",
            "TAB: open settings",
            "L: toggle activity log",
            "Hover over units to see details (crosshair cursor).",
            "V: toggle VSync | F: fullscreen | R: resizable (settings open)",
            "-/=: adjust render distance (settings open)",
            "Robots gather scrap, alloy, crystal, and capacitors to grow bases.",
            "Civilians gather resources, build towns, roads, and defenses.",
            "Repair bots mend damaged structures after disasters.",
            "Alloy builds maze halls, crystal builds rooms, capacitors power defenses.",
            "Aliens periodically spawn: sentinels defend, raiders attack.",
            "The world expands with new biomes and tribes as you explore.",
            "Vehicles and mechs add heavy support with pulse and laser attacks.",
            "Regions and day/night cycles shift the glow of the battlefield.",
            "Soft SFX are generated for lasers, pulses, and claws.",
            "Hover units, structures, or memorials to see details.",
            "Water natives attack when units enter rivers.",
            "Patrol platoons move in formation and react to threats.",
            "Advanced tribes field warships and heavier formations.",
            "Natives emerge at night and radiation storms sweep the wastes.",
            "Native hives pulse in the distance; queens rise when hives are shattered.",
            "Rare sand worms surface to hunt and trigger earthquakes.",
            "Natural disasters can damage structures; repairs keep cities alive.",
        ]
        y = panel.top + 16
        for line in lines:
            text = self.big_font.render(line, True, (220, 220, 230)) if line == "Help Menu" else self.font.render(
                line, True, (200, 200, 210)
            )
            self.screen.blit(text, (panel.left + 16, y))
            y += 24

    def _draw_settings(self) -> None:
        panel = pygame.Rect(120, 120, int(self.view_size.x) - 240, 260)
        pygame.draw.rect(self.screen, (16, 16, 24), panel)
        pygame.draw.rect(self.screen, (90, 90, 110), panel, 2)
        lines = [
            "Settings (press TAB to close)",
            f"V: VSync {'On' if self.vsync_enabled else 'Off'}",
            f"F: Fullscreen {'On' if self.fullscreen else 'Off'}",
            f"R: Resizable {'On' if self.resizable else 'Off'}",
            f"G: Graphics Detail {'High' if self.high_detail else 'Low'}",
            f"L: Activity Log {'Shown' if self.show_logs else 'Hidden'}",
            f"-/=: Render Distance {self.render_distance_scale:.1f}x",
        ]
        y = panel.top + 18
        for line in lines:
            text = self.big_font.render(line, True, (220, 220, 230)) if line.startswith("Settings") else self.font.render(
                line, True, (200, 200, 210)
            )
            self.screen.blit(text, (panel.left + 16, y))
            y += 26

    def _update_region(self, view_center: Point, dt: float) -> None:
        region_key = self.wasteland.region_key(view_center)
        if region_key not in self.region_names:
            self.region_names[region_key] = self._generate_region_name()
            self.current_region_name = self.region_names[region_key]
            self.region_timer = 4.0
        elif self.current_region_name != self.region_names[region_key]:
            self.current_region_name = self.region_names[region_key]
            self.region_timer = 4.0
        if self.region_timer > 0:
            self.region_timer = max(0.0, self.region_timer - dt)
        else:
            self.current_region_name = ""
        self._maybe_spawn_native_hive(view_center, dt)
        self.tribe_spawn_timer -= dt
        if self.tribe_spawn_timer <= 0:
            self._spawn_new_tribe_if_needed(view_center)
            self.tribe_spawn_timer = random.uniform(8.0, 16.0)

    def _maybe_spawn_native_hive(self, view_center: Point, dt: float) -> None:
        if len(self.native_hives) >= 6:
            return
        self.native_hive_timer -= dt
        if self.native_hive_timer > 0:
            return
        view_rect = pygame.Rect(
            view_center.x - self.view_size.x / 2,
            view_center.y - self.view_size.y / 2,
            self.view_size.x,
            self.view_size.y,
        ).inflate(800, 800)
        for _ in range(12):
            distance = random.randint(900, 1600)
            angle = random.random() * math.tau
            candidate = view_center + Point(math.cos(angle), math.sin(angle)) * distance
            if not view_rect.collidepoint(candidate):
                kind = random.choice(["lumen", "brine", "ember"])
                self.native_hives.append(NativeHive(pos=candidate, kind=kind))
                self._log("A distant native hive pulses in the wastes.")
                break
        self.native_hive_timer = random.uniform(18.0, 36.0)

    def _generate_region_name(self) -> str:
        roots = ["Aether", "Vanta", "Rift", "Solon", "Nyx", "Obsid", "Auric", "Gale"]
        suffixes = ["Reach", "Basin", "Front", "Span", "Hollow", "Dunes", "Wastes", "Cradle"]
        return f"{random.choice(roots)} {random.choice(suffixes)}"

    def _generate_sfx_pack(self) -> Dict[str, List[pygame.mixer.Sound]]:
        return {
            "laser": [self._make_tone(520, 0.12), self._make_tone(610, 0.1)],
            "pulse": [self._make_tone(260, 0.14), self._make_tone(320, 0.12)],
            "claw": [self._make_noise(0.12), self._make_noise(0.1)],
            "roar": [self._make_tone(90, 0.4), self._make_tone(110, 0.35)],
        }

    def _make_tone(self, frequency: float, duration: float) -> pygame.mixer.Sound:
        sample_rate = 22050
        count = int(sample_rate * duration)
        buf = array("h")
        volume = 0.25
        for i in range(count):
            t = i / sample_rate
            wave = math.sin(2 * math.pi * frequency * t) * (1 - t / duration)
            buf.append(int(wave * 32767 * volume))
        return pygame.mixer.Sound(buffer=buf)

    def _make_noise(self, duration: float) -> pygame.mixer.Sound:
        sample_rate = 22050
        count = int(sample_rate * duration)
        buf = array("h")
        volume = 0.2
        for i in range(count):
            decay = 1 - (i / count)
            noise = (random.random() * 2 - 1) * decay
            buf.append(int(noise * 32767 * volume))
        return pygame.mixer.Sound(buffer=buf)

    def _play_sfx(self, kind: str, team: Optional[Team], pos: Optional[Point] = None) -> None:
        pack = self.sfx.get(kind)
        if not pack:
            return
        if pos is not None:
            view_rect = self._view_rect().inflate(200, 200)
            if not view_rect.collidepoint(pos):
                return
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            distance = pos.distance_to(view_center)
            max_dist = max(self.view_size.x, self.view_size.y) * 0.75
            volume_scale = max(0.2, 1 - (distance / max_dist))
        else:
            volume_scale = 1.0
        sound = random.choice(pack)
        tech_bonus = team.tech_level * 0.03 if team else 0.0
        sound.set_volume((0.15 + tech_bonus) * volume_scale)
        sound.play()

    def _resource_lure(self, robot: Robot) -> Optional[Point]:
        best = None
        best_score = 0.0
        tiles = int(max(4, min(8, robot.scan_radius / TILE_SIZE)))
        for dy in range(-tiles, tiles + 1):
            for dx in range(-tiles, tiles + 1):
                probe = robot.pos + Point(dx * TILE_SIZE, dy * TILE_SIZE)
                if probe.distance_to(robot.pos) > min(robot.scan_radius, RESOURCE_ATTRACT_RADIUS * 1.5):
                    continue
                tile = self.wasteland.tile_at(probe)
                if not tile:
                    continue
                score = tile.scrap + tile.alloy * 1.4 + tile.crystal * 1.8 + tile.capacitor * 2.2
                if score > best_score:
                    best_score = score
                    best = probe
        return best

    def _tile_in_pickup_range(self, pos: Point) -> Optional[Tile]:
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                probe = pos + Point(dx * TILE_SIZE, dy * TILE_SIZE)
                if probe.distance_to(pos) > PICKUP_RADIUS:
                    continue
                tile = self.wasteland.tile_at(probe)
                if not tile:
                    continue
                if tile.scrap or tile.alloy or tile.crystal or tile.capacitor:
                    return tile
        return None

    def _wander_target(self, team: Team, pos: Point) -> Point:
        angle = random.random() * math.tau
        distance = random.randint(120, 260)
        bias = team.base_pos if team.stance == "passive" else pos
        return bias + Point(math.cos(angle), math.sin(angle)) * distance

    def _formation_offsets(self, stance: str, count: int) -> List[Point]:
        spacing = 24
        if stance == "tyrannic":
            offsets = [Point(i * spacing, 0) for i in range(-count // 2, count // 2 + 1)][:count]
        elif stance == "explorer":
            offsets = [Point(math.cos(i), math.sin(i)) * spacing for i in [0, 2, 4][:count]]
        elif stance == "colonizer":
            offsets = [Point(0, i * spacing) for i in range(-count // 2, count // 2 + 1)][:count]
        else:
            offsets = [Point(math.cos(i * math.tau / count), math.sin(i * math.tau / count)) * spacing for i in range(count)]
        angle = random.random() * math.tau
        rot = Point(math.cos(angle), math.sin(angle))
        return [Point(offset.x * rot.x - offset.y * rot.y, offset.x * rot.y + offset.y * rot.x) for offset in offsets]

    def _enemy_base_hint(self, team: Team, pos: Point) -> Point:
        enemies = [other.base_pos for other in self.teams if other is not team]
        if not enemies:
            return pos
        target = min(enemies, key=lambda base: base.distance_to(pos))
        jitter = Point(random.randint(-40, 40), random.randint(-40, 40))
        return target + jitter

    def _expand_maze(self, team: Team) -> None:
        offset = Point((team.maze_extent % 6) * 18 - 45, (team.maze_extent // 6) * 12 - 18)
        pos = team.base_pos + offset
        team.structures.append(self._make_structure(team, "maze", pos, 12))

    def _expand_rooms(self, team: Team) -> None:
        ring = team.room_level // 4 + 1
        angle = (team.room_level % 6) * (math.tau / 6)
        radius = 40 + ring * 18
        pos = team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius
        team.structures.append(self._make_structure(team, "room", pos, 22))

    def _add_defense(self, team: Team) -> None:
        angle = random.random() * math.tau
        radius = 70 + team.defense_level * 10
        pos = team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius
        team.structures.append(self._make_structure(team, "defense", pos, 14, cooldown=random.random()))

    def _add_generator(self, team: Team) -> None:
        angle = random.random() * math.tau
        radius = 36 + (len(team.structures) % 5) * 10
        pos = team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius
        team.structures.append(self._make_structure(team, "generator", pos, 16))

    def _add_relay(self, team: Team) -> None:
        angle = random.random() * math.tau
        radius = 42 + (len(team.structures) % 5) * 12
        pos = team.base_pos + Point(math.cos(angle), math.sin(angle)) * radius
        team.structures.append(self._make_structure(team, "relay", pos, 14))

    def _apply_structure_effects(self, robot: Robot, dt: float) -> None:
        for structure in robot.team.structures:
            if structure.kind == "generator" and robot.pos.distance_to(structure.pos) < 60:
                robot.hp = min(100, robot.hp + 8 * dt)
            if structure.kind == "relay" and robot.pos.distance_to(structure.pos) < 80:
                robot.scan_radius = min(220, robot.scan_radius + 10 * dt)

    def _relay_speed_bonus(self, robot: Robot) -> float:
        for structure in robot.team.structures:
            if structure.kind == "relay" and robot.pos.distance_to(structure.pos) < 90:
                return 20.0
        return 0.0

    def _update_defenses(self, dt: float) -> None:
        for team in self.teams:
            if team.extinct:
                continue
            for structure in team.structures:
                if structure.kind not in ("defense", "gun_tower"):
                    continue
                structure.cooldown = max(0.0, structure.cooldown - dt)
                if structure.cooldown > 0:
                    continue
                target = self._find_enemy_for_defense(team, structure.pos)
                if target and self._can_fire_at(structure.pos, target.pos, LASER_RANGE):
                    direction = (target.pos - structure.pos).normalize()
                    self.projectiles.append(
                        Projectile(pos=structure.pos.copy(), vel=direction * LASER_SPEED, team=team, kind="laser")
                    )
                    structure.cooldown = LASER_COOLDOWN if structure.kind == "defense" else LASER_COOLDOWN * 0.8
                    self._play_sfx("laser", team, structure.pos)


    def _find_enemy_for_defense(self, team: Team, pos: Point) -> Optional[object]:
        spatial = getattr(self, "_spatial", None)
        if spatial is None or not spatial.cells:
            return self._nearest_enemy_unit(team, pos, include_structures=False, include_hives=True, include_queens=True)

        candidates = spatial.query(pos, LASER_RANGE)
        best = LASER_RANGE * LASER_RANGE
        closest: Optional[object] = None
        for obj in candidates:
            obj_team = getattr(obj, "team", None)
            if team is not None and obj_team is team:
                continue
            if isinstance(obj_team, Team) and not self._teams_hostile(team, obj_team):
                continue
            if not hasattr(obj, "pos"):
                continue
            p = obj.pos
            d2 = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
            if d2 < best:
                best = d2
                closest = obj
        return closest

    def _view_rect(self) -> pygame.Rect:
        return pygame.Rect(self.camera.pos.x, self.camera.pos.y, self.view_size.x, self.view_size.y)

    def _render_rect(self) -> pygame.Rect:
        scale = max(0.6, self.render_distance_scale)
        base = self._view_rect()
        inflate_x = int(base.width * (scale - 1))
        inflate_y = int(base.height * (scale - 1))
        return base.inflate(inflate_x, inflate_y)

    def _render_range(self) -> float:
        return max(self.view_size.x, self.view_size.y) * self.render_distance_scale

    def _can_fire_at(self, shooter_pos: Point, target_pos: Point, max_range: float) -> bool:
        effective_range = min(max_range, self._render_range())
        if shooter_pos.distance_to(target_pos) > effective_range:
            return False
        view_rect = self._render_rect()
        if not view_rect.collidepoint(shooter_pos):
            return False
        if not view_rect.collidepoint(target_pos):
            return False
        return True

    def _apply_damage(self, target: object, damage: float, attacker: Optional[Team], action: str) -> None:
        if isinstance(target, Structure):
            self._apply_structure_damage(target, damage, attacker)
            return
        if isinstance(target, NativeHive):
            target.hp -= damage
            if target.hp <= 0:
                self._destroy_native_hive(target, attacker)
            return
        if isinstance(target, NativeQueen):
            target.hp -= damage
            if target.hp <= 0:
                self._destroy_native_queen(target, attacker)
            return
        if isinstance(target, Civilian):
            if not target.team.threatened:
                target.team.threatened = True
                target.team.spawn_wave_timer = 0.0
                self._log(f"{target.team.name} civilians report hostile contact.", team=target.team)
            target.hp -= damage
            if target.hp <= 0:
                if target in target.team.civilians:
                    target.team.civilians.remove(target)
                self._register_death(target, attacker=attacker, action=action)
                if attacker and target.team is not attacker:
                    self._spawn_civilians(attacker, count=1)
            return
        if isinstance(target, RepairBot):
            target.hp -= damage
            if target.hp <= 0:
                if target in target.team.repair_bots:
                    target.team.repair_bots.remove(target)
                self._register_death(target, attacker=attacker, action=action)
                if attacker and target.team is not attacker:
                    self._spawn_civilians(attacker, count=1)
            return
        if hasattr(target, "hp"):
            target.hp -= damage
            if target.hp <= 0:
                self._register_death(target, attacker=attacker, action=action)
                self._respawn_unit(target)
                if attacker and hasattr(target, "team") and target.team is not attacker:
                    self._spawn_civilians(attacker, count=1)

    def _apply_structure_damage(self, structure: Structure, damage: float, attacker: Optional[Team]) -> None:
        if self._has_forcefield(structure.team, structure.pos):
            damage *= 0.6
        structure.hp -= damage
        if structure.hp <= 0:
            self._destroy_structure(structure, attacker)

    def _has_forcefield(self, team: Team, pos: Point) -> bool:
        for structure in team.structures:
            if structure.kind == "forcefield" and structure.pos.distance_to(pos) < 140:
                return True
        return False

    def _destroy_structure(self, structure: Structure, attacker: Optional[Team]) -> None:
        if structure in structure.team.structures:
            structure.team.structures.remove(structure)
        self._add_explosion(structure.pos, (200, 160, 120), 0.8)
        self._log(f"{structure.team.name} {structure.kind} destroyed.", team=structure.team)
        if structure.kind == "core":
            self._handle_core_destroyed(structure.team, attacker)

    def _handle_core_destroyed(self, team: Team, attacker: Optional[Team]) -> None:
        self._award_epoch(attacker, reason="core victory")
        if self._team_has_survivors(team):
            self._relocate_team(team)
            self._log(f"{team.name} fled and rebuilt their core.", team=team)
        else:
            team.extinct = True
            team.structures.clear()
            team.robots.clear()
            team.vehicles.clear()
            team.mechs.clear()
            team.ships.clear()
            team.troops.clear()
            team.generals.clear()
            team.snipers.clear()
            team.drones.clear()
            team.sprites.clear()
            team.civilians.clear()
            team.repair_bots.clear()
            self._log(f"{team.name} has gone extinct.", team=team)

    def _team_has_survivors(self, team: Team) -> bool:
        return any(
            unit.hp > 0
            for unit in team.robots
            + team.vehicles
            + team.mechs
            + team.ships
            + team.troops
            + team.generals
            + team.snipers
            + team.drones
            + team.sprites
            + team.civilians
            + team.repair_bots
        )

    def _relocate_team(self, team: Team) -> None:
        view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
        view_rect = pygame.Rect(
            view_center.x - self.view_size.x / 2,
            view_center.y - self.view_size.y / 2,
            self.view_size.x,
            self.view_size.y,
        ).inflate(1200, 1200)
        new_base = team.base_pos
        for _ in range(12):
            distance = random.randint(1200, 2000)
            angle = random.random() * math.tau
            candidate = view_center + Point(math.cos(angle), math.sin(angle)) * distance
            if not view_rect.collidepoint(candidate):
                new_base = candidate
                break
        team.base_pos = new_base
        team.resources = 0
        team.maze_extent = 0
        team.room_level = 0
        team.defense_level = 0
        team.structures = [
            self._make_structure(team, "core", team.base_pos, 28),
            self._make_structure(team, "generator", team.base_pos + Point(26, -18), 18),
            self._make_structure(team, "relay", team.base_pos + Point(-28, 18), 16),
        ]
        for unit in (
            team.robots
            + team.vehicles
            + team.mechs
            + team.ships
            + team.troops
            + team.generals
            + team.snipers
            + team.drones
            + team.sprites
            + team.civilians
            + team.repair_bots
        ):
            unit.pos = team.base_pos + Point(random.randint(-120, 120), random.randint(-120, 120))
            unit.target = None
            unit.stuck_timer = 0.0
            unit.last_pos = unit.pos.copy()

    def _destroy_native_hive(self, hive: NativeHive, attacker: Optional[Team]) -> None:
        if hive in self.native_hives:
            self.native_hives.remove(hive)
        self._add_explosion(hive.pos, (160, 120, 200), 1.2)
        self.native_queens.append(NativeQueen(pos=hive.pos.copy(), kind=hive.kind))
        self._log("A native queen rises from the shattered hive.")

    def _destroy_native_queen(self, queen: NativeQueen, attacker: Optional[Team]) -> None:
        if queen in self.native_queens:
            self.native_queens.remove(queen)
        self._add_explosion(queen.pos, (220, 140, 240), 1.6)
        self._award_epoch(attacker, reason="queen victory")
        self._log("The native queen falls; a new ruler ascends.", team=attacker)

    def _award_epoch(self, team: Optional[Team], reason: str) -> None:
        if team is None or team.extinct:
            return
        team.epoch += 1
        team.tech_level = min(5, team.tech_level + 1)
        team.defense_level += 1
        team.aggression = min(1.0, team.aggression + 0.1)
        for robot in team.robots:
            robot.hp += 10
        for vehicle in team.vehicles:
            vehicle.hp += 14
        for mech in team.mechs:
            mech.hp += 18
        for ship in team.ships:
            ship.hp += 26
        for troop in team.troops:
            troop.hp += 8
        for general in team.generals:
            general.hp += 12
        for sniper in team.snipers:
            sniper.hp += 6
        for drone in team.drones:
            drone.hp += 6
        for sprite in team.sprites:
            sprite.hp += 6
        self._log(f"{team.name} advances to epoch {team.epoch} after {reason}.", team=team)

    def _update_vehicle(self, vehicle: Vehicle, dt: float) -> None:
        vehicle.cooldown = max(0.0, vehicle.cooldown - dt)
        target = self._nearest_enemy_unit(
            vehicle.team,
            vehicle.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target and vehicle.cooldown <= 0 and self._can_fire_at(vehicle.pos, target.pos, self._render_range()):
            direction = (target.pos - vehicle.pos).normalize()
            self.projectiles.append(
                Projectile(pos=vehicle.pos.copy(), vel=direction * (LASER_SPEED + 40), team=vehicle.team, kind="pulse")
            )
            vehicle.cooldown = 1.8
            self._play_sfx("pulse", vehicle.team, vehicle.pos)
        if target:
            vehicle.target = target.pos
        elif vehicle.target is None or vehicle.pos.distance_to(vehicle.target) < 10:
            vehicle.target = self._wander_target(vehicle.team, vehicle.pos)
        self._move_mobile(vehicle, dt, speed=90 if vehicle.role == "scout" else 70)
        self._check_stuck(vehicle, dt, vehicle.team)

    def _update_mech(self, mech: Mech, dt: float) -> None:
        mech.cooldown = max(0.0, mech.cooldown - dt)
        target = self._nearest_enemy_unit(
            mech.team,
            mech.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            mech.target = target.pos
        if target and mech.cooldown <= 0 and self._can_fire_at(mech.pos, target.pos, self._render_range()):
            direction = (target.pos - mech.pos).normalize()
            self.projectiles.append(
                Projectile(pos=mech.pos.copy(), vel=direction * (LASER_SPEED - 40), team=mech.team, kind="laser")
            )
            mech.cooldown = 1.2 if mech.role == "brawler" else 2.4
            self._play_sfx("laser", mech.team, mech.pos)
        elif mech.target is None or mech.pos.distance_to(mech.target) < 10:
            mech.target = self._wander_target(mech.team, mech.pos)
        self._move_mobile(mech, dt, speed=60 if mech.role == "brawler" else 45)
        self._check_stuck(mech, dt, mech.team)

    def _update_ship(self, ship: Ship, dt: float) -> None:
        ship.cooldown = max(0.0, ship.cooldown - dt)
        target = self._nearest_enemy_unit(
            ship.team,
            ship.pos,
            include_structures=True,
            include_hives=True,
            include_queens=True,
        )
        if target:
            ship.target = target.pos
        if target and ship.cooldown <= 0 and self._can_fire_at(ship.pos, target.pos, self._render_range()):
            direction = (target.pos - ship.pos).normalize()
            for _ in range(2):
                self.projectiles.append(
                    Projectile(pos=ship.pos.copy(), vel=direction * (LASER_SPEED + 60), team=ship.team, kind="laser")
                )
            ship.cooldown = 1.0
            self._play_sfx("laser", ship.team, ship.pos)
        elif ship.target is None or ship.pos.distance_to(ship.target) < 20:
            ship.target = self._wander_target(ship.team, ship.pos)
        self._move_mobile(ship, dt, speed=75)
        self._check_stuck(ship, dt, ship.team)

    def _update_patrols(self, team: Team, dt: float) -> None:
        for platoon in team.patrols:
            platoon.cooldown = max(0.0, platoon.cooldown - dt)
            enemy = self._nearest_enemy_unit(
                team,
                platoon.anchor,
                include_structures=True,
                include_hives=True,
                include_queens=True,
            )
            if enemy:
                platoon.target = enemy.pos
            elif platoon.cooldown <= 0:
                platoon.target = self._wander_target(team, platoon.anchor)
                platoon.cooldown = 4.0
            self._assign_platoon_targets(platoon)

    def _assign_platoon_targets(self, platoon: PatrolPlatoon) -> None:
        for member, offset in zip(platoon.members, platoon.formation):
            member.target = platoon.target + offset

    def _check_stuck(self, unit: object, dt: float, team: Team) -> None:
        if not hasattr(unit, "last_pos"):
            return
        moved = unit.pos.distance_to(unit.last_pos)
        if moved < 2:
            unit.stuck_timer += dt
        else:
            unit.stuck_timer = 0.0
            unit.last_pos = unit.pos.copy()
        if unit.stuck_timer > STUCK_TIME:
            target = self._resource_target_for_team(team, unit.pos)
            unit.target = target if target else self._wander_target(team, unit.pos)
            unit.stuck_timer = 0.0

    def _resource_target_for_team(self, team: Team, pos: Point) -> Optional[Point]:
        search = 6 if team.resource_pressure > 0.5 else 4
        best = None
        best_score = 0
        for dy in range(-search, search + 1):
            for dx in range(-search, search + 1):
                probe = pos + Point(dx * TILE_SIZE, dy * TILE_SIZE)
                tile = self.wasteland.tile_at(probe)
                if not tile:
                    continue
                score = tile.scrap + tile.alloy * 2 + tile.crystal * 2 + tile.capacitor * 3
                if score > best_score:
                    best_score = score
                    best = probe
        return best

    def _move_mobile(self, unit: object, dt: float, speed: float) -> None:
        target = unit.target
        if target is None:
            return
        direction = target - unit.pos
        if direction.length() < 1:
            return
        direction = direction.normalize()
        unit.pos += direction * speed * dt

    def _update_team_state(self, team: Team, dt: float) -> None:
        scarcity = max(0, 5 - team.resources)
        team.resource_pressure = min(1.0, team.resource_pressure + scarcity * 0.02 * dt)
        if team.resources > 6:
            team.resource_pressure = max(0.0, team.resource_pressure - dt * 0.03)
        stance_bias = {
            "passive": -0.1,
            "neutral": 0.0,
            "explorer": 0.1,
            "colonizer": 0.15,
            "tyrannic": 0.25,
        }.get(team.stance, 0.0)
        team.aggression = max(0.1, min(1.0, team.aggression + stance_bias * dt + team.resource_pressure * 0.15 * dt))
        if team.stance in ("explorer", "colonizer") and team.resources > 8:
            team.tech_level = min(4, team.tech_level + 1)
        if team.tech_level >= 4 and not team.ships:
            ship = Ship(pos=team.base_pos + Point(0, -200), team=team, role="warship")
            team.ships.append(ship)

    def _update_death_markers(self, dt: float) -> None:
        survivors: List[DeathMarker] = []
        for marker in self.death_markers:
            marker.ttl -= dt
            if marker.ttl > 0:
                survivors.append(marker)
        self.death_markers = survivors


    def _resolve_collisions(self) -> None:
        # Broadphase collision using spatial hash (prevents O(N^2) blowups as armies grow).
        self._rebuild_spatial()
        spatial = self._spatial
        if not spatial.cells:
            return

        def collidable(o: object) -> bool:
            return isinstance(o, (Robot, Vehicle, Mech, Ship, Troop, General, Sniper, Drone, Sprite, Alien, Dino))

        checked_neighbors = ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 1))
        min_dist = 16.0
        min_d2 = min_dist * min_dist

        for (cx, cy), bucket in list(spatial.cells.items()):
            # Local list for this bucket
            local = [o for o in bucket if collidable(o) and hasattr(o, "pos")]
            if not local:
                continue

            # Same-cell pairs
            for i in range(len(local)):
                a = local[i]
                for j in range(i + 1, len(local)):
                    b = local[j]
                    dx = a.pos.x - b.pos.x
                    dy = a.pos.y - b.pos.y
                    d2 = dx * dx + dy * dy
                    if d2 < min_d2:
                        if d2 <= 1e-6:
                            # random tiny nudge direction
                            rx = random.uniform(-1, 1)
                            ry = random.uniform(-1, 1)
                            inv = 1.0 / max(1e-6, math.hypot(rx, ry))
                            nx, ny = rx * inv, ry * inv
                            dist = 1e-3
                        else:
                            dist = math.sqrt(d2)
                            nx, ny = dx / dist, dy / dist
                        push = (min_dist - dist) * 0.5
                        a.pos.x += nx * push
                        a.pos.y += ny * push
                        b.pos.x -= nx * push
                        b.pos.y -= ny * push

            # Cross-cell pairs with a fixed neighbor set to avoid double-work.
            for ox, oy in checked_neighbors[1:]:
                nb = spatial.cells.get((cx + ox, cy + oy))
                if not nb:
                    continue
                other = [o for o in nb if collidable(o) and hasattr(o, "pos")]
                if not other:
                    continue
                for a in local:
                    for b in other:
                        dx = a.pos.x - b.pos.x
                        dy = a.pos.y - b.pos.y
                        d2 = dx * dx + dy * dy
                        if d2 < min_d2:
                            if d2 <= 1e-6:
                                rx = random.uniform(-1, 1)
                                ry = random.uniform(-1, 1)
                                inv = 1.0 / max(1e-6, math.hypot(rx, ry))
                                nx, ny = rx * inv, ry * inv
                                dist = 1e-3
                            else:
                                dist = math.sqrt(d2)
                                nx, ny = dx / dist, dy / dist
                            push = (min_dist - dist) * 0.5
                            a.pos.x += nx * push
                            a.pos.y += ny * push
                            b.pos.x -= nx * push
                            b.pos.y -= ny * push


    def _update_aliens(self, dt: float) -> None:
        self.alien_spawn_timer -= dt
        if self.alien_spawn_timer <= 0:
            for team in self.teams:
                if sum(1 for alien in self.aliens if alien.team is team) < ALIEN_MAX_PER_TEAM:
                    roll = random.random()
                    if roll > 0.7:
                        kind = "warden"
                    elif roll > 0.4:
                        kind = "sentinel"
                    else:
                        kind = "raider"
                    self.aliens.append(Alien(pos=team.base_pos.copy(), team=team, kind=kind))
                    self._log(f"Spawned {kind} alien.", team=team)
            self.alien_spawn_timer = ALIEN_SPAWN_INTERVAL

        for alien in self.aliens:
            if alien.kind == "sentinel":
                self._alien_defend(alien, dt)
            else:
                self._alien_attack(alien, dt)

    def _update_dinosaurs(self, dt: float) -> None:
        night = math.sin((self.day_timer / DAY_LENGTH) * math.tau) > 0.4
        self.dino_spawn_timer -= dt
        if night and self.dino_spawn_timer <= 0:
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            spawn = view_center + Point(random.randint(-400, 400), random.randint(-400, 400))
            kind = random.choice(["reef", "ember", "brine"])
            self.dinosaurs.append(Dino(pos=spawn, kind=kind))
            self.dino_spawn_timer = DINO_SPAWN_INTERVAL
        survivors: List[Dino] = []
        for dino in self.dinosaurs:
            target = self._nearest_enemy_unit(
                None,
                dino.pos,
                include_dinosaurs=False,
                include_structures=False,
                include_hives=False,
                include_queens=False,
            )
            if target:
                dino.target = target.pos
                if dino.pos.distance_to(target.pos) < 70:
                    self._apply_damage(target, 20 * dt, None, action="torn apart by a native")
            if dino.target:
                direction = dino.target - dino.pos
                if direction.length() > 1:
                    dino.pos += direction.normalize() * 85 * dt
            if dino.hp > 0:
                survivors.append(dino)
        self.dinosaurs = survivors

    def _update_native_queens(self, dt: float) -> None:
        survivors: List[NativeQueen] = []
        for queen in self.native_queens:
            target = self._nearest_enemy_unit(
                None,
                queen.pos,
                include_structures=True,
                include_dinosaurs=False,
                include_hives=False,
                include_queens=False,
            )
            if target:
                queen.target = target.pos
                if queen.pos.distance_to(target.pos) < 80:
                    self._apply_damage(target, 30 * dt, None, action="crushed by a native queen")
            if queen.target:
                direction = queen.target - queen.pos
                if direction.length() > 1:
                    queen.pos += direction.normalize() * 70 * dt
            if queen.hp > 0:
                survivors.append(queen)
        self.native_queens = survivors

    def _update_sand_worms(self, dt: float) -> None:
        self.worm_spawn_timer -= dt
        if self.worm_spawn_timer <= 0 and len(self.sand_worms) < 2:
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            distance = random.randint(500, 900)
            angle = random.random() * math.tau
            spawn = view_center + Point(math.cos(angle), math.sin(angle)) * distance
            worm = SandWorm(pos=spawn, emerge_timer=12.0, active=True)
            self.sand_worms.append(worm)
            self.shake_intensity = min(1.0, self.shake_intensity + 0.8)
            self._play_sfx("roar", None, spawn)
            self._log("A sand worm erupts from the dunes.")
            self.worm_spawn_timer = random.uniform(40.0, 65.0)

        survivors: List[SandWorm] = []
        for worm in self.sand_worms:
            worm.emerge_timer -= dt
            target = self._nearest_organic_target(worm.pos)
            if target:
                worm.target = target.pos
                if worm.pos.distance_to(target.pos) < 60:
                    self._apply_damage(target, 30 * dt, None, action="devoured by a sand worm")
            if worm.target:
                direction = worm.target - worm.pos
                if direction.length() > 1:
                    worm.pos += direction.normalize() * 120 * dt
            if worm.emerge_timer > 0:
                survivors.append(worm)
        self.sand_worms = survivors

    def _nearest_organic_target(self, pos: Point) -> Optional[object]:
        targets: List[object] = []
        for team in self.teams:
            if team.extinct:
                continue
            targets.extend(team.civilians)
            targets.extend(team.troops)
            targets.extend(team.generals)
            targets.extend(team.snipers)
        if not targets:
            return None
        return min(targets, key=lambda target: target.pos.distance_to(pos))

    def _update_disasters(self, dt: float) -> None:
        self.disaster_timer -= dt
        if self.disaster_timer <= 0 and len(self.disasters) < 2:
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            distance = random.randint(600, 1100)
            angle = random.random() * math.tau
            pos = view_center + Point(math.cos(angle), math.sin(angle)) * distance
            self.disasters.append(Disaster(pos=pos, radius=240, ttl=12.0))
            self._log("A rare geomagnetic storm batters nearby structures.")
            self.disaster_timer = random.uniform(55.0, 90.0)

        survivors: List[Disaster] = []
        for disaster in self.disasters:
            disaster.ttl -= dt
            for team in self.teams:
                if team.extinct:
                    continue
                for structure in list(team.structures):
                    if structure.pos.distance_to(disaster.pos) < disaster.radius:
                        self._apply_structure_damage(structure, 2.0 * dt, None)
            if disaster.ttl > 0:
                survivors.append(disaster)
        self.disasters = survivors

    def _update_water_natives(self, dt: float) -> None:
        if len(self.water_nests) < 6 and random.random() < 0.002:
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            for _ in range(8):
                candidate = view_center + Point(random.randint(-800, 800), random.randint(-800, 800))
                tile = self.wasteland.tile_at(candidate)
                if tile and tile.river:
                    self.water_nests.append(WaterNest(pos=candidate))
                    self._log("A water nest ripples beneath the surface.")
                    break
        survivors: List[WaterMonster] = []
        for monster in self.water_monsters:
            target = self._nearest_water_target(monster.pos)
            if target:
                monster.target = target.pos
                if monster.pos.distance_to(target.pos) < 50:
                    self._apply_damage(target, 18 * dt, None, action="dragged under by a water native")
            if monster.target:
                direction = monster.target - monster.pos
                if direction.length() > 1:
                    monster.pos += direction.normalize() * 90 * dt
            if monster.hp > 0:
                survivors.append(monster)
        self.water_monsters = survivors
        for nest in self.water_nests:
            if random.random() < 0.01 and len(self.water_monsters) < 8:
                self.water_monsters.append(WaterMonster(pos=nest.pos.copy()))

    def _nearest_water_target(self, pos: Point) -> Optional[object]:
        targets: List[object] = []
        for team in self.teams:
            if team.extinct:
                continue
            targets.extend(team.civilians)
            targets.extend(team.troops)
            targets.extend(team.generals)
            targets.extend(team.snipers)
            targets.extend(team.robots)
        for target in targets:
            tile = self.wasteland.tile_at(target.pos)
            if tile and tile.river:
                return target
        return None

    def _update_radiation(self, dt: float) -> None:
        self.radiation_timer -= dt
        if self.radiation_timer <= 0:
            view_center = self.camera.pos + Point(self.view_size.x / 2, self.view_size.y / 2)
            self.radiation_center = view_center + Point(random.randint(-600, 600), random.randint(-600, 600))
            self.radiation_timer = random.uniform(18, 28)
        for team in self.teams:
            if team.extinct:
                continue
            for unit in (
                team.robots
                + team.vehicles
                + team.mechs
                + team.ships
                + team.troops
                + team.generals
                + team.snipers
                + team.drones
                + team.sprites
                + team.civilians
                + team.repair_bots
            ):
                if unit.pos.distance_to(self.radiation_center) < 180:
                    unit.hp -= 6 * dt

    def _alien_defend(self, alien: Alien, dt: float) -> None:
        target = self._nearest_enemy_unit(alien.team, alien.pos)
        if target and alien.pos.distance_to(target.pos) < 120:
            alien.target = target.pos
            damage = 10 * dt if alien.kind != "warden" else 18 * dt
            self._apply_damage(target, damage, alien.team, action="defending the nest")
            if random.random() < 0.05:
                self._play_sfx("claw", alien.team, alien.pos)
        else:
            alien.target = alien.team.base_pos
        speed = 70 if alien.kind != "warden" else 55
        self._move_alien(alien, dt, speed=speed)

    def _alien_attack(self, alien: Alien, dt: float) -> None:
        target = self._nearest_enemy_unit(alien.team, alien.pos)
        if target:
            alien.target = target.pos
            if alien.pos.distance_to(target.pos) < 60:
                damage = 14 * dt if alien.kind != "warden" else 20 * dt
                self._apply_damage(target, damage, alien.team, action="charging an enemy")
            if random.random() < 0.08:
                self._play_sfx("claw", alien.team, alien.pos)
        speed = 90 if alien.kind != "warden" else 65
        self._move_alien(alien, dt, speed=speed)

    def _move_alien(self, alien: Alien, dt: float, speed: float) -> None:
        if alien.target is None:
            return
        direction = alien.target - alien.pos
        if direction.length() < 1:
            return
        direction = direction.normalize()
        alien.pos += direction * speed * dt

    def _update_projectiles(self, dt: float) -> None:
        survivors: List[Projectile] = []
        for projectile in self.projectiles:
            projectile.pos += projectile.vel * dt
            projectile.ttl -= dt
            hit = self._projectile_hit(projectile)
            if projectile.ttl > 0 and not hit:
                survivors.append(projectile)
        self.projectiles = survivors

    def _projectile_hit(self, projectile: Projectile) -> bool:
        for team in self.teams:
            if team is projectile.team:
                continue
            for robot in team.robots:
                if projectile.pos.distance_to(robot.pos) < 8:
                    damage = 18 if projectile.kind == "laser" else 24
                    self._apply_damage(robot, damage, projectile.team, action="caught in crossfire")
                    return True
            for civilian in team.civilians:
                if projectile.pos.distance_to(civilian.pos) < 8:
                    damage = 12 if projectile.kind == "laser" else 16
                    self._apply_damage(civilian, damage, projectile.team, action="caught in crossfire")
                    return True
            for repair_bot in team.repair_bots:
                if projectile.pos.distance_to(repair_bot.pos) < 8:
                    damage = 16 if projectile.kind == "laser" else 20
                    self._apply_damage(repair_bot, damage, projectile.team, action="caught in crossfire")
                    return True
            for vehicle in team.vehicles:
                if projectile.pos.distance_to(vehicle.pos) < 10:
                    damage = 22 if projectile.kind == "laser" else 28
                    self._apply_damage(vehicle, damage, projectile.team, action="hit by heavy fire")
                    return True
            for mech in team.mechs:
                if projectile.pos.distance_to(mech.pos) < 12:
                    damage = 26 if projectile.kind == "laser" else 32
                    self._apply_damage(mech, damage, projectile.team, action="overwhelmed in combat")
                    return True
            for ship in team.ships:
                if projectile.pos.distance_to(ship.pos) < 14:
                    damage = 32 if projectile.kind == "laser" else 38
                    self._apply_damage(ship, damage, projectile.team, action="shot out of the sky")
                    return True
            for alien in self.aliens:
                if alien.team is team and projectile.pos.distance_to(alien.pos) < 10:
                    damage = 22 if projectile.kind == "laser" else 28
                    self._apply_damage(alien, damage, projectile.team, action="fell in the skirmish")
                    return True
            for structure in team.structures:
                if projectile.pos.distance_to(structure.pos) < structure.size:
                    damage = 1.0 if projectile.kind == "laser" else 1.2
                    self._apply_damage(structure, damage, projectile.team, action="structure breached")
                    return True
        for dino in self.dinosaurs:
            if projectile.pos.distance_to(dino.pos) < 12:
                dino.hp -= 26 if projectile.kind == "laser" else 32
                if dino.hp <= 0:
                    self._add_explosion(dino.pos, (120, 200, 120), 0.8)
                return True
        for hive in self.native_hives:
            if projectile.pos.distance_to(hive.pos) < 20:
                damage = 1.0 if projectile.kind == "laser" else 1.2
                self._apply_damage(hive, damage, projectile.team, action="hive shattered")
                return True
        for queen in self.native_queens:
            if projectile.pos.distance_to(queen.pos) < 20:
                damage = 16 if projectile.kind == "laser" else 22
                self._apply_damage(queen, damage, projectile.team, action="queen felled")
                return True
        return False

    def _respawn_unit(self, unit: object) -> None:
        if hasattr(unit, "team") and unit.team.extinct:
            return
        if isinstance(unit, Robot):
            unit.hp = 100
            unit.pos = unit.team.base_pos + Point(random.randint(-30, 30), random.randint(-30, 30))
            self._log("Robot respawned.", team=unit.team)
        elif isinstance(unit, Alien):
            unit.hp = 120
            unit.pos = unit.team.base_pos + Point(random.randint(-40, 40), random.randint(-40, 40))
            self._log("Alien respawned.", team=unit.team)
        elif isinstance(unit, Vehicle):
            unit.hp = 160
            unit.pos = unit.team.base_pos + Point(random.randint(-60, 60), random.randint(-60, 60))
            self._log("Vehicle respawned.", team=unit.team)
        elif isinstance(unit, Mech):
            unit.hp = 260
            unit.pos = unit.team.base_pos + Point(random.randint(-70, 70), random.randint(-70, 70))
            self._log("Mech respawned.", team=unit.team)
        elif isinstance(unit, Ship):
            unit.hp = 420
            unit.pos = unit.team.base_pos + Point(random.randint(-90, 90), random.randint(-220, -160))
            self._log("Ship respawned.", team=unit.team)

    def _register_death(self, unit: object, attacker: Optional[Team], action: str) -> None:
        if isinstance(unit, Robot):
            name = "robot"
            self._add_explosion(unit.pos, (120, 160, 200), 0.6)
        elif isinstance(unit, Vehicle):
            name = "vehicle"
            self._add_explosion(unit.pos, (200, 140, 120), 0.9)
        elif isinstance(unit, Mech):
            name = "mech"
            self._add_explosion(unit.pos, (240, 120, 160), 1.2)
        elif isinstance(unit, Alien):
            name = "alien"
            self._add_explosion(unit.pos, (140, 220, 180), 0.5)
        elif isinstance(unit, Ship):
            name = "ship"
            self._add_explosion(unit.pos, (200, 220, 255), 1.4)
        else:
            name = "unit"
        attacker_name = attacker.name if attacker else "Wilderness"
        unit_team = getattr(unit, "team", None)
        story = f"{attacker_name} {name} fell while {action}."
        self.death_markers.append(DeathMarker(pos=unit.pos.copy(), team=unit_team, story=story))
        self._log(f"{name.capitalize()} lost: {action}.", team=unit_team)

    def _log(self, message: str, team: Optional[Team] = None) -> None:
        tag = team.name if team else "System"
        self.logs.append((tag, message))
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]

    # ----------------------------
    # Settings persistence
    # ----------------------------
    def _settings_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(base, "Logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except Exception:
            logs_dir = base
        return os.path.join(logs_dir, "holowars_settings.json")

    def _load_settings(self) -> None:
        path = self._settings_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        def b(key: str, default: bool) -> bool:
            v = data.get(key, default)
            return bool(v)

        def fnum(key: str, default: float) -> float:
            try:
                return float(data.get(key, default))
            except Exception:
                return default

        self.vsync_enabled = b("vsync_enabled", self.vsync_enabled)
        self.fullscreen = b("fullscreen", self.fullscreen)
        self.resizable = b("resizable", self.resizable)
        self.high_detail = b("high_detail", self.high_detail)
        self.show_logs = b("show_logs", self.show_logs)
        self.render_distance_scale = max(0.6, min(1.6, fnum("render_distance_scale", getattr(self, "render_distance_scale", 1.0))))

        ws = data.get("windowed_size")
        if isinstance(ws, (list, tuple)) and len(ws) == 2:
            try:
                w = int(ws[0]); h = int(ws[1])
                self.windowed_size = Point(max(640, w), max(360, h))
                # Only apply to screen_size when not fullscreen (fullscreen overrides)
                if not self.fullscreen:
                    self.screen_size = self.windowed_size.copy()
            except Exception:
                pass

    def _save_settings(self) -> None:
        # Avoid excessive disk churn: only write when something changed.
        payload = {
            "vsync_enabled": bool(self.vsync_enabled),
            "fullscreen": bool(self.fullscreen),
            "resizable": bool(self.resizable),
            "high_detail": bool(self.high_detail),
            "show_logs": bool(self.show_logs),
            "render_distance_scale": float(self.render_distance_scale),
            "windowed_size": [int(self.windowed_size.x), int(self.windowed_size.y)],
        }
        try:
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except Exception:
            return
        if getattr(self, "_settings_cache", None) == raw:
            return
        self._settings_cache = raw
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, indent=2))
        except Exception:
            pass

    # ----------------------------
    # Spatial hash rebuild (performance)
    # ----------------------------
    def _rebuild_spatial(self) -> None:
        self._spatial.clear()
        # Structures + units
        for team in self.teams:
            if team.extinct:
                continue
            for s in team.structures:
                self._spatial.add(s, s.pos, s.team, "structure")
            for u in (
                team.robots
                + team.civilians
                + team.repair_bots
                + team.vehicles
                + team.mechs
                + team.ships
                + team.troops
                + team.generals
                + team.snipers
                + team.drones
                + team.sprites
            ):
                self._spatial.add(u, u.pos, getattr(u, "team", None), "unit")
        for a in self.aliens:
            self._spatial.add(a, a.pos, a.team, "alien")
        for d in self.dinosaurs:
            self._spatial.add(d, d.pos, None, "dino")
        for h in self.native_hives:
            self._spatial.add(h, h.pos, None, "hive")
        for q in self.native_queens:
            self._spatial.add(q, q.pos, None, "queen")
        for w in self.water_monsters:
            self._spatial.add(w, w.pos, None, "water")
        for n in self.water_nests:
            self._spatial.add(n, n.pos, None, "waternest")
        for sw in self.sand_worms:
            self._spatial.add(sw, sw.pos, None, "worm")



def report_crash(error: BaseException) -> None:
    with open("crash_report.txt", "w", encoding="utf-8") as report:
        report.write("Wasteland Foundries Crash Report\n")
        report.write(traceback.format_exc())
    print("A crash report was generated at crash_report.txt.")
    print(error)


if __name__ == "__main__":
    try:
        Game().run()
    except Exception as exc:
        report_crash(exc)