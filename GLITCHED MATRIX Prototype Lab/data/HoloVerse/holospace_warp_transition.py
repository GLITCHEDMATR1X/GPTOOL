from __future__ import annotations

"""Clean HoloVerse 4D warp transition.

This module is the intended replacement for the old Liquid Orb / 10-second
travel UI. It keeps the transition camera-owned, full-screen, and visual-only:
only a centered countdown is allowed; no help labels, HUD panels, line rings, or visible edge cage.
"""

import math
from direct.gui.DirectGui import DirectLabel
from panda3d.core import CardMaker, Shader, TextNode, TransparencyAttrib

WARP_VERTEX = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 v_uv;
void main() {
    v_uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

WARP_FRAGMENT = """
#version 150
uniform float time_sec;
uniform float progress;
uniform float warp_gain;
uniform vec4 dimension_tint;
in vec2 v_uv;
out vec4 fragColor;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
        mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
        u.y
    );
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= 1.7777778;
    float r = length(uv);
    vec2 dir = r > 0.0001 ? uv / r : vec2(0.0);
    vec2 tangent = vec2(-dir.y, dir.x);
    float open = smoothstep(0.0, 0.18, progress) * (1.0 - smoothstep(0.86, 1.0, progress));
    float pull = warp_gain * open / max(0.12, r + 0.18);
    vec2 warped = uv - dir * pull + tangent * (0.24 + 0.62 * open) * sin(time_sec * 1.7 + r * 7.0);
    float tunnel = exp(-r * (1.15 - open * 0.34));
    float rings = sin((r * 22.0 - time_sec * 7.5) + noise(warped * 3.0 + time_sec * 0.12) * 5.0);
    float fold = sin(atan(warped.y, warped.x) * 4.0 + time_sec * 2.3 + r * 8.0);
    float core = smoothstep(0.62, 0.02, r);
    vec3 cyan = vec3(0.12, 0.95, 1.0);
    vec3 violet = vec3(0.62, 0.18, 1.0);
    vec3 amber = vec3(1.0, 0.45, 0.16);
    vec3 base = mix(cyan, violet, 0.5 + 0.5 * fold);
    base = mix(base, amber, 0.22 * (0.5 + 0.5 * rings));
    base = mix(base, dimension_tint.rgb, clamp(dimension_tint.a, 0.0, 1.0));
    float glow = tunnel * (0.35 + 0.65 * open) + core * 0.55;
    glow += pow(abs(rings) * 0.5 + 0.5, 5.0) * 0.18 * open;
    float vignette = smoothstep(1.38, 0.28, r);
    float alpha = clamp((0.10 + glow) * vignette, 0.0, 1.0);
    alpha *= smoothstep(0.0, 0.08, progress) * (1.0 - smoothstep(0.96, 1.0, progress));
    fragColor = vec4(base * (0.55 + glow * 1.35), alpha);
}
"""


class HoloSpaceWarpTransition:
    """Full-screen, camera-centered 4D warp with no transition UI."""

    DIMENSION_TINTS = {
        0: (0.72, 0.95, 1.00, 0.12),
        1: (0.34, 1.00, 0.62, 0.22),
        2: (0.78, 1.00, 0.35, 0.18),
        3: (0.84, 0.36, 1.00, 0.26),
        4: (1.00, 0.62, 0.22, 0.22),
        5: (0.50, 0.90, 1.00, 0.28),
        6: (1.00, 0.20, 0.92, 0.24),
        7: (0.10, 0.98, 1.00, 0.30),
        8: (0.28, 0.46, 1.00, 0.32),
        9: (1.00, 1.00, 1.00, 0.14),
    }

    def __init__(self, app, duration: float = 2.8) -> None:
        self.app = app
        self.duration = max(0.45, float(duration))
        self.elapsed = 0.0
        self.active = False
        self.root = None
        self.card = None
        self.shader = None
        self.countdown_label = None
        self.dimension_index = 8
        self.source = ""

    def build(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            return
        cm = CardMaker("holoverse-4d-warp-card")
        cm.setFrame(-2.0, 2.0, -1.2, 1.2)
        self.root = self.app.camera.attachNewNode("holoverse-camera-centered-4d-warp")
        self.root.setPos(0, 1.0, 0)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setBin("fixed", 40)
        self.card = self.root.attachNewNode(cm.generate())
        self.card.setTransparency(TransparencyAttrib.MAlpha)
        self.card.setDepthWrite(False)
        self.card.setDepthTest(False)
        self.card.setLightOff(1)
        # Keep the transition presentation deterministic and UI-clean.  The
        # shader source remains for future visual expansion, but the current
        # route uses a dark camera card plus countdown so unsupported GLSL
        # drivers never produce a full-screen white flash.
        self.shader = None
        self.card.setColor(0.0, 0.0, 0.0, 0.88)
        if self.countdown_label is None:
            self.countdown_label = DirectLabel(
                parent=self.app.aspect2d, text="", text_align=TextNode.ACenter,
                text_scale=0.20, text_fg=(0.92, 0.98, 1.0, 0.94),
                frameColor=(0, 0, 0, 0), pos=(0, 0, -0.02), textMayChange=True,
            )
            self.countdown_label.hide()
        self.root.hide()

    def start(self, *, duration: float | None = None, source: str = "") -> None:
        self.build()
        self.duration = max(0.45, float(duration if duration is not None else self.duration))
        self.elapsed = 0.0
        self.active = True
        self.source = str(source or "warp")
        if self.root is not None:
            self.root.show()
        if self.countdown_label is not None:
            self.countdown_label.show()
        self._face_camera_center()
        self.update(0.0)

    def stop(self) -> None:
        self.active = False
        if self.root is not None and not self.root.isEmpty():
            self.root.hide()
        if self.countdown_label is not None:
            try:
                self.countdown_label.hide()
                self.countdown_label["text"] = ""
            except Exception:
                pass

    def set_dimension_preset(self, index: int) -> bool:
        try:
            self.dimension_index = int(index)
        except Exception:
            self.dimension_index = 8
        return True

    def update(self, dt: float) -> bool:
        if not self.active:
            return False
        self.elapsed = min(self.duration, self.elapsed + max(0.0, min(0.08, float(dt))))
        progress = self.elapsed / max(0.001, self.duration)
        self._face_camera_center()
        tint = self.DIMENSION_TINTS.get(self.dimension_index, self.DIMENSION_TINTS[8])
        t = self.elapsed
        if self.countdown_label is not None:
            try:
                remaining = max(0.0, self.duration - self.elapsed)
                self.countdown_label["text"] = str(max(1, int(math.ceil(remaining))))
            except Exception:
                pass
        if self.card is not None and not self.card.isEmpty():
            if self.shader is not None:
                try:
                    self.card.setShaderInput("time_sec", float(t))
                    self.card.setShaderInput("progress", float(progress))
                    self.card.setShaderInput("warp_gain", 0.92 + 0.38 * math.sin(progress * math.pi))
                    self.card.setShaderInput("dimension_tint", *tint)
                except Exception:
                    pass
            else:
                alpha = 0.78 + math.sin(max(0.0, min(1.0, progress)) * math.pi) * 0.16
                self.card.setColor(0.0, 0.0, 0.0, alpha)
        return progress >= 1.0

    def _face_camera_center(self) -> None:
        try:
            if self.root is None or self.root.isEmpty():
                return
            self.root.setPos(0, 1.0, 0)
            self.root.setHpr(0, 0, 0)
        except Exception:
            pass


# Compatibility alias for existing imports/callers.
HoloSpaceTravelSequence = HoloSpaceWarpTransition
