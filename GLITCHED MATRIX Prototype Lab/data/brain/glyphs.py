import hashlib
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pygame

from .utils import clamp

PX = 2  # pixel block size

def _h256(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).digest()

def _byte01(b: int) -> float:
    return b / 255.0

def _mood_to_params(mood: Tuple[float, float, float]) -> Tuple[float, float, float]:
    v, a, f = mood
    stroke_len = 0.55 + 1.15 * a
    tight = 0.35 + 0.65 * f
    curve = v * 0.9
    return stroke_len, tight, curve

def _color_shift(base: Tuple[int,int,int], mood: Tuple[float,float,float]) -> Tuple[int,int,int]:
    v, a, f = mood
    r, g, b = base
    r = int(clamp(r + 35*a + 25*v, 0, 255))
    g = int(clamp(g + 25*a + 10*v, 0, 255))
    b = int(clamp(b + 30*a - 10*v, 0, 255))
    return r, g, b

def _bresenham(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int,int]]:
    pts = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        pts.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return pts

@dataclass
class CamGlyphRenderer:
    """
    Thought-cam renderer that *draws in realtime*.

    - ingest_thought() creates a new drawing plan (points queue)
    - update(dt) draws a slice of that plan each frame
    - surface changes continuously while drawing, but the plan itself is deterministic
      from (seed + intent + mood + payload + caption)

    Result: evolving Rorschach-like glyphs that can also write short words.
    """
    w: int
    h: int
    seed: int
    base_color: Tuple[int, int, int]

    def __post_init__(self):
        self.surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA).convert_alpha()
        self.core = (self.w // 2, self.h // 2)

        self._bg = (8, 8, 8, 255)
        self._frame = (18, 18, 18, 255)

        self.steps: List[Tuple[int,int,Tuple[int,int,int]]] = []
        self.step_i = 0

        self.pending_clear = False
        self.clear_alpha = 0.0

        self._last_mood = (0.0, 0.3, 0.5)
        self._last_seed_payload = "boot"
        self._idle_timer = 0.0
        self._idle_target = 3.5

        self._font = pygame.font.Font(None, 20)

        self._render_base()

    def _render_base(self):
        self.surf.fill(self._bg)
        pygame.draw.rect(self.surf, self._frame, pygame.Rect(0, 0, self.w, self.h), 2, border_radius=10)
        # core dot
        cx, cy = self.core
        pygame.draw.circle(self.surf, (235, 235, 235), (cx, cy), 2)

    def ingest_thought(self, intent: str, mood: Tuple[float,float,float], payload: str, caption: str = ""):
        self._last_mood = mood
        self._last_seed_payload = f"{intent}|{payload}|{caption}"
        self._idle_timer = 0.0
        # when a new thought arrives, fade old canvas out instead of instant clear
        self.pending_clear = True
        self.clear_alpha = 0.0

        self.steps = self._build_plan(intent=intent, mood=mood, payload=payload, caption=caption)
        self.step_i = 0

    def update(self, dt: float):
        # idle thoughts: even if chat is slow, cams keep expressing
        self._idle_timer += dt
        if self._idle_timer >= self._idle_target and self.step_i >= len(self.steps):
            # auto-generate a new thought-plan (no chat content)
            self._idle_timer = 0.0
            self._idle_target = 2.7 + (1.8 * (1.0 - self._last_mood[2])) + (1.2 * (1.0 - self._last_mood[1]))
            self.ingest_thought("idle", self._last_mood, payload=self._last_seed_payload, caption="")

        # fade old drawing if needed
        if self.pending_clear:
            # overlay black with increasing alpha
            self.clear_alpha += dt * 220.0  # ~1.1s full fade
            a = int(clamp(self.clear_alpha, 0, 255))
            overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, a))
            self.surf.blit(overlay, (0, 0))
            # keep frame and core visible
            pygame.draw.rect(self.surf, self._frame, pygame.Rect(0, 0, self.w, self.h), 2, border_radius=10)
            cx, cy = self.core
            pygame.draw.circle(self.surf, (235, 235, 235), (cx, cy), 2)
            if a >= 250:
                self.pending_clear = False
                # rebuild base to remove artifacts, then continue drawing
                self._render_base()

        # draw steps gradually
        if self.step_i < len(self.steps):
            v, a, f = self._last_mood
            # draw speed is the *flow* of thought: arousal & focus increase speed
            rate = 380.0 + 980.0 * a + 620.0 * f
            budget = int(rate * max(0.0, dt))
            budget = max(1, min(budget, 4200))
            end = min(len(self.steps), self.step_i + budget)
            for i in range(self.step_i, end):
                x, y, col = self.steps[i]
                pygame.draw.rect(self.surf, col, pygame.Rect(x, y, PX, PX))
            self.step_i = end

            # core stays visible
            cx, cy = self.core
            pygame.draw.circle(self.surf, (235, 235, 235), (cx, cy), 2)

    def render_surface(self) -> pygame.Surface:
        return self.surf

    # ---------- plan building ----------

    def _build_plan(self, intent: str, mood: Tuple[float,float,float], payload: str, caption: str) -> List[Tuple[int,int,Tuple[int,int,int]]]:
        digest = _h256(f"{self.seed}|{intent}|{payload}|{round(mood[0],2)}|{round(mood[1],2)}|{round(mood[2],2)}|{caption}")
        stroke_len, tight, curve = _mood_to_params(mood)

        family = {
            "question": 1, "challenge": 2, "comfort": 3, "joke": 4, "statement": 5,
            "research": 6, "idle": 7, "boot": 8,
        }.get(intent, 0)

        base_col = _color_shift(self.base_color, mood)

        cx, cy = self.core
        max_r = int(min(self.w, self.h) * 0.44)

        steps: List[Tuple[int,int,Tuple[int,int,int]]] = []

        # pulse ring first
        ring_r = int(10 + 16 * mood[1])
        steps += self._ring_steps(cx, cy, ring_r, base_col, density=family + 4)

        # vectors
        nvec = 3 + (digest[0] % 4)
        for i in range(nvec):
            b0 = digest[2 + i*5]
            b1 = digest[3 + i*5]
            b2 = digest[4 + i*5]
            b3 = digest[5 + i*5]
            b4 = digest[6 + i*5]

            ang = (2 * math.pi) * (_byte01(b0) ** (0.7 + 0.6 * tight))
            ang += family * 0.55

            rad = int(max_r * (0.35 + 0.65 * _byte01(b1)) * stroke_len)
            tx = int(cx + math.cos(ang) * rad)
            ty = int(cy + math.sin(ang) * rad)

            bend = (_byte01(b2) - 0.5) * 0.9 + curve * 0.6
            mx = int((cx + tx) / 2 + math.cos(ang + math.pi/2) * rad * 0.18 * bend)
            my = int((cy + ty) / 2 + math.sin(ang + math.pi/2) * rad * 0.18 * bend)

            thickness = 1 + (b3 % 2)
            steps += self._stroke_steps(cx, cy, mx, my, base_col, thickness)
            steps += self._stroke_steps(mx, my, tx, ty, base_col, 1 + (b4 % 2))

            # meaning markers by family
            if family in (1, 2):  # question/challenge spikes
                steps += self._spike_steps(tx, ty, ang, base_col, count=2 + (b4 % 3))
            elif family in (3,):  # comfort blob
                steps += self._blob_steps(tx, ty, base_col, radius=6 + (b3 % 8))
            elif family in (4,):  # joke spiral
                steps += self._spiral_steps(tx, ty, base_col, turns=1 + (b3 % 2))
            elif family in (6,):  # research: lattice stamp + inner ring
                steps += self._stamp_steps(tx, ty, base_col, size=6 + (b3 % 5))
                steps += self._ring_steps(tx, ty, 6 + (b4 % 10), base_col, density=10)
            else:
                steps += self._stamp_steps(tx, ty, base_col, size=5 + (b3 % 6))

        # optional writing: short caption, drawn as pixels gradually
        cap = (caption or "").strip()
        if cap:
            cap = cap.replace("\n", " ").strip()
            cap = cap[:18]
            steps += self._text_steps(cap, digest, base_col)

        # clamp to surface bounds and lightly shuffle ordering (deterministic) to feel "alive"
        # We don't fully randomize; we interleave chunks so strokes appear to grow outward.
        steps = [(int(clamp(x, 2, self.w-2-PX)), int(clamp(y, 2, self.h-2-PX)), col) for (x,y,col) in steps]
        return self._interleave(steps, digest)

    def _interleave(self, steps: List[Tuple[int,int,Tuple[int,int,int]]], digest: bytes) -> List[Tuple[int,int,Tuple[int,int,int]]]:
        if len(steps) < 400:
            return steps
        # split into 12 buckets and interleave to simulate multiple "pens" drawing
        buckets = [[] for _ in range(12)]
        for i, item in enumerate(steps):
            buckets[(i + digest[i % len(digest)]) % 12].append(item)
        out: List[Tuple[int,int,Tuple[int,int,int]]] = []
        while True:
            any_added = False
            for b in buckets:
                if b:
                    out.append(b.pop(0))
                    any_added = True
            if not any_added:
                break
        return out

    def _stroke_steps(self, x0: int, y0: int, x1: int, y1: int, col: Tuple[int,int,int], thickness: int = 1):
        pts = _bresenham(x0 // PX, y0 // PX, x1 // PX, y1 // PX)
        out = []
        for (x, y) in pts:
            for ox in range(-thickness, thickness+1):
                for oy in range(-thickness, thickness+1):
                    out.append(((x+ox) * PX, (y+oy) * PX, col))
        return out

    def _ring_steps(self, x: int, y: int, r: int, col: Tuple[int,int,int], density: int = 8):
        if r <= 0:
            return []
        steps = max(18, density * 10)
        out = []
        for i in range(steps):
            a = (2 * math.pi) * (i / steps)
            px = int(x + math.cos(a) * r)
            py = int(y + math.sin(a) * r)
            out.append((px, py, col))
        return out

    def _spike_steps(self, x: int, y: int, ang: float, col: Tuple[int,int,int], count: int = 3):
        out = []
        for i in range(count):
            da = (i - count/2) * 0.25
            ln = 14 + i * 6
            tx = int(x + math.cos(ang + da) * ln)
            ty = int(y + math.sin(ang + da) * ln)
            out += self._stroke_steps(x, y, tx, ty, col, thickness=1)
        return out

    def _blob_steps(self, x: int, y: int, col: Tuple[int,int,int], radius: int = 10):
        out = []
        for dy in range(-radius, radius+1):
            for dx in range(-radius, radius+1):
                if dx*dx + dy*dy <= radius*radius and (dx + dy) % 3 == 0:
                    out.append((x + dx*PX//2, y + dy*PX//2, col))
        return out

    def _spiral_steps(self, x: int, y: int, col: Tuple[int,int,int], turns: int = 2):
        out = []
        tmax = turns * 2 * math.pi
        t = 0.0
        while t < tmax:
            r = 3 + 10 * (t / tmax)
            px = int(x + math.cos(t) * r)
            py = int(y + math.sin(t) * r)
            out.append((px, py, col))
            t += 0.16
        return out

    def _stamp_steps(self, x: int, y: int, col: Tuple[int,int,int], size: int = 8):
        out = []
        for i in range(-size, size+1):
            if i % 2 == 0:
                out.append((x + i, y, col))
                out.append((x, y + i, col))
            if i % 3 == 0:
                out.append((x + i, y + i, col))
        return out

    def _text_steps(self, text: str, digest: bytes, col: Tuple[int,int,int]):
        # Render a small caption and convert its opaque pixels into draw-steps.
        # Avoid numpy/surfarray to keep installs simple.
        surf = self._font.render(text, True, (255, 255, 255)).convert_alpha()
        w, h = surf.get_size()
    
        bias = digest[1] % 3
        if bias == 0:
            ox = int(self.w * 0.12)
        elif bias == 1:
            ox = int((self.w - w) / 2)
        else:
            ox = int(self.w * 0.70) - w
        oy = int(self.h * 0.72) - int((digest[2] % 18))
        ox = int(clamp(ox, 8, self.w - w - 8))
        oy = int(clamp(oy, 28, self.h - h - 8))
    
        stride = 1 if w * h < 2200 else 2
        pts = []
        surf.lock()
        try:
            for yy in range(0, h, stride):
                for xx in range(0, w, stride):
                    if surf.get_at((xx, yy)).a > 0:
                        pts.append((ox + xx, oy + yy))
        finally:
            surf.unlock()
    
        jitter = (digest[3] % 7) - 3
        pts.sort(key=lambda p: (p[1] + ((p[0] + jitter) % 7), p[0]))
    
        out = [(x, y, col) for (x, y) in pts]
        return out
