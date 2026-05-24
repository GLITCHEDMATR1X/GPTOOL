import os
import sys
import math
import random
import time
import traceback
import wave
from array import array
from dataclasses import dataclass

import pygame


CRASH_REPORT_PATH = "crash_report.txt"
ASSETS_DIR = "assets"
SFX_DIR = os.path.join(ASSETS_DIR, "sfx")
HUD_HEIGHT = 72


@dataclass
class Camera:
    x: int
    y: int
    width: int
    height: int

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)


@dataclass
class SceneConfig:
    cols: int = 70
    rows: int = 45
    tile_w: int = 26
    tile_h: int = 34


@dataclass
class GameState:
    started: bool = False
    found: bool = False
    start_time: float = 0.0
    found_time: float = 0.0
    renaldo_rect: pygame.Rect | None = None
    renaldo_pos: tuple[int, int] | None = None


@dataclass
class Person:
    rect: pygame.Rect
    sprite: pygame.Surface
    is_renaldo: bool = False


@dataclass
class Explosion:
    x: int
    y: int
    start_time: float


class CrashReporter:
    @staticmethod
    def capture(exc: BaseException) -> None:
        report_lines = [
            "=== Crash Report ===",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Python: {sys.version}",
            f"Platform: {sys.platform}",
            f"Executable: {sys.executable}",
            "",
            "--- Traceback ---",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ]
        with open(CRASH_REPORT_PATH, "w", encoding="utf-8") as handle:
            handle.write("\n".join(report_lines))


