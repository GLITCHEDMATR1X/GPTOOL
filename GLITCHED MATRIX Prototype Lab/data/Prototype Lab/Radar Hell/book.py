"""
Inferno: The Book of Blood — Pygame Text Adventure (Dante-inspired)
-----------------------------------------------------------------
Expanded exploration + slower progression + hidden exit + button UI + storybook saves.

Controls
- Mouse: click buttons; click map nodes to inspect; wheel scrolls journal
- TAB: toggle borderless fullscreen windowed
- ESC: press once to arm exit, press again to quit
"""

from __future__ import annotations

import json
import math
import re
import random
import time
import traceback
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pygame
from pygame import gfxdraw

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import letter
except Exception:
    rl_canvas = None
    letter = None

VIRTUAL_W, VIRTUAL_H = 1920, 1080
FPS = 60
APP_TITLE = "The Book of Blood"

BASE_DIR = Path(__file__).resolve().parent

SAVE_DIR = BASE_DIR / "saves"
LOG_DIR = BASE_DIR / "Logs"
MUSIC_DIR = BASE_DIR / "music"  # drop .mp3/.ogg/.wav here
MEDIA_DIR = BASE_DIR / "media"  # generated runtime media (auto-cleaned on new story)

SAVE_JSON_BEGIN = "===STATE_JSON_BEGIN==="
SAVE_JSON_END = "===STATE_JSON_END==="
SAVE_SLOTS = ["slot1", "slot2", "slot3", "slot4", "slot5"]

THEME = {
    # Deep hell palette: reds + blacks only (no yellows/greens)
    "bg": (6, 2, 4),
    "panel_fill": (12, 4, 6),
    "panel_border": (90, 10, 18),
    "panel_border_strong": (160, 20, 30),

    "accent_red": (230, 30, 45),
    "accent_red_soft": (150, 12, 22),

    "text": (246, 228, 234),
    "text_dim": (210, 170, 178),
    "text_muted": (168, 118, 130),

    "btn_fill": (16, 6, 8),
    "btn_fill_hover": (26, 8, 10),
    "btn_border": (120, 14, 24),
    "btn_border_hover": (230, 30, 45),
    "btn_text": (248, 232, 238),

    "map_edge": (60, 8, 12),
    "map_edge_visited": (115, 18, 28),
    "map_node": (130, 18, 30),
    "map_node_visited": (210, 35, 50),
    "map_node_current": (255, 120, 130),
}

# Internal directive token (not shown to the player unless Sketch is used)
INTERNAL_ILLUSTRATION_TAG = "\u2063ILLUSTRATION"

# ----------------------------
# UI polish helpers
# ----------------------------

def make_red_arrow_cursor() -> "pygame.cursors.Cursor":
    """
    Custom red mouse arrow (best-effort). Some platforms ignore custom cursors.
    We also draw a larger software cursor for visibility.
    """
    # 48x48 arrow with black outline + bright red fill + pale highlight
    W, H = 48, 48
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    # A fat arrow polygon (tip at 3,3)
    outline_pts = [(3,3), (3,34), (12,28), (18,46), (24,44), (18,26), (35,26)]
    fill_pts    = [(5,5), (5,31), (13,26), (18,42), (21,41), (16,24), (32,24)]

    # glow
    glow = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(glow, (255, 40, 60, 90), [(x+1,y+1) for x,y in outline_pts])
    pygame.draw.polygon(glow, (255, 40, 60, 55), [(x+2,y+2) for x,y in outline_pts])
    surf.blit(glow, (0,0))

    # black outline
    pygame.draw.polygon(surf, (0,0,0,255), outline_pts)
    # bright red fill
    pygame.draw.polygon(surf, (255, 30, 55, 255), fill_pts)
    # inner highlight
    pygame.draw.line(surf, (255, 220, 230, 220), (8,8), (8,26), 2)
    pygame.draw.line(surf, (255, 220, 230, 200), (8,26), (15,22), 2)

    # hotspot at tip
    return pygame.cursors.Cursor((3,3), surf)

def try_apply_red_cursor() -> None:
    """
    Try setting an OS cursor (may be ignored). We also prefer a software cursor for brightness.
    """
    try:
        pygame.mouse.set_cursor(make_red_arrow_cursor())
    except Exception:
        pass
    # draw our own cursor for visibility
    try:
        pygame.mouse.set_visible(False)
    except Exception:
        pass

def draw_soft_cursor_screen(screen: pygame.Surface, mx: int, my: int, view_rect: pygame.Rect) -> None:
    """
    High-visibility software cursor rendered after scaling (window-space).
    """
    if not view_rect.collidepoint(mx, my):
        return

    # Big bright arrow + glow
    pts = [(mx, my), (mx, my+26), (mx+10, my+22), (mx+14, my+40), (mx+20, my+38), (mx+14, my+20), (mx+30, my+20)]
    # glow layers
    pygame.draw.polygon(screen, (255, 40, 60), pts)
    pygame.draw.polygon(screen, (0,0,0), pts, width=2)
    # extra highlight tip
    pygame.draw.circle(screen, (255, 220, 230), (mx, my), 3)

def _small_noise_tile(rng: random.Random, w: int, h: int, alpha: int = 60) -> pygame.Surface:
    """
    Small noise tile biased to reds/blacks only.
    Fast-path uses numpy; fallback uses set_at.
    """
    try:
        import numpy as _np  # type: ignore
        seed = rng.getrandbits(32)
        _rng = _np.random.default_rng(seed)
        r = _rng.integers(0, 256, size=(w, h), dtype=_np.uint8)
        g = _rng.integers(0, 18, size=(w, h), dtype=_np.uint8)
        b = _rng.integers(0, 18, size=(w, h), dtype=_np.uint8)
        arr = _np.dstack([r, g, b])  # (w,h,3)
        s = pygame.surfarray.make_surface(arr).convert()
        s.set_alpha(alpha)
        return s
    except Exception:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.lock()
        try:
            for y in range(h):
                for x in range(w):
                    rv = rng.randint(0, 255)
                    gv = rng.randint(0, 18)
                    bv = rng.randint(0, 18)
                    s.set_at((x, y), (rv, gv, bv, alpha))
        finally:
            s.unlock()
        return s

def _black_static_tile(rng: random.Random, w: int, h: int) -> pygame.Surface:
    """
    Black static tile (grayscale) for demonic face embossing.
    """
    try:
        import numpy as _np  # type: ignore
        seed = rng.getrandbits(32)
        _rng = _np.random.default_rng(seed)
        g = _rng.integers(0, 52, size=(w, h), dtype=_np.uint8)
        arr = _np.dstack([g, g, g])
        s = pygame.surfarray.make_surface(arr).convert_alpha()
        return s
    except Exception:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.lock()
        try:
            for y in range(h):
                for x in range(w):
                    v = rng.randint(0, 52)
                    s.set_at((x, y), (v, v, v, 255))
        finally:
            s.unlock()
        return s

