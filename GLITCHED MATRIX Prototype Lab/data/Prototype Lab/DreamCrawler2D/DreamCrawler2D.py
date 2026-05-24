# Dream Crawler v7 (co-op perception crawler)
import os
import math
import random
import traceback
import datetime
from heapq import heappush, heappop


def _ensure(p):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        pass


_ensure("logs")
_ensure(os.path.join("assets", "sfx"))
_ensure(os.path.join("assets", "music"))


def _crash(exc: BaseException):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = os.path.join("logs", f"crash_{ts}.txt")
    try:
        with open(fn, "w", encoding="utf-8") as f:
            f.write("Dream Crawler crash report\n")
            f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass
    return fn


try:
    import pygame
except Exception as e:
    _crash(e)
    raise

AUDIO_OK = False
try:
    pygame.init()
    try:
        pygame.mixer.init()
        AUDIO_OK = True
    except Exception:
        AUDIO_OK = False
except Exception as e:
    _crash(e)
    raise


def _load_any(path_no_ext: str):
    if not AUDIO_OK:
        return None
    for ext in (".wav", ".ogg", ".mp3"):
        p = path_no_ext + ext
        if os.path.isfile(p):
            try:
                return pygame.mixer.Sound(p)
            except Exception:
                return None
    return None


SFX = {
    "spawn": _load_any(os.path.join("assets", "sfx", "spawn")),
    "exit": _load_any(os.path.join("assets", "sfx", "exit")),
    "step": _load_any(os.path.join("assets", "sfx", "step")),
    "caught": _load_any(os.path.join("assets", "sfx", "caught")),
    "hit": _load_any(os.path.join("assets", "sfx", "hit")),
    "loot": _load_any(os.path.join("assets", "sfx", "loot")),
}


def play_sfx(name, vol=0.6):
    s = SFX.get(name)
    if not s:
        return
    try:
        s.set_volume(max(0.0, min(1.0, float(vol))))
        s.play()
    except Exception:
        pass


def start_music():
    if not AUDIO_OK:
        return
    md = os.path.join("assets", "music")
    try:
        files = [os.path.join(md, f) for f in os.listdir(md) if f.lower().endswith((".mp3", ".ogg", ".wav"))]
        if not files:
            return
        files.sort()
        pygame.mixer.music.load(files[0])
        pygame.mixer.music.set_volume(0.42)
        pygame.mixer.music.play(-1)
    except Exception:
        pass


FORCE_MATRIX_LAUNCH = True
MATRIX_LAUNCH_OK = os.getenv("PYGAME_OS_LAUNCHER") == "1" or os.getenv("DREAMCRAWLER_ALLOW_STANDALONE") == "1"

W, H = 1280, 720
WINDOW_W, WINDOW_H = W, H
screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)
pygame.display.set_caption("Dream Crawler v7 Co-op")
clock = pygame.time.Clock()

TILE = 20
GRID_W = 78
GRID_H = 50

WALL = 1
FLOOR = 0
STAIRS = 3

PLAYER_R = 7.0
VISION_RADIUS_TILES = 9

FONT = None
BIG = None


def clamp(x, a, b):
    return a if x < a else b if x > b else x


def in_bounds(x, y):
    return 0 <= x < GRID_W and 0 <= y < GRID_H


def carve_room(g, x0, y0, rw, rh):
    for y in range(y0, y0 + rh):
        for x in range(x0, x0 + rw):
            if in_bounds(x, y):
                g[y][x] = FLOOR


