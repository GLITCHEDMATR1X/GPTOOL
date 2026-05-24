from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    PNMImage,
    TextNode,
    Texture,
    Vec3,
    Vec4,
)

from main import (
    CELL,
    DECK,
    MODULE_CELLS,
    MODULE_SIZE,
    PLAYER_RADIUS,
    WALL_H,
    clamp,
    install_crash_logger,
    PoolroomsArtGame,
)


class Level2Game(PoolroomsArtGame):
    def __init__(self) -> None:
        self.book_open = False
        self.book_prompt_radius = 2.2
        self.book_asset_root: Optional[Path] = None
        self.book_entries: List[Dict[str, Any]] = []
        self.book_nodes: List[Dict[str, Any]] = []
        self.book_ui_root = None
        self.book_ui_title = None
        self.book_ui_body = None
        self.book_ui_footer = None
        self.active_book: Optional[Dict[str, Any]] = None
        self.active_book_pages: List[str] = []
        self.active_book_page_index = 0
        self._level2_collider_cache: Dict[Tuple[int, int], List[Tuple[float, float, float, float]]] = {}

        super().__init__()

        self.settings["quality_preset"] = "Low"
        self.settings["water_reflections"] = 0.0
        self.settings["tile_reflections"] = 0.0
        self.settings["dof_strength"] = 0.0
        self.settings["fog_density"] = 1.18
        self.settings["fov"] = 66.0
        self._sync_sliders_from_settings()
        self._apply_all_settings()

        self._build_library_textures()
        self._ensure_book_assets()
        self._load_books_from_folder()
        self._load_level(2)
        self._setup_weapon_lighting()
        self._setup_book_ui()
        self._refresh_book_nodes()

        self.accept("r", self._try_open_book)
        self.accept("page_up", self._page_book, [-1])
        self.accept("page_down", self._page_book, [1])
        self.accept("arrow_left", self._page_book, [-1])
        self.accept("arrow_right", self._page_book, [1])
        self.accept("escape", self._on_escape_pressed_override)

        self._toast("Level 2 loaded", duration=1.2)

    # ----------------------------
    # Level identity / controls
    # ----------------------------
    def _help_text(self) -> str:
        return (
            "WASD Move • Shift Sprint • Ctrl Speed Lock • H HUD\n"
            "LMB Fire • R Read book • PgUp/PgDn Pages • N Night Vision • Esc Menu"
        )

    def _load_level(self, level_index: int) -> None:
        super()._load_level(2)
        if hasattr(self, "weapon_root") and self.weapon_root is not None and not self.weapon_root.isEmpty():
            self.weapon_root.show()
        self._refresh_book_nodes()
        self._close_book(force=True)

    def _stream_radii(self) -> Tuple[int, int]:
        return 1, 1

    def _shadow_enabled_for_level(self, level_index: Optional[int] = None) -> bool:
        return False

    def _level_allows_hall_return(self, level_index: Optional[int] = None) -> bool:
        return False

    def _toggle_menu(self) -> None:
        if self.book_open:
            self._close_book(force=True)
        super()._toggle_menu()

    def _update_mouse_capture(self, force: bool = False) -> None:
        should_capture = (not self.menu_open) and (not self.book_open) and self._window_has_focus()
        if force or should_capture != self.mouse_captured:
            self._request_mouse_mode(should_capture)

    def _on_escape_pressed_override(self) -> None:
        if self.book_open:
            self._close_book()
            return
        PoolroomsArtGame._on_escape_pressed(self)

    # ----------------------------
    # Library-specific art
    # ----------------------------
    def _build_library_textures(self) -> None:
        self.library_wall_tex = self._make_library_wall_texture()
        self.library_ceiling_tex = self._make_library_ceiling_texture()
        self.library_carpet_tex = self._make_library_carpet_texture()
        self.library_trim_tex = self._make_library_trim_texture()
        self.library_edge_tex = self._make_library_edge_texture()
        self.library_shelf_tex = self._make_library_shelf_texture()
        self.library_column_tex = self._make_library_column_texture()
        self.library_book_tex = self._make_library_book_texture()
        self.library_sign_tex = self._make_library_sign_texture()

    def _finish_local_tex(self, tex: Texture, clamp_mode: bool = False) -> Texture:
        if hasattr(tex, "setMagfilter"):
            tex.setMagfilter(Texture.FTLinear)
        if hasattr(tex, "setMinfilter"):
            tex.setMinfilter(Texture.FTLinearMipmapLinear)
        if clamp_mode:
            if hasattr(tex, "setWrapU"):
                tex.setWrapU(Texture.WMClamp)
            if hasattr(tex, "setWrapV"):
                tex.setWrapV(Texture.WMClamp)
        return tex

    def _make_library_wall_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            band = math.sin(fy * math.tau * 0.7) * 0.014
            for x in range(512):
                grain = (((x * 13 + y * 19) % 61) / 61.0 - 0.5) * 0.018
                roller = math.sin(x * 0.014 + y * 0.006) * 0.010
                base = 0.79 + band + grain + roller
                r = clamp(base * 1.10, 0.0, 1.0)
                g = clamp(base * 0.97, 0.0, 1.0)
                b = clamp(base * 0.72, 0.0, 1.0)
                if y % 128 < 2:
                    r, g, b = 0.54, 0.43, 0.26
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_wall_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_ceiling_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        tile = 46
        for y in range(512):
            for x in range(512):
                tx = x % tile
                ty = y % tile
                seam = tx < 2 or ty < 2
                speck = (((x * 11 + y * 7) % 47) / 47.0 - 0.5) * 0.025
                base = 0.82 + speck
                if seam:
                    r, g, b = 0.60, 0.58, 0.54
                else:
                    r = clamp(base * 1.02, 0.0, 1.0)
                    g = clamp(base * 1.00, 0.0, 1.0)
                    b = clamp(base * 0.94, 0.0, 1.0)
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_ceiling_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_carpet_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(512):
                fx = x / 511.0
                weave = (((x * 9 + y * 5) % 37) / 37.0 - 0.5) * 0.025
                broad = math.sin(fx * math.tau * 1.8) * 0.020 + math.cos(fy * math.tau * 1.2) * 0.018
                r = clamp(0.22 + weave * 0.16 + broad * 0.15, 0.0, 1.0)
                g = clamp(0.20 + weave * 0.14 + broad * 0.13, 0.0, 1.0)
                b = clamp(0.17 + weave * 0.10 + broad * 0.09, 0.0, 1.0)
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_carpet_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_trim_texture(self) -> Texture:
        img = PNMImage(512, 256, 4)
        for y in range(256):
            for x in range(512):
                grain = math.sin(x * 0.070 + y * 0.014) * 0.05 + math.cos(x * 0.031 - y * 0.020) * 0.03
                pore = (((x * 17 + y * 29) % 41) / 41.0 - 0.5) * 0.028
                base = 0.21 + grain + pore
                r = clamp(base * 1.08, 0.0, 1.0)
                g = clamp(base * 0.72, 0.0, 1.0)
                b = clamp(base * 0.38, 0.0, 1.0)
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_trim_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_edge_texture(self) -> Texture:
        img = PNMImage(192, 512, 4)
        for y in range(512):
            fy = y / 511.0
            vertical = math.sin(fy * math.tau * 1.15) * 0.012
            for x in range(192):
                fx = x / 191.0
                center_falloff = 1.0 - abs(fx - 0.5) * 1.7
                rib = math.sin(fx * math.tau * 7.0) * 0.014
                speck = (((x * 23 + y * 11) % 53) / 53.0 - 0.5) * 0.018
                base = 0.54 + vertical + rib * center_falloff + speck
                r = clamp(base * 0.96, 0.0, 1.0)
                g = clamp(base * 0.94, 0.0, 1.0)
                b = clamp(base * 0.88, 0.0, 1.0)
                if x < 3 or x > 188:
                    r, g, b = 0.26, 0.25, 0.23
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_edge_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_shelf_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            for x in range(512):
                grain = math.sin(x * 0.085 + y * 0.010) * 0.04 + math.cos(x * 0.026 - y * 0.022) * 0.03
                base = 0.15 + grain + (((x * 7 + y * 13) % 31) / 31.0 - 0.5) * 0.020
                r = clamp(base * 1.06, 0.0, 1.0)
                g = clamp(base * 0.72, 0.0, 1.0)
                b = clamp(base * 0.38, 0.0, 1.0)
                if y % 104 < 5:
                    r, g, b = 0.05, 0.04, 0.03
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_shelf_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_column_texture(self) -> Texture:
        img = PNMImage(256, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(256):
                stipple = (((x * 11 + y * 5) % 29) / 29.0 - 0.5) * 0.020
                base = 0.63 + stipple + math.sin(fy * math.tau * 0.9) * 0.010
                r = clamp(base * 0.78, 0.0, 1.0)
                g = clamp(base * 0.96, 0.0, 1.0)
                b = clamp(base * 0.68, 0.0, 1.0)
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_column_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_book_texture(self) -> Texture:
        img = PNMImage(256, 256, 4)
        stripes = [
            (0.78, 0.16, 0.12),
            (0.16, 0.34, 0.70),
            (0.76, 0.66, 0.16),
            (0.18, 0.54, 0.32),
            (0.58, 0.18, 0.44),
            (0.80, 0.42, 0.12),
        ]
        band_h = 256 // len(stripes)
        for i, color in enumerate(stripes):
            y0 = i * band_h
            y1 = 256 if i == len(stripes) - 1 else (i + 1) * band_h
            for y in range(y0, y1):
                for x in range(256):
                    shade = 1.0 - abs((x / 255.0) - 0.5) * 0.16
                    r = clamp(color[0] * shade, 0.0, 1.0)
                    g = clamp(color[1] * shade, 0.0, 1.0)
                    b = clamp(color[2] * shade, 0.0, 1.0)
                    if x < 3 or x > 252:
                        r, g, b = 0.92, 0.84, 0.66
                    img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("library_book_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    def _make_library_sign_texture(self) -> Texture:
        img = PNMImage(512, 128, 4)
        for y in range(128):
            for x in range(512):
                base = 0.85 + math.sin(x * 0.012) * 0.010 + (((x * 7 + y * 11) % 41) / 41.0 - 0.5) * 0.012
                img.setXelA(x, y, clamp(base * 1.04, 0.0, 1.0), clamp(base * 0.97, 0.0, 1.0), clamp(base * 0.72, 0.0, 1.0), 1.0)
        tex = Texture("library_sign_tex")
        tex.load(img)
        return self._finish_local_tex(tex)

    # ----------------------------
    # Mood / lighting
    # ----------------------------
    def _apply_environment_mood(self) -> None:
        if int(getattr(self, "current_level", 0)) != 2:
            super()._apply_environment_mood()
            self._update_weapon_light_colors()
            return

        density = clamp(float(self.settings.get("fog_density", 1.18)), 0.50, 1.90)
        if self.nightvision_on:
            bg = Vec4(0.01, 0.03, 0.02, 1.0)
            fog = Vec4(0.04, 0.16, 0.08, 1.0)
            amb = Vec4(0.16, 0.24, 0.16, 1.0)
            sun = Vec4(0.10, 0.14, 0.10, 1.0)
            fill = Vec4(0.08, 0.12, 0.08, 1.0)
            lift = Vec4(0.08, 0.18, 0.10, 1.0)
            self.nv_overlay.show()
            if self.hud_visible and not self.menu_open:
                self.nv_scan.show()
            self.ui_cursor.setFg((0.74, 1.0, 0.76, 0.82))
        else:
            bg = Vec4(0.006, 0.006, 0.008, 1.0)
            fog = Vec4(0.0, 0.0, 0.0, 1.0)
            amb = Vec4(0.08, 0.075, 0.065, 1.0)
            sun = Vec4(0.10, 0.09, 0.075, 1.0)
            fill = Vec4(0.035, 0.032, 0.028, 1.0)
            lift = Vec4(0.018, 0.018, 0.022, 1.0)
            self.nv_overlay.hide()
            if self.nightvision_cooldown_left <= 0.0:
                self.nv_scan.hide()
            self.ui_cursor.setFg((0.94, 0.98, 0.95, 0.55))

        self.setBackgroundColor(bg)
        self.scene_fog.setColor(fog)
        self.scene_fog.setLinearRange(max(2.0, 3.5 / density), max(10.0, 18.0 / density))
        self.amb_np.node().setColor(amb)
        self.sun_np.node().setColor(sun)
        self.fill_np.node().setColor(fill)
        self.lift_np.node().setColor(lift)
        self._update_weapon_light_colors()

    def _setup_weapon_lighting(self) -> None:
        if not hasattr(self, "weapon_root") or self.weapon_root is None or self.weapon_root.isEmpty():
            return
        try:
            self.weapon_root.clearLightOff()
            self.weapon_root.clearLight()
        except Exception:
            pass
        try:
            self.weapon_root.setShaderAuto()
        except Exception:
            pass

        self.weapon_light_parent = self.camera.attachNewNode("weapon_light_parent")

        amb = AmbientLight("weapon_amb")
        self.weapon_amb_np = self.weapon_light_parent.attachNewNode(amb)
        self.weapon_root.setLight(self.weapon_amb_np)

        key = DirectionalLight("weapon_key")
        self.weapon_key_np = self.weapon_light_parent.attachNewNode(key)
        self.weapon_key_np.setHpr(-36.0, -18.0, 0.0)
        self.weapon_root.setLight(self.weapon_key_np)

        rim = DirectionalLight("weapon_rim")
        self.weapon_rim_np = self.weapon_light_parent.attachNewNode(rim)
        self.weapon_rim_np.setHpr(144.0, 10.0, 0.0)
        self.weapon_root.setLight(self.weapon_rim_np)

        self._update_weapon_light_colors()

    def _update_weapon_light_colors(self) -> None:
        if not hasattr(self, "weapon_amb_np"):
            return
        if self.nightvision_on:
            amb = Vec4(0.14, 0.22, 0.14, 1.0)
            key = Vec4(0.22, 0.34, 0.22, 1.0)
            rim = Vec4(0.08, 0.12, 0.09, 1.0)
        elif int(getattr(self, "current_level", 0)) == 2:
            amb = Vec4(0.16, 0.14, 0.12, 1.0)
            key = Vec4(0.26, 0.22, 0.18, 1.0)
            rim = Vec4(0.06, 0.05, 0.05, 1.0)
        else:
            amb = Vec4(0.10, 0.10, 0.10, 1.0)
            key = Vec4(0.18, 0.18, 0.18, 1.0)
            rim = Vec4(0.06, 0.06, 0.06, 1.0)
        self.weapon_amb_np.node().setColor(amb)
        self.weapon_key_np.node().setColor(key)
        self.weapon_rim_np.node().setColor(rim)

    # ----------------------------
    # Layout / generation
    # ----------------------------
    def _hash_pair(self, mx: int, my: int) -> int:
        seed = (mx * 92837111) ^ (my * 689287499) ^ 0x5F3759DF
        return seed & 0xFFFFFFFF

    def _library_layout(self, mx: int, my: int) -> Dict[str, Any]:
        seed = self._hash_pair(mx, my)
        variant = seed % 4
        vertical = (seed & 1) == 0

        shelves: List[Dict[str, Any]] = []
        pedestals: List[Tuple[float, float]] = []
        columns: List[Tuple[float, float, float]] = []
        partitions: List[Dict[str, Any]] = []

        edge_pad = 1.8
        gap_low = MODULE_SIZE * 0.42
        gap_high = MODULE_SIZE * 0.58
        shelf_h = 2.48

        if vertical:
            lane_x = [CELL * 1.15, CELL * 2.75, CELL * 4.35, CELL * 7.65, CELL * 9.25, CELL * 10.85]
            if variant == 1:
                lane_x = lane_x[:-1]
            elif variant == 2:
                lane_x = lane_x[1:]
            elif variant == 3:
                lane_x = [CELL * 1.15, CELL * 3.05, CELL * 8.95, CELL * 10.85]
            for idx, x in enumerate(lane_x):
                lane_seed = (seed >> (idx * 3)) & 7
                width = 0.92 + (0.10 if idx % 3 == 1 else 0.0)
                segs = [
                    (edge_pad, gap_low - 0.55 - lane_seed * 0.03),
                    (gap_high + lane_seed * 0.03, MODULE_SIZE - edge_pad),
                ]
                if variant == 3 and idx in (1, 2):
                    segs = [
                        (edge_pad, MODULE_SIZE * 0.30),
                        (MODULE_SIZE * 0.36, MODULE_SIZE * 0.50),
                        (MODULE_SIZE * 0.62, MODULE_SIZE - edge_pad),
                    ]
                for y0, y1 in segs:
                    length = max(4.2, y1 - y0)
                    cy = (y0 + y1) * 0.5
                    shelves.append({"center": (x, cy), "size": (width, length, shelf_h), "axis": "y"})
            pedestals = [
                (MODULE_SIZE * 0.50, MODULE_SIZE * 0.50),
                (MODULE_SIZE * 0.50, MODULE_SIZE * 0.28),
                (MODULE_SIZE * 0.50, MODULE_SIZE * 0.72),
            ]
            columns = [
                (CELL * 0.78, CELL * 0.78, CELL * 0.66),
                (MODULE_SIZE - CELL * 0.78, CELL * 0.78, CELL * 0.66),
                (CELL * 0.78, MODULE_SIZE - CELL * 0.78, CELL * 0.66),
                (MODULE_SIZE - CELL * 0.78, MODULE_SIZE - CELL * 0.78, CELL * 0.66),
            ]
            if variant in (0, 2):
                partitions.append({"center": (MODULE_SIZE * 0.18, MODULE_SIZE * 0.50), "length": CELL * 2.8, "axis": "y", "height": 3.18})
                partitions.append({"center": (MODULE_SIZE * 0.82, MODULE_SIZE * 0.50), "length": CELL * 2.8, "axis": "y", "height": 3.18})
        else:
            lane_y = [CELL * 1.15, CELL * 2.75, CELL * 4.35, CELL * 7.65, CELL * 9.25, CELL * 10.85]
            if variant == 1:
                lane_y = lane_y[:-1]
            elif variant == 2:
                lane_y = lane_y[1:]
            elif variant == 3:
                lane_y = [CELL * 1.15, CELL * 3.05, CELL * 8.95, CELL * 10.85]
            for idx, y in enumerate(lane_y):
                lane_seed = (seed >> (idx * 3)) & 7
                depth = 0.92 + (0.10 if idx % 3 == 1 else 0.0)
                segs = [
                    (edge_pad, gap_low - 0.55 - lane_seed * 0.03),
                    (gap_high + lane_seed * 0.03, MODULE_SIZE - edge_pad),
                ]
                if variant == 3 and idx in (1, 2):
                    segs = [
                        (edge_pad, MODULE_SIZE * 0.30),
                        (MODULE_SIZE * 0.36, MODULE_SIZE * 0.50),
                        (MODULE_SIZE * 0.62, MODULE_SIZE - edge_pad),
                    ]
                for x0, x1 in segs:
                    length = max(4.2, x1 - x0)
                    cx = (x0 + x1) * 0.5
                    shelves.append({"center": (cx, y), "size": (length, depth, shelf_h), "axis": "x"})
            pedestals = [
                (MODULE_SIZE * 0.50, MODULE_SIZE * 0.50),
                (MODULE_SIZE * 0.28, MODULE_SIZE * 0.50),
                (MODULE_SIZE * 0.72, MODULE_SIZE * 0.50),
            ]
            columns = [
                (CELL * 0.78, CELL * 0.78, CELL * 0.66),
                (MODULE_SIZE - CELL * 0.78, CELL * 0.78, CELL * 0.66),
                (CELL * 0.78, MODULE_SIZE - CELL * 0.78, CELL * 0.66),
                (MODULE_SIZE - CELL * 0.78, MODULE_SIZE - CELL * 0.78, CELL * 0.66),
            ]
            if variant in (0, 2):
                partitions.append({"center": (MODULE_SIZE * 0.50, MODULE_SIZE * 0.18), "length": CELL * 2.8, "axis": "x", "height": 3.18})
                partitions.append({"center": (MODULE_SIZE * 0.50, MODULE_SIZE * 0.82), "length": CELL * 2.8, "axis": "x", "height": 3.18})

        return {
            "shelves": shelves,
            "pedestals": pedestals,
            "columns": columns,
            "partitions": partitions,
            "show_sign": mx == 0 and my == 0,
        }

    def _module_data(self, mx: int, my: int):
        if int(getattr(self, "current_level", 0)) != 2:
            return super()._module_data(mx, my)
        key = (mx, my)
        if key in self.module_data_cache:
            return self.module_data_cache[key]
        grid = [[DECK for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
        data = type("ModuleData", (), {"grid": grid, "style_id": 2})()
        self.module_data_cache[key] = data
        return data

    def _build_module(self, mx: int, my: int):
        if int(getattr(self, "current_level", 0)) != 2:
            return super()._build_module(mx, my)
        data = self._module_data(mx, my)
        root = self.world_root.attachNewNode(f"library_module_{mx}_{my}")
        root.setPos(mx * MODULE_SIZE, my * MODULE_SIZE, 0)
        water_root = root.attachNewNode("water_root")
        self._build_library_module(root, mx, my, data.grid)
        return type(
            "ModuleChunk",
            (),
            {"mx": mx, "my": my, "root": root, "water_root": water_root, "style_name": "Abandoned Library"},
        )()

    def _build_library_module(self, parent, mx: int, my: int, grid: List[List[int]]) -> None:
        del grid
        center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, 0.0)
        floor = self._add_plane(parent, Vec3(center.x, center.y, 0.012), MODULE_SIZE, MODULE_SIZE, (0, -90, 0), self.library_carpet_tex, 2.6, 2.6)
        floor.setColorScale(0.82, 0.82, 0.82, 1.0)
        self.deck_surfaces.append(floor)

        ceiling = self._add_plane(parent, Vec3(center.x, center.y, WALL_H), MODULE_SIZE, MODULE_SIZE, (0, -90, 0), self.library_ceiling_tex, 2.0, 2.0)
        ceiling.setColorScale(0.80, 0.80, 0.76, 1.0)

        layout = self._library_layout(mx, my)
        self._build_library_light_rows(parent, mx, my)
        self._build_library_columns(parent, layout)
        self._build_library_shelves(parent, layout)
        self._build_library_partitions(parent, layout)
        if layout["show_sign"]:
            self._build_library_sign_wall(parent)
        self._build_book_props(parent, mx, my, layout)

    def _build_library_light_rows(self, parent, mx: int, my: int) -> None:
        del my
        seed = self._hash_pair(mx, 17)
        x_positions = [MODULE_SIZE * 0.18, MODULE_SIZE * 0.40, MODULE_SIZE * 0.62, MODULE_SIZE * 0.84]
        y = CELL * 0.95
        idx = 0
        while y < MODULE_SIZE - CELL * 0.55:
            shift = (((seed >> (idx % 8)) & 3) - 1.5) * 0.12
            for x in x_positions:
                housing = self._add_box(parent, Vec3(x + shift, y, WALL_H - 0.07), Vec3(1.26, 0.42, 0.10), self.library_trim_tex)
                housing.setColorScale(0.18, 0.13, 0.09, 1.0)
                panel = self._add_plane(parent, Vec3(x + shift, y, WALL_H - 0.02), 1.10, 0.26, (0, -90, 0), self.light_tex, 1.0, 1.0, True)
                panel.setColorScale(0.82, 0.78, 0.64, 0.70)
                self._add_point_light(parent, Vec3(x + shift, y, WALL_H - 0.28), Vec4(0.34, 0.28, 0.20, 1.0), Vec3(1.0, 0.0, 0.10), phase=idx * 0.31, pulse=0.006)
                idx += 1
            y += CELL * 2.18

    def _build_library_columns(self, parent, layout: Dict[str, Any]) -> None:
        for x, y, size in layout["columns"]:
            pos = Vec3(x, y, WALL_H * 0.5)
            column = self._add_box(parent, pos, Vec3(size, size, WALL_H), self.library_column_tex)
            column.setColorScale(0.44, 0.58, 0.42, 1.0)
            base = self._add_box(parent, pos + Vec3(0.0, 0.0, -WALL_H * 0.5 + 0.14), Vec3(size * 1.22, size * 1.22, 0.28), self.library_trim_tex)
            base.setColorScale(0.10, 0.08, 0.06, 1.0)

    def _build_library_shelves(self, parent, layout: Dict[str, Any]) -> None:
        for shelf_data in layout["shelves"]:
            cx, cy = shelf_data["center"]
            width, depth, height = shelf_data["size"]
            axis = shelf_data["axis"]

            shelf = self._add_box(parent, Vec3(cx, cy, height * 0.5), Vec3(width, depth, height), self.library_shelf_tex)
            shelf.setColorScale(0.56, 0.42, 0.28, 1.0)

            shelf_levels = [0.28, 0.90, 1.52, 2.12]
            if axis == "y":
                for z in shelf_levels:
                    board = self._add_box(parent, Vec3(cx, cy, z), Vec3(width * 0.92, depth * 0.96, 0.05), self.library_trim_tex)
                    board.setColorScale(0.08, 0.06, 0.04, 1.0)
                for side in (-1.0, 1.0):
                    strip = self._add_box(parent, Vec3(cx + side * (width * 0.5 + 0.05), cy, 1.28), Vec3(0.10, depth * 0.94, 1.90), self.library_book_tex)
                    strip.setColorScale(0.88, 0.88, 0.88, 1.0)
            else:
                for z in shelf_levels:
                    board = self._add_box(parent, Vec3(cx, cy, z), Vec3(width * 0.96, depth * 0.92, 0.05), self.library_trim_tex)
                    board.setColorScale(0.08, 0.06, 0.04, 1.0)
                for side in (-1.0, 1.0):
                    strip = self._add_box(parent, Vec3(cx, cy + side * (depth * 0.5 + 0.05), 1.28), Vec3(width * 0.94, 0.10, 1.90), self.library_book_tex)
                    strip.setColorScale(0.88, 0.88, 0.88, 1.0)

            top = self._add_box(parent, Vec3(cx, cy, height - 0.04), Vec3(width * 1.03, depth * 1.03, 0.08), self.library_trim_tex)
            top.setColorScale(0.10, 0.08, 0.05, 1.0)

    def _add_partition_wall(self, parent, center: Vec3, length: float, axis: str, height: float = 3.18, face_gap: float = 0.07, cap_thickness: float = 0.18):
        tex_scale_u = max(1.0, length / 5.8)
        if axis == "x":
            front = self._add_plane(parent, center + Vec3(0.0, face_gap, 0.0), length, height, (180, 0, 0), self.library_wall_tex, tex_scale_u, 1.0)
            back = self._add_plane(parent, center - Vec3(0.0, face_gap, 0.0), length, height, (0, 0, 0), self.library_wall_tex, tex_scale_u, 1.0)
            top = self._add_box(parent, center + Vec3(0.0, 0.0, height * 0.5 - 0.05), Vec3(length, cap_thickness, 0.10), self.library_edge_tex)
            left_cap = self._add_box(parent, center + Vec3(-length * 0.5 + 0.05, 0.0, 0.0), Vec3(0.10, cap_thickness, height), self.library_edge_tex)
            right_cap = self._add_box(parent, center + Vec3(length * 0.5 - 0.05, 0.0, 0.0), Vec3(0.10, cap_thickness, height), self.library_edge_tex)
        else:
            front = self._add_plane(parent, center + Vec3(face_gap, 0.0, 0.0), length, height, (90, 0, 0), self.library_wall_tex, tex_scale_u, 1.0)
            back = self._add_plane(parent, center - Vec3(face_gap, 0.0, 0.0), length, height, (-90, 0, 0), self.library_wall_tex, tex_scale_u, 1.0)
            top = self._add_box(parent, center + Vec3(0.0, 0.0, height * 0.5 - 0.05), Vec3(cap_thickness, length, 0.10), self.library_edge_tex)
            left_cap = self._add_box(parent, center + Vec3(0.0, -length * 0.5 + 0.05, 0.0), Vec3(cap_thickness, 0.10, height), self.library_edge_tex)
            right_cap = self._add_box(parent, center + Vec3(0.0, length * 0.5 - 0.05, 0.0), Vec3(cap_thickness, 0.10, height), self.library_edge_tex)
        for wall in (front, back):
            wall.setColorScale(0.78, 0.74, 0.66, 1.0)
        for cap in (top, left_cap, right_cap):
            cap.setColorScale(0.38, 0.36, 0.34, 1.0)

    def _build_library_partitions(self, parent, layout: Dict[str, Any]) -> None:
        for part in layout["partitions"]:
            center = Vec3(part["center"][0], part["center"][1], part["height"] * 0.5)
            self._add_partition_wall(parent, center, part["length"], part["axis"], part["height"])

    def _build_library_sign_wall(self, parent) -> None:
        center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE - 0.58, 1.62)
        self._add_partition_wall(parent, center, CELL * 6.4, "x", height=3.24)
        back = self._add_box(parent, Vec3(MODULE_SIZE * 0.5, MODULE_SIZE - 0.50, 3.06), Vec3(CELL * 2.9, 0.14, 0.54), self.library_sign_tex)
        back.setColorScale(1.0, 0.96, 0.78, 1.0)
        text = TextNode("library_sign")
        text.setText("THE END")
        text.setTextColor(0.08, 0.07, 0.06, 1.0)
        text.setAlign(TextNode.ACenter)
        sign_np = parent.attachNewNode(text.generate())
        sign_np.setScale(0.54)
        sign_np.setPos(MODULE_SIZE * 0.5, MODULE_SIZE - 0.40, 2.92)
        sign_np.setH(180.0)
        sign_np.setTwoSided(True)

    def _record_rect(self, colliders: List[Tuple[float, float, float, float]], cx: float, cy: float, hx: float, hy: float) -> None:
        colliders.append((cx - hx, cx + hx, cy - hy, cy + hy))

    def _module_colliders(self, mx: int, my: int) -> List[Tuple[float, float, float, float]]:
        key = (mx, my)
        cached = self._level2_collider_cache.get(key)
        if cached is not None:
            return cached

        layout = self._library_layout(mx, my)
        colliders: List[Tuple[float, float, float, float]] = []
        for shelf in layout["shelves"]:
            cx, cy = shelf["center"]
            width, depth, _ = shelf["size"]
            self._record_rect(colliders, cx, cy, width * 0.5, depth * 0.5)
        for x, y, size in layout["columns"]:
            self._record_rect(colliders, x, y, size * 0.5, size * 0.5)
        wall_half = 0.09
        for part in layout["partitions"]:
            cx, cy = part["center"]
            if part["axis"] == "x":
                self._record_rect(colliders, cx, cy, part["length"] * 0.5, wall_half)
            else:
                self._record_rect(colliders, cx, cy, wall_half, part["length"] * 0.5)
        if layout["show_sign"]:
            self._record_rect(colliders, MODULE_SIZE * 0.5, MODULE_SIZE - 0.58, CELL * 6.4 * 0.5, wall_half)

        self._level2_collider_cache[key] = colliders
        return colliders

    def _circle_hits_rect(self, px: float, py: float, rect: Tuple[float, float, float, float]) -> bool:
        min_x, max_x, min_y, max_y = rect
        hit_x = clamp(px, min_x, max_x)
        hit_y = clamp(py, min_y, max_y)
        return (px - hit_x) ** 2 + (py - hit_y) ** 2 < PLAYER_RADIUS ** 2

    def _collides(self, pos: Vec3) -> bool:
        if int(getattr(self, "current_level", 0)) != 2:
            return super()._collides(pos)

        pmx, pmy = self._module_of_pos(pos.x, pos.y)
        for my in range(pmy - 1, pmy + 2):
            base_y = my * MODULE_SIZE
            for mx in range(pmx - 1, pmx + 2):
                base_x = mx * MODULE_SIZE
                for rect in self._module_colliders(mx, my):
                    world_rect = (rect[0] + base_x, rect[1] + base_x, rect[2] + base_y, rect[3] + base_y)
                    if self._circle_hits_rect(pos.x, pos.y, world_rect):
                        return True
        return False

    # ----------------------------
    # Books
    # ----------------------------
    def _ensure_book_assets(self) -> None:
        self.book_asset_root = self.base_dir / "assets" / "levels" / "level2" / "books"
        self.book_asset_root.mkdir(parents=True, exist_ok=True)
        samples = {
            "welcome_to_the_end.txt": (
                "Welcome to the end.\n\n"
                "The shelves still stand, but nobody checks anything out anymore. "
                "The lamps hum. The carpet holds its dust. The books wait for hands that do not come.\n\n"
                "Put your own .txt files in this folder and Level 2 will load them as readable books."
            ),
            "closing_notes.txt": (
                "Closing Notes\n\n"
                "1. Count the returns.\n"
                "2. Turn off the terminal.\n"
                "3. Lock the side office.\n"
                "4. Do not follow footsteps after closing.\n\n"
                "If the overhead lights dim in sequence, leave the cart where it is and walk away."
            ),
        }
        for name, text in samples.items():
            path = self.book_asset_root / name
            if not path.exists():
                path.write_text(text, encoding="utf-8")

    def _load_books_from_folder(self) -> None:
        self.book_entries = []
        if self.book_asset_root is None:
            return
        files = sorted(self.book_asset_root.glob("*.txt"))
        if not files:
            return
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            title = path.stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled"
            pages = self._paginate_book_text(text)
            self.book_entries.append({"title": title, "path": path, "pages": pages})

    def _paginate_book_text(self, text: str) -> List[str]:
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ["(empty)"]
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        pages: List[str] = []
        current_lines: List[str] = []
        current_len = 0
        max_lines = 18
        max_chars = 1100
        for para in paragraphs:
            wrapped = textwrap.wrap(para, width=58) or [""]
            block = wrapped + [""]
            if current_lines and (len(current_lines) + len(block) > max_lines or current_len + len(para) > max_chars):
                pages.append("\n".join(current_lines).strip())
                current_lines = []
                current_len = 0
            current_lines.extend(block)
            current_len += len(para)
        if current_lines:
            pages.append("\n".join(current_lines).strip())
        return pages or ["(empty)"]

    def _refresh_book_nodes(self) -> None:
        self.book_nodes = [entry for entry in self.book_nodes if entry.get("node") is not None and not entry["node"].isEmpty()]

    def _build_book_props(self, parent, mx: int, my: int, layout: Dict[str, Any]) -> None:
        del mx, my
        if not self.book_entries:
            return
        positions = list(layout["pedestals"])
        for idx, base_xy in enumerate(positions):
            book = self.book_entries[idx % len(self.book_entries)]
            base_pos = Vec3(base_xy[0], base_xy[1], 0.0)
            stand = self._add_box(parent, base_pos + Vec3(0.0, 0.0, 0.52), Vec3(0.52, 0.52, 1.04), self.library_trim_tex)
            stand.setColorScale(0.14, 0.10, 0.08, 1.0)
            prop = self._add_box(parent, base_pos + Vec3(0.0, 0.0, 1.10), Vec3(0.24, 0.14, 0.34), self.library_book_tex)
            prop.setColorScale(1.0, 1.0, 1.0, 1.0)
            marker_pos = base_pos + Vec3(0.0, 0.0, 1.44)

            glow = self._add_plane(parent, marker_pos, 0.22, 0.22, (0, 0, 0), self.light_tex, 1.0, 1.0, True)
            glow.setColorScale(1.0, 0.92, 0.62, 0.44)
            glow.setBillboardPointEye()

            self.book_nodes.append(
                {
                    "title": book["title"],
                    "pages": list(book["pages"]),
                    "node": prop,
                    "glow": glow,
                    "world_pos": Vec3(parent.getX() + base_pos.x, parent.getY() + base_pos.y, base_pos.z),
                }
            )

    def _nearest_book(self) -> Tuple[Optional[Dict[str, Any]], float]:
        self._refresh_book_nodes()
        best: Optional[Dict[str, Any]] = None
        best_dist = 1e9
        player = Vec3(self.player_pos.x, self.player_pos.y, 0.0)
        for entry in self.book_nodes:
            pos = entry["world_pos"]
            dist = (Vec3(pos.x, pos.y, 0.0) - player).length()
            if dist < best_dist:
                best = entry
                best_dist = dist
        return best, best_dist

    def _setup_book_ui(self) -> None:
        self.book_ui_root = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-1.08, 1.08, -0.82, 0.82),
            frameColor=(0.07, 0.05, 0.03, 0.96),
            relief=None,
            sortOrder=20,
        )
        self.book_ui_title = DirectLabel(
            parent=self.book_ui_root,
            text="",
            text_scale=0.060,
            text_fg=(0.98, 0.92, 0.78, 1.0),
            relief=None,
            pos=(0.0, 0.0, 0.70),
            text_align=TextNode.ACenter,
        )
        self.book_ui_body = DirectLabel(
            parent=self.book_ui_root,
            text="",
            text_scale=0.045,
            text_fg=(0.92, 0.88, 0.80, 1.0),
            relief=None,
            pos=(-0.92, 0.0, 0.50),
            text_align=TextNode.ALeft,
            text_wordwrap=42,
        )
        self.book_ui_footer = DirectLabel(
            parent=self.book_ui_root,
            text="PgUp/PgDn • Esc to close",
            text_scale=0.038,
            text_fg=(0.84, 0.78, 0.70, 1.0),
            relief=None,
            pos=(0.0, 0.0, -0.72),
            text_align=TextNode.ACenter,
        )
        self.book_ui_root.hide()

    def _try_open_book(self) -> None:
        if self.menu_open:
            return
        book, dist = self._nearest_book()
        if book is None or dist > self.book_prompt_radius:
            self._toast("No readable book nearby", duration=1.0)
            return
        self.active_book = book
        self.active_book_pages = list(book["pages"])
        self.active_book_page_index = 0
        self.book_open = True
        self._show_book_page()
        self._update_mouse_capture(force=True)

    def _show_book_page(self) -> None:
        if not self.book_open or self.active_book is None:
            return
        page_count = max(1, len(self.active_book_pages))
        page_index = max(0, min(self.active_book_page_index, page_count - 1))
        self.active_book_page_index = page_index
        self.book_ui_title["text"] = self.active_book["title"]
        self.book_ui_body["text"] = self.active_book_pages[page_index]
        self.book_ui_footer["text"] = f"Page {page_index + 1}/{page_count}  •  PgUp/PgDn  •  Esc to close"
        self.book_ui_root.show()

    def _page_book(self, direction: int) -> None:
        if not self.book_open:
            return
        page_count = max(1, len(self.active_book_pages))
        self.active_book_page_index = max(0, min(page_count - 1, self.active_book_page_index + int(direction)))
        self._show_book_page()

    def _close_book(self, force: bool = False) -> None:
        if not self.book_open and not force:
            return
        self.book_open = False
        self.active_book = None
        self.active_book_pages = []
        self.active_book_page_index = 0
        if self.book_ui_root is not None:
            self.book_ui_root.hide()
        self._update_mouse_capture(force=True)

    # ----------------------------
    # UI hooks
    # ----------------------------
    def _update_hub_interact_prompt(self) -> None:
        if not hasattr(self, "ui_interact"):
            return
        if self.menu_open or self.book_open:
            self.ui_interact.setText("")
            return
        book, dist = self._nearest_book()
        if book is not None and dist <= self.book_prompt_radius:
            self.ui_interact.setText(f"Press R to Read: {book['title']}")
        else:
            self.ui_interact.setText("")

    def _update_ui(self) -> None:
        pmx, pmy = self._module_of_pos(self.player_pos.x, self.player_pos.y)
        gx, gy = self._world_cell_from_pos(self.player_pos.x, self.player_pos.y)
        preset = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
        book, dist = self._nearest_book()
        nearby = book["title"] if book is not None and dist <= self.book_prompt_radius else "None"
        self.ui_status.setText(
            f"Level 2 • Abandoned Library • Grid {gx},{gy} • Module {pmx},{pmy}\n"
            f"Readable book: {nearby} • Shots {self.shots_fired:03d} • {preset}"
        )
        self._apply_hud_visibility()

    def _clear_runtime_world(self) -> None:
        super()._clear_runtime_world()
        self.book_nodes = []
        self._level2_collider_cache.clear()
        self._close_book(force=True)


def main() -> None:
    install_crash_logger()
    game = Level2Game()
    game.run()


if __name__ == "__main__":
    main()
