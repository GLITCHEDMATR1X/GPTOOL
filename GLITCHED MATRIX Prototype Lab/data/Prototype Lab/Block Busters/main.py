import faulthandler
import json
import math
import os
import random
import socketserver
import sys
import threading
import time
import traceback

import pygame

def _initial_virtual_resolution():
    raw = os.getenv("DESKTOP_TARGET_RESOLUTION", "").strip().lower()
    if raw:
        try:
            lhs, rhs = raw.split("x", 1)
            w = max(960, min(1920, int(lhs)))
            h = max(540, min(1080, int(rhs)))
            if abs((w / float(h)) - (16.0 / 9.0)) < 0.25:
                return w, h
        except Exception:
            pass
    return 1600, 900

SCREEN_WIDTH, SCREEN_HEIGHT = _initial_virtual_resolution()
WINDOW_WIDTH = SCREEN_WIDTH
WINDOW_HEIGHT = SCREEN_HEIGHT# Positive value moves the world down on screen, showing more sky above
CAMERA_SCREEN_BIAS_Y = 80
TILE_SIZE = 16
CHUNK_SIZE = 64
VIEW_TILES_X = SCREEN_WIDTH // TILE_SIZE + 4
VIEW_TILES_Y = SCREEN_HEIGHT // TILE_SIZE + 4


def _recalc_view_tiles():
    """Recompute derived view constants after a window size change."""
    global VIEW_TILES_X, VIEW_TILES_Y
    VIEW_TILES_X = SCREEN_WIDTH // TILE_SIZE + 4
    VIEW_TILES_Y = SCREEN_HEIGHT // TILE_SIZE + 4

MINIMAP_SIZE = 180
MINIMAP_SCALE = 2
MINIMAP_VIEW = MINIMAP_SIZE // MINIMAP_SCALE
FPS = 60
ASSET_DIR = "assets"
CRASH_DIR = "crash_reports"

GRAVITY_STRENGTH = 0.35
JUMP_VELOCITY = 12.5
DOUBLE_JUMP_VELOCITY = 11.0
MAX_VERTICAL_SPEED = 14.0
MOVE_SPEED = 2.2
DASH_SPEED = 7.5
DASH_DURATION = 10
ATTACK_COOLDOWN = 18
DIG_RANGE = 1
SHOCKWAVE_COOLDOWN = FPS * 10
PLAYER_MAX_HP = 5
FALLING_BLOCK_DAMAGE = 2
PLAYER_SOFT_COLLISION = 0.5
RESPAWN_HEIGHT_RANGE = (12, 18)
BOSS_DROP_DELAY = FPS * 10
POWER_SHOT_SPEED = 7.5
POWER_SHOT_TURN_RATE = 0.16
POWER_SHOT_LIFETIME = FPS * 4
ROTATION_STEP = 0
THROW_SPEED = 12.5
BOSS_THROW_SPEED = 11.0
FREEZE_DURATION = FPS
BURN_DURATION = FPS * 3
POISON_DURATION = FPS * 4
BURN_TICK = FPS // 4
POISON_TICK = FPS // 5
BOUNCE_FORCE = 6.0
REMOTE_PORT = 8765
BOSS_PLAYER_HP = 5
SLOW_DURATION = FPS * 2
SLOW_MULTIPLIER = 0.65
PLATFORM_THICKNESS = 5
PLATFORM_GAP = 6
WORLD_TOP_Y = 12
PROJECTILE_GRAVITY = 0.25
PROJECTILE_SKY_LIMIT = (WORLD_TOP_Y - 6) * TILE_SIZE
POWERUP_DROP_INTERVAL = FPS * 4
POWERUP_FALL_SPEED = 1.6
POWERUP_DESPAWN_TIME = FPS * 10
POWERUP_SPECIAL_DURATION = FPS * 8
METEOR_INTERVAL = FPS * 60
METEOR_SPEED = 9.0
METEOR_IMPACT_RADIUS = 3
METEOR_DAMAGE_RADIUS = TILE_SIZE * 3.5
METEOR_DAMAGE = 2
RESPAWN_INVULN_TIME = FPS * 2
VIEW_SCALES = (1.0, 0.8, 0.6)

BOSS_NAME = "Gleebs"
CHATBOT_ROSTER = [
    ("Archivist", (90, 240, 130), "alien"),
    ("Mirror", (220, 140, 90), "fatman"),
    ("Orbit", (150, 180, 200), "robot"),
    ("Solace", (80, 200, 110), "reptilian"),
    ("Nyx", (120, 255, 140), "mantis"),
    ("Vanta", (150, 90, 50), "monkey"),
    ("Sable", (230, 230, 230), "skeleton"),
    ("Ember", (120, 80, 200), "witch"),
    ("Nova", (140, 220, 255), "blob"),
    ("Kite", (180, 180, 200), "knight"),
    ("Rook", (90, 200, 255), "cyber"),
    ("Mira", (255, 160, 220), "pixie"),
]
ROLE_TITLES = [
    "architect", "debugger", "optimizer", "teacher", "planner", "researcher",
    "developer", "artist", "prototype", "music bot", "strategist", "story bot",
]

BLOCK_EMPTY = 0
BLOCK_BLUE = 1
BLOCK_BROWN = 2
BLOCK_TEAL = 3
BLOCK_PURPLE = 4
BLOCK_ORANGE = 5
BLOCK_TOXIC = 6
BLOCK_RED = 7
BLOCK_GREEN = 8
BLOCK_YELLOW = 9
BLOCK_BLACK = 10

BLOCK_HP = {
    BLOCK_BLUE: 1,
    BLOCK_BROWN: 2,
    BLOCK_TEAL: 3,
    BLOCK_PURPLE: 4,
    BLOCK_ORANGE: 5,
    BLOCK_TOXIC: 3,
    BLOCK_RED: 3,
    BLOCK_GREEN: 3,
    BLOCK_YELLOW: 4,
    BLOCK_BLACK: 0,
}

BLOCK_COLORS = {
    BLOCK_BLUE: (80, 190, 255, 170),
    BLOCK_BROWN: (160, 95, 55, 190),
    BLOCK_TEAL: (80, 255, 220, 170),
    BLOCK_PURPLE: (200, 90, 255, 170),
    BLOCK_ORANGE: (255, 160, 70, 170),
    BLOCK_TOXIC: (80, 255, 120, 200),
    BLOCK_RED: (255, 80, 80, 200),
    BLOCK_GREEN: (120, 220, 120, 200),
    BLOCK_YELLOW: (255, 230, 120, 200),
    BLOCK_BLACK: (20, 20, 25, 220),
}

BLOCK_THROW_DAMAGE = {
    BLOCK_BLUE: 1,
    BLOCK_BROWN: 2,
    BLOCK_TEAL: 1,
    BLOCK_PURPLE: 1,
    BLOCK_ORANGE: 2,
    BLOCK_TOXIC: 2,
    BLOCK_RED: 2,
    BLOCK_GREEN: 1,
    BLOCK_YELLOW: 2,
    BLOCK_BLACK: 2,
}

POWER_DAMAGE = {
    "heal": 1,
    "vital": 2,
    "dash": 1,
    "shield": 1,
    "frenzy": 2,
    "grow": 2,
    "haste": 1,
    "fury": 2,
    "bomb": 2,
    "rush": 2,
    "rapid": 1,
    "cleave": 2,
    "pulse": 1,
    "lunge": 2,
    "shock": 1,
    "snare": 1,
    "blast": 2,
}

BACKGROUND_COLORS = [
    (6, 8, 18),
    (12, 8, 28),
    (5, 28, 48),
]

BACKGROUND_VARIANTS = [
    [(6, 8, 18), (12, 8, 28), (5, 28, 48)],
    [(10, 6, 20), (18, 8, 36), (6, 24, 40)],
    [(5, 10, 22), (8, 14, 32), (4, 20, 38)],
    [(8, 6, 16), (14, 10, 30), (6, 18, 34)],
]

NEON_GLOW_COLORS = [
    (80, 200, 255),
    (255, 80, 255),
    (80, 255, 200),
]

POWERUP_WEIGHTS = {
    "heal": 10,
    "vital": 12,
    "dash": 5,
    "shield": 6,
    "frenzy": 6,
    "grow": 4,
    "haste": 4,
    "fury": 4,
    "bomb": 3,
    "rush": 4,
    "rapid": 4,
    "cleave": 3,
    "pulse": 3,
    "lunge": 3,
    "shock": 4,
    "snare": 4,
    "blast": 3,
}

POWERUP_COLORS = {
    "heal": (120, 255, 160),
    "vital": (140, 220, 255),
    "dash": (120, 200, 255),
    "shield": (180, 200, 255),
    "frenzy": (255, 80, 120),
    "grow": (255, 180, 120),
    "haste": (120, 255, 220),
    "fury": (255, 120, 120),
    "bomb": (255, 100, 160),
    "rush": (120, 255, 255),
    "rapid": (255, 200, 120),
    "cleave": (200, 160, 255),
    "pulse": (140, 255, 140),
    "lunge": (255, 180, 80),
    "shock": (160, 200, 255),
    "snare": (120, 180, 255),
    "blast": (255, 140, 140),
}