def carve_hall(g, x1, y1, x2, y2, width=2):
    sx = 1 if x2 >= x1 else -1
    for xx in range(x1, x2 + sx, sx):
        for dy in range(-width // 2, width // 2 + 1):
            if in_bounds(xx, y1 + dy):
                g[y1 + dy][xx] = FLOOR
    sy = 1 if y2 >= y1 else -1
    for yy in range(y1, y2 + sy, sy):
        for dx in range(-width // 2, width // 2 + 1):
            if in_bounds(x2 + dx, yy):
                g[yy][x2 + dx] = FLOOR


def generate_grid(seed=None):
    rng = random.Random(seed)
    g = [[WALL for _ in range(GRID_W)] for _ in range(GRID_H)]
    rooms = []

    for _ in range(rng.randint(16, 24)):
        rw = rng.randint(8, 15)
        rh = rng.randint(7, 12)
        x0 = rng.randint(1, GRID_W - rw - 2)
        y0 = rng.randint(1, GRID_H - rh - 2)
        carve_room(g, x0, y0, rw, rh)
        rooms.append((x0 + rw // 2, y0 + rh // 2, x0, y0, rw, rh))

    rooms.sort(key=lambda r: r[0] + r[1])
    for i in range(1, len(rooms)):
        x1, y1 = rooms[i - 1][0], rooms[i - 1][1]
        x2, y2 = rooms[i][0], rooms[i][1]
        carve_hall(g, x1, y1, x2, y2, width=2 if rng.random() < 0.9 else 1)

    for _ in range(rng.randint(48, 78)):
        cx = rng.randint(2, GRID_W - 3)
        cy = rng.randint(2, GRID_H - 3)
        r = rng.randint(1, 4)
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if in_bounds(xx, yy) and (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r * r:
                    if rng.random() < 0.72:
                        g[yy][xx] = FLOOR

    sx, sy = rooms[0][0], rooms[0][1]
    ex, ey = rooms[-1][0], rooms[-1][1]
    g[ey][ex] = STAIRS
    return g, (sx, sy), (ex, ey)


def is_wall(g, tx, ty):
    if not in_bounds(tx, ty):
        return True
    return g[ty][tx] == WALL


def resolve_circle(px, py, g):
    tx = int(px // TILE)
    ty = int(py // TILE)
    for yy in range(ty - 1, ty + 2):
        for xx in range(tx - 1, tx + 2):
            if is_wall(g, xx, yy):
                rx, ry = xx * TILE, yy * TILE
                cx = clamp(px, rx, rx + TILE)
                cy = clamp(py, ry, ry + TILE)
                dx = px - cx
                dy = py - cy
                dist2 = dx * dx + dy * dy
                if dist2 < PLAYER_R * PLAYER_R and dist2 > 1e-9:
                    dist = math.sqrt(dist2)
                    push = PLAYER_R - dist
                    px += (dx / dist) * push
                    py += (dy / dist) * push
                elif dist2 <= 1e-9:
                    px += 0.4
                    py += 0.4
    return px, py


def noisy_surface(size, rng, base=180, contrast=55):
    w, h = size
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            n = rng.randint(-contrast, contrast)
            v = clamp(base + n, 0, 255)
            a = rng.randint(140, 220)
            s.set_at((x, y), (v, v, v, a))
    return s


def make_player_sprite(seed, color):
    rng = random.Random(seed)
    s = pygame.Surface((22, 26), pygame.SRCALPHA)
    for y in range(26):
        for x in range(22):
            d = math.hypot(x - 11, (y - 13) * 1.15)
            if d < 8.8 and rng.random() < 0.9:
                c0 = clamp(color[0] + rng.randint(-30, 30), 0, 255)
                c1 = clamp(color[1] + rng.randint(-30, 30), 0, 255)
                c2 = clamp(color[2] + rng.randint(-30, 30), 0, 255)
                s.set_at((x, y), (c0, c1, c2, 230))
    pygame.draw.circle(s, (20, 20, 26, 230), (8, 10), 1)
    pygame.draw.circle(s, (20, 20, 26, 230), (14, 10), 1)
    pygame.draw.line(s, (20, 20, 26, 200), (8, 15), (14, 15), 1)
    for _ in range(12):
        x = rng.randrange(0, 22)
        y1 = rng.randrange(0, 26)
        y2 = clamp(y1 + rng.randrange(4, 10), 0, 25)
        pygame.draw.line(s, (255, 255, 255, rng.randint(30, 70)), (x, y1), (x, y2), 1)
    return s


def line_of_sight(g, ax, ay, bx, by):
    x0, y0 = ax, ay
    x1, y1 = bx, by
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        if is_wall(g, x0, y0) and (x0, y0) != (ax, ay) and (x0, y0) != (bx, by):
            return False
        if x0 == x1 and y0 == y1:
            return True
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def astar(start, goal, is_walkable):
    if start == goal:
        return [start]
    open_set = []
    heappush(open_set, (0.0, start))
    g_score = {start: 0.0}
    came = {}

    def h(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    while open_set:
        _, cur = heappop(open_set)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path

        cx, cy = cur
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            nxt = (nx, ny)
            if not is_walkable(nxt):
                continue
            tentative = g_score[cur] + 1.0
            if tentative < g_score.get(nxt, 1e9):
                came[nxt] = cur
                g_score[nxt] = tentative
                heappush(open_set, (tentative + h(nxt, goal), nxt))
    return []


class Player:
    def __init__(self, name, ai=False, color=(180, 220, 230), seed=0):
        self.name = name
        self.ai = ai
        self.x = 0.0
        self.y = 0.0
        self.alive = True
        self.weapons = 0
        self.treasure = 0
        self.speed = 108.0
        self.sprite = make_player_sprite(seed, color)
        self.anim_t = 0.0
        self.attack_anim_t = 0.0
        self.attack_flash_t = 0.0
        self.swing_dir = -1 if (seed % 2) else 1

        self.vision_radius = VISION_RADIUS_TILES + (seed % 2)
        self.known_open = set()
        self.known_walls = set()
        self.known_treasures = set()
        self.known_weapons = set()
        self.known_stairs = None
        self.known_monster = None
        self.ai_target = None
        self.ai_path = []
        self.stuck_time = 0.0
        self.last_tile = None

    def spawn(self, sx, sy):
        self.x = (sx + random.uniform(-0.2, 0.2) + 0.5) * TILE
        self.y = (sy + random.uniform(-0.2, 0.2) + 0.5) * TILE
        self.alive = True
        self.weapons = max(0, self.weapons)
        self.ai_target = None
        self.ai_path = []
        self.stuck_time = 0.0
        self.last_tile = None
        self.known_open.clear()
        self.known_walls.clear()
        self.known_treasures.clear()
        self.known_weapons.clear()
        self.known_stairs = None
        self.known_monster = None

    def draw(self, surf, camx, camy):
        if not self.alive:
            return
        bob = int(math.sin(self.anim_t * 8.0) * 2)
        px = int(self.x - camx)
        py = int(self.y - camy)
        surf.blit(self.sprite, (px - 11, py - 13 + bob))

        if self.weapons > 0:
            wx = px + (7 * self.swing_dir)
            wy = py - 2
            pygame.draw.line(surf, (220, 220, 230), (px, py), (wx, wy), 2)
            pygame.draw.circle(surf, (245, 205, 120), (wx, wy), 2)

        if self.attack_anim_t > 0.0:
            pulse = int(18 + 12 * (self.attack_anim_t / 0.18))
            color = (255, 180, 120, 160)
            ring = pygame.Surface((pulse * 2, pulse * 2), pygame.SRCALPHA)
            pygame.draw.circle(ring, color, (pulse, pulse), pulse, 2)
            surf.blit(ring, (px - pulse, py - pulse))


class Monster:
    def __init__(self, x, y, seed=0):
        self.x = x
        self.y = y
        self.hp = 3
        self.seed = seed
        self.v = 72.0
        self.base = noisy_surface((30, 34), random.Random(seed), base=200, contrast=52)
        self.t = 0.0

    @property
    def alive(self):
        return self.hp > 0

    def update(self, dt, target):
        if not self.alive:
            return
        self.t += dt
        tx, ty = target
        dx = tx - self.x
        dy = ty - self.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            self.x += (dx / d) * self.v * dt
            self.y += (dy / d) * self.v * dt

    def draw(self, surf, camx, camy):
        if not self.alive:
            return
        jx = int(math.sin(self.t * 14 + self.seed) * 2)
        jy = int(math.cos(self.t * 11 + self.seed) * 2)
        surf.blit(self.base, (int(self.x - camx) - 15 + jx, int(self.y - camy) - 17 + jy))
        if FONT:
            img = FONT.render(f"HP:{self.hp}", True, (255, 220, 220))
            surf.blit(img, (int(self.x - camx) - 14, int(self.y - camy) - 28))


class Game:
    def __init__(self):
        self.room_index = 0
        self.seed_base = random.randint(0, 9_999_999)
        self.chat_lines = []
        self.chat_timer = 0.0
        self.chat_cooldowns = {}

        self.players = [
            Player("You", ai=False, color=(130, 235, 210), seed=1),
            Player("Nova", ai=True, color=(245, 180, 130), seed=2),
            Player("Kite", ai=True, color=(145, 200, 255), seed=3),
            Player("Rook", ai=True, color=(210, 210, 120), seed=4),
            Player("Mira", ai=True, color=(225, 160, 235), seed=5),
            Player("Echo", ai=True, color=(145, 235, 170), seed=6),
            Player("Vex", ai=True, color=(235, 150, 165), seed=7),
            Player("Lux", ai=True, color=(170, 185, 245), seed=8),
            Player("Drift", ai=True, color=(230, 210, 140), seed=9),
        ]
        self.human = self.players[0]

        self.grid = []
        self.stairs = (0, 0)
        self.monster = None
        self.treasures = []
        self.weapons_pickups = []
        self.weapon_pickup_types = {}
        self.weapon_type_styles = {
            "stick": ("Stick", (152, 114, 72), (210, 182, 130)),
            "spike": ("Spike", (176, 176, 192), (228, 228, 240)),
            "club": ("Club", (124, 94, 60), (200, 170, 120)),
            "shard": ("Shard", (120, 178, 205), (190, 230, 245)),
        }
        self.level_message = ""
        self.level_message_t = 0.0

        self.human_visible = set()
        self.human_explored = set()
        self.used_level_seeds = set()
        self._new_room(initial=True)

    def _log_chat(self, who, text):
        key = f"{who}:{text.lower()}"
        now = pygame.time.get_ticks() / 1000.0
        if self.chat_cooldowns.get(key, 0) > now:
            return
        self.chat_cooldowns[key] = now + 6.0
        self.chat_lines.append((who, text))
        self.chat_lines = self.chat_lines[-7:]

    def _new_room(self, initial=False):
        seed = self.seed_base + self.room_index * 1171 + random.randint(0, 999)
        attempts = 0
        while seed in self.used_level_seeds and attempts < 16:
            seed += random.randint(31, 997)
            attempts += 1
        self.used_level_seeds.add(seed)
        self.grid, (sx, sy), self.stairs = generate_grid(seed)

        mx = (self.stairs[0] + 0.5) * TILE
        my = (self.stairs[1] + 0.5) * TILE
        self.monster = Monster(mx, my, seed=seed + 77)

        for p in self.players:
            p.spawn(sx, sy)
            if not initial:
                p.weapons = 0
            self._observe_world(p)

        rng = random.Random(seed + 333)
        floor_tiles = [(x, y) for y in range(GRID_H) for x in range(GRID_W) if self.grid[y][x] == FLOOR]
        rng.shuffle(floor_tiles)
        self.treasures = floor_tiles[:rng.randint(16, 24)]
        self.weapons_pickups = floor_tiles[rng.randint(26, 34):rng.randint(42, 54)]
        self.weapon_pickup_types = {
            tile: rng.choice(tuple(self.weapon_type_styles.keys())) for tile in self.weapons_pickups
        }

        self.human_visible.clear()
        self.human_explored.clear()
        self._observe_world(self.human, update_player_fog=True)

        self.level_message = f"Room {self.room_index + 1}: clear monster or race for stairs"
        self.level_message_t = 0.0
        self._play_spatial_sfx("spawn", ((sx + 0.5) * TILE, (sy + 0.5) * TILE), 0.55)

    def _move_player(self, p, dx, dy, dt):
        if not p.alive:
            return
        mag = math.hypot(dx, dy)
        if mag > 0:
            dx /= mag
            dy /= mag
        speed = p.speed + (12 if p.ai else 0)
        nx = p.x + dx * speed * dt
        ny = p.y + dy * speed * dt
        p.x, p.y = resolve_circle(nx, ny, self.grid)
        p.anim_t += dt

    def _play_spatial_sfx(self, name: str, source_xy: tuple[float, float], base_vol: float = 0.55, max_dist_tiles: float = 16.0):
        if not self.human.alive:
            play_sfx(name, base_vol * 0.35)
            return
        hx, hy = self.human.x, self.human.y
        sx, sy = source_xy
        dist = math.hypot(hx - sx, hy - sy)
        max_dist = max(1.0, max_dist_tiles * TILE)
        atten = max(0.0, 1.0 - (dist / max_dist))
        if atten > 0.015:
            play_sfx(name, base_vol * atten)

    def _nearest_alive_player_to_monster(self):
        alive = [p for p in self.players if p.alive]
        if not alive:
            return self.human
        return min(alive, key=lambda pl: math.hypot(pl.x - self.monster.x, pl.y - self.monster.y))

    def _observe_world(self, p, update_player_fog=False):
        if not p.alive:
            return
        cx, cy = int(p.x // TILE), int(p.y // TILE)
        visible = set()
        r = p.vision_radius
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if not in_bounds(xx, yy):
                    continue
                if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) > r * r:
                    continue
                if not line_of_sight(self.grid, cx, cy, xx, yy):
                    continue
                visible.add((xx, yy))
                t = self.grid[yy][xx]
                if t == WALL:
                    p.known_walls.add((xx, yy))
                else:
                    p.known_open.add((xx, yy))
                if t == STAIRS:
                    p.known_stairs = (xx, yy)

        p.known_treasures.intersection_update(self.treasures)
        p.known_weapons.intersection_update(self.weapons_pickups)

        for item in self.treasures:
            if item in visible:
                p.known_treasures.add(item)
        for item in self.weapons_pickups:
            if item in visible:
                p.known_weapons.add(item)

        if self.monster is not None:
            mtx, mty = int(self.monster.x // TILE), int(self.monster.y // TILE)
            if self.monster.alive and (mtx, mty) in visible:
                p.known_monster = (mtx, mty)
            elif p.known_monster and not self.monster.alive:
                p.known_monster = None
        elif p.known_monster:
            p.known_monster = None

        if update_player_fog:
            self.human_visible = visible
            self.human_explored.update(visible)

    def _pickup_checks(self, p):
        tx, ty = int(p.x // TILE), int(p.y // TILE)
        if (tx, ty) in self.treasures:
            self.treasures.remove((tx, ty))
            p.treasure += 1
            for q in self.players:
                q.known_treasures.discard((tx, ty))
            if p.ai:
                self._log_chat(p.name, "found treasure in this cavern")
            self._play_spatial_sfx("loot", (p.x, p.y), 0.36)
        if (tx, ty) in self.weapons_pickups:
            self.weapons_pickups.remove((tx, ty))
            weapon_kind = self.weapon_pickup_types.pop((tx, ty), "stick")
            p.weapons += 1
            for q in self.players:
                q.known_weapons.discard((tx, ty))
            if p.ai:
                label = self.weapon_type_styles.get(weapon_kind, (weapon_kind.title(),))[0]
                self._log_chat(p.name, f"grabbed a one-use {label}")
            self._play_spatial_sfx("loot", (p.x, p.y), 0.34)

    def _monster_combat(self, p, attack=False):
        if not p.alive or not self.monster.alive:
            return
        d = math.hypot(p.x - self.monster.x, p.y - self.monster.y)
        if attack and d < 42 and p.weapons > 0:
            p.weapons -= 1
            p.attack_anim_t = 0.18
            p.attack_flash_t = 0.10
            self.monster.hp = max(0, self.monster.hp - 1)
            self._log_chat(p.name, f"hit monster ({self.monster.hp}/3 left)")
            self._play_spatial_sfx("hit", (self.monster.x, self.monster.y), 0.62)
            if self.monster.hp <= 0:
                self._log_chat("System", "monster down — stairs are clear")
                self._play_spatial_sfx("exit", (self.monster.x, self.monster.y), 0.74)
        # one boss bite downs a player until the next generated level.
        if d < 20 and self.monster.alive:
            p.alive = False
            self._play_spatial_sfx("caught", (p.x, p.y), 0.62)
            self._log_chat("System", f"{p.name} is down until next room")

    def _find_frontier(self, p, tx, ty):
        best = None
        bestd = 1e9
        for x, y in p.known_open:
            unknown_n = 0
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if in_bounds(nx, ny) and (nx, ny) not in p.known_open and (nx, ny) not in p.known_walls:
                    unknown_n += 1
            if unknown_n <= 0:
                continue
            d = (x - tx) * (x - tx) + (y - ty) * (y - ty)
            if d < bestd:
                bestd = d
                best = (x, y)
        return best

    def _walkable_known(self, p, tile, target):
        x, y = tile
        if not in_bounds(x, y):
            return False
        if tile == target:
            return not is_wall(self.grid, x, y)
        if tile in p.known_walls:
            return False
        if tile in p.known_open:
            return True
        return False

    def _ai_update(self, p, dt):
        if not p.alive:
            return

        self._observe_world(p)
        tx, ty = int(p.x // TILE), int(p.y // TILE)

        target = None
        if p.weapons <= 0 and p.known_weapons:
            target = min(p.known_weapons, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
        elif self.monster.alive and p.known_monster:
            target = p.known_monster
        elif p.known_treasures:
            target = min(p.known_treasures, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
        elif p.known_stairs and not self.monster.alive:
            target = p.known_stairs
        else:
            target = self._find_frontier(p, tx, ty)
            if target is None:
                target = (tx, ty)

        current_tile = (tx, ty)
        if current_tile == p.last_tile:
            p.stuck_time += dt
        else:
            p.stuck_time = 0.0
            p.last_tile = current_tile

        if target != p.ai_target or not p.ai_path or p.stuck_time > 0.9:
            p.ai_target = target
            p.ai_path = astar(current_tile, target, lambda t: self._walkable_known(p, t, target))
            if p.ai_path and p.ai_path[0] == current_tile:
                p.ai_path = p.ai_path[1:]
            if p.stuck_time > 0.9 and not p.ai_path:
                dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
                random.shuffle(dirs)
                for dx, dy in dirs:
                    nx, ny = tx + dx, ty + dy
                    if in_bounds(nx, ny) and not is_wall(self.grid, nx, ny):
                        p.ai_path = [(nx, ny)]
                        break
                p.stuck_time = 0.0

        if p.ai_path:
            gx, gy = p.ai_path[0]
            wx = (gx + 0.5) * TILE
            wy = (gy + 0.5) * TILE
            dx = wx - p.x
            dy = wy - p.y
            if dx * dx + dy * dy < 16.0:
                p.ai_path.pop(0)
            else:
                self._move_player(p, dx, dy, dt)
        else:
            self._move_player(p, 0.0, 0.0, dt)

        self._pickup_checks(p)
        self._monster_combat(p, attack=True)

    def update(self, dt, keys):
        self.level_message_t += dt
        self.chat_timer += dt

        dx = dy = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1

        self._move_player(self.human, dx, dy, dt)
        self._observe_world(self.human, update_player_fog=True)
        self._pickup_checks(self.human)
        self._monster_combat(self.human, attack=bool(keys[pygame.K_SPACE]))

        for p in self.players[1:]:
            self._ai_update(p, dt)

        for p in self.players:
            if p.attack_anim_t > 0.0:
                p.attack_anim_t = max(0.0, p.attack_anim_t - dt)
            if p.attack_flash_t > 0.0:
                p.attack_flash_t = max(0.0, p.attack_flash_t - dt)

        if self.monster.alive:
            t = self._nearest_alive_player_to_monster()
            self.monster.update(dt, (t.x, t.y))

        if not self.human.alive:
            self.room_index = 0
            self._log_chat("System", "you were downed — run restarted")
            self._new_room(initial=True)
            return

        if not any(p.alive for p in self.players):
            self.room_index += 1
            self._log_chat("System", "party wiped, next room generated")
            self._new_room()
            return

        for p in self.players:
            if not p.alive:
                continue
            if (int(p.x // TILE), int(p.y // TILE)) == self.stairs:
                self.room_index += 1
                self._log_chat("System", f"{p.name} reached the stairs")
                self._play_spatial_sfx("exit", (p.x, p.y), 0.72)
                self._new_room()
                return

        if self.chat_timer > random.uniform(3.8, 6.6):
            self.chat_timer = 0.0
            alive_ai = [p for p in self.players[1:] if p.alive]
            if alive_ai and random.random() < 0.6:
                speaker = random.choice(alive_ai)
                line = random.choice([
                    "checking side cavern for loot",
                    "marking a wall choke point",
                    "monster route is near center",
                    "need another weapon pickup",
                    "stairs should be past this tunnel",
                ])
                self._log_chat(speaker.name, line)

    def draw(self, surf):
        camx = clamp(self.human.x - W * 0.5, 0, GRID_W * TILE - W)
        camy = clamp(self.human.y - H * 0.5, 0, GRID_H * TILE - H)

        y0 = max(0, int(camy // TILE) - 1)
        y1 = min(GRID_H, int((camy + H) // TILE) + 2)
        x0 = max(0, int(camx // TILE) - 1)
        x1 = min(GRID_W, int((camx + W) // TILE) + 2)

        for y in range(y0, y1):
            for x in range(x0, x1):
                r = pygame.Rect(x * TILE - camx, y * TILE - camy, TILE, TILE)
                tile = (x, y)

                if tile not in self.human_explored:
                    pygame.draw.rect(surf, (3, 4, 6), r)
                    continue

                t = self.grid[y][x]
                if t == WALL:
                    v = 28 + ((x * 11 + y * 17) % 32)
                    base = (v, v + 3, v + 6)
                elif t == STAIRS:
                    base = (84, 86, 102)
                else:
                    v = 42 + ((x * 3 + y * 5) % 18)
                    base = (v, v + 7, v + 4)
                pygame.draw.rect(surf, base, r)

                if t == STAIRS:
                    pygame.draw.rect(surf, (180, 185, 205), r.inflate(-8, -8), 2)

                if tile not in self.human_visible:
                    shadow = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                    shadow.fill((0, 0, 0, 140))
                    surf.blit(shadow, r.topleft)

        for x, y in self.treasures:
            if (x, y) in self.human_visible:
                px, py = int(x * TILE - camx), int(y * TILE - camy)
                pygame.draw.circle(surf, (235, 195, 90), (px + TILE // 2, py + TILE // 2), 4)

        for x, y in self.weapons_pickups:
            if (x, y) in self.human_visible:
                px, py = int(x * TILE - camx), int(y * TILE - camy)
                kind = self.weapon_pickup_types.get((x, y), "stick")
                _label, c0, c1 = self.weapon_type_styles.get(kind, ("Item", (180, 140, 100), (220, 200, 170)))
                cx = px + TILE // 2
                cy = py + TILE // 2
                if kind == "stick":
                    pygame.draw.line(surf, c0, (cx - 4, cy + 3), (cx + 4, cy - 3), 3)
                    pygame.draw.circle(surf, c1, (cx + 4, cy - 3), 2)
                elif kind == "spike":
                    pygame.draw.polygon(surf, c1, [(cx, cy - 5), (cx + 4, cy + 4), (cx - 4, cy + 4)])
                    pygame.draw.polygon(surf, c0, [(cx, cy - 3), (cx + 2, cy + 3), (cx - 2, cy + 3)])
                elif kind == "club":
                    pygame.draw.line(surf, c0, (cx - 4, cy + 4), (cx + 3, cy - 3), 3)
                    pygame.draw.circle(surf, c1, (cx + 4, cy - 4), 3)
                else:
                    pygame.draw.polygon(surf, c1, [(cx, cy - 5), (cx + 4, cy), (cx, cy + 5), (cx - 4, cy)])
                    pygame.draw.polygon(surf, c0, [(cx, cy - 2), (cx + 2, cy), (cx, cy + 2), (cx - 2, cy)])

        m_tile = (int(self.monster.x // TILE), int(self.monster.y // TILE))
        if self.monster.alive and (m_tile in self.human_visible or math.hypot(self.human.x - self.monster.x, self.human.y - self.monster.y) < TILE * 1.8):
            self.monster.draw(surf, camx, camy)

        for p in self.players:
            if not p.alive:
                continue
            ptile = (int(p.x // TILE), int(p.y // TILE))
            if p is self.human or ptile in self.human_visible:
                p.draw(surf, camx, camy)

        if FONT:
            alive = sum(1 for p in self.players if p.alive)
            total_treasure = sum(p.treasure for p in self.players)
            status = f"Room {self.room_index + 1}  Alive {alive}/{len(self.players)}  MonsterHP {self.monster.hp if self.monster.alive else 0}  Treasure {total_treasure}"
            surf.blit(FONT.render(status, True, (235, 235, 240)), (12, H - 26))
            p = self.human
            surf.blit(FONT.render(f"You: weapons {p.weapons}  treasure {p.treasure}  (SPACE = attack)", True, (230, 250, 235)), (12, H - 48))

            y = 12
            for who, line in self.chat_lines[-6:]:
                surf.blit(FONT.render(f"{who}: {line}", True, (220, 220, 230)), (12, y))
                y += 18

            if self.level_message and self.level_message_t < 2.8 and BIG:
                img = BIG.render(self.level_message, True, (238, 238, 246))
                surf.blit(img, img.get_rect(center=(W // 2, 34)))


def main():
    global FONT, BIG, screen, WINDOW_W, WINDOW_H
    pygame.font.init()
    FONT = pygame.font.SysFont("consolas", 18)
    BIG = pygame.font.SysFont("consolas", 28, bold=True)

    if FORCE_MATRIX_LAUNCH and not MATRIX_LAUNCH_OK:
        print("Dreamcrawler is intended to run from MatrixOS. Set DREAMCRAWLER_ALLOW_STANDALONE=1 to test standalone.")
        return

    start_music()
    g = Game()
    frame_surface = pygame.Surface((W, H))
    running = True

    while running:
        dt = clock.tick(60) / 1000.0
        if dt > 0.05:
            dt = 0.05

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE:
                new_w = max(640, e.w)
                new_h = max(360, e.h)
                WINDOW_W, WINDOW_H = new_w, new_h
                screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)

        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            running = False

        g.update(dt, keys)
        frame_surface.fill((8, 10, 14))
        g.draw(frame_surface)

        if WINDOW_W == W and WINDOW_H == H:
            screen.blit(frame_surface, (0, 0))
        else:
            target_ratio = W / float(H)
            win_ratio = WINDOW_W / float(max(1, WINDOW_H))
            if win_ratio > target_ratio:
                render_h = WINDOW_H
                render_w = int(render_h * target_ratio)
            else:
                render_w = WINDOW_W
                render_h = int(render_w / target_ratio)
            off_x = (WINDOW_W - render_w) // 2
            off_y = (WINDOW_H - render_h) // 2
            screen.fill((0, 0, 0))
            scaled = pygame.transform.smoothscale(frame_surface, (render_w, render_h))
            screen.blit(scaled, (off_x, off_y))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fn = _crash(e)
        print("Crashed. Report written to:", fn)
        raise
