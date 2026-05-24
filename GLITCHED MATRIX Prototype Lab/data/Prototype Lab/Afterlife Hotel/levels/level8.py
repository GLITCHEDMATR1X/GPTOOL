import math
import os
import random
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

from panda3d.core import (
    AmbientLight,
    BitMask32,
    CardMaker,
    CollisionBox,
    CollisionHandlerPusher,
    CollisionNode,
    CollisionRay,
    CollisionSegment,
    CollisionTraverser,
    DirectionalLight,
    Filename,
    Fog,
    KeyboardButton,
    LQuaternionf,
    LVector3,
    NodePath,
    PandaNode,
    Point3,
    Spotlight,
    TextNode,
    TransparencyAttrib,
    Vec3,
    WindowProperties,
    loadPrcFileData,
)

# -----------------------------
# Config
# -----------------------------
SCREENSHOT_MODE = "--screenshot" in sys.argv
SCREENSHOT_PATH = None
if SCREENSHOT_MODE:
    try:
        idx = sys.argv.index("--screenshot")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
            SCREENSHOT_PATH = sys.argv[idx + 1]
    except ValueError:
        pass
    if not SCREENSHOT_PATH:
        SCREENSHOT_PATH = "level8_screenshot.png"

loadPrcFileData("", "sync-video false")
loadPrcFileData("", "show-frame-rate-meter false")
loadPrcFileData("", "textures-power-2 none")
loadPrcFileData("", "window-title Liminal Offices - Level 8")
loadPrcFileData("", "cursor-hidden true")
loadPrcFileData("", "audio-library-name null")
if SCREENSHOT_MODE:
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "win-size 1280 720")
    loadPrcFileData("", "aux-display pandatiny")
    loadPrcFileData("", "framebuffer-software true")
else:
    loadPrcFileData("", "win-size 1600 900")

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task


# -----------------------------
# Crash logging
# -----------------------------
def write_crash_log(exc: BaseException) -> str:
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(logs_dir, f"crash_{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Level 8 crash log\n")
        f.write(f"UTC: {datetime.now(timezone.utc).isoformat()}Z\n\n")
        traceback.print_exc(file=f)
    return path


