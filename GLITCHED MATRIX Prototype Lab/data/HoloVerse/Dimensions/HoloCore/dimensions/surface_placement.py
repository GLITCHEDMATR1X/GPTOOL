"""
Surface object placement for streamed HoloVerse dimension layers.

The grid/terrain stays shared. This system loads the active dimension's drop-in
asset folder and places flora/natural objects against the sampled terrain
surface. When dimensions switch, old objects fade out and the new active biome
objects fade in without changing the underlying grid surface.

Drop-in object format:
    assets/<biome_folder>/<object>.py
        SURFACE_OBJECT = {...}
        build(parent, x, y, z, rng, metadata) -> NodePath | None

Hierarchy density rule inside each biome folder:
    hierarchy 0 = baseline
    hierarchy 1 = 25% less than hierarchy 0
    hierarchy 2 = 25% less than hierarchy 1
    ... scale = 0.75 ** hierarchy
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from types import ModuleType
from typing import Callable, Iterable

from panda3d.core import NodePath, TransparencyAttrib, Vec3
from direct.task import Task

from world_grid import CELL_SIZE, FLAT_WORLD_RADIUS, HUB_VISUAL_EXTENT, Rect, smoothstep


HeightFn = Callable[[float, float], float]
LAYER_FADE_IN_SECONDS = 0.85
LAYER_FADE_OUT_SECONDS = 0.65


@dataclass(frozen=True)
class SurfaceObjectAsset:
    """Loaded drop-in surface object definition."""

    asset_id: str
    weight: float
    module: ModuleType
    hierarchy: int = 0
    min_distance_from_hub: float = FLAT_WORLD_RADIUS + 40.0
    max_slope: float = 0.70
    local_density: float = 1.0
    spawn_multiplier: float | None = None

    @property
    def hierarchy_density_scale(self) -> float:
        if self.spawn_multiplier is not None:
            return max(0.0, self.spawn_multiplier)
        return max(0.05, 0.75 ** max(0, self.hierarchy))

    def build(self, parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath | None:
        builder = getattr(self.module, "build", None)
        if not callable(builder):
            return None
        return builder(parent, x, y, z, rng, metadata)


@dataclass
class SurfaceObjectLayer:
    """One active or fading biome object layer inside a streamed chunk."""

    chunk_key: tuple[int, int]
    node: NodePath
    alpha: float = 1.0
    state: str = "stable"  # fading_in | stable | fading_out
    rendered_alpha: float | None = None

    def apply_alpha(self) -> None:
        if self.node.isEmpty():
            return
        alpha = max(0.0, min(1.0, self.alpha))
        if self.rendered_alpha is not None and abs(self.rendered_alpha - alpha) < 0.002:
            return
        if self.rendered_alpha is None:
            self.node.setTransparency(TransparencyAttrib.MAlpha)
        self.node.setColorScale(1.0, 1.0, 1.0, alpha)
        self.rendered_alpha = alpha


@dataclass
class SurfacePlacementSystem:
    """Sparse, deterministic surface placement for active dimension content."""

    asset_dir: Path
    floor_z: float
    surface_height: HeightFn
    root_name: str = "surface_object_placement_root"
    placement_step: float = CELL_SIZE * 2.0
    base_density: float = 0.13
    chunk_layers: dict[tuple[int, int], SurfaceObjectLayer] = field(default_factory=dict)
    fading_layers: list[SurfaceObjectLayer] = field(default_factory=list)
    assets: list[SurfaceObjectAsset] = field(default_factory=list)
    animated_nodes: list[NodePath] = field(default_factory=list)
    ambient_update_interval: float = 1.0 / 30.0
    _ambient_update_elapsed: float = 0.0

    def load_assets(self) -> "SurfacePlacementSystem":
        self.assets.clear()
        if not self.asset_dir.exists():
            return self

        loaded: list[SurfaceObjectAsset] = []
        for order, path in enumerate(sorted(self.asset_dir.glob("*.py"))):
            if path.name.startswith("_"):
                continue
            module = self._load_module(path)
            if module is None:
                continue
            info = getattr(module, "SURFACE_OBJECT", {})
            asset_id = str(info.get("id") or path.stem)
            weight = float(info.get("weight", 1.0))
            if weight <= 0:
                continue
            hierarchy = int(info.get("hierarchy", order))
            spawn_multiplier = info.get("spawn_multiplier", None)
            loaded.append(
                SurfaceObjectAsset(
                    asset_id=asset_id,
                    weight=weight,
                    module=module,
                    hierarchy=hierarchy,
                    min_distance_from_hub=float(info.get("min_distance_from_hub", FLAT_WORLD_RADIUS + 40.0)),
                    max_slope=float(info.get("max_slope", 0.70)),
                    local_density=float(info.get("local_density", 1.0)),
                    spawn_multiplier=None if spawn_multiplier is None else float(spawn_multiplier),
                )
            )
        self.assets = sorted(loaded, key=lambda asset: (asset.hierarchy, asset.asset_id))
        return self

    def set_asset_dir(self, asset_dir: Path) -> "SurfacePlacementSystem":
        self.asset_dir = asset_dir
        return self.load_assets()

    def _load_module(self, path: Path) -> ModuleType | None:
        # Include folder name in the module id so biome1/crystal.py and
        # biome2/crystal.py can coexist without import cache collisions.
        module_name = f"{path.parent.name}_asset_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def build_for_chunk(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int], fade_in: bool = False) -> NodePath:
        layer = self._build_layer(chunk_np, rect, chunk_key)
        if fade_in:
            layer.alpha = 0.0
            layer.state = "fading_in"
        layer.apply_alpha()
        self.chunk_layers[chunk_key] = layer
        return layer.node

    def replace_for_chunk(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int], fade: bool = True) -> NodePath:
        """Fade old dimension content out and build active dimension content in."""
        old = self.chunk_layers.pop(chunk_key, None)
        if old is not None and not old.node.isEmpty():
            if fade:
                old.state = "fading_out"
                old.alpha = min(1.0, max(0.0, old.alpha))
                self.fading_layers.append(old)
            else:
                old.node.removeNode()
        return self.build_for_chunk(chunk_np, rect, chunk_key, fade_in=fade)

    def remove_chunk(self, chunk_key: tuple[int, int]) -> None:
        layer = self.chunk_layers.pop(chunk_key, None)
        if layer is not None and not layer.node.isEmpty():
            layer.node.removeNode()
        kept: list[SurfaceObjectLayer] = []
        for fading in self.fading_layers:
            if fading.chunk_key == chunk_key:
                if not fading.node.isEmpty():
                    fading.node.removeNode()
            else:
                kept.append(fading)
        self.fading_layers = kept
        self._prune_animated_nodes()

    def update(self, task: Task) -> None:
        dt = min(getattr(task, "dt", 0.0) or 0.016, 0.05)
        self._update_layer_fades(dt)
        if not self.animated_nodes:
            return
        self._ambient_update_elapsed += dt
        if self._ambient_update_elapsed < self.ambient_update_interval:
            return
        self._ambient_update_elapsed = min(self._ambient_update_elapsed - self.ambient_update_interval, self.ambient_update_interval)
        self._update_ambient_motion(task.time)

    def _update_layer_fades(self, dt: float) -> None:
        for key, layer in list(self.chunk_layers.items()):
            if layer.node.isEmpty():
                self.chunk_layers.pop(key, None)
                continue
            if layer.state == "fading_in":
                layer.alpha = min(1.0, layer.alpha + dt / max(0.01, LAYER_FADE_IN_SECONDS))
                if layer.alpha >= 1.0:
                    layer.state = "stable"
                layer.apply_alpha()

        live_fading: list[SurfaceObjectLayer] = []
        for layer in self.fading_layers:
            if layer.node.isEmpty():
                continue
            layer.alpha = max(0.0, layer.alpha - dt / max(0.01, LAYER_FADE_OUT_SECONDS))
            layer.apply_alpha()
            if layer.alpha <= 0.0:
                layer.node.removeNode()
            else:
                live_fading.append(layer)
        self.fading_layers = live_fading

    def _update_ambient_motion(self, time_value: float) -> None:
        alive: list[NodePath] = []
        for node in self.animated_nodes:
            if node.isEmpty():
                continue
            if node.getPythonTag("bubble_emitter"):
                self._update_bubble_emitter(node, time_value)
                alive.append(node)
                continue

            phase = float(node.getPythonTag("flow_phase") or 0.0)
            amp = float(node.getPythonTag("flow_amplitude") or 2.0)
            rate = float(node.getPythonTag("flow_rate") or 0.22)
            kind = str(node.getPythonTag("ambient_motion_kind") or "sway")
            base_h = float(node.getPythonTag("ambient_base_h") or 0.0)
            base_p = float(node.getPythonTag("ambient_base_p") or 0.0)
            base_r = float(node.getPythonTag("ambient_base_r") or 0.0)
            base_sx = float(node.getPythonTag("ambient_base_sx") or 1.0)
            base_sy = float(node.getPythonTag("ambient_base_sy") or 1.0)
            base_sz = float(node.getPythonTag("ambient_base_sz") or 1.0)
            pulse_amp = float(node.getPythonTag("flow_pulse_amplitude") or 0.055)
            scale_amp = float(node.getPythonTag("flow_scale_amplitude") or 0.0)
            spin_rate = float(node.getPythonTag("flow_spin_rate") or 0.0)

            if kind == "orbit_spin":
                node.setH(base_h + time_value * spin_rate + math.sin(time_value * rate + phase) * amp * 0.18)
                node.setP(base_p + math.sin(time_value * rate * 0.62 + phase) * amp * 0.20)
                node.setR(base_r + math.cos(time_value * rate * 0.70 + phase) * amp * 0.24)
                pulse = 0.88 + math.sin(time_value * rate * 0.80 + phase) * pulse_amp
            elif kind == "signal_pulse":
                node.setH(base_h)
                node.setP(base_p)
                node.setR(base_r)
                scale = 1.0 + math.sin(time_value * rate + phase) * scale_amp
                node.setScale(base_sx * scale, base_sy * scale, base_sz * scale)
                pulse = 0.84 + math.sin(time_value * rate * 0.95 + phase) * pulse_amp
            elif kind == "electric_flicker":
                snap = math.sin(time_value * rate * 5.5 + phase)
                snap += math.sin(time_value * rate * 11.0 + phase * 1.7) * 0.42
                node.setH(base_h + snap * amp * 0.18)
                node.setP(base_p + math.sin(time_value * rate * 2.1 + phase) * amp * 0.38)
                node.setR(base_r + snap * amp * 0.32)
                pulse = 0.82 + abs(snap) * pulse_amp
            else:
                node.setH(base_h)
                node.setP(base_p + math.sin(time_value * rate + phase) * amp)
                node.setR(base_r + math.cos(time_value * rate * 0.77 + phase * 0.6) * amp * 0.42)
                pulse = 0.86 + math.sin(time_value * rate * 0.52 + phase) * pulse_amp

            node.setColorScale(1, 1, 1, max(0.0, min(1.0, pulse)))
            alive.append(node)
        self.animated_nodes = alive

    def _update_bubble_emitter(self, node: NodePath, time_value: float) -> None:
        """Update prebuilt lightweight bubbles for Dimension 3.

        Bubble objects are generated once by the drop-in asset and only moved /
        alpha-faded here. This avoids runtime create/destroy churn while still
        making the tube feel alive.
        """
        phase = float(node.getPythonTag("flow_phase") or 0.0)
        rate = float(node.getPythonTag("flow_rate") or 0.025)
        tube_pulse = 0.92 + math.sin(time_value * rate * 13.0 + phase) * 0.045
        node.setColorScale(1, 1, 1, tube_pulse)

        particles = node.getPythonTag("bubble_particles") or []
        for bubble in particles:
            if bubble.isEmpty():
                continue
            origin_x = float(bubble.getPythonTag("bubble_origin_x") or 0.0)
            origin_y = float(bubble.getPythonTag("bubble_origin_y") or 0.0)
            origin_z = float(bubble.getPythonTag("bubble_origin_z") or 0.0)
            rise = float(bubble.getPythonTag("bubble_rise") or 60.0)
            drift = float(bubble.getPythonTag("bubble_drift") or 7.0)
            bubble_phase = float(bubble.getPythonTag("bubble_phase") or 0.0)
            bubble_rate = float(bubble.getPythonTag("bubble_rate") or 0.03)
            bubble_spin = float(bubble.getPythonTag("bubble_spin") or 0.0)
            progress = (time_value * bubble_rate + bubble_phase) % 1.0

            # Rise high, drift gently, and disappear near the top of the cycle.
            fade_in = smoothstep(0.00, 0.12, progress)
            fade_out = 1.0 - smoothstep(0.62, 1.00, progress)
            alpha = max(0.0, min(1.0, fade_in * fade_out))
            drift_angle = phase + bubble_phase * math.tau + progress * math.tau * 0.72
            wobble = math.sin(progress * math.tau * 1.35 + phase) * drift * 0.36
            bubble.setPos(
                origin_x + math.cos(drift_angle) * drift * progress + math.cos(drift_angle * 1.7) * wobble,
                origin_y + math.sin(drift_angle) * drift * progress + math.sin(drift_angle * 1.3) * wobble,
                origin_z + rise * progress,
            )
            bubble.setHpr(
                bubble_spin * time_value + progress * 120.0,
                math.sin(time_value * 0.35 + bubble_phase * math.tau) * 11.0,
                math.cos(time_value * 0.28 + bubble_phase * math.tau) * 9.0,
            )
            base = bubble.getPythonTag("bubble_base_color") or (1.0, 0.55, 0.12, 0.42)
            bubble.setColorScale(base[0], base[1], base[2], base[3] * alpha)

    def _build_layer(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> SurfaceObjectLayer:
        root = chunk_np.attachNewNode(f"surface_objects_{self.asset_dir.name}_{chunk_key[0]}_{chunk_key[1]}")
        root.setTransparency(TransparencyAttrib.MAlpha)
        if not self.assets:
            return SurfaceObjectLayer(chunk_key=chunk_key, node=root)

        layer_animated_nodes: list[NodePath] = []
        for x, y in self._candidate_points(rect):
            if self._inside_hub_exclusion(x, y):
                continue
            distance = math.hypot(x, y)
            if distance < FLAT_WORLD_RADIUS + 20.0:
                continue

            slope = self._approx_surface_slope(x, y)
            base_density = self._density_for_point(x, y, distance)
            if base_density <= 0:
                continue

            # Hierarchy rule: earlier assets get first claim. Later assets only
            # attempt points left empty by earlier entries inside the active dimension.
            for asset in self.assets:
                if distance < asset.min_distance_from_hub or slope > asset.max_slope:
                    continue

                rng = Random(self._stable_asset_seed(x, y, asset.asset_id, self.asset_dir.name))
                object_density = base_density * asset.weight * asset.local_density * asset.hierarchy_density_scale
                object_density = max(0.0, min(0.94, object_density))
                if rng.random() > object_density:
                    continue

                jitter = self.placement_step * 0.26
                px = x + (rng.random() - 0.5) * jitter
                py = y + (rng.random() - 0.5) * jitter
                if self._inside_hub_exclusion(px, py):
                    continue
                pz = self.floor_z + self.surface_height(px, py)

                metadata = {
                    "asset_id": asset.asset_id,
                    "biome_folder": self.asset_dir.name,
                    "hierarchy": asset.hierarchy,
                    "hierarchy_density_scale": asset.hierarchy_density_scale,
                    "distance_from_hub": distance,
                    "surface_slope": slope,
                    "surface_position": Vec3(px, py, pz),
                    # Drop-in assets may use this to conform multi-part objects
                    # to the terrain surface instead of assuming a flat local patch.
                    "surface_z_at": lambda sx, sy: self.floor_z + self.surface_height(sx, sy),
                    "surface_height_at": self.surface_height,
                    "floor_z": self.floor_z,
                }
                node = asset.build(root, px, py, pz, rng, metadata)
                if node is None:
                    continue
                node.setPythonTag("surface_anchor_z", pz)
                node.setPythonTag("surface_asset_id", asset.asset_id)
                node.setPythonTag("surface_biome_folder", self.asset_dir.name)
                node.setPythonTag("surface_hierarchy", asset.hierarchy)
                if node.getPythonTag("animated_surface_object"):
                    layer_animated_nodes.append(node)
                break

        self.animated_nodes.extend(layer_animated_nodes)
        return SurfaceObjectLayer(chunk_key=chunk_key, node=root)

    def _candidate_points(self, rect: Rect) -> Iterable[tuple[float, float]]:
        start_x = math.floor(rect.x1 / self.placement_step) * self.placement_step + self.placement_step * 0.5
        start_y = math.floor(rect.y1 / self.placement_step) * self.placement_step + self.placement_step * 0.5
        x = start_x
        while x < rect.x2:
            y = start_y
            while y < rect.y2:
                if rect.x1 <= x <= rect.x2 and rect.y1 <= y <= rect.y2:
                    yield round(x, 6), round(y, 6)
                y += self.placement_step
            x += self.placement_step

    def _inside_hub_exclusion(self, x: float, y: float) -> bool:
        return -HUB_VISUAL_EXTENT < x < HUB_VISUAL_EXTENT and -HUB_VISUAL_EXTENT < y < HUB_VISUAL_EXTENT

    def _approx_surface_slope(self, x: float, y: float) -> float:
        sample = CELL_SIZE * 0.5
        hx1 = self.surface_height(x - sample, y)
        hx2 = self.surface_height(x + sample, y)
        hy1 = self.surface_height(x, y - sample)
        hy2 = self.surface_height(x, y + sample)
        return max(abs(hx2 - hx1), abs(hy2 - hy1)) / (sample * 2.0)

    def _density_for_point(self, x: float, y: float, distance: float) -> float:
        density_rng = Random(self._stable_seed(x, y))
        object_density = self.base_density * smoothstep(FLAT_WORLD_RADIUS + 40.0, FLAT_WORLD_RADIUS + 720.0, distance)
        object_density *= 0.70 + density_rng.random() * 0.60
        return max(0.0, min(0.94, object_density))

    def _stable_seed(self, x: float, y: float) -> int:
        ix = int(math.floor(x / self.placement_step))
        iy = int(math.floor(y / self.placement_step))
        seed = (ix * 73856093) ^ (iy * 19349663) ^ 0xB10A1E
        return seed & 0xFFFFFFFF

    def _stable_asset_seed(self, x: float, y: float, asset_id: str, biome_folder: str) -> int:
        asset_hash = 0x345678
        for char in f"{biome_folder}:{asset_id}":
            asset_hash = ((asset_hash * 1000003) ^ ord(char)) & 0xFFFFFFFF
        return (self._stable_seed(x, y) ^ asset_hash) & 0xFFFFFFFF

    def _prune_animated_nodes(self) -> None:
        live_roots = [layer.node for layer in self.chunk_layers.values() if not layer.node.isEmpty()]
        live_roots.extend(layer.node for layer in self.fading_layers if not layer.node.isEmpty())
        self.animated_nodes = [
            node for node in self.animated_nodes
            if not node.isEmpty() and any(self._is_under(node, root) for root in live_roots)
        ]

    def _is_under(self, node: NodePath, ancestor: NodePath) -> bool:
        current = node
        while not current.isEmpty():
            if current == ancestor:
                return True
            current = current.getParent()
        return False

# PASS23_BUBBLE_WEED_SMOOTHER
PASS23_EXTRA_BIOME_OBJECTS = {
    3: [
        {
            'module': 'assets.biome3.bubble_weed_cluster',
            'object_id': 'bubble_weed_cluster',
            'spawn_weight': 0.75,
            'claim_radius': 6.5,
            'surface_anchored': True,
            'near': 'lava_bubble_tube',
        },
    ],
}