class SpriteFactory:
    def make_person(self, seed: int, role: str = "npc") -> pygame.Surface:
        rng = random.Random(seed)
        width, height = 24, 32
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        palette = self._make_palette(rng, role)
        pixel = 2

        self._draw_body(surface, palette, pixel, role)
        self._draw_face(surface, palette, pixel, rng)
        self._draw_accessory(surface, palette, pixel, rng)
        return surface

    def _make_palette(self, rng: random.Random, role: str) -> dict[str, pygame.Color]:
        skin_tones = [
            pygame.Color(244, 204, 176),
            pygame.Color(220, 170, 140),
            pygame.Color(198, 140, 110),
            pygame.Color(140, 92, 60),
        ]
        if role in {"renaldo", "lookalike"}:
            primary = pygame.Color(200, 40, 40)
            secondary = pygame.Color(245, 245, 245)
            if role == "lookalike":
                primary = pygame.Color(180 + rng.randrange(40), 50 + rng.randrange(40), 50 + rng.randrange(40))
                secondary = pygame.Color(220 + rng.randrange(20), 220 + rng.randrange(20), 220 + rng.randrange(20))
        else:
            primary = pygame.Color(rng.randrange(60, 210), rng.randrange(60, 210), rng.randrange(60, 210))
            secondary = pygame.Color(rng.randrange(140, 255), rng.randrange(140, 255), rng.randrange(140, 255))

        return {
            "skin": rng.choice(skin_tones),
            "hair": pygame.Color(rng.randrange(40, 120), rng.randrange(20, 70), rng.randrange(10, 50)),
            "shirt": primary,
            "stripe": secondary,
            "pants": pygame.Color(rng.randrange(30, 90), rng.randrange(30, 90), rng.randrange(80, 170)),
            "shoes": pygame.Color(20, 20, 20),
            "accent": pygame.Color(rng.randrange(120, 220), rng.randrange(60, 140), rng.randrange(60, 140)),
        }

    def _draw_body(self, surface: pygame.Surface, palette: dict[str, pygame.Color], pixel: int, role: str) -> None:
        shirt_rect = pygame.Rect(6, 12, 12, 10)
        for y in range(shirt_rect.top, shirt_rect.bottom, pixel):
            for x in range(shirt_rect.left, shirt_rect.right, pixel):
                if (y // pixel) % 2 == 0:
                    surface.fill(palette["stripe"], (x, y, pixel, pixel))
                else:
                    surface.fill(palette["shirt"], (x, y, pixel, pixel))

        pants_rect = pygame.Rect(6, 22, 12, 6)
        surface.fill(palette["pants"], pants_rect)

        surface.fill(palette["shoes"], (6, 28, 5, 3))
        surface.fill(palette["shoes"], (13, 28, 5, 3))

    def _draw_face(self, surface: pygame.Surface, palette: dict[str, pygame.Color], pixel: int, rng: random.Random) -> None:
        surface.fill(palette["skin"], (7, 4, 10, 8))
        surface.fill(palette["hair"], (7, 4, 10, 3))
        if rng.random() < 0.4:
            surface.fill(palette["accent"], (6, 11, 12, 1))
        surface.fill(pygame.Color(20, 20, 20), (9, 8, pixel, pixel))
        surface.fill(pygame.Color(20, 20, 20), (13, 8, pixel, pixel))
        surface.fill(pygame.Color(120, 60, 60), (10, 10, 4, 2))
        if rng.random() < 0.3:
            surface.fill(pygame.Color(30, 30, 30), (8, 7, 8, 1))

    def _draw_accessory(self, surface: pygame.Surface, palette: dict[str, pygame.Color], pixel: int, rng: random.Random) -> None:
        if rng.random() < 0.35:
            surface.fill(palette["accent"], (15, 12, 3, 8))
        if rng.random() < 0.35:
            surface.fill(pygame.Color(240, 220, 100), (4, 16, 3, 3))
        if rng.random() < 0.2:
            surface.fill(pygame.Color(80, 120, 180), (5, 22, 2, 4))
        if rng.random() < 0.25:
            surface.fill(pygame.Color(100, 70, 40), (17, 20, 3, 3))


def ensure_assets(factory: SpriteFactory) -> dict[str, pygame.Surface]:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(SFX_DIR, exist_ok=True)
    sprites: dict[str, pygame.Surface] = {}

    renaldo_sprite = factory.make_person(999, role="renaldo")
    sprites["renaldo"] = renaldo_sprite
    pygame.image.save(renaldo_sprite, os.path.join(ASSETS_DIR, "renaldo.png"))

    for idx in range(10):
        sprite = factory.make_person(idx, role="npc")
        sprites[f"npc_{idx}"] = sprite
        pygame.image.save(sprite, os.path.join(ASSETS_DIR, f"npc_{idx}.png"))

    for idx in range(4):
        sprite = factory.make_person(100 + idx, role="lookalike")
        sprites[f"lookalike_{idx}"] = sprite
        pygame.image.save(sprite, os.path.join(ASSETS_DIR, f"lookalike_{idx}.png"))

    generate_sfx(os.path.join(SFX_DIR, "start.wav"), frequency=520, duration=0.25)
    generate_sfx(os.path.join(SFX_DIR, "explode.wav"), frequency=140, duration=0.3, noise=True)
    generate_sfx(os.path.join(SFX_DIR, "win.wav"), frequency=720, duration=0.35)

    return sprites


def generate_sfx(path: str, frequency: int, duration: float, noise: bool = False) -> None:
    sample_rate = 44100
    amplitude = 16000
    total_samples = int(sample_rate * duration)
    samples = array("h")
    for i in range(total_samples):
        t = i / sample_rate
        if noise:
            value = random.uniform(-1.0, 1.0)
        else:
            value = math.sin(2 * math.pi * frequency * t)
        envelope = 1.0 - (i / total_samples)
        samples.append(int(amplitude * value * envelope))

    with wave.open(path, "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(sample_rate)
        wave_file.writeframes(samples.tobytes())


def build_scene(
    config: SceneConfig,
    factory: SpriteFactory,
    forbidden_rect: pygame.Rect,
) -> tuple[pygame.Surface, pygame.Rect, tuple[int, int], list[Person]]:
    scene_width = config.cols * config.tile_w
    scene_height = config.rows * config.tile_h
    scene = pygame.Surface((scene_width, scene_height))
    scene.fill((0, 0, 0))

    rng = random.Random()
    renaldo_cell = _pick_renaldo_cell(rng, config, forbidden_rect)
    renaldo_pos = (renaldo_cell[0] * config.tile_w, renaldo_cell[1] * config.tile_h)

    people: list[Person] = []

    for row in range(config.rows):
        for col in range(config.cols):
            tile_rect = pygame.Rect(col * config.tile_w, row * config.tile_h, config.tile_w, config.tile_h)
            _draw_tile(scene, tile_rect, rng)

            seed = rng.randrange(1_000_000)
            is_renaldo = (col, row) == renaldo_cell
            if is_renaldo:
                role = "renaldo"
            elif rng.random() < 0.08:
                role = "lookalike"
            else:
                role = "npc"
            sprite = factory.make_person(seed, role=role)

            sprite_rect = sprite.get_rect()
            sprite_rect.midbottom = (tile_rect.centerx, tile_rect.bottom - 2)
            people.append(Person(rect=sprite_rect.copy(), sprite=sprite, is_renaldo=is_renaldo))

            if rng.random() < 0.16:
                _draw_prop(scene, tile_rect, rng)

    renaldo_rect = pygame.Rect(renaldo_pos[0], renaldo_pos[1], config.tile_w, config.tile_h)
    return scene, renaldo_rect, renaldo_pos, people


def _pick_renaldo_cell(rng: random.Random, config: SceneConfig, forbidden_rect: pygame.Rect) -> tuple[int, int]:
    max_attempts = 5000
    for _ in range(max_attempts):
        col = rng.randrange(config.cols)
        row = rng.randrange(config.rows)
        tile_rect = pygame.Rect(col * config.tile_w, row * config.tile_h, config.tile_w, config.tile_h)
        if not tile_rect.colliderect(forbidden_rect):
            return col, row
    return config.cols - 1, config.rows - 1


def _draw_tile(surface: pygame.Surface, rect: pygame.Rect, rng: random.Random) -> None:
    base_color = pygame.Color(20 + rng.randrange(25), 20 + rng.randrange(25), 20 + rng.randrange(25))
    surface.fill(base_color, rect)
    pygame.draw.rect(surface, pygame.Color(35, 35, 35), rect, 1)


def _draw_prop(surface: pygame.Surface, rect: pygame.Rect, rng: random.Random) -> None:
    prop_type = rng.choice(["balloon", "umbrella", "flag", "sign"])
    center_x = rect.centerx
    top = rect.top + 4
    if prop_type == "balloon":
        color = pygame.Color(rng.randrange(180, 255), rng.randrange(40, 160), rng.randrange(40, 160))
        pygame.draw.circle(surface, color, (center_x, top + 4), 4)
        pygame.draw.line(surface, pygame.Color(80, 80, 80), (center_x, top + 8), (center_x, rect.bottom - 6), 1)
    elif prop_type == "umbrella":
        color = pygame.Color(rng.randrange(80, 180), rng.randrange(80, 180), rng.randrange(140, 220))
        pygame.draw.polygon(surface, color, [
            (center_x - 6, top + 6),
            (center_x + 6, top + 6),
            (center_x, top),
        ])
        pygame.draw.line(surface, pygame.Color(80, 80, 80), (center_x, top + 6), (center_x, rect.bottom - 6), 1)
    elif prop_type == "sign":
        color = pygame.Color(rng.randrange(150, 220), rng.randrange(120, 200), rng.randrange(80, 160))
        pygame.draw.rect(surface, color, (center_x - 5, top + 2, 10, 6))
        pygame.draw.line(surface, pygame.Color(60, 60, 60), (center_x, top + 8), (center_x, rect.bottom - 6), 1)
    else:
        color = pygame.Color(rng.randrange(160, 240), rng.randrange(60, 120), rng.randrange(60, 120))
        pygame.draw.rect(surface, color, (center_x - 2, top + 2, 4, 6))
        pygame.draw.line(surface, pygame.Color(60, 60, 60), (center_x, top + 8), (center_x, rect.bottom - 6), 1)


def draw_hud(
    screen: pygame.Surface,
    game_state: GameState,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    renaldo_sprite: pygame.Surface,
) -> None:
    bar_rect = pygame.Rect(0, 0, screen.get_width(), HUD_HEIGHT)
    pygame.draw.rect(screen, (0, 0, 0), bar_rect)
    pygame.draw.line(screen, (40, 40, 40), (0, HUD_HEIGHT - 1), (screen.get_width(), HUD_HEIGHT - 1), 2)

    title = font.render("Where's Renaldo?", True, (230, 230, 240))
    screen.blit(title, (16, 10))

    if game_state.started:
        elapsed = (game_state.found_time or time.time()) - game_state.start_time
        timer_text = small_font.render(f"Time: {elapsed:.1f}s", True, (200, 220, 240))
    else:
        timer_text = small_font.render("Press SPACE to begin", True, (200, 220, 240))
    screen.blit(timer_text, (16, 40))

    instruction = "Click renaldo!" if game_state.started else "Arrow keys / WASD to pan"
    instruction_text = small_font.render(instruction, True, (180, 200, 220))
    screen.blit(instruction_text, (240, 42))

    sprite_rect = renaldo_sprite.get_rect()
    sprite_rect.midleft = (screen.get_width() - 120, HUD_HEIGHT // 2)
    screen.blit(renaldo_sprite, sprite_rect)
    label = small_font.render("Find:", True, (200, 200, 210))
    screen.blit(label, (sprite_rect.left - 50, sprite_rect.centery - 8))


def draw_message(screen: pygame.Surface, font: pygame.font.Font, message: str) -> None:
    overlay = pygame.Surface((screen.get_width(), screen.get_height() - HUD_HEIGHT), pygame.SRCALPHA)
    overlay.fill((10, 10, 20, 200))
    screen.blit(overlay, (0, HUD_HEIGHT))

    text_surface = font.render(message, True, (240, 240, 240))
    text_rect = text_surface.get_rect(center=(screen.get_width() // 2, HUD_HEIGHT + (screen.get_height() - HUD_HEIGHT) // 2))
    screen.blit(text_surface, text_rect)


def clamp_camera(camera: Camera, config: SceneConfig) -> None:
    max_x = config.cols * config.tile_w - camera.width
    max_y = config.rows * config.tile_h - camera.height
    camera.x = max(0, min(camera.x, max_x))
    camera.y = max(0, min(camera.y, max_y))


def draw_explosions(screen: pygame.Surface, camera: Camera, explosions: list[Explosion]) -> None:
    now = time.time()
    for explosion in explosions[:]:
        age = now - explosion.start_time
        if age > 0.6:
            explosions.remove(explosion)
            continue
        radius = int(6 + age * 24)
        alpha = max(0, 200 - int(age * 320))
        color = pygame.Color(255, 120, 60, alpha)
        overlay = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(overlay, color, (radius, radius), radius)
        screen.blit(overlay, (explosion.x - camera.x - radius, explosion.y - camera.y - radius + HUD_HEIGHT))


def load_sfx() -> dict[str, pygame.mixer.Sound] | None:
    try:
        pygame.mixer.init()
    except pygame.error:
        return None

    sounds: dict[str, pygame.mixer.Sound] = {}
    for name in ("start", "explode", "win"):
        path = os.path.join(SFX_DIR, f"{name}.wav")
        if os.path.exists(path):
            sounds[name] = pygame.mixer.Sound(path)
    return sounds


def play_sound(sounds: dict[str, pygame.mixer.Sound] | None, key: str) -> None:
    if sounds is None:
        return
    sound = sounds.get(key)
    if sound:
        sound.play()


def run_game() -> None:
    pygame.init()
    pygame.display.set_caption("Where's Renaldo - Pixel Hunt")

    screen = pygame.display.set_mode((960, 640))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 24, bold=True)
    small_font = pygame.font.SysFont("arial", 16)

    factory = SpriteFactory()
    ensure_assets(factory)
    renaldo_sprite = factory.make_person(999, role="renaldo")
    sounds = load_sfx()
    config = SceneConfig()

    scene_width = config.cols * config.tile_w
    scene_height = config.rows * config.tile_h
    view_height = screen.get_height() - HUD_HEIGHT
    camera = Camera(
        (scene_width - screen.get_width()) // 2,
        (scene_height - view_height) // 2,
        screen.get_width(),
        view_height,
    )

    scene, renaldo_rect, renaldo_pos, people = build_scene(config, factory, camera.rect())
    game_state = GameState(renaldo_rect=renaldo_rect, renaldo_pos=renaldo_pos)
    markers: list[tuple[int, int, float]] = []
    explosions: list[Explosion] = []

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_SPACE and not game_state.started:
                    game_state.started = True
                    game_state.start_time = time.time()
                    play_sound(sounds, "start")
                if event.key == pygame.K_r:
                    camera.x = (scene_width - screen.get_width()) // 2
                    camera.y = (scene_height - view_height) // 2
                    scene, renaldo_rect, renaldo_pos, people = build_scene(config, factory, camera.rect())
                    game_state = GameState(renaldo_rect=renaldo_rect, renaldo_pos=renaldo_pos)
                    markers.clear()
                    explosions.clear()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game_state.started:
                if event.pos[1] < HUD_HEIGHT:
                    continue
                world_x = camera.x + event.pos[0]
                world_y = camera.y + (event.pos[1] - HUD_HEIGHT)
                click_pos = (world_x, world_y)
                if game_state.renaldo_rect.collidepoint(click_pos):
                    game_state.found = True
                    game_state.found_time = time.time()
                    play_sound(sounds, "win")
                else:
                    hit_person = None
                    for person in people:
                        if person.rect.collidepoint(click_pos):
                            hit_person = person
                            break
                    if hit_person and not hit_person.is_renaldo:
                        people.remove(hit_person)
                        explosions.append(Explosion(click_pos[0], click_pos[1], time.time()))
                        play_sound(sounds, "explode")
                    markers.append((click_pos[0], click_pos[1], time.time()))

        keys = pygame.key.get_pressed()
        move_speed = int(260 * dt)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            camera.x -= move_speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            camera.x += move_speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            camera.y -= move_speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            camera.y += move_speed

        clamp_camera(camera, config)

        screen.fill((0, 0, 0))
        screen.blit(scene, (0, HUD_HEIGHT), area=camera.rect())

        for person in people:
            screen.blit(person.sprite, (person.rect.x - camera.x, person.rect.y - camera.y + HUD_HEIGHT))

        now = time.time()
        for mark in markers[:]:
            if now - mark[2] > 1.2:
                markers.remove(mark)
                continue
            screen_x = mark[0] - camera.x
            screen_y = mark[1] - camera.y + HUD_HEIGHT
            pygame.draw.line(screen, (240, 60, 60), (screen_x - 8, screen_y - 8), (screen_x + 8, screen_y + 8), 2)
            pygame.draw.line(screen, (240, 60, 60), (screen_x + 8, screen_y - 8), (screen_x - 8, screen_y + 8), 2)

        draw_explosions(screen, camera, explosions)
        draw_hud(screen, game_state, font, small_font, renaldo_sprite)

        if not game_state.started:
            draw_message(screen, font, "Press SPACE to start hunting!")
        elif game_state.found:
            elapsed = game_state.found_time - game_state.start_time
            draw_message(screen, font, f"You found renaldo in {elapsed:.1f}s! Press R to replay")

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    try:
        run_game()
    except Exception as exc:
        CrashReporter.capture(exc)
        print("A crash occurred. Check crash_report.txt for details.")
        raise