@dataclass
class AABB:
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    def expanded(self, r: float) -> "AABB":
        return AABB(self.min_x - r, self.max_x + r, self.min_y - r, self.max_y + r)

    def contains(self, x: float, y: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y


class Level8LiminalOffices(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.96, 0.97, 0.98, 1.0)

        self.accept("escape", sys.exit)
        self.accept("mouse1", self.fire_weapon)
        self.accept("h", self.toggle_hud)

        self.speed = 20.0
        self.mouse_sensitivity = 0.16
        self.player_height = 1.75
        self.player_radius = 0.38
        self.gravity = 0.0
        self.hud_visible = not SCREENSHOT_MODE
        self.yaw = 0.0
        self.pitch = -5.0
        self.velocity = Vec3(0, 0, 0)
        self.world_seed = 80421
        self.rng = random.Random(self.world_seed)
        self.chunk_size = 42.0
        self.active_radius = 2
        self.loaded_chunks = {}
        self.world_colliders: list[AABB] = []
        self.wall_nodes = []
        self.weapon_flash_timer = 0.0
        self.last_shot_t = -99.0

        if not SCREENSHOT_MODE:
            self.render.setShaderAuto()

        self.setup_lighting()
        self.setup_fog()
        self.setup_camera()
        self.setup_ui()
        self.setup_weapon()
        self.setup_shadow_creature()

        self.taskMgr.add(self.update, "update")
        self.taskMgr.add(self.stream_world_task, "stream_world")
        if SCREENSHOT_MODE:
            self.taskMgr.add(self.auto_capture_task, "auto_capture")

        self.stream_world(force=True)
        self.spawn_player()

    # ---------- setup ----------
    def setup_lighting(self):
        ambient = AmbientLight("ambient")
        ambient.setColor((0.45, 0.47, 0.47, 1.0))
        self.render.setLight(self.render.attachNewNode(ambient))

        ceiling_light = DirectionalLight("ceiling_dir")
        ceiling_light.setColor((0.82, 0.83, 0.84, 1.0))
        ceiling_np = self.render.attachNewNode(ceiling_light)
        ceiling_np.setHpr(35, -88, 0)
        self.render.setLight(ceiling_np)

        creature_light = Spotlight("creature_glow")
        creature_light.setColor((0.18, 0.2, 0.22, 1.0))
        creature_light.setExponent(18)
        creature_light.setShadowCaster(False)
        self.creature_light_np = self.render.attachNewNode(creature_light)
        self.render.setLight(self.creature_light_np)

    def setup_fog(self):
        self.fog = Fog("office_fog")
        self.fog.setColor(0.93, 0.95, 0.96)
        self.fog.setExpDensity(0.011)
        self.render.setFog(self.fog)

    def setup_camera(self):
        self.camera.reparentTo(self.render)
        self.camera.setPos(0, 0, self.player_height)
        self.camera.setHpr(self.yaw, self.pitch, 0)
        if not SCREENSHOT_MODE and self.win:
            props = WindowProperties()
            allow_mouse_capture = not (
                os.environ.get('GX_DISABLE_MOUSE_CAPTURE') == '1'
                or os.environ.get('GLITCHED_MATRIX_DISABLE_MOUSE_CAPTURE') == '1'
            )
            props.setCursorHidden(bool(allow_mouse_capture))
            if allow_mouse_capture:
                props.setMouseMode(WindowProperties.M_relative)
            else:
                props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)

    def setup_ui(self):
        self.hud = []
        self.crosshair = OnscreenText(
            text="+",
            pos=(0, -0.02),
            fg=(0.05, 0.05, 0.05, 0.8),
            scale=0.06,
            mayChange=False,
        )
        self.hud.append(self.crosshair)

        self.hud_text = OnscreenText(
            text="Level 8 - Endless Liminal Offices\nWASD Move  Mouse Look  LMB Fire  H Toggle HUD",
            pos=(-1.29, 0.92),
            align=TextNode.ALeft,
            fg=(0.06, 0.06, 0.06, 0.78),
            scale=0.045,
            mayChange=False,
        )
        self.hud.append(self.hud_text)

        self.status_text = OnscreenText(
            text="Shadow creature present",
            pos=(-1.29, -0.92),
            align=TextNode.ALeft,
            fg=(0.08, 0.08, 0.08, 0.7),
            scale=0.04,
            mayChange=True,
        )
        self.hud.append(self.status_text)

        if SCREENSHOT_MODE:
            self.toggle_hud(force=False)

    def toggle_hud(self, force=None):
        self.hud_visible = (not self.hud_visible) if force is None else force
        for item in self.hud:
            if self.hud_visible:
                item.show()
            else:
                item.hide()

    def setup_weapon(self):
        self.weapon_root = self.camera.attachNewNode("weapon_root")
        self.weapon_root.setPos(0.55, 0.92, -0.55)
        self.weapon_root.setHpr(-3, -3, 0)

        box = self.loader.loadModel("models/box")
        body = box.copyTo(self.weapon_root)
        body.setScale(0.08, 0.48, 0.07)
        body.setPos(0, 0.05, 0)
        body.setColor(0.1, 0.1, 0.1, 1)

        barrel = box.copyTo(self.weapon_root)
        barrel.setScale(0.03, 0.4, 0.03)
        barrel.setPos(0, 0.46, 0.02)
        barrel.setColor(0.16, 0.16, 0.16, 1)

        grip = box.copyTo(self.weapon_root)
        grip.setScale(0.03, 0.06, 0.11)
        grip.setPos(0, -0.03, -0.09)
        grip.setHpr(0, 28, 0)
        grip.setColor(0.07, 0.07, 0.07, 1)

        sight = box.copyTo(self.weapon_root)
        sight.setScale(0.014, 0.05, 0.017)
        sight.setPos(0, 0.17, 0.065)
        sight.setColor(0.02, 0.38, 0.2, 1)

        muzzle = box.copyTo(self.weapon_root)
        muzzle.setScale(0.015, 0.04, 0.015)
        muzzle.setPos(0, 0.68, 0.02)
        muzzle.setColor(0.65, 0.72, 0.75, 1)
        self.weapon_muzzle = muzzle

    def setup_shadow_creature(self):
        self.creature_root = self.render.attachNewNode("shadow_creature")
        self.creature_root.setTransparency(TransparencyAttrib.MAlpha)
        self.creature_root.setColor(0.02, 0.025, 0.03, 0.78)

        box = self.loader.loadModel("models/box")
        torso = box.copyTo(self.creature_root)
        torso.setScale(0.36, 0.16, 0.86)
        torso.setPos(0, 0, 1.1)

        head = box.copyTo(self.creature_root)
        head.setScale(0.2, 0.13, 0.22)
        head.setPos(0, 0, 2.05)

        arm_l = box.copyTo(self.creature_root)
        arm_l.setScale(0.1, 0.1, 0.72)
        arm_l.setPos(-0.37, 0, 1.12)
        arm_l.setR(8)

        arm_r = box.copyTo(self.creature_root)
        arm_r.setScale(0.1, 0.1, 0.72)
        arm_r.setPos(0.37, 0, 1.12)
        arm_r.setR(-8)

        leg_l = box.copyTo(self.creature_root)
        leg_l.setScale(0.11, 0.1, 0.9)
        leg_l.setPos(-0.14, 0, 0.25)

        leg_r = box.copyTo(self.creature_root)
        leg_r.setScale(0.11, 0.1, 0.9)
        leg_r.setPos(0.14, 0, 0.25)

        aura = CardMaker("aura")
        aura.setFrame(-1.2, 1.2, -1.2, 1.2)
        aura_np = self.creature_root.attachNewNode(aura.generate())
        aura_np.setP(90)
        aura_np.setPos(0, 0.02, 1.35)
        aura_np.setColor(0.03, 0.04, 0.05, 0.14)
        aura_np.setTransparency(TransparencyAttrib.MAlpha)
        aura_np.setTwoSided(True)

        self.creature_alive = True
        self.place_creature(initial=True)

    # ---------- world ----------
    def spawn_player(self):
        self.camera.setPos(0, 0, self.player_height)
        self.yaw = -20
        self.pitch = -4
        self.camera.setHpr(self.yaw, self.pitch, 0)

    def stream_world_task(self, task):
        self.stream_world()
        return Task.cont

    def stream_world(self, force=False):
        px, py, _ = self.camera.getPos()
        cx = int(math.floor(px / self.chunk_size))
        cy = int(math.floor(py / self.chunk_size))
        needed = set()
        for dx in range(-self.active_radius, self.active_radius + 1):
            for dy in range(-self.active_radius, self.active_radius + 1):
                needed.add((cx + dx, cy + dy))

        if not force and needed == set(self.loaded_chunks.keys()):
            return

        for key in list(self.loaded_chunks.keys()):
            if key not in needed:
                node, colliders = self.loaded_chunks.pop(key)
                node.removeNode()
                for c in colliders:
                    if c in self.world_colliders:
                        self.world_colliders.remove(c)

        for key in needed:
            if key not in self.loaded_chunks:
                node, colliders = self.build_chunk(*key)
                self.loaded_chunks[key] = (node, colliders)
                self.world_colliders.extend(colliders)

    def build_chunk(self, cx, cy):
        chunk = self.render.attachNewNode(f"chunk_{cx}_{cy}")
        colliders = []
        rng = random.Random((cx * 92837111) ^ (cy * 689287499) ^ self.world_seed)
        base_x = cx * self.chunk_size
        base_y = cy * self.chunk_size

        box = self.loader.loadModel("models/box")

        floor = box.copyTo(chunk)
        floor.setPos(base_x + self.chunk_size / 2, base_y + self.chunk_size / 2, -0.08)
        floor.setScale(self.chunk_size / 2, self.chunk_size / 2, 0.08)
        floor.setColor(0.55, 0.67, 0.54, 1)

        ceiling = box.copyTo(chunk)
        ceiling.setPos(base_x + self.chunk_size / 2, base_y + self.chunk_size / 2, 3.25)
        ceiling.setScale(self.chunk_size / 2, self.chunk_size / 2, 0.07)
        ceiling.setColor(0.88, 0.89, 0.9, 1)

        # ceiling grid panels
        panel_size = 3.5
        cells = int(self.chunk_size / panel_size)
        for ix in range(cells):
            for iy in range(cells):
                px = base_x + ix * panel_size + panel_size * 0.5
                py = base_y + iy * panel_size + panel_size * 0.5
                inset = 0.18
                panel = box.copyTo(chunk)
                panel.setPos(px, py, 3.16)
                panel.setScale((panel_size - inset) * 0.5, (panel_size - inset) * 0.5, 0.03)
                brightness = 0.92 + 0.05 * ((ix + iy) % 2)
                panel.setColor(brightness, brightness, brightness, 1)

                frame = box.copyTo(chunk)
                frame.setPos(px, py, 3.06)
                frame.setScale(panel_size * 0.5, panel_size * 0.5, 0.05)
                frame.setColor(0.73, 0.74, 0.75, 1)

        # pillars
        pillar_positions = [(10, 10), (32, 10), (10, 32), (32, 32)]
        for ox, oy in pillar_positions:
            if rng.random() < 0.9:
                node = box.copyTo(chunk)
                x = base_x + ox + rng.uniform(-1.5, 1.5)
                y = base_y + oy + rng.uniform(-1.5, 1.5)
                node.setPos(x, y, 1.5)
                node.setScale(0.75, 0.75, 1.5)
                node.setColor(0.9, 0.91, 0.92, 1)
                colliders.append(AABB(x - 0.8, x + 0.8, y - 0.8, y + 0.8))

        # long office walls
        if rng.random() < 0.94:
            horiz_y = base_y + rng.choice([8.5, 17.5, 26.5, 34.0])
            gap_center = base_x + rng.choice([8, 17, 25, 33])
            self.add_wall_run(chunk, colliders, base_x + 1.0, gap_center - 2.2, horiz_y, True, box)
            self.add_wall_run(chunk, colliders, gap_center + 2.2, base_x + self.chunk_size - 1.0, horiz_y, True, box)

        if rng.random() < 0.94:
            vert_x = base_x + rng.choice([7.5, 16.5, 25.5, 34.5])
            gap_center = base_y + rng.choice([8, 17, 25, 33])
            self.add_wall_run(chunk, colliders, base_y + 1.0, gap_center - 2.2, vert_x, False, box)
            self.add_wall_run(chunk, colliders, gap_center + 2.2, base_y + self.chunk_size - 1.0, vert_x, False, box)

        # desk islands
        desk_count = rng.randint(1, 3)
        for _ in range(desk_count):
            dx = base_x + rng.uniform(6, self.chunk_size - 6)
            dy = base_y + rng.uniform(6, self.chunk_size - 6)
            if any(c.expanded(1.2).contains(dx, dy) for c in colliders):
                continue
            self.add_desk_island(chunk, colliders, dx, dy, box, rng)

        return chunk, colliders

    def add_wall_run(self, parent, colliders, start, end, fixed, horizontal, box):
        if end <= start:
            return
        length = end - start
        node = box.copyTo(parent)
        if horizontal:
            cx = (start + end) * 0.5
            cy = fixed
            node.setPos(cx, cy, 1.4)
            node.setScale(length * 0.5, 0.16, 1.4)
            colliders.append(AABB(start, end, fixed - 0.28, fixed + 0.28))
        else:
            cx = fixed
            cy = (start + end) * 0.5
            node.setPos(cx, cy, 1.4)
            node.setScale(0.16, length * 0.5, 1.4)
            colliders.append(AABB(fixed - 0.28, fixed + 0.28, start, end))
        node.setColor(0.95, 0.95, 0.96, 1)

        trim = box.copyTo(parent)
        trim.setColor(0.18, 0.28, 0.42, 1)
        if horizontal:
            trim.setPos((start + end) * 0.5, fixed, 0.08)
            trim.setScale(length * 0.5, 0.18, 0.08)
        else:
            trim.setPos(fixed, (start + end) * 0.5, 0.08)
            trim.setScale(0.18, length * 0.5, 0.08)

    def add_desk_island(self, parent, colliders, x, y, box, rng):
        desktop = box.copyTo(parent)
        desktop.setPos(x, y, 0.72)
        desktop.setScale(1.5, 0.75, 0.05)
        desktop.setColor(0.96, 0.96, 0.96, 1)

        leg_offsets = [(-1.2, -0.55), (1.2, -0.55), (-1.2, 0.55), (1.2, 0.55)]
        for ox, oy in leg_offsets:
            leg = box.copyTo(parent)
            leg.setPos(x + ox * 0.5, y + oy * 0.5, 0.35)
            leg.setScale(0.05, 0.05, 0.35)
            leg.setColor(0.72, 0.72, 0.73, 1)

        for side in (-1, 1):
            chair = box.copyTo(parent)
            chair.setPos(x + side * 1.2, y + rng.uniform(-0.25, 0.25), 0.35)
            chair.setScale(0.35, 0.35, 0.35)
            chair.setColor(0.12, 0.13, 0.14, 1)

        if rng.random() < 0.88:
            monitor = box.copyTo(parent)
            monitor.setPos(x + rng.uniform(-0.3, 0.3), y, 1.08)
            monitor.setScale(0.3, 0.06, 0.22)
            monitor.setColor(0.1, 0.16, 0.11, 1)

        colliders.append(AABB(x - 1.55, x + 1.55, y - 0.85, y + 0.85))

    # ---------- creature ----------
    def place_creature(self, initial=False):
        px, py, _ = self.camera.getPos()
        attempts = 60
        for _ in range(attempts):
            dist = 18 if initial else random.uniform(16, 34)
            ang = math.radians(self.yaw + random.uniform(-120, 120))
            x = px + math.sin(ang) * dist + random.uniform(-6, 6)
            y = py + math.cos(ang) * dist + random.uniform(-6, 6)
            if any(c.expanded(1.2).contains(x, y) for c in self.world_colliders):
                continue
            self.creature_root.setPos(x, y, 0)
            self.creature_root.lookAt(self.camera)
            self.creature_alive = True
            self.status_text.setText("Shadow creature present")
            return
        self.creature_root.setPos(px + 10, py + 8, 0)

    def update_creature(self, dt):
        pos = self.creature_root.getPos()
        cam = self.camera.getPos()
        flat = Vec3(cam.x - pos.x, cam.y - pos.y, 0)
        dist = max(0.001, flat.length())
        bob = math.sin(self.taskMgr.globalClock.getFrameTime() * 2.2) * 0.05
        self.creature_root.setZ(bob)
        self.creature_root.lookAt(self.camera)

        self.creature_light_np.setPos(pos.x, pos.y - 0.2, 3.2)
        self.creature_light_np.lookAt(pos.x, pos.y, 0.8)

        if dist > 40:
            self.place_creature()
        elif dist < 4.8 and self.taskMgr.globalClock.getFrameTime() - self.last_shot_t > 2.5:
            self.place_creature()
            self.status_text.setText("It moved when you got close")

    # ---------- input/update ----------
    def update(self, task):
        dt = min(globalClock.getDt(), 0.033)
        if not SCREENSHOT_MODE:
            self.update_mouse_look()
        self.update_player(dt)
        self.update_weapon(dt)
        self.update_creature(dt)
        return Task.cont

    def update_mouse_look(self):
        if not self.mouseWatcherNode.hasMouse():
            return
        mw = self.win.getPointer(0)
        x = mw.getX()
        y = mw.getY()
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        dx = x - cx
        dy = y - cy
        if dx or dy:
            self.yaw -= dx * self.mouse_sensitivity
            self.pitch = max(-80, min(80, self.pitch - dy * self.mouse_sensitivity * 0.7))
            self.camera.setHpr(self.yaw, self.pitch, 0)
            self.win.movePointer(0, cx, cy)

    def key_down(self, key_name: str) -> bool:
        if SCREENSHOT_MODE or not getattr(self, "mouseWatcherNode", None):
            return False
        return self.mouseWatcherNode.isButtonDown(KeyboardButton.asciiKey(key_name.encode("ascii")))

    def update_player(self, dt):
        move = Vec3(0, 0, 0)
        if self.key_down("w"):
            move.y += 1
        if self.key_down("s"):
            move.y -= 1
        if self.key_down("a"):
            move.x -= 1
        if self.key_down("d"):
            move.x += 1

        if move.lengthSquared() > 0:
            move.normalize()
            heading_rad = math.radians(self.yaw)
            forward = Vec3(math.sin(heading_rad), math.cos(heading_rad), 0)
            right = Vec3(forward.y, -forward.x, 0)
            wish = (forward * move.y + right * move.x) * self.speed * dt
            self.move_with_collision(wish.x, wish.y)

        self.camera.setZ(self.player_height)

    def move_with_collision(self, dx, dy):
        pos = self.camera.getPos()
        new_x = pos.x + dx
        new_y = pos.y + dy

        blocked_x = any(c.expanded(self.player_radius).contains(new_x, pos.y) for c in self.world_colliders)
        blocked_y = any(c.expanded(self.player_radius).contains(pos.x, new_y) for c in self.world_colliders)
        blocked_xy = any(c.expanded(self.player_radius).contains(new_x, new_y) for c in self.world_colliders)

        if not blocked_x and not blocked_xy:
            pos.x = new_x
        if not blocked_y and not blocked_xy:
            pos.y = new_y
        self.camera.setPos(pos)

    def update_weapon(self, dt):
        t = self.taskMgr.globalClock.getFrameTime()
        sway = math.sin(t * 5.0) * 0.006
        base_pos = Point3(0.55, 0.92, -0.55)
        self.weapon_root.setPos(base_pos + Vec3(sway, 0, abs(sway) * 0.6))
        if self.weapon_flash_timer > 0:
            self.weapon_flash_timer -= dt
            pulse = 0.85 if self.weapon_flash_timer > 0 else 0.0
            self.weapon_muzzle.setColor(1.0, 0.9 + pulse * 0.1, 0.6, 1)
        else:
            self.weapon_muzzle.setColor(0.65, 0.72, 0.75, 1)

    def fire_weapon(self):
        t = self.taskMgr.globalClock.getFrameTime()
        if t - self.last_shot_t < 0.18:
            return
        self.last_shot_t = t
        self.weapon_flash_timer = 0.06
        self.weapon_root.setZ(-0.6)

        cam_pos = self.camera.getPos(self.render)
        forward = self.camera.getQuat(self.render).getForward()
        to_creature = self.creature_root.getPos(self.render) + Vec3(0, 0, 1.4) - cam_pos
        dist = to_creature.length()
        if dist < 45:
            alignment = forward.normalized().dot(to_creature.normalized())
            if alignment > 0.992:
                self.status_text.setText("Hit confirmed - it slipped deeper into the offices")
                self.place_creature()
            else:
                self.status_text.setText("Shot fired")
        else:
            self.status_text.setText("Shot fired")

    # ---------- screenshot ----------
    def auto_capture_task(self, task):
        if task.time < 0.75:
            return Task.cont
        self.yaw = -18
        self.pitch = -6
        self.camera.setHpr(self.yaw, self.pitch, 0)
        self.stream_world(force=True)
        self.graphicsEngine.renderFrame()
        self.graphicsEngine.renderFrame()
        self.screenshot(namePrefix=Filename.fromOsSpecific(SCREENSHOT_PATH), defaultFilename=False)
        raise SystemExit(0)


def main():
    try:
        app = Level8LiminalOffices()
        app.run()
    except SystemExit:
        raise
    except BaseException as exc:
        path = write_crash_log(exc)
        print(f"CRASH LOG: {path}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