def overlay_demonic_face(bg: pygame.Surface, rng: random.Random) -> None:
    """
    Subtle demonic face formed from black static, baked into the background.
    The effect is intentionally faint so UI text remains legible.
    """
    W, H = bg.get_size()

    # Create a masked noise layer
    noise = _black_static_tile(rng, 320, 180)
    noise = pygame.transform.scale(noise, (W, H))

    mask = pygame.Surface((W, H), pygame.SRCALPHA)

    # Face anchor (upper-mid, offset behind left panel mostly)
    cx = int(W * 0.62)
    cy = int(H * 0.48)
    fw = int(min(W, H) * 0.62)
    fh = int(min(W, H) * 0.76)

    # Main face silhouette
    pygame.draw.ellipse(mask, (255, 255, 255, 44), pygame.Rect(cx - fw//2, cy - fh//2, fw, fh))

    # Horns
    horn_w = int(fw * 0.42)
    horn_h = int(fh * 0.28)
    left_horn = [(cx - int(fw*0.26), cy - int(fh*0.44)),
                 (cx - int(fw*0.52), cy - int(fh*0.64)),
                 (cx - int(fw*0.40), cy - int(fh*0.30))]
    right_horn = [(cx + int(fw*0.26), cy - int(fh*0.44)),
                  (cx + int(fw*0.52), cy - int(fh*0.64)),
                  (cx + int(fw*0.40), cy - int(fh*0.30))]
    pygame.draw.polygon(mask, (255,255,255,58), left_horn)
    pygame.draw.polygon(mask, (255,255,255,58), right_horn)

    # Eyes (stronger darkness)
    eye_w = int(fw * 0.16)
    eye_h = int(fh * 0.10)
    eye_y = cy - int(fh * 0.10)
    pygame.draw.ellipse(mask, (255,255,255,96), pygame.Rect(cx - int(fw*0.18) - eye_w//2, eye_y - eye_h//2, eye_w, eye_h))
    pygame.draw.ellipse(mask, (255,255,255,96), pygame.Rect(cx + int(fw*0.18) - eye_w//2, eye_y - eye_h//2, eye_w, eye_h))

    # Mouth / grin crack
    mx1 = cx - int(fw * 0.20)
    mx2 = cx + int(fw * 0.20)
    my = cy + int(fh * 0.18)
    pygame.draw.line(mask, (255,255,255,86), (mx1, my), (mx2, my), 6)
    pygame.draw.line(mask, (255,255,255,70), (mx1, my), (mx1 - int(fw*0.08), my + int(fh*0.05)), 3)
    pygame.draw.line(mask, (255,255,255,70), (mx2, my), (mx2 + int(fw*0.08), my + int(fh*0.05)), 3)

    # Multiply noise by mask alpha then subtract from bg (darken)
    masked = noise.convert_alpha()
    masked.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    bg.blit(masked, (0, 0), special_flags=pygame.BLEND_RGB_SUB)

def gen_gritty_background(circle_name: str, size: Tuple[int,int], seed: int) -> pygame.Surface:
    """
    Per-circle gritty, faded background for the main scene (behind UI panels).
    Cached by caller.
    """
    W, H = size
    rng = random.Random((hash(circle_name) ^ seed ^ 0x31B7A113) & 0xFFFFFFFF)
    bg = pygame.Surface((W, H))
    style = _circle_style(circle_name)

    # base tint (reds/blacks only)
    if style == "mist":
        top, bot = (18, 4, 8), (6, 1, 2)
    elif style == "storm":
        top, bot = (22, 6, 10), (7, 1, 2)
    elif style == "sludge":
        top, bot = (20, 3, 6), (6, 0, 1)
    elif style == "gold":
        # keep name for compatibility; render as "blooded brass" not yellow
        top, bot = (26, 5, 8), (8, 1, 2)
    elif style == "iron":
        top, bot = (18, 3, 6), (6, 1, 2)
    elif style == "fire":
        top, bot = (30, 4, 8), (9, 1, 2)
    elif style == "ice":
        # frozen hell still stays in the red/black family (cold maroon)
        top, bot = (16, 4, 10), (6, 1, 4)
    else:
        top, bot = (16, 4, 8), (6, 1, 2)

    for y in range(H):
        t = y / max(1, (H - 1))
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        pygame.draw.line(bg, (r, g, b), (0, y), (W, y))

    # overlay scaled noise tile
    tile = _small_noise_tile(rng, 240, 135, alpha=50)
    tile2 = pygame.transform.scale(tile, (W, H))
    bg.blit(tile2, (0, 0))

    # demonic face formed from black static (baked into background)
    overlay_demonic_face(bg, rng)

    # scratches / ash streaks
    scratch = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(220):
        x1 = rng.randrange(-W//4, W)
        y1 = rng.randrange(0, H)
        x2 = x1 + rng.randrange(W//8, W//2)
        y2 = y1 + rng.randrange(-50, 50)
        a = rng.randint(8, 28)
        c = rng.randint(120, 220)
        pygame.draw.line(scratch, (c, max(0, c//12), max(0, c//16), a), (x1, y1), (x2, y2), 1)
    # vignette
    vign = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(14):
        a = int(10 + i * 6)
        pygame.draw.rect(vign, (0, 0, 0, a), pygame.Rect(i*6, i*6, W - i*12, H - i*12), width=6)
    bg.blit(scratch, (0, 0))
    bg.blit(vign, (0, 0))
    return bg

def gen_map_noise(circle_name: str, size: Tuple[int,int], seed: int) -> pygame.Surface:
    """
    Noise + faint "hell cartography" texture for the right-side map panel.
    """
    W, H = size
    rng = random.Random((hash(circle_name) ^ seed ^ 0xA0C0FFEE) & 0xFFFFFFFF)
    s = pygame.Surface((W, H))
    # dark base
    s.fill((8, 2, 4))
    # coarse noise
    tile = _small_noise_tile(rng, 220, 260, alpha=55)
    tile = pygame.transform.scale(tile, (W, H))
    s.blit(tile, (0, 0))

    # "regions" layer: big blood-dark patches and borders so the map reads like territory
    regions = pygame.Surface((W, H), pygame.SRCALPHA)
    region_centers: List[Tuple[int,int,int]] = []
    count = 14 + (abs(hash(circle_name)) % 7)
    for _ in range(count):
        cx = rng.randrange(-W//6, W + W//6)
        cy = rng.randrange(-H//6, H + H//6)
        rad = rng.randrange(int(min(W, H) * 0.10), int(min(W, H) * 0.26))
        col_r = rng.randint(60, 140)
        col = (col_r, rng.randint(0, 18), rng.randint(0, 18), rng.randint(18, 36))
        pygame.draw.circle(regions, col, (cx, cy), rad)
        # border ring (very faint)
        pygame.draw.circle(regions, (200, 30, 45, 12), (cx, cy), rad, 2)
        region_centers.append((cx, cy, rad))
    # add a few long "fault" seams
    for _ in range(10):
        x1 = rng.randrange(-W//3, W + W//3)
        y1 = rng.randrange(0, H)
        x2 = x1 + rng.randrange(int(W*0.4), int(W*0.9)) * (1 if rng.random() < 0.5 else -1)
        y2 = y1 + rng.randrange(-int(H*0.3), int(H*0.3))
        a = rng.randint(18, 35)
        pygame.draw.line(regions, (0, 0, 0, a), (x1, y1), (x2, y2), 3)
        pygame.draw.line(regions, (150, 12, 22, max(8, a-12)), (x1, y1), (x2, y2), 1)
    s.blit(regions, (0, 0))

    # faint contour rings / strata

    # faint contour rings / strata
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(12):
        y = int((i+1) * H / 13)
        a = 18 if i % 2 == 0 else 10
        pygame.draw.line(overlay, (120, 30, 40, a), (0, y), (W, y), 1)
    # ink veins
    for _ in range(90):
        x = rng.randrange(0, W)
        y = rng.randrange(0, H)
        dx = rng.randrange(-120, 120)
        dy = rng.randrange(-120, 120)
        a = rng.randint(10, 26)
        pygame.draw.line(overlay, (0, 0, 0, a), (x, y), (x+dx, y+dy), 1)
    # faded emblem (big circle)
    cx, cy = W//2, int(H*0.62)
    for r in range(int(min(W, H)*0.46), int(min(W, H)*0.25), -12):
        pygame.draw.circle(overlay, (180, 40, 50, 10), (cx, cy), r, 2)

    s.blit(overlay, (0, 0))
    return s

# Item name prettifier (display only)
_ITEM_PRETTY = {
    "mercy_thorn": "Mercy Thorn",
    "black_glass": "Black Glass",
    "wax_seal": "Wax Seal",
    "sealed_index": "Sealed Index",
    "forgiven_page": "Forgiven Page",
    "seal_of_exit": "Seal of Exit",
}

def pretty_item_name(it: str) -> str:
    it = (it or "").strip().lower()
    if it in _ITEM_PRETTY:
        return _ITEM_PRETTY[it]
    return it.replace("_", " ").strip()


def ensure_dirs() -> None:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)



def _safe_clear_dir(p: Path) -> None:
    """Delete contents of a directory, keeping the directory itself."""
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
        return
    for child in p.iterdir():
        try:
            if child.is_dir():
                import shutil
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            # Never crash on cleanup.
            pass

def clean_generated_media(reason: str = "new_story") -> None:
    """
    Auto-clean generated media when a NEW STORY begins.

    Safe policy:
      - Clears BASE_DIR/media (runtime generated)
      - Clears any ./saves/*_media folders (generated sketches tied to saves)
      - NEVER touches user assets (./music, ./assets)
    """
    ensure_dirs()
    _safe_clear_dir(MEDIA_DIR)

    # Clean per-slot media (sketches are generated; can be regenerated on load)
    for p in SAVE_DIR.glob("*_media"):
        if p.is_dir():
            _safe_clear_dir(p)

    # Small marker for testers (not shown in game UI)
    try:
        (MEDIA_DIR / "_clean_marker.txt").write_text(
            f"cleaned_reason={reason}\n"
            f"cleaned_at={datetime.datetime.now().isoformat()}\n",
            encoding="utf-8"
        )
    except Exception:
        pass

def _parse_rid_from_inkblot_filename(name: str) -> str:
    m = re.search(r"inkblot_([^_]+)_", name)
    return m.group(1) if m else ""

def render_inkblot_surface(gs: "GameState", world: Dict[str, "Room"], rid: str, seed: int) -> pygame.Surface:
    """
    Deterministic inkblot renderer used to regenerate missing sketch PNGs during LOAD.
    Uses reds/blacks only, symmetric Rorschach style.
    """
    room = world.get(rid, world[gs.current])
    rng = random.Random(seed)
    style = _circle_style(room.circle + " " + room.name)

    W, H = 960, 540
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    paper_top = (84, 10, 18, 255)
    paper_bot = (16, 2, 4, 255)
    for y in range(H):
        t = y / (H - 1)
        col = (
            int(paper_top[0] * (1 - t) + paper_bot[0] * t),
            int(paper_top[1] * (1 - t) + paper_bot[1] * t),
            int(paper_top[2] * (1 - t) + paper_bot[2] * t),
            255,
        )
        gfxdraw.hline(surf, 0, W - 1, y, col)

    ink = pygame.Surface((W, H), pygame.SRCALPHA)
    base = {
        "mist": (18, 4, 8),
        "storm": (20, 3, 7),
        "sludge": (14, 2, 4),
        "stone": (16, 3, 6),
        "swamp": (14, 2, 4),
        "embers": (26, 4, 6),
        "blood": (22, 3, 6),
        "tar": (10, 1, 2),
        "ice": (16, 3, 7),
    }.get(style, (18, 3, 6))
    accent = {
        "embers": (150, 18, 24),
        "blood": (190, 22, 34),
        "tar": (120, 12, 22),
        "ice": (140, 16, 30),
        "storm": (160, 18, 32),
    }.get(style, (160, 18, 30))

    def splat(x, y, r, a, col):
        c = (col[0], col[1], col[2], a)
        gfxdraw.filled_circle(ink, x, y, r, c)
        gfxdraw.aacircle(ink, x, y, r, c)

    half = W // 2
    core_x = rng.randint(int(half * 0.35), int(half * 0.85))
    core_y = rng.randint(int(H * 0.35), int(H * 0.70))

    for _ in range(220):
        x = int(rng.gauss(core_x, half * 0.18))
        y = int(rng.gauss(core_y, H * 0.18))
        x = max(0, min(half - 1, x))
        y = max(0, min(H - 1, y))
        r = max(1, int(abs(rng.gauss(6.5, 5.0))))
        a = rng.randint(50, 160)
        col = base if rng.random() > 0.12 else accent
        splat(x, y, r, a, col)
        splat(W - 1 - x, y, r, a, col)

    for _ in range(10):
        x = rng.randint(int(half * 0.10), int(half * 0.95))
        y = rng.randint(int(H * 0.10), int(H * 0.90))
        dx = rng.uniform(-1.6, 1.6)
        dy = rng.uniform(-1.6, 1.6)
        steps = rng.randint(70, 170)
        col = base if rng.random() > 0.18 else accent
        for s in range(steps):
            x += dx + rng.uniform(-0.6, 0.6)
            y += dy + rng.uniform(-0.6, 0.6)
            dx = max(-2.8, min(2.8, dx + rng.uniform(-0.35, 0.35)))
            dy = max(-2.8, min(2.8, dy + rng.uniform(-0.35, 0.35)))
            ix = int(max(0, min(half - 1, x)))
            iy = int(max(0, min(H - 1, y)))
            r = 1 + (s // 35)
            a = rng.randint(30, 120)
            splat(ix, iy, r, a, col)
            splat(W - 1 - ix, iy, r, a, col)

    if rng.random() < 0.55:
        eye_y = rng.randint(int(H * 0.30), int(H * 0.55))
        eye_x = rng.randint(int(half * 0.22), int(half * 0.42))
        for rr in range(14, 0, -1):
            a = int(18 + rr * 5)
            col = accent if rr < 6 else base
            splat(eye_x, eye_y, rr, a, col)
            splat(W - 1 - eye_x, eye_y, rr, a, col)

    small = pygame.transform.smoothscale(ink, (W // 3, H // 3))
    ink = pygame.transform.smoothscale(small, (W, H))

    grain_tile = make_grain_tile(rng, 256, 256)
    blit_tiled_grain(surf, grain_tile)

    surf.blit(ink, (0, 0))

    if rng.random() < 0.7:
        vign = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(10):
            pad = 22 + i * 14
            a = 22 + i * 9
            pygame.draw.rect(vign, (0, 0, 0, a), pygame.Rect(pad, pad, W - pad * 2, H - pad * 2), width=6, border_radius=24)
        surf.blit(vign, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

    # Preserve the secret thorn visual-only hint logic on regen.
    secret_hint_rooms = {"blood_archive", "ice_cracks", "frozen_tears"}
    secret_item_room = "thorn_reliquary"
    secret_hint_active = (room.rid in secret_hint_rooms or room.rid == secret_item_room) and (gs.inventory.get("mercy_thorn", 0) <= 0)
    if secret_hint_active:
        glyph = pygame.Surface((W, H), pygame.SRCALPHA)
        cx = W // 2
        top_y = int(H * 0.18)
        bot_y = int(H * 0.82)
        pygame.draw.line(glyph, (230, 225, 235, 90), (cx, top_y), (cx, bot_y), 3)
        for i in range(10):
            t = i / 9.0
            yb = int(top_y * (1 - t) + bot_y * t)
            dx = int(22 + 18 * math.sin(t * math.pi))
            pygame.draw.line(glyph, (230, 225, 235, 70), (cx, yb), (cx + dx, yb - 8), 2)
            pygame.draw.line(glyph, (230, 225, 235, 70), (cx, yb), (cx - dx, yb - 8), 2)
        pygame.draw.circle(glyph, (180, 40, 50, 55), (cx, int(H * 0.72)), 14, 2)
        surf.blit(glyph, (0, 0))

    return surf

def regenerate_missing_media(gs: "GameState", world: Dict[str, "Room"]) -> None:
    """
    If generated sketch PNGs referenced by the journal are missing (because media was cleaned),
    regenerate them deterministically so LOAD is self-healing.
    """
    ensure_dirs()
    changed = False
    for ln in list(gs.log):
        if not ln.startswith(INTERNAL_ILLUSTRATION_TAG):
            continue
        meta_json = ln[len(INTERNAL_ILLUSTRATION_TAG):].strip()
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except Exception:
            meta = {}
        path = str(meta.get("path", "")).strip()
        if not path:
            continue
        pth = Path(path)
        if not pth.is_absolute():
            pth = (BASE_DIR / pth).resolve()
        if pth.exists():
            continue

        # Try to recover room id from meta or filename
        rid = str(meta.get("rid", "")).strip() or _parse_rid_from_inkblot_filename(pth.name) or gs.current

        # Deterministic seed for regen (stable across machines)
        seed = int(meta.get("seed", 0)) if isinstance(meta.get("seed", 0), int) and int(meta.get("seed", 0)) != 0 else None
        if seed is None:
            seed = (gs.rng_seed ^ (hash(rid) & 0x7FFFFFFF) ^ 0x3D2E1B) & 0x7FFFFFFF

        # Ensure parent
        pth.parent.mkdir(parents=True, exist_ok=True)
        try:
            surf = render_inkblot_surface(gs, world, rid, seed)
            pygame.image.save(surf, pth.as_posix())
            changed = True
        except Exception:
            # If regen fails, keep missing placeholder (do not crash load)
            pass

    if changed:
        gs.log_version += 1

def write_crash_log(exc: BaseException) -> Path:
    ensure_dirs()
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    p = LOG_DIR / f"crash_{ts}.txt"
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    p.write_text(tb, encoding="utf-8")
    return p


# ----------------------------
# Music (drop files into ./music)
# ----------------------------

def init_music() -> None:
    '''
    Loads the first audio file found in MUSIC_DIR and loops it.
    Supported by pygame mixer depending on system codecs: .ogg/.wav are safest; .mp3 often works.
    '''
    try:
        pygame.mixer.init()
    except Exception:
        # Don't hard-fail if audio isn't available.
        return

    try:
        files = []
        for ext in ("*.ogg", "*.wav", "*.mp3"):
            files.extend(sorted(MUSIC_DIR.glob(ext)))
        if not files:
            return

        track = files[0]
        pygame.mixer.music.load(track.as_posix())
        pygame.mixer.music.set_volume(0.35)
        pygame.mixer.music.play(-1)  # loop forever
    except Exception:
        # Audio failures should not crash the game.
        return

class RNG:
    def __init__(self, seed: int, calls: int = 0):
        self.seed = seed
        self.calls = calls
        self._rng = random.Random(seed)
        for _ in range(calls):
            self._rng.random()

    def randint(self, a: int, b: int) -> int:
        self.calls += 1
        return self._rng.randint(a, b)

    def random(self) -> float:
        self.calls += 1
        return self._rng.random()

    def choice(self, seq):
        self.calls += 1
        return self._rng.choice(seq)

def gs_rng(gs: "GameState") -> RNG:
    return RNG(gs.rng_seed, gs.rng_calls)

def commit_rng(gs: "GameState", rng: RNG) -> None:
    gs.rng_calls = rng.calls

@dataclass
class Encounter:
    key: str
    name: str
    kind: str  # "combat" or "block"
    hp: int = 0
    atk: int = 0
    defense: int = 0
    intro: str = ""
    victory: str = ""
    defeat: str = ""
    loot: Dict[str, int] = field(default_factory=dict)
    blocks_exits: List[str] = field(default_factory=list)
    requires_item: Optional[str] = None
    consume_item: bool = False

@dataclass
class Room:
    rid: str
    circle: str
    name: str
    desc: str
    exits: Dict[str, str] = field(default_factory=dict)
    npcs: Dict[str, List[str]] = field(default_factory=dict)
    items: Dict[str, int] = field(default_factory=dict)
    encounter: Optional[Encounter] = None
    pos: Tuple[int, int] = (0, 0)

@dataclass
class Player:
    hp: int = 30
    hp_max: int = 30
    atk: int = 7
    defense: int = 3
    resolve: int = 10
    gold: int = 0

@dataclass
class GameState:
    current: str
    previous: Optional[str] = None
    visited: set = field(default_factory=set)
    discovered: set = field(default_factory=set)
    resolved_encounters: set = field(default_factory=set)
    inventory: Dict[str, int] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    log_version: int = 0
    story: List[str] = field(default_factory=list)
    story_version: int = 0
    codex: Dict[str, str] = field(default_factory=dict)
    objectives: List[str] = field(default_factory=list)
    chapters: List[Tuple[str, str, str]] = field(default_factory=list)
    player: Player = field(default_factory=Player)
    in_combat: bool = False
    combat_enemy: Optional[Encounter] = None
    guard_next: bool = False
    rng_seed: int = 123456
    rng_calls: int = 0
    # Illustration (generated when SKETCH is pressed)
    last_illustration_path: str = ""
    last_illustration_caption: str = ""
    show_illustration_overlay: bool = False

    # Narrative / endings (positive = mercy; negative = taint)
    merit: int = 0
    pending_event: str = ""

    # Persistent per-room items (so saves don't respawn loot)
    room_items: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Recent ambient lines (to reduce repetition)
    recent_ambient: List[str] = field(default_factory=list)

    menu: str = ""
    menu_version: int = 0

    def to_json(self) -> dict:
        return {
            "current": self.current,
            "previous": self.previous,
            "visited": sorted(list(self.visited)),
            "discovered": sorted(list(self.discovered)),
            "resolved_encounters": sorted(list(self.resolved_encounters)),
            "inventory": self.inventory,
            "flags": self.flags,
            "log": self.log[-4000:],
            "story": self.story[-15000:],
            "codex": self.codex,
            "objectives": self.objectives[-2000:],
            "chapters": self.chapters[-1200:],
            "player": self.player.__dict__,
            "in_combat": self.in_combat,
            "combat_enemy": (self.combat_enemy.__dict__ if self.combat_enemy else None),
            "guard_next": self.guard_next,
            "rng_seed": self.rng_seed,
            "rng_calls": self.rng_calls,
            "last_illustration_path": self.last_illustration_path,
            "last_illustration_caption": self.last_illustration_caption,
            "merit": self.merit,
            "pending_event": self.pending_event,
            "room_items": self.room_items,
            "recent_ambient": self.recent_ambient[-50:],
        }

    @staticmethod
    def from_json(d: dict) -> "GameState":
        gs = GameState(current=d["current"], previous=d.get("previous"))
        gs.visited = set(d.get("visited", []))
        gs.discovered = set(d.get("discovered", []))
        gs.resolved_encounters = set(d.get("resolved_encounters", []))
        gs.inventory = dict(d.get("inventory", {}))
        gs.flags = dict(d.get("flags", {}))
        gs.log = list(d.get("log", []))
        gs.story = list(d.get("story", []))
        gs.codex = dict(d.get("codex", {}))
        gs.objectives = list(d.get("objectives", []))
        gs.chapters = list(d.get("chapters", []))
        p = d.get("player", {})
        gs.player = Player(
            hp=int(p.get("hp", 30)),
            hp_max=int(p.get("hp_max", 30)),
            atk=int(p.get("atk", 7)),
            defense=int(p.get("defense", 3)),
            resolve=int(p.get("resolve", 10)),
            gold=int(p.get("gold", 0)),
        )
        gs.in_combat = bool(d.get("in_combat", False))
        enemy = d.get("combat_enemy")
        gs.combat_enemy = Encounter(**enemy) if enemy else None
        gs.guard_next = bool(d.get("guard_next", False))
        gs.rng_seed = int(d.get("rng_seed", 123456))
        gs.rng_calls = int(d.get("rng_calls", 0))
        gs.last_illustration_path = str(d.get("last_illustration_path", ""))
        gs.last_illustration_caption = str(d.get("last_illustration_caption", ""))
        gs.merit = int(d.get("merit", 0))
        gs.pending_event = str(d.get("pending_event", ""))
        gs.room_items = dict(d.get("room_items", {}))
        gs.recent_ambient = list(d.get("recent_ambient", []))
        gs.show_illustration_overlay = False
        gs.menu = ""
        gs.menu_version = 0
        gs.log_version = 0
        gs.story_version = 0
        return gs

# Hidden exits until flag is set
HIDDEN_EXIT_FLAGS: Dict[str, Dict[str, str]] = {
    "lucifer_pit": {"ascent": "ascent_revealed"},
    "ascent_tunnel": {"surface": "ascent_revealed"},
    "hall_of_names": {"archive": "archive_revealed"},
    "ice_cracks": {"reliquary": "reliquary_revealed"},
}

def exit_is_visible(gs: GameState, room_id: str, exit_label: str) -> bool:
    rules = HIDDEN_EXIT_FLAGS.get(room_id)
    if not rules or exit_label not in rules:
        return True
    return bool(gs.flags.get(rules[exit_label], False))

def add_log(gs: GameState, text: str) -> None:
    for ln in text.split("\n"):
        gs.log.append(ln.rstrip())
    gs.log = gs.log[-5000:]
    gs.log_version += 1

def add_story(gs: GameState, text: str) -> None:
    for ln in text.split("\n"):
        gs.story.append(ln.rstrip())
    gs.story = gs.story[-20000:]
    gs.story_version += 1

def add_codex(gs: GameState, title: str, body: str) -> None:
    if title not in gs.codex:
        gs.codex[title] = body
        add_log(gs, f"📜 Codex: {title}")

def push_objective(gs: GameState, text: str) -> None:
    if not gs.objectives or gs.objectives[-1] != text:
        gs.objectives.append(text)
        add_log(gs, f"◆ Objective: {text}")

def can_use_exit(gs: GameState, room: Room, exit_label: str) -> bool:
    enc = room.encounter
    if enc and enc.key not in gs.resolved_encounters and enc.blocks_exits:
        return exit_label not in enc.blocks_exits
    return True

def format_exits(room: Room, gs: GameState) -> str:
    # Exits are shown via MOVE buttons (not printed in the journal).
    return ""

def build_world() -> Dict[str, Room]:
    # Expanded map placements (right panel)
    map_left, map_top, map_w, map_h = 1220, 60, 660, 800
    MAX_ROWS = 26  # keep all nodes inside the map panel
    def pos(row: int, col: int, cols: int = 7) -> Tuple[int,int]:
        # Start the journey near the bottom of the map and climb upward as row increases.
        t = max(0.0, min(1.0, row / float(MAX_ROWS)))
        y = map_top + int((map_h - 120) * (1.0 - t)) + 60
        x = map_left + int(map_w * ((col + 1) / (cols + 1)))
        return (x, y)

    rooms: Dict[str, Room] = {}
    def add(r: Room): rooms[r.rid] = r

    # ---- Antechamber
    add(Room("gate","Antechamber","The Gate of Hell",
             "A towering arch bears a warning carved in stone.\nBeyond it: a descent arranged with merciless logic.",
             exits={"forward":"vestibule"}, npcs={"stone_inscription":["The words are not a threat so much as a verdict."]}, pos=pos(0,4)))
    add(Room("vestibule","Antechamber","The Vestibule",
             "Here rush the uncommitted. A blank banner whips forever; stinging insects drive them onward.",
             exits={"back":"gate","to_acheron":"acheron_bank","west":"banner_field"},
             encounter=Encounter("wasps_vestibule","Swarm of Stinging Insects","combat",hp=10,atk=4,defense=1,
                                intro="A swarm descends in a furious cloud—needles of pain in the air.",
                                victory="The swarm breaks apart and scatters into the dimness.",
                                defeat="The swarm overwhelms you; you stagger back, bleeding and shaken.",
                                loot={"bandage":1}),
             pos=pos(1,4)))
    add(Room("banner_field","Antechamber","The Blank Banner Field",
             "A featureless standard snaps in the wind. The uncommitted chase it in circles.",
             exits={"east":"vestibule","south":"acheron_bank"}, items={"torn_thread":1}, pos=pos(1,2)))
    add(Room("acheron_bank","Antechamber","The Bank of Acheron",
             "Black water slides without reflection. A ferryman watches. A coin glints in the mud.",
             exits={"north":"banner_field","back":"vestibule","boat":"acheron_crossing","down":"limbo_meadow"},
             npcs={"charon":["Charon’s eyes burn like coals. “Do not think to cross,” he snarls—yet the skiff rocks."]},
             items={"charons_coin":1}, pos=pos(2,5)))
    add(Room("acheron_crossing","Antechamber","On Charon's Skiff",
             "The boat cuts the current. The air is colder here; the shore fades behind.",
             exits={"land":"limbo_meadow"}, pos=pos(2,6)))

    # ---- Circle I: Limbo
    add(Room("limbo_meadow","Circle I — Limbo","The Meadow of Limbo",
             "A gentle gloom. No screams—only the ache of an unfulfilled horizon.",
             exits={"up":"acheron_bank","east":"castle_reason","west":"quiet_colonnade","south":"minos_threshold"},
             npcs={"the_poets":["A quiet company walks the dusk: voices of antiquity, lit by intellect rather than sun."]},
             pos=pos(3,5)))
    add(Room("quiet_colonnade","Circle I — Limbo","The Quiet Colonnade",
             "Stone pillars hold up nothing but air. A low table offers water that cannot bless—but can steady.",
             exits={"east":"limbo_meadow","south":"scribe_table"}, items={"ration":1}, pos=pos(3,2)))
    add(Room("scribe_table","Circle I — Limbo","The Scribe's Table",
             "A writing desk under a lamp that never sputters. Here, memory is currency.",
             exits={"north":"quiet_colonnade","east":"castle_reason"}, npcs={"scribe":["“If you keep a record, you keep a self.”"]},
             items={"ink_of_remembrance":1}, pos=pos(4,2)))
    add(Room("castle_reason","Circle I — Limbo","The Castle of Reason",
             "Seven walls, seven gates: a fortress built of human excellence—honored, yet still incomplete.",
             exits={"west":"limbo_meadow","south":"limbo_poets_walk","east":"hall_of_names"},
             npcs={"ovid":["“Every descent remakes the traveler.”"]}, pos=pos(3,4)))
    add(Room("hall_of_names","Circle I — Limbo","The Hall of Names",
             "A corridor inscribed with names that refuse oblivion.",
             exits={"west":"castle_reason","south":"limbo_poets_walk","archive":"blood_archive"}, items={"wax_seal":1}, pos=pos(3,6)))
    add(Room("limbo_poets_walk","Circle I — Limbo","The Poets' Walk",
             "You walk among names that outlast empires. Their talk is measured, precise.",
             exits={"north":"castle_reason","west":"limbo_meadow","south":"minos_threshold"}, pos=pos(4,4)))

    # ---- Minos gate to Circle II
    add(Room("minos_threshold","Threshold","Minos' Judgment",
             "A judge coils his tail to decree each soul’s descent. Verdicts become motion.",
             exits={"north":"limbo_meadow","east":"minos_antechamber","down":"lust_hub"},
             npcs={"minos":["Minos studies you. His tail twitches, counting what you will not confess aloud."]},
             encounter=Encounter("minos_test","Minos' Appraisal","block",
                                intro="Minos blocks your descent, demanding clarity of purpose.",
                                victory="Minos releases the way. The descent is open.",
                                defeat="Minos does not move. You remain on the threshold.",
                                blocks_exits=["down"], requires_item="ink_of_remembrance", consume_item=False),
             pos=pos(5,4)))
    add(Room("minos_antechamber","Threshold","Antechamber of Judgments",
             "A narrow space where verdicts hang in the air. Scratches in stone suggest others pleaded here.",
             exits={"west":"minos_threshold"}, items={"bandage":1}, pos=pos(5,6)))

    # ---- Circle II: Lust
    add(Room("lust_hub","Circle II — Lust","The Storm's Verge",
             "A hurricane without season tears souls through darkness. No solid ground—only consequence.",
             exits={"up":"minos_threshold","east":"francesca_whirl","west":"whisper_gallery","south":"lust_gate"},
             pos=pos(6,4)))
    add(Room("whisper_gallery","Circle II — Lust","The Whisper Gallery",
             "A ledge where voices trade promises like currency. Temptation is polite here.",
             exits={"east":"lust_hub","south":"tempest_lens"}, npcs={"whispers":["“Desire is not a sin—only its throne.”"]},
             items={"storm_charm":1}, pos=pos(6,2)))
    add(Room("tempest_lens","Circle II — Lust","The Tempest Lens",
             "A shard of glass catches the storm and bends it. For a moment, you see faces inside the wind.",
             exits={"north":"whisper_gallery","east":"francesca_whirl"}, items={"silver_ribbon":1}, pos=pos(7,2)))
    add(Room("francesca_whirl","Circle II — Lust","Francesca's Whirl",
             "Two shades spiral together, a tragic orbit—love mistaken for absolution.",
             exits={"west":"lust_hub","south":"tempest_lens"}, npcs={"francesca":["“There is no greater sorrow than to recall a happy time in misery.”"]},
             pos=pos(6,6)))
    add(Room("lust_gate","Circle II — Lust","The Gale Stair",
             "A downward stair appears only when the storm agrees you are finished here.",
             exits={"north":"lust_hub","down":"gluttony_hub"},
             encounter=Encounter("lust_gate","Storm's Consent","block",
                                intro="The wind denies the stairs. It demands a token of restraint.",
                                victory="The wind loosens. A stair forms out of air and shadow.",
                                defeat="The gale throws you back. The stair does not form.",
                                blocks_exits=["down"], requires_item="silver_ribbon", consume_item=True),
             pos=pos(7,4)))

    # ---- Circle III: Gluttony
    add(Room("gluttony_hub","Circle III — Gluttony","The Mire of Cold Rain",
             "Endless rain, foul and heavy. The ground is a slurry of appetite.",
             exits={"up":"lust_gate","east":"cerberus_maw","west":"ciacco_hollow","south":"gluttony_gate"},
             items={"mud_clod":1}, pos=pos(8,4)))
    add(Room("ciacco_hollow","Circle III — Gluttony","Ciacco's Hollow",
             "A shape in the sludge speaks as if prophecy were a snack.",
             exits={"east":"gluttony_hub","south":"drainage_runnel"}, npcs={"ciacco":["“Cities rot,” he says, “quietly, then all at once.”"]},
             items={"ration":1}, pos=pos(8,2)))
    add(Room("drainage_runnel","Circle III — Gluttony","The Drainage Runnel",
             "A narrow runnel where filth gathers into thicker darkness. Something glints: not gold, but its idea.",
             exits={"north":"ciacco_hollow","east":"greed_side_entry"}, items={"greasy_token":1}, pos=pos(9,2)))
    add(Room("cerberus_maw","Circle III — Gluttony","Cerberus' Maw",
             "A three-throated beast rends the mire with hunger. Want made flesh.",
             exits={"west":"gluttony_hub","south":"greed_side_entry"},
             encounter=Encounter("cerberus","Cerberus","combat",hp=18,atk=6,defense=2,
                                intro="Cerberus lunges, jaws snapping in three directions at once!",
                                victory="Cerberus recoils, snarling, and sinks back into the mire.",
                                defeat="Cerberus bowls you over; you escape bruised and shaken.",
                                loot={"ration":1,"bandage":1,"cerberus_fang":1}),
             pos=pos(8,6)))
    add(Room("greed_side_entry","Boundary","A Slippery Slope",
             "A slick incline drops toward the clamor of stone and shouting. The rain thins. The noise grows.",
             exits={"north":"cerberus_maw","west":"drainage_runnel","down":"greed_hub"}, pos=pos(9,4)))
    add(Room("gluttony_gate","Circle III — Gluttony","The Sour Stair",
             "A stair of compacted filth leads down. It demands proof you faced appetite—and survived it.",
             exits={"north":"gluttony_hub","down":"greed_hub"},
             encounter=Encounter("gluttony_gate","Sour Stair's Toll","block",
                                intro="The stair resists. It demands a token torn from hunger.",
                                victory="The stair yields. You descend into heavier stone and voices.",
                                defeat="You cannot find footing. The stair holds you here.",
                                blocks_exits=["down"], requires_item="cerberus_fang", consume_item=False),
             pos=pos(9,6)))

    # ---- Circle IV: Greed
    add(Room("greed_hub","Circle IV — Greed","The Rolling Weights",
             "Two crowds slam immense stones against each other. Hoarding and squandering—twin distortions of value.",
             exits={"up":"gluttony_gate","north":"greed_side_entry","west":"misers_gallery","east":"spendthrifts_run","south":"greed_gate"},
             pos=pos(10,4)))
    add(Room("misers_gallery","Circle IV — Greed","The Misers' Gallery",
             "A corridor lined with locked chests. The locks are on the inside.",
             exits={"east":"greed_hub","south":"plutus_roar"}, items={"bandage":1}, pos=pos(10,2)))
    add(Room("spendthrifts_run","Circle IV — Greed","The Spendthrifts' Run",
             "Coins scatter like gravel. To waste is to worship the moment and despise the future.",
             exits={"west":"greed_hub","south":"plutus_roar"}, items={"gold_dust":1}, pos=pos(10,6)))
    add(Room("plutus_roar","Circle IV — Greed","Plutus' Roar",
             "A guardian snarls in a broken tongue. Greed has made language into noise.",
             exits={"north":"misers_gallery","east":"spendthrifts_run","west":"greed_hub"},
             encounter=Encounter("plutus","Plutus","combat",hp=16,atk=7,defense=3,
                                intro="Plutus charges—rage and appetite for possession!",
                                victory="Plutus collapses; the roar fades into hollow echo.",
                                defeat="You fend him off and stagger away, the roar ringing in your skull.",
                                loot={"gold":15,"plutus_token":1}),
             pos=pos(11,4)))
    add(Room("greed_gate","Circle IV — Greed","The Counting Step",
             "A step marked with tally strokes. To descend, you must pay with proof you resisted Greed.",
             exits={"north":"greed_hub","down":"wrath_hub"},
             encounter=Encounter("greed_gate","The Counting Step","block",
                                intro="The step refuses you. It demands a token taken from Greed itself.",
                                victory="The step accepts the token. The world sinks into swampy rage.",
                                defeat="The step holds. You are not finished here.",
                                blocks_exits=["down"], requires_item="plutus_token", consume_item=True),
             pos=pos(12,4)))

    # ---- Circle V: Wrath
    add(Room("wrath_hub","Circle V — Wrath","The Stygian Marsh",
             "A swamp of anger. The wrathful tear at each other; the sullen sink beneath the slime.",
             exits={"up":"greed_gate","east":"phlegyas_skiff","west":"sullen_reach","south":"dis_gate"},
             pos=pos(13,4)))
    add(Room("sullen_reach","Circle V — Wrath","The Sullen Reach",
             "Bubbles rise from below as if the mud itself is trying to speak.",
             exits={"east":"wrath_hub","south":"sunken_words"}, items={"stygian_shard":1}, pos=pos(13,2)))
    add(Room("sunken_words","Circle V — Wrath","The Sunken Words",
             "A submerged alcove where murmurs cling to stone. A broken oar lies here.",
             exits={"north":"sullen_reach","east":"phlegyas_skiff"}, items={"stygian_oar":1}, pos=pos(14,2)))
    add(Room("phlegyas_skiff","Circle V — Wrath","Phlegyas' Skiff",
             "A boatman of fury rows as if every stroke is an insult. Across the marsh, the iron city: Dis.",
             exits={"west":"wrath_hub","north":"sunken_words"}, npcs={"phlegyas":["“Hurry!” he barks, though there is nowhere to be that is not here."]},
             pos=pos(13,6)))
    add(Room("dis_gate","Boundary","The Gates of Dis",
             "Walls loom. The air tastes metallic. The gate answers only to a ferryman’s token.",
             exits={"north":"wrath_hub","east":"watchers_wall","down":"heresy_hub"},
             encounter=Encounter("dis_gate","Fallen Watchers","block",
                                intro="Fallen watchers bar the way. The gate answers only to a ferryman’s token.",
                                victory="The iron gives. The city of Dis admits you into hotter stone.",
                                defeat="The watchers jeer. The gate does not move.",
                                blocks_exits=["down"], requires_item="stygian_oar", consume_item=True),
             pos=pos(14,4)))
    add(Room("watchers_wall","Boundary","The Watchers' Wall",
             "A wall of iron plates hammered with old names. Your reflection looks like regret.",
             exits={"west":"dis_gate"}, items={"bandage":1}, pos=pos(14,6)))

    # ---- Circle VI: Heresy
    add(Room("heresy_hub","Circle VI — Heresy","Flaming Tombs",
             "Sepulchers glow red, lids half-open as if the dead cannot stay contained.",
             exits={"up":"dis_gate","east":"farinata_sep","west":"epicurean_row","south":"violence_gate"},
             pos=pos(15,4)))
    add(Room("epicurean_row","Circle VI — Heresy","Epicurean Row",
             "Tombs stretch like a neighborhood of stubborn claims. Voices argue about endings while flames argue back.",
             exits={"east":"heresy_hub","south":"cinders_alley"}, npcs={"heretic":["“Nothing survives,” the shade insists, even as it screams."]},
             pos=pos(15,2)))
    add(Room("cinders_alley","Circle VI — Heresy","Cinders Alley",
             "Ash collects in drifts. A ember still pulses, refusing to be only a remnant.",
             exits={"north":"epicurean_row","east":"farinata_sep"}, items={"ember_shard":1}, pos=pos(16,2)))
    add(Room("farinata_sep","Circle VI — Heresy","Farinata's Sepulcher",
             "A proud shade rises from flame to speak of honor and stubborn vision.",
             exits={"west":"heresy_hub","south":"cinders_alley"}, npcs={"farinata":["“What you call the future is already half ash.”"]},
             pos=pos(15,6)))
    add(Room("violence_gate","Circle VI — Heresy","The Cracked Ramp",
             "A cracked ramp falls away into darker violence. Only fire-touched proof will open the path.",
             exits={"north":"heresy_hub","down":"violence_hub"},
             encounter=Encounter("violence_gate","Ramp of Proof","block",
                                intro="The ramp rejects you. It demands a shard of living ember.",
                                victory="The ember’s heat answers the stone. The ramp releases you downward.",
                                defeat="The stone stays cold. You cannot descend yet.",
                                blocks_exits=["down"], requires_item="ember_shard", consume_item=True),
             pos=pos(16,4)))

    # ---- Circle VII: Violence
    add(Room("violence_hub","Circle VII — Violence","Minotaur's Pass",
             "Broken rock descends sharply. A beast paces—rage made labyrinth.",
             exits={"up":"violence_gate","east":"phlegethon_river","west":"blood_scree","south":"suicides_wood"},
             encounter=Encounter("minotaur","The Minotaur","combat",hp=22,atk=8,defense=3,
                                intro="The Minotaur bellows and charges, hooves striking sparks from stone!",
                                victory="The beast staggers back. You slip past into deeper violence.",
                                defeat="You evade the horns and retreat, shaken.",
                                loot={"bandage":1}),
             pos=pos(17,4)))
    add(Room("blood_scree","Circle VII — Violence","The Blood Scree",
             "A slope of red stone where old battles echo. A centaur’s arrow is lodged here—still warm.",
             exits={"east":"violence_hub","south":"phlegethon_river"}, items={"centaur_arrow":1}, pos=pos(17,2)))
    add(Room("phlegethon_river","Circle VII — Violence","The River of Blood",
             "A boiling river carries the violent against others. Centaurs patrol with bows, enforcing measure.",
             exits={"west":"violence_hub","east":"blasphemers_sand","south":"geryon_cliff"},
             npcs={"centaur":["“Bring proof you did not come only to watch.”"]},
             pos=pos(17,6)))
    add(Room("suicides_wood","Circle VII — Violence","The Wood of the Suicides",
             "A forest of thorned trees, bark bruised with trapped voices. Harpies tear at leaves.",
             exits={"north":"violence_hub","east":"blasphemers_sand"},
             encounter=Encounter("harpies","Harpies","combat",hp=16,atk=7,defense=2,
                                intro="Harpies swoop down, talons raking, voices laughing without joy!",
                                victory="The harpies scatter to higher branches, cursing as they go.",
                                defeat="You fend them off, bleeding, and stumble out of the thorns.",
                                loot={"ration":1,"feather_black":1}),
             pos=pos(18,4)))
    add(Room("blasphemers_sand","Circle VII — Violence","The Burning Sand",
             "A desert of scorching sand under a rain of fire. Each defiance becomes its own cell.",
             exits={"west":"phlegethon_river","north":"suicides_wood","south":"geryon_cliff"}, items={"charred_coin":1}, pos=pos(18,6)))
    add(Room("geryon_cliff","Transition","Geryon's Cliff",
             "A monstrous figure waits—honest face, serpentine body: fraud in a single shape.\nThe drop below is vast: Malebolge.",
             exits={"north":"phlegethon_river","west":"blasphemers_sand","ride":"malebolge_rim"},
             encounter=Encounter("geryon","Geryon","block",
                                intro="Geryon refuses to carry you. It demands a marked passage—permission earned, not claimed.",
                                victory="Geryon coils and offers passage. You descend into Malebolge.",
                                defeat="Geryon remains still, waiting for steadier proof.",
                                blocks_exits=["ride"], requires_item="centaur_pass", consume_item=False),
             pos=pos(19,5)))

    # ---- Circle VIII: Fraud (Malebolge) + side bridgework + fraud_mark
    add(Room("malebolge_rim","Circle VIII — Fraud","The Rim of Malebolge",
             "A vast, concentric structure of ditches and bridges. Demons patrol with administrative cruelty.",
             exits={"up":"geryon_cliff","bolgia1":"bolgia_seducers","west":"bridgework"}, pos=pos(16,6)))
    add(Room("bridgework","Circle VIII — Fraud","The Bridgework",
             "A lattice of bridges, each built to look sturdy. The safest route is rarely the obvious one.",
             exits={"east":"malebolge_rim","down":"bolgia_hypocrites","west":"bolgia_diviners"}, items={"fraud_mark":1}, pos=pos(16,4)))

    bolge = [
        ("bolgia_seducers","Bolgia I — Seducers","Forced marching under whips: manipulation made visible."),
        ("bolgia_flatterers","Bolgia II — Flatterers","A ditch of filth: praise sold until it becomes waste."),
        ("bolgia_simonists","Bolgia III — Simoniacs","Inverted burials: feet aflame, holy offices traded like coin."),
        ("bolgia_diviners","Bolgia IV — Diviners","Heads twisted backward: those who claimed foresight now cannot look ahead."),
        ("bolgia_barrators","Bolgia V — Barrators","Boiling pitch and hooked demons: public trust sold for private gain."),
        ("bolgia_hypocrites","Bolgia VI — Hypocrites","Gilded cloaks lined with lead: the weight of appearances."),
        ("bolgia_thieves","Bolgia VII — Thieves","Serpents coil; identities blur: theft as metamorphosis."),
        ("bolgia_counselors","Bolgia VIII — Fraudulent Counselors","Tongues of flame: clever speech that burned others."),
        ("bolgia_discord","Bolgia IX — Sowers of Discord","A blade repeats what schism began: division without end."),
        ("bolgia_falsifiers","Bolgia X — Falsifiers","Disease, stench, frenzy: reality forged until it rots."),
    ]
    for i,(rid,nm,desc) in enumerate(bolge, start=1):
        exits = {}
        if i==1: exits["back"]="malebolge_rim"
        else: exits["prev"]=bolge[i-2][0]
        if i<10: exits["next"]=bolge[i][0]
        else: exits["well"]="giants_well"
        if rid=="bolgia_seducers": exits["bridge"]="bolgia_hypocrites"
        if rid=="bolgia_diviners": exits["bridge"]="bridgework"
        if rid=="bolgia_hypocrites": exits["bridge"]="bridgework"
        if rid=="bolgia_thieves": exits["bridge"]="bolgia_diviners"
        add(Room(rid,"Circle VIII — Fraud",nm,desc,exits=exits,pos=pos(17+(0 if i<=5 else 1), (i%7) or 7)))

    rooms["bolgia_barrators"].encounter = Encounter("malebranche","A Malebranche Demon","combat",hp=20,atk=9,defense=3,
        intro="A hook-bearing demon leaps from the pitch, snarling, “Paperwork!”",
        victory="The demon sinks back into the tar, cursing your refusal to be processed.",
        defeat="The hook catches your sleeve. You tear free, escaping only by luck.",
        loot={"bandage":1,"pitch_talisman":1},
        blocks_exits=["next"])
    rooms["bolgia_thieves"].encounter = Encounter("serpents","Serpents of Theft","combat",hp=14,atk=8,defense=2,
        intro="Serpents strike, and your sense of self wavers for a moment!",
        victory="The serpents retreat, hissing as if offended by your persistence.",
        defeat="Your grip on yourself loosens; you stumble back before it becomes total.",
        loot={"ration":1,"scale_shard":1},
        blocks_exits=["next"])
    rooms["bolgia_diviners"].npcs = {"diviner":["“Seeking certainty is its own deception.”"]}
    rooms["bolgia_hypocrites"].items = {"lead_cloak_thread":1}
    rooms["bolgia_flatterers"].items = {"soapstone":1}

    # ---- Giants Well (gate to Circle IX requires fraud_mark)
    add(Room("giants_well","Transition","The Well of Giants",
             "A pit lined with towering figures half-buried in stone. A narrow descent leads into ice: treachery.",
             exits={"up":"bolgia_falsifiers","down":"caina","west":"giant_runes"},
             encounter=Encounter("nimrod","Nimrod's Babble","block",
                                intro="A giant’s shadow blocks the way. It will only yield to a mark of Fraud’s domain.",
                                victory="The giant withdraws, and the cold below breathes upward.",
                                defeat="You cannot pass. The giant’s presence is immovable.",
                                blocks_exits=["down"], requires_item="fraud_mark", consume_item=False),
             pos=pos(20,6)))
    add(Room("giant_runes","Transition","Runes of the Giants",
             "Carved symbols like broken sentences. Even here, pride clings to language.",
             exits={"east":"giants_well"}, items={"bandage":1}, pos=pos(20,4)))

    # ---- Circle IX: Treachery + hidden exit
    add(Room("caina","Circle IX — Treachery","Caina (Against Kin)",
             "Ice, not fire. Betrayal is cold because it is calculated.",
             exits={"up":"giants_well","east":"antenora","west":"ice_cracks","down":"judecca"}, pos=pos(21,6)))
    add(Room("ice_cracks","Circle IX — Treachery","Cracks in Cocytus",
             "The ice shivers with old regrets. Something sharp rests in a crack: black glass.",
             exits={"east":"caina","south":"frozen_tears","reliquary":"thorn_reliquary"}, items={"black_glass":1}, pos=pos(21,4)))
    add(Room("thorn_reliquary","Circle IX — Treachery","The Thorn Reliquary",
             "Behind the crack: a pocket of air that should not exist. A pale thorn hangs in the ice like a memory refusing to freeze.\n"
             "The walls sweat black brine. Something here does not belong to Hell.",
             exits={"back":"ice_cracks"},
             items={"mercy_thorn":1},
             pos=pos(22,3)))
    add(Room("frozen_tears","Circle IX — Treachery","Frozen Tears",
             "Tears freeze in the eye before they can fall. Even sorrow is captured here.",
             exits={"north":"ice_cracks","east":"ptolomea"}, items={"ration":1}, pos=pos(22,4)))
    add(Room("antenora","Circle IX — Treachery","Antenora (Against Country)",
             "Faces frozen mid-plea. The ice holds every word that came too late.",
             exits={"west":"caina","east":"ptolomea"}, pos=pos(21,7)))
    add(Room("ptolomea","Circle IX — Treachery","Ptolomea (Against Guests)",
             "A wind skates across the ice. Hospitality is inverted into ambush.",
             exits={"west":"antenora","south":"judecca","west2":"frozen_tears"}, pos=pos(22,7)))
    add(Room("judecca","Circle IX — Treachery","Judecca (Against Benefactors)",
             "The deepest ice. Bodies are entirely encased, stripped even of posture.",
             exits={"up":"caina","down":"lucifer_pit"}, pos=pos(23,6)))
    add(Room("lucifer_pit","Circle IX — Treachery","The Pit of Lucifer",
             "At the center: a colossal figure, frozen to the waist, wings beating a wind that sustains the ice.",
             exits={"up":"judecca","ascent":"ascent_tunnel"},
             encounter=Encounter("lucifer","Lucifer (The Frozen King)","combat",hp=28,atk=11,defense=3,
                                intro="The air fractures. Lucifer’s wings thunder, and the cold becomes a weapon.",
                                victory="The wind stills for a heartbeat. Something in the ice shifts—as if it can be opened.",
                                defeat="The cold drives into your bones. You retreat, alive only by chance.",
                                loot={"seal_of_exit":1}),
             pos=pos(24,6)))
    add(Room("ascent_tunnel","The Hidden Way","The Narrow Ascent",
             "A passage no map would admit. This is not victory—it is escape, which is rarer.",
             exits={"back":"lucifer_pit","surface":"surface_end"}, pos=pos(24,4)))
    add(Room("surface_end","The World Above","The Starlit Exit",
             "You emerge into air that is not owned by Hell. The stars look colder than you remembered, but they are yours to name again.",
             exits={"back":"ascent_tunnel","beyond":"heaven_threshold"}, pos=pos(24,2)))

    # ---- Secret Archive (hidden until you "touch" the Hall of Names)
    add(Room("blood_archive","Circle I — Limbo","The Blood Archive",
             "A door of pressed parchment opens into shelves that should not fit inside any wall.\n"
             "Books breathe. Ink moves like insects. Names are stitched into the spines with thread that looks too much like vein.",
             exits={"back":"hall_of_names","down":"minos_threshold"},
             encounter=Encounter("archivist","The Archivist of Names","combat",hp=18,atk=7,defense=2,
                                intro="A librarian-shade unfolds from the stacks, face ink-blurred, hands full of hooks made of quills.",
                                victory="The Archivist collapses into loose pages. A book falls open—your name is inside, written in a stranger’s hand.",
                                defeat="The Archivist drives you back with quill-hooks; the shelves seem to lean closer.",
                                loot={"forgiven_page":1,"bandage":1}),
             items={"sealed_index":1},
             npcs={"murmuring_catalog":["The shelves whisper: not titles, but confessions. Some are yours."]},
             pos=pos(4,6)))

    # ---- The Empyrean (final plane after escape)
    add(Room("heaven_threshold","The Empyrean","The First Light",
             "Light without heat. Air that does not belong to anyone.\n"
             "Behind you, the world still remembers ice; ahead, the sky looks like an unopened letter.",
             exits={"back":"surface_end","forward":"heaven_hall"},
             npcs={"distant_voice":["“You carried a book into Hell. Do you know why?”"]},
             pos=pos(25,2)))
    add(Room("heaven_hall","The Empyrean","The Hall of Forgiveness",
             "A vast chamber of pale stone and soft shadow. Nothing here screams—yet everything here remembers screams.",
             exits={"back":"heaven_threshold"},
             npcs={"judgment":["A presence weighs you without touch. The silence is not empty; it is listening."]},
             pos=pos(26,3)))

    return rooms


def init_room_items(gs: GameState, world: Dict[str, Room]) -> None:
    """Apply/initialize per-room item state so saves don't respawn room loot."""
    # If this save predates room_items, it may be empty; initialize from world defaults.
    if not isinstance(gs.room_items, dict):
        gs.room_items = {}
    for rid, room in world.items():
        saved = gs.room_items.get(rid)
        if isinstance(saved, dict):
            # sanitize ints
            room.items = {str(k): int(v) for k, v in saved.items() if int(v) > 0}
        else:
            gs.room_items[rid] = {str(k): int(v) for k, v in room.items.items() if int(v) > 0}

AMBIENT_DETAILS = {
    "mist": [
        "Mist clings to your lashes like unspoken apologies.",
        "Footsteps sound borrowed, as if the air expects them back.",
        "A gentle gloom presses in—comfort shaped like loss.",
    ],
    "storm": [
        "The wind speaks in bites and broken vows.",
        "Something laughs inside the gale, too close to be only sound.",
        "Your thoughts skid like stones across black water.",
    ],
    "sludge": [
        "Rain hits like spit; the ground accepts it hungrily.",
        "The air tastes of old hunger and newer regret.",
        "Every breath is a negotiation with filth.",
    ],
    "stone": [
        "Stone grinds under weight that has never learned to stop.",
        "You hear counting—numbers that measure nothing but obsession.",
        "Metallic dust coats your tongue like a vow made wrong.",
    ],
    "swamp": [
        "Bubbles rise as if the mud is trying to confess.",
        "Anger hangs low, a fog you can inhale by accident.",
        "Something tugs at your ankles—not hands, just resentment.",
    ],
    "embers": [
        "Heat is a language here; it speaks only in punishment.",
        "Ash drifts like snow that forgot how to be clean.",
        "The tombs breathe—a furnace's patience.",
    ],
    "blood": [
        "The air is copper and old battle prayers.",
        "Distant screams arrive late, as if even sound is wounded.",
        "Your shadow looks sharper than it should.",
    ],
    "tar": [
        "The dark has a viscosity, as if it could be ladled.",
        "Hooks scrape somewhere unseen; paperwork becomes pain.",
        "Lies stick to you like pitch, even when you tell the truth.",
    ],
    "ice": [
        "Cold does not bite here—it records.",
        "The ice holds faces the way glass holds fingerprints.",
        "Wind gnaws the world down to intention.",
    ],
}


def choose_ambient_detail(gs: GameState, style: str, rng: RNG) -> str:
    """Pick an ambient line with a small non-repetition window."""
    pool = AMBIENT_DETAILS.get(style) or ["The air changes."]
    recent = set(gs.recent_ambient[-10:]) if hasattr(gs, "recent_ambient") else set()
    cands = [p for p in pool if p not in recent] or list(pool)
    pick = rng.choice(cands)
    try:
        gs.recent_ambient.append(pick)
        if len(gs.recent_ambient) > 24:
            gs.recent_ambient = gs.recent_ambient[-24:]
    except Exception:
        pass
    return pick

ROOM_EVENTS = {
    "hall_of_names": "name_contact",
    "sullen_reach": "sullen_soul",
    "bolgia_flatterers": "filth_oracle",
    "ice_cracks": "black_glass",
}

def trigger_event(gs: GameState, event_id: str, intro: str) -> None:
    if gs.pending_event:
        return
    gs.pending_event = event_id
    set_menu(gs, "event")
    add_log(gs, "—")
    add_log(gs, intro)
    add_story(gs, intro)

def circle_danger_multiplier(room: Room) -> float:
    # very light parser based on circle naming
    name = room.circle.lower()
    if "circle ix" in name or "treachery" in name:
        return 0.22
    if "circle viii" in name or "fraud" in name:
        return 0.18
    if "circle vii" in name or "violence" in name:
        return 0.15
    if "circle vi" in name or "heresy" in name:
        return 0.12
    if "circle v" in name or "wrath" in name:
        return 0.10
    if "circle iv" in name or "greed" in name:
        return 0.08
    if "circle iii" in name or "glutton" in name:
        return 0.06
    if "circle ii" in name or "lust" in name:
        return 0.05
    return 0.03

def maybe_roaming_encounter(gs: GameState, world: Dict[str, Room], rng: RNG) -> None:
    # Only if not already in a room encounter
    if gs.in_combat or gs.combat_enemy:
        return
    # Never start with an ambush on the very first room entry (avoids 'game starts in combat').
    if len(gs.visited) <= 1:
        return
    room = world[gs.current]
    # No roaming fights in the Empyrean / ending zones
    if room.circle.lower().startswith("the empyrean") or room.rid in ("surface_end","heaven_threshold","heaven_hall"):
        return
    base = circle_danger_multiplier(room)
    # If the traveler has acted cruelly, Hell becomes more interested.
    if gs.merit < 0:
        base += 0.06
    # If low HP, reduce frequency (avoid death-spirals)
    if gs.player.hp <= max(6, gs.player.hp_max // 4):
        base *= 0.45
    if rng.random() >= base:
        return

    enemy = rng.choice([
        Encounter("roamer_hook","Hook-Tongued Demon","combat",hp=14,atk=8,defense=2,
                  intro="A thin demon unfolds from shadow, tongue ending in a hook that tastes fear.",
                  victory="It snaps backward into darkness, leaving behind a wet, glittering token.",
                  defeat="It drags you three steps toward nothingness before you tear free.",
                  loot={"bandage":1,"gold":8}),
        Encounter("roamer_wraith","Ink Wraith","combat",hp=12,atk=7,defense=1,
                  intro="Letters crawl out of the air and knit themselves into a figure that hates being read.",
                  victory="The letters scatter like startled insects. A fragment of meaning remains.",
                  defeat="The words wrap your throat; you wrench free, coughing up black spit.",
                  loot={"ration":1}),
        Encounter("roamer_cold","Cocytus Breath","combat",hp=16,atk=9,defense=3,
                  intro="A breath of living cold finds you, shaped like a mouth you can't see.",
                  victory="The cold loses interest, withdrawing into the cracks.",
                  defeat="Your fingers go numb. You stumble away before they stop belonging to you.",
                  loot={"stygian_shard":1}),
    ])

    add_log(gs, f"⚠ Ambush: {enemy.name}")
    add_log(gs, enemy.intro)
    add_story(gs, f"An ambush finds you: {enemy.name}. {enemy.intro}")
    gs.in_combat = True
    gs.combat_enemy = Encounter(**{**enemy.__dict__})

def build_storybook_text(gs: GameState, world: Dict[str, Room]) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = world[gs.current]
    p = gs.player
    lines: List[str] = []
    lines += [APP_TITLE, f"Saved: {now}", "", "BOOK OF DESCENT", "==============", ""]
    lines += [f"Current Location: {cur.circle} — {cur.name}", ""]
    lines += ["The Traveler", "------------",
              f"Health: {p.hp}/{p.hp_max}    Strength: {p.atk}    Defense: {p.defense}    Resolve: {p.resolve}    Gold: {p.gold}    Merit: {gs.merit}", ""]
    lines += ["Inventory", "---------"]
    if gs.inventory:
        for k in sorted(gs.inventory.keys()):
            lines.append(f"- {pretty_item_name(k)} x{gs.inventory[k]}")
    else:
        lines.append("(empty)")
    lines += ["", "Objectives", "----------"]
    if gs.objectives:
        for o in gs.objectives[-40:]:
            lines.append(f"- {o}")
    else:
        lines.append("(none)")
    lines += ["", "Codex", "-----"]
    if gs.codex:
        for t in sorted(gs.codex.keys())[:120]:
            lines.append(f"* {t}")
    else:
        lines.append("(empty)")
    lines += ["", "Table of Chapters", "-----------------"]
    if gs.chapters:
        for i,(c,rm,ts) in enumerate(gs.chapters, start=1):
            lines.append(f"Chapter {i:03d}: {c} — {rm} ({ts})")
    else:
        lines.append("(no chapters yet)")
    lines += ["", "The Story", "---------"]
    lines += [ln for ln in gs.story if not ln.startswith(INTERNAL_ILLUSTRATION_TAG)]
    lines += ["", SAVE_JSON_BEGIN, json.dumps(gs.to_json(), ensure_ascii=False, indent=2), SAVE_JSON_END, ""]
    return "\n".join(lines)

def save_to_slot(gs: GameState, world: Dict[str, Room], slot: str) -> Path:
    ensure_dirs()
    s = slot.strip().lower()
    if s not in SAVE_SLOTS: s = "slot1"
    p = SAVE_DIR / f"{s}.txt"
    p.write_text(build_storybook_text(gs, world), encoding="utf-8")
    return p

def load_from_slot(slot: str) -> GameState:
    ensure_dirs()
    s = slot.strip().lower()
    if s not in SAVE_SLOTS: s = "slot1"
    p = SAVE_DIR / f"{s}.txt"
    if not p.exists():
        raise FileNotFoundError(f"No save found: {p.as_posix()}")
    txt = p.read_text(encoding="utf-8", errors="replace")
    a, b = txt.find(SAVE_JSON_BEGIN), txt.find(SAVE_JSON_END)
    if a == -1 or b == -1 or b <= a:
        raise ValueError("Save file missing embedded JSON state block.")
    d = json.loads(txt[a+len(SAVE_JSON_BEGIN):b].strip())
    return GameState.from_json(d)

def export_pdf_from_slot(slot: str) -> Path:
    """
    Export the storybook TXT to an illustrated PDF.
    If the TXT contains lines like:
        [Illustration: path/to/image.png]
    the PDF will embed that image at that point in the narrative (with automatic scaling + page breaks).
    """
    ensure_dirs()
    if rl_canvas is None or letter is None:
        raise RuntimeError("PDF export requires reportlab (not available).")

    s = slot.strip().lower()
    if s not in SAVE_SLOTS:
        s = "slot1"

    txt_path = SAVE_DIR / f"{s}.txt"
    if not txt_path.exists():
        raise FileNotFoundError(f"No save TXT found: {txt_path.as_posix()}")

    pdf_path = SAVE_DIR / f"{s}.pdf"
    txt = txt_path.read_text(encoding="utf-8", errors="replace")

    c = rl_canvas.Canvas(str(pdf_path), pagesize=letter)
    page_w, page_h = letter
    margin = 54  # 0.75"
    x = margin
    y = page_h - margin

    # Typography
    font_name = "Courier"
    font_size = 10
    line_h = 12
    c.setFont(font_name, font_size)

    max_chars = 95  # for wrapping plain lines
    max_img_w = page_w - 2 * margin
    max_img_h = page_h - 2 * margin - 2 * line_h

    def new_page():
        nonlocal y
        c.showPage()
        c.setFont(font_name, font_size)
        y = page_h - margin

    def draw_wrapped_line(raw_line: str):
        nonlocal y
        pieces = [raw_line[i:i + max_chars] for i in range(0, len(raw_line), max_chars)] or [""]
        for line in pieces:
            if y < margin + line_h:
                new_page()
            c.drawString(x, y, line)
            y -= line_h

    def draw_image(path: str):
        nonlocal y
        # Resolve relative paths against the game folder for portability.
        pth = Path(path)
        if not pth.is_absolute():
            pth = (BASE_DIR / pth).resolve()
        path = str(pth)
        # Reserve some space; if not enough, page break.
        if y < margin + 200:
            new_page()

        # ReportLab can drawImage directly from file path.
        # We compute aspect-fit into max_img_w/max_img_h.
        try:
            from reportlab.lib.utils import ImageReader
            img = ImageReader(path)
            iw, ih = img.getSize()
            if iw <= 0 or ih <= 0:
                raise ValueError("Invalid image size")
            scale = min(max_img_w / iw, max_img_h / ih, 1.0)
            tw = iw * scale
            th = ih * scale
            if y - th < margin:
                new_page()
            # draw centered
            ix = margin + (max_img_w - tw) / 2.0
            iy = y - th
            c.drawImage(img, ix, iy, width=tw, height=th, preserveAspectRatio=True, mask='auto')
            y = iy - line_h  # spacing after image
        except Exception as e:
            draw_wrapped_line(f"[Missing/invalid illustration: {path}] ({e})")

    # Walk through TXT lines, embedding images inline.
    for raw_line in txt.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("[Illustration:") and stripped.endswith("]"):
            # Extract path between colon and closing bracket
            path = stripped[len("[Illustration:"): -1].strip()
            if path:
                draw_wrapped_line("")  # small spacing
                draw_image(path)
                draw_wrapped_line("")  # small spacing
            else:
                draw_wrapped_line("[Illustration: (empty path)]")
            continue

        draw_wrapped_line(raw_line)

    c.save()
    return pdf_path


@dataclass
class Viewport:
    win_w: int
    win_h: int
    scale: float
    view_w: int
    view_h: int
    view_x: int
    view_y: int

def compute_viewport(win_w: int, win_h: int) -> Viewport:
    scale = min(win_w / VIRTUAL_W, win_h / VIRTUAL_H)
    view_w = max(1, int(VIRTUAL_W * scale))
    view_h = max(1, int(VIRTUAL_H * scale))
    view_x = (win_w - view_w) // 2
    view_y = (win_h - view_h) // 2
    return Viewport(win_w, win_h, scale, view_w, view_h, view_x, view_y)

def window_to_virtual(vp: Viewport, mx: int, my: int) -> Optional[Tuple[int, int]]:
    if mx < vp.view_x or my < vp.view_y or mx >= vp.view_x + vp.view_w or my >= vp.view_y + vp.view_h:
        return None
    vx = int((mx - vp.view_x) / vp.scale)
    vy = int((my - vp.view_y) / vp.scale)
    vx = max(0, min(VIRTUAL_W - 1, vx))
    vy = max(0, min(VIRTUAL_H - 1, vy))
    return vx, vy

def wrap_text(font: pygame.font.Font, text: str, max_width: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        test = cur + " " + w
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines

class TextCache:
    def __init__(self):
        self.cache: Dict[Tuple[str, int], pygame.Surface] = {}
    def render(self, font: pygame.font.Font, text: str, color: Tuple[int,int,int]) -> pygame.Surface:
        key = (text, (color[0]<<16)|(color[1]<<8)|color[2])
        surf = self.cache.get(key)
        if surf is None:
            surf = font.render(text, True, color)
            self.cache[key] = surf
        return surf


class ImageCache:
    def __init__(self):
        self.cache: Dict[Tuple[str, int, int], pygame.Surface] = {}

    def get_scaled(self, path: str, w: int, h: int) -> Optional[pygame.Surface]:
        if not path:
            return None
        key = (path, w, h)
        surf = self.cache.get(key)
        if surf is not None:
            return surf
        try:
            pth = Path(path)
            if not pth.is_absolute():
                pth = (BASE_DIR / pth).resolve()
            img = pygame.image.load(pth.as_posix()).convert_alpha()
            img = pygame.transform.smoothscale(img, (max(1, w), max(1, h)))
            self.cache[key] = img
            return img
        except Exception:
            return None

class WrapCache:
    def __init__(self):
        self.version = -1
        self.width = -1
        self.items: List[dict] = []  # [{kind:'text', text, h} | {kind:'img', path, caption_lines, hint_lines, tw, th, h}]
        self.total_h: int = 0

    def rebuild(self, font_main: pygame.font.Font, font_small: pygame.font.Font, raw_lines: List[str], version: int, width: int):
        if self.version == version and self.width == width:
            return
        self.version = version
        self.width = width

        line_h = font_main.get_linesize()
        small_h = font_small.get_linesize()

        out: List[dict] = []
        total_h = 0

        # Inline sketch sizing (generated sketches are 960x540 by default)
        BASE_W, BASE_H = 960, 540
        MAX_IMG_H = 320
        INNER_W = max(1, width - 28)  # account for box padding

        for ln in raw_lines:
            if ln.startswith(INTERNAL_ILLUSTRATION_TAG):
                meta_json = ln[len(INTERNAL_ILLUSTRATION_TAG):].strip()
                try:
                    meta = json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta = {}

                path = str(meta.get('path', '')).strip()
                caption = str(meta.get('caption', '')).strip()
                hint = str(meta.get('hint', '')).strip()

                # Fit by height first so it doesn't dominate the journal.
                scale = min(INNER_W / BASE_W, MAX_IMG_H / BASE_H)
                tw = max(1, int(BASE_W * scale))
                th = max(1, int(BASE_H * scale))

                cap_lines = wrap_text(font_small, caption, INNER_W) if caption else []
                hint_label = hint
                if hint_label and not hint_label.lower().startswith('hint'):
                    hint_label = 'Hint: ' + hint_label
                hint_lines = wrap_text(font_small, hint_label, INNER_W) if hint_label else []

                pad_top = 10
                pad_mid = 8
                pad_bot = 10

                box_h = pad_top + th + pad_mid
                if cap_lines:
                    box_h += len(cap_lines) * small_h + 4
                if hint_lines:
                    box_h += len(hint_lines) * small_h + 2
                box_h += pad_bot

                out.append({
                    'kind': 'img',
                    'path': path,
                    'caption_lines': cap_lines,
                    'hint_lines': hint_lines,
                    'tw': tw,
                    'th': th,
                    'h': box_h,
                })
                total_h += box_h
                continue

            # Normal text lines
            if not ln:
                out.append({'kind': 'text', 'text': '', 'h': line_h})
                total_h += line_h
            else:
                for wln in wrap_text(font_main, ln, width):
                    out.append({'kind': 'text', 'text': wln, 'h': line_h})
                    total_h += line_h

        self.items = out
        self.total_h = total_h

# ----------------------------
# Film grain overlay (subtle black grain) (subtle black grain)
# ----------------------------

def make_grain_tile(rng: random.Random, w: int = 256, h: int = 256) -> pygame.Surface:
    """
    Fast film-grain: generate a small black-static tile and BLEND_RGB_SUB tile it.
    This avoids per-frame smoothscales of a full-screen surface.
    """
    # Prefer numpy for speed if available, fallback to loops.
    try:
        import numpy as _np  # type: ignore
        seed = rng.getrandbits(32)
        _rng = _np.random.default_rng(seed)
        # Low-intensity grain so SUB blending stays subtle
        g = _rng.integers(0, 22, size=(w, h), dtype=_np.uint8)
        arr = _np.dstack([g, g, g])  # (w,h,3) for make_surface
        s = pygame.surfarray.make_surface(arr)
        s = s.convert()
    except Exception:
        s = pygame.Surface((w, h)).convert()
        px = pygame.PixelArray(s)
        for y in range(h):
            for x in range(w):
                v = rng.randint(0, 22)
                px[x, y] = (v << 16) | (v << 8) | v
        del px
    s.set_alpha(26)
    return s

def blit_tiled_grain(target: pygame.Surface, tile: pygame.Surface) -> None:
    tw, th = tile.get_size()
    for y in range(0, target.get_height(), th):
        for x in range(0, target.get_width(), tw):
            target.blit(tile, (x, y), special_flags=pygame.BLEND_RGB_SUB)


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, border: Tuple[int,int,int], fill: Tuple[int,int,int], accent: bool=False):
    pygame.draw.rect(surface, fill, rect, border_radius=12)
    pygame.draw.rect(surface, border, rect, width=2, border_radius=12)
    if accent:
        pygame.draw.rect(surface, THEME["accent_red"], pygame.Rect(rect.x, rect.y, rect.w, 3), border_radius=12)

def draw_shadowed_rect(surface: pygame.Surface, rect: pygame.Rect, fill: Tuple[int,int,int], border: Tuple[int,int,int], border_w: int=2):
    sh = pygame.Rect(rect.x+2, rect.y+3, rect.w, rect.h)
    pygame.draw.rect(surface, (0,0,0), sh, border_radius=10)
    pygame.draw.rect(surface, fill, rect, border_radius=10)
    pygame.draw.rect(surface, border, rect, width=border_w, border_radius=10)

@dataclass
class UIButton:
    rect: pygame.Rect
    label: str
    on_click: Callable[[], None]
    enabled: bool = True

def draw_button(surface: pygame.Surface, btn: UIButton, font: pygame.font.Font, cache: TextCache, mouse: Tuple[int,int]):
    hovered = btn.rect.collidepoint(mouse)
    fill = THEME["btn_fill_hover"] if hovered else THEME["btn_fill"]
    border = THEME["btn_border_hover"] if hovered else THEME["btn_border"]
    if not btn.enabled:
        fill = (16,12,16); border = (50,46,56)
    draw_shadowed_rect(surface, btn.rect, fill, border, 2)
    col = THEME["btn_text"] if btn.enabled else THEME["text_muted"]
    s = cache.render(font, btn.label, col)
    surface.blit(s, (btn.rect.centerx - s.get_width()//2, btn.rect.centery - s.get_height()//2))


def draw_map(surface: pygame.Surface,
             world: Dict[str, Room],
             gs: GameState,
             map_rect: pygame.Rect,
             font: pygame.font.Font,
             cache: TextCache,
             mouse_v: Tuple[int,int],
             hover_rid: Optional[str],
             popup_text: str,
             popup_until_ms: int,
             seed: int,
             map_noise_cache: Dict[Tuple[str,int,int], pygame.Surface]) -> None:
    """
    Readability-first map:
    - No permanent labels (prevents overlap)
    - Hover tooltip shows name/details
    - Click shows a temporary info card (popup_text)
    - Procedural noisy "hell cartography" backdrop
    """
    draw_panel(surface, map_rect, THEME["panel_border"], THEME["panel_fill"], accent=True)

    # background noise (cached per circle+size)
    cur_circle = world[gs.current].circle
    key = (cur_circle, map_rect.w, map_rect.h)
    bg = map_noise_cache.get(key)
    if bg is None:
        bg = gen_map_noise(cur_circle, (map_rect.w, map_rect.h), seed)
        map_noise_cache[key] = bg

    # clip
    old_clip = surface.get_clip()
    surface.set_clip(map_rect)

    surface.blit(bg, (map_rect.x, map_rect.y))

    # Header
    header = f"MAP — {cur_circle}"
    max_header_w = map_rect.w - 260  # room for utility buttons on right
    if font.size(header)[0] > max_header_w:
        h = header
        while h and font.size(h + "…")[0] > max_header_w:
            h = h[:-1]
        header = (h + "…") if h else "MAP"
    surface.blit(cache.render(font, header, THEME["text"]), (map_rect.x + 16, map_rect.y + 12))

    # Edges (only between visited nodes to reduce clutter)
    for r in world.values():
        if r.rid not in gs.visited:
            continue
        for lbl, dst in r.exits.items():
            if not exit_is_visible(gs, r.rid, lbl):
                continue
            if dst not in gs.visited:
                continue
            x1, y1 = r.pos
            x2, y2 = world[dst].pos
            pygame.draw.line(surface, THEME["map_edge_visited"], (x1, y1), (x2, y2), 2)

    # Nodes
    for r in world.values():
        if r.rid not in gs.discovered:
            continue
        x, y = r.pos
        is_cur = (r.rid == gs.current)
        is_vis = (r.rid in gs.visited)

        rad = 12 if is_cur else (9 if is_vis else 7)
        col = THEME["map_node_current"] if is_cur else (THEME["map_node_visited"] if is_vis else THEME["map_node"])
        pygame.draw.circle(surface, col, (x, y), rad)

        if is_cur:
            pygame.draw.circle(surface, THEME["accent_red"], (x, y), rad + 2, 2)

        # subtle outer ring
        pygame.draw.circle(surface, (0,0,0), (x, y), rad + 1, 1)

    # Hover tooltip
    if hover_rid and hover_rid in world:
        r = world[hover_rid]
        tag = "CURRENT" if hover_rid == gs.current else ("VISITED" if hover_rid in gs.visited else "DISCOVERED")
        title = r.name.split(" (")[0].strip()
        subtitle = f"{r.circle} — {tag}"
        tw = max(font.size(title)[0], font.size(subtitle)[0])
        th = font.get_linesize() * 2 + 12

        # position near mouse but clamp inside map rect
        mx, my = mouse_v
        bx = mx + 16
        by = my + 16
        bx = max(map_rect.x + 10, min(bx, map_rect.right - 10 - tw - 20))
        by = max(map_rect.y + 54, min(by, map_rect.bottom - 10 - th))

        box = pygame.Rect(bx, by, tw + 20, th)
        pygame.draw.rect(surface, (0,0,0), box.move(2,3), border_radius=10)
        pygame.draw.rect(surface, (12,4,6), box, border_radius=10)
        pygame.draw.rect(surface, THEME["accent_red_soft"], box, width=2, border_radius=10)

        surface.blit(cache.render(font, title, THEME["text"]), (box.x + 10, box.y + 6))
        surface.blit(cache.render(font, subtitle, THEME["text_dim"]), (box.x + 10, box.y + 6 + font.get_linesize()))

    # Click popup (temporary)
    now_ms = pygame.time.get_ticks()
    if popup_text and now_ms < popup_until_ms:
        # wrap text to fit
        max_w = map_rect.w - 40
        words = popup_text.split()
        lines: List[str] = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if font.size(test)[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lines = lines[:4]  # cap
        lh = font.get_linesize()
        box_h = lh * len(lines) + 18
        box = pygame.Rect(map_rect.x + 20, map_rect.bottom - 20 - box_h, map_rect.w - 40, box_h)

        pygame.draw.rect(surface, (0,0,0), box.move(2,3), border_radius=12)
        pygame.draw.rect(surface, (10,2,4), box, border_radius=12)
        pygame.draw.rect(surface, THEME["accent_red_soft"], box, width=2, border_radius=12)

        yy = box.y + 9
        for ln in lines:
            surface.blit(cache.render(font, ln, THEME["text"]), (box.x + 12, yy))
            yy += lh

    surface.set_clip(old_clip)
def room_hit_test(world: Dict[str, Room], gs: GameState, map_rect: pygame.Rect, mx: int, my: int) -> Optional[str]:
    if not map_rect.collidepoint(mx, my):
        return None
    for r in world.values():
        if r.rid not in gs.discovered:
            continue
        x,y = r.pos
        if (mx-x)*(mx-x) + (my-y)*(my-y) <= 16*16:
            return r.rid
    return None


# ----------------------------
# Procedural "data-driven screenshot" (Sketch button)
# ----------------------------

def _seed_from_state(gs: GameState, world: Dict[str, Room]) -> int:
    room = world[gs.current]
    x = gs.rng_seed ^ (hash(room.rid) & 0x7FFFFFFF)
    x ^= (len(gs.visited) * 2654435761) & 0x7FFFFFFF
    x ^= (len(gs.inventory) * 97531) & 0x7FFFFFFF
    if room.encounter and room.encounter.key not in gs.resolved_encounters:
        x ^= (hash(room.encounter.key) & 0x7FFFFFFF)
    return x & 0x7FFFFFFF

def _circle_style(circle_name: str) -> str:
    c = circle_name.lower()
    if "limbo" in c:
        return "mist"
    if "lust" in c or "storm" in c:
        return "storm"
    if "glutton" in c or "mire" in c:
        return "sludge"
    if "greed" in c or "weights" in c:
        return "stone"
    if "wrath" in c or "styg" in c:
        return "swamp"
    if "heresy" in c or "tombs" in c:
        return "embers"
    if "violence" in c or "blood" in c:
        return "blood"
    if "fraud" in c or "bolgia" in c:
        return "tar"
    if "treachery" in c or "ice" in c or "cocytus" in c:
        return "ice"
    return "stone"

def _aa_line(surf: pygame.Surface, p1, p2, color, width=2):
    x1, y1 = p1
    x2, y2 = p2
    for o in range(-(width//2), width//2 + 1):
        gfxdraw.line(surf, x1, y1+o, x2, y2+o, color)
        gfxdraw.line(surf, x1+o, y1, x2+o, y2, color)

def _aa_circle(surf: pygame.Surface, x, y, r, color, fill=True):
    if fill:
        gfxdraw.filled_circle(surf, x, y, r, color)
    gfxdraw.aacircle(surf, x, y, r, color)


def generate_illustration_hint(gs: GameState, world: Dict[str, Room], room: Room, rng: random.Random) -> str:
    """Return a short, actionable hint tied to the current state.

    Hints are meant to be *useful* without hard-spoiling names of unvisited rooms.
    """
    # Gate hints around required items for unresolved block encounters.
    enc = room.encounter
    if enc and enc.kind == "block" and enc.key not in gs.resolved_encounters and enc.requires_item:
        need = enc.requires_item
        if gs.inventory.get(need, 0) <= 0:
            sources = []
            for r in world.values():
                if r.items and need in r.items:
                    sources.append(r)
                if r.encounter and r.encounter.loot and need in r.encounter.loot:
                    sources.append(r)
            if sources:
                unvis = [r for r in sources if r.rid not in gs.visited]
                src = rng.choice(unvis or sources)
                # If unvisited, only mention the circle (not the exact room name).
                loc = f"{src.circle} — {src.name}" if src.rid in gs.visited else f"{src.circle}"
                return f"A gate demands {need.replace('_',' ')}. It clings to {loc}."
            return f"A gate demands {need.replace('_',' ')}. Seek it in the side paths."

    # Lucifer: keep it short and practical.
    if room.rid == "lucifer_pit":
        return "Guard to blunt the wing-thunder, then strike. His seal can reveal a hidden ascent."

    # Hidden exits: nudge toward the relevant trigger without spelling the exact switch.
    if room.rid == "hall_of_names" and not gs.flags.get("archive_revealed", False):
        return "Names can open what stone denies. Hear the whisper; answer without cruelty."

    # If low on HP, remind to bandage/rest.
    if gs.player.hp <= max(8, gs.player.hp_max // 3):
        return "Survive first: bandage, ration, or rest—then take the next step."

    # General: exploration + dead ends.
    return rng.choice([
        "Dead ends are not empty—look twice before you turn back.",
        "Side rooms hide the tokens the main path pretends it never needed.",
        "The map lies by omission; the journal tells the truth.",
    ])

def generate_illustration(gs: GameState, world: Dict[str, Room], slot_hint: str = "slot1") -> Tuple[str, str, str]:
    """Generate a procedural Rorschach-like inkblot sketch (symmetry + strange anatomy hints).

    Saved as PNG into ./saves/<slot>_media/ and returned as a *relative* path for portability.
    """
    ensure_dirs()
    room = world[gs.current]
    seed = _seed_from_state(gs, world)
    rng = random.Random(seed)

    style = _circle_style(room.circle + " " + room.name)

    # Higher-res than before for nicer ink texture
    W, H = 960, 540
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    # "Paper" background: dark parchment / soot
    paper_top = (84, 10, 18, 255)
    paper_bot = (16, 2, 4, 255)
    for y in range(H):
        t = y / (H - 1)
        col = (
            int(paper_top[0] * (1 - t) + paper_bot[0] * t),
            int(paper_top[1] * (1 - t) + paper_bot[1] * t),
            int(paper_top[2] * (1 - t) + paper_bot[2] * t),
            255,
        )
        gfxdraw.hline(surf, 0, W - 1, y, col)

    # Ink surface (we draw half then mirror)
    ink = pygame.Surface((W, H), pygame.SRCALPHA)
    # Palette varies by circle "style"
    base = {
    # Restrict to reds + blacks only
    "mist": (18, 4, 8),
    "storm": (20, 3, 7),
    "sludge": (14, 2, 4),
    "stone": (16, 3, 6),
    "swamp": (14, 2, 4),
    "embers": (26, 4, 6),
    "blood": (22, 3, 6),
    "tar": (10, 1, 2),
    "ice": (16, 3, 7),
    }.get(style, (18, 3, 6))
    
    # Subtle accent that sometimes "bleeds" (not neon)
    accent = {
    # bleed accents (still within reds/blacks)
    "embers": (150, 18, 24),
    "blood": (190, 22, 34),
    "tar": (120, 12, 22),
    "ice": (140, 16, 30),
    "storm": (160, 18, 32),
    }.get(style, (160, 18, 30))

    def splat(x, y, r, a, col):
        c = (col[0], col[1], col[2], a)
        gfxdraw.filled_circle(ink, x, y, r, c)
        gfxdraw.aacircle(ink, x, y, r, c)

    # Primary blots
    half = W // 2
    core_x = rng.randint(int(half * 0.35), int(half * 0.85))
    core_y = rng.randint(int(H * 0.35), int(H * 0.70))

    # Dense core
    for _ in range(220):
        x = int(rng.gauss(core_x, half * 0.18))
        y = int(rng.gauss(core_y, H * 0.18))
        x = max(0, min(half - 1, x))
        y = max(0, min(H - 1, y))
        r = max(1, int(abs(rng.gauss(6.5, 5.0))))
        a = rng.randint(50, 160)
        col = base if rng.random() > 0.12 else accent
        splat(x, y, r, a, col)
        # mirror
        splat(W - 1 - x, y, r, a, col)

    # Tendrils / horns via mirrored random walks
    for _ in range(10):
        x = rng.randint(int(half * 0.10), int(half * 0.95))
        y = rng.randint(int(H * 0.10), int(H * 0.90))
        dx = rng.uniform(-1.6, 1.6)
        dy = rng.uniform(-1.6, 1.6)
        steps = rng.randint(70, 170)
        col = base if rng.random() > 0.18 else accent
        for s in range(steps):
            x += dx + rng.uniform(-0.6, 0.6)
            y += dy + rng.uniform(-0.6, 0.6)
            dx = max(-2.8, min(2.8, dx + rng.uniform(-0.35, 0.35)))
            dy = max(-2.8, min(2.8, dy + rng.uniform(-0.35, 0.35)))
            ix = int(max(0, min(half - 1, x)))
            iy = int(max(0, min(H - 1, y)))
            r = 1 + (s // 35)
            a = rng.randint(30, 120)
            splat(ix, iy, r, a, col)
            splat(W - 1 - ix, iy, r, a, col)

    # "Eyes" (rare) — uncanny bilateral marks
    if rng.random() < 0.55:
        eye_y = rng.randint(int(H * 0.30), int(H * 0.55))
        eye_x = rng.randint(int(half * 0.22), int(half * 0.42))
        for rr in range(14, 0, -1):
            a = int(18 + rr * 5)
            col = accent if rr < 6 else base
            splat(eye_x, eye_y, rr, a, col)
            splat(W - 1 - eye_x, eye_y, rr, a, col)

    # Blur/smear by downscale + upscale (cheap ink diffusion)
    small = pygame.transform.smoothscale(ink, (W // 3, H // 3))
    ink = pygame.transform.smoothscale(small, (W, H))

    # Add grain for "charcoal paper" feel
    grain_tile = make_grain_tile(rng, 256, 256)
    blit_tiled_grain(surf, grain_tile)

    # Composite ink
    surf.blit(ink, (0, 0))

    # Occasional "burnt edge" vignette
    if rng.random() < 0.7:
        vign = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W // 2, H // 2
        for i in range(10):
            pad = 22 + i * 14
            a = 22 + i * 9
            pygame.draw.rect(vign, (0, 0, 0, a), pygame.Rect(pad, pad, W - pad * 2, H - pad * 2), width=6, border_radius=24)
        surf.blit(vign, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

    
    # SECRET_THORN — image-only hint for a relic that can end Lucifer quickly.
    secret_hint_rooms = {"blood_archive", "ice_cracks", "frozen_tears"}
    secret_item_room = "thorn_reliquary"
    secret_hint_active = (room.rid in secret_hint_rooms or room.rid == secret_item_room) and (gs.inventory.get("mercy_thorn", 0) <= 0)

    if secret_hint_active:
        # draw a pale "thorn" glyph (subtle but readable) as a visual-only clue
        glyph = pygame.Surface((W, H), pygame.SRCALPHA)
        cx = W // 2
        top_y = int(H * 0.18)
        bot_y = int(H * 0.82)
        # spine
        pygame.draw.line(glyph, (230, 225, 235, 90), (cx, top_y), (cx, bot_y), 3)
        # barbs
        for i in range(10):
            t = i / 9.0
            yb = int(top_y * (1 - t) + bot_y * t)
            dx = int(22 + 18 * math.sin(t * math.pi))
            pygame.draw.line(glyph, (230, 225, 235, 70), (cx, yb), (cx + dx, yb - 8), 2)
            pygame.draw.line(glyph, (230, 225, 235, 70), (cx, yb), (cx - dx, yb - 8), 2)
        # a "break" mark near bottom
        pygame.draw.circle(glyph, (180, 40, 50, 55), (cx, int(H * 0.72)), 14, 2)
        surf.blit(glyph, (0, 0))

        # silently reveal the hidden reliquary exit (no text; the clue is the image itself)
        gs.flags["reliquary_revealed"] = True
# Caption: short, varied, no filename/path
    cap_bits = [
        "An inkblot blooms into the shape of a thing that refuses naming.",
        "A mirrored stain suggests wings, then wounds, then a crown.",
        "The page drinks darkness until it resembles a prayer turned inside-out.",
        "A symmetric blot forms a face for an instant—then denies it.",
        "Black symmetry: anatomy imagined by punishment.",
        "Two halves agree on one horror.",
    ]
    if style == "blood":
        cap_bits += ["The ink smells faintly of iron, though it is only ink.", "Red undertones gather like a verdict."]
    elif style == "ice":
        cap_bits += ["The symmetry feels cold, as if the blot remembers winter.", "Edges crystallize into sharp quiet."]
    elif style == "embers":
        cap_bits += ["The stain burns at the edges without light.", "Ash-tones cluster like singed scripture."]
    caption = rng.choice(cap_bits)

    hint = generate_illustration_hint(gs, world, room, rng)
    if 'secret_hint_active' in locals() and secret_hint_active:
        hint = ""  # image-only

    # Save to slot media folder (portable relative path)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    slot_safe = "".join(ch for ch in slot_hint if ch.isalnum()) or "slot1"
    media_dir = SAVE_DIR / f"{slot_safe}_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    out_path = media_dir / f"inkblot_{room.rid}_{stamp}.png"
    pygame.image.save(surf, out_path.as_posix())

    rel = out_path.relative_to(BASE_DIR).as_posix()
    return rel, caption, hint

def on_enter_room(gs: GameState, world: Dict[str, Room]) -> None:
    rng = gs_rng(gs)
    room = world[gs.current]
    # Sync per-room item state from save
    if isinstance(gs.room_items, dict) and room.rid in gs.room_items:
        room.items = {str(k): int(v) for k, v in gs.room_items.get(room.rid, {}).items() if int(v) > 0}
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    first = gs.current not in gs.visited
    if first:
        gs.visited.add(gs.current)
        gs.chapters.append((room.circle, room.name, ts))
    gs.discovered = set(gs.visited)
    gs.discovered.add(gs.current)
    # NOTE: Nodes unlock only when entered (visited).

    add_log(gs, "")
    add_log(gs, f"[{room.circle}] {room.name}")
    add_log(gs, room.desc)

    # Extra sensory detail (keeps the prose dense without rewriting every room)
    style = _circle_style(room.circle + " " + room.name)
    if rng.random() < (0.75 if first else 0.45):
        add_log(gs, "… " + choose_ambient_detail(gs, style, rng))
    if room.items:
        add_log(gs, "Items here: " + ", ".join([f"{k} x{v}" for k,v in room.items.items()]))
    gs.room_items[room.rid] = dict(room.items)
    if room.npcs:
        add_log(gs, "Voices here: " + ", ".join(room.npcs.keys()))

    if first:
        chap_no = len(gs.chapters)
        add_story(gs, "")
        add_story(gs, f"Chapter {chap_no:03d}: {room.circle} — {room.name}")
        add_story(gs, room.desc.replace("\n"," "))
        if room.circle.startswith("Circle"):
            add_codex(gs, room.circle, f"{room.circle} — {room.desc.replace(chr(10),' ')}")

    # ambient chance
    if first and rng.random() < 0.12:
        evt = rng.choice([
            ("A cold gust steals your breath.", "You lose 1 HP.", -1, None),
            ("You find a dry scrap of cloth.", "Bandage +1.", 0, ("bandage",1)),
            ("A whisper steadies you.", "Resolve +1.", 0, ("resolve",1)),
            ("A dim warmth returns to your fingers.", "HP +2.", 2, None),
        ])
        add_log(gs, f"… {evt[0]} {evt[1]}")
        add_story(gs, f"{evt[0]} {evt[1]}")
        if evt[2] < 0:
            gs.player.hp = max(1, gs.player.hp + evt[2])
        elif evt[2] > 0:
            gs.player.hp = min(gs.player.hp_max, gs.player.hp + evt[2])
        if evt[3]:
            k,v = evt[3]
            if k == "resolve":
                gs.player.resolve = min(25, gs.player.resolve + v)
            else:
                gs.inventory[k] = gs.inventory.get(k, 0) + v

    # Rare finding: even dead ends can hide something (saved per-room)
    if first and rng.random() < 0.065 and not gs.in_combat:
        rare_pool = {
            "mist": [("pale_lily", "A pale lily grows where sunlight never agreed to exist.")],
            "storm": [("torn_vow", "A strip of ribbon flutters, knotted like a promise that broke itself.")],
            "sludge": [("sweet_rot", "Something sweet rots slowly in the mire—still edible, if you dare.")],
            "stone": [("ledger_shard", "A shard of a ledger—numbers written so hard they scored the stone.")],
            "swamp": [("sunken_murmur", "A small charm rises from the mud, humming with swallowed anger.")],
            "embers": [("ember_rose", "A coal-red rose: beautiful, and hot enough to hurt to remember.")],
            "blood": [("scarlet_mint", "A leaf that smells like iron and clean air at once.")],
            "tar": [("pitch_sigil", "A tar-smeared sigil that sticks to your fingers and refuses to be only dirt.")],
            "ice": [("frost_mirror", "A sliver of ice that reflects you as you were, not as you are.")],
        }
        pool = rare_pool.get(style, [("strange_token", "A strange token waits where no one should have left it.")])
        item, line = rng.choice(pool)
        room.items[item] = room.items.get(item, 0) + 1
        gs.room_items[room.rid] = dict(room.items)
        add_log(gs, "✧ Rare finding: " + line + f" ({item} +1)")
        add_story(gs, line)

    # encounter auto
    if room.encounter and room.encounter.key not in gs.resolved_encounters:
        enc = room.encounter
        if enc.kind == "combat":
            add_log(gs, f"⚠ Encounter: {enc.name}")
            add_log(gs, enc.intro)
            add_story(gs, f"A threat rises: {enc.name}. {enc.intro}")
            gs.in_combat = True
            gs.combat_enemy = Encounter(**{**enc.__dict__})
        else:
            add_log(gs, f"⛔ {enc.intro}")
            add_story(gs, f"A barrier stands in your way: {enc.intro}")
            gs.in_combat = False
            gs.combat_enemy = None
    else:
        gs.in_combat = False
        gs.combat_enemy = None

    # objectives nudges
    if first and room.rid == "vestibule":
        push_objective(gs, "Find a way to cross Acheron into Limbo.")
    if first and room.rid == "minos_threshold":
        push_objective(gs, "Earn Minos' consent to descend into the storm.")
    if first and room.rid == "lust_gate":
        push_objective(gs, "Find a token of restraint to form the stairs downward.")
    if first and room.rid == "greed_gate":
        push_objective(gs, "Break Greed's hold and open the way to Wrath.")
    if first and room.rid == "lucifer_pit":
        push_objective(gs, "Survive the center of ice. Find a way out that Hell will not show you.")


    # One-shot narrative events (choice-driven) — only on first entry and only if not already in combat
    if first and (not gs.in_combat) and room.rid in ROOM_EVENTS:
        eid = ROOM_EVENTS[room.rid]
        if not gs.flags.get(f"event_done_{eid}", False):
            if eid == "name_contact":
                trigger_event(gs, eid,
                    "The names on the wall throb as if they have pulse. One line is smeared—then sharp again—then you realize it is trying to become *yours*.")
            elif eid == "sullen_soul":
                trigger_event(gs, eid,
                    "A hand breaks the surface of the mud—slow, exhausted. A sullen soul does not ask for mercy; it only *reaches* as if remembering the shape of help.")
            elif eid == "filth_oracle":
                trigger_event(gs, eid,
                    "In the ditch, a voice bubbles up through filth: “I can tell you what Hell wrote about you—if you pay in honesty.”")
            elif eid == "black_glass":
                trigger_event(gs, eid,
                    "A shard of black glass hums inside the crack. In its surface, you see a version of yourself walking out of Hell… and turning around to go back in.")
    # Endings / epilogue logic
    if room.rid == "heaven_hall" and not gs.flags.get("ending_done", False):
        gs.flags["ending_done"] = True
        add_story(gs, "")
        add_story(gs, "Epilogue — The Weight of the Book")
        add_story(gs, "--------------------------------")
        # Merit gates the final tone. Secrets/items can sharpen the twist.
        has_page = gs.inventory.get("forgiven_page", 0) > 0
        has_seal = gs.inventory.get("wax_seal", 0) > 0
        if gs.merit >= 3 and (has_page or has_seal):
            add_story(gs, "The presence does not accuse. It asks one question: *Who did you carry?*")
            add_story(gs, "You remember the faces in the storm, the mouths in the mud, the names that kept trying to become yours.")
            add_story(gs, "Then the twist lands softly: you were never sentenced. You were sent—because you were willing to return with the record.")
            add_story(gs, "Light opens like a door. Forgiveness is not a prize; it is a task handed back to you.")
            add_log(gs, "✦ Ending: Forgiven — You carried the record out.")
        elif gs.merit >= 1:
            add_story(gs, "The presence is quiet. It shows you the book you dragged through Hell—its pages are wet with other lives.")
            add_story(gs, "A verdict forms: you resisted becoming the place, but you did not yet learn how to unmake it.")
            add_story(gs, "You are offered rest, not release—an interlude that smells like rain and clean stone.")
            add_log(gs, "✦ Ending: The Interlude — Rest without forgetting.")
        else:
            add_story(gs, "The presence turns the book toward you. The ink rearranges itself into a sentence you cannot deny.")
            add_story(gs, "Plot twist: the descent did not end when you escaped. It ended when you stopped feeding Hell with your own choices.")
            add_story(gs, "You are not dragged back—worse—you are *returned*, gently, to begin again with memory intact.")
            add_log(gs, "✦ Ending: The Loop — Hell remembers you.")
        add_log(gs, "Game complete. You can keep exploring, or return to the book and save/export.")
    # Roaming danger (ambushes) — escalates with depth
    maybe_roaming_encounter(gs, world, rng)
    commit_rng(gs, rng)

def do_travel(gs: GameState, world: Dict[str, Room], exit_label: str) -> None:
    room = world[gs.current]
    if exit_label not in room.exits:
        add_log(gs, "That way is not open.")
        return
    if not exit_is_visible(gs, room.rid, exit_label):
        add_log(gs, "That way is not visible.")
        return
    if not can_use_exit(gs, room, exit_label):
        add_log(gs, "Something blocks that way.")
        return
    dest_id = room.exits[exit_label]
    add_story(gs, f"You choose the {exit_label} path toward {world[dest_id].name}.")
    gs.previous = gs.current
    gs.current = dest_id
    gs.guard_next = False
    on_enter_room(gs, world)

    # Film grain
    grain_rng = random.Random(gs.rng_seed ^ 0xA5A5A5)
    grain_tile = make_grain_tile(grain_rng, 256, 256)
    grain_timer = 0

def resolve_block(gs: GameState, world: Dict[str, Room]) -> None:
    rng = gs_rng(gs)
    room = world[gs.current]
    enc = room.encounter
    if not enc or enc.kind != "block" or enc.key in gs.resolved_encounters:
        add_log(gs, "There is nothing to press through here.")
        commit_rng(gs, rng)
        return
    if enc.requires_item:
        have = gs.inventory.get(enc.requires_item, 0)
        if have > 0:
            gs.resolved_encounters.add(enc.key)
            add_log(gs, f"✓ {enc.victory}")
            add_story(gs, enc.victory)
            if enc.consume_item:
                gs.inventory[enc.requires_item] = have - 1
                if gs.inventory[enc.requires_item] <= 0:
                    del gs.inventory[enc.requires_item]
                add_story(gs, f"You surrender {enc.requires_item} to the gate.")
            commit_rng(gs, rng)
            return
        else:
            add_log(gs, f"(You likely need: {enc.requires_item})")
    roll = rng.randint(1,20)
    total = gs.player.resolve + roll
    if total >= 20:
        gs.resolved_encounters.add(enc.key)
        add_log(gs, f"✓ {enc.victory}")
        add_story(gs, enc.victory)
    else:
        add_log(gs, f"✗ {enc.defeat} (Resolve {gs.player.resolve}+{roll}={total})")
        add_story(gs, f"You try and fail: {enc.defeat}")
    commit_rng(gs, rng)

def combat_player_strike(gs: GameState) -> None:
    rng = gs_rng(gs)
    enemy = gs.combat_enemy
    # Secret relic: Mercy Thorn can end Lucifer quickly (image-hinted only)
    if enemy and enemy.key == 'lucifer' and gs.inventory.get('mercy_thorn', 0) > 0 and not gs.flags.get('mercy_thorn_used', False):
        enemy.hp = 0
        gs.flags['mercy_thorn_used'] = True
        add_log(gs, "The Mercy Thorn flares—ice fractures and the wings falter.")
        add_story(gs, "A pale thorn remembers a gentler world. The frozen king stutters, then cracks.")
        commit_rng(gs, rng)
        return
    if not enemy:
        commit_rng(gs, rng); return
    var = rng.randint(-2,2)
    dmg = max(1, gs.player.atk - enemy.defense + var)
    enemy.hp -= dmg
    add_log(gs, f"You strike for {dmg} damage. ({enemy.name} HP {max(enemy.hp,0)})")
    add_story(gs, f"You strike true, carving {dmg} from {enemy.name}.")
    commit_rng(gs, rng)

def combat_player_guard(gs: GameState) -> None:
    gs.guard_next = True
    add_log(gs, "You brace and guard, reducing the next hit.")
    add_story(gs, "You brace yourself, turning fear into posture.")

def combat_enemy_turn(gs: GameState) -> None:
    rng = gs_rng(gs)
    enemy = gs.combat_enemy
    if not enemy:
        commit_rng(gs, rng); return
    var = rng.randint(-1,2)
    dmg = max(1, enemy.atk - gs.player.defense + var)
    if gs.guard_next:
        dmg = max(0, dmg - 4)
        gs.guard_next = False
    gs.player.hp -= dmg
    add_log(gs, f"{enemy.name} hits you for {dmg} damage. (HP {max(gs.player.hp,0)}/{gs.player.hp_max})")
    add_story(gs, f"{enemy.name} answers with violence; you endure {dmg} pain.")
    commit_rng(gs, rng)

def finish_combat_if_needed(gs: GameState, world: Dict[str, Room]) -> None:
    enemy = gs.combat_enemy
    if not enemy:
        return
    if enemy.hp <= 0:
        room = world[gs.current]
        enc = room.encounter
        if enc:
            gs.resolved_encounters.add(enc.key)
            add_log(gs, f"✓ {enc.victory}")
            add_story(gs, enc.victory)
            if enc.loot:
                got = []
                for item, qty in enc.loot.items():
                    if item == "gold":
                        gs.player.gold += int(qty); got.append(f"gold +{qty}")
                    else:
                        gs.inventory[item] = gs.inventory.get(item,0) + int(qty); got.append(f"{item} x{qty}")
                add_log(gs, "Loot: " + ", ".join(got))
                add_story(gs, f"In the aftermath, you gather what remains: {', '.join(got)}.")
        else:
            # Roaming / non-room encounters can still drop loot.
            if enemy.loot:
                got = []
                for item, qty in enemy.loot.items():
                    if item == "gold":
                        gs.player.gold += int(qty); got.append(f"gold +{qty}")
                    else:
                        gs.inventory[item] = gs.inventory.get(item,0) + int(qty); got.append(f"{item} x{qty}")
                add_log(gs, "Loot: " + ", ".join(got))
                add_story(gs, f"You take what you can before the dark reorganizes: {', '.join(got)}.")
        gs.in_combat = False
        gs.combat_enemy = None
        return
    if gs.player.hp <= 0:
        add_log(gs, "✗ You collapse. Instinct drags you away from the killing blow...")
        add_story(gs, "Darkness takes you—but something refuses to let you end here.")
        gs.player.hp = max(1, gs.player.hp_max // 3)
        if gs.previous and gs.previous in world:
            gs.current = gs.previous
            gs.previous = None
            gs.in_combat = False
            gs.combat_enemy = None
            add_log(gs, "You awaken higher up, battered but alive.")
            add_story(gs, "You awaken higher up, battered but alive.")
            on_enter_room(gs, world)
        else:
            gs.in_combat = False
            gs.combat_enemy = None

def take_item(gs: GameState, world: Dict[str, Room], item: str) -> None:
    room = world[gs.current]
    it = item.strip().lower()
    if it not in room.items:
        add_log(gs, "That item isn't here."); return
    room.items[it] -= 1
    if room.items[it] <= 0: del room.items[it]
    gs.room_items[room.rid] = dict(room.items)
    gs.inventory[it] = gs.inventory.get(it,0) + 1
    add_log(gs, f"You take {pretty_item_name(it)}.")
    add_story(gs, f"You take {pretty_item_name(it)}, tucking it away for what waits below.")

def talk_to(gs: GameState, world: Dict[str, Room], npc: str) -> None:
    room = world[gs.current]
    if npc not in room.npcs:
        add_log(gs, "No one here answers to that."); return
    add_log(gs, f"{npc}:")
    add_story(gs, f"You speak with {npc}.")
    for ln in room.npcs[npc]:
        add_log(gs, f"  {ln}")
        add_story(gs, ln)
    # special: centaur grants pass if you have centaur_arrow
    if room.rid == "phlegethon_river" and npc == "centaur":
        if gs.inventory.get("centaur_arrow",0) > 0 and gs.inventory.get("centaur_pass",0) == 0:
            gs.inventory["centaur_pass"] = 1
            add_log(gs, "The centaur marks you. (centaur_pass +1)")
            add_story(gs, "The centaur accepts your proof and marks you for passage.")

def use_item(gs: GameState, world: Dict[str, Room], item: str) -> None:
    rng = gs_rng(gs)
    it = item.strip().lower()
    if gs.inventory.get(it,0) <= 0:
        add_log(gs, "You don't have that.")
        commit_rng(gs, rng); return
    room = world[gs.current]

    if it == "bandage":
        heal = 8
        gs.player.hp = min(gs.player.hp_max, gs.player.hp + heal)
        gs.inventory[it] -= 1
        if gs.inventory[it] <= 0: del gs.inventory[it]
        add_log(gs, f"You apply a bandage. +{heal} HP.")
        add_story(gs, "You bind your wounds, refusing to surrender to the descent.")
        commit_rng(gs, rng); return

    if it == "ration":
        heal = 5
        gs.player.hp = min(gs.player.hp_max, gs.player.hp + heal)
        gs.player.resolve = min(25, gs.player.resolve + 1)
        gs.inventory[it] -= 1
        if gs.inventory[it] <= 0: del gs.inventory[it]
        add_log(gs, f"You eat a ration. +{heal} HP, +1 Resolve.")
        add_story(gs, "You eat in silence, strength returning in small, stubborn increments.")
        commit_rng(gs, rng); return

    if it == "ink_of_remembrance":
        gs.player.resolve = min(25, gs.player.resolve + 2)
        gs.inventory[it] -= 1
        if gs.inventory[it] <= 0: del gs.inventory[it]
        add_log(gs, "Ink-dark memory steadies you. +2 Resolve.")
        add_story(gs, "You remember who you were. The memory steadies your resolve.")
        commit_rng(gs, rng); return

    if it == "mud_clod" and room.encounter and room.encounter.key == "cerberus" and "cerberus" not in gs.resolved_encounters:
        gs.inventory[it] -= 1
        if gs.inventory[it] <= 0: del gs.inventory[it]
        gs.resolved_encounters.add("cerberus")
        add_log(gs, "You hurl mud into Cerberus' mouths. The beast chokes and retreats.")
        add_story(gs, "You feed Cerberus the mire itself; hunger falters into confusion.")
        commit_rng(gs, rng); return

    if it == "seal_of_exit" and room.rid == "lucifer_pit":
        gs.flags["ascent_revealed"] = True
        add_log(gs, "The seal burns against the ice. A hidden passage becomes visible: ASCENT.")
        add_story(gs, "You press the seal to the ice. The world admits a crack it tried to hide.")
        commit_rng(gs, rng); return

    add_log(gs, "Nothing happens.")
    commit_rng(gs, rng)

def rest(gs: GameState) -> None:
    rng = gs_rng(gs)
    heal = 3
    gs.player.hp = min(gs.player.hp_max, gs.player.hp + heal)
    add_log(gs, f"You rest briefly. +{heal} HP.")
    add_story(gs, "You rest—briefly—stealing a moment from the machine of punishment.")
    # risk based on circles visited count
    risk = min(0.35, 0.10 + 0.02 * max(0, len(gs.visited)//8))
    if rng.random() < risk:
        loss = rng.randint(1,3)
        gs.player.hp = max(1, gs.player.hp - loss)
        add_log(gs, f"… The place answers your pause. -{loss} HP.")
        add_story(gs, "The place answers your pause with a small cruelty.")
    commit_rng(gs, rng)

def pray(gs: GameState) -> None:
    rng = gs_rng(gs)
    gs.player.resolve = min(25, gs.player.resolve + 1)
    add_log(gs, "You steady your breath. Resolve +1.")
    add_story(gs, "You steady your breath and refuse to let despair become your language.")
    if rng.random() < 0.10:
        add_log(gs, "… Something notices.")
        add_story(gs, "Something notices.")
    commit_rng(gs, rng)

def show_inventory(gs: GameState) -> None:
    if not gs.inventory:
        add_log(gs, "Inventory: (empty)"); return
    add_log(gs, "Inventory: " + ", ".join([f"{pretty_item_name(k)} x{v}" for k,v in sorted(gs.inventory.items())]))

def show_stats(gs: GameState) -> None:
    p = gs.player
    add_log(gs, f"Stats: HP {p.hp}/{p.hp_max} | ATK {p.atk} | DEF {p.defense} | RESOLVE {p.resolve} | GOLD {p.gold}")

def show_objectives(gs: GameState) -> None:
    if not gs.objectives:
        add_log(gs, "Objectives: (none)"); return
    add_log(gs, "Objectives:")
    for o in gs.objectives[-12:]:
        add_log(gs, f"  - {o}")

def set_menu(gs: GameState, m: str) -> None:
    if gs.menu != m:
        gs.menu = m
        gs.menu_version += 1

def clear_menu(gs: GameState) -> None:
    set_menu(gs, "")

def build_action_bar(gs: GameState, world: Dict[str, Room]) -> List[str]:
    room = world[gs.current]
    if gs.in_combat and gs.combat_enemy:
        return ["STRIKE","GUARD","USE","FLEE","STATS","SAVE"]
    if room.encounter and room.encounter.kind == "block" and room.encounter.key not in gs.resolved_encounters:
        return ["PROCEED","LOOK","MOVE","TALK","USE","SKETCH","SAVE","OBJECTIVES","CODEX"]
    return ["MOVE","LOOK","TALK","TAKE","USE","SKETCH","REST","PRAY","INVENTORY","STATS","OBJECTIVES","CODEX","SAVE","LOAD","HELP"]


def ui_action(gs: GameState, world: Dict[str, Room], action: str) -> None:
    a = action.upper()

    if a == "MOVE":
        set_menu(gs, "move")
        return

    if a == "LOOK":
        room = world[gs.current]
        add_log(gs, room.desc)

        # Optional extra sensory texture on LOOK (deterministic RNG)
        rng = gs_rng(gs)
        style = _circle_style(room.circle + " " + room.name)
        if rng.random() < 0.40:
            add_log(gs, "… " + choose_ambient_detail(gs, style, rng))
        commit_rng(gs, rng)

        if room.items:
            add_log(gs, "Items here: " + ", ".join([f"{k} x{v}" for k, v in room.items.items()]))
        if room.npcs:
            add_log(gs, "Voices here: " + ", ".join(room.npcs.keys()))
        if room.encounter and room.encounter.key not in gs.resolved_encounters:
            add_log(gs, f"Unresolved: {room.encounter.name}")
        return

    if a == "TALK":
        set_menu(gs, "talk"); return
    if a == "TAKE":
        set_menu(gs, "take"); return
    if a == "USE":
        set_menu(gs, "use"); return
    if a == "INVENTORY":
        show_inventory(gs); return
    if a == "STATS":
        show_stats(gs); return
    if a == "OBJECTIVES":
        show_objectives(gs); return
    if a == "CODEX":
        set_menu(gs, "codex"); return
    if a == "REST":
        rest(gs); return
    if a == "PRAY":
        pray(gs); return

    if a == "SKETCH":
        # Generate a procedural illustration driven by current room + entities.
        path, caption, hint = generate_illustration(gs, world, slot_hint="slot1")
        gs.last_illustration_path = path
        gs.last_illustration_caption = caption
        gs.show_illustration_overlay = False  # shown inline in the journal; click it to enlarge

        # Insert an inline illustration marker into the journal stream.
        meta = {"path": path, "caption": caption, "hint": hint, "rid": world[gs.current].rid, "seed": _seed_from_state(gs, world)}
        add_log(gs, "")
        add_log(gs, "🜂 The book drinks ink. A symmetric blot rises between heartbeats.")
        add_log(gs, INTERNAL_ILLUSTRATION_TAG + json.dumps(meta, ensure_ascii=False))
        add_log(gs, "")

        # Savebook keeps the raw path for PDF embedding, but the *game UI* never prints it.
        add_story(gs, "")
        add_story(gs, f"[Illustration: {path}]")
        add_story(gs, caption)
        if hint:
            add_story(gs, f"Hint: {hint}")
        return

    if a == "SAVE":
        set_menu(gs, "save"); return
    if a == "LOAD":
        set_menu(gs, "load"); return

    if a == "HELP":
        add_log(gs,
            "How to play:\n"
            "  - Use buttons (no typing).\n"
            "  - MOVE shows exits; click one. Unknown destinations stay hidden until visited.\n"
            "  - Map is informational: click nodes to inspect (no movement).\n"
            "  - PROCEED resolves blockages; combat requires STRIKE/GUARD/USE/FLEE.\n"
            "  - SAVE/LOAD uses slot files in ./saves.\n"
            "  - GHOST PLAY toggles autopilot (random playthrough, real-time).\n"
            "Controls: TAB fullscreen windowed | ESC exit confirm"
        )
        return

    if a == "PROCEED":
        resolve_block(gs, world); return

    if a == "STRIKE":
        combat_player_strike(gs)
        if gs.combat_enemy and gs.combat_enemy.hp > 0:
            combat_enemy_turn(gs)
        finish_combat_if_needed(gs, world)
        return

    if a == "GUARD":
        combat_player_guard(gs)
        combat_enemy_turn(gs)
        finish_combat_if_needed(gs, world)
        return

    if a == "FLEE":
        add_log(gs, "You break away from combat.")
        add_story(gs, "You break away from combat, refusing a senseless death.")
        gs.in_combat = False
        gs.combat_enemy = None
        if gs.previous and gs.previous in world:
            gs.current, gs.previous = gs.previous, gs.current
            on_enter_room(gs, world)
        return

def build_context_choices(gs: GameState, world: Dict[str, Room]) -> List[Tuple[str, Callable[[], None], bool]]:
    room = world[gs.current]
    out: List[Tuple[str, Callable[[], None], bool]] = []
    def add(label: str, fn: Callable[[], None], enabled: bool=True):
        out.append((label, fn, enabled))

    if gs.menu == "move":
        for lbl, dst in room.exits.items():
            if not exit_is_visible(gs, room.rid, lbl):
                continue
            enabled = can_use_exit(gs, room, lbl)
            dst_name = world[dst].name if (dst in gs.discovered) else "Unknown"
            add(f"{lbl.upper()} → {dst_name}", (lambda l=lbl: (clear_menu(gs), do_travel(gs, world, l))), enabled)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "talk":
        if room.npcs:
            for npc in room.npcs.keys():
                add(npc, (lambda n=npc: (talk_to(gs, world, n), clear_menu(gs))), True)
        else:
            add("(no one here)", (lambda: None), False)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "take":
        if room.items:
            for item, qty in sorted(room.items.items()):
                add(f"{item} x{qty}", (lambda it=item: (take_item(gs, world, it), clear_menu(gs))), True)
        else:
            add("(nothing to take)", (lambda: None), False)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "use":
        if gs.inventory:
            for item, qty in sorted(gs.inventory.items()):
                add(f"{item} x{qty}", (lambda it=item: (use_item(gs, world, it), clear_menu(gs))), qty > 0)
        else:
            add("(no items)", (lambda: None), False)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "save":
        for s in SAVE_SLOTS:
            add(s.upper(), (lambda sl=s: (save_to_slot(gs, world, sl), add_log(gs, f"Saved to {sl}."), add_story(gs, f"You set ink to page, preserving the descent (saved to {sl})."), clear_menu(gs))), True)
        add("EXPORT PDF (choose slot)", (lambda: set_menu(gs, "pdf")), True)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "load":
        for s in SAVE_SLOTS:
            enabled = (SAVE_DIR / f"{s}.txt").exists()
            def loader(sl=s):
                ngs = load_from_slot(sl)
                gs.current = ngs.current
                gs.previous = ngs.previous
                gs.visited = ngs.visited
                gs.discovered = ngs.discovered
                gs.resolved_encounters = ngs.resolved_encounters
                gs.inventory = ngs.inventory
                gs.flags = ngs.flags
                gs.log = ngs.log
                gs.story = ngs.story
                gs.codex = ngs.codex
                gs.objectives = ngs.objectives
                gs.chapters = ngs.chapters
                gs.player = ngs.player
                gs.in_combat = False
                gs.combat_enemy = None
                gs.guard_next = False
                gs.rng_seed = ngs.rng_seed
                gs.rng_calls = ngs.rng_calls
                gs.log_version += 1
                gs.story_version += 1
                add_log(gs, f"Loaded {sl}.")
                add_story(gs, "")
                add_story(gs, f"(The book opens again at {world[gs.current].name}.)")
                init_room_items(gs, world)
                regenerate_missing_media(gs, world)
                on_enter_room(gs, world)
            add(s.upper(), (lambda fn=loader: (fn(), clear_menu(gs))), enabled)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    elif gs.menu == "pdf":
        for s in SAVE_SLOTS:
            enabled = (SAVE_DIR / f"{s}.txt").exists()
            def exporter(sl=s):
                try:
                    p = export_pdf_from_slot(sl)
                    add_log(gs, f"Exported PDF: {sl}.pdf (see the saves folder)")
                    add_story(gs, f"You press the book into a more permanent form (exported PDF: {sl}).")
                except Exception as e:
                    add_log(gs, f"PDF export failed: {e}")
            add(f"{s.upper()} → PDF", (lambda fn=exporter: (fn(), clear_menu(gs))), enabled)
        add("CANCEL", (lambda: clear_menu(gs)), True)


    elif gs.menu == "event":
        eid = gs.pending_event

        def done():
            gs.flags[f"event_done_{eid}"] = True
            gs.pending_event = ""
            clear_menu(gs)

        if eid == "name_contact":
            add("PRESS YOUR THUMB TO THE NAME", (lambda: (
                add_log(gs, "Cold goes through you like ink through paper. The wall accepts a print that is not blood—yet."),
                add_story(gs, "You press your thumb to the stone. The cold writes you down."),
                setattr(gs, "merit", gs.merit + 1),
                gs.flags.__setitem__("archive_revealed", True),
                add_log(gs, "A hidden seam opens in the Hall of Names. (Secret path revealed)"),
                add_story(gs, "A seam in the wall loosens. An archive door admits you were expected."),
                done()
            )), True)
            add("TURN AWAY", (lambda: (
                add_log(gs, "You refuse the wall’s invitation. The names continue without you."),
                add_story(gs, "You turn away. The wall watches anyway."),
                setattr(gs, "merit", gs.merit - 1),
                done()
            )), True)

        elif eid == "sullen_soul":
            add("PULL THEM FREE", (lambda: (
                add_log(gs, "You grab the wrist. The mud fights you like a jealous god."),
                add_story(gs, "You pull. The mud tries to keep its secret."),
                setattr(gs, "merit", gs.merit + 1),
                setattr(gs.player, "hp", max(1, gs.player.hp - 2)),
                gs.inventory.__setitem__("ration", gs.inventory.get("ration", 0) + 1),
                add_log(gs, "The soul coughs up a ration wrapped in cloth. (-2 HP, ration +1, merit +1)"),
                add_story(gs, "It gives you a small kindness it never got to spend: a ration, still dry."),
                done()
            )), True)
            add("LET THEM SINK", (lambda: (
                add_log(gs, "The hand slowly disappears. The marsh makes no sound of thanks."),
                add_story(gs, "You do nothing. The marsh learns your shape."),
                setattr(gs, "merit", gs.merit - 1),
                done()
            )), True)

        elif eid == "filth_oracle":
            add("CONFESS SOMETHING TRUE", (lambda: (
                add_log(gs, "You speak a truth that stings. The ditch listens greedily."),
                add_story(gs, "You confess. The filth becomes a mouth for a moment."),
                setattr(gs, "merit", gs.merit + 1),
                add_codex(gs, "A Dirty Prophecy", "A voice in filth told you: 'The only exit Hell hides is the one you refuse to deserve.'"),
                add_log(gs, "Your resolve hardens. (merit +1, codex unlocked)"),
                done()
            )), True)
            add("LIE / BRIBE WITH GOLD", (lambda: (
                add_log(gs, "You try to buy knowledge with small metal. The filth laughs."),
                add_story(gs, "You lie. Hell recognizes its dialect."),
                setattr(gs, "merit", gs.merit - 1),
                gs.player.__setattr__("gold", max(0, gs.player.gold - 5)),
                add_log(gs, "The ditch takes 5 gold and gives you nothing. (merit -1)"),
                done()
            )), True)

        elif eid == "black_glass":
            add("TAKE THE GLASS AND KEEP IT", (lambda: (
                take_item(gs, world, "black_glass"),
                add_log(gs, "The shard feels heavier than its size."),
                add_story(gs, "In it, your reflection blinks out of sync."),
                setattr(gs, "merit", gs.merit - 1),
                done()
            )), True)
            add("BREAK IT TO FREE THE TEARS", (lambda: (
                (lambda room=world[gs.current]: (room.items.pop("black_glass", None), gs.room_items.__setitem__(room.rid, dict(room.items))))(),
                add_log(gs, "You shatter the glass. The ice exhales a sound like relief."),
                add_story(gs, "You break it. Somewhere, a frozen tear finally falls."),
                setattr(gs, "merit", gs.merit + 2),
                setattr(gs.player, "resolve", min(25, gs.player.resolve + 1)),
                add_log(gs, "Resolve +1. (merit +2)"),
                done()
            )), True)

        else:
            add("(nothing to decide)", (lambda: done()), True)
    elif gs.menu == "codex":
        if gs.codex:
            for t in sorted(gs.codex.keys())[:30]:
                def opener(title=t):
                    add_log(gs, "")
                    add_log(gs, f"📜 {title}")
                    add_log(gs, gs.codex[title])
                add(t if len(t)<=28 else t[:28]+"…", (lambda fn=opener: (fn(), clear_menu(gs))), True)
        else:
            add("(codex empty)", (lambda: None), False)
        add("CANCEL", (lambda: clear_menu(gs)), True)

    return out


# ----------------------------
# Ghost Play (autopilot)
# ----------------------------

_ROMAN = {"i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,"x":10}

def _room_depth(room: Room) -> int:
    c = (room.circle or "").lower()
    if c.startswith("antechamber"):
        return 0
    if "empyrean" in c or c.startswith("heaven"):
        return 20
    m = re.search(r"circle\s+([ivx]+)", c)
    if m:
        return int(_ROMAN.get(m.group(1), 0))
    m = re.search(r"circle\s+(\d+)", c)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    return 0

def _weighted_choice(rng: random.Random, items: list, weights: list[float]):
    total = 0.0
    for w in weights:
        total += max(0.0, float(w))
    if total <= 0.0:
        return rng.choice(items)
    r = rng.random() * total
    acc = 0.0
    for it, w in zip(items, weights):
        acc += max(0.0, float(w))
        if r <= acc:
            return it
    return items[-1]

def ghost_play_step(gs: GameState, world: Dict[str, Room], rng: random.Random) -> bool:
    """Returns True if autopilot should continue."""

    # Stop automatically when the epilogue has fired.
    if gs.flags.get("ending_done", False):
        add_log(gs, "Ghost Play: complete.")
        return False

    # Close illustration overlay automatically.
    if gs.show_illustration_overlay:
        gs.show_illustration_overlay = False
        return True

    room = world[gs.current]

    # If a contextual menu is open, pick one enabled option.
    if gs.menu:
        choices = build_context_choices(gs, world)
        enabled = [(lab, fn) for (lab, fn, en) in choices if en]
        if not enabled:
            clear_menu(gs)
            return True
        lab, fn = rng.choice(enabled)
        add_log(gs, f"[Ghost] {lab}")
        try:
            fn()
        except Exception as e:
            add_log(gs, f"[Ghost] action error: {e}")
            clear_menu(gs)
        return True

    # Combat logic
    if gs.in_combat and gs.combat_enemy:
        # Heal first if needed
        if gs.player.hp <= max(8, gs.player.hp_max // 3):
            if gs.inventory.get("bandage", 0) > 0:
                add_log(gs, "[Ghost] USE bandage")
                use_item(gs, world, "bandage")
                return True
            if gs.inventory.get("ration", 0) > 0:
                add_log(gs, "[Ghost] USE ration")
                use_item(gs, world, "ration")
                return True

        # If critically low, sometimes flee (if possible)
        if gs.player.hp <= 6 and gs.previous and rng.random() < 0.35:
            add_log(gs, "[Ghost] FLEE")
            ui_action(gs, world, "FLEE")
            return True

        # Otherwise strike/guard with a little variance
        if rng.random() < 0.82:
            add_log(gs, "[Ghost] STRIKE")
            ui_action(gs, world, "STRIKE")
        else:
            add_log(gs, "[Ghost] GUARD")
            ui_action(gs, world, "GUARD")
        return True

    # Block encounters: keep trying to PROCEED.
    if room.encounter and room.encounter.kind == "block" and room.encounter.key not in gs.resolved_encounters:
        add_log(gs, "[Ghost] PROCEED")
        ui_action(gs, world, "PROCEED")
        return True

    # Opportunistic survival
    if gs.player.hp <= gs.player.hp_max // 2:
        if gs.inventory.get("bandage", 0) > 0 and rng.random() < 0.55:
            add_log(gs, "[Ghost] USE bandage")
            use_item(gs, world, "bandage")
            return True
        if gs.inventory.get("ration", 0) > 0 and rng.random() < 0.40:
            add_log(gs, "[Ghost] USE ration")
            use_item(gs, world, "ration")
            return True

    # Loot and lore first (randomized)
    if room.items and rng.random() < 0.62:
        it = rng.choice(list(room.items.keys()))
        add_log(gs, f"[Ghost] TAKE {it}")
        take_item(gs, world, it)
        return True

    if room.npcs and rng.random() < 0.24:
        npc = rng.choice(list(room.npcs.keys()))
        add_log(gs, f"[Ghost] TALK {npc}")
        talk_to(gs, world, npc)
        return True

    if rng.random() < 0.035:
        add_log(gs, "[Ghost] SKETCH")
        ui_action(gs, world, "SKETCH")
        return True

    # Movement choice (weighted toward descent + unexplored)
    cands = []
    for lbl, dst in room.exits.items():
        if not exit_is_visible(gs, room.rid, lbl):
            continue
        if not can_use_exit(gs, room, lbl):
            continue
        cands.append((lbl, dst))
    if not cands:
        add_log(gs, "[Ghost] LOOK")
        ui_action(gs, world, "LOOK")
        return True

    cur_d = _room_depth(room)
    weights = []
    for lbl, dst in cands:
        dr = world[dst]
        w = 1.0
        if dst not in gs.visited:
            w *= 3.0
        dd = _room_depth(dr)
        if dd > cur_d:
            w *= 3.4
        elif dd < cur_d:
            w *= 0.7
        if gs.previous and dst == gs.previous:
            w *= 0.20

        l = lbl.lower()
        if l in ("down","south","forward","to_acheron","boat","land","ascent","archive"):
            w *= 2.0
        if l in ("back","up","north"):
            w *= 0.9

        weights.append(w)

    lbl, dst = _weighted_choice(rng, cands, weights)
    add_log(gs, f"[Ghost] MOVE {lbl.upper()}")
    do_travel(gs, world, lbl)
    return True

def main(
    host_mode: bool = False,
    start_window_size: Tuple[int, int] | None = None,
    start_borderless: bool = False,
    clean_start_media: bool = False,
    capture_frame: str | None = None,
):
    ensure_dirs()
    if clean_start_media:
        clean_generated_media(reason="new_story")
    pygame.init()
    init_music()
    pygame.display.set_caption(APP_TITLE)

    window_size = tuple(start_window_size or (VIRTUAL_W, VIRTUAL_H))
    is_borderless = bool(start_borderless)
    if is_borderless:
        screen = pygame.display.set_mode(window_size, pygame.NOFRAME | pygame.DOUBLEBUF)
    else:
        try:
            screen = pygame.display.set_mode(window_size, pygame.RESIZABLE | pygame.DOUBLEBUF, vsync=1)
        except TypeError:
            screen = pygame.display.set_mode(window_size, pygame.RESIZABLE | pygame.DOUBLEBUF)

    try_apply_red_cursor()

    virtual = pygame.Surface((VIRTUAL_W, VIRTUAL_H)).convert()
    clock = pygame.time.Clock()

    font_ui = pygame.font.SysFont("consolas", 20) or pygame.font.Font(None, 22)
    font_small = pygame.font.SysFont("consolas", 16) or pygame.font.Font(None, 18)
    font_title = pygame.font.SysFont("consolas", 28, bold=True) or pygame.font.Font(None, 30)

    cache = TextCache()
    wrap_cache = WrapCache()

    image_cache = ImageCache()
    journal_image_hitboxes: List[Tuple[pygame.Rect, str, str, str]] = []


    world = build_world()

    seed = int(time.time()) & 0x7FFFFFFF
    gs = GameState(current="gate", rng_seed=seed, rng_calls=0)
    gs.flags["ascent_revealed"] = False

    init_room_items(gs, world)

    add_log(gs, "Welcome. Explore side paths to unlock deeper descent.")
    add_story(gs, "")
    add_story(gs, "Prologue")
    add_story(gs, "--------")
    add_story(gs, "You arrive at the threshold of a descent described in an older tongue—still accurate in its cruelty.")
    push_objective(gs, "Enter the Vestibule and find a way toward Acheron.")
    add_codex(gs, "The Descent", "Hell is structured as a series of circles, each reflecting a moral logic and a punishment that mirrors the sin.")

    on_enter_room(gs, world)

    left_rect = pygame.Rect(40, 40, 1140, 1000)
    story_rect = pygame.Rect(left_rect.x + 16, left_rect.y + 64, left_rect.w - 32, left_rect.h - 190)
    bottom_rect = pygame.Rect(left_rect.x + 16, left_rect.bottom - 112, left_rect.w - 32, 92)

    map_rect = pygame.Rect(1220, 40, 660, 800)
    stats_rect = pygame.Rect(1220, 860, 660, 180)

    # Per-circle gritty backgrounds + map noise cache
    bg_cache: Dict[str, pygame.Surface] = {}
    map_noise_cache: Dict[Tuple[str,int,int], pygame.Surface] = {}
    last_bg_circle = ""

    # Map hover/click popup
    map_popup_text = ""
    map_popup_until_ms = 0

    # Ghost Play (autopilot)
    ghost_play = False
    ghost_next_ms = 0
    ghost_rng = random.Random(seed ^ 0x5A17C0DE)


    scroll = 0
    exit_armed = False
    exit_armed_at = 0.0

    prev_windowed_size = window_size

    action_buttons: List[UIButton] = []
    menu_buttons: List[UIButton] = []
    last_action_sig = ""
    last_menu_sig = ""
    last_menu_version = -1

    # Illustration overlay hitbox (updated during render)
    illustration_box_rect = None

    def arm_exit():
        nonlocal exit_armed, exit_armed_at
        exit_armed = True
        exit_armed_at = time.time()
        add_log(gs, "Press ESC again to quit.")

    def disarm_exit():
        nonlocal exit_armed
        exit_armed = False


    # A single utility button, far from the action bar: toggles autopilot.
    ghost_btn = UIButton(
        pygame.Rect(map_rect.right - 230, map_rect.y + 8, 210, 40),
        "GHOST PLAY: OFF",
        (lambda: None),
        True
    )

    def toggle_ghost_play():
        nonlocal ghost_play, ghost_next_ms
        ghost_play = not ghost_play
        ghost_next_ms = pygame.time.get_ticks() + 300
        add_log(gs, f"Ghost Play: {'ON' if ghost_play else 'OFF'}")
        add_story(gs, f"(Autopilot {'engaged' if ghost_play else 'disengaged'}.)")

    ghost_btn.on_click = toggle_ghost_play

    def toggle_borderless():
        nonlocal screen, is_borderless, prev_windowed_size
        if not is_borderless:
            prev_windowed_size = screen.get_size()
            info = pygame.display.Info()
            w, h = info.current_w, info.current_h
            try:
                screen = pygame.display.set_mode((w, h), pygame.NOFRAME | pygame.DOUBLEBUF, vsync=1)
            except TypeError:
                screen = pygame.display.set_mode((w, h), pygame.NOFRAME | pygame.DOUBLEBUF)
            is_borderless = True
            try_apply_red_cursor()
            add_log(gs, "Borderless fullscreen windowed: ON")
        else:
            try:
                screen = pygame.display.set_mode(prev_windowed_size, pygame.RESIZABLE | pygame.DOUBLEBUF, vsync=1)
            except TypeError:
                screen = pygame.display.set_mode(prev_windowed_size, pygame.RESIZABLE | pygame.DOUBLEBUF)
            is_borderless = False
            try_apply_red_cursor()
            add_log(gs, "Borderless fullscreen windowed: OFF")

    def clamp_scroll():
        nonlocal scroll
        scroll = max(0, scroll)

    def rebuild_action_buttons():
        nonlocal action_buttons, last_action_sig
        actions = build_action_bar(gs, world)
        sig = "|".join(actions) + f"|combat={gs.in_combat}|menu={gs.menu}"
        if sig == last_action_sig:
            return
        last_action_sig = sig
        action_buttons = []
        pad = 10
        cols = 6
        rows = max(1, math.ceil(len(actions) / cols))
        btn_w = (bottom_rect.w - pad*(cols-1)) // cols
        btn_h = (bottom_rect.h - pad*(rows-1)) // rows

        room = world[gs.current]

        def action_enabled(label: str) -> bool:
            lab = label.upper()
            if lab == "INVENTORY":
                return len(gs.inventory) > 0
            if lab == "USE":
                return len(gs.inventory) > 0
            if lab == "TAKE":
                return len(room.items) > 0
            if lab == "TALK":
                return len(room.npcs) > 0
            if lab == "MOVE":
                # any visible exits?
                for ex in room.exits.keys():
                    if exit_is_visible(gs, room.rid, ex):
                        return True
                return False
            if lab == "CODEX":
                return len(gs.codex) > 0
            if lab == "OBJECTIVES":
                return len(gs.objectives) > 0
            if lab == "FLEE":
                return bool(gs.previous and gs.previous in world)
            # SAVE/LOAD/LOOK/STATS/REST/PRAY/HELP/PROCEED/STRIKE/GUARD always enabled
            return True

        for i,a in enumerate(actions):
            r = i // cols
            c = i % cols
            x = bottom_rect.x + c*(btn_w+pad)
            y = bottom_rect.y + r*(btn_h+pad)
            rect = pygame.Rect(x,y,btn_w,btn_h)
            enabled = action_enabled(a)

            def mk(act=a):
                def _():
                    disarm_exit()
                    ui_action(gs, world, act)
                    clamp_scroll()
                return _
            action_buttons.append(UIButton(rect, a, mk(), enabled))

    def rebuild_menu_buttons():
        nonlocal menu_buttons, last_menu_sig, last_menu_version
        if gs.menu == "":
            menu_buttons = []
            last_menu_sig = ""
            last_menu_version = gs.menu_version
            return
        if last_menu_version == gs.menu_version:
            return
        last_menu_version = gs.menu_version
        choices = build_context_choices(gs, world)
        labels = [c[0] for c in choices]
        sig = gs.menu + "|" + "|".join(labels)
        if sig == last_menu_sig:
            return
        last_menu_sig = sig
        menu_buttons = []

        strip_h = 138
        strip = pygame.Rect(story_rect.x, story_rect.bottom - strip_h, story_rect.w, strip_h)
        pad = 10
        cols = 2 if len(choices) <= 6 else 3
        rows = max(1, math.ceil(len(choices) / cols))
        btn_w = (strip.w - pad*(cols-1)) // cols
        btn_h = max(36, (strip.h - pad*(rows-1)) // rows)

        for i,(label, fn, enabled) in enumerate(choices):
            rr = i // cols
            cc = i % cols
            x = strip.x + cc*(btn_w+pad)
            y = strip.y + rr*(btn_h+pad)
            rect = pygame.Rect(x,y,btn_w,btn_h)
            def mk(cb=fn):
                def _():
                    disarm_exit()
                    cb()
                    clamp_scroll()
                return _
            menu_buttons.append(UIButton(rect, label, mk(), enabled))

    # --- DEFENSIVE GRAIN INIT ---

    # Ensure film grain locals exist before first use

    try:

        grain_timer

    except Exception:

        grain_timer = 0

    try:

        grain_rng

    except Exception:

        grain_rng = random.Random(gs.rng_seed ^ 0xA5A5A5)
    if 'grain_tile' not in locals():
        grain_tile = make_grain_tile(grain_rng, 256, 256)

    if capture_frame:
        cur_circle = world[gs.current].circle
        bg_cache[cur_circle] = gen_gritty_background(cur_circle, (VIRTUAL_W, VIRTUAL_H), seed)
        virtual.blit(bg_cache[cur_circle], (0, 0))
        draw_panel(virtual, left_rect, THEME['panel_border'], THEME['panel_fill'], accent=True)
        virtual.blit(cache.render(font_title, 'JOURNAL', THEME['text']), (left_rect.x+16, left_rect.y+16))
        draw_panel(virtual, stats_rect, THEME['panel_border'], THEME['panel_fill'], accent=True)
        draw_map(virtual, world, gs, map_rect, font_small, cache, (0, 0), None, '', 0, seed, map_noise_cache)
        pygame.image.save(virtual, capture_frame)
        if not host_mode:
            pygame.quit()
        return capture_frame

    while True:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if host_mode:
                    return "return_to_host"
                arm_exit()

            elif event.type == pygame.KEYDOWN:
                if exit_armed and event.key != pygame.K_ESCAPE:
                    disarm_exit()
                if event.key == pygame.K_ESCAPE:
                    if not exit_armed:
                        arm_exit()
                    else:
                        if host_mode:
                            return "return_to_host"
                        pygame.quit(); return
                elif event.key == pygame.K_TAB:
                    toggle_borderless()

            elif event.type == pygame.MOUSEWHEEL:
                scroll += -event.y * 40
                scroll = max(0, scroll)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                vp = compute_viewport(*screen.get_size())
                vpos = window_to_virtual(vp, *event.pos)
                if not vpos:
                    continue
                mx,my = vpos

                # Close illustration overlay if clicked
                if gs.show_illustration_overlay and illustration_box_rect is not None:
                    if illustration_box_rect.collidepoint((mx,my)):
                        gs.show_illustration_overlay = False
                        continue




                # Inline sketches in journal: click to enlarge
                if (not gs.show_illustration_overlay) and journal_image_hitboxes and story_rect.collidepoint((mx, my)):
                    opened = False
                    for rr, pth, cap, hint in journal_image_hitboxes:
                        if rr.collidepoint((mx, my)):
                            if pth:
                                gs.last_illustration_path = pth
                                gs.last_illustration_caption = (cap + ('  ' + hint if hint else '')).strip()
                                gs.show_illustration_overlay = True
                            opened = True
                            break
                    if opened:
                        continue
                # Ghost Play button (utility; kept away from other buttons)
                if ghost_btn.enabled and ghost_btn.rect.collidepoint((mx, my)):
                    ghost_btn.on_click()
                    continue

                clicked = False
                for btn in menu_buttons:
                    if btn.enabled and btn.rect.collidepoint((mx,my)):
                        btn.on_click(); clicked = True; break
                if clicked: continue
                for btn in action_buttons:
                    if btn.enabled and btn.rect.collidepoint((mx,my)):
                        btn.on_click(); clicked = True; break
                if clicked: continue

                hit = room_hit_test(world, gs, map_rect, mx, my)
                if hit:
                    # Map is informational only: clicking nodes should never move the player.
                    r = world.get(hit)
                    if r:
                        tag = "CURRENT" if hit == gs.current else ("VISITED" if hit in gs.visited else "DISCOVERED")
                        base = r.name.split(" (")[0].strip()
                        snippet = r.desc.split("\n")[0].strip()
                        if len(snippet) > 90:
                            snippet = snippet[:87].rstrip() + "…"
                        map_popup_text = f"{r.circle} — {base} ({tag}). {snippet}"
                        map_popup_until_ms = pygame.time.get_ticks() + 2600
                    continue

            elif event.type == pygame.VIDEORESIZE and not is_borderless:
                try:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE | pygame.DOUBLEBUF, vsync=1)
                except TypeError:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE | pygame.DOUBLEBUF)
                try_apply_red_cursor()

        if exit_armed and (time.time() - exit_armed_at) > 3.0:
            exit_armed = False
        # Ghost Play scheduler (real-time autopilot)
        if ghost_play:
            now_ms = pygame.time.get_ticks()
            if now_ms >= ghost_next_ms:
                # Vary cadence slightly so it feels "alive"
                ghost_next_ms = now_ms + int(420 + ghost_rng.random() * 720)
                try:
                    cont = ghost_play_step(gs, world, ghost_rng)
                except Exception as e:
                    add_log(gs, f"Ghost Play crashed: {e}")
                    cont = False
                if not cont:
                    ghost_play = False

        rebuild_action_buttons()
        rebuild_menu_buttons()

        # Render virtual (per-circle gritty faded background)
        cur_circle = world[gs.current].circle
        if cur_circle != last_bg_circle or cur_circle not in bg_cache:
            bg_cache[cur_circle] = gen_gritty_background(cur_circle, (VIRTUAL_W, VIRTUAL_H), seed)
            last_bg_circle = cur_circle
        virtual.blit(bg_cache.get(cur_circle), (0, 0))

        draw_panel(virtual, left_rect, THEME["panel_border"], THEME["panel_fill"], accent=True)
        virtual.blit(cache.render(font_title, "JOURNAL", THEME["text"]), (left_rect.x+16, left_rect.y+16))

        wrap_cache.rebuild(font_ui, font_small, gs.log, gs.log_version, story_rect.w)

        # Pixel-accurate scrolling for mixed text + inline illustrations
        max_scroll = max(0, wrap_cache.total_h - story_rect.h)
        scroll = max(0, min(scroll, max_scroll))
        view_top = max(0, wrap_cache.total_h - story_rect.h - scroll)
        view_bottom = view_top + story_rect.h

        # Clip journal rendering to its rect
        old_clip = virtual.get_clip()
        virtual.set_clip(story_rect)

        # Track clickable sketch rects for this frame
        journal_image_hitboxes.clear()

        cum = 0
        for item in wrap_cache.items:
            item_top = cum
            item_bot = cum + int(item.get('h', 0))
            if item_bot < view_top:
                cum = item_bot
                continue
            if item_top > view_bottom:
                break

            y = story_rect.y + int(item_top - view_top)

            if item.get('kind') == 'text':
                txt = item.get('text', '')
                virtual.blit(cache.render(font_ui, txt, THEME['text_dim']), (story_rect.x, y))
            else:
                # Inline illustration box
                tw = int(item.get('tw', 1))
                th = int(item.get('th', 1))
                box_h = int(item.get('h', th + 40))
                box = pygame.Rect(story_rect.x, y, story_rect.w, box_h)

                # Box background + border
                pygame.draw.rect(virtual, (0, 0, 0), box.move(2, 3), border_radius=12)
                pygame.draw.rect(virtual, (12, 8, 12), box, border_radius=12)
                pygame.draw.rect(virtual, THEME['accent_red_soft'], box, width=2, border_radius=12)

                pad = 12
                ix = box.x + (box.w - tw) // 2
                iy = box.y + pad

                img = image_cache.get_scaled(item.get('path', ''), tw, th)
                if img is not None:
                    virtual.blit(img, (ix, iy))
                else:
                    # Fallback if missing
                    pygame.draw.rect(virtual, (20, 16, 22), pygame.Rect(ix, iy, tw, th), border_radius=10)
                    miss = cache.render(font_small, '(missing sketch)', THEME['text_muted'])
                    virtual.blit(miss, (ix + tw//2 - miss.get_width()//2, iy + th//2 - miss.get_height()//2))

                # Clickable hitbox to enlarge
                journal_image_hitboxes.append((pygame.Rect(ix, iy, tw, th), item.get('path', ''),
                                              ' '.join(item.get('caption_lines', [])),
                                              ' '.join(item.get('hint_lines', []))))

                ty = iy + th + 10
                for ln in item.get('caption_lines', []):
                    virtual.blit(cache.render(font_small, ln, THEME['text']), (box.x + pad, ty))
                    ty += font_small.get_linesize()
                if item.get('caption_lines'):
                    ty += 4
                for ln in item.get('hint_lines', []):
                    virtual.blit(cache.render(font_small, ln, THEME['accent_red']), (box.x + pad, ty))
                    ty += font_small.get_linesize()

            cum = item_bot

        virtual.set_clip(old_clip)
        if gs.menu:
            virtual.blit(cache.render(font_small, f"CHOICES — {gs.menu.upper()}", THEME["accent_red"]), (story_rect.x, story_rect.bottom - 155))

        if menu_buttons:
            strip = pygame.Rect(story_rect.x - 8, story_rect.bottom - 138, story_rect.w + 16, 138)
            pygame.draw.rect(virtual, (10,2,4), strip, border_radius=12)
            pygame.draw.rect(virtual, THEME["accent_red_soft"], strip, width=2, border_radius=12)

        pygame.draw.rect(virtual, (10,7,10), bottom_rect, border_radius=12)
        pygame.draw.rect(virtual, THEME["panel_border_strong"], bottom_rect, width=2, border_radius=12)
        pygame.draw.rect(virtual, THEME["accent_red"], pygame.Rect(bottom_rect.x, bottom_rect.y, bottom_rect.w, 3), border_radius=12)

        vp = compute_viewport(*screen.get_size())
        mv = window_to_virtual(vp, *pygame.mouse.get_pos())
        mouse_v = mv if mv else (0,0)
        hover_rid = room_hit_test(world, gs, map_rect, mouse_v[0], mouse_v[1]) if mv else None

        for btn in menu_buttons:
            draw_button(virtual, btn, font_small, cache, mouse_v)
        for btn in action_buttons:
            draw_button(virtual, btn, font_small, cache, mouse_v)

        draw_map(virtual, world, gs, map_rect, font_small, cache, mouse_v, hover_rid, map_popup_text, map_popup_until_ms, seed, map_noise_cache)

        # Update + draw Ghost Play button (in the map header area)
        ghost_btn.label = "GHOST PLAY: ON" if ghost_play else "GHOST PLAY: OFF"
        draw_button(virtual, ghost_btn, font_small, cache, mouse_v)


        draw_panel(virtual, stats_rect, THEME["panel_border"], THEME["panel_fill"], accent=True)
        cur = world[gs.current]
        p = gs.player
        stats_lines = [
            f"Location: {cur.circle} — {cur.name}",
            f"HP {p.hp}/{p.hp_max}   ATK {p.atk}   DEF {p.defense}   RESOLVE {p.resolve}   GOLD {p.gold}",
            f"Visited: {len(gs.visited)} / {len(world)}   Discovered: {len(gs.discovered)}   Merit: {gs.merit}",
            f"Mode: {'COMBAT' if gs.in_combat else 'EXPLORATION'}   TAB: fullscreen windowed   ESC: exit",
            "Progression is gated: explore side rooms for tokens/sigils.",
            "Secrets exist. Some paths are hidden until the world admits you earned them.",
        ]
        sy = stats_rect.y + 14
        for ln in stats_lines:
            virtual.blit(cache.render(font_small, ln, THEME["text"]), (stats_rect.x+16, sy))
            sy += font_small.get_linesize() + 4

        # Illustration overlay (click to close). Generated at high-res to avoid blockiness.
        illustration_box_rect = None
        if gs.show_illustration_overlay and gs.last_illustration_path:
            try:
                img_path = Path(gs.last_illustration_path)
                if not img_path.is_absolute():
                    img_path = (BASE_DIR / img_path).resolve()
                img = pygame.image.load(img_path.as_posix()).convert_alpha()
                max_w = story_rect.w
                max_h = 380
                iw, ih = img.get_size()
                scale = min(max_w / iw, max_h / ih, 1.0)
                tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
                thumb = pygame.transform.smoothscale(img, (tw, th))
                box = pygame.Rect(story_rect.x, story_rect.y + 10, max_w, th + 60)
                pygame.draw.rect(virtual, (0,0,0), box.move(3,4), border_radius=12)
                pygame.draw.rect(virtual, (10,2,4), box, border_radius=12)
                pygame.draw.rect(virtual, THEME["accent_red_soft"], box, width=2, border_radius=12)
                virtual.blit(thumb, (box.x + (box.w - tw)//2, box.y + 36))
                title = "ILLUSTRATION (click to close)"
                virtual.blit(cache.render(font_small, title, THEME["accent_red"]), (box.x + 12, box.y + 10))
                cap = gs.last_illustration_caption[:120]
                virtual.blit(cache.render(font_small, cap, THEME["text"]), (box.x + 12, box.y + 14 + font_small.get_linesize()))
                illustration_box_rect = box
            except Exception:
                illustration_box_rect = None
        if exit_armed:
            overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
            overlay.fill((0,0,0,140))
            virtual.blit(overlay, (0,0))
            msg = cache.render(font_title, "Press ESC again to quit", (255,220,230))
            virtual.blit(msg, (VIRTUAL_W//2 - msg.get_width()//2, VIRTUAL_H//2 - msg.get_height()//2))

        
        # Film grain (tiled; refresh every ~10 frames for speed)
        grain_timer = (grain_timer + 1) if 'grain_timer' in locals() else 1
        if grain_timer >= 10 or 'grain_tile' not in locals():
            grain_timer = 0
            grain_tile = make_grain_tile(grain_rng, 256, 256)
        blit_tiled_grain(virtual, grain_tile)

        # Scale to window
        win_w, win_h = screen.get_size()
        vp2 = compute_viewport(win_w, win_h)
        screen.fill((0,0,0))
        scaled = pygame.transform.scale(virtual, (vp2.view_w, vp2.view_h))
        screen.blit(scaled, (vp2.view_x, vp2.view_y))
        # In-window frame (OS border colors can't be controlled reliably; draw an internal frame instead)
        frame = pygame.Rect(vp2.view_x, vp2.view_y, vp2.view_w, vp2.view_h)
        # heavy black casing + red trim
        pygame.draw.rect(screen, (0,0,0), frame.inflate(10,10), width=10)
        pygame.draw.rect(screen, (30,0,6), frame.inflate(6,6), width=3)
        pygame.draw.rect(screen, THEME['accent_red'], frame.inflate(4,4), width=2)

        # High-visibility software cursor (bigger + brighter than OS cursor)
        mx_s, my_s = pygame.mouse.get_pos()
        draw_soft_cursor_screen(screen, mx_s, my_s, frame)

        pygame.display.flip()

if __name__ == "__main__":
    try:
        main(clean_start_media=True)
    except Exception as e:
        p = write_crash_log(e)
        try:
            print(f"Crash log written to: {p.as_posix()}")
        except Exception:
            pass
        raise