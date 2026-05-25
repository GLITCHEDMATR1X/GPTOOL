import json
import math
import random
import shutil
import sys
import traceback
from tkinter import Tk
from tkinter import filedialog, simpledialog
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

ASSET_DIR = Path("assets")
GENERATED_DIR = ASSET_DIR / "generated"
REPLACEMENT_DIR = ASSET_DIR / "replacements"
CRASH_DIR = Path("crash_reports")
SAVE_DIR = Path("saves")
CONFIG_PATH = SAVE_DIR / "config.json"

DEFAULT_TILE_TYPES = ["water", "dirt", "grass", "stone", "lava", "snow"]

DEFAULT_COLORS = {
    "water": (50, 110, 200),
    "dirt": (120, 85, 60),
    "grass": (60, 140, 70),
    "stone": (110, 110, 120),
    "lava": (220, 80, 30),
    "snow": (230, 230, 240),
}

TILE_WIDTH = 32
TILE_HEIGHT = 16
CUBE_HEIGHT = 16

MAX_HEIGHT = 100
MIN_HEIGHT = -100

FPS = 60


@dataclass
class TileStyle:
    base_color: Tuple[int, int, int]
    brightness: float = 1.0
    contrast: float = 1.0
    tint: Tuple[int, int, int] = (0, 0, 0)
    darkness: float = 0.0
    texture_seed: int = 0

    def apply(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        r, g, b = color
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        r = int((r - 128) * self.contrast + 128)
        g = int((g - 128) * self.contrast + 128)
        b = int((b - 128) * self.contrast + 128)
        r = int(r - self.darkness * 255)
        g = int(g - self.darkness * 255)
        b = int(b - self.darkness * 255)
        r = max(0, min(255, r + self.tint[0]))
        g = max(0, min(255, g + self.tint[1]))
        b = max(0, min(255, b + self.tint[2]))
        return r, g, b


@dataclass
class Tile:
    height: int
    tile_type: str
    texture_override: Optional[str] = None
    rotation: int = 0


@dataclass
class Player:
    x: float
    y: float
    height: int
    mode: str = "smooth"
    speed: float = 4.0
    swim_speed: float = 2.5
    direction: Tuple[int, int] = (0, 1)
    is_swimming: bool = False


@dataclass
class World:
    width: int
    height: int
    tiles: Dict[Tuple[int, int], Tile] = field(default_factory=dict)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        return self.tiles.get((x, y))

    def set_tile(self, x: int, y: int, tile_type: str, height: int) -> None:
        height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))
        if not self.in_bounds(x, y):
            return
        self.tiles[(x, y)] = Tile(height=height, tile_type=tile_type)

    def clear_tile(self, x: int, y: int) -> None:
        self.tiles.pop((x, y), None)

    def raise_tile(self, x: int, y: int, tile_type: str) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, tile_type, 0)
            return
        if tile.tile_type != tile_type:
            tile.tile_type = tile_type
        tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height + 1))

    def lower_tile(self, x: int, y: int) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, "dirt", -1)
            return
        tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height - 1))

    def paint_tile(self, x: int, y: int, tile_type: str, bump: bool = True) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, tile_type, 0)
            return
        if bump:
            tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height + 1))
        tile.tile_type = tile_type
        tile.texture_override = None
        tile.rotation = 0

    def to_dict(self) -> Dict:
        return {
            "width": self.width,
            "height": self.height,
            "tiles": [
                {
                    "x": x,
                    "y": y,
                    "height": tile.height,
                    "tile_type": tile.tile_type,
                    "texture_override": tile.texture_override,
                    "rotation": tile.rotation,
                }
                for (x, y), tile in self.tiles.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "World":
        world = cls(width=data["width"], height=data["height"])
        for entry in data.get("tiles", []):
            world.set_tile(entry["x"], entry["y"], entry["tile_type"], entry["height"])
            tile = world.get_tile(entry["x"], entry["y"])
            if tile is not None:
                tile.texture_override = entry.get("texture_override")
                tile.rotation = entry.get("rotation", 0)
        return world


@dataclass
class UndoAction:
    positions: List[Tuple[int, int]]
    previous_tiles: List[Optional[Tile]]


class CrashReporter:
    def __init__(self, crash_dir: Path) -> None:
        self.crash_dir = crash_dir
        self.crash_dir.mkdir(parents=True, exist_ok=True)

    def report(self, exc: BaseException) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self.crash_dir / f"crash_{timestamp}.txt"
        with path.open("w", encoding="utf-8") as handle:
            handle.write("Isometric World Engine Crash Report\n")
            handle.write(f"Time (UTC): {timestamp}\n")
            handle.write(f"Python: {sys.version}\n")
            handle.write(f"Platform: {sys.platform}\n")
            handle.write(f"Exception: {repr(exc)}\n\n")
            handle.write("Traceback:\n")
            handle.write("".join(traceback.format_tb(exc.__traceback__)))
        print(f"Crash report saved to {path}")


@dataclass
class Button:
    label: str
    rect: pygame.Rect
    callback: callable
    toggle: bool = False
    toggled: bool = False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, offset: Tuple[int, int] = (0, 0)) -> None:
        rect = self.rect.move(-offset[0], -offset[1])
        base_color = (70, 70, 90)
        if self.toggle and self.toggled:
            base_color = (110, 120, 80)
        pygame.draw.rect(surface, base_color, rect, border_radius=4)
        pygame.draw.rect(surface, (20, 20, 30), rect, 2, border_radius=4)
        text_surface = font.render(self.label, True, (230, 230, 230))
        text_rect = text_surface.get_rect(center=rect.center)
        surface.blit(text_surface, text_rect)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.rect.collidepoint(pos):
            if self.toggle:
                self.toggled = not self.toggled
            self.callback()
            return True
        return False


class AssetManager:
    def __init__(self, styles: Dict[str, TileStyle], tile_types: List[str]) -> None:
        self.styles = styles
        self.tile_types = tile_types
        ASSET_DIR.mkdir(exist_ok=True)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        REPLACEMENT_DIR.mkdir(parents=True, exist_ok=True)

    def generate_tile_texture(self, tile_type: str) -> pygame.Surface:
        style = self.styles[tile_type]
        rng = random.Random(style.texture_seed)
        surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
        base_color = style.apply(style.base_color)
        for y in range(TILE_HEIGHT):
            for x in range(TILE_WIDTH):
                noise = rng.randint(-8, 8)
                color = (
                    max(0, min(255, base_color[0] + noise)),
                    max(0, min(255, base_color[1] + noise)),
                    max(0, min(255, base_color[2] + noise)),
                )
                surface.set_at((x, y), color)
        return surface

    def save_generated_assets(self) -> None:
        for tile_type in self.tile_types:
            surface = self.generate_tile_texture(tile_type)
            pygame.image.save(surface, GENERATED_DIR / f"{tile_type}.png")

    def generate_replacement_placeholders(self) -> None:
        for tile_type in self.tile_types:
            surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            base = DEFAULT_COLORS[tile_type]
            for y in range(TILE_HEIGHT):
                for x in range(TILE_WIDTH):
                    shade = 20 if (x + y) % 2 == 0 else -10
                    color = (
                        max(0, min(255, base[0] + shade)),
                        max(0, min(255, base[1] + shade)),
                        max(0, min(255, base[2] + shade)),
                    )
                    surface.set_at((x, y), color)
            pygame.image.save(surface, REPLACEMENT_DIR / f"{tile_type}_replace.png")


class IsoRenderer:
    def __init__(self, screen: pygame.Surface, styles: Dict[str, TileStyle]) -> None:
        self.screen = screen
        self.styles = styles
        self.cache: Dict[str, pygame.Surface] = {}
        self.texture_cache: Dict[str, pygame.Surface] = {}

    def iso_to_screen(self, x: int, y: int, height: int, offset: Tuple[int, int]) -> Tuple[int, int]:
        screen_x = (x - y) * (TILE_WIDTH // 2) + offset[0]
        screen_y = (x + y) * (TILE_HEIGHT // 2) + offset[1] - height * CUBE_HEIGHT
        return screen_x, screen_y

    @staticmethod
    def point_in_diamond(point: Tuple[int, int], top_left: Tuple[int, int]) -> bool:
        px, py = point
        tx, ty = top_left
        cx = tx + TILE_WIDTH / 2
        cy = ty + TILE_HEIGHT / 2
        dx = abs(px - cx) / (TILE_WIDTH / 2)
        dy = abs(py - cy) / (TILE_HEIGHT / 2)
        return dx + dy <= 1

    def draw_tile(self, tile: Tile, x: int, y: int, offset: Tuple[int, int]) -> None:
        style = self.styles[tile.tile_type]
        override_key = ""
        override_surface = None
        if tile.texture_override:
            override_surface = self._load_override_texture(tile.texture_override, tile.rotation)
            override_key = f"override_{tile.texture_override}_{tile.rotation}"
        key = (
            f"{tile.tile_type}_{style.brightness}_{style.contrast}_{style.darkness}_{style.tint}_{style.texture_seed}_"
            f"{override_key}"
        )
        if key not in self.cache:
            self.cache[key] = self._create_tile_surface(tile.tile_type, override_surface)
        surface = self.cache[key]
        screen_x, screen_y = self.iso_to_screen(x, y, tile.height, offset)
        self.screen.blit(surface, (screen_x, screen_y))

    def _load_override_texture(self, path: str, rotation: int) -> Optional[pygame.Surface]:
        if path in self.texture_cache:
            base = self.texture_cache[path]
        else:
            texture_path = Path(path)
            if not texture_path.exists():
                return None
            base = pygame.image.load(str(texture_path)).convert_alpha()
            base = pygame.transform.smoothscale(base, (TILE_WIDTH, TILE_HEIGHT))
            self.texture_cache[path] = base
        rotated = pygame.transform.rotate(base, rotation)
        return pygame.transform.smoothscale(rotated, (TILE_WIDTH, TILE_HEIGHT))

    def _apply_top_texture(self, target: pygame.Surface, texture: pygame.Surface) -> None:
        top_mask = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
        top = [
            (TILE_WIDTH // 2, 0),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (0, TILE_HEIGHT // 2),
        ]
        pygame.draw.polygon(top_mask, (255, 255, 255, 255), top)
        textured = texture.copy()
        textured.blit(top_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(textured, (0, 0))

    def _create_tile_surface(self, tile_type: str, texture_override: Optional[pygame.Surface] = None) -> pygame.Surface:
        style = self.styles[tile_type]
        top_color = style.apply(style.base_color)
        left_color = style.apply(tuple(max(0, c - 30) for c in style.base_color))
        right_color = style.apply(tuple(max(0, c - 15) for c in style.base_color))
        tile_surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT + CUBE_HEIGHT), pygame.SRCALPHA)
        top = [
            (TILE_WIDTH // 2, 0),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (0, TILE_HEIGHT // 2),
        ]
        left = [
            (0, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1 + CUBE_HEIGHT),
            (0, TILE_HEIGHT // 2 + CUBE_HEIGHT),
        ]
        right = [
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2 + CUBE_HEIGHT),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1 + CUBE_HEIGHT),
        ]
        pygame.draw.polygon(tile_surface, top_color, top)
        if texture_override is not None:
            self._apply_top_texture(tile_surface, texture_override)
        pygame.draw.polygon(tile_surface, left_color, left)
        pygame.draw.polygon(tile_surface, right_color, right)
        return tile_surface

    def draw_vertical_face(
        self,
        x: int,
        y: int,
        height: int,
        neighbor_height: int,
        tile_type: str,
        offset: Tuple[int, int],
    ) -> None:
        if neighbor_height >= height:
            return
        style = self.styles[tile_type]
        face_color = style.apply(tuple(max(0, c - 40) for c in style.base_color))
        screen_x, screen_y = self.iso_to_screen(x, y, height, offset)
        diff = height - neighbor_height
        face_height = diff * CUBE_HEIGHT
        left_face = [
            (screen_x, screen_y + TILE_HEIGHT // 2),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT + face_height),
            (screen_x, screen_y + TILE_HEIGHT // 2 + face_height),
        ]
        right_face = [
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT),
            (screen_x + TILE_WIDTH, screen_y + TILE_HEIGHT // 2),
            (screen_x + TILE_WIDTH, screen_y + TILE_HEIGHT // 2 + face_height),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT + face_height),
        ]
        pygame.draw.polygon(self.screen, face_color, left_face)
        pygame.draw.polygon(self.screen, face_color, right_face)


class IsoApp:
    def __init__(self, world_size: Tuple[int, int]) -> None:
        pygame.init()
        pygame.display.set_caption("Isometric World Engine")
        self.screen = pygame.display.set_mode((1280, 720))
        self.clock = pygame.time.Clock()
        self.ui_font = pygame.font.SysFont("consolas", 16)
        self.info_font = pygame.font.SysFont("consolas", 16)
        self.tile_types = list(DEFAULT_TILE_TYPES)
        self.styles = {
            tile_type: TileStyle(base_color=DEFAULT_COLORS[tile_type], texture_seed=i)
            for i, tile_type in enumerate(self.tile_types)
        }
        self.asset_manager = AssetManager(self.styles, self.tile_types)
        self.world = World(width=world_size[0], height=world_size[1])
        self.renderer = IsoRenderer(self.screen, self.styles)
        self.offset = (self.screen.get_width() // 2, 120)
        self.selected_tile_type = "grass"
        self.current_tool = "raise"
        self.brush_size = 1
        self.undo_stack: List[UndoAction] = []
        self.redo_stack: List[UndoAction] = []
        self.show_help = False
        self.buttons: List[Button] = []
        self.tool_buttons: Dict[str, Button] = {}
        self.tile_buttons: Dict[str, Button] = {}
        self.last_paint_time = 0
        self.drag_interval_ms = 120
        self.ui_rect = pygame.Rect(self.screen.get_width() - 260, 10, 250, self.screen.get_height() - 20)
        self.info_rect = pygame.Rect(10, 10, 260, 170)
        self.replacement_images: List[Path] = []
        self.replacement_index = 0
        self.replacement_rotation = 0
        self.world_seed = random.randint(0, 999999)
        self.last_directory = self.load_last_directory()
        self.last_image_directory = self.load_last_image_directory()
        self.replacement_order = self.load_replacement_order()
        self.panel_scroll = 0
        self.texture_scroll = 0
        self.texture_area_rect = pygame.Rect(self.ui_rect.x + 10, self.ui_rect.bottom - 250, self.ui_rect.width - 20, 240)
        self.texture_scroll_speed = 24
        self.texture_item_height = 36
        self.texture_sidebar_width = 8
        self.player_mode = False
        self.player: Optional[Player] = None
        self.texture_thumbs: Dict[str, pygame.Surface] = {}
        self.build_ui()
        self.load_replacement_images()
        self.generate_world()

    def build_ui(self) -> None:
        self.buttons.clear()
        self.tool_buttons.clear()
        self.tile_buttons.clear()
        x = self.ui_rect.x + 10
        y = self.ui_rect.y + 10
        button_w = self.ui_rect.width - 20
        button_h = 26
        gap = 6

        def add_button(label: str, callback: callable, toggle: bool = False, toggled: bool = False) -> Button:
            nonlocal y
            rect = pygame.Rect(x, y, button_w, button_h)
            button = Button(label=label, rect=rect, callback=callback, toggle=toggle, toggled=toggled)
            self.buttons.append(button)
            y += button_h + gap
            return button

        add_button("World: Regenerate", self.generate_world)
        add_button("World: Randomize", self.randomize_world)
        add_button("World: Smooth Heights", self.smooth_heights)
        add_button("World: Flatten", self.flatten_world)
        add_button("World: Center Camera", self.center_camera)

        y += 6
        add_button("Save World", self.save_world_dialog)
        add_button("Load World", self.load_world_dialog)
        add_button("Export PNG", self.export_world_dialog)
        add_button("Generate Assets", self.asset_manager.save_generated_assets)
        add_button("Create Tile Type", self.create_tile_type)

        y += 10
        tool_buttons = [
            ("Tool: Raise", "raise"),
            ("Tool: Lower", "lower"),
            ("Tool: Paint", "paint"),
            ("Tool: Erase", "erase"),
            ("Tool: Pick", "pick"),
            ("Tool: Replace Texture", "replace_texture"),
            ("Tool: Remove Texture", "remove_texture"),
        ]
        for label, tool in tool_buttons:
            button = add_button(label, lambda t=tool: self.set_tool(t), toggle=True)
            self.tool_buttons[tool] = button

        add_button("Brush: Smaller", self.decrease_brush)
        add_button("Brush: Larger", self.increase_brush)

        y += 10
        for tile_type in self.tile_types:
            button = add_button(f"Tile: {tile_type.title()}", lambda t=tile_type: self.set_tile_type(t), toggle=True)
            self.tile_buttons[tile_type] = button

        y += 10
        add_button("Style: Brightness +", lambda: self.adjust_style(self.selected_tile_type, brightness=0.1))
        add_button("Style: Brightness -", lambda: self.adjust_style(self.selected_tile_type, brightness=-0.1))
        add_button("Style: Contrast +", lambda: self.adjust_style(self.selected_tile_type, contrast=0.1))
        add_button("Style: Contrast -", lambda: self.adjust_style(self.selected_tile_type, contrast=-0.1))
        add_button("Style: Darker", lambda: self.adjust_style(self.selected_tile_type, darkness=0.05))
        add_button("Style: Lighter", lambda: self.adjust_style(self.selected_tile_type, darkness=-0.05))
        add_button("Style: Tint +R", lambda: self.shift_tint(self.selected_tile_type, 6, 0, 0))
        add_button("Style: Tint -R", lambda: self.shift_tint(self.selected_tile_type, -6, 0, 0))
        add_button("Style: Tint +G", lambda: self.shift_tint(self.selected_tile_type, 0, 6, 0))
        add_button("Style: Tint -G", lambda: self.shift_tint(self.selected_tile_type, 0, -6, 0))
        add_button("Style: Tint +B", lambda: self.shift_tint(self.selected_tile_type, 0, 0, 6))
        add_button("Style: Tint -B", lambda: self.shift_tint(self.selected_tile_type, 0, 0, -6))
        add_button("Style: Shuffle Texture", self.shuffle_texture)
        add_button("Style: Reset", self.reset_style)

        y += 10
        add_button("Texture: Prev", self.prev_replacement)
        add_button("Texture: Next", self.next_replacement)
        add_button("Texture: Load Image", self.load_replacement_image)
        add_button("Texture: Rotate 90", self.rotate_replacement)
        add_button("Texture: Clear Tile", lambda: self.set_tool("remove_texture"))
        add_button("Texture: Regenerate", self.asset_manager.generate_replacement_placeholders)

        y += 10
        add_button("Toggle Player Mode", self.toggle_player_mode, toggle=True)
        add_button("Player Move: Smooth", lambda: self.set_player_mode("smooth"), toggle=True)
        add_button("Player Move: Grid", lambda: self.set_player_mode("grid"), toggle=True)
        add_button("Player: Respawn", self.spawn_player)

        y += 10
        add_button("Undo", lambda: self.apply_undo(self.undo_stack, self.redo_stack))
        add_button("Redo", lambda: self.apply_undo(self.redo_stack, self.undo_stack))
        add_button("Toggle Help", self.toggle_help)

        self.refresh_button_states()

    def refresh_button_states(self) -> None:
        for tool, button in self.tool_buttons.items():
            button.toggled = tool == self.current_tool
        for tile_type, button in self.tile_buttons.items():
            button.toggled = tile_type == self.selected_tile_type
        for button in self.buttons:
            if button.label == "Toggle Player Mode":
                button.toggled = self.player_mode
            if button.label == "Player Move: Smooth":
                button.toggled = self.player is not None and self.player.mode == "smooth"
            if button.label == "Player Move: Grid":
                button.toggled = self.player is not None and self.player.mode == "grid"

    def set_tool(self, tool: str) -> None:
        self.current_tool = tool
        self.refresh_button_states()

    def set_tile_type(self, tile_type: str) -> None:
        self.selected_tile_type = tile_type
        self.refresh_button_states()

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def center_camera(self) -> None:
        self.offset = (self.screen.get_width() // 2, 120)

    def increase_brush(self) -> None:
        self.brush_size = min(6, self.brush_size + 1)

    def decrease_brush(self) -> None:
        self.brush_size = max(1, self.brush_size - 1)

    def shuffle_texture(self) -> None:
        style = self.styles[self.selected_tile_type]
        style.texture_seed = random.randint(0, 9999)
        self.renderer.cache.clear()

    def reset_style(self) -> None:
        self.styles[self.selected_tile_type] = TileStyle(
            base_color=DEFAULT_COLORS[self.selected_tile_type],
            texture_seed=self.tile_types.index(self.selected_tile_type),
        )
        self.renderer.styles = self.styles
        self.renderer.cache.clear()

    def toggle_player_mode(self) -> None:
        self.player_mode = not self.player_mode
        if self.player_mode and self.player is None:
            self.spawn_player()
        self.refresh_button_states()

    def set_player_mode(self, mode: str) -> None:
        if self.player is None:
            self.spawn_player()
        if self.player:
            self.player.mode = mode
        self.refresh_button_states()

    def load_last_directory(self) -> Path:
        SAVE_DIR.mkdir(exist_ok=True)
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                path = data.get("last_directory")
                if path:
                    return Path(path)
            except json.JSONDecodeError:
                pass
        return Path.cwd()

    def load_last_image_directory(self) -> Path:
        SAVE_DIR.mkdir(exist_ok=True)
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                path = data.get("last_image_directory")
                if path:
                    return Path(path)
            except json.JSONDecodeError:
                pass
        return Path.cwd()

    def save_last_directory(self, path: Path) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        data = {
            "last_directory": str(path),
            "last_image_directory": str(self.last_image_directory),
            "replacement_order": self.replacement_order,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.last_directory = path

    def save_last_image_directory(self, path: Path) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        data = {
            "last_directory": str(self.last_directory),
            "last_image_directory": str(path),
            "replacement_order": self.replacement_order,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.last_image_directory = path

    def load_replacement_order(self) -> List[str]:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                order = data.get("replacement_order")
                if isinstance(order, list):
                    return order
            except json.JSONDecodeError:
                pass
        return []

    def save_replacement_order(self) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        data = {
            "last_directory": str(self.last_directory),
            "last_image_directory": str(self.last_image_directory),
            "replacement_order": self.replacement_order,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_replacement_images(self) -> None:
        REPLACEMENT_DIR.mkdir(parents=True, exist_ok=True)
        images = list(REPLACEMENT_DIR.glob("*.png"))
        if not images:
            self.asset_manager.generate_replacement_placeholders()
            images = list(REPLACEMENT_DIR.glob("*.png"))
        if self.replacement_order:
            ordered = []
            remaining = {str(path): path for path in images}
            for entry in self.replacement_order:
                path = remaining.pop(entry, None)
                if path:
                    ordered.append(path)
            ordered.extend(sorted(remaining.values()))
            self.replacement_images = ordered
        else:
            self.replacement_images = sorted(images)
        self.replacement_index = 0
        self.texture_thumbs.clear()

    def current_replacement(self) -> Optional[Path]:
        if not self.replacement_images:
            return None
        return self.replacement_images[self.replacement_index % len(self.replacement_images)]

    def current_replacement_name(self) -> str:
        replacement = self.current_replacement()
        if replacement is None:
            return "None"
        return replacement.name

    def load_replacement_image(self) -> None:
        path = self.open_file_dialog("Select replacement image", [("PNG files", "*.png")], use_image_dir=True)
        if path is None:
            return
        destination = REPLACEMENT_DIR / path.name
        if destination.exists():
            destination = REPLACEMENT_DIR / f"{path.stem}_{random.randint(0, 9999)}{path.suffix}"
        shutil.copy2(path, destination)
        self.replacement_images.append(destination)
        self.replacement_order = [str(p) for p in self.replacement_images]
        self.save_replacement_order()
        self.replacement_index = self.replacement_images.index(destination)

    def open_file_dialog(
        self,
        title: str,
        filetypes: List[Tuple[str, str]],
        use_image_dir: bool = False,
    ) -> Optional[Path]:
        root = Tk()
        root.withdraw()
        initial_dir = self.last_image_directory if use_image_dir else self.last_directory
        path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=initial_dir,
        )
        root.destroy()
        if not path:
            return None
        chosen = Path(path)
        if chosen.parent:
            if use_image_dir:
                self.save_last_image_directory(chosen.parent)
            else:
                self.save_last_directory(chosen.parent)
        return chosen

    def save_file_dialog(self, title: str, default_name: str, filetypes: List[Tuple[str, str]]) -> Optional[Path]:
        root = Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=filetypes[0][1],
            filetypes=filetypes,
            initialdir=self.last_directory,
            initialfile=default_name,
        )
        root.destroy()
        if not path:
            return None
        chosen = Path(path)
        if chosen.parent:
            self.save_last_directory(chosen.parent)
        return chosen

    def save_world_dialog(self) -> None:
        path = self.save_file_dialog("Save world", "world.json", [("JSON files", "*.json")])
        if path is None:
            return
        self.save_world(path)

    def load_world_dialog(self) -> None:
        path = self.open_file_dialog("Load world", [("JSON files", "*.json")])
        if path is None:
            return
        self.load_world(path)

    def export_world_dialog(self) -> None:
        path = self.save_file_dialog("Export PNG", "world_export.png", [("PNG files", "*.png")])
        if path is None:
            return
        self.export_for_pygame(path)

    def create_tile_type(self) -> None:
        root = Tk()
        root.withdraw()
        name = simpledialog.askstring("New Tile", "Tile name:", parent=root)
        root.destroy()
        if not name:
            return
        sanitized = name.strip().lower().replace(" ", "_")
        if not sanitized or sanitized in self.tile_types:
            return
        image_path = self.open_file_dialog(
            "Select tile image (optional)",
            [("PNG files", "*.png")],
            use_image_dir=True,
        )
        rotation = 0
        if image_path is not None:
            root = Tk()
            root.withdraw()
            rotation = simpledialog.askinteger(
                "Rotate Tile Image",
                "Rotation (0, 90, 180, 270):",
                initialvalue=0,
                minvalue=0,
                maxvalue=270,
                parent=root,
            )
            root.destroy()
            rotation = rotation or 0
            rotation = int(round(rotation / 90) * 90) % 360
        color = (
            random.randint(40, 220),
            random.randint(40, 220),
            random.randint(40, 220),
        )
        if image_path is not None:
            image_surface = pygame.image.load(str(image_path)).convert_alpha()
            image_surface = pygame.transform.rotate(image_surface, rotation)
            image_surface = pygame.transform.smoothscale(image_surface, (TILE_WIDTH, TILE_HEIGHT))
            avg_color = self.average_color(image_surface)
            color = avg_color
            destination = REPLACEMENT_DIR / f"{sanitized}{image_path.suffix}"
            pygame.image.save(image_surface, destination)
            self.replacement_images.append(destination)
            self.replacement_order = [str(p) for p in self.replacement_images]
            self.save_replacement_order()
            if destination in self.replacement_images:
                self.replacement_index = self.replacement_images.index(destination)
        self.tile_types.append(sanitized)
        DEFAULT_COLORS[sanitized] = color
        self.styles[sanitized] = TileStyle(base_color=color, texture_seed=len(self.tile_types))
        self.asset_manager.tile_types = self.tile_types
        self.build_ui()
        self.set_tile_type(sanitized)

    def average_color(self, surface: pygame.Surface) -> Tuple[int, int, int]:
        width, height = surface.get_size()
        total_r = total_g = total_b = count = 0
        for y in range(height):
            for x in range(width):
                r, g, b, a = surface.get_at((x, y))
                if a == 0:
                    continue
                total_r += r
                total_g += g
                total_b += b
                count += 1
        if count == 0:
            return (120, 120, 120)
        return (total_r // count, total_g // count, total_b // count)

    def spawn_player(self) -> None:
        center_x = self.world.width // 2
        center_y = self.world.height // 2
        tile = self.world.get_tile(center_x, center_y)
        height = tile.height if tile else 0
        self.player = Player(x=float(center_x), y=float(center_y), height=height)
        self.refresh_button_states()

    def update_player(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        if not self.player_mode or self.player is None:
            return
        player = self.player
        move_x = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        move_y = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])
        if move_x != 0 or move_y != 0:
            player.direction = (move_x, move_y)
        current_tile = self.world.get_tile(int(round(player.x)), int(round(player.y)))
        player.is_swimming = current_tile is not None and current_tile.tile_type == "water"
        speed = player.swim_speed if player.is_swimming else player.speed
        if player.mode == "smooth":
            target_x = player.x + move_x * speed * dt
            target_y = player.y + move_y * speed * dt
            self.try_move_player(target_x, target_y)
        else:
            if move_x != 0 or move_y != 0:
                target_x = player.x + move_x
                target_y = player.y + move_y
                self.try_move_player(target_x, target_y)

    def try_move_player(self, target_x: float, target_y: float) -> None:
        if self.player is None:
            return
        next_x = int(round(target_x))
        next_y = int(round(target_y))
        if not self.world.in_bounds(next_x, next_y):
            return
        next_tile = self.world.get_tile(next_x, next_y)
        current_tile = self.world.get_tile(int(round(self.player.x)), int(round(self.player.y)))
        next_height = next_tile.height if next_tile else 0
        current_height = current_tile.height if current_tile else 0
        if next_height - current_height > 1:
            return
        self.player.x = target_x
        self.player.y = target_y
        self.player.height = next_height

    def jump_player(self) -> None:
        if self.player is None:
            return
        dx, dy = self.player.direction
        if dx == 0 and dy == 0:
            return
        target_x = int(round(self.player.x + dx))
        target_y = int(round(self.player.y + dy))
        if not self.world.in_bounds(target_x, target_y):
            return
        next_tile = self.world.get_tile(target_x, target_y)
        current_tile = self.world.get_tile(int(round(self.player.x)), int(round(self.player.y)))
        next_height = next_tile.height if next_tile else 0
        current_height = current_tile.height if current_tile else 0
        if next_height - current_height <= 1:
            self.player.x = float(target_x)
            self.player.y = float(target_y)
            self.player.height = next_height

    def mine_ahead(self) -> None:
        if self.player is None:
            return
        dx, dy = self.player.direction
        target_x = int(round(self.player.x + dx))
        target_y = int(round(self.player.y + dy))
        tile = self.world.get_tile(target_x, target_y)
        if tile is None:
            return
        tile.height -= 1
        if tile.height < MIN_HEIGHT:
            self.world.clear_tile(target_x, target_y)

    def next_replacement(self) -> None:
        if self.replacement_images:
            self.replacement_index = (self.replacement_index + 1) % len(self.replacement_images)

    def prev_replacement(self) -> None:
        if self.replacement_images:
            self.replacement_index = (self.replacement_index - 1) % len(self.replacement_images)

    def rotate_replacement(self) -> None:
        self.replacement_rotation = (self.replacement_rotation + 90) % 360

    def apply_texture_override(self, x: int, y: int) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            self.world.set_tile(x, y, self.selected_tile_type, 0)
            tile = self.world.get_tile(x, y)
        if tile is None:
            return
        replacement = self.current_replacement()
        if replacement is None:
            return
        tile.texture_override = str(replacement)
        tile.rotation = self.replacement_rotation

    def remove_texture_override(self, x: int, y: int) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            return
        tile.texture_override = None
        tile.rotation = 0

    def generate_world(self) -> None:
        self.world_seed = random.randint(0, 999999)
        self.world.tiles.clear()
        rng = random.Random(self.world_seed)
        for y in range(self.world.height):
            for x in range(self.world.width):
                base_height = self.natural_height(x, y, self.world_seed)
                tile_type = self.pick_tile_type(base_height, rng)
                self.world.set_tile(x, y, tile_type, base_height)
        if self.player_mode:
            self.spawn_player()

    def randomize_world(self) -> None:
        seed = random.randint(0, 999999)
        rng = random.Random(seed)
        for y in range(self.world.height):
            for x in range(self.world.width):
                height = self.natural_height(x, y, seed)
                tile_type = self.pick_tile_type(height, rng)
                self.world.set_tile(x, y, tile_type, height)
        if self.player_mode:
            self.spawn_player()

    def natural_height(self, x: int, y: int, seed: int) -> int:
        rng = random.Random(seed)
        freq_a = rng.uniform(0.12, 0.22)
        freq_b = rng.uniform(0.08, 0.16)
        offset_x = rng.uniform(-10, 10)
        offset_y = rng.uniform(-10, 10)
        base = math.sin((x + offset_x) * freq_a) * 2 + math.cos((y + offset_y) * freq_b) * 2
        ridge = math.sin((x + y) * (freq_a * 0.6)) * 1.5
        noise = math.sin((x * 0.9 + seed) * 0.2) + math.cos((y * 0.7 + seed) * 0.3)
        height = base + ridge + noise
        return int(round(height))

    def pick_tile_type(self, height: int, rng: random.Random) -> str:
        if height <= -1:
            return "water"
        if height <= 1:
            return rng.choice(["grass", "dirt"])
        if height <= 3:
            return rng.choice(["grass", "stone"])
        return rng.choice(["stone", "snow"])
    def smooth_heights(self) -> None:
        positions = [(x, y) for y in range(self.world.height) for x in range(self.world.width)]
        self.record_undo(positions)
        new_tiles: Dict[Tuple[int, int], Tile] = {}
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            neighbors = [
                self.world.get_tile(nx, ny)
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
            ]
            heights = [tile.height] + [n.height for n in neighbors if n is not None]
            avg_height = int(round(sum(heights) / len(heights)))
            new_tiles[(x, y)] = Tile(avg_height, tile.tile_type)
        self.world.tiles.update(new_tiles)

    def flatten_world(self) -> None:
        positions = [(x, y) for y in range(self.world.height) for x in range(self.world.width)]
        self.record_undo(positions)
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                self.world.set_tile(x, y, self.selected_tile_type, 0)
            else:
                tile.height = 0
                tile.tile_type = self.selected_tile_type

    def save_world(self, path: Path) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        data = self.world.to_dict()
        data["tile_types"] = self.tile_types
        data["styles"] = {
            tile_type: {
                "base_color": self.styles[tile_type].base_color,
                "brightness": self.styles[tile_type].brightness,
                "contrast": self.styles[tile_type].contrast,
                "tint": self.styles[tile_type].tint,
                "darkness": self.styles[tile_type].darkness,
                "texture_seed": self.styles[tile_type].texture_seed,
            }
            for tile_type in self.tile_types
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def load_world(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        tile_types = data.get("tile_types")
        if tile_types:
            self.tile_types = list(tile_types)
        styles_data = data.get("styles", {})
        for tile_type in self.tile_types:
            if tile_type in styles_data:
                style = styles_data[tile_type]
                self.styles[tile_type] = TileStyle(
                    base_color=tuple(style.get("base_color", DEFAULT_COLORS.get(tile_type, (120, 120, 120)))),
                    brightness=style.get("brightness", 1.0),
                    contrast=style.get("contrast", 1.0),
                    tint=tuple(style.get("tint", (0, 0, 0))),
                    darkness=style.get("darkness", 0.0),
                    texture_seed=style.get("texture_seed", 0),
                )
        self.world = World.from_dict(data)
        self.asset_manager.tile_types = self.tile_types
        self.renderer = IsoRenderer(self.screen, self.styles)
        self.build_ui()

    def export_for_pygame(self, path: Path) -> None:
        surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        original_screen = self.screen
        self.screen = surface
        self.render()
        pygame.image.save(surface, path)
        self.screen = original_screen

    def get_world_coords(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        return self.get_tile_at_screen(mouse_pos)

    def get_tile_at_screen(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        best_tile: Optional[Tuple[int, int]] = None
        best_height = -10**6
        best_screen_y = 10**6
        for (x, y), tile in self.world.tiles.items():
            screen_x, screen_y = self.renderer.iso_to_screen(x, y, tile.height, self.offset)
            if not IsoRenderer.point_in_diamond(mouse_pos, (screen_x, screen_y)):
                continue
            if tile.height > best_height or (tile.height == best_height and screen_y < best_screen_y):
                best_tile = (x, y)
                best_height = tile.height
                best_screen_y = screen_y
        return best_tile

    def record_undo(self, positions: List[Tuple[int, int]]) -> None:
        previous_tiles = [self.world.get_tile(x, y) for x, y in positions]
        copied_tiles: List[Optional[Tile]] = []
        for tile in previous_tiles:
            if tile is None:
                copied_tiles.append(None)
            else:
                copied_tiles.append(Tile(tile.height, tile.tile_type))
        self.undo_stack.append(UndoAction(positions, copied_tiles))
        self.redo_stack.clear()

    def apply_undo(self, stack_from: List[UndoAction], stack_to: List[UndoAction]) -> None:
        if not stack_from:
            return
        action = stack_from.pop()
        current_tiles = [self.world.get_tile(x, y) for x, y in action.positions]
        current_copy: List[Optional[Tile]] = []
        for tile in current_tiles:
            if tile is None:
                current_copy.append(None)
            else:
                current_copy.append(Tile(tile.height, tile.tile_type))
        for (x, y), tile in zip(action.positions, action.previous_tiles):
            if tile is None:
                self.world.clear_tile(x, y)
            else:
                self.world.set_tile(x, y, tile.tile_type, tile.height)
        stack_to.append(UndoAction(action.positions, current_copy))

    def paint_at(self, grid_pos: Tuple[int, int], add_action: bool = True) -> None:
        x, y = grid_pos
        positions = []
        for dy in range(-self.brush_size + 1, self.brush_size):
            for dx in range(-self.brush_size + 1, self.brush_size):
                tx, ty = x + dx, y + dy
                if self.world.in_bounds(tx, ty):
                    positions.append((tx, ty))
        self.record_undo(positions)
        tool = self.current_tool
        if not add_action:
            tool = self.inverse_tool(tool)
        for tx, ty in positions:
            if tool == "raise":
                self.world.raise_tile(tx, ty, self.selected_tile_type)
            elif tool == "lower":
                self.world.lower_tile(tx, ty)
            elif tool == "paint":
                self.world.paint_tile(tx, ty, self.selected_tile_type, bump=False)
            elif tool == "erase":
                self.world.clear_tile(tx, ty)
            elif tool == "pick":
                picked = self.world.get_tile(tx, ty)
                if picked:
                    self.set_tile_type(picked.tile_type)
                return
            elif tool == "replace_texture":
                self.apply_texture_override(tx, ty)
            elif tool == "remove_texture":
                self.remove_texture_override(tx, ty)

    def inverse_tool(self, tool: str) -> str:
        if tool == "raise":
            return "lower"
        if tool == "lower":
            return "raise"
        if tool == "paint":
            return "erase"
        if tool == "erase":
            return "paint"
        if tool == "replace_texture":
            return "remove_texture"
        if tool == "remove_texture":
            return "replace_texture"
        return tool

    def adjust_style(self, tile_type: str, brightness: float = 0.0, contrast: float = 0.0, darkness: float = 0.0) -> None:
        style = self.styles[tile_type]
        style.brightness = max(0.2, min(2.0, style.brightness + brightness))
        style.contrast = max(0.5, min(2.0, style.contrast + contrast))
        style.darkness = max(0.0, min(0.8, style.darkness + darkness))
        self.renderer.cache.clear()

    def shift_tint(self, tile_type: str, r: int, g: int, b: int) -> None:
        style = self.styles[tile_type]
        tint = (
            max(-80, min(80, style.tint[0] + r)),
            max(-80, min(80, style.tint[1] + g)),
            max(-80, min(80, style.tint[2] + b)),
        )
        style.tint = tint
        self.renderer.cache.clear()

    def handle_input(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_h:
                    self.toggle_help()
                if event.key == pygame.K_p:
                    self.toggle_player_mode()
                if event.key == pygame.K_SPACE:
                    self.jump_player()
                if event.key == pygame.K_m:
                    self.mine_ahead()
                if event.key == pygame.K_u:
                    self.apply_undo(self.undo_stack, self.redo_stack)
                if event.key == pygame.K_y:
                    self.apply_undo(self.redo_stack, self.undo_stack)
                if event.key == pygame.K_r:
                    self.randomize_world()
                if event.key == pygame.K_g:
                    self.generate_world()
                if event.key == pygame.K_s:
                    self.save_world(SAVE_DIR / "world.json")
                if event.key == pygame.K_l:
                    self.load_world(SAVE_DIR / "world.json")
                if event.key == pygame.K_e:
                    self.export_for_pygame(SAVE_DIR / "world_export.png")
                if event.key == pygame.K_F5:
                    self.asset_manager.save_generated_assets()
                if pygame.K_1 <= event.key <= pygame.K_6:
                    index = event.key - pygame.K_1
                    if index < len(self.tile_types):
                        self.set_tile_type(self.tile_types[index])
                if event.key == pygame.K_EQUALS:
                    self.adjust_style(self.selected_tile_type, brightness=0.1)
                if event.key == pygame.K_MINUS:
                    self.adjust_style(self.selected_tile_type, brightness=-0.1)
                if event.key == pygame.K_RIGHTBRACKET:
                    self.adjust_style(self.selected_tile_type, contrast=0.1)
                if event.key == pygame.K_LEFTBRACKET:
                    self.adjust_style(self.selected_tile_type, contrast=-0.1)
                if event.key == pygame.K_SEMICOLON:
                    self.adjust_style(self.selected_tile_type, darkness=0.05)
                if event.key == pygame.K_QUOTE:
                    self.adjust_style(self.selected_tile_type, darkness=-0.05)
                if event.key == pygame.K_COMMA:
                    self.shift_tint(self.selected_tile_type, -5, 0, 0)
                if event.key == pygame.K_PERIOD:
                    self.shift_tint(self.selected_tile_type, 5, 0, 0)
                if event.key == pygame.K_SLASH:
                    self.shift_tint(self.selected_tile_type, 0, 5, 0)
                if event.key == pygame.K_BACKSLASH:
                    self.shift_tint(self.selected_tile_type, 0, 0, 5)
                if not self.player_mode:
                    if event.key == pygame.K_RIGHT:
                        self.offset = (self.offset[0] + 20, self.offset[1])
                    if event.key == pygame.K_LEFT:
                        self.offset = (self.offset[0] - 20, self.offset[1])
                    if event.key == pygame.K_UP:
                        self.offset = (self.offset[0], self.offset[1] - 20)
                    if event.key == pygame.K_DOWN:
                        self.offset = (self.offset[0], self.offset[1] + 20)
                if event.key == pygame.K_9:
                    self.decrease_brush()
                if event.key == pygame.K_0:
                    self.increase_brush()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                if self.handle_ui_click(event.pos):
                    continue
                if not self.player_mode:
                    grid_pos = self.get_world_coords(event.pos)
                    if grid_pos:
                        self.paint_at(grid_pos, add_action=event.button == 1)
            if event.type == pygame.MOUSEWHEEL:
                mouse_pos = pygame.mouse.get_pos()
                if self.ui_rect.collidepoint(mouse_pos):
                    if self.texture_area_rect.collidepoint(mouse_pos):
                        self.scroll_texture_list(-event.y * self.texture_scroll_speed)
                    else:
                        self.scroll_panel(-event.y * self.texture_scroll_speed)
        mouse_pressed = pygame.mouse.get_pressed()
        now = pygame.time.get_ticks()
        if mouse_pressed[0] or mouse_pressed[2]:
            if now - self.last_paint_time > self.drag_interval_ms:
                self.last_paint_time = now
                if not self.is_over_ui(pygame.mouse.get_pos()) and not self.player_mode:
                    grid_pos = self.get_world_coords(pygame.mouse.get_pos())
                    if grid_pos:
                        self.paint_at(grid_pos, add_action=mouse_pressed[0])
        return True

    def handle_ui_click(self, pos: Tuple[int, int]) -> bool:
        if not self.is_over_ui(pos):
            return False
        if self.texture_area_rect.collidepoint(pos):
            if self.handle_texture_click(pos):
                return True
        for button in self.buttons:
            if self.handle_button_click(button, pos):
                self.refresh_button_states()
                return True
        return True

    def handle_button_click(self, button: Button, pos: Tuple[int, int]) -> bool:
        adjusted = button.rect.move(0, -self.panel_scroll)
        if adjusted.collidepoint(pos):
            if button.toggle:
                button.toggled = not button.toggled
            button.callback()
            return True
        return False

    def scroll_panel(self, delta: int) -> None:
        max_scroll = max(0, self.total_button_height() - (self.ui_rect.height - 20))
        self.panel_scroll = max(0, min(max_scroll, self.panel_scroll + delta))

    def total_button_height(self) -> int:
        if not self.buttons:
            return 0
        top = min(button.rect.top for button in self.buttons)
        bottom = max(button.rect.bottom for button in self.buttons)
        return bottom - top + 10

    def scroll_texture_list(self, delta: int) -> None:
        total_height = len(self.replacement_images) * self.texture_item_height
        visible = self.texture_area_rect.height - 22
        max_scroll = max(0, total_height - visible)
        self.texture_scroll = max(0, min(max_scroll, self.texture_scroll + delta))

    def handle_texture_click(self, pos: Tuple[int, int]) -> bool:
        local_y = pos[1] - self.texture_area_rect.top + self.texture_scroll - 22
        if local_y < 0:
            return True
        index = local_y // self.texture_item_height
        if 0 <= index < len(self.replacement_images):
            self.replacement_index = int(index)
            return True
        return False

    def is_over_ui(self, pos: Tuple[int, int]) -> bool:
        return self.ui_rect.collidepoint(pos)

    def render_grid(self) -> None:
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if tile is None:
                    continue
                neighbor_heights = [
                    self.world.get_tile(x - 1, y),
                    self.world.get_tile(x + 1, y),
                    self.world.get_tile(x, y - 1),
                    self.world.get_tile(x, y + 1),
                ]
                for neighbor in neighbor_heights:
                    neighbor_height = neighbor.height if neighbor else min(tile.height, 0)
                    self.renderer.draw_vertical_face(
                        x,
                        y,
                        tile.height,
                        neighbor_height,
                        tile.tile_type,
                        self.offset,
                    )
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if tile:
                    self.renderer.draw_tile(tile, x, y, self.offset)

    def draw_help(self) -> None:
        if not self.show_help:
            return
        lines = [
            "Controls:",
            "Left Click: apply tool (add) | Right Click: opposite (subtract)",
            "1-6: select tile | 9/0: brush size",
            "=: brightness up | -: brightness down",
            "[: contrast down | ]: contrast up",
            ";: darker | ': lighter",
            ",/.\\: tint adjustments",
            "Texture mode: use Replace Texture tool",
            "Player: P toggle, WASD/Arrows move, Space jump, M mine",
            "U/Y: undo/redo",
            "R: randomize | G: regenerate",
            "S/L: save/load | E: export image",
            "F5: regenerate assets",
            "Arrows: pan camera | H: toggle help",
        ]
        padding = 8
        rect_height = len(lines) * 20 + padding * 2
        overlay = pygame.Surface((420, rect_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        for i, line in enumerate(lines):
            text_surface = self.ui_font.render(line, True, (240, 240, 240))
            overlay.blit(text_surface, (padding, padding + i * 20))
        y_offset = self.info_rect.bottom + 10
        self.screen.blit(overlay, (10, y_offset))

    def draw_info(self) -> None:
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 30, 220))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        header = self.info_font.render("Status", True, (230, 230, 230))
        panel.blit(header, (10, 8))
        status = [
            f"Tool: {self.current_tool.title()}",
            f"Tile: {self.selected_tile_type.title()}",
            f"Brush: {self.brush_size}x{self.brush_size}",
            f"Texture: {self.current_replacement_name()}",
            f"Rotation: {self.replacement_rotation}°",
            f"Player: {'On' if self.player_mode else 'Off'}",
            f"Move: {self.player.mode.title() if self.player else 'N/A'}",
        ]
        for i, line in enumerate(status):
            text = self.info_font.render(line, True, (200, 200, 210))
            panel.blit(text, (10, 28 + i * 18))
        self.screen.blit(panel, self.info_rect.topleft)

    def draw_player(self) -> None:
        if not self.player_mode or self.player is None:
            return
        player = self.player
        screen_x, screen_y = self.renderer.iso_to_screen(
            int(round(player.x)),
            int(round(player.y)),
            player.height,
            self.offset,
        )
        center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
        body_color = (60, 180, 220) if player.is_swimming else (240, 200, 120)
        outline = (30, 30, 40)
        shadow = (10, 10, 15, 120)
        shadow_surface = pygame.Surface((18, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surface, shadow, shadow_surface.get_rect())
        self.screen.blit(shadow_surface, (center[0] - 9, center[1] + 6))
        diamond = [
            (center[0], center[1] - 6),
            (center[0] + 6, center[1]),
            (center[0], center[1] + 6),
            (center[0] - 6, center[1]),
        ]
        pygame.draw.polygon(self.screen, outline, diamond)
        inner = [
            (center[0], center[1] - 5),
            (center[0] + 5, center[1]),
            (center[0], center[1] + 5),
            (center[0] - 5, center[1]),
        ]
        pygame.draw.polygon(self.screen, body_color, inner)
        pygame.draw.circle(self.screen, (250, 250, 250), (center[0] - 2, center[1] - 2), 2)

    def draw_texture_list(self, panel: pygame.Surface) -> None:
        rect = self.texture_area_rect
        view = pygame.Surface(rect.size, pygame.SRCALPHA)
        view.fill((15, 15, 25, 200))
        pygame.draw.rect(view, (10, 10, 20), view.get_rect(), 1)
        header = self.ui_font.render("Textures", True, (220, 220, 230))
        view.blit(header, (6, 4))
        list_offset = 22
        start_index = max(0, self.texture_scroll // self.texture_item_height)
        end_index = min(
            len(self.replacement_images),
            start_index + (rect.height - list_offset) // self.texture_item_height + 2,
        )
        for idx in range(start_index, end_index):
            image_path = self.replacement_images[idx]
            item_y = idx * self.texture_item_height - self.texture_scroll + list_offset
            item_rect = pygame.Rect(0, item_y, rect.width - self.texture_sidebar_width - 4, self.texture_item_height)
            if idx == self.replacement_index:
                pygame.draw.rect(view, (60, 90, 130), item_rect)
            thumb = self.get_texture_thumb(image_path)
            view.blit(thumb, (6, item_y + 6))
            label = self.ui_font.render(image_path.stem, True, (220, 220, 230))
            view.blit(label, (36, item_y + 8))
        self.draw_texture_scrollbar(view)
        panel.blit(view, (rect.x - self.ui_rect.x, rect.y - self.ui_rect.y))

    def get_texture_thumb(self, path: Path) -> pygame.Surface:
        key = str(path)
        if key in self.texture_thumbs:
            return self.texture_thumbs[key]
        surface = pygame.image.load(str(path)).convert_alpha()
        thumb = pygame.transform.smoothscale(surface, (24, 24))
        self.texture_thumbs[key] = thumb
        return thumb

    def draw_texture_scrollbar(self, surface: pygame.Surface) -> None:
        total_height = len(self.replacement_images) * self.texture_item_height
        if total_height <= 0:
            return
        visible = self.texture_area_rect.height - 22
        if total_height <= visible:
            return
        bar_height = max(20, int(visible * (visible / total_height)))
        scroll_ratio = self.texture_scroll / (total_height - visible)
        bar_y = int(22 + scroll_ratio * (visible - bar_height))
        bar_rect = pygame.Rect(
            surface.get_width() - self.texture_sidebar_width,
            bar_y,
            self.texture_sidebar_width - 2,
            bar_height,
        )
        pygame.draw.rect(surface, (70, 90, 120), bar_rect)

    def draw_ui(self) -> None:
        self.texture_area_rect = pygame.Rect(
            self.ui_rect.x + 10,
            self.ui_rect.bottom - 250,
            self.ui_rect.width - 20,
            240,
        )
        panel = pygame.Surface(self.ui_rect.size, pygame.SRCALPHA)
        panel.fill((25, 25, 40, 220))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        header = self.ui_font.render("Isometric Editor", True, (230, 230, 230))
        panel.blit(header, (10, 8))
        for button in self.buttons:
            offset = (self.ui_rect.x, self.ui_rect.y + self.panel_scroll)
            button.draw(panel, self.ui_font, offset)
        self.draw_panel_scrollbar(panel)
        self.draw_texture_list(panel)
        self.screen.blit(panel, self.ui_rect.topleft)

    def draw_panel_scrollbar(self, panel: pygame.Surface) -> None:
        total_height = self.total_button_height()
        visible = self.ui_rect.height - 20
        if total_height <= visible:
            return
        bar_height = max(24, int(visible * (visible / total_height)))
        scroll_ratio = self.panel_scroll / max(1, total_height - visible)
        bar_y = int(10 + scroll_ratio * (visible - bar_height))
        bar_rect = pygame.Rect(panel.get_width() - 6, bar_y, 4, bar_height)
        pygame.draw.rect(panel, (70, 90, 120), bar_rect)

    def render(self) -> None:
        self.screen.fill((40, 40, 60))
        self.render_grid()
        self.draw_player()
        self.draw_info()
        self.draw_ui()
        self.draw_help()

    def run(self) -> None:
        running = True
        while running:
            running = self.handle_input()
            dt = self.clock.get_time() / 1000.0
            self.update_player(dt, pygame.key.get_pressed())
            self.render()
            pygame.display.flip()
            self.clock.tick(FPS)


def parse_world_size() -> Tuple[int, int]:
    if len(sys.argv) >= 3:
        try:
            width = int(sys.argv[1])
            height = int(sys.argv[2])
            width = max(1, min(200, width))
            height = max(1, min(200, height))
            if width * height > 10000:
                height = max(1, min(height, 10000 // width))
            return width, height
        except ValueError:
            pass
    return 40, 40


def main() -> None:
    world_size = parse_world_size()
    app = IsoApp(world_size)
    app.run()


if __name__ == "__main__":
    crash_reporter = CrashReporter(CRASH_DIR)
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        crash_reporter.report(exc)
        pygame.quit()
        raise