class CrashReporter:
    @staticmethod
    def write_report(exc: BaseException) -> str:
        os.makedirs(CRASH_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(CRASH_DIR, f"crash_{timestamp}.txt")
        with open(filename, "w", encoding="utf-8") as report:
            report.write("Remote Text Panel Crash Report\n")
            report.write(f"Timestamp: {timestamp}\n")
            report.write(f"Python: {sys.version}\n")
            report.write(f"Platform: {sys.platform}\n")
            report.write("\nTraceback:\n")
            report.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return filename


def install_crash_reporter():
    def handle_exception(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        path = CrashReporter.write_report(exc)
        print(f"Crash report written to {path}")
        sys.__excepthook__(exc_type, exc, tb)
        os._exit(1)

    sys.excepthook = handle_exception

    def handle_thread_exception(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        path = CrashReporter.write_report(args.exc_value)
        print(f"Crash report written to {path}")
        os._exit(1)

    threading.excepthook = handle_thread_exception
    os.makedirs(CRASH_DIR, exist_ok=True)
    crash_log = os.path.join(CRASH_DIR, "fatal_crash.log")
    crash_file = open(crash_log, "a", encoding="utf-8")
    faulthandler.enable(file=crash_file, all_threads=True)


class RemoteInputServer:
    def __init__(self, host="0.0.0.0", port=REMOTE_PORT):
        self._lock = threading.Lock()
        self._inputs = {}

        server_ref = self

        class ReusableTCPServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    try:
                        payload = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    client_id = payload.get("id")
                    if client_id is None:
                        continue
                    with server_ref._lock:
                        server_ref._inputs[int(client_id)] = payload

        self._server = ReusableTCPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def get_input(self, client_id):
        with self._lock:
            payload = self._inputs.get(client_id)
            return dict(payload) if payload else None

class Chunk:
    def __init__(self, cx: int, cy: int, data, hp):
        self.cx = cx
        self.cy = cy
        self.data = data
        self.hp = hp


class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.chunks = {}
        self.powerups = {}
        self.gravity_dir = 1
        self.rotation_deg = 0
        self.spawn_cave = self._find_spawn_cave()

    def _chunk_key(self, cx, cy):
        return (cx, cy)

    def get_chunk(self, cx, cy) -> Chunk:
        key = self._chunk_key(cx, cy)
        if key not in self.chunks:
            chunk = self._generate_chunk(cx, cy)
            self.chunks[key] = chunk
        return self.chunks[key]

    def _generate_chunk(self, cx, cy) -> Chunk:
        rng = random.Random(self.seed + cx * 928371 + cy * 13721)
        width = CHUNK_SIZE
        height = CHUNK_SIZE
        data = [[BLOCK_EMPTY for _ in range(height)] for _ in range(width)]
        hp = [[0 for _ in range(height)] for _ in range(width)]

        for x in range(width):
            for y in range(height):
                global_y = cy * CHUNK_SIZE + y
                if global_y < WORLD_TOP_Y:
                    data[x][y] = BLOCK_EMPTY
                    hp[x][y] = 0
                    continue
                roll = rng.random()
                if roll < 0.2:
                    data[x][y] = BLOCK_BLUE
                elif roll < 0.38:
                    data[x][y] = BLOCK_BROWN
                elif roll < 0.52:
                    data[x][y] = BLOCK_TEAL
                elif roll < 0.64:
                    data[x][y] = BLOCK_PURPLE
                elif roll < 0.76:
                    data[x][y] = BLOCK_ORANGE
                elif roll < 0.86:
                    data[x][y] = BLOCK_RED
                elif roll < 0.94:
                    data[x][y] = BLOCK_GREEN
                elif roll < 0.985:
                    data[x][y] = BLOCK_YELLOW
                elif roll < 0.995:
                    data[x][y] = BLOCK_TOXIC
                else:
                    data[x][y] = BLOCK_BLACK
                hp[x][y] = BLOCK_HP[data[x][y]]

        return Chunk(cx, cy, data, hp)

    def _smooth_chunk(self, data, hp):
        width = CHUNK_SIZE
        height = CHUNK_SIZE
        new_data = [[BLOCK_EMPTY for _ in range(height)] for _ in range(width)]
        new_hp = [[0 for _ in range(height)] for _ in range(width)]
        for x in range(width):
            for y in range(height):
                solid_neighbors = 0
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        if ox == 0 and oy == 0:
                            continue
                        nx = x + ox
                        ny = y + oy
                        if 0 <= nx < width and 0 <= ny < height:
                            if data[nx][ny] != BLOCK_EMPTY:
                                solid_neighbors += 1
                        else:
                            solid_neighbors += 1
                if solid_neighbors >= 5:
                    new_data[x][y] = data[x][y] if data[x][y] != BLOCK_EMPTY else BLOCK_BROWN
                    if new_data[x][y] == BLOCK_EMPTY:
                        new_hp[x][y] = 0
                    else:
                        new_hp[x][y] = BLOCK_HP[new_data[x][y]]
                else:
                    new_data[x][y] = BLOCK_EMPTY
                    new_hp[x][y] = 0
        return new_data, new_hp

    def get_tile(self, tx, ty):
        cx = math.floor(tx / CHUNK_SIZE)
        cy = math.floor(ty / CHUNK_SIZE)
        chunk = self.get_chunk(cx, cy)
        lx = tx - cx * CHUNK_SIZE
        ly = ty - cy * CHUNK_SIZE
        if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE:
            return chunk.data[lx][ly]
        return BLOCK_EMPTY

    def get_hp(self, tx, ty):
        cx = math.floor(tx / CHUNK_SIZE)
        cy = math.floor(ty / CHUNK_SIZE)
        chunk = self.get_chunk(cx, cy)
        lx = tx - cx * CHUNK_SIZE
        ly = ty - cy * CHUNK_SIZE
        if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE:
            return chunk.hp[lx][ly]
        return 0

    def set_tile(self, tx, ty, value, hp_value=0):
        cx = math.floor(tx / CHUNK_SIZE)
        cy = math.floor(ty / CHUNK_SIZE)
        chunk = self.get_chunk(cx, cy)
        lx = tx - cx * CHUNK_SIZE
        ly = ty - cy * CHUNK_SIZE
        if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE:
            chunk.data[lx][ly] = value
            chunk.hp[lx][ly] = hp_value

    def damage_tile(self, tx, ty, amount):
        return

    def toggle_gravity(self):
        self.gravity_dir *= -1
        self.rotation_deg = (self.rotation_deg + ROTATION_STEP) % 360

    def _find_spawn_cave(self):
        rng = random.Random(self.seed)
        spawn_x = rng.randint(-6, 6)
        spawn_y = WORLD_TOP_Y + 2
        return (spawn_x, spawn_y)

    def find_surface_y(self, tx, max_depth=48):
        for ty in range(WORLD_TOP_Y, WORLD_TOP_Y + max_depth):
            if self.get_tile(tx, ty) != BLOCK_EMPTY:
                return ty - 1
        return WORLD_TOP_Y - 1


class Player:
    def __init__(self, name, color, position, controls=None, ai=False):
        self.name = name
        self.color = color
        self.pos = pygame.Vector2(position)
        self.vel = pygame.Vector2(0, 0)
        self.on_ground = False
        self.facing = 1
        self.controls = controls
        self.ai = ai
        self.max_hp = PLAYER_MAX_HP
        self.hitpoints = PLAYER_MAX_HP
        self.attack_timer = 0
        self.threat_timer = 0
        self.dash_timer = 0
        self.dash_cooldown = 0
        self.invuln = 0
        self.invuln_until_landed = False
        self.powerup = None
        self.power_intent = False
        self.power_target = None
        self.sprite_frame = 0
        self.sprite_tick = 0
        self.score = 0
        self.base_radius = 10
        self.size_scale = 1.0
        self.radius = self.base_radius
        self.speed_multiplier = 1.0
        self.strength_multiplier = 1.0
        self.is_boss = False
        self.remote_id = None
        self.move_intent = 0
        self.jump_intent = False
        self.attack_intent = False
        self.dash_intent = False
        self.pickup_intent = False
        self.shockwave_intent = False
        self.shockwave_timer = 0
        self.carried_block = None
        self.throw_intent = False
        self.throw_dir = pygame.Vector2(1, 0)
        self.pickup_target = None
        self.jumped_this_frame = False
        self.prev_vel_y = 0
        self.jump_power = JUMP_VELOCITY
        self.jump_count = 0
        self.jump_multiplier = 1.0
        self.prev_jump_intent = False
        self.prev_dash_button = False
        self.respawn_timer = 0
        self.freeze_timer = 0
        self.burn_timer = 0
        self.poison_timer = 0
        self.burn_tick_timer = BURN_TICK
        self.poison_tick_timer = POISON_TICK
        self.damage_flash = 0
        self.slow_timer = 0
        self.attack_range_bonus = 0
        self.attack_cooldown_multiplier = 1.0
        self.rapid_timer = 0
        self.cleave_timer = 0
        self.pulse_timer = 0
        self.lunge_timer = 0
        self.attack_flash_timer = 0
        self.attack_flash_pos = None
        self.projectile_ghost_timer = 0
        self.ghosted_tile = None
        self.personality = {
            "name": "neutral",
            "aggression": 0.5,
            "wander": 0.4,
            "space": TILE_SIZE * 2.5,
            "power_use": 0.08,
        }

    def set_personality(self, profile):
        self.personality = dict(profile)

    def read_input(self, keys):
        if self.controls is None:
            return
        left = keys[self.controls["left"]]
        right = keys[self.controls["right"]]
        self.move_intent = (1 if right else 0) - (1 if left else 0)
        self.jump_intent = keys[self.controls["jump"]] or keys[self.controls["jump_alt"]]
        self.attack_intent = keys[self.controls["attack"]]
        dash_pressed = keys[self.controls["dash"]]
        self.dash_intent = dash_pressed and not self.prev_dash_button
        self.prev_dash_button = dash_pressed
        self.shockwave_intent = keys[self.controls["shockwave"]]

    def ai_input(self, world, opponents, boss=None, powerups=None, frenzy_active=False):
        # Personality-driven combat AI with situational power usage.
        if not opponents:
            self.move_intent = 0
            self.jump_intent = False
            self.attack_intent = False
            self.dash_intent = False
            self.pickup_intent = False
            self.throw_intent = False
            self.shockwave_intent = False
            self.power_intent = False
            self.power_target = None
            return

        living = [p for p in opponents if getattr(p, "hitpoints", 0) > 0]
        if not living:
            living = opponents

        target = min(living, key=lambda p: (p.pos - self.pos).length_squared())
        to_target = target.pos - self.pos
        dist_sq = to_target.length_squared()
        dist = math.sqrt(dist_sq) if dist_sq > 0 else 0.0
        if dist_sq > 0:
            self.throw_dir = to_target.normalize()

        aggression = float(self.personality.get("aggression", 0.55))
        wander = float(self.personality.get("wander", 0.40))
        desired_space = float(self.personality.get("space", TILE_SIZE * 2.6))
        power_use = float(self.personality.get("power_use", 0.10))
        build_bias = float(self.personality.get("build_bias", 0.10))
        dig_bias = float(self.personality.get("dig_bias", 0.10))
        defense = float(self.personality.get("defense", 0.85))

        # Threat signal is computed by the game loop (projectiles + melee wind-ups).
        threatened = getattr(self, "threat_timer", 0) > 0

        # Base intents
        self.attack_intent = False
        self.dash_intent = False
        self.jump_intent = False
        self.pickup_intent = False
        self.throw_intent = False
        self.shockwave_intent = False
        self.power_intent = False
        self.power_target = None

        # Movement: approach, kite, or roam depending on spacing and personality.
        if dist > desired_space * 1.4:
            self.move_intent = 1 if to_target.x > 12 else (-1 if to_target.x < -12 else 0)
        elif dist < desired_space * 0.85:
            self.move_intent = -1 if to_target.x > 0 else 1
        else:
            if random.random() < 0.06 + 0.10 * wander:
                self.move_intent = random.choice([-1, 0, 1])

        # Jump: reach vertical targets or dodge under pressure.
        if abs(to_target.y) > 26 and random.random() < 0.55:
            self.jump_intent = True
        elif threatened and random.random() < 0.18 + 0.10 * aggression:
            self.jump_intent = True

        # Dash: close quickly or disengage.
        if dist > 170 and random.random() < 0.18 + 0.12 * aggression:
            self.dash_intent = True
        elif threatened and dist < 120 and random.random() < 0.20 + 0.10 * aggression:
            self.dash_intent = True

        # Attack and shockwave.
        if dist < 95 and random.random() < 0.22 + 0.55 * aggression:
            self.attack_intent = True
        if threatened and dist < 95 and random.random() < 0.05 + 0.12 * aggression:
            self.shockwave_intent = True

        # Opportunistic digging/tunneling through blocks.
        ahead_tx = int((self.pos.x + self.facing * TILE_SIZE) // TILE_SIZE)
        ahead_ty = int(self.pos.y // TILE_SIZE)
        ahead_tile = world.get_tile(ahead_tx, ahead_ty)
        if ahead_tile != BLOCK_EMPTY and random.random() < dig_bias:
            self.attack_intent = True
            if random.random() < 0.22 + 0.18 * dig_bias:
                self.shockwave_intent = True

        # Powerup seeking.
        powerup_target = None
        if powerups:
            try:
                powerup_target = min(powerups, key=lambda orb: (orb.pos - self.pos).length_squared())
            except Exception:
                powerup_target = None

        if powerup_target and random.random() < 0.10 + 0.25 * wander:
            self.move_intent = 1 if powerup_target.pos.x > self.pos.x else -1
            if abs(powerup_target.pos.y - self.pos.y) > 18:
                self.jump_intent = True

        # Block pickup/throw (builder archetype uses blocks more aggressively).
        if self.carried_block is None:
            if random.random() < 0.10 + 0.18 * build_bias + (0.08 if threatened else 0.0):
                self.pickup_intent = True
        else:
            if (dist < 280 and random.random() < 0.08 + 0.18 * aggression) or (random.random() < 0.05 + 0.22 * build_bias):
                self.throw_intent = True

        # Power usage:
        # - "shield" is treated as a defensive reaction (used only while being attacked).
        if self.powerup:
            if self.powerup == "shield":
                if threatened and random.random() < defense:
                    self.power_intent = True
                    self.power_target = target
            else:
                if random.random() < power_use:
                    self.power_intent = True
                    self.power_target = target

        if self.is_boss:
            self.attack_intent = True
            if abs(to_target.y) > 20 and random.random() < 0.65:
                self.jump_intent = True
            if dist > 180 and random.random() < 0.30:
                self.dash_intent = True

        if self.throw_intent:
            direction = (target.pos - self.pos)
            if direction.length_squared() > 0:
                self.throw_dir = direction.normalize()

    def apply_powerup(self, power, world=None):
        self.powerup = power
        self.power_intent = False
        self.power_target = None

    def update_size(self):
        boss_scale = 2.0 if self.is_boss else 1.0
        effective_scale = max(self.size_scale, boss_scale)
        self.radius = int(self.base_radius * effective_scale)
        return effective_scale

    def damage_multiplier(self):
        mult = self.strength_multiplier
        if self.is_boss:
            mult *= 2.0
        return mult

    def take_damage(self, amount, allow_kill=True):
        if getattr(self, 'invuln_until_landed', False):
            return False
        if self.invuln > 0:
            return False
        if not allow_kill and self.hitpoints - amount <= 0:
            self.hitpoints = 1
        else:
            self.hitpoints -= amount
        self.invuln = FPS // 6
        self.damage_flash = FPS // 8
        return self.hitpoints <= 0

    def apply_knockback(self, source_pos, strength, world):
        direction = self.pos - source_pos
        if direction.length_squared() == 0:
            direction = pygame.Vector2(self.facing, 0)
        direction = direction.normalize()
        self.vel.x += direction.x * strength
        self.vel.y -= abs(direction.y) * strength * 0.6 * world.gravity_dir

    def apply_projectile_effect(self, block_type, direction):
        if block_type == BLOCK_BLUE:
            self.freeze_timer = max(self.freeze_timer, FREEZE_DURATION)
        elif block_type == BLOCK_BROWN:
            self.slow_timer = max(self.slow_timer, SLOW_DURATION // 2)
        elif block_type == BLOCK_TEAL:
            knockback = direction.normalize() if direction.length_squared() > 0 else pygame.Vector2(self.facing, 0)
            self.vel += knockback * (BOUNCE_FORCE * 0.7)
            self.vel.y -= 2 * math.copysign(1, direction.y or -1)
        elif block_type == BLOCK_RED:
            self.burn_timer = max(self.burn_timer, BURN_DURATION)
            self.burn_tick_timer = BURN_TICK
        elif block_type == BLOCK_ORANGE:
            self.burn_timer = max(self.burn_timer, BURN_DURATION // 2)
            self.burn_tick_timer = max(1, BURN_TICK - 2)
        elif block_type == BLOCK_GREEN:
            self.poison_timer = max(self.poison_timer, POISON_DURATION)
            self.poison_tick_timer = POISON_TICK
            self.slow_timer = max(self.slow_timer, SLOW_DURATION)
        elif block_type == BLOCK_TOXIC:
            self.poison_timer = max(self.poison_timer, int(POISON_DURATION * 1.25))
            self.poison_tick_timer = max(1, POISON_TICK - 1)
        elif block_type == BLOCK_PURPLE:
            knockback = direction.normalize() if direction.length_squared() > 0 else pygame.Vector2(self.facing, 0)
            self.vel += knockback * BOUNCE_FORCE * 1.2
            self.vel.y -= 3 * math.copysign(1, direction.y or -1)
        elif block_type == BLOCK_YELLOW:
            self.freeze_timer = max(self.freeze_timer, FREEZE_DURATION // 3)
            knockback = direction.normalize() if direction.length_squared() > 0 else pygame.Vector2(self.facing, 0)
            self.vel += knockback * (BOUNCE_FORCE * 0.5)
        elif block_type == BLOCK_BLACK:
            self.slow_timer = max(self.slow_timer, int(SLOW_DURATION * 1.3))
            self.burn_timer = max(self.burn_timer, BURN_DURATION // 3)
            self.burn_tick_timer = BURN_TICK

    def update(self, world, players, boss=None, powerups=None, frenzy_active=False):
        if self.ai:
            opponents = [p for p in players if p is not self]
            self.ai_input(world, opponents, boss=boss, powerups=powerups, frenzy_active=frenzy_active)

        if getattr(self, 'threat_timer', 0) > 0:
            self.threat_timer -= 1

        if self.respawn_timer > 0:
            self.respawn_timer -= 1
            self.invuln = max(self.invuln, self.respawn_timer)
            self.move_intent = 0
            self.jump_intent = False
            self.attack_intent = False
            self.dash_intent = False
            self.pickup_intent = False
            self.throw_intent = False
            self.shockwave_intent = False

        if self.invuln > 0:
            self.invuln -= 1
            self.attack_intent = False
            self.throw_intent = False
            self.shockwave_intent = False
            self.power_intent = False
        if self.freeze_timer > 0:
            self.freeze_timer -= 1
        if self.burn_timer > 0:
            self.burn_timer -= 1
            self.burn_tick_timer -= 1
            if self.burn_tick_timer <= 0:
                if self.hitpoints > 1:
                    self.take_damage(1, allow_kill=False)
                self.burn_tick_timer = BURN_TICK
        if self.poison_timer > 0:
            self.poison_timer -= 1
            self.poison_tick_timer -= 1
            if self.poison_tick_timer <= 0:
                if self.hitpoints > 1:
                    self.take_damage(1, allow_kill=False)
                self.poison_tick_timer = POISON_TICK
        if self.damage_flash > 0:
            self.damage_flash -= 1
        if self.slow_timer > 0:
            self.slow_timer -= 1
        if self.rapid_timer > 0:
            self.rapid_timer -= 1
            self.attack_cooldown_multiplier = 0.6
        else:
            self.attack_cooldown_multiplier = 1.0
        if self.cleave_timer > 0:
            self.cleave_timer -= 1
        if self.pulse_timer > 0:
            self.pulse_timer -= 1
        if self.lunge_timer > 0:
            self.lunge_timer -= 1
            self.attack_range_bonus = 8
        elif self.attack_range_bonus != 0:
            self.attack_range_bonus = 0
        if self.attack_flash_timer > 0:
            self.attack_flash_timer -= 1
        if self.projectile_ghost_timer > 0:
            self.projectile_ghost_timer -= 1
            if self.projectile_ghost_timer == 0:
                self.ghosted_tile = None

        if self.attack_timer > 0:
            self.attack_timer -= 1
        if self.dash_timer > 0:
            self.dash_timer -= 1
        if self.dash_cooldown > 0:
            self.dash_cooldown -= 1
        if self.shockwave_timer > 0:
            self.shockwave_timer -= 1

        if self.freeze_timer > 0:
            self.move_intent = 0
            self.jump_intent = False
            self.attack_intent = False
            self.dash_intent = False
            self.pickup_intent = False
            self.throw_intent = False
            self.shockwave_intent = False
        slow_factor = SLOW_MULTIPLIER if self.slow_timer > 0 else 1.0
        if self.dash_timer > 0:
            speed = DASH_SPEED * self.facing * self.speed_multiplier * slow_factor
        else:
            speed = MOVE_SPEED * self.move_intent * self.speed_multiplier * slow_factor

        self.vel.x = speed
        if self.dash_timer > 0:
            self.damage_dash_blocks(world)

        if self.dash_intent and self.dash_cooldown <= 0:
            self.dash_timer = DASH_DURATION
            self.dash_cooldown = FPS // 2
            self.dash_intent = False
        if self.shockwave_intent and self.shockwave_timer <= 0:
            self.perform_shockwave(world)
            self.shockwave_timer = SHOCKWAVE_COOLDOWN
            self.shockwave_intent = False

        if self.on_ground:
            self.jump_count = 0
        touching_wall = self.touching_wall(world)
        if touching_wall and not self.on_ground:
            self.jump_count = min(self.jump_count, 1)
        self.jumped_this_frame = False
        if self.jump_intent and not self.prev_jump_intent:
            if self.on_ground or touching_wall or self.jump_count < 2:
                base_jump = JUMP_VELOCITY if self.jump_count == 0 else DOUBLE_JUMP_VELOCITY
                self.jump_power = base_jump * self.jump_multiplier
                self.vel.y = -self.jump_power * world.gravity_dir
                self.on_ground = False
                self.jumped_this_frame = True
                self.jump_count += 1
        self.vel.y += GRAVITY_STRENGTH * world.gravity_dir
        self.vel.y = max(min(self.vel.y, MAX_VERTICAL_SPEED), -MAX_VERTICAL_SPEED)
        self.prev_vel_y = self.vel.y

        self.move_with_collisions(world, axis=0, amount=self.vel.x)

        self.on_ground = False
        self.move_with_collisions(world, axis=1, amount=self.vel.y)

        # Drop-spawn immunity ends on first landing.
        if getattr(self, 'invuln_until_landed', False) and self.on_ground:
            self.invuln_until_landed = False

        if self.attack_intent and self.attack_timer <= 0:
            self.attack_timer = max(6, int(ATTACK_COOLDOWN * self.attack_cooldown_multiplier))
            self.perform_attack(world, players, boss=boss)
            self.attack_intent = False

        if self.pickup_intent and self.respawn_timer <= 0:
            self.try_pickup_or_drop(world)
            self.pickup_intent = False

        self.sprite_tick = (self.sprite_tick + 1) % 60
        if self.sprite_tick % 8 == 0:
            self.sprite_frame = (self.sprite_frame + 1) % 4

        if self.move_intent != 0 and self.respawn_timer <= 0:
            self.facing = 1 if self.move_intent > 0 else -1
        if self.on_ground and not self.jump_intent:
            self.jump_power = JUMP_VELOCITY * self.jump_multiplier
        self.update_size()
        self.prev_jump_intent = self.jump_intent

    def perform_attack(self, world, players, boss=None):
        attack_range = 18 + self.attack_range_bonus
        attack_centers = [pygame.Vector2(self.pos.x + self.facing * attack_range, self.pos.y)]
        if self.cleave_timer > 0:
            attack_centers.append(pygame.Vector2(self.pos.x - self.facing * attack_range, self.pos.y))
        damage = max(1, int(round(self.damage_multiplier())))
        self.attack_flash_timer = FPS // 6
        for attack_center in attack_centers:
            self.attack_flash_pos = pygame.Vector2(attack_center)
            for other in players:
                if other is self:
                    continue
                if (other.pos - attack_center).length() < 20:
                    previous_hp = other.hitpoints
                    killed = other.take_damage(damage)
                    if other.hitpoints < previous_hp:
                        self.score += 1
                        other.apply_knockback(self.pos, 4.0, world)
                    if killed:
                        self.score += 1
                        other.vel.x += self.facing * 3
                        other.vel.y -= 2 * world.gravity_dir
                        other.pvp_respawn_timer = FPS * 3
                        other.pvp_pending_respawn = False
                        other.waiting_for_boss_respawn = False
                        other.death_order = None
            if boss and boss.alive:
                if (boss.pos - attack_center).length() < boss.radius + 6:
                    if boss.take_damage(damage, self):
                        pass
            tx = int((attack_center.x) / TILE_SIZE)
            ty = int((attack_center.y) / TILE_SIZE)
            for ox in range(-DIG_RANGE, DIG_RANGE + 1):
                for oy in range(-DIG_RANGE, DIG_RANGE + 1):
                    world.damage_tile(tx + ox, ty + oy, damage)
        if self.pulse_timer > 0:
            self.perform_shockwave(world)

    def damage_dash_blocks(self, world):
        dash_tx = int((self.pos.x + self.facing * TILE_SIZE) // TILE_SIZE)
        dash_ty = int(self.pos.y // TILE_SIZE)
        for oy in (-1, 0, 1):
            world.damage_tile(dash_tx, dash_ty + oy, 1)

    def perform_shockwave(self, world):
        center_tx = int(self.pos.x // TILE_SIZE)
        center_ty = int(self.pos.y // TILE_SIZE)
        weak_blocks = []
        for ox in range(-3, 4):
            for oy in range(-3, 4):
                tx = center_tx + ox
                ty = center_ty + oy
                if world.get_hp(tx, ty) == 1:
                    weak_blocks.append((tx, ty))
        random.shuffle(weak_blocks)
        for tx, ty in weak_blocks[:8]:
            world.damage_tile(tx, ty, 1)

    def try_pickup_or_drop(self, world):
        if self.carried_block is None:
            if self.pickup_target:
                tx, ty = self.pickup_target
                tile = world.get_tile(tx, ty)
                if tile != BLOCK_EMPTY and tile != BLOCK_BLACK:
                    self.carried_block = tile
                    world.set_tile(tx, ty, BLOCK_EMPTY, 0)
                self.pickup_target = None
                return
            current_tx = int(self.pos.x // TILE_SIZE)
            current_ty = int(self.pos.y // TILE_SIZE)
            tile = world.get_tile(current_tx, current_ty)
            if tile != BLOCK_EMPTY and tile != BLOCK_BLACK:
                self.carried_block = tile
                world.set_tile(current_tx, current_ty, BLOCK_EMPTY, 0)
                return
            tx = int((self.pos.x + self.facing * TILE_SIZE) // TILE_SIZE)
            ty = int(self.pos.y // TILE_SIZE)
            tile = world.get_tile(tx, ty)
            if tile != BLOCK_EMPTY and tile != BLOCK_BLACK:
                self.carried_block = tile
                world.set_tile(tx, ty, BLOCK_EMPTY, 0)
        else:
            drop_tx = int((self.pos.x + self.facing * TILE_SIZE) // TILE_SIZE)
            drop_ty = int(self.pos.y // TILE_SIZE)
            if world.get_tile(drop_tx, drop_ty) == BLOCK_EMPTY:
                world.set_tile(drop_tx, drop_ty, self.carried_block, BLOCK_HP[self.carried_block])
                self.carried_block = None

    def touching_wall(self, world):
        tx = int(self.pos.x // TILE_SIZE)
        ty = int(self.pos.y // TILE_SIZE)
        return world.get_tile(tx - 1, ty) != BLOCK_EMPTY or world.get_tile(tx + 1, ty) != BLOCK_EMPTY

    def try_throw(self):
        if self.carried_block is None:
            return None
        direction = self.throw_dir
        if direction.length_squared() == 0:
            direction = pygame.Vector2(self.facing, 0)
        speed = THROW_SPEED + self.strength_multiplier
        projectile = BlockProjectile(
            pygame.Vector2(self.pos),
            direction.normalize() * speed,
            self.carried_block,
            BLOCK_HP[self.carried_block],
            self,
        )
        self.carried_block = None
        return projectile

    def detonate_bomb(self, world):
        center_tx = int(self.pos.x // TILE_SIZE)
        center_ty = int(self.pos.y // TILE_SIZE)
        for ox in range(-5, 6):
            for oy in range(-5, 6):
                if ox * ox + oy * oy <= 25:
                    world.damage_tile(center_tx + ox, center_ty + oy, 10)

    def resolve_collisions(self, world, axis=0):
        rect = pygame.Rect(self.pos.x - self.radius, self.pos.y - self.radius, self.radius * 2, self.radius * 2)
        min_tx = int(rect.left // TILE_SIZE) - 1
        max_tx = int(rect.right // TILE_SIZE) + 1
        min_ty = int(rect.top // TILE_SIZE) - 1
        max_ty = int(rect.bottom // TILE_SIZE) + 1

        for tx in range(min_tx, max_tx + 1):
            for ty in range(min_ty, max_ty + 1):
                if world.get_tile(tx, ty) == BLOCK_EMPTY:
                    continue
                tile_rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                if rect.colliderect(tile_rect):
                    if self.projectile_ghost_timer > 0 and self.ghosted_tile == (tx, ty):
                        continue
                    if axis == 0:
                        if self.vel.x > 0:
                            rect.right = tile_rect.left
                        elif self.vel.x < 0:
                            rect.left = tile_rect.right
                        self.pos.x = rect.centerx
                        self.vel.x = 0
                    else:
                        if self.vel.y * world.gravity_dir > 0:
                            rect.bottom = tile_rect.top
                            self.on_ground = True
                            if abs(self.prev_vel_y) > 3:
                                world.damage_tile(tx, ty, 1)
                        elif self.vel.y * world.gravity_dir < 0:
                            rect.top = tile_rect.bottom
                            if self.jump_power > JUMP_VELOCITY + 0.5:
                                world.damage_tile(tx, ty, 1)
                        self.pos.y = rect.centery
                        self.vel.y = 0

    def move_with_collisions(self, world, axis, amount):
        step = TILE_SIZE / 2
        remaining = amount
        while abs(remaining) > 0:
            move = max(-step, min(step, remaining))
            if axis == 0:
                self.pos.x += move
            else:
                self.pos.y += move
            self.resolve_collisions(world, axis=axis)
            remaining -= move


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.layer = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self.block_surfaces = self._create_block_surfaces()
        self.player_frames = self._create_player_frames()
        self.boss_blob = self._create_boss_blob_surface()
        self.font = pygame.font.SysFont("consolas", 11)
        self.hud_font = pygame.font.SysFont("consolas", 13)
        rng = random.Random(42)
        w, h = self.screen.get_size()
        self.stars = [
            (
                rng.randrange(0, w),
                rng.randrange(0, h),
                rng.choice([1, 1, 2]),
                rng.choice(NEON_GLOW_COLORS),
            )
            for _ in range(120)
        ]
        self.background_variant = random.choice(BACKGROUND_VARIANTS)
        # Champion emblem cache (highest scoring player badge in background)
        self._champion_key = None
        self._champion_emblem = None

        # Camera screen bias to show more sky above the action
        self.camera_bias_y = CAMERA_SCREEN_BIAS_Y

        # Prebuilt distant mountain layers (block-based, shaded)
        self._mountain_layers = self._build_mountain_layers()
        # Prebuilt nearer ground silhouette layer (block-based, shaded)
        self._ground_layer = self._build_ground_layer()
        self._background_gradient_cache = None
        self._background_gradient_cache = None
        self._frame_cache = {}
        self._glow_cache = {}
        self._name_surface_cache = {}
        self._powerup_glow_cache = {}
        self._boss_surface_cache = {}
        self._boss_glow_cache = {}

    def randomize_background(self):
        self.background_variant = random.choice(BACKGROUND_VARIANTS)

    def on_resize(self, new_screen):
        """Rebind renderer to a new display surface and rebuild size-dependent caches."""
        self.screen = new_screen
        self.layer = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        w, h = self.screen.get_size()
        rng = random.Random(42)
        self.stars = [
            (
                rng.randrange(0, w),
                rng.randrange(0, h),
                rng.choice([1, 1, 2]),
                rng.choice(NEON_GLOW_COLORS),
            )
            for _ in range(120)
        ]
        # Rebuild parallax layers for the new size.
        self._mountain_layers = self._build_mountain_layers()
        self._ground_layer = self._build_ground_layer()

    def draw_champion_emblem(self, boss, players):
        """Draw a semi-transparent circular champion emblem.

        Champion is the highest-scoring living player (ties broken by name).
        """
        if not players:
            return

        living = [
            p
            for p in players
            if getattr(p, "hitpoints", 0) > 0 and not getattr(p, "waiting_for_boss_respawn", False)
        ]
        pool = living if living else list(players)

        try:
            champ = sorted(
                pool,
                key=lambda p: (-int(getattr(p, "score", 0)), str(getattr(p, "name", ""))),
            )[0]
        except Exception:
            return

        frames = self.player_frames.get(getattr(champ, "name", ""))
        if not frames:
            return
        champ_surface = frames[0]

        champ_name = str(getattr(champ, "name", "")).upper()
        champ_score = int(getattr(champ, "score", 0))

        # Circular badge, top-center. Sized to avoid the top-left HUD.
        badge_r = 78
        pad = 14
        badge_w = badge_r * 2 + pad * 2
        badge_h = badge_r * 2 + pad * 2 + 44  # room for name/score beneath
        x = SCREEN_WIDTH // 2 - badge_w // 2
        y = 10

        badge = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)

        center = (badge_w // 2, pad + badge_r)

        # Soft back glow
        glow = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
        pygame.draw.circle(glow, (80, 255, 255, 18), center, badge_r + 26)
        pygame.draw.circle(glow, (120, 200, 255, 22), center, badge_r + 16)
        badge.blit(glow, (0, 0))

        # Main disc
        pygame.draw.circle(badge, (10, 15, 30, 140), center, badge_r)
        pygame.draw.circle(badge, (80, 255, 255, 95), center, badge_r, 2)
        pygame.draw.circle(badge, (120, 200, 255, 55), center, badge_r - 10, 2)

        # Champion sprite inside disc
        try:
            target_h = int(badge_r * 1.05)
            scale = target_h / float(max(1, champ_surface.get_height()))
            target_w = max(1, int(champ_surface.get_width() * scale))
            sprite = pygame.transform.scale(champ_surface, (target_w, target_h)).convert_alpha()
        except Exception:
            sprite = champ_surface.copy()

        # Slightly dim the sprite so it reads as an emblem layer
        sprite = sprite.copy()
        fade = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
        fade.fill((255, 255, 255, 120))
        sprite.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        badge.blit(sprite, (center[0] - sprite.get_width() // 2, center[1] - sprite.get_height() // 2))

        # Text beneath (centered)
        label = self.font.render("LEADER", True, (130, 210, 220))
        name_surf = self.hud_font.render(champ_name, True, (230, 235, 255))
        score_surf = self.font.render(f"SCORE {champ_score}", True, (180, 190, 220))

        tx = badge_w // 2
        badge.blit(label, (tx - label.get_width() // 2, pad + badge_r * 2 + 2))
        badge.blit(name_surf, (tx - name_surf.get_width() // 2, pad + badge_r * 2 + 18))
        badge.blit(score_surf, (tx - score_surf.get_width() // 2, pad + badge_r * 2 + 34))

        badge.set_alpha(135)
        self.screen.blit(badge, (x, y))

    def _create_block_surfaces(self):
        os.makedirs(ASSET_DIR, exist_ok=True)
        surfaces = {}
        for block_type, color in BLOCK_COLORS.items():
            surface = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            r, g, b, a = color
            if block_type == BLOCK_BLACK:
                pygame.draw.rect(surface, (r, g, b, a), pygame.Rect(0, 0, TILE_SIZE, TILE_SIZE), border_radius=2)
                pygame.draw.rect(surface, (60, 60, 70, 220), pygame.Rect(1, 1, TILE_SIZE - 2, TILE_SIZE - 2), 1)
                for i in range(0, TILE_SIZE, 4):
                    pygame.draw.line(surface, (30, 30, 40, 200), (i, 0), (i, TILE_SIZE))
            else:
                for i in range(3):
                    pygame.draw.rect(
                        surface,
                        (r, g, b, max(0, a - i * 40)),
                        pygame.Rect(i, i, TILE_SIZE - i * 2, TILE_SIZE - i * 2),
                        border_radius=3,
                    )
                highlight = (min(r + 60, 255), min(g + 60, 255), min(b + 60, 255), 200)
                pygame.draw.line(surface, highlight, (2, 2), (TILE_SIZE - 3, 2), 2)
                pygame.draw.line(surface, highlight, (2, 2), (2, TILE_SIZE - 3), 2)
            try:
                surface = surface.convert_alpha()
            except Exception:
                pass
            surfaces[block_type] = surface
            pygame.image.save(surface, os.path.join(ASSET_DIR, f"block_{block_type}.png"))
        return surfaces

    def _draw_pixel_pattern(self, surface, pattern, palette, pixel):
        for y, row in enumerate(pattern):
            for x, cell in enumerate(row):
                color = palette.get(cell)
                if not color:
                    continue
                rect = pygame.Rect(x * pixel, y * pixel, pixel, pixel)
                pygame.draw.rect(surface, color, rect)

    def _create_player_frames(self):
        os.makedirs(ASSET_DIR, exist_ok=True)
        pixel = 2
        sprite_defs = {
            "alien": {
                "palette": {"X": (90, 240, 130), "O": (40, 160, 90), "E": (10, 10, 20), "A": (150, 255, 170)},
                "base": [
                    "....A..A....",
                    ".....AA.....",
                    "....XXXX....",
                    "....XOOOX...",
                    "...XOEOX....",
                    "...XOOOOX...",
                    "....XXXX....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "..X.XX.X....",
                    "...X..X.....",
                    "............",
                ],
                "alt": [
                    "....A..A....",
                    ".....AA.....",
                    "....XXXX....",
                    "....XOOOX...",
                    "...XOEOX....",
                    "...XOOOOX...",
                    "....XXXX....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "............",
                ],
            },
            "fatman": {
                "palette": {"X": (220, 140, 90), "O": (255, 210, 180), "E": (30, 20, 20), "B": (120, 70, 50)},
                "base": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOOOOOOX..",
                    "..XOEOEOOX..",
                    "..XOOOOOOX..",
                    "..XOOOOOOX..",
                    "..XOBBXOOX..",
                    "..XOBBXOOX..",
                    "..XOOOOOOX..",
                    "...XOOOOX...",
                    "....XXXX....",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOOOOOOX..",
                    "..XOEOEOOX..",
                    "..XOOOOOOX..",
                    "..XOOOOOOX..",
                    "..XOBBXOOX..",
                    "..XOBBXOOX..",
                    "..XOOOOOOX..",
                    "...XOOOOX...",
                    "....X..X....",
                    "...X....X...",
                ],
            },
            "robot": {
                "palette": {"X": (150, 180, 200), "O": (80, 110, 130), "E": (20, 240, 255), "B": (60, 70, 90)},
                "base": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "...XOEEOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XBBX....",
                    "...XBBBBX...",
                    "...XBBBBX...",
                    "....XBBX....",
                    "...X....X...",
                    "...X....X...",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "...XOEEOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XBBX....",
                    "...XBBBBX...",
                    "...XBBBBX...",
                    "....XBBX....",
                    "....X..X....",
                    "...X....X...",
                    "............",
                ],
            },
            "reptilian": {
                "palette": {"X": (80, 200, 110), "O": (40, 120, 70), "E": (255, 220, 40), "B": (30, 70, 40)},
                "base": [
                    "....XXXX....",
                    "...XOOOX....",
                    "..XOEOOX....",
                    "..XOOOXX....",
                    "...XXXX.....",
                    "...XBBX.....",
                    "..XBBBBX....",
                    "..XBBBBX....",
                    "...XBBX.....",
                    "..X..X......",
                    "...X..X.....",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOX....",
                    "..XOEOOX....",
                    "..XOOOXX....",
                    "...XXXX.....",
                    "...XBBX.....",
                    "..XBBBBX....",
                    "..XBBBBX....",
                    "...XBBX.....",
                    "...X..X.....",
                    "..X..X......",
                    "............",
                ],
            },
            "mantis": {
                "palette": {"X": (120, 255, 140), "O": (60, 160, 80), "E": (20, 20, 20), "B": (40, 90, 50)},
                "base": [
                    "....X..X....",
                    "....XEXX....",
                    "...XXXXX....",
                    "..XOOOXX....",
                    "...XXXXX....",
                    "...XBBX.....",
                    "..XBBBBX....",
                    "...XBBX.....",
                    "..X....X....",
                    "...X..X.....",
                    "..X..X......",
                    "............",
                ],
                "alt": [
                    "....X..X....",
                    "....XEXX....",
                    "...XXXXX....",
                    "..XOOOXX....",
                    "...XXXXX....",
                    "...XBBX.....",
                    "..XBBBBX....",
                    "...XBBX.....",
                    "...X..X.....",
                    "..X..X......",
                    "...X..X.....",
                    "............",
                ],
            },
            "monkey": {
                "palette": {"X": (150, 90, 50), "O": (220, 170, 120), "E": (20, 20, 20), "T": (120, 70, 40)},
                "base": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...XTTX.....",
                    "..XTTTTX....",
                    "..XTTTTX....",
                    "...XTTX.....",
                    "..X....X....",
                    "...X..X.....",
                    "....X.......",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...XTTX.....",
                    "..XTTTTX....",
                    "..XTTTTX....",
                    "...XTTX.....",
                    "...X..X.....",
                    "..X....X....",
                    "...X........",
                ],
            },
            "skeleton": {
                "palette": {"X": (230, 230, 230), "O": (180, 180, 180), "E": (20, 20, 20)},
                "base": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "..X.XX.X....",
                    "...X..X.....",
                    "..X....X....",
                    "...X..X.....",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "...X..X.....",
                    "..X.XX.X....",
                    "...X..X.....",
                    "..X....X....",
                    "............",
                ],
            },
            "witch": {
                "palette": {"X": (120, 80, 200), "O": (220, 180, 240), "E": (20, 20, 20), "H": (40, 20, 60)},
                "base": [
                    ".....H......",
                    "....HHH.....",
                    "...HHHHH....",
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...XHHX.....",
                    "..XHHHHX....",
                    "..X....X....",
                    "............",
                ],
                "alt": [
                    ".....H......",
                    "....HHH.....",
                    "...HHHHH....",
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "...XOOOX....",
                    "...XHHX.....",
                    "..XHHHHX....",
                    "...X..X.....",
                    "..X....X....",
                ],
            },
            "blob": {
                "palette": {"X": (140, 220, 255), "O": (80, 150, 190), "E": (20, 20, 30)},
                "base": [
                    "............",
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "..XOOOOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....X..X....",
                    "...X..X.....",
                    "............",
                    "............",
                ],
                "alt": [
                    "............",
                    "....XXXX....",
                    "...XOOOOX...",
                    "..XOEOEOX...",
                    "..XOOOOOX...",
                    "..XOOOOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "...X..X.....",
                    "....X..X....",
                    "............",
                    "............",
                ],
            },
            "knight": {
                "palette": {"X": (180, 180, 200), "O": (100, 100, 120), "E": (20, 20, 20), "C": (200, 60, 60)},
                "base": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "...XOEOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XCCX....",
                    "...XCCCCX...",
                    "...XCCCCX...",
                    "....XCCX....",
                    "...X....X...",
                    "....X..X....",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOOX...",
                    "...XOEOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XCCX....",
                    "...XCCCCX...",
                    "...XCCCCX...",
                    "....XCCX....",
                    "....X..X....",
                    "...X....X...",
                    "............",
                ],
            },
            "cyber": {
                "palette": {"X": (90, 200, 255), "O": (40, 90, 120), "E": (255, 40, 140), "B": (30, 30, 40)},
                "base": [
                    "....XXXX....",
                    "...XOOOEX...",
                    "...XOOOEX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XBBX....",
                    "...XBBBBX...",
                    "...XBBBBX...",
                    "....XBBX....",
                    "...X....X...",
                    "....X..X....",
                    "............",
                ],
                "alt": [
                    "....XXXX....",
                    "...XOOOEX...",
                    "...XOOOEX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....XBBX....",
                    "...XBBBBX...",
                    "...XBBBBX...",
                    "....XBBX....",
                    "....X..X....",
                    "...X....X...",
                    "............",
                ],
            },
            "pixie": {
                "palette": {"X": (255, 160, 220), "O": (255, 220, 245), "E": (20, 20, 20), "W": (180, 255, 240)},
                "base": [
                    ".....W......",
                    "....WWW.....",
                    "...WXXXW....",
                    "...XOOOOX...",
                    "...XOEOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....X..X....",
                    "...X.XX.X...",
                    "....X..X....",
                    "............",
                    "............",
                ],
                "alt": [
                    ".....W......",
                    "....WWW.....",
                    "...WXXXW....",
                    "...XOOOOX...",
                    "...XOEOOX...",
                    "...XOOOOX...",
                    "....XXXX....",
                    "....X..X....",
                    "....X..X....",
                    "...X.XX.X...",
                    "............",
                    "............",
                ],
            },
        }

        frames = {}
        for name, data in sprite_defs.items():
            palette = data["palette"]
            base = data["base"]
            alt = data["alt"]
            frame_list = []
            for pattern in (base, alt, base, alt):
                surf = pygame.Surface((len(pattern[0]) * pixel, len(pattern) * pixel), pygame.SRCALPHA)
                self._draw_pixel_pattern(surf, pattern, palette, pixel)
                try:
                    surf = surf.convert_alpha()
                except Exception:
                    pass
                frame_list.append(surf)
                pygame.image.save(surf, os.path.join(ASSET_DIR, f"player_{name}_{len(frame_list) - 1}.png"))
            frames[name] = frame_list
        return frames

    def _create_boss_blob_surface(self):
        pixel = 2
        palette = {"X": (140, 220, 255), "O": (80, 150, 190), "E": (20, 20, 30)}
        pattern = [
            "............",
            "....XXXX....",
            "...XOOOOX...",
            "..XOEOEOX...",
            "..XOOOOOX...",
            "..XOOOOOX...",
            "...XOOOOX...",
            "....XXXX....",
            "....X..X....",
            "...X..X.....",
            "............",
            "............",
        ]
        surf = pygame.Surface((len(pattern[0]) * pixel, len(pattern) * pixel), pygame.SRCALPHA)
        self._draw_pixel_pattern(surf, pattern, palette, pixel)
        try:
            surf = surf.convert_alpha()
        except Exception:
            pass
        pygame.image.save(surf, os.path.join(ASSET_DIR, "boss_blob.png"))
        return surf

    def _get_gradient_background(self):
        key = (self.screen.get_width(), self.screen.get_height(), tuple(self.background_variant))
        cached = self._background_gradient_cache
        if cached and cached[0] == key:
            return cached[1]
        surf = pygame.Surface(self.screen.get_size()).convert()
        top = self.background_variant[0]
        bottom = self.background_variant[-1]
        h = max(1, SCREEN_HEIGHT)
        for y in range(SCREEN_HEIGHT):
            blend = y / h
            color = (
                int(top[0] * (1 - blend) + bottom[0] * blend),
                int(top[1] * (1 - blend) + bottom[1] * blend),
                int(top[2] * (1 - blend) + bottom[2] * blend),
            )
            pygame.draw.line(surf, color, (0, y), (SCREEN_WIDTH, y))
        self._background_gradient_cache = (key, surf)
        return surf

    def _get_player_frame_for_draw(self, player):
        skin_key = getattr(player, "skin_key", str(getattr(player, "name", "player")).lower())
        frames = self.player_frames.get(skin_key) or self.player_frames.get(str(getattr(player, "name", "player")).lower())
        if not frames:
            frames = next(iter(self.player_frames.values()))
        frame = frames[player.sprite_frame % len(frames)]
        effective_scale = player.update_size()
        target_size = max(1, int(frame.get_width() * effective_scale))
        key = (skin_key, int(player.sprite_frame), 1 if player.facing < 0 else 0, target_size)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached
        frame_to_draw = frame if player.facing > 0 else pygame.transform.flip(frame, True, False)
        if frame_to_draw.get_width() != target_size:
            frame_to_draw = pygame.transform.scale(frame_to_draw, (target_size, target_size))
        try:
            frame_to_draw = frame_to_draw.convert_alpha()
        except Exception:
            pass
        self._frame_cache[key] = frame_to_draw
        return frame_to_draw

    def _get_glow_surface(self, size, color, alpha=80, pad=10):
        key = (int(size[0]), int(size[1]), tuple(color), int(alpha), int(pad))
        cached = self._glow_cache.get(key)
        if cached is not None:
            return cached
        surf = pygame.Surface((max(1, int(size[0])) + pad, max(1, int(size[1])) + pad), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (*color, alpha), surf.get_rect())
        self._glow_cache[key] = surf
        return surf

    def _get_name_surface(self, name):
        key = str(name).upper()
        cached = self._name_surface_cache.get(key)
        if cached is not None:
            return cached
        surf = self.font.render(key, True, (255, 255, 255))
        self._name_surface_cache[key] = surf
        return surf

    def _get_powerup_glow(self, kind):
        key = str(kind)
        cached = self._powerup_glow_cache.get(key)
        if cached is not None:
            return cached
        base_color = POWERUP_COLORS.get(kind, (200, 255, 200))
        glow = pygame.Surface((TILE_SIZE * 2, TILE_SIZE * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*base_color, 90), (TILE_SIZE, TILE_SIZE), TILE_SIZE)
        self._powerup_glow_cache[key] = glow
        return glow

    def draw_background(self, camera_offset, gravity_dir, rotation_deg):
        self.screen.blit(self._get_gradient_background(), (0, 0))

        # Stars (very light parallax)
        for idx, (sx, sy, size, color) in enumerate(self.stars):
            offset_x = int(camera_offset.x * (0.01 + (idx % 3) * 0.01))
            offset_y = int(camera_offset.y * (0.008 + (idx % 4) * 0.006))
            x = (sx + offset_x) % SCREEN_WIDTH
            y = (sy + offset_y) % SCREEN_HEIGHT
            pygame.draw.rect(self.screen, color, pygame.Rect(x, y, size, size))

        # Distant block mountains (shaded, far away, parallax)
        self._draw_mountain_layers(camera_offset)
        # Nearer block ground layer in front of mountains
        self._draw_ground_layer(camera_offset)

    def _build_mountain_layers(self):
        """Prebuild shaded, block-based mountain layers as transparent surfaces.

        Uses the same block visuals as the game world, but tinted/dimmed and drawn far in the distance.
        """
        rng = random.Random(1337)

        # Prefer darker / rocky-feeling blocks; fall back safely if surfaces are missing.
        pool = [BLOCK_BROWN, BLOCK_BLACK, BLOCK_PURPLE, BLOCK_BLUE, BLOCK_TEAL]
        pool = [b for b in pool if b in self.block_surfaces]
        if not pool:
            pool = [BLOCK_BROWN]

        def make_tile(tile_id, px, tint_rgb, alpha):
            base = self.block_surfaces[tile_id]
            tile = pygame.transform.scale(base, (px, px)).convert_alpha()
            tint = pygame.Surface(tile.get_size(), pygame.SRCALPHA)
            tint.fill((*tint_rgb, 255))
            tile.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            tile.set_alpha(alpha)
            return tile

        def build_layer(base_y, px, amp, parallax, tint_rgb, alpha, seed_offset):
            layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            cols = SCREEN_WIDTH // px + 3

            local_rng = random.Random(2000 + seed_offset)
            # Height profile via random walk + smoothing
            h = local_rng.randint(int(amp * 0.35), int(amp * 0.65))
            heights = []
            for _ in range(cols):
                h += local_rng.randint(-2, 2)
                h += int((amp * 0.50 - h) * 0.03)
                h = max(int(amp * 0.12), min(int(amp * 0.92), h))
                heights.append(h)

            for _ in range(3):
                for i in range(1, len(heights) - 1):
                    heights[i] = int((heights[i - 1] + heights[i] * 2 + heights[i + 1]) / 4)

            tile_cache = {tid: make_tile(tid, px, tint_rgb, alpha) for tid in pool}

            # Draw block columns downwards from a jagged ridgeline.
            # Keep this in the lower half so it never intrudes into the emblem area.
            for i, mh in enumerate(heights):
                x = i * px
                ridge_y = base_y - mh + local_rng.randint(-px // 2, px // 2)
                y = max(int(SCREEN_HEIGHT * 0.56), ridge_y)
                max_y = min(SCREEN_HEIGHT, base_y + int(px * 3.0))
                while y < max_y:
                    tid = local_rng.choice(pool)
                    layer.blit(tile_cache[tid], (x, y))
                    y += px

            return {"surface": layer, "parallax": parallax}

        # Far layer: smaller blocks, darker, higher base (still below emblem)
        far = build_layer(
            base_y=int(SCREEN_HEIGHT * 0.70),
            px=8,
            amp=int(SCREEN_HEIGHT * 0.18),
            parallax=0.045,
            tint_rgb=(65, 70, 88),
            alpha=90,
            seed_offset=1,
        )

        # Mid layer: slightly larger blocks, a bit brighter, lower base
        mid = build_layer(
            base_y=int(SCREEN_HEIGHT * 0.80),
            px=12,
            amp=int(SCREEN_HEIGHT * 0.24),
            parallax=0.080,
            tint_rgb=(80, 82, 100),
            alpha=120,
            seed_offset=2,
        )

        return [far, mid]

    def _build_ground_layer(self):
        """Prebuild a shaded, block-based ground layer that sits below and in front of the mountains.

        This layer fills down to the bottom of the screen and stays well below the champion emblem area.
        """
        # Prefer earthy / dark blocks; fall back safely.
        pool = [BLOCK_BROWN, BLOCK_BLACK, BLOCK_ORANGE, BLOCK_PURPLE, BLOCK_GREEN, BLOCK_BLUE]
        pool = [b for b in pool if b in getattr(self, "block_surfaces", {})]
        if not pool:
            pool = [BLOCK_BROWN]

        px = 16  # block size for the nearer ground layer (still background)
        cols = SCREEN_WIDTH // px + 3
        layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

        def make_tile(tile_id, tint_rgb, alpha):
            base = self.block_surfaces[tile_id]
            tile = pygame.transform.scale(base, (px, px)).convert_alpha()
            tint = pygame.Surface(tile.get_size(), pygame.SRCALPHA)
            tint.fill((*tint_rgb, 255))
            tile.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            tile.set_alpha(alpha)
            return tile

        rng = random.Random(4242)

        # A low, gentle ridgeline so it reads as foreground ground below mountains.
        base_y = int(SCREEN_HEIGHT * 0.88)
        amp = int(SCREEN_HEIGHT * 0.10)

        h = rng.randint(int(amp * 0.35), int(amp * 0.70))
        heights = []
        for _ in range(cols):
            h += rng.randint(-2, 2)
            h += int((amp * 0.55 - h) * 0.04)
            h = max(int(amp * 0.10), min(int(amp * 0.95), h))
            heights.append(h)

        # Light smoothing
        for _ in range(2):
            for i in range(1, len(heights) - 1):
                heights[i] = int((heights[i - 1] + heights[i] * 2 + heights[i + 1]) / 4)

        tile_cache = {tid: make_tile(tid, tint_rgb=(55, 58, 70), alpha=170) for tid in pool}

        # Clamp ridge so it never intrudes into emblem region.
        min_ridge_y = int(SCREEN_HEIGHT * 0.68)

        for i, mh in enumerate(heights):
            x = i * px
            ridge_y = base_y - mh + rng.randint(-px // 3, px // 3)
            y = max(min_ridge_y, ridge_y)
            # Fill down to bottom of screen.
            while y < SCREEN_HEIGHT:
                tid = rng.choice(pool)
                layer.blit(tile_cache[tid], (x, y))
                y += px

        return {"surface": layer, "parallax": 0.13}

    def _draw_ground_layer(self, camera_offset):
                layer = getattr(self, "_ground_layer", None)
                if not layer:
                    return
                surf = layer["surface"]
                par = layer["parallax"]
                # Non-wrapping ground: clamp so it does not tile infinitely.
                raw_ox = int(camera_offset.x * par)
                if surf.get_width() > SCREEN_WIDTH:
                    ox = max(0, min(raw_ox, surf.get_width() - SCREEN_WIDTH))
                else:
                    ox = 0
                oy = int(camera_offset.y * (par * 0.10))
                self.screen.blit(surf, (-ox, oy))

    def _draw_mountain_layers(self, camera_offset):
                layers = getattr(self, "_mountain_layers", None)
                if not layers:
                    return
                for layer in layers:
                    surf = layer["surface"]
                    par = layer["parallax"]
                    # Non-wrapping mountains: clamp so the mountain mass ends at the screen edges.
                    raw_ox = int(camera_offset.x * par)
                    if surf.get_width() > SCREEN_WIDTH:
                        ox = max(0, min(raw_ox, surf.get_width() - SCREEN_WIDTH))
                    else:
                        ox = 0
                    oy = int(camera_offset.y * (par * 0.15))
                    self.screen.blit(surf, (-ox, oy))




    def _draw_background_grid(self, camera_offset):
        grid_color = (20, 40, 70)
        for x in range(0, SCREEN_WIDTH, 40):
            offset_x = int(camera_offset.x * 0.02) % 40
            pygame.draw.line(self.screen, grid_color, (x + offset_x, 0), (x + offset_x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, 40):
            offset_y = int(camera_offset.y * 0.02) % 40
            pygame.draw.line(self.screen, grid_color, (0, y + offset_y), (SCREEN_WIDTH, y + offset_y), 1)

    def _draw_compass(self, angle):
        center_x = SCREEN_WIDTH // 2
        center_y = SCREEN_HEIGHT // 2
        pixel = 6
        compass = [
            "....XX....",
            "...XXXX...",
            "..XX..XX..",
            ".XX....XX.",
            "XX......XX",
            "..XX..XX..",
            "...XXXX...",
            "....XX....",
        ]
        surf = pygame.Surface((len(compass[0]) * pixel, len(compass) * pixel), pygame.SRCALPHA)
        for y, row in enumerate(compass):
            for x, cell in enumerate(row):
                if cell == "X":
                    rect = pygame.Rect(x * pixel, y * pixel, pixel, pixel)
                    pygame.draw.rect(surf, (40, 90, 140), rect)
        rotated = pygame.transform.rotozoom(surf, angle, 1.0)
        rect = rotated.get_rect(center=(center_x, center_y))
        self.screen.blit(rotated, rect.topleft)

    def draw_world(self, world, players, camera_offset, gravity_dir, rotation_deg, view_tiles_x, view_tiles_y):
        self.layer.fill((0, 0, 0, 0))
        start_tx = int(camera_offset.x // TILE_SIZE) - view_tiles_x // 2
        start_ty = int(camera_offset.y // TILE_SIZE) - view_tiles_y // 2

        # Champion marker (highest score; prefer living players).
        _living = [p for p in players if getattr(p, "hitpoints", 0) > 0 and not getattr(p, "waiting_for_boss_respawn", False)]
        _pool = _living if _living else list(players)
        champion_player = None
        if _pool:
            try:
                champion_player = sorted(_pool, key=lambda p: (-int(getattr(p, "score", 0)), str(getattr(p, "name", ""))))[0]
            except Exception:
                champion_player = None

        for tx in range(start_tx, start_tx + view_tiles_x):
            for ty in range(start_ty, start_ty + view_tiles_y):
                tile = world.get_tile(tx, ty)
                if tile == BLOCK_EMPTY:
                    continue
                world_x = tx * TILE_SIZE - camera_offset.x + SCREEN_WIDTH / 2
                world_y = ty * TILE_SIZE - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
                self.layer.blit(self.block_surfaces[tile], (world_x, world_y))

        for player in players:
            frame_to_draw = self._get_player_frame_for_draw(player)
            pos_x = player.pos.x - camera_offset.x + SCREEN_WIDTH / 2 - frame_to_draw.get_width() / 2
            pos_y = player.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y - frame_to_draw.get_height() / 2
            glow = self._get_glow_surface(frame_to_draw.get_size(), player.color, alpha=80, pad=10)
            self.layer.blit(glow, (pos_x - 5, pos_y - 5))
            if player.invuln > 0:
                blink = pygame.Surface(frame_to_draw.get_size(), pygame.SRCALPHA)
                blink.fill((255, 255, 255, 80))
                frame_to_draw = frame_to_draw.copy()
                frame_to_draw.blit(blink, (0, 0))
            if player.damage_flash > 0:
                flash = pygame.Surface(frame_to_draw.get_size(), pygame.SRCALPHA)
                pygame.draw.circle(
                    flash,
                    (255, 60, 60, 140),
                    (frame_to_draw.get_width() // 2, frame_to_draw.get_height() // 2),
                    frame_to_draw.get_width() // 2,
                )
                frame_to_draw = frame_to_draw.copy()
                frame_to_draw.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self.layer.blit(frame_to_draw, (pos_x, pos_y))
            if champion_player is player and getattr(player, "hitpoints", 0) > 0:
                cx = int(pos_x + frame_to_draw.get_width() / 2)
                top = int(pos_y - 10)
                pts = [(cx, top + 7), (cx - 6, top), (cx + 6, top)]
                pygame.draw.polygon(self.layer, (80, 255, 255, 220), pts)
            if player.attack_flash_timer > 0 and player.attack_flash_pos is not None:
                flash_pos = player.attack_flash_pos
                fx_x = flash_pos.x - camera_offset.x + SCREEN_WIDTH / 2
                fx_y = flash_pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
                radius = 8 + int(4 * (player.attack_flash_timer / (FPS // 6)))
                pygame.draw.circle(self.layer, (255, 180, 120, 160), (int(fx_x), int(fx_y)), radius)
            tag = self._get_name_surface(getattr(player, "display_name", player.name))
            self.layer.blit(tag, (pos_x - 4, pos_y - 14))

        draw_layer = self.layer
        if rotation_deg:
            draw_layer = pygame.transform.rotozoom(draw_layer, -rotation_deg, 1.0)
        rect = draw_layer.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 + self.camera_bias_y))
        self.screen.blit(draw_layer, rect.topleft)

    def draw_powerups(self, powerups, camera_offset):
        pixel = 3
        pattern = [
            "..X..",
            ".XXX.",
            "XXXXX",
            ".XXX.",
            "..X..",
        ]
        for orb in powerups:
            world_x = orb.pos.x - camera_offset.x + SCREEN_WIDTH / 2
            world_y = orb.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
            base_color = POWERUP_COLORS.get(orb.kind, (200, 255, 200))
            glow = self._get_powerup_glow(orb.kind)
            self.screen.blit(glow, (world_x - TILE_SIZE, world_y - TILE_SIZE))
            for y, row in enumerate(pattern):
                for x, cell in enumerate(row):
                    if cell != "X":
                        continue
                    rect = pygame.Rect(
                        world_x + (x - 2) * pixel,
                        world_y + (y - 2) * pixel,
                        pixel,
                        pixel,
                    )
                    pygame.draw.rect(self.screen, base_color, rect)

    def draw_boss(self, boss, camera_offset, gravity_dir):
        if not boss or not boss.alive:
            return
        target_size = int(boss.radius * 2.2)
        boss_surface = self._boss_surface_cache.get(target_size)
        if boss_surface is None:
            boss_surface = self.boss_blob if self.boss_blob.get_width() == target_size else pygame.transform.scale(self.boss_blob, (target_size, target_size))
            try:
                boss_surface = boss_surface.convert_alpha()
            except Exception:
                pass
            self._boss_surface_cache[target_size] = boss_surface
        glow = self._boss_glow_cache.get(target_size)
        if glow is None:
            glow = pygame.Surface((target_size + 12, target_size + 12), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (120, 200, 255, 140), glow.get_rect())
            self._boss_glow_cache[target_size] = glow
        screen_x = boss.pos.x - camera_offset.x + SCREEN_WIDTH / 2 - target_size / 2
        screen_y = boss.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y - target_size / 2
        self.screen.blit(glow, (screen_x - 6, screen_y - 6))
        self.screen.blit(boss_surface, (screen_x, screen_y))
        if boss.damage_flash > 0:
            flash = pygame.Surface((target_size, target_size), pygame.SRCALPHA)
            pygame.draw.circle(
                flash,
                (255, 60, 60, 140),
                (target_size // 2, target_size // 2),
                target_size // 2,
            )
            self.screen.blit(flash, (screen_x, screen_y), special_flags=pygame.BLEND_RGBA_ADD)
        label = self.hud_font.render(str(getattr(boss, "display_name", BOSS_NAME)).upper(), True, (255, 200, 255))
        self.screen.blit(label, (screen_x + 6, screen_y - 12))

    
    def draw_leader_pip(self, world, players, boss, status_messages, camera_offset):

        """Top-right respawn queue (dead players waiting for the boss to die).

        Only appears while at least one player is waiting to respawn.
        """
        if not players:
            return
        if not boss or not getattr(boss, "alive", False):
            return

        waiting = [p for p in players if getattr(p, "waiting_for_boss_respawn", False)]
        if not waiting:
            return

        # Oldest death on the right, extending left.
        waiting.sort(key=lambda p: getattr(p, "death_order", 10**9))

        icon_h = 34
        pad = 8
        step = icon_h + 6
        x_right = SCREEN_WIDTH - 14
        y_top = 14

        # Draw icons right-to-left.
        for i, p in enumerate(waiting):
            frames = self.player_frames.get(getattr(p, "skin_key", str(getattr(p, "name", "")).lower()), None)
            if not frames:
                continue
            surf = frames[0]
            try:
                sc = icon_h / float(max(1, surf.get_height()))
                tw = max(1, int(surf.get_width() * sc))
                icon = pygame.transform.scale(surf, (tw, icon_h)).convert_alpha()
            except Exception:
                icon = surf

            icon = icon.copy()
            fade = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
            fade.fill((200, 200, 210, 140))
            icon.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            x = x_right - i * step - icon.get_width()
            y = y_top
            # Stop if off-screen left.
            if x < 10:
                break

            bg = pygame.Surface((icon.get_width() + pad * 2, icon.get_height() + pad * 2), pygame.SRCALPHA)
            bg.fill((10, 15, 30, 90))
            pygame.draw.rect(bg, (80, 255, 255, 50), bg.get_rect(), 2, border_radius=10)
            self.screen.blit(bg, (x - pad, y - pad))
            self.screen.blit(icon, (x, y))

            # X marker
            mx = x + icon.get_width() // 2
            my = y + 6
            pygame.draw.line(self.screen, (255, 120, 140, 180), (mx - 6, my - 6), (mx + 6, my + 6), 2)
            pygame.draw.line(self.screen, (255, 120, 140, 180), (mx + 6, my - 6), (mx - 6, my + 6), 2)

        # Caption (only while someone is dead).
        caption = f"Waiting for {BOSS_NAME} to go down..."
        cap = self.font.render(caption, True, (210, 220, 240))
        # Fit under the icon bar width.
        max_w = min(SCREEN_WIDTH - 20, len(waiting) * step)
        if cap.get_width() > max_w:
            try:
                scale_w = max_w / float(max(1, cap.get_width()))
                nh = max(8, int(cap.get_height() * scale_w))
                cap = pygame.transform.scale(cap, (max_w, nh)).convert_alpha()
            except Exception:
                cap = self.font.render("Waiting for the next Boss...", True, (210, 220, 240))

        cap_x = max(10, x_right - max_w)
        cap_y = y_top + icon_h + 10
        cap2 = cap.copy()
        cap2.set_alpha(200)
        self.screen.blit(cap2, (cap_x, cap_y))

    def draw_hud(self, players, world, status_messages, boss, view_percent, show_settings):
        """Unified top-left UI (no bottom-left/right HUD)."""
        if not players:
            return

        focus = players[0]
        top_player = max(players, key=lambda p: getattr(p, "score", 0))
        cyan = (80, 255, 255)
        fg = (230, 230, 255)
        dim = (180, 190, 220)

        # Build line items (headers in cyan).
        items = []

        items.append(("SETTINGS", cyan, True))
        items.append(("O: OPEN SETTINGS" if not show_settings else "O: CLOSE SETTINGS", fg, False))
        items.append((None, None, False))

        gravity_label = "INVERTED" if getattr(world, "gravity_dir", 1) < 0 else "NORMAL"
        items.append(("GRAVITY", cyan, True))
        items.append((f"GRAVITY: {gravity_label}", fg, False))
        items.append((f"VIEW: {int(view_percent)}%", dim, False))
        items.append((None, None, False))

        items.append(("SCORES", cyan, True))
        items.append((f"YOU: {focus.name.upper()}  HP {focus.hitpoints}/{focus.max_hp}  SCORE {focus.score}", fg, False))
        items.append((f"TOP: {top_player.name.upper()}  SCORE {top_player.score}", fg, False))

        title_txt = getattr(focus, "personality_title", None)
        if title_txt and title_txt.lower() != "player":
            items.append((f"TITLE: {str(title_txt).upper()}", dim, False))

        if focus.powerup:
            items.append((None, None, False))
            items.append(("POWER", cyan, True))
            items.append((f"POWER: {focus.powerup.upper()}", fg, False))
            items.append(("RMB: CAST POWER", dim, False))

        if boss is not None and getattr(boss, "alive", False):
            items.append((None, None, False))
            items.append((str(getattr(boss, "display_name", BOSS_NAME)).upper(), cyan, True))
            items.append((f"HP: {int(getattr(boss, 'hp', 0))}", fg, False))

        # Activity feed (status messages).
        recent = []
        try:
            recent = [m[0] for m in (status_messages or [])][-5:]
        except Exception:
            recent = []
        if recent:
            items.append((None, None, False))
            items.append(("ACTIVITY", cyan, True))
            for msg in recent:
                items.append((str(msg), dim, False))

        # Render panel.
        font = self.hud_font
        pad = 8
        x0, y0 = 12, 12
        line_h = max(14, font.get_height() + 2)
        spacer_h = 5

        rendered = []
        max_w = 0
        total_h = pad * 2

        for text, color, is_header in items:
            if text is None:
                rendered.append((None, 0))
                total_h += spacer_h
                continue
            surf = font.render(text, True, color)
            rendered.append((surf, line_h))
            max_w = max(max_w, surf.get_width())
            total_h += line_h

        panel_w = max_w + pad * 2
        panel_h = total_h

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((10, 15, 30, 120))
        pygame.draw.rect(panel, (60, 90, 140, 170), panel.get_rect(), 2, border_radius=6)

        y = pad
        for surf, h in rendered:
            if surf is None:
                y += spacer_h
                continue
            panel.blit(surf, (pad, y))
            y += h

        self.screen.blit(panel, (x0, y0))

    def draw_settings_menu(self, master_volume, sfx_volume, fullscreen, selected_index):
        """Settings panel (volumes + maximize)."""
        cyan = (80, 255, 255)
        fg = (230, 230, 255)
        dim = (180, 190, 220)

        w, h = 520, 260
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 15, 30, 160))
        pygame.draw.rect(panel, (80, 140, 200, 170), panel.get_rect(), 2, border_radius=8)

        title = self.hud_font.render("SETTINGS", True, cyan)
        panel.blit(title, (16, 12))

        def pct(v):
            try:
                return int(round(float(v) * 100))
            except Exception:
                return 0

        rows = [
            ("MASTER VOLUME", f"{pct(master_volume):>3}%"),
            ("SFX VOLUME", f"{pct(sfx_volume):>3}%"),
            ("MAXIMIZED WINDOW", "ON" if fullscreen else "OFF"),
        ]

        y = 50
        for i, (label, value) in enumerate(rows):
            color = cyan if i == selected_index else fg
            line = self.hud_font.render(f"{label}: {value}", True, color)
            panel.blit(line, (16, y))
            y += 26

        help1 = self.font.render("UP/DOWN: SELECT   LEFT/RIGHT: ADJUST/TOGGLE", True, dim)
        help2 = self.font.render("O: CLOSE", True, dim)
        panel.blit(help1, (16, h - 44))
        panel.blit(help2, (16, h - 24))

        self.screen.blit(panel, (SCREEN_WIDTH // 2 - w // 2, SCREEN_HEIGHT // 2 - h // 2))

    def draw_projectiles(self, projectiles, camera_offset, gravity_dir):
        for projectile in projectiles:
            world_x = projectile.pos.x - camera_offset.x + SCREEN_WIDTH / 2
            world_y = projectile.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
            surface = self.block_surfaces.get(projectile.block_type)
            if surface:
                self.screen.blit(surface, (world_x - TILE_SIZE / 2, world_y - TILE_SIZE / 2))
            else:
                color = BLOCK_COLORS.get(projectile.block_type, (255, 255, 255, 200))
                pygame.draw.circle(self.screen, color, (int(world_x), int(world_y)), projectile.radius)

    def draw_power_projectiles(self, projectiles, camera_offset):
        for projectile in projectiles:
            world_x = projectile.pos.x - camera_offset.x + SCREEN_WIDTH / 2
            world_y = projectile.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
            color = POWERUP_COLORS.get(projectile.kind, (255, 255, 255))
            pygame.draw.circle(self.screen, color, (int(world_x), int(world_y)), projectile.radius)
            pygame.draw.circle(
                self.screen,
                (255, 255, 255),
                (int(world_x), int(world_y)),
                max(1, projectile.radius // 2),
                1,
            )

    def draw_meteorites(self, meteorites, camera_offset):
        # "Skystrike" destructive blocks (meteorites) with a nicer trail.
        trail_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for meteor in meteorites:
            world_x = meteor.pos.x - camera_offset.x + SCREEN_WIDTH / 2
            world_y = meteor.pos.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y

            # Trail
            if getattr(meteor, "trail", None):
                pts = meteor.trail[-22:]
                if len(pts) >= 2:
                    for i in range(1, len(pts)):
                        a = int(180 * (i / len(pts)))
                        p0 = pts[i - 1]
                        p1 = pts[i]
                        x0 = p0.x - camera_offset.x + SCREEN_WIDTH / 2
                        y0 = p0.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
                        x1 = p1.x - camera_offset.x + SCREEN_WIDTH / 2
                        y1 = p1.y - camera_offset.y + SCREEN_HEIGHT / 2 + self.camera_bias_y
                        pygame.draw.line(trail_surf, (255, 210, 140, a), (x0, y0), (x1, y1), 3)

            # Core block
            bt = getattr(meteor, "block_type", BLOCK_BROWN)
            col = BLOCK_COLORS.get(bt, (255, 140, 90, 255))
            rgb = (int(col[0]), int(col[1]), int(col[2]))
            size = TILE_SIZE
            rect = pygame.Rect(int(world_x - size // 2), int(world_y - size // 2), size, size)
            pygame.draw.rect(self.screen, rgb, rect)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 1)
            pygame.draw.circle(trail_surf, (255, 210, 140, 110), (int(world_x), int(world_y)), size)

        self.screen.blit(trail_surf, (0, 0))



class BlockProjectile:
    def __init__(self, pos, vel, block_type, hp, owner):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.block_type = block_type
        self.hp = hp
        self.radius = TILE_SIZE // 2
        self.owner = owner
        self.landed_tile = None

    def update(self, world, players, boss=None, camera=None):
        prev_pos = pygame.Vector2(self.pos)
        self.pos += self.vel
        if camera is not None:
            screen_x = self.pos.x - camera.x + SCREEN_WIDTH / 2
            screen_y = self.pos.y - camera.y + SCREEN_HEIGHT / 2 + CAMERA_SCREEN_BIAS_Y

            # Horizontal wrap: leaving left/right edge transfers to the opposite side.
            wrap_width = SCREEN_WIDTH + TILE_SIZE * 2
            if screen_x < -TILE_SIZE:
                self.pos.x += wrap_width
            elif screen_x > SCREEN_WIDTH + TILE_SIZE:
                self.pos.x -= wrap_width

            # Vertical bounds: keep existing behavior (respawn) to avoid losing projectiles forever.
            if screen_y < -TILE_SIZE or screen_y > SCREEN_HEIGHT + TILE_SIZE:
                self._respawn_projectile(camera)
                return True
        for player in players:
            if player is self.owner:
                continue
            player_rect = pygame.Rect(
                player.pos.x - player.radius,
                player.pos.y - player.radius,
                player.radius * 2,
                player.radius * 2,
            )
            proj_rect = pygame.Rect(
                self.pos.x - self.radius,
                self.pos.y - self.radius,
                self.radius * 2,
                self.radius * 2,
            )
            if proj_rect.colliderect(player_rect):
                damage = BLOCK_THROW_DAMAGE.get(self.block_type, 1)
                previous_hp = player.hitpoints
                killed = player.take_damage(damage, allow_kill=True)
                if player.hitpoints < previous_hp:
                    if self.owner:
                        self.owner.score += 1
                    player.apply_knockback(self.pos, 5.0, world)
                if killed and self.owner:
                    self.owner.score += 1
                    # PVP respawn rule: if a player kills a player, respawn after 3 seconds.
                    if isinstance(self.owner, Player):
                        player.pvp_respawn_timer = FPS * 3
                        player.pvp_pending_respawn = False
                        player.waiting_for_boss_respawn = False
                        player.death_order = None
                if player.hitpoints < previous_hp:
                    player.apply_projectile_effect(self.block_type, self.vel)
                landed = self._land_projectile(world, fallback_pos=prev_pos)
                if self.landed_tile:
                    player.projectile_ghost_timer = FPS // 6
                    player.ghosted_tile = self.landed_tile
                return landed
        if boss and boss.alive and boss is not self.owner:
            boss_rect = pygame.Rect(
                boss.pos.x - boss.radius,
                boss.pos.y - boss.radius,
                boss.radius * 2,
                boss.radius * 2,
            )
            proj_rect = pygame.Rect(
                self.pos.x - self.radius,
                self.pos.y - self.radius,
                self.radius * 2,
                self.radius * 2,
            )
            if proj_rect.colliderect(boss_rect):
                damage = BLOCK_THROW_DAMAGE.get(self.block_type, 1)
                boss.register_projectile_hit(self.owner)
                boss.take_damage(damage, self.owner)
                return self._land_projectile(world, fallback_pos=prev_pos)
        tx = int(self.pos.x // TILE_SIZE)
        ty = int(self.pos.y // TILE_SIZE)
        tile = world.get_tile(tx, ty)
        if tile != BLOCK_EMPTY:
            return self._land_projectile(world, fallback_pos=prev_pos)
        return True

    def _land_projectile(self, world, fallback_pos):
        positions = [
            self.pos,
            fallback_pos,
        ]
        for pos in positions:
            tx = int(pos.x // TILE_SIZE)
            ty = int(pos.y // TILE_SIZE)
            if world.get_tile(tx, ty) == BLOCK_EMPTY:
                world.set_tile(tx, ty, self.block_type, max(1, BLOCK_HP.get(self.block_type, 1)))
                self.landed_tile = (tx, ty)
                return False
        tx = int(self.pos.x // TILE_SIZE)
        ty = int(self.pos.y // TILE_SIZE)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                nx = tx + ox
                ny = ty + oy
                if world.get_tile(nx, ny) == BLOCK_EMPTY:
                    world.set_tile(nx, ny, self.block_type, max(1, BLOCK_HP.get(self.block_type, 1)))
                    self.landed_tile = (nx, ny)
                    return False
        self.pos = fallback_pos
        self.vel = pygame.Vector2(0, 0)
        return True

    def _respawn_projectile(self, camera):
        self.pos.x = camera.x + random.randint(-SCREEN_WIDTH // 2, SCREEN_WIDTH // 2)
        self.pos.y = camera.y + random.randint(-SCREEN_HEIGHT // 2, SCREEN_HEIGHT // 2)


class PowerProjectile:
    def __init__(self, owner, target, kind):
        self.owner = owner
        self.target = target
        self.kind = kind
        self.pos = pygame.Vector2(owner.pos)
        self.vel = pygame.Vector2(0, 0)
        self.radius = 6
        self.lifetime = POWER_SHOT_LIFETIME

    def _select_target(self, players):
        candidates = [p for p in players if p is not self.owner and p.hitpoints > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda p: (p.pos - self.pos).length_squared())

    def update(self, world, players, game=None):
        self.lifetime -= 1
        if self.lifetime <= 0:
            return False
        if not self.target or self.target.hitpoints <= 0:
            self.target = self._select_target(players)
        if self.target:
            direction = self.target.pos - self.pos
            if direction.length_squared() > 0:
                desired = direction.normalize() * POWER_SHOT_SPEED
            else:
                desired = pygame.Vector2(self.owner.facing, 0) * POWER_SHOT_SPEED
        else:
            desired = pygame.Vector2(self.owner.facing, 0) * POWER_SHOT_SPEED
        self.vel = self.vel.lerp(desired, POWER_SHOT_TURN_RATE)
        self.pos += self.vel

        for player in players:
            if player is self.owner or player.hitpoints <= 0:
                continue
            if (player.pos - self.pos).length() < player.radius + self.radius:
                self.apply_hit(player, world, players, game)
                return False
        return True

    def apply_hit(self, player, world, players, game):
        damage = max(1, min(POWER_DAMAGE.get(self.kind, 1), PLAYER_MAX_HP - 1))
        previous_hp = player.hitpoints
        killed = player.take_damage(damage, allow_kill=True)
        if player.hitpoints < previous_hp and self.owner:
            self.owner.score += 1
        if killed and self.owner:
            self.owner.score += 1
        if player.hitpoints == previous_hp:
            return
        player.apply_knockback(self.pos, 3.5, world)

        if self.kind == "heal":
            if self.owner:
                self.owner.hitpoints = min(self.owner.max_hp, self.owner.hitpoints + 1)
            player.slow_timer = max(player.slow_timer, SLOW_DURATION // 3)
        elif self.kind == "vital":
            player.poison_timer = max(player.poison_timer, POISON_DURATION // 2)
            player.poison_tick_timer = POISON_TICK
        elif self.kind == "dash":
            knockback = (player.pos - self.pos).normalize() if (player.pos - self.pos).length_squared() > 0 else pygame.Vector2(1, 0)
            player.vel += knockback * (BOUNCE_FORCE * 0.8)
        elif self.kind == "shield":
            player.freeze_timer = max(player.freeze_timer, FREEZE_DURATION // 3)
        elif self.kind == "frenzy":
            player.burn_timer = max(player.burn_timer, BURN_DURATION // 2)
            player.burn_tick_timer = BURN_TICK
            player.slow_timer = max(player.slow_timer, SLOW_DURATION // 3)
            if game:
                game.frenzy_timer = FPS * 6
                game.add_status_message("FRENZY MODE!")
        elif self.kind == "grow":
            player.slow_timer = max(player.slow_timer, SLOW_DURATION)
        elif self.kind == "haste":
            player.slow_timer = max(player.slow_timer, SLOW_DURATION)
        elif self.kind == "fury":
            player.burn_timer = max(player.burn_timer, BURN_DURATION // 2)
            player.burn_tick_timer = BURN_TICK
        elif self.kind == "bomb":
            center_tx = int(self.pos.x // TILE_SIZE)
            center_ty = int(self.pos.y // TILE_SIZE)
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    if ox * ox + oy * oy <= 9:
                        world.damage_tile(center_tx + ox, center_ty + oy, 3)
            for other in players:
                if other is self.owner:
                    continue
                if (other.pos - self.pos).length() < TILE_SIZE * 3:
                    other.take_damage(1, allow_kill=False)
        elif self.kind == "rush":
            player.slow_timer = max(player.slow_timer, SLOW_DURATION // 2)
        elif self.kind == "rapid":
            player.freeze_timer = max(player.freeze_timer, FREEZE_DURATION // 4)
        elif self.kind == "cleave":
            knockback = (player.pos - self.pos).normalize() if (player.pos - self.pos).length_squared() > 0 else pygame.Vector2(1, 0)
            player.vel += knockback * (BOUNCE_FORCE * 1.1)
        elif self.kind == "pulse":
            player.slow_timer = max(player.slow_timer, SLOW_DURATION // 2)
        elif self.kind == "lunge":
            knockback = (player.pos - self.pos).normalize() if (player.pos - self.pos).length_squared() > 0 else pygame.Vector2(1, 0)
            player.vel += knockback * (BOUNCE_FORCE * 0.9)
        elif self.kind == "shock":
            player.freeze_timer = max(player.freeze_timer, FREEZE_DURATION // 5)
            player.slow_timer = max(player.slow_timer, SLOW_DURATION // 2)
        elif self.kind == "snare":
            player.slow_timer = max(player.slow_timer, int(SLOW_DURATION * 1.2))
        elif self.kind == "blast":
            for other in players:
                if (other.pos - self.pos).length() < TILE_SIZE * 3:
                    other.take_damage(1, allow_kill=False)
                    other.apply_knockback(self.pos, 4.5, world)


class Meteorite:
    def __init__(self, pos, velocity, block_type):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(velocity)
        self.radius = 10
        self.alive = True
        self.block_type = block_type
        self.trail = []

    def update(self, world):
        # record trail
        self.trail.append(self.pos.copy())
        if len(self.trail) > 22:
            self.trail.pop(0)

        self.pos += self.vel
        tx = int(self.pos.x // TILE_SIZE)
        ty = int(self.pos.y // TILE_SIZE)
        if world.get_tile(tx, ty) != BLOCK_EMPTY:
            return False
        if self.pos.y > (WORLD_TOP_Y + CHUNK_SIZE) * TILE_SIZE:
            return False
        return True

class PowerupOrb:
    def __init__(self, pos, kind):
        self.pos = pygame.Vector2(pos)
        self.kind = kind
        self.vel = pygame.Vector2(0, POWERUP_FALL_SPEED)
        self.landed = False
        self.despawn_timer = POWERUP_DESPAWN_TIME

    def update(self, world):
        if not self.landed:
            self.pos.y += self.vel.y * world.gravity_dir
            tx = int(self.pos.x // TILE_SIZE)
            ty = int(self.pos.y // TILE_SIZE)
            if world.gravity_dir > 0:
                landing_y = (ty + 1) * TILE_SIZE - TILE_SIZE / 2
                if world.get_tile(tx, ty + 1) != BLOCK_EMPTY and self.pos.y >= landing_y:
                    self.pos.y = landing_y
                    self.landed = True
                    self.vel.y = 0
            else:
                landing_y = ty * TILE_SIZE + TILE_SIZE / 2
                if world.get_tile(tx, ty - 1) != BLOCK_EMPTY and self.pos.y <= landing_y:
                    self.pos.y = landing_y
                    self.landed = True
                    self.vel.y = 0
        else:
            self.despawn_timer -= 1
            if self.despawn_timer <= 0:
                return False
        return True

class Boss:
    def __init__(self, spawn_tile):
        self.pos = pygame.Vector2(spawn_tile[0] * TILE_SIZE, spawn_tile[1] * TILE_SIZE)
        self.vel = pygame.Vector2(0, 0)
        self.radius = 24
        self.hp = 30
        self.alive = True
        self.attack_cooldown = 0
        self.jump_cooldown = 0
        self.just_killed_by = None
        self.projectile_hits = {}
        self.carried_blocks = []
        self.pickup_cooldown = 0
        self.throw_cooldown = FPS // 2
        self.damage_flash = 0
        self.special_cooldown = FPS * 4
        self.display_name = BOSS_NAME

    def update(self, players, world):
        if not self.alive:
            return []
        new_projectiles = []
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.jump_cooldown > 0:
            self.jump_cooldown -= 1
        if self.pickup_cooldown > 0:
            self.pickup_cooldown -= 1
        if self.throw_cooldown > 0:
            self.throw_cooldown -= 1
        if self.damage_flash > 0:
            self.damage_flash -= 1
        if self.special_cooldown > 0:
            self.special_cooldown -= 1
        target = min(players, key=lambda p: (p.pos - self.pos).length_squared())
        direction = (target.pos - self.pos)
        if direction.length_squared() > 1:
            direction = direction.normalize()
        self.vel.x = direction.x * 2.0
        self.vel.y += GRAVITY_STRENGTH * 1.4 * world.gravity_dir
        self.vel.y = max(min(self.vel.y, 10), -10)
        if self.jump_cooldown <= 0 and abs(direction.y) > 0.5:
            self.vel.y = -12.0 * world.gravity_dir
            self.jump_cooldown = FPS

        self.pos.x += self.vel.x
        self.move_with_collisions(world, axis=0, amount=self.vel.x)
        self.pos.y += self.vel.y
        self.move_with_collisions(world, axis=1, amount=self.vel.y)
        self.dig_blocks(world, direction)
        if (target.pos - self.pos).length() < self.radius + 10 and self.attack_cooldown <= 0:
            if target.take_damage(2):
                pass
            target.apply_knockback(self.pos, 5.5, world)
            self.damage_nearby_blocks(world)
            self.attack_cooldown = FPS // 2

        if len(self.carried_blocks) < 3 and self.pickup_cooldown <= 0:
            self.pick_up_blocks(world)
            self.pickup_cooldown = FPS // 4
        if len(self.carried_blocks) >= 3 and self.throw_cooldown <= 0:
            new_projectiles = self.throw_blocks(target)
            self.throw_cooldown = FPS
        if self.special_cooldown <= 0 and (target.pos - self.pos).length() < 180:
            self.perform_special(players, world)
            self.special_cooldown = FPS * 5
        return new_projectiles

    def perform_special(self, players, world):
        center = pygame.Vector2(self.pos)
        for player in players:
            if player.hitpoints <= 0:
                continue
            if (player.pos - center).length() < TILE_SIZE * 6:
                player.take_damage(1, allow_kill=False)
                player.apply_knockback(center, 6.0, world)
        center_tx = int(self.pos.x // TILE_SIZE)
        center_ty = int(self.pos.y // TILE_SIZE)
        for ox in range(-2, 3):
            for oy in range(-2, 3):
                if ox * ox + oy * oy <= 4:
                    world.set_tile(center_tx + ox, center_ty + oy, BLOCK_EMPTY, 0)

    def pick_up_blocks(self, world):
        base_tx = int(self.pos.x // TILE_SIZE)
        base_ty = int(self.pos.y // TILE_SIZE)
        for oy in range(-1, 2):
            for ox in range(-1, 2):
                if len(self.carried_blocks) >= 3:
                    return
                tx = base_tx + ox
                ty = base_ty + oy
                tile = world.get_tile(tx, ty)
                if tile not in (BLOCK_EMPTY, BLOCK_BLACK):
                    self.carried_blocks.append(tile)
                    world.set_tile(tx, ty, BLOCK_EMPTY, 0)

    def throw_blocks(self, target):
        projectiles = []
        direction = (target.pos - self.pos)
        if direction.length_squared() == 0:
            direction = pygame.Vector2(1, 0)
        base_dir = direction.normalize()
        spread = [-12, 0, 12]
        for angle in spread:
            if not self.carried_blocks:
                break
            block_type = self.carried_blocks.pop(0)
            velocity = base_dir.rotate(angle) * BOSS_THROW_SPEED
            projectiles.append(
                BlockProjectile(
                    pygame.Vector2(self.pos),
                    velocity,
                    block_type,
                    max(1, BLOCK_HP.get(block_type, 1)),
                    self,
                )
            )
        return projectiles

    def dig_blocks(self, world, direction):
        base_tx = int(self.pos.x // TILE_SIZE)
        base_ty = int(self.pos.y // TILE_SIZE)
        offsets = [
            (int(direction.x), int(direction.y)),
            (int(direction.x), 0),
            (0, int(direction.y)),
            (0, 0),
        ]
        for ox, oy in offsets:
            world.damage_tile(base_tx + ox, base_ty + oy, 2)

    def damage_nearby_blocks(self, world):
        base_tx = int(self.pos.x // TILE_SIZE)
        base_ty = int(self.pos.y // TILE_SIZE)
        for ox, oy in [(0, 0), (1, 0), (0, 1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)]:
            world.damage_tile(base_tx + ox, base_ty + oy, 2)

    def resolve_collisions(self, world, axis=0):
        rect = pygame.Rect(self.pos.x - self.radius, self.pos.y - self.radius, self.radius * 2, self.radius * 2)
        min_tx = int(rect.left // TILE_SIZE) - 1
        max_tx = int(rect.right // TILE_SIZE) + 1
        min_ty = int(rect.top // TILE_SIZE) - 1
        max_ty = int(rect.bottom // TILE_SIZE) + 1
        for tx in range(min_tx, max_tx + 1):
            for ty in range(min_ty, max_ty + 1):
                if world.get_tile(tx, ty) == BLOCK_EMPTY:
                    continue
                tile_rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                if rect.colliderect(tile_rect):
                    if axis == 0:
                        if self.vel.x > 0:
                            rect.right = tile_rect.left
                        elif self.vel.x < 0:
                            rect.left = tile_rect.right
                        self.pos.x = rect.centerx
                        self.vel.x = 0
                    else:
                        if self.vel.y * world.gravity_dir > 0:
                            rect.bottom = tile_rect.top
                        elif self.vel.y * world.gravity_dir < 0:
                            rect.top = tile_rect.bottom
                        self.pos.y = rect.centery
                        self.vel.y = 0

    def move_with_collisions(self, world, axis, amount):
        step = TILE_SIZE / 2
        remaining = amount
        while abs(remaining) > 0:
            move = max(-step, min(step, remaining))
            if axis == 0:
                self.pos.x += move
            else:
                self.pos.y += move
            self.resolve_collisions(world, axis=axis)
            remaining -= move

    def take_damage(self, amount, attacker):
        if not self.alive:
            return False
        self.hp -= amount
        self.damage_flash = FPS // 8
        if self.hp <= 0:
            self.alive = False
            # attacker may be None for environmental kills (e.g., skystrikes).
            self.just_killed_by = attacker
            if attacker is not None:
                attacker.score += 10
                attacker.is_boss = True
                attacker.update_size()
                attacker.max_hp = max(attacker.max_hp, BOSS_PLAYER_HP)
                attacker.hitpoints = attacker.max_hp
            return True
        return False

    def register_projectile_hit(self, attacker):
        """Track projectile hits per attacker; on enough hits, the boss is executed."""
        if attacker is None:
            return
        self.projectile_hits[attacker] = self.projectile_hits.get(attacker, 0) + 1
        if self.projectile_hits[attacker] >= 4:
            # Execute the boss (counts as the attacker killing it).
            self.take_damage(self.hp, attacker)



class Game:
    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        pygame.display.set_caption("Neon Arena: Gravity Flip")

        # Fixed virtual resolution (authoritative game space).
        # The OS window is RESIZABLE; we scale/blit this 1920x1080 surface each frame using
        # aspect-preserving letterbox/pillarbox so resizing never changes world scale/zoom.
        info = pygame.display.Info()
        desk_w = int(getattr(info, "current_w", SCREEN_WIDTH))
        desk_h = int(getattr(info, "current_h", SCREEN_HEIGHT))

        # Start "fullscreen-looking" but still windowed with borders/titlebar:
        # - Prefer SDL2 maximize if available.
        # - Otherwise start near the desktop size and let the user maximize normally.
        self.windowed_size = (SCREEN_WIDTH, SCREEN_HEIGHT)
        # Presentation backend:
        # Prefer SDL renderer scaling (pygame.SCALED) for performance at large window sizes.
        # If unavailable or it fails to initialize, we fall back to manual CPU scaling.
        self._use_scaled_present = bool(getattr(pygame, "SCALED", 0))
        self._last_known_window_size = self.windowed_size
        self._startup_fallback_size = (max(640, desk_w - 16), max(360, desk_h - 16))

        self.window_maximized = False
        self.quit_overlay = False

        self._apply_display_mode()
        if self._maximize_window():
            self.window_maximized = True
            try:
                sw, sh = self._get_actual_window_size()
                self._last_known_window_size = (int(sw), int(sh))
                self._set_screen_metrics(int(sw), int(sh))
            except Exception:
                pass
        else:
            # SDL2 maximize unavailable; use a near-desktop initial size.
            self.windowed_size = self._startup_fallback_size
            self._apply_display_mode()

        self.clock = pygame.time.Clock()
        self.world = World(seed=random.randint(0, 99999))
        self.renderer = Renderer(self.screen)

        self.remote_players = int(os.getenv("REMOTE_PLAYERS", "0"))
        self.remote_server = None
        if self.remote_players > 0:
            self.remote_server = RemoteInputServer()
            self.remote_server.start()

        self.players = self._create_players()
        self.death_seq = 0
        self.boss = None
        self.boss_spawn_timer = BOSS_DROP_DELAY
        self.projectiles = []
        self.power_projectiles = []
        self.meteorites = []
        self.powerup_orbs = []
        self.powerup_timer = POWERUP_DROP_INTERVAL
        self.frenzy_timer = 0

        self.camera = pygame.Vector2(self.players[0].pos)

        self._fixed_camera = pygame.Vector2(self.camera)
        self.running = True
        self.status_messages = []

        self.master_volume = 1.0
        self.sfx_volume = 1.0
        self.show_settings = False
        self.settings_index = 0
        self._sfx_base_volumes = {}
        self.sfx = self._create_sfx()
        self._apply_audio_volumes()

        self.meteor_timer = METEOR_INTERVAL

        self.show_help = False
        self.view_index = 1

        self._playstyle_elapsed = 0.0
        self._playstyle_assigned = False
        self._playstyle_stats = {"move": 0, "jump": 0, "attack": 0, "dash": 0, "shock": 0, "build": 0, "deaths": 0}

    def _safe_set_mode(self, size, flags):
        """Create the display surface with best-effort vsync.

        Some pygame builds don't support the `vsync` kwarg; never crash if it's unavailable.
        """
        w, h = int(size[0]), int(size[1])
        try:
            return pygame.display.set_mode((w, h), flags, vsync=1)
        except TypeError:
            return pygame.display.set_mode((w, h), flags)
        except pygame.error:
            return pygame.display.set_mode((w, h), flags)

    def _get_actual_window_size(self):
        """Best-effort actual OS window size (not the logical surface size).

        In pygame.SCALED mode, the display Surface size stays at the logical size (1920x1080),
        while the actual window can be larger. We need the real window size for correct mouse mapping.
        """
        # Newer pygame:
        try:
            if hasattr(pygame.display, "get_window_size"):
                w, h = pygame.display.get_window_size()
                if w and h:
                    return int(w), int(h)
        except Exception:
            pass

        # SDL2 window wrapper:
        try:
            from pygame._sdl2 import Window  # type: ignore
            w, h = Window.from_display_module().size
            if w and h:
                return int(w), int(h)
        except Exception:
            pass

        # Last known size from resize events (works even without SDL2 helpers):
        try:
            w, h = getattr(self, "_last_known_window_size", (SCREEN_WIDTH, SCREEN_HEIGHT))
            return int(w), int(h)
        except Exception:
            return SCREEN_WIDTH, SCREEN_HEIGHT

    def _maximize_window(self) -> bool:
        """Maximize the OS window while keeping borders/titlebar (best-effort)."""
        try:
            from pygame._sdl2 import Window  # type: ignore
            Window.from_display_module().maximize()
            pygame.event.pump()
            return True
        except Exception:
            return False

    def toggle_maximize(self):
        """Toggle maximize/restore for the decorated window (best-effort)."""
        if getattr(self, "window_maximized", False):
            self.window_maximized = False
            self.windowed_size = getattr(self, "_restore_windowed_size", (SCREEN_WIDTH, SCREEN_HEIGHT))
            self._apply_display_mode()
            self.add_status_message("WINDOW RESTORED")
            return

        try:
            self._restore_windowed_size = self.window.get_size()
        except Exception:
            self._restore_windowed_size = getattr(self, "windowed_size", (SCREEN_WIDTH, SCREEN_HEIGHT))

        if self._maximize_window():
            self.window_maximized = True
            self.add_status_message("WINDOW MAXIMIZED")
        else:
            # SDL2 maximize not available: keep current window; user can use the OS maximize button.
            self.window_maximized = False
            self.add_status_message("USE OS MAXIMIZE BUTTON")

    def _set_screen_metrics(self, w: int, h: int):
        """Update *window* size globals used for scaling/mouse mapping.
        The game logic/world rendering stays at the fixed virtual resolution (SCREEN_WIDTH/SCREEN_HEIGHT).
        """
        global WINDOW_WIDTH, WINDOW_HEIGHT
        WINDOW_WIDTH = max(320, int(w))
        WINDOW_HEIGHT = max(240, int(h))
        _recalc_view_tiles()
        self._recalc_scale()

    def _recalc_scale(self):
        """Compute how the fixed virtual surface maps into the resizable window."""
        # Use letterboxing to preserve aspect ratio and prevent the world from expanding.
        ww, wh = int(WINDOW_WIDTH), int(WINDOW_HEIGHT)
        if ww <= 0 or wh <= 0:
            ww, wh = SCREEN_WIDTH, SCREEN_HEIGHT

        sx = ww / float(SCREEN_WIDTH)
        sy = wh / float(SCREEN_HEIGHT)
        scale = min(sx, sy)

        # Avoid zero-size blits
        dw = max(1, int(SCREEN_WIDTH * scale))
        dh = max(1, int(SCREEN_HEIGHT * scale))
        ox = (ww - dw) // 2
        oy = (wh - dh) // 2

        self._blit_scale = scale
        self._blit_offset = (ox, oy)
        self._blit_size = (dw, dh)
        self._blit_rect = pygame.Rect(ox, oy, dw, dh)

    def window_to_screen(self, pos):
        """Map window pixel coordinates -> virtual screen coordinates (SCREEN_WIDTH/SCREEN_HEIGHT).
        Returns None if outside the letterboxed game area.
        """
        if pos is None:
            return None
        x, y = int(pos[0]), int(pos[1])
        # If we are using pygame.SCALED, SDL may already be providing *logical* (virtual)
        # coordinates for mouse events (i.e., already in 0..SCREEN_WIDTH/HEIGHT).
        # In that case, we must NOT apply our manual window->virtual transform again,
        # or aiming will be distorted (everything points roughly the same direction).
        if getattr(self, "_use_scaled_present", False) and self.screen is self.window:
            if 0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT:
                return (x, y)
        if not hasattr(self, '_blit_rect'):
            self._recalc_scale()
        if not self._blit_rect.collidepoint(x, y):
            return None
        ox, oy = self._blit_offset
        scale = self._blit_scale if getattr(self, '_blit_scale', 0) else 1.0
        sx = (x - ox) / scale
        sy = (y - oy) / scale
        # Clamp to the virtual surface bounds.
        sx_i = max(0, min(SCREEN_WIDTH - 1, int(sx)))
        sy_i = max(0, min(SCREEN_HEIGHT - 1, int(sy)))
        return (sx_i, sy_i)


    def _apply_display_mode(self):
        # IMPORTANT:
        # - The game renders to a fixed virtual resolution (SCREEN_WIDTH/SCREEN_HEIGHT).
        # - The OS window can be any size; resizing must NOT change world scale/zoom.
        #
        # For performance at large window sizes, prefer pygame.SCALED (SDL renderer scaling).
        # If that isn't available, fall back to manual CPU scaling in _present().
        if getattr(self, "_use_scaled_present", False):
            flags = pygame.RESIZABLE | int(getattr(pygame, "SCALED", 0)) | int(getattr(pygame, "DOUBLEBUF", 0))
            try:
                # In SCALED mode, the display surface IS the fixed logical (virtual) surface.
                self.window = self._safe_set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
                self.screen = self.window
                ww, wh = self._get_actual_window_size()
                self._set_screen_metrics(ww, wh)
                return
            except Exception:
                # If SCALED fails on this platform/build, revert to manual scaling.
                self._use_scaled_present = False

        # Manual scaling fallback: create a real resizable window surface, render into a fixed 1920x1080 Surface,
        # then scale/blit it each frame using letterbox/pillarbox.
        w, h = getattr(self, "windowed_size", (SCREEN_WIDTH, SCREEN_HEIGHT))
        flags = pygame.RESIZABLE | int(getattr(pygame, "DOUBLEBUF", 0))
        self.window = self._safe_set_mode((int(w), int(h)), flags)

        # Create/keep the fixed virtual render surface.
        if not hasattr(self, "screen") or self.screen is None or self.screen.get_size() != (SCREEN_WIDTH, SCREEN_HEIGHT):
            self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()

        # Update window metrics + scaling rect.
        sw, sh = self.window.get_size()
        self._set_screen_metrics(sw, sh)


    def _present(self):
        """Present the current frame.

        - If pygame.SCALED is active, SDL handles scaling/letterboxing efficiently; we only flip.
        - Otherwise we do manual letterbox scaling from the fixed 1920x1080 surface to the resizable window.
        """
        if not hasattr(self, 'window') or self.window is None:
            pygame.display.flip()
            return

        # Fast, GPU-friendly path (when available):
        if getattr(self, "_use_scaled_present", False):
            ww, wh = self._get_actual_window_size()
            if getattr(self, '_last_win_size', None) != (ww, wh):
                self._last_win_size = (ww, wh)
                self._set_screen_metrics(ww, wh)
            pygame.display.flip()
            return

        # Manual CPU scaling fallback:
        ww, wh = self.window.get_size()
        if getattr(self, '_last_win_size', None) != (ww, wh):
            self._last_win_size = (ww, wh)
            self._set_screen_metrics(ww, wh)

        if not hasattr(self, '_blit_size'):
            self._recalc_scale()

        # Letterbox fill
        self.window.fill((0, 0, 0))

        dw, dh = self._blit_size
        if dw <= 0 or dh <= 0:
            pygame.display.flip()
            return

        # Fast path: no scaling needed (exact match)
        if (dw, dh) == self.screen.get_size() and getattr(self, '_blit_offset', (0, 0)) == (0, 0):
            self.window.blit(self.screen, (0, 0))
            pygame.display.flip()
            return

        # Cache scaled surface when window size is stable
        cache_key = (dw, dh)
        if getattr(self, '_scaled_cache_key', None) != cache_key:
            self._scaled_cache_key = cache_key
            # Keep SRCALPHA; some UI layers rely on it (we still clear the window to black each frame).
            self._scaled_cache_surf = pygame.Surface(cache_key, pygame.SRCALPHA)

        # Scale into cached surface (fast scale; smoothscale is much heavier)
        try:
            pygame.transform.scale(self.screen, cache_key, self._scaled_cache_surf)
        except TypeError:
            # Older pygame builds don't accept a destination surface.
            self._scaled_cache_surf = pygame.transform.scale(self.screen, cache_key)

        self.window.blit(self._scaled_cache_surf, self._blit_offset)
        pygame.display.flip()


    def _create_players(self):
        offsets = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25]
        roster = list(CHATBOT_ROSTER)
        # Keep the local player stable and rotate the AI roster for variety.
        leader = roster[0]
        ai_roster = roster[1:]
        random.shuffle(ai_roster)
        roster = [leader] + ai_roster

        personalities = [
            {"name": "architect", "title": "architect", "aggression": 0.28, "wander": 0.26, "space": TILE_SIZE * 3.2, "power_use": 0.08, "defense": 0.92, "build_bias": 0.16, "dig_bias": 0.08},
            {"name": "debugger", "title": "debugger", "aggression": 0.60, "wander": 0.35, "space": TILE_SIZE * 2.5, "power_use": 0.11, "defense": 0.86, "build_bias": 0.12, "dig_bias": 0.12},
            {"name": "optimizer", "title": "optimizer", "aggression": 0.52, "wander": 0.20, "space": TILE_SIZE * 2.4, "power_use": 0.12, "defense": 0.90, "build_bias": 0.10, "dig_bias": 0.10},
            {"name": "teacher", "title": "teacher", "aggression": 0.42, "wander": 0.42, "space": TILE_SIZE * 2.9, "power_use": 0.10, "defense": 0.78, "build_bias": 0.14, "dig_bias": 0.10},
            {"name": "planner", "title": "planner", "aggression": 0.46, "wander": 0.25, "space": TILE_SIZE * 3.0, "power_use": 0.13, "defense": 0.88, "build_bias": 0.16, "dig_bias": 0.08},
            {"name": "researcher", "title": "researcher", "aggression": 0.64, "wander": 0.58, "space": TILE_SIZE * 2.3, "power_use": 0.16, "defense": 0.72, "build_bias": 0.12, "dig_bias": 0.15},
            {"name": "developer", "title": "developer", "aggression": 0.72, "wander": 0.48, "space": TILE_SIZE * 2.1, "power_use": 0.13, "defense": 0.68, "build_bias": 0.18, "dig_bias": 0.18},
            {"name": "artist", "title": "artist", "aggression": 0.55, "wander": 0.62, "space": TILE_SIZE * 2.6, "power_use": 0.14, "defense": 0.74, "build_bias": 0.16, "dig_bias": 0.12},
            {"name": "prototype", "title": "prototype", "aggression": 0.58, "wander": 0.55, "space": TILE_SIZE * 2.5, "power_use": 0.12, "defense": 0.76, "build_bias": 0.18, "dig_bias": 0.16},
            {"name": "music bot", "title": "music bot", "aggression": 0.44, "wander": 0.72, "space": TILE_SIZE * 2.8, "power_use": 0.10, "defense": 0.70, "build_bias": 0.12, "dig_bias": 0.10},
            {"name": "strategist", "title": "strategist", "aggression": 0.66, "wander": 0.24, "space": TILE_SIZE * 2.2, "power_use": 0.15, "defense": 0.88, "build_bias": 0.12, "dig_bias": 0.12},
            {"name": "story bot", "title": "story bot", "aggression": 0.50, "wander": 0.60, "space": TILE_SIZE * 2.7, "power_use": 0.11, "defense": 0.80, "build_bias": 0.12, "dig_bias": 0.10},
        ]

        controls = {
            "left": pygame.K_a,
            "right": pygame.K_d,
            "jump": pygame.K_SPACE,
            "jump_alt": pygame.K_w,
            "attack": pygame.K_f,
            "dash": pygame.K_LSHIFT,
            "shockwave": pygame.K_e,
        }

        personality_pool = list(personalities)
        random.shuffle(personality_pool)

        players = []
        for i in range(12):
            spawn_tx = offsets[i]
            spawn_ty = self.world.find_surface_y(spawn_tx)
            position = (spawn_tx * TILE_SIZE, spawn_ty * TILE_SIZE)
            name, color, skin_key = roster[i]
            if i == 0:
                p0 = Player(name, color, position, controls=controls)
                p0.personality_title = "player"
                p0.skin_key = skin_key
                p0.display_name = name
                players.append(p0)
            else:
                player = Player(name, color, position, ai=True)
                player.skin_key = skin_key
                player.display_name = name
                if not personality_pool:
                    personality_pool = list(personalities)
                    random.shuffle(personality_pool)
                profile = personality_pool.pop()
                player.set_personality(profile)
                player.personality_title = profile.get("title", profile.get("name", "neutral"))
                if i <= self.remote_players:
                    player.ai = False
                    player.remote_id = i
                players.append(player)
        return players


    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue

            # Window resize: always keep the game in the fixed virtual resolution.
            if event.type == pygame.VIDEORESIZE:
                new_size = (max(320, int(event.w)), max(240, int(event.h)))
                self.windowed_size = new_size
                self._last_known_window_size = new_size
                if getattr(self, "_use_scaled_present", False):
                    # SCALED mode adjusts automatically; we only update mouse-mapping metrics.
                    self._set_screen_metrics(new_size[0], new_size[1])
                else:
                    # Manual mode needs a real window surface at the new size.
                    self._apply_display_mode()
                continue

            # Some platforms emit WINDOWEVENT resize notifications.
            if hasattr(pygame, "WINDOWEVENT") and event.type == pygame.WINDOWEVENT:
                resized_evt = getattr(pygame, "WINDOWEVENT_SIZE_CHANGED", None)
                resized_evt2 = getattr(pygame, "WINDOWEVENT_RESIZED", None)
                if event.event in (resized_evt, resized_evt2):
                    w = int(getattr(event, "data1", SCREEN_WIDTH))
                    h = int(getattr(event, "data2", SCREEN_HEIGHT))
                    new_size = (max(320, w), max(240, h))
                    self.windowed_size = new_size
                    self._last_known_window_size = new_size
                    if getattr(self, "_use_scaled_present", False):
                        self._set_screen_metrics(new_size[0], new_size[1])
                    else:
                        self._apply_display_mode()
                    continue

            if event.type == pygame.KEYDOWN:
                # Quit confirmation modal has priority and pauses simulation.
                if getattr(self, "quit_overlay", False):
                    if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.running = False
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        self.quit_overlay = False
                    continue

                # First ESC opens quit confirmation.
                if event.key == pygame.K_ESCAPE:
                    self.quit_overlay = True
                    continue

                # Settings menu toggle
                if event.key == pygame.K_o:
                    self.show_settings = not self.show_settings
                    continue

                # Settings controls (while open)
                if self.show_settings:
                    if event.key == pygame.K_UP:
                        self.settings_index = max(0, self.settings_index - 1)
                    elif event.key == pygame.K_DOWN:
                        self.settings_index = min(2, self.settings_index + 1)
                    elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        if self.settings_index == 0:
                            delta = -0.05 if event.key == pygame.K_LEFT else 0.05
                            self.master_volume = max(0.0, min(1.0, self.master_volume + delta))
                            self._apply_audio_volumes()
                            self.add_status_message(f"MASTER VOLUME {int(self.master_volume * 100)}%")
                        elif self.settings_index == 1:
                            delta = -0.05 if event.key == pygame.K_LEFT else 0.05
                            self.sfx_volume = max(0.0, min(1.0, self.sfx_volume + delta))
                            self._apply_audio_volumes()
                            self.add_status_message(f"SFX VOLUME {int(self.sfx_volume * 100)}%")
                        else:
                            self.toggle_maximize()
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self.settings_index == 2:
                            self.toggle_maximize()
                    continue

                # Help + view controls
                if event.key == pygame.K_h:
                    self.show_help = not self.show_help
                elif event.key == pygame.K_z:
                    self.view_index = (self.view_index + 1) % len(VIEW_SCALES)
                    self.add_status_message(f"VIEW DISTANCE {int(VIEW_SCALES[self.view_index] * 100)}%")

            # Ignore gameplay mouse input while settings or quit modal is open.
            if self.show_settings or getattr(self, "quit_overlay", False):
                continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Map click position from window space -> virtual game space (ignore black bars).
                    sp = self.window_to_screen(getattr(event, "pos", None))
                    if sp is None:
                        continue

                    player = self.players[0]
                    if player.carried_block is not None:
                        player.throw_intent = True
                        player.throw_dir = self.screen_to_world_dir(sp, player.pos)
                        self.play_sfx("throw")
                    else:
                        nearest = self.find_nearest_block(player.pos, search_radius=4)
                        if nearest:
                            player.pickup_target = nearest
                            player.pickup_intent = True
                            self.play_sfx("pickup")
                if event.button == 3:
                    sp = self.window_to_screen(getattr(event, "pos", None))
                    if sp is None:
                        continue
                    player = self.players[0]
                    if player.powerup:
                        target = self.find_player_near_screen(sp, exclude=player)
                        if target:
                            player.power_intent = True
                            player.power_target = target

    def find_nearest_block(self, pos, search_radius=4):
        center_tx = int(pos.x // TILE_SIZE)
        center_ty = int(pos.y // TILE_SIZE)
        best = None
        best_dist = None
        for ox in range(-search_radius, search_radius + 1):
            for oy in range(-search_radius, search_radius + 1):
                tx = center_tx + ox
                ty = center_ty + oy
                tile = self.world.get_tile(tx, ty)
                if tile == BLOCK_EMPTY or tile == BLOCK_BLACK:
                    continue
                dx = ox * TILE_SIZE
                dy = oy * TILE_SIZE
                dist = dx * dx + dy * dy
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = (tx, ty)
        return best

    def screen_to_world(self, pos):
        mouse_x, mouse_y = pos
        world_x = self.camera.x + (mouse_x - SCREEN_WIDTH / 2)
        world_y = self.camera.y + (mouse_y - (SCREEN_HEIGHT / 2 + CAMERA_SCREEN_BIAS_Y))
        return pygame.Vector2(world_x, world_y)

    def find_player_near_screen(self, pos, exclude=None, max_distance=TILE_SIZE * 6):
        world_pos = self.screen_to_world(pos)
        candidates = [p for p in self.players if p is not exclude and p.hitpoints > 0]
        if not candidates:
            return None
        nearest = min(candidates, key=lambda p: (p.pos - world_pos).length_squared())
        if (nearest.pos - world_pos).length() <= max_distance:
            return nearest
        return None

    def apply_remote_input(self, player):
        if not self.remote_server or player.remote_id is None:
            return
        payload = self.remote_server.get_input(player.remote_id)
        if not payload:
            return
        left = bool(payload.get("left"))
        right = bool(payload.get("right"))
        player.move_intent = (1 if right else 0) - (1 if left else 0)
        player.jump_intent = bool(payload.get("jump"))
        player.attack_intent = bool(payload.get("attack"))
        player.dash_intent = bool(payload.get("dash"))
        player.shockwave_intent = bool(payload.get("shockwave"))
        player.pickup_intent = bool(payload.get("pickup"))
        if payload.get("throw"):
            player.throw_intent = True
        if payload.get("power") and player.powerup:
            opponents = [p for p in self.players if p is not player and p.hitpoints > 0]
            if opponents:
                player.power_intent = True
                player.power_target = min(opponents, key=lambda p: (p.pos - player.pos).length_squared())
        aim = payload.get("aim")
        if isinstance(aim, (list, tuple)) and len(aim) == 2:
            direction = pygame.Vector2(aim[0], aim[1])
            if direction.length_squared() > 0:
                player.throw_dir = direction.normalize()

    def screen_to_tile(self, pos):
        mouse_x, mouse_y = pos
        world_x = self.camera.x + (mouse_x - SCREEN_WIDTH / 2)
        world_y = self.camera.y + (mouse_y - (SCREEN_HEIGHT / 2 + CAMERA_SCREEN_BIAS_Y))
        return int(world_x // TILE_SIZE), int(world_y // TILE_SIZE)

    def screen_to_world_dir(self, pos, origin):
        mouse_x, mouse_y = pos
        world_x = self.camera.x + (mouse_x - SCREEN_WIDTH / 2)
        world_y = self.camera.y + (mouse_y - (SCREEN_HEIGHT / 2 + CAMERA_SCREEN_BIAS_Y))
        direction = pygame.Vector2(world_x, world_y) - origin
        if direction.length_squared() == 0:
            return pygame.Vector2(1, 0)
        return direction.normalize()

    def update_camera(self):
        # Camera is fixed: keep the viewport centered on the initial anchor.
        if not hasattr(self, "_fixed_camera"):
            self._fixed_camera = pygame.Vector2(self.camera)
        self.camera.x = float(self._fixed_camera.x)
        self.camera.y = float(self._fixed_camera.y)




    def wrap_world_x(self, world_x: float) -> float:
        """Horizontal screen-wrap for world-space X based on the current camera viewport."""
        screen_x = world_x - self.camera.x + SCREEN_WIDTH / 2
        wrap_width = SCREEN_WIDTH + TILE_SIZE * 2
        if screen_x < -TILE_SIZE:
            return world_x + wrap_width
        if screen_x > SCREEN_WIDTH + TILE_SIZE:
            return world_x - wrap_width
        return world_x

    def wrap_entities_horizontal(self):
        """Wrap players and moving entities horizontally when they leave the screen."""
        for p in self.players:
            p.pos.x = self.wrap_world_x(p.pos.x)

        for proj in self.projectiles:
            proj.pos.x = self.wrap_world_x(proj.pos.x)

        for proj in self.power_projectiles:
            proj.pos.x = self.wrap_world_x(proj.pos.x)

        for meteor in self.meteorites:
            meteor.pos.x = self.wrap_world_x(meteor.pos.x)

        for orb in self.powerup_orbs:
            orb.pos.x = self.wrap_world_x(orb.pos.x)


    def get_view_tiles(self):
        scale = VIEW_SCALES[self.view_index]
        view_x = max(8, int(VIEW_TILES_X * scale))
        view_y = max(8, int(VIEW_TILES_Y * scale))
        return view_x, view_y

    def spawn_boss(self):
        spawn_x = int(self.camera.x // TILE_SIZE)
        spawn_ty = self.world.find_surface_y(spawn_x)
        spawn_y = (spawn_ty - 8) * TILE_SIZE
        self.boss = Boss((spawn_x, spawn_ty - 8))
        self.boss.pos.y = spawn_y
        self.add_status_message(f"{BOSS_NAME.upper()} DROPPING IN!")

    def resolve_player_collisions(self):
        for i, player in enumerate(self.players):
            for other in self.players[i + 1 :]:
                if player.hitpoints <= 0 or other.hitpoints <= 0:
                    continue
                delta = player.pos - other.pos
                distance = delta.length()
                min_distance = player.radius + other.radius - PLAYER_SOFT_COLLISION
                if distance == 0:
                    delta = pygame.Vector2(random.choice([-1, 1]), 0)
                    distance = 1
                if distance < min_distance:
                    push = (min_distance - distance) / 2
                    direction = delta.normalize()
                    player.pos += direction * push
                    other.pos -= direction * push

    def cast_power(self, player):
        if not player.powerup:
            return
        target = player.power_target
        if not target or target.hitpoints <= 0:
            opponents = [p for p in self.players if p is not player and p.hitpoints > 0]
            if not opponents:
                return
            target = min(opponents, key=lambda p: (p.pos - player.pos).length_squared())
        self.power_projectiles.append(PowerProjectile(player, target, player.powerup))
        self.add_status_message(f"{player.name.upper()} CAST {player.powerup.upper()}")
        player.powerup = None
        player.power_intent = False
        player.power_target = None

    def spawn_meteorite(self):
        view_tiles_x, _ = self.get_view_tiles()
        start_x = self.camera.x + random.randint(-view_tiles_x, view_tiles_x) * TILE_SIZE
        start_y = self.camera.y - SCREEN_HEIGHT * 2.5

        # Diagonal entries only (never straight down).
        if random.random() < 0.5:
            angle = random.uniform(35, 70)   # down-right
        else:
            angle = random.uniform(110, 145) # down-left

        velocity = pygame.Vector2(1, 0).rotate(angle) * METEOR_SPEED

        # "Destructive block" look: pick an existing solid block type.
        block_type = random.choice([k for k in BLOCK_COLORS.keys() if k != BLOCK_EMPTY])
        self.meteorites.append(Meteorite((start_x, start_y), velocity, block_type))

    def handle_meteorite_impact(self, meteor):
        center_tx = int(meteor.pos.x // TILE_SIZE)
        center_ty = int(meteor.pos.y // TILE_SIZE)

        # Destroy at least 10 nearest blocks in a circular area around impact.
        search_r = 6
        candidates = []
        for ox in range(-search_r, search_r + 1):
            for oy in range(-search_r, search_r + 1):
                d2 = ox * ox + oy * oy
                if d2 <= search_r * search_r:
                    tx = center_tx + ox
                    ty = center_ty + oy
                    bt = self.world.get_tile(tx, ty)
                    if bt != BLOCK_EMPTY:
                        candidates.append((d2, tx, ty))

        candidates.sort(key=lambda t: t[0])
        destroyed = 0
        for _, tx, ty in candidates:
            self.world.set_tile(tx, ty, BLOCK_EMPTY, 0)
            destroyed += 1
            if destroyed >= 10:
                break

        # Always carve a small crater even if few blocks exist.
        crater_r = 3
        for ox in range(-crater_r, crater_r + 1):
            for oy in range(-crater_r, crater_r + 1):
                if ox * ox + oy * oy <= crater_r * crater_r:
                    self.world.set_tile(center_tx + ox, center_ty + oy, BLOCK_EMPTY, 0)

        # Lethal blast to players and boss within radius.
        blast_radius = METEOR_DAMAGE_RADIUS
        for player in self.players:
            if (player.pos - meteor.pos).length() < blast_radius:
                player.take_damage(999, allow_kill=True)
                player.apply_knockback(meteor.pos, 9.0, self.world)

        if self.boss and getattr(self.boss, "alive", False):
            if (self.boss.pos - meteor.pos).length() < blast_radius + self.boss.radius:
                self.boss.take_damage(999, None)

        self.add_status_message("SKYSTRIKE IMPACT!")
        self.play_sfx("skystrike")


    def update_powerups(self):
        for orb in list(self.powerup_orbs):
            if not orb.update(self.world):
                self.powerup_orbs.remove(orb)
                continue
            for player in self.players:
                if (player.pos - orb.pos).length() < player.radius + TILE_SIZE * 0.6:
                    player.apply_powerup(orb.kind, self.world)
                    self.add_status_message(f"{player.name.upper()} GOT {orb.kind.upper()}")
                    self.play_sfx("powerup")
                    self.powerup_orbs.remove(orb)
                    break

        self.powerup_timer -= 1
        if self.powerup_timer <= 0:
            self.spawn_powerup_orb()
            self.powerup_timer = POWERUP_DROP_INTERVAL

    def spawn_powerup_orb(self):
        kind = random.choices(list(POWERUP_WEIGHTS.keys()), weights=list(POWERUP_WEIGHTS.values()), k=1)[0]
        view_x, _ = self.get_view_tiles()
        spawn_x = self.camera.x + random.randint(-view_x // 2, view_x // 2) * TILE_SIZE
        spawn_y = (WORLD_TOP_Y - 6) * TILE_SIZE
        self.powerup_orbs.append(PowerupOrb((spawn_x, spawn_y), kind))

    def update_blocks(self):
        return

    def damage_players_from_block(self, tx, ty):
        tile_rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        for player in self.players:
            player_rect = pygame.Rect(
                player.pos.x - player.radius,
                player.pos.y - player.radius,
                player.radius * 2,
                player.radius * 2,
            )
            if player_rect.colliderect(tile_rect):
                if player.take_damage(FALLING_BLOCK_DAMAGE):
                    self.respawn_player(player)

    def handle_death(self, player):
                # PVP deaths respawn after a short delay, even during boss fights.
                if getattr(player, "pvp_respawn_timer", 0) > 0:
                    player.pvp_respawn_timer -= 1
                    # Keep them out of the world while waiting.
                    player.vel = pygame.Vector2(0, 0)
                    player.pos = pygame.Vector2(-99999, -99999)
                    return
                if getattr(player, "pvp_pending_respawn", False):
                    player.pvp_pending_respawn = False
                    self.respawn_player(player)
                    return
        
                # Avoid repeated processing while already waiting.
                if getattr(player, "waiting_for_boss_respawn", False):
                    return
        
                if self.boss is not None and getattr(self.boss, "alive", False):
                    player.waiting_for_boss_respawn = True
                    # Assign a stable queue order for the respawn bar.
                    if getattr(player, 'death_order', None) is None:
                        player.death_order = self.death_seq
                        self.death_seq += 1
                    player.vel = pygame.Vector2(0, 0)
                    # Park them far away so they don't interact while waiting.
                    player.pos = pygame.Vector2(-99999, -99999)
                    self.add_status_message(f"{player.name.upper()} DOWN (WAITING FOR BOSS)")
                    return
        
                # No active boss: respawn immediately.
                self.respawn_player(player)

    def respawn_waiting_players(self):
        # Respawn everyone waiting in the death queue by dropping them from above the screen.
        waiting = [p for p in self.players if getattr(p, "waiting_for_boss_respawn", False)]
        if not waiting:
            return

        # Oldest death first.
        waiting.sort(key=lambda p: getattr(p, "death_order", 10**9))

        # Visible world-space horizontal span.
        left_world = self.camera.x - SCREEN_WIDTH / 2 + 90
        right_world = self.camera.x + SCREEN_WIDTH / 2 - 90
        span = max(1.0, right_world - left_world)

        n = len(waiting)
        if n == 1:
            xs = [self.camera.x]
        else:
            step = span / float(n - 1)
            xs = [left_world + i * step for i in range(n)]
            random.shuffle(xs)

        # Start above the top of the screen so they fall into view.
        start_y = self.camera.y - SCREEN_HEIGHT / 2 - 180

        for p, xw in zip(waiting, xs):
            p.waiting_for_boss_respawn = False
            p.death_order = None

            p.pos = pygame.Vector2(float(xw), float(start_y) - random.randint(0, 80))
            p.vel = pygame.Vector2(0, 0)

            p.max_hp = PLAYER_MAX_HP
            p.hitpoints = PLAYER_MAX_HP

            # Immune until first landing.
            p.respawn_timer = 0
            p.invuln = 0
            p.invuln_until_landed = True

            p.jump_count = 0
            p.jump_multiplier = 1.0
            p.size_scale = 1.0

    def reset_game(self):
        # Preserve settings while resetting gameplay state.
        self.world = World(seed=random.randint(0, 99999))
        self.players = self._create_players()
        self.boss = None
        self.death_seq = 0
        for p in self.players:
            if hasattr(p, 'death_order'):
                p.death_order = None
        self.boss_spawn_timer = BOSS_DROP_DELAY
        self.projectiles = []
        self.power_projectiles = []
        self.meteorites = []
        self.powerup_orbs = []
        self.powerup_timer = POWERUP_DROP_INTERVAL
        self.frenzy_timer = 0
        self.camera = pygame.Vector2(self.players[0].pos)
        self.status_messages = []
        self.show_help = False
        self.show_settings = False
        self.settings_index = 0
        self.add_status_message("RESET!")
    def respawn_player(self, player, forced_tx=None):
        main_tx = int(self.players[0].pos.x // TILE_SIZE)
        respawn_tx = main_tx if forced_tx is None else int(forced_tx)
        if forced_tx is None:
            for _ in range(10):
                candidate = int(self.camera.x // TILE_SIZE) + random.randint(-14, 14)
                if abs(candidate - main_tx) > 6:
                    respawn_tx = candidate
                    break
            else:
                respawn_tx = main_tx + random.choice([-10, 10])
        surface_ty = self.world.find_surface_y(respawn_tx)
        respawn_ty = surface_ty - random.randint(RESPAWN_HEIGHT_RANGE[0] + 3, RESPAWN_HEIGHT_RANGE[1] + 6)
        player.pos = pygame.Vector2(respawn_tx * TILE_SIZE, respawn_ty * TILE_SIZE)
        player.vel = pygame.Vector2(0, 0)
        player.max_hp = PLAYER_MAX_HP
        player.hitpoints = PLAYER_MAX_HP
        player.respawn_timer = RESPAWN_INVULN_TIME
        player.invuln = RESPAWN_INVULN_TIME
        player.jump_count = 0
        player.jump_multiplier = 1.0
        player.size_scale = 1.0
        player.speed_multiplier = 1.0
        player.strength_multiplier = 1.0
        player.attack_range_bonus = 0
        player.attack_cooldown_multiplier = 1.0
        player.rapid_timer = 0
        player.cleave_timer = 0
        player.pulse_timer = 0
        player.lunge_timer = 0
        player.attack_flash_timer = 0
        player.attack_flash_pos = None
        player.projectile_ghost_timer = 0
        player.ghosted_tile = None
        player.radius = player.base_radius
        player.freeze_timer = 0
        player.burn_timer = 0
        player.poison_timer = 0
        player.damage_flash = 0
        player.slow_timer = 0
        player.powerup = None
        player.power_intent = False
        player.power_target = None
        if player.is_boss:
            player.is_boss = False
            self.boss = Boss((respawn_tx, respawn_ty))
            self.add_status_message(f"{player.name.upper()} LOST {BOSS_NAME.upper()}")

    def enforce_minimap_bounds(self, player):
        return

    def update_threats(self):
        """Compute a short 'threat window' for each AI player."""
        if not self.players:
            return

        for player in self.players:
            if not getattr(player, "ai", False) or getattr(player, "hitpoints", 0) <= 0:
                continue

            threat = 0

            for proj in self.projectiles:
                owner = getattr(proj, "owner", None)
                if owner is player:
                    continue
                d = player.pos - proj.pos
                if d.length_squared() < (220 * 220) and getattr(proj, "vel", pygame.Vector2(0, 0)).length_squared() > 0 and d.length_squared() > 0:
                    v = proj.vel.normalize()
                    dn = d.normalize()
                    if v.dot(dn) > 0.55:
                        threat = max(threat, FPS // 6)

            for proj in self.power_projectiles:
                owner = getattr(proj, "owner", None)
                if owner is player:
                    continue
                d = player.pos - proj.pos
                if d.length_squared() < (240 * 240) and getattr(proj, "vel", pygame.Vector2(0, 0)).length_squared() > 0 and d.length_squared() > 0:
                    v = proj.vel.normalize()
                    dn = d.normalize()
                    if v.dot(dn) > 0.50:
                        threat = max(threat, FPS // 6)

            for other in self.players:
                if other is player or getattr(other, "hitpoints", 0) <= 0:
                    continue
                if getattr(other, "attack_flash_timer", 0) > 0 and getattr(other, "attack_flash_pos", None) is not None:
                    if (player.pos - other.attack_flash_pos).length() < 64:
                        threat = max(threat, FPS // 5)
                if getattr(other, "attack_intent", False) and (player.pos - other.pos).length() < 110:
                    threat = max(threat, FPS // 8)

            player.threat_timer = max(getattr(player, "threat_timer", 0), threat)


    def game_loop(self):
        while self.running:
            self.clock.tick(FPS)
            dt = self.clock.get_time() / 1000.0 if self.clock.get_time() else (1.0 / FPS)

            self.handle_events()

            paused = bool(getattr(self, "quit_overlay", False))

            if not paused:
                keys = pygame.key.get_pressed()
                p0 = self.players[0]
                p0.read_input(keys)

                # Simple cosmetic playstyle labeling after 5 minutes (does not affect gameplay).
                self._playstyle_elapsed += dt
                if p0.move_intent != 0:
                    self._playstyle_stats["move"] += 1

                if self.frenzy_timer > 0:
                    self.frenzy_timer -= 1

                self.update_threats()

                for player in self.players:
                    self.apply_remote_input(player)

                    if player.hitpoints <= 0:
                        self.handle_death(player)
                        continue

                    player.update(
                        self.world,
                        self.players,
                        boss=self.boss,
                        powerups=self.powerup_orbs,
                        frenzy_active=self.frenzy_timer > 0,
                    )

                    if player is p0:
                        if player.jumped_this_frame:
                            self._playstyle_stats["jump"] += 1
                        if player.attack_flash_timer == FPS // 6:
                            self._playstyle_stats["attack"] += 1
                        if player.dash_timer == DASH_DURATION:
                            self._playstyle_stats["dash"] += 1
                        if player.shockwave_timer == SHOCKWAVE_COOLDOWN:
                            self._playstyle_stats["shock"] += 1

                    if player.jumped_this_frame:
                        self.play_sfx("jump")

                    if player.hitpoints <= 0:
                        self.handle_death(player)
                        continue

                    self.enforce_minimap_bounds(player)

                    if player.throw_intent:
                        projectile = player.try_throw()
                        if projectile:
                            self.projectiles.append(projectile)
                        player.throw_intent = False

                    if player.powerup and not player.power_intent:
                        opponents = [p for p in self.players if p is not player and p.hitpoints > 0]
                        if opponents:
                            player.power_intent = True
                            player.power_target = min(opponents, key=lambda p: (p.pos - player.pos).length_squared())

                    if player.power_intent:
                        self.cast_power(player)

                # Assign label once after 5 minutes.
                if (not self._playstyle_assigned) and self._playstyle_elapsed >= 300.0:
                    s = self._playstyle_stats
                    secs = max(1.0, self._playstyle_elapsed)
                    move_rate = s["move"] / (secs * FPS)
                    attacks = s["attack"] / secs
                    dashes = s["dash"] / secs
                    builds = s["build"] / secs
                    label = "casual"
                    if builds >= 2.0:
                        label = "builder"
                    elif dashes >= 1.2 and move_rate >= 0.45:
                        label = "hyperactive"
                    elif attacks >= 3.0:
                        label = "tryhard"
                    elif attacks < 1.2 and move_rate < 0.20:
                        label = "lazy"
                    p0.playstyle_label = label
                    self._playstyle_assigned = True

                if self.boss is not None and getattr(self.boss, "alive", False):
                    if all(p.hitpoints <= 0 for p in self.players):
                        self.reset_game()
                        continue

                self.resolve_player_collisions()

                if self.boss is None:
                    if self.boss_spawn_timer > 0:
                        self.boss_spawn_timer -= 1
                    if self.boss_spawn_timer == 0:
                        self.spawn_boss()

                if self.boss and self.boss.alive:
                    boss_projectiles = self.boss.update(self.players, self.world)
                    if boss_projectiles:
                        self.projectiles.extend(boss_projectiles)

                active_projectiles = []
                for projectile in self.projectiles:
                    if projectile.update(self.world, self.players, boss=self.boss, camera=self.camera):
                        active_projectiles.append(projectile)
                self.projectiles = active_projectiles

                active_power_projectiles = []
                for projectile in self.power_projectiles:
                    if projectile.update(self.world, self.players, game=self):
                        active_power_projectiles.append(projectile)
                self.power_projectiles = active_power_projectiles

                self.meteor_timer -= 1
                if self.meteor_timer <= 0:
                    self.spawn_meteorite()
                    self.meteor_timer = METEOR_INTERVAL

                active_meteorites = []
                for meteor in self.meteorites:
                    if meteor.update(self.world):
                        active_meteorites.append(meteor)
                    else:
                        self.handle_meteorite_impact(meteor)
                self.meteorites = active_meteorites

                self.update_blocks()
                self.update_powerups()

                if self.boss and self.boss.just_killed_by:
                    self.add_status_message(f"{self.boss.just_killed_by.name.upper()} BECAME {BOSS_NAME.upper()}")
                    self.play_sfx("powerup")
                    self.boss.just_killed_by = None

                if self.boss is not None and not getattr(self.boss, "alive", True):
                    self.respawn_waiting_players()
                    self.boss = None
                    self.boss_spawn_timer = BOSS_DROP_DELAY

                self.update_status_messages()
                self.update_camera()
                self.wrap_entities_horizontal()

            view_tiles_x, view_tiles_y = self.get_view_tiles()

            self.renderer.draw_background(self.camera, self.world.gravity_dir, self.world.rotation_deg)
            self.renderer.draw_champion_emblem(self.boss, self.players)
            self.renderer.draw_world(
                self.world,
                self.players,
                self.camera,
                self.world.gravity_dir,
                self.world.rotation_deg,
                view_tiles_x,
                view_tiles_y,
            )
            self.renderer.draw_projectiles(self.projectiles, self.camera, self.world.gravity_dir)
            self.renderer.draw_power_projectiles(self.power_projectiles, self.camera)
            self.renderer.draw_meteorites(self.meteorites, self.camera)
            self.renderer.draw_powerups(self.powerup_orbs, self.camera)
            self.renderer.draw_boss(self.boss, self.camera, self.world.gravity_dir)
            self.renderer.draw_leader_pip(self.world, self.players, self.boss, self.status_messages, self.camera)
            self.renderer.draw_hud(
                self.players,
                self.world,
                self.status_messages,
                self.boss,
                int(VIEW_SCALES[self.view_index] * 100),
                self.show_settings,
            )
            if self.show_settings:
                self.renderer.draw_settings_menu(self.master_volume, self.sfx_volume, self.window_maximized, self.settings_index)
            if self.show_help:
                self.draw_help_overlay()

            if paused:
                self.draw_quit_overlay()

            self._present()


        pygame.quit()


    def _create_sfx(self):
        if not pygame.mixer.get_init():
            return {}
        return {
            "jump": self._tone(220, 0.05, 0.2),
            "throw": self._tone(140, 0.05, 0.2),
            "pickup": self._tone(260, 0.03, 0.15),
            "powerup": self._tone(320, 0.08, 0.2),
            "skystrike": self._tone(70, 0.20, 0.45),
        }

    def _tone(self, frequency, duration, volume):
        sample_rate = 22050
        length = int(sample_rate * duration)
        buf = bytearray()
        period = int(sample_rate / frequency)
        for i in range(length):
            value = 127 if (i // (period // 2 + 1)) % 2 == 0 else -128
            buf.extend(int(value).to_bytes(1, byteorder="little", signed=True))
        sound = pygame.mixer.Sound(buffer=bytes(buf))
        base = float(volume)
        # pygame.mixer.Sound does not reliably allow custom attributes across builds;
        # track base volume separately.
        try:
            self._sfx_base_volumes[id(sound)] = base
        except Exception:
            pass
        sound.set_volume(base)
        return sound
    def _apply_audio_volumes(self):
        if not pygame.mixer.get_init():
            return
        master = max(0.0, min(1.0, float(getattr(self, "master_volume", 1.0))))
        sfx = max(0.0, min(1.0, float(getattr(self, "sfx_volume", 1.0))))
        for snd in getattr(self, "sfx", {}).values():
            try:
                base = float(getattr(self, "_sfx_base_volumes", {}).get(id(snd), snd.get_volume()))
                snd.set_volume(max(0.0, min(1.0, base * master * sfx)))
            except Exception:
                pass
    def play_sfx(
self, key):
        sound = self.sfx.get(key)
        if sound:
            sound.play()

    def add_status_message(self, text, duration=FPS * 3):
        self.status_messages.append([text, duration])

    def update_status_messages(self):
        for message in self.status_messages:
            message[1] -= 1
        self.status_messages = [m for m in self.status_messages if m[1] > 0]

    def draw_status_messages(self):
        x = SCREEN_WIDTH - 360
        y = SCREEN_HEIGHT - 120
        for idx, (text, _) in enumerate(self.status_messages[-4:]):
            surf = self.renderer.hud_font.render(text, True, (200, 200, 255))
            self.screen.blit(surf, (x, y + idx * 18))

    def draw_help_overlay(self):
        panel_w = 560
        panel_h = 420
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((10, 15, 30, 210))
        pygame.draw.rect(panel, (60, 90, 140), panel.get_rect(), 2)

        lines = [
            "CONTROLS",
            "A/D: MOVE    SPACE/W: JUMP",
            "SHIFT: DASH",
            "F: ATTACK    E: BOSS POWER",
            "LMB: PICKUP/THROW   RMB: CAST POWER",
            "H: TOGGLE HELP      Z: VIEW DISTANCE",
        ]
        y = 12
        for idx, line in enumerate(lines):
            color = (200, 220, 255) if idx == 0 else (190, 200, 220)
            surf = self.renderer.hud_font.render(line, True, color)
            panel.blit(surf, (12, y))
            y += 26

        y += 6
        pygame.draw.line(panel, (70, 110, 170), (12, y), (panel_w - 12, y), 2)
        y += 12

        title = self.renderer.hud_font.render("LEADERBOARD", True, (220, 235, 255))
        panel.blit(title, (12, y))
        y += 26

        players_sorted = sorted(self.players, key=lambda p: (-getattr(p, "score", 0), p.name))
        col_w = (panel_w - 36) // 2
        x_cols = [12, 12 + col_w + 12]
        row_h = 34
        font_main = self.renderer.hud_font
        font_sub = getattr(self.renderer, "hud_small_font", self.renderer.font)

        split = (len(players_sorted) + 1) // 2
        for i, p in enumerate(players_sorted):
            col = 0 if i < split else 1
            row = i if col == 0 else i - split
            x = x_cols[col]
            yy = y + row * row_h

            rank = i + 1
            name = p.name.upper()
            score = getattr(p, "score", 0)
            title_txt = getattr(p, "personality_title", "neutral")

            line1 = f"{rank:>2}. {name:<10}  {score:>3}"
            line2 = f"    {title_txt}"

            surf1 = font_main.render(line1, True, (230, 230, 255))
            surf2 = font_sub.render(line2, True, (170, 190, 220))

            panel.blit(surf1, (x, yy))
            panel.blit(surf2, (x, yy + 18))

        self.screen.blit(panel, (20, 20))


    def draw_quit_overlay(self):
        """Modal quit confirmation overlay (simulation is paused while visible)."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))

        box_w, box_h = 720, 220
        x = SCREEN_WIDTH // 2 - box_w // 2
        y = SCREEN_HEIGHT // 2 - box_h // 2
        box = pygame.Rect(x, y, box_w, box_h)

        pygame.draw.rect(overlay, (10, 15, 30, 230), box, border_radius=14)
        pygame.draw.rect(overlay, (80, 255, 255, 180), box, 2, border_radius=14)

        title = self.renderer.hud_font.render("QUIT?", True, (230, 240, 255))
        msg = self.renderer.hud_font.render("Y / ENTER = YES     N / ESC = NO", True, (190, 210, 235))
        hint = self.renderer.font.render("Gameplay paused while this prompt is open.", True, (160, 180, 210))

        overlay.blit(title, (box.centerx - title.get_width() // 2, box.y + 42))
        overlay.blit(msg, (box.centerx - msg.get_width() // 2, box.y + 92))
        overlay.blit(hint, (box.centerx - hint.get_width() // 2, box.y + 140))

        self.screen.blit(overlay, (0, 0))


def main():
    install_crash_reporter()
    game = Game()
    game.game_loop()


if __name__ == "__main__":
    main()
