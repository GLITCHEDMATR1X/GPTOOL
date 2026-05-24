from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from direct.gui.DirectGui import DirectFrame, DirectLabel
from direct.task import Task
from panda3d.core import (
    Filename,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    PNMImage,
    SamplerState,
    Shader,
    TextNode,
    Texture,
    TransparencyAttrib,
    Vec2,
    Vec3,
)


SPHERE_VERTEX = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 v_local_pos;
out vec3 v_normal;
void main() {
    v_local_pos = p3d_Vertex.xyz;
    v_normal = p3d_Normal;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

SPHERE_FRAGMENT = """
#version 150
uniform sampler2D media_tex;
uniform vec2 flow_offset;
uniform vec2 warp_velocity;
uniform float media_scale;
uniform float lensing_gain;
uniform float lensing_swirl;
uniform float accretion_threshold;
uniform float accretion_gain;
uniform float brightness;
uniform float bubble_fresnel;
uniform float time_sec;
uniform vec4 dimension_tint;

in vec3 v_local_pos;
in vec3 v_normal;
out vec4 fragColor;

float saturate(float x) { return clamp(x, 0.0, 1.0); }
mat2 rot(float a) {
    float s = sin(a);
    float c = cos(a);
    return mat2(c, -s, s, c);
}
vec3 sample_triplanar(vec3 p, vec3 n) {
    vec3 an = pow(abs(n), vec3(3.0));
    an /= max(an.x + an.y + an.z, 1e-5);
    vec3 sx = texture(media_tex, p.yz).rgb;
    vec3 sy = texture(media_tex, p.xz).rgb;
    vec3 sz = texture(media_tex, p.xy).rgb;
    return sx * an.x + sy * an.y + sz * an.z;
}
void main() {
    vec3 dir = normalize(v_local_pos);
    vec2 screenish = dir.xz / max(0.22, dir.y + 1.08);
    vec2 velocity = warp_velocity;
    float speed = length(velocity);
    float lens = lensing_gain * (speed / (1.0 + speed * 0.35));
    float r = length(screenish);
    vec2 radial = (r > 1e-5) ? screenish / r : vec2(0.0, 0.0);
    vec2 tangential = vec2(-radial.y, radial.x);
    vec2 warped = screenish - radial * (lens / (1.0 + r * 8.0));
    warped += tangential * (lensing_swirl * speed * exp(-r * 4.0));
    warped += velocity * 0.11;
    float w_phase = time_sec * (0.12 + speed * 0.06);
    vec3 sample_pos = vec3(
        warped.x,
        dir.y * media_scale + sin(w_phase + dir.z * 3.2) * 0.08,
        warped.y
    ) * media_scale;
    sample_pos.xy *= rot(w_phase * 0.6 + speed * 0.22);
    sample_pos += vec3(flow_offset.x, time_sec * 0.01 + sin(w_phase) * 0.03, flow_offset.y);
    vec3 color = sample_triplanar(sample_pos, dir);
    float disk_mask = smoothstep(accretion_threshold, accretion_threshold + 0.16, speed);
    float ring = exp(-pow((r - 0.28 - speed * 0.10) / max(0.05, 0.12 - speed * 0.01), 2.0));
    vec2 streak_uv = vec2(
        atan(warped.y, warped.x) / 6.28318530718 + 0.5 + speed * 0.03,
        r * (2.8 + speed * 0.35) + time_sec * (0.05 + speed * 0.03)
    );
    vec3 streak = texture(media_tex, streak_uv).rgb;
    color = mix(color, streak * (1.08 + speed * 0.6), ring * disk_mask * accretion_gain * 0.26);
    float fresnel = pow(1.0 - saturate(abs(dot(dir, vec3(0.0, 1.0, 0.0)))), 2.0);
    color += vec3(0.05, 0.08, 0.12) * fresnel * bubble_fresnel;
    color = mix(color, dimension_tint.rgb * max(0.55, dot(color, vec3(0.30, 0.59, 0.11)) + 0.35), dimension_tint.a);
    color *= brightness;
    fragColor = vec4(color, 1.0);
}
"""


@dataclass
class _VideoState:
    path: Path
    cap: object
    texture: Optional[Texture]
    fps: float
    frame_interval: float
    accum: float = 0.0

    def close(self) -> None:
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass


class HoloSpaceTravelSequence:
    """Camera-owned Liquid Orb travel bubble for HoloSpace entry.

    The player can still look around inside the transition, but the presentation
    is intentionally HUD-clean: only a simple countdown is visible.
    """

    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".ogv")
    DIMENSION_PRESETS = {
        0: ("HUB", (0.72, 0.95, 1.00, 0.10), 0.92, 1.00, 1.00),
        1: ("FOREST", (0.34, 1.00, 0.62, 0.24), 0.86, 1.05, 0.92),
        2: ("HILLS", (0.78, 1.00, 0.35, 0.20), 0.96, 0.96, 0.88),
        3: ("MUSHROOM", (0.84, 0.36, 1.00, 0.28), 1.16, 1.18, 1.18),
        4: ("DESERT", (1.00, 0.62, 0.22, 0.22), 1.04, 0.88, 0.82),
        5: ("ICE", (0.50, 0.90, 1.00, 0.30), 0.74, 1.32, 0.74),
        6: ("URBAN", (1.00, 0.20, 0.92, 0.24), 1.32, 1.22, 1.24),
        7: ("METROPOLIS", (0.10, 0.98, 1.00, 0.30), 1.42, 1.36, 1.30),
        8: ("HOLOSPACE", (0.28, 0.46, 1.00, 0.32), 1.72, 1.52, 1.55),
        9: ("SPAWN", (1.00, 1.00, 1.00, 0.16), 1.00, 0.92, 0.92),
    }

    def __init__(self, app, duration: float = 10.0) -> None:
        self.app = app
        self.duration = max(0.5, float(duration))
        self.active = False
        self.elapsed = 0.0
        self.source = ""
        self.root = None
        self.sphere = None
        self.rings = []
        self.label_root = None
        self.countdown_label = None
        self.help_label = None
        self.media_path = ""
        self.media_kind = "image"
        self.texture = None
        self.shader = None
        self.shader_enabled = False
        self.video_state: Optional[_VideoState] = None
        self.flow_seed = random.Random(84624)
        self.flow_offset = Vec2(0.0, 0.0)
        self.warp_velocity = Vec2(0.0, 0.0)
        self.dimension_index = 8
        self.dimension_name = "HOLOSPACE"
        self.dimension_speed = 1.72
        self.dimension_depth = 0.0
        self.swirl_bias = 0.0
        self.look_yaw = 0.0
        self.look_pitch = 0.0
        self.controls_bound = False
        self.last_control_signal = "IDLE"
        self.input_energy = 0.0
        self.reload_count = 0

    def build(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            return
        app = self.app
        self.root = app.camera.attachNewNode("holospace-liquid-orb-transition")
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)
        self.root.setBin("fixed", 18)
        self.root.hide()

        self.sphere = self._create_inside_sphere("holospace-transition-orb", 18.0, 128, 64)
        self.sphere.reparentTo(self.root)
        self.sphere.setTwoSided(True)
        self.sphere.setLightOff(1)
        self.sphere.setTransparency(TransparencyAttrib.MAlpha)
        self.sphere.setDepthWrite(False)
        self.sphere.setDepthTest(False)
        self.sphere.setBin("fixed", 17)
        self.sphere.setColorScale(1.0, 1.0, 1.0, 0.96)
        self._install_shader()
        self.reload_media(initial=True)
        self._apply_dimension_preset_to_shader()

        self.rings = []
        for axis, color, scale in (
            ("xy", (0.20, 0.95, 1.0, 0.38), 1.00),
            ("xz", (0.95, 0.28, 1.0, 0.28), 0.92),
            ("yz", (1.0, 0.82, 0.28, 0.22), 0.84),
        ):
            ring = self._create_ring(f"holospace-transition-ring-{axis}", 16.4 * scale, axis, color)
            ring.reparentTo(self.root)
            ring.setDepthWrite(False)
            ring.setDepthTest(False)
            ring.setBin("fixed", 19)
            self.rings.append((ring, axis))

        self.label_root = DirectFrame(parent=app.aspect2d, frameColor=(0, 0, 0, 0))
        self.countdown_label = DirectLabel(
            parent=self.label_root,
            text="",
            text_align=TextNode.ACenter,
            text_scale=0.072,
            text_fg=(0.90, 1.0, 1.0, 0.96),
            frameColor=(0, 0, 0, 0),
            pos=(0.0, 0.0, -0.82),
            textMayChange=True,
        )
        # No help label, control hint, speed label, dimension label, or panel is
        # allowed during this transition.  The countdown text is the only UI.
        self.help_label = None
        self.label_root.hide()

    def start(self, *, duration: float | None = None, source: str = "") -> None:
        self.build()
        self.duration = max(0.5, float(duration if duration is not None else self.duration))
        self.elapsed = 0.0
        self.source = str(source or "space")
        self.active = True
        self.flow_offset = Vec2(0.0, 0.0)
        self.warp_velocity = Vec2(0.0, 0.0)
        self.dimension_depth = 0.0
        self.swirl_bias = 0.0
        self.input_energy = 0.0
        self.set_dimension_preset(8 if "space" in self.source.lower() else self.dimension_index)
        self._bind_controls()
        if self.root is not None:
            self.root.show()
        if self.label_root is not None:
            self.label_root.show()
        self.update(0.0)

    def stop(self) -> None:
        self.active = False
        if self.root is not None and not self.root.isEmpty():
            self.root.hide()
        if self.label_root is not None:
            self.label_root.hide()
        if self.video_state is not None:
            try:
                self.video_state.close()
            except Exception:
                pass
            self.video_state = None

    def _bind_controls(self) -> None:
        if self.controls_bound:
            return
        app = self.app
        try:
            app.accept("r", self.reload_media)
            app.accept("wheel_up", self.adjust_speed_bias, [0.18])
            app.accept("wheel_down", self.adjust_speed_bias, [-0.18])
            self.controls_bound = True
        except Exception:
            self.controls_bound = False

    def adjust_speed_bias(self, delta: float) -> None:
        self.dimension_speed = max(0.35, min(3.25, float(self.dimension_speed) + float(delta)))
        self.last_control_signal = "WHEEL SPEED"

    def set_dimension_preset(self, index: int) -> bool:
        try:
            index = int(index)
        except Exception:
            index = 8
        if index not in self.DIMENSION_PRESETS:
            index = 8
        self.dimension_index = index
        name, tint, speed, lens, swirl = self.DIMENSION_PRESETS[index]
        self.dimension_name = str(name)
        self.dimension_speed = float(speed)
        self._preset_tint = tint
        self._preset_lens = float(lens)
        self._preset_swirl = float(swirl)
        self._apply_dimension_preset_to_shader()
        self.last_control_signal = f"PRESET {index}:{self.dimension_name}"
        return True

    def update(self, dt: float) -> bool:
        if not self.active:
            return False
        dt = max(0.0, min(0.08, float(dt)))
        self.elapsed = min(self.duration, self.elapsed + dt)
        remaining = max(0.0, self.duration - self.elapsed)
        t = self.elapsed
        progress = self.elapsed / max(0.001, self.duration)
        self._update_mouse_look()
        self._update_control_effects(dt)
        self._update_video(dt)
        self._apply_shader_inputs(t)
        speed = self.warp_velocity.length()
        if self.sphere is not None and not self.sphere.isEmpty():
            sx = 1.00 + math.sin(t * (1.45 + speed)) * 0.055 + progress * 0.10 + self.dimension_depth * 0.12
            sy = 0.98 + math.sin(t * 1.07 + 1.4 + self.swirl_bias) * 0.070 + speed * 0.06
            sz = 1.02 + math.sin(t * 1.92 + 0.6) * 0.045 - self.dimension_depth * 0.055
            self.sphere.setScale(sx, sy, sz)
            self.sphere.setHpr(t * (8.5 + speed * 6.5), math.sin(t * 0.7) * 7.5, math.cos(t * 0.9) * 5.5)
            pulse = 0.82 + 0.16 * math.sin(t * 2.5 + speed)
            if not self.shader_enabled:
                self.sphere.setColorScale(0.82 + progress * 0.22, 0.92 + pulse * 0.08, 1.0, 0.94)
        for idx, (ring, axis) in enumerate(self.rings):
            if ring is not None and not ring.isEmpty():
                ring.setHpr(t * (10 + idx * 7 + speed * 18), t * (4 + idx * 2), t * (6 + idx * 3 + self.swirl_bias * 12))
                s = 1.0 + math.sin(t * (1.3 + idx * 0.3)) * 0.035 + speed * 0.018
                ring.setScale(s)
        if self.countdown_label is not None:
            self.countdown_label["text"] = str(max(1, int(math.ceil(remaining))))
        if self.help_label is not None:
            self.help_label["text"] = ""
        return remaining <= 0.0

    def _install_shader(self) -> None:
        raw = str(os.environ.get("HOLOSPACE_TRANSITION_SHADER", "off")).strip().lower()
        if raw in {"0", "false", "off", "no", ""}:
            self.shader = None
            self.shader_enabled = False
            return
        try:
            self.shader = Shader.make(Shader.SL_GLSL, SPHERE_VERTEX, SPHERE_FRAGMENT)
            if self.sphere is not None:
                self.sphere.setShader(self.shader)
            self.shader_enabled = True
        except Exception:
            self.shader = None
            self.shader_enabled = False

    def _apply_dimension_preset_to_shader(self) -> None:
        if self.sphere is None or self.sphere.isEmpty():
            return
        tint = getattr(self, "_preset_tint", self.DIMENSION_PRESETS.get(self.dimension_index, self.DIMENSION_PRESETS[8])[1])
        try:
            self.sphere.setShaderInput("dimension_tint", *tint)
        except Exception:
            pass

    def _apply_shader_inputs(self, t: float) -> None:
        if self.sphere is None or self.sphere.isEmpty():
            return
        if self.shader_enabled:
            try:
                self.sphere.setShaderInput("flow_offset", self.flow_offset)
                self.sphere.setShaderInput("warp_velocity", self.warp_velocity)
                self.sphere.setShaderInput("time_sec", float(t))
                self.sphere.setShaderInput("media_scale", 1.45 + self.dimension_depth * 0.45)
                self.sphere.setShaderInput("lensing_gain", 2.1 * float(getattr(self, "_preset_lens", 1.0)))
                self.sphere.setShaderInput("lensing_swirl", 1.35 * float(getattr(self, "_preset_swirl", 1.0)) + self.swirl_bias)
                self.sphere.setShaderInput("accretion_threshold", max(0.05, 0.10 - abs(self.dimension_depth) * 0.025))
                self.sphere.setShaderInput("accretion_gain", 2.5 + self.input_energy * 0.6)
                self.sphere.setShaderInput("brightness", 1.08 + self.input_energy * 0.08)
                self.sphere.setShaderInput("bubble_fresnel", 0.16 + abs(self.dimension_depth) * 0.10)
            except Exception:
                self.shader_enabled = False
                try:
                    self.sphere.clearShader()
                except Exception:
                    pass

    def _update_control_effects(self, dt: float) -> None:
        keys = getattr(self.app, "keys", {}) or {}
        accel = 0.010 * max(0.35, float(self.dimension_speed))
        if keys.get("shift"):
            accel *= 2.85
        signal = []
        if keys.get("w"):
            self.warp_velocity.y += accel
            signal.append("W")
        if keys.get("s"):
            self.warp_velocity.y -= accel
            signal.append("S")
        if keys.get("a"):
            self.warp_velocity.x -= accel
            signal.append("A")
        if keys.get("d"):
            self.warp_velocity.x += accel
            signal.append("D")
        if keys.get("q"):
            self.swirl_bias -= dt * 1.25
            signal.append("Q")
        if keys.get("e"):
            self.swirl_bias += dt * 1.25
            signal.append("E")
        if keys.get("space"):
            self.dimension_depth = min(1.0, self.dimension_depth + dt * 0.95)
            signal.append("SPACE")
        elif keys.get("control"):
            self.dimension_depth = max(-0.65, self.dimension_depth - dt * 0.95)
            signal.append("CTRL")
        else:
            self.dimension_depth *= max(0.0, 1.0 - dt * 1.35)
        self.warp_velocity *= 0.985
        max_len = 1.85
        if self.warp_velocity.lengthSquared() > max_len * max_len:
            self.warp_velocity.normalize()
            self.warp_velocity *= max_len
        self.flow_offset += self.warp_velocity * dt * 60.0
        self.input_energy = max(0.0, min(1.0, self.warp_velocity.length() / 1.85 + abs(self.dimension_depth) * 0.18))
        if signal:
            self.last_control_signal = "+".join(signal)
        else:
            self.last_control_signal = "IDLE"

    def _update_mouse_look(self) -> None:
        # Imported from the original Liquid Orb scenario but safe for the game:
        # it changes the camera view inside the bubble only. The player position is
        # still frozen and HoloSpace spawn is applied after the timer finishes.
        app = self.app
        try:
            if getattr(app, "win", None) is None:
                return
            if not bool(getattr(app, "mouse_captured", True)):
                return
            md = app.win.getPointer(0)
            cx = app.win.getXSize() // 2
            cy = app.win.getYSize() // 2
            dx = md.getX() - cx
            dy = md.getY() - cy
            if abs(dx) < 1 and abs(dy) < 1:
                return
            sens = 0.070
            self.look_yaw -= dx * sens
            self.look_pitch -= dy * sens
            self.look_pitch = max(-82.0, min(82.0, self.look_pitch))
            app.camera.setHpr(float(getattr(app, "player_yaw", 0.0)) + self.look_yaw, self.look_pitch, 0)
            try:
                app.win.movePointer(0, cx, cy)
            except Exception:
                pass
        except Exception:
            return

    def _resolve_media_path(self) -> Path:
        root = Path(getattr(self.app, "ASSETS", Path(__file__).resolve().parent / "assets"))
        orb_dir = root / "orb"
        candidates = []
        for stem in ("orb_override", "orb_media"):
            for ext in self.VIDEO_EXTS + self.IMAGE_EXTS:
                candidates.append(orb_dir / f"{stem}{ext}")
        try:
            candidates.extend(sorted(p for p in orb_dir.iterdir() if p.suffix.lower() in set(self.VIDEO_EXTS + self.IMAGE_EXTS) and not p.name.startswith("orb_side_")))
        except Exception:
            pass
        for item in candidates:
            if item.exists() and item.is_file():
                return item
        fallback = orb_dir / "orb_media.png"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        if not fallback.exists():
            self._write_fallback_media(fallback)
        return fallback

    def reload_media(self, initial: bool = False) -> None:
        path = self._resolve_media_path()
        self.media_path = str(path)
        self.reload_count += 0 if initial else 1
        if self.video_state is not None:
            try:
                self.video_state.close()
            except Exception:
                pass
            self.video_state = None
        tex = None
        kind = "image"
        if path.suffix.lower() in self.VIDEO_EXTS:
            tex = self._load_video_texture(path)
            kind = "video" if tex is not None else "image-fallback"
        if tex is None:
            tex = self._load_image_texture(path)
        self.media_kind = kind
        self.texture = tex
        if self.sphere is not None and tex is not None:
            if self.shader_enabled:
                try:
                    self.sphere.setShaderInput("media_tex", tex)
                except Exception:
                    self.sphere.setTexture(tex, 1)
            else:
                self.sphere.setTexture(tex, 1)
        self.last_control_signal = "RELOAD MEDIA" if not initial else self.last_control_signal

    def _load_video_texture(self, path: Path):
        try:
            import cv2
            import numpy as np
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                return None
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = float(fps if fps and fps > 1.0 else 30.0)
            ok, frame = cap.read()
            if not ok:
                cap.release()
                return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            max_width = 1024
            h, w = frame.shape[:2]
            if w > max_width:
                scale = max_width / float(w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            frame = self._make_tileable_array(frame, 0.16, np)
            h, w = frame.shape[:2]
            tex = Texture(path.stem or "orb_video")
            tex.setup2dTexture(w, h, Texture.T_unsigned_byte, Texture.F_rgba8)
            tex.setRamImage(frame.tobytes())
            self._configure_texture(tex)
            self.video_state = _VideoState(path=path, cap=cap, texture=tex, fps=fps, frame_interval=1.0 / fps)
            return tex
        except Exception:
            return None

    def _update_video(self, dt: float) -> None:
        if self.video_state is None:
            return
        try:
            import cv2
            import numpy as np
            st = self.video_state
            st.accum += dt
            if st.accum < st.frame_interval:
                return
            st.accum = 0.0
            ok, frame = st.cap.read()
            if not ok:
                st.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = st.cap.read()
            if not ok:
                return
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            h, w = frame.shape[:2]
            if w > 1024:
                scale = 1024 / float(w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            frame = self._make_tileable_array(frame, 0.16, np)
            st.texture.setRamImage(frame.tobytes())
            if self.sphere is not None and self.shader_enabled:
                self.sphere.setShaderInput("media_tex", st.texture)
        except Exception:
            return

    def _make_tileable_array(self, arr, blend_fraction: float, np):
        arr = arr.astype(np.float32)
        h, w = arr.shape[:2]
        out = arr.copy()
        edge_x = max(1, int(w * blend_fraction))
        edge_y = max(1, int(h * blend_fraction))
        if edge_x > 1:
            t = np.linspace(0.0, 1.0, edge_x, dtype=np.float32)[None, :, None]
            mix = (1.0 - t) * 0.5
            left = arr[:, :edge_x, :]
            right = arr[:, -edge_x:, :]
            out[:, :edge_x, :] = left * (1.0 - mix) + right * mix
            out[:, -edge_x:, :] = right * (1.0 - mix[:, ::-1, :]) + left * mix[:, ::-1, :]
        if edge_y > 1:
            t = np.linspace(0.0, 1.0, edge_y, dtype=np.float32)[:, None, None]
            mix = (1.0 - t) * 0.5
            top = out[:edge_y, :, :]
            bottom = out[-edge_y:, :, :]
            out[:edge_y, :, :] = top * (1.0 - mix) + bottom * mix
            out[-edge_y:, :, :] = bottom * (1.0 - mix[::-1, :, :]) + top * mix[::-1, :, :]
        return np.clip(out, 0.0, 255.0).astype(np.uint8)

    def _load_image_texture(self, path: Path):
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(path).convert("RGBA")
            if img.width > 1024:
                scale = 1024 / float(img.width)
                img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
            arr = np.array(img, dtype=np.uint8)
            arr = self._make_tileable_array(arr, 0.16, np)
            tex = Texture(path.stem or "orb_media")
            tex.setup2dTexture(arr.shape[1], arr.shape[0], Texture.T_unsigned_byte, Texture.F_rgba8)
            tex.setRamImage(arr.tobytes())
            self._configure_texture(tex)
            return tex
        except Exception:
            pass
        source_path = self._power2_media_copy(path)
        try:
            tex = self.app.loader.loadTexture(Filename.fromOsSpecific(str(source_path)))
            if tex is not None:
                self._configure_texture(tex)
                return tex
        except Exception:
            pass
        return None

    def _configure_texture(self, tex: Texture) -> None:
        tex.setWrapU(SamplerState.WMRepeat)
        tex.setWrapV(SamplerState.WMRepeat)
        tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
        tex.setMagfilter(SamplerState.FTLinear)
        tex.setAnisotropicDegree(8)

    def _power2_media_copy(self, path: Path) -> Path:
        cache = path.with_name(f"{path.stem}_holospace_p2.png")
        try:
            if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
                return cache
        except Exception:
            pass
        try:
            from PIL import Image
            img = Image.open(path).convert("RGBA")
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
            img.save(cache)
            return cache
        except Exception:
            try:
                src = PNMImage()
                if src.read(Filename.fromOsSpecific(str(path))):
                    dst = PNMImage(1024, 1024)
                    dst.quickFilterFrom(src)
                    dst.write(Filename.fromOsSpecific(str(cache)))
                    return cache
            except Exception:
                pass
        return path

    def _write_fallback_media(self, path: Path) -> None:
        size = 512
        img = PNMImage(size, size)
        for y in range(size):
            for x in range(size):
                dx = (x / max(1, size - 1)) * 2.0 - 1.0
                dy = (y / max(1, size - 1)) * 2.0 - 1.0
                r = min(1.0, math.sqrt(dx * dx + dy * dy))
                a = math.atan2(dy, dx)
                img.setXel(
                    x,
                    y,
                    0.18 + 0.35 * (0.5 + 0.5 * math.sin(a * 3.0 + r * 12.0)),
                    0.24 + 0.45 * (0.5 + 0.5 * math.cos(a * 2.0 - r * 9.0)),
                    0.42 + 0.50 * (1.0 - r),
                )
        img.write(Filename.fromOsSpecific(str(path)))

    def _create_inside_sphere(self, name: str, radius: float, segments_u: int, segments_v: int):
        fmt = GeomVertexFormat.getV3n3t2()
        vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        texcoord = GeomVertexWriter(vdata, "texcoord")
        prim = GeomTriangles(Geom.UHStatic)
        for y in range(segments_v + 1):
            v = y / float(segments_v)
            phi = v * math.pi
            for x in range(segments_u + 1):
                u = x / float(segments_u)
                theta = u * math.pi * 2.0
                sx = math.sin(phi) * math.cos(theta)
                sy = math.sin(phi) * math.sin(theta)
                sz = math.cos(phi)
                vertex.addData3f(sx * radius, sy * radius, sz * radius)
                normal.addData3f(-sx, -sy, -sz)
                texcoord.addData2f(u, 1.0 - v)
        stride = segments_u + 1
        for y in range(segments_v):
            for x in range(segments_u):
                i0 = y * stride + x
                i1 = i0 + 1
                i2 = i0 + stride
                i3 = i2 + 1
                prim.addVertices(i0, i2, i1)
                prim.addVertices(i1, i2, i3)
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode(name)
        node.addGeom(geom)
        return self.app.render.attachNewNode(node)

    def _create_ring(self, name: str, radius: float, axis: str, color):
        segs = LineSegs(name)
        segs.setThickness(2.4)
        segs.setColor(*color)
        steps = 144
        for i in range(steps + 1):
            a = (i / float(steps)) * math.tau
            x = math.cos(a) * radius
            y = math.sin(a) * radius
            if axis == "xy":
                p = Vec3(x, y, 0)
            elif axis == "xz":
                p = Vec3(x, 0, y)
            else:
                p = Vec3(0, x, y)
            if i == 0:
                segs.moveTo(p)
            else:
                segs.drawTo(p)
        return self.app.render.attachNewNode(segs.create())
