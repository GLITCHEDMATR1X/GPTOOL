from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "gptool-panda-xr-vr-builder-scene-v3"
SUPPORTED_SCHEMAS = {
    "gptool-panda-xr-vr-builder-scene-v1",
    "gptool-panda-xr-vr-builder-scene-v2",
    SCHEMA_VERSION,
}
ALLOWED_BEHAVIOR_TYPES = {"spin", "bob", "pulse_color", "follow_path", "orbit"}
ALLOWED_MATERIAL_SHADES = {"matte", "satin", "gloss", "emissive", "unlit"}
Vec3 = tuple[float, float, float]
Face = tuple[int, ...]


def _r(value: float) -> float:
    return round(float(value), 6)


def _vadd(a: Vec3, b: Vec3) -> Vec3:
    return (_r(a[0] + b[0]), _r(a[1] + b[1]), _r(a[2] + b[2]))


def _vsub(a: Vec3, b: Vec3) -> Vec3:
    return (_r(a[0] - b[0]), _r(a[1] - b[1]), _r(a[2] - b[2]))


def _vmul(a: Vec3, scalar: float) -> Vec3:
    return (_r(a[0] * scalar), _r(a[1] * scalar), _r(a[2] * scalar))


def _vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vcross(a: Vec3, b: Vec3) -> Vec3:
    return (
        _r(a[1] * b[2] - a[2] * b[1]),
        _r(a[2] * b[0] - a[0] * b[2]),
        _r(a[0] * b[1] - a[1] * b[0]),
    )


def _vlen(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _vnorm(a: Vec3, fallback: Vec3 = (0.0, 0.0, 1.0)) -> Vec3:
    length = _vlen(a)
    if length < 1e-8:
        return fallback
    return (_r(a[0] / length), _r(a[1] / length), _r(a[2] / length))


def _vlerp(a: Vec3, b: Vec3, amount: float) -> Vec3:
    amount = max(0.0, min(1.0, amount))
    return (
        _r(a[0] + (b[0] - a[0]) * amount),
        _r(a[1] + (b[1] - a[1]) * amount),
        _r(a[2] + (b[2] - a[2]) * amount),
    )


def _as_vec3(value: Iterable[float], default: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    items = list(value) if value is not None else list(default)
    while len(items) < 3:
        items.append(0.0)
    return (_r(items[0]), _r(items[1]), _r(items[2]))


def _as_int3(value: Iterable[int] | Iterable[float] | None, default: tuple[int, int, int] = (1, 1, 1)) -> tuple[int, int, int]:
    items = list(value) if value is not None else list(default)
    while len(items) < 3:
        items.append(1)
    return (max(1, int(items[0])), max(1, int(items[1])), max(1, int(items[2])))


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_bytes(data)
    temp_path.replace(path)


def _pad4(data: bytes, pad_byte: bytes = b"\x00") -> bytes:
    return data + pad_byte * ((-len(data)) % 4)


def _smooth_weight(distance: float, radius: float) -> float:
    if radius <= 0.0 or distance >= radius:
        return 0.0
    t = 1.0 - max(0.0, distance / radius)
    return t * t * (3.0 - 2.0 * t)


def _rotate_xyz(point: Vec3, rotation_deg: Vec3) -> Vec3:
    x, y, z = point
    rx, ry, rz = (math.radians(v) for v in rotation_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return (_r(x), _r(y), _r(z))


def _triangulate_faces(faces: Iterable[Face]) -> list[tuple[int, int, int]]:
    triangles: list[tuple[int, int, int]] = []
    for face in faces:
        for index in range(1, len(face) - 1):
            triangles.append((face[0], face[index], face[index + 1]))
    return triangles


def _yaw_from_points(a: Vec3, b: Vec3) -> float:
    delta = _vsub(b, a)
    if abs(delta[0]) + abs(delta[1]) < 1e-8:
        return 0.0
    return math.degrees(math.atan2(delta[1], delta[0]))


def _distance(a: Vec3, b: Vec3) -> float:
    return _vlen(_vsub(a, b))


def _finite_vec(vec: Vec3) -> bool:
    return all(math.isfinite(value) for value in vec)


def _as_color(value: Iterable[float] | None, default: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)) -> tuple[float, float, float, float]:
    items = list(value) if value is not None else list(default)
    while len(items) < 4:
        items.append(1.0 if len(items) == 3 else 0.8)
    return tuple(max(0.0, min(1.0, _r(item))) for item in items[:4])  # type: ignore[return-value]


def _object_material(obj: "BuilderObject") -> dict[str, Any]:
    material = dict(obj.metadata.get("material") or {})
    color = _as_color(material.get("base_color"), (0.75, 0.78, 0.82, 1.0))
    shade = str(material.get("shade", "matte"))
    if shade == "emissive":
        material.setdefault("emission_strength", 0.8)
    return {
        "base_color": color,
        "shade": shade,
        "roughness": float(material.get("roughness", 0.72)),
        "metallic": float(material.get("metallic", 0.0)),
        "emission_strength": float(material.get("emission_strength", 0.0)),
    }


@dataclass
class MeshData:
    vertices: list[Vec3]
    faces: list[Face]

    def bounds(self) -> dict[str, Vec3]:
        if not self.vertices:
            return {"min": (0.0, 0.0, 0.0), "max": (0.0, 0.0, 0.0)}
        xs, ys, zs = zip(*self.vertices)
        return {
            "min": (_r(min(xs)), _r(min(ys)), _r(min(zs))),
            "max": (_r(max(xs)), _r(max(ys)), _r(max(zs))),
        }

    def checksum(self) -> str:
        payload = json.dumps({"vertices": self.vertices, "faces": self.faces}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ControlPoint:
    id: str
    position: Vec3
    delta: Vec3
    radius: float
    mode: str = "smooth_pull"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlPoint":
        return cls(
            id=str(data["id"]),
            position=_as_vec3(data.get("position", (0, 0, 0))),
            delta=_as_vec3(data.get("delta", (0, 0, 0))),
            radius=float(data.get("radius", 1.0)),
            mode=str(data.get("mode", "smooth_pull")),
        )


@dataclass
class Transform:
    position: Vec3 = (0.0, 0.0, 0.0)
    rotation: Vec3 = (0.0, 0.0, 0.0)
    scale: Vec3 = (1.0, 1.0, 1.0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transform":
        return cls(
            position=_as_vec3(data.get("position", (0, 0, 0))),
            rotation=_as_vec3(data.get("rotation", (0, 0, 0))),
            scale=_as_vec3(data.get("scale", (1, 1, 1)), (1.0, 1.0, 1.0)),
        )


@dataclass
class EditorPanel:
    id: str
    label: str
    transform: Transform = field(default_factory=Transform)
    size: tuple[float, float] = (0.62, 0.38)
    opacity: float = 0.86
    pinned: bool = True
    content: dict[str, Any] = field(default_factory=dict)
    controls: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "transform": asdict(self.transform),
            "size": [_r(self.size[0]), _r(self.size[1])],
            "opacity": _r(max(0.0, min(1.0, self.opacity))),
            "pinned": bool(self.pinned),
            "content": self.content,
            "controls": self.controls,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorPanel":
        size = list(data.get("size", (0.62, 0.38)))
        while len(size) < 2:
            size.append(0.38)
        return cls(
            id=str(data["id"]),
            label=str(data.get("label", data["id"])),
            transform=Transform.from_dict(data.get("transform", {})),
            size=(_r(size[0]), _r(size[1])),
            opacity=float(data.get("opacity", 0.86)),
            pinned=bool(data.get("pinned", True)),
            content=dict(data.get("content", {})),
            controls=list(data.get("controls", [])),
        )


@dataclass
class Grid3DSettings:
    id: str = "main_grid"
    enabled: bool = True
    origin: Vec3 = (-3.0, -2.0, 0.0)
    cell_size: float = 0.25
    dimensions: tuple[int, int, int] = (24, 16, 10)
    proximity_radius: float = 4.0
    major_every: int = 4
    opacity: float = 0.28
    snap_enabled: bool = True
    fill_mode: str = "cell_volume"
    render_strategy: str = "proximity_chunked_lines"
    color: tuple[float, float, float, float] = (0.42, 0.72, 1.0, 0.32)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "origin": list(self.origin),
            "cell_size": _r(self.cell_size),
            "dimensions": list(self.dimensions),
            "proximity_radius": _r(self.proximity_radius),
            "major_every": max(1, int(self.major_every)),
            "opacity": _r(max(0.0, min(1.0, self.opacity))),
            "snap_enabled": bool(self.snap_enabled),
            "fill_mode": self.fill_mode,
            "render_strategy": self.render_strategy,
            "color": list(_as_color(self.color)),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Grid3DSettings":
        data = dict(data or {})
        return cls(
            id=str(data.get("id", "main_grid")),
            enabled=bool(data.get("enabled", True)),
            origin=_as_vec3(data.get("origin", (-3.0, -2.0, 0.0))),
            cell_size=max(0.01, float(data.get("cell_size", 0.25))),
            dimensions=_as_int3(data.get("dimensions", (24, 16, 10)), (24, 16, 10)),
            proximity_radius=max(0.25, float(data.get("proximity_radius", 4.0))),
            major_every=max(1, int(data.get("major_every", 4))),
            opacity=max(0.0, min(1.0, float(data.get("opacity", 0.28)))),
            snap_enabled=bool(data.get("snap_enabled", True)),
            fill_mode=str(data.get("fill_mode", "cell_volume")),
            render_strategy=str(data.get("render_strategy", "proximity_chunked_lines")),
            color=_as_color(data.get("color"), (0.42, 0.72, 1.0, 0.32)),
        )

    def snap_position(self, position: Vec3) -> Vec3:
        return tuple(
            _r(self.origin[index] + round((position[index] - self.origin[index]) / self.cell_size) * self.cell_size)
            for index in range(3)
        )  # type: ignore[return-value]

    def cell_min(self, cell: tuple[int, int, int]) -> Vec3:
        return (
            _r(self.origin[0] + cell[0] * self.cell_size),
            _r(self.origin[1] + cell[1] * self.cell_size),
            _r(self.origin[2] + cell[2] * self.cell_size),
        )

    def cell_center(self, cell: tuple[int, int, int], fill: tuple[int, int, int] = (1, 1, 1)) -> Vec3:
        return (
            _r(self.origin[0] + (cell[0] + fill[0] / 2.0) * self.cell_size),
            _r(self.origin[1] + (cell[1] + fill[1] / 2.0) * self.cell_size),
            _r(self.origin[2] + (cell[2] + fill[2] / 2.0) * self.cell_size),
        )

    def nearest_cell(self, position: Vec3) -> tuple[int, int, int]:
        return tuple(
            int(math.floor((position[index] - self.origin[index]) / self.cell_size))
            for index in range(3)
        )  # type: ignore[return-value]

    def line_count(self) -> int:
        x, y, z = self.dimensions
        return (y + 1) * (z + 1) + (x + 1) * (z + 1) + (x + 1) * (y + 1)


@dataclass
class BuilderObject:
    id: str
    kind: str
    params: dict[str, float] = field(default_factory=dict)
    transform: Transform = field(default_factory=Transform)
    control_points: list[ControlPoint] = field(default_factory=list)
    collision: dict[str, Any] = field(default_factory=dict)
    sockets: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def base_mesh(self) -> MeshData:
        if self.kind == "cube":
            return make_box_mesh(float(self.params.get("size", 1.0)), float(self.params.get("size", 1.0)), float(self.params.get("size", 1.0)), int(self.params.get("subdivisions", 2)))
        if self.kind == "floor":
            return make_box_mesh(float(self.params.get("width", 4.0)), float(self.params.get("depth", 4.0)), float(self.params.get("thickness", 0.12)), int(self.params.get("subdivisions", 1)))
        if self.kind == "wall":
            return make_box_mesh(float(self.params.get("width", 4.0)), float(self.params.get("thickness", 0.16)), float(self.params.get("height", 2.5)), int(self.params.get("subdivisions", 1)))
        if self.kind == "sphere":
            return make_sphere_mesh(float(self.params.get("radius", 0.5)), int(self.params.get("rings", 12)), int(self.params.get("segments", 16)))
        if self.kind == "cylinder":
            return make_cylinder_mesh(float(self.params.get("radius", 0.5)), float(self.params.get("height", 1.0)), int(self.params.get("segments", 16)), int(self.params.get("height_segments", 1)))
        if self.kind == "capsule":
            return make_capsule_mesh(float(self.params.get("radius", 0.5)), float(self.params.get("cylinder_height", 1.0)), int(self.params.get("segments", 16)), int(self.params.get("hemisphere_rings", 6)))
        if self.kind == "stroke":
            stroke = self.metadata.get("stroke") or {}
            points = [_as_vec3(point) for point in stroke.get("points", [])]
            radius = float(stroke.get("radius", self.params.get("radius", 0.04)))
            radial_segments = int(stroke.get("radial_segments", self.params.get("radial_segments", 6)))
            max_points = int(stroke.get("max_points", self.params.get("max_points", 128)))
            return make_stroke_mesh(points, radius, radial_segments, max_points)
        raise ValueError(f"Unsupported Panda XR object kind: {self.kind}")

    def deformed_mesh(self) -> MeshData:
        mesh = self.base_mesh()
        if not self.control_points:
            return mesh
        vertices: list[Vec3] = []
        for vertex in mesh.vertices:
            next_vertex = vertex
            for control in self.control_points:
                weight = _smooth_weight(_distance(vertex, control.position), control.radius)
                if weight:
                    next_vertex = _vadd(next_vertex, _vmul(control.delta, weight))
            vertices.append(next_vertex)
        return MeshData(vertices, mesh.faces)

    def world_mesh(self) -> MeshData:
        mesh = self.deformed_mesh()
        vertices: list[Vec3] = []
        for vertex in mesh.vertices:
            scaled = (
                _r(vertex[0] * self.transform.scale[0]),
                _r(vertex[1] * self.transform.scale[1]),
                _r(vertex[2] * self.transform.scale[2]),
            )
            vertices.append(_vadd(_rotate_xyz(scaled, self.transform.rotation), self.transform.position))
        return MeshData(vertices, mesh.faces)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "params": self.params,
            "transform": asdict(self.transform),
            "control_points": [asdict(item) for item in self.control_points],
            "collision": self.collision,
            "sockets": self.sockets,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuilderObject":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            params=dict(data.get("params", {})),
            transform=Transform.from_dict(data.get("transform", {})),
            control_points=[ControlPoint.from_dict(item) for item in data.get("control_points", [])],
            collision=dict(data.get("collision", {})),
            sockets=list(data.get("sockets", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class BuilderScene:
    name: str
    objects: list[BuilderObject] = field(default_factory=list)
    connections: list[dict[str, Any]] = field(default_factory=list)
    path_nodes: list[dict[str, Any]] = field(default_factory=list)
    animations: list[dict[str, Any]] = field(default_factory=list)
    behaviors: list[dict[str, Any]] = field(default_factory=list)
    operation_history: list[dict[str, Any]] = field(default_factory=list)
    performance_budget: dict[str, Any] = field(default_factory=lambda: {
        "max_stroke_points_per_object": 128,
        "max_stroke_radial_segments": 8,
        "target_frame_rate": 90,
        "recommended_draw_call_groups": 48,
        "max_grid_visible_lines": 2400,
        "max_grid_occupied_cells": 4096,
    })
    editor_panels: list[EditorPanel] = field(default_factory=list)
    grid: Grid3DSettings = field(default_factory=Grid3DSettings)
    metadata: dict[str, Any] = field(default_factory=dict)
    units: str = "meters"

    def object_by_id(self, object_id: str) -> BuilderObject:
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        raise KeyError(f"No Panda XR object named {object_id!r}")

    def record(self, operation: str, **details: Any) -> None:
        self.operation_history.append({"index": len(self.operation_history), "operation": operation, "details": details})

    def create_object(self, obj: BuilderObject) -> BuilderObject:
        if any(existing.id == obj.id for existing in self.objects):
            raise ValueError(f"Duplicate Panda XR object id: {obj.id}")
        self.objects.append(obj)
        self.record("create_object", object=obj.id, kind=obj.kind)
        return obj

    def panel_by_id(self, panel_id: str) -> EditorPanel:
        for panel in self.editor_panels:
            if panel.id == panel_id:
                return panel
        raise KeyError(f"No Panda XR editor panel named {panel_id!r}")

    def add_editor_panel(
        self,
        panel_id: str,
        label: str,
        position: Vec3,
        rotation: Vec3 = (0.0, 0.0, 0.0),
        size: tuple[float, float] = (0.62, 0.38),
        *,
        content: dict[str, Any] | None = None,
        controls: list[dict[str, Any]] | None = None,
        opacity: float = 0.86,
        pinned: bool = True,
    ) -> EditorPanel:
        if any(panel.id == panel_id for panel in self.editor_panels):
            raise ValueError(f"Duplicate Panda XR editor panel id: {panel_id}")
        panel = EditorPanel(
            panel_id,
            label,
            Transform(position=_as_vec3(position), rotation=_as_vec3(rotation), scale=(1.0, 1.0, 1.0)),
            size=(_r(size[0]), _r(size[1])),
            opacity=max(0.0, min(1.0, opacity)),
            pinned=pinned,
            content=dict(content or {}),
            controls=list(controls or []),
        )
        self.editor_panels.append(panel)
        self.record("add_editor_panel", panel=panel_id, position=panel.transform.position, size=panel.size)
        return panel

    def move_editor_panel(self, panel_id: str, position: Vec3, rotation: Vec3 | None = None, smoothing: float = 1.0) -> None:
        panel = self.panel_by_id(panel_id)
        amount = max(0.0, min(1.0, smoothing))
        panel.transform.position = _vlerp(panel.transform.position, _as_vec3(position), amount)
        if rotation is not None:
            panel.transform.rotation = _vlerp(panel.transform.rotation, _as_vec3(rotation), amount)
        self.record("move_editor_panel", panel=panel_id, position=panel.transform.position, rotation=panel.transform.rotation, smoothing=amount)

    def configure_grid_3d(
        self,
        *,
        origin: Vec3 | None = None,
        cell_size: float | None = None,
        dimensions: tuple[int, int, int] | None = None,
        proximity_radius: float | None = None,
        major_every: int | None = None,
        opacity: float | None = None,
        snap_enabled: bool | None = None,
    ) -> None:
        current = self.grid
        self.grid = Grid3DSettings(
            id=current.id,
            enabled=current.enabled,
            origin=_as_vec3(origin, current.origin) if origin is not None else current.origin,
            cell_size=max(0.01, float(cell_size if cell_size is not None else current.cell_size)),
            dimensions=_as_int3(dimensions, current.dimensions) if dimensions is not None else current.dimensions,
            proximity_radius=max(0.25, float(proximity_radius if proximity_radius is not None else current.proximity_radius)),
            major_every=max(1, int(major_every if major_every is not None else current.major_every)),
            opacity=max(0.0, min(1.0, float(opacity if opacity is not None else current.opacity))),
            snap_enabled=current.snap_enabled if snap_enabled is None else bool(snap_enabled),
            fill_mode=current.fill_mode,
            render_strategy=current.render_strategy,
            color=current.color,
        )
        self.record("configure_grid_3d", grid=self.grid.to_dict())

    def snap_position_to_grid(self, position: Vec3) -> Vec3:
        return self.grid.snap_position(_as_vec3(position))

    def create_grid_block(
        self,
        object_id: str,
        cell: tuple[int, int, int],
        fill_cells: tuple[int, int, int] = (1, 1, 1),
        color: tuple[float, float, float, float] = (0.78, 0.86, 1.0, 1.0),
        snap_group: str = "grid_art",
    ) -> BuilderObject:
        cell = tuple(int(value) for value in cell)  # type: ignore[assignment]
        fill = _as_int3(fill_cells)
        center = self.grid.cell_center(cell, fill)
        obj = BuilderObject(
            object_id,
            "cube",
            {"size": self.grid.cell_size, "subdivisions": 1},
            Transform(position=center, scale=(float(fill[0]), float(fill[1]), float(fill[2]))),
            collision={"type": "box", "deformed": False, "grid_fill": list(fill)},
            metadata={
                "material": {"base_color": list(_as_color(color)), "shade": "satin", "roughness": 0.5},
                "grid": {
                    "grid_id": self.grid.id,
                    "cell": list(cell),
                    "fill_cells": list(fill),
                    "snapped": True,
                    "snap_group": snap_group,
                    "batch_key": f"{self.grid.id}:{snap_group}:{_as_color(color)}",
                },
                "smoothing": {"enabled": True, "level": 0.35, "edge_preserve": True},
                "performance": {"batchable": True, "render_strategy": "instanced_or_merged_by_batch_key"},
            },
        )
        self.create_object(obj)
        self.record("create_grid_block", object=object_id, cell=cell, fill_cells=fill, snap_group=snap_group)
        return obj

    def snap_object_to_grid(self, object_id: str, fill_cells: tuple[int, int, int] = (1, 1, 1), snap_group: str = "objects") -> None:
        obj = self.object_by_id(object_id)
        fill = _as_int3(fill_cells)
        cell = self.grid.nearest_cell(obj.transform.position)
        obj.transform.position = self.grid.cell_center(cell, fill)
        if obj.kind == "cube":
            obj.params["size"] = self.grid.cell_size
            obj.transform.scale = (float(fill[0]), float(fill[1]), float(fill[2]))
        obj.metadata["grid"] = {
            "grid_id": self.grid.id,
            "cell": list(cell),
            "fill_cells": list(fill),
            "snapped": True,
            "snap_group": snap_group,
            "batch_key": f"{self.grid.id}:{snap_group}:{obj.kind}",
        }
        obj.metadata.setdefault("performance", {})["batchable"] = True
        self.record("snap_object_to_grid", object=object_id, cell=cell, fill_cells=fill, snap_group=snap_group)

    def set_object_smoothing(self, object_id: str, level: float = 0.5, edge_preserve: bool = True) -> None:
        obj = self.object_by_id(object_id)
        obj.metadata["smoothing"] = {
            "enabled": True,
            "level": _r(max(0.0, min(1.0, level))),
            "edge_preserve": bool(edge_preserve),
            "mode": "editor_preview_and_export_hint",
        }
        self.record("set_object_smoothing", object=object_id, level=obj.metadata["smoothing"]["level"], edge_preserve=edge_preserve)

    def two_hand_resize(self, object_id: str, start_a: Vec3, start_b: Vec3, end_a: Vec3, end_b: Vec3) -> None:
        obj = self.object_by_id(object_id)
        start = max(0.001, _distance(start_a, start_b))
        end = max(0.001, _distance(end_a, end_b))
        factor = _r(end / start)
        obj.transform.scale = tuple(_r(value * factor) for value in obj.transform.scale)  # type: ignore[assignment]
        obj.metadata["last_resize_factor"] = factor
        self.record("two_hand_resize", object=object_id, start_distance=_r(start), end_distance=_r(end), factor=factor)

    def two_hand_twist(self, object_id: str, start_a: Vec3, start_b: Vec3, end_a: Vec3, end_b: Vec3) -> None:
        obj = self.object_by_id(object_id)
        yaw_delta = _r(_yaw_from_points(end_a, end_b) - _yaw_from_points(start_a, start_b))
        obj.transform.rotation = (obj.transform.rotation[0], obj.transform.rotation[1], _r(obj.transform.rotation[2] + yaw_delta))
        obj.metadata["last_twist_degrees"] = yaw_delta
        self.record("two_hand_twist", object=object_id, yaw_delta=yaw_delta)

    def squeeze_morph(self, object_id: str, grip_a: Vec3, grip_b: Vec3, amount: float = 0.2, radius: float = 1.0) -> None:
        obj = self.object_by_id(object_id)
        center = ((_r((grip_a[0] + grip_b[0]) / 2)), (_r((grip_a[1] + grip_b[1]) / 2)), (_r((grip_a[2] + grip_b[2]) / 2)))
        delta = _vmul(_vsub(center, obj.transform.position), amount)
        control = ControlPoint(f"{object_id}_squeeze_{len(obj.control_points)}", center, delta, radius, "vr_squeeze")
        obj.control_points.append(control)
        obj.metadata["last_squeeze_amount"] = amount
        self.record("squeeze_morph", object=object_id, control_point=control.id, center=center, delta=delta, radius=radius)

    def connect_sockets(self, connection_id: str, from_object: str, from_socket: str, to_object: str, to_socket: str, connection_type: str = "builder_connection") -> None:
        self.connections.append({
            "id": connection_id,
            "from": {"object": from_object, "socket": from_socket},
            "to": {"object": to_object, "socket": to_socket},
            "type": connection_type,
        })
        self.record("connect_sockets", connection=connection_id, from_object=from_object, to_object=to_object)

    def add_path_node(self, node_id: str, position: Vec3, links: list[str] | None = None, radius: float = 0.35) -> None:
        self.path_nodes.append({"id": node_id, "position": list(position), "links": links or [], "radius": radius})
        self.record("add_path_node", node=node_id, position=position, links=links or [])

    def begin_stroke(
        self,
        stroke_id: str,
        color: tuple[float, float, float, float] = (0.35, 0.75, 1.0, 1.0),
        radius: float = 0.045,
        shade: str = "emissive",
        radial_segments: int = 6,
        max_points: int | None = None,
    ) -> BuilderObject:
        max_points = int(max_points or self.performance_budget.get("max_stroke_points_per_object", 128))
        radial_segments = min(int(radial_segments), int(self.performance_budget.get("max_stroke_radial_segments", 8)))
        obj = BuilderObject(
            stroke_id,
            "stroke",
            {"radius": radius, "radial_segments": radial_segments, "max_points": max_points},
            metadata={
                "stroke": {"points": [], "radius": radius, "radial_segments": radial_segments, "max_points": max_points},
                "material": {"base_color": list(_as_color(color)), "shade": shade, "roughness": 0.38, "emission_strength": 0.55 if shade == "emissive" else 0.0},
                "performance": {"dynamic_art": True, "lod_group": "stroke", "max_points": max_points},
            },
            collision={"type": "stroke_tube", "radius": radius, "deformed": True},
        )
        self.create_object(obj)
        self.record("begin_stroke", object=stroke_id, radius=radius, radial_segments=radial_segments, max_points=max_points)
        return obj

    def draw_stroke_points(self, stroke_id: str, points: Iterable[Vec3], min_distance: float = 0.025) -> None:
        obj = self.object_by_id(stroke_id)
        if obj.kind != "stroke":
            raise ValueError(f"Object {stroke_id!r} is not a stroke")
        stroke = obj.metadata.setdefault("stroke", {"points": []})
        existing = [_as_vec3(point) for point in stroke.get("points", [])]
        for raw_point in points:
            point = _as_vec3(raw_point)
            if not existing or _distance(existing[-1], point) >= min_distance:
                existing.append(point)
        max_points = int(stroke.get("max_points", self.performance_budget.get("max_stroke_points_per_object", 128)))
        if len(existing) > max_points:
            existing = _resample_points(existing, max_points)
        stroke["points"] = [list(point) for point in existing]
        obj.metadata["stroke"] = stroke
        self.record("draw_stroke_points", object=stroke_id, point_count=len(existing), min_distance=min_distance)

    def smooth_stroke(self, stroke_id: str, passes: int = 1) -> None:
        obj = self.object_by_id(stroke_id)
        stroke = obj.metadata.setdefault("stroke", {"points": []})
        points = [_as_vec3(point) for point in stroke.get("points", [])]
        for _ in range(max(0, passes)):
            points = _smooth_polyline(points)
        max_points = int(stroke.get("max_points", self.performance_budget.get("max_stroke_points_per_object", 128)))
        if len(points) > max_points:
            points = _resample_points(points, max_points)
        stroke["points"] = [list(point) for point in points]
        obj.metadata["stroke"] = stroke
        self.record("smooth_stroke", object=stroke_id, passes=passes, point_count=len(points))

    def smooth_grab_resize(self, object_id: str, target_scale: Vec3, smoothing: float = 0.35) -> None:
        obj = self.object_by_id(object_id)
        obj.transform.scale = _vlerp(obj.transform.scale, target_scale, smoothing)
        obj.metadata["last_smooth_resize"] = {"target_scale": list(target_scale), "smoothing": smoothing}
        self.record("smooth_grab_resize", object=object_id, target_scale=target_scale, smoothing=smoothing, result_scale=obj.transform.scale)

    def grab_move(self, object_id: str, hand_start: Vec3, hand_end: Vec3, smoothing: float = 1.0) -> None:
        obj = self.object_by_id(object_id)
        delta = _vmul(_vsub(hand_end, hand_start), max(0.0, min(1.0, smoothing)))
        obj.transform.position = _vadd(obj.transform.position, delta)
        self.record("grab_move", object=object_id, delta=delta, smoothing=smoothing)

    def set_material(
        self,
        object_id: str,
        base_color: tuple[float, float, float, float],
        shade: str = "matte",
        roughness: float = 0.72,
        metallic: float = 0.0,
        emission_strength: float = 0.0,
    ) -> None:
        obj = self.object_by_id(object_id)
        obj.metadata["material"] = {
            "base_color": list(_as_color(base_color)),
            "shade": shade,
            "roughness": max(0.0, min(1.0, roughness)),
            "metallic": max(0.0, min(1.0, metallic)),
            "emission_strength": max(0.0, emission_strength),
        }
        self.record("set_material", object=object_id, shade=shade, base_color=list(_as_color(base_color)))

    def program_behavior(self, behavior_id: str, target: str, behavior_type: str, params: dict[str, Any]) -> None:
        if behavior_type not in ALLOWED_BEHAVIOR_TYPES:
            raise ValueError(f"Unsupported safe behavior type: {behavior_type}")
        self.object_by_id(target)
        behavior = {"id": behavior_id, "target": target, "type": behavior_type, "params": params, "runtime": "safe_dataflow_v1"}
        self.behaviors.append(behavior)
        self.record("program_behavior", behavior=behavior_id, target=target, type=behavior_type)

    def evaluate_behaviors(self, time_sec: float) -> dict[str, Any]:
        preview: dict[str, Any] = {}
        for behavior in self.behaviors:
            obj = self.object_by_id(str(behavior["target"]))
            params = dict(behavior.get("params") or {})
            state = preview.setdefault(obj.id, {"position": list(obj.transform.position), "rotation": list(obj.transform.rotation), "scale": list(obj.transform.scale), "material": _object_material(obj)})
            if behavior["type"] == "spin":
                axis = str(params.get("axis", "z"))
                speed = float(params.get("degrees_per_second", 45.0))
                index = {"x": 0, "y": 1, "z": 2}.get(axis, 2)
                state["rotation"][index] = _r(float(state["rotation"][index]) + speed * time_sec)
            elif behavior["type"] == "bob":
                amplitude = float(params.get("amplitude", 0.2))
                frequency = float(params.get("frequency", 1.0))
                state["position"][2] = _r(float(state["position"][2]) + math.sin(time_sec * math.tau * frequency) * amplitude)
            elif behavior["type"] == "pulse_color":
                color_a = _as_color(params.get("color_a"), (0.4, 0.8, 1.0, 1.0))
                color_b = _as_color(params.get("color_b"), (1.0, 0.4, 0.8, 1.0))
                frequency = float(params.get("frequency", 1.0))
                mix = 0.5 + 0.5 * math.sin(time_sec * math.tau * frequency)
                state["material"]["base_color"] = [_r(color_a[i] + (color_b[i] - color_a[i]) * mix) for i in range(4)]
            elif behavior["type"] == "orbit":
                radius = float(params.get("radius", 1.0))
                speed = float(params.get("cycles_per_second", 0.25))
                center = _as_vec3(params.get("center", (0.0, 0.0, 0.0)))
                angle = time_sec * math.tau * speed
                state["position"][0] = _r(center[0] + math.cos(angle) * radius)
                state["position"][1] = _r(center[1] + math.sin(angle) * radius)
            elif behavior["type"] == "follow_path" and self.path_nodes:
                path_ids = list(params.get("path", []))
                nodes = [node for node in self.path_nodes if node.get("id") in path_ids] or self.path_nodes
                index = int(time_sec * float(params.get("nodes_per_second", 1.0))) % len(nodes)
                state["position"] = list(_as_vec3(nodes[index].get("position", (0, 0, 0))))
        return preview

    def performance_summary(self) -> dict[str, Any]:
        summaries = self.mesh_summaries()
        stroke_points = 0
        for obj in self.objects:
            if obj.kind == "stroke":
                stroke_points += len((obj.metadata.get("stroke") or {}).get("points", []))
        vertices = sum(item["vertex_count"] for item in summaries)
        faces = sum(item["face_count"] for item in summaries)
        grid_objects = [obj for obj in self.objects if (obj.metadata.get("grid") or {}).get("snapped")]
        batch_keys = {str((obj.metadata.get("grid") or {}).get("batch_key", obj.kind)) for obj in grid_objects}
        occupied_cells = self.grid_occupancy_summary()
        return {
            "object_count": len(self.objects),
            "stroke_object_count": sum(1 for obj in self.objects if obj.kind == "stroke"),
            "stroke_point_count": stroke_points,
            "vertex_count": vertices,
            "face_count": faces,
            "triangle_estimate": sum(len(_triangulate_faces(obj.world_mesh().faces)) for obj in self.objects),
            "editor_panel_count": len(self.editor_panels),
            "grid": self.grid_summary(),
            "grid_snapped_object_count": len(grid_objects),
            "grid_occupied_cell_count": occupied_cells["occupied_cell_count"],
            "grid_batch_count": len(batch_keys),
            "budget": self.performance_budget,
            "recommendations": [
                "batch stroke meshes by material shade",
                "prefer radial_segments <= 8 for VR paint",
                "resample dynamic strokes before export",
                "run behavior programs as dataflow updates, not arbitrary Python",
                "render the 3D grid as proximity-chunked lines, not one object per cell",
                "batch snapped grid fills by batch_key before runtime export",
            ],
        }

    def grid_summary(self) -> dict[str, Any]:
        x, y, z = self.grid.dimensions
        visible_lines = self.grid.line_count() if self.grid.enabled else 0
        return {
            "id": self.grid.id,
            "enabled": self.grid.enabled,
            "cell_size": self.grid.cell_size,
            "dimensions": [x, y, z],
            "proximity_radius": self.grid.proximity_radius,
            "major_every": self.grid.major_every,
            "visible_line_count": visible_lines,
            "render_strategy": self.grid.render_strategy,
            "snap_enabled": self.grid.snap_enabled,
            "integrity": "persistent_lattice_origin_cell_size_dimensions",
        }

    def grid_occupancy_summary(self) -> dict[str, Any]:
        occupied: set[tuple[int, int, int]] = set()
        overlaps = 0
        for obj in self.objects:
            grid = obj.metadata.get("grid") or {}
            if not grid.get("snapped"):
                continue
            cell = tuple(int(value) for value in grid.get("cell", (0, 0, 0)))
            fill = _as_int3(grid.get("fill_cells", (1, 1, 1)))
            for ix in range(cell[0], cell[0] + fill[0]):
                for iy in range(cell[1], cell[1] + fill[1]):
                    for iz in range(cell[2], cell[2] + fill[2]):
                        coord = (ix, iy, iz)
                        if coord in occupied:
                            overlaps += 1
                        occupied.add(coord)
        return {
            "occupied_cell_count": len(occupied),
            "overlap_count": overlaps,
            "max_occupied_cell_budget": int(self.performance_budget.get("max_grid_occupied_cells", 4096)),
        }

    def validate_scene(self) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        def issue(target: list[dict[str, Any]], code: str, message: str, path: str) -> None:
            target.append({"code": code, "message": message, "path": path})

        object_ids: set[str] = set()
        socket_ids: dict[str, set[str]] = {}
        for index, obj in enumerate(self.objects):
            path = f"objects[{index}]"
            if not obj.id:
                issue(errors, "object_id_empty", "Object id is required.", path)
            if obj.id in object_ids:
                issue(errors, "object_id_duplicate", f"Duplicate object id {obj.id!r}.", path)
            object_ids.add(obj.id)
            if obj.kind not in {"cube", "floor", "wall", "sphere", "cylinder", "capsule", "stroke"}:
                issue(errors, "object_kind_unknown", f"Unsupported object kind {obj.kind!r}.", path)
            if not (_finite_vec(obj.transform.position) and _finite_vec(obj.transform.rotation) and _finite_vec(obj.transform.scale)):
                issue(errors, "transform_non_finite", "Transform contains non-finite values.", path)
            if any(value <= 0 for value in obj.transform.scale):
                issue(errors, "scale_non_positive", "Object scale must stay positive.", path)

            material = _object_material(obj)
            if material["shade"] not in ALLOWED_MATERIAL_SHADES:
                issue(warnings, "material_shade_unknown", f"Unknown material shade {material['shade']!r}; exporters will preserve it as metadata.", f"{path}.metadata.material")
            if not all(0.0 <= value <= 1.0 for value in material["base_color"]):
                issue(errors, "material_color_range", "Material base color must be RGBA values in 0..1.", f"{path}.metadata.material.base_color")

            local_socket_ids: set[str] = set()
            for socket_index, socket in enumerate(obj.sockets):
                socket_id = str(socket.get("id", ""))
                socket_path = f"{path}.sockets[{socket_index}]"
                if not socket_id:
                    issue(errors, "socket_id_empty", "Socket id is required.", socket_path)
                if socket_id in local_socket_ids:
                    issue(errors, "socket_id_duplicate", f"Duplicate socket id {socket_id!r} on object {obj.id!r}.", socket_path)
                local_socket_ids.add(socket_id)
                if not _finite_vec(_as_vec3(socket.get("position", (0, 0, 0)))):
                    issue(errors, "socket_position_non_finite", "Socket position contains non-finite values.", socket_path)
            socket_ids[obj.id] = local_socket_ids

            if obj.kind == "stroke":
                stroke = obj.metadata.get("stroke") or {}
                points = stroke.get("points", [])
                radial_segments = int(stroke.get("radial_segments", obj.params.get("radial_segments", 6)))
                max_points = int(stroke.get("max_points", obj.params.get("max_points", 128)))
                budget_points = int(self.performance_budget.get("max_stroke_points_per_object", 128))
                budget_segments = int(self.performance_budget.get("max_stroke_radial_segments", 8))
                if len(points) < 2:
                    issue(errors, "stroke_point_count_low", "Stroke objects need at least two points.", f"{path}.metadata.stroke.points")
                if len(points) > budget_points or max_points > budget_points:
                    issue(errors, "stroke_point_budget_exceeded", "Stroke point count exceeds the scene performance budget.", f"{path}.metadata.stroke")
                if radial_segments > budget_segments:
                    issue(errors, "stroke_radial_budget_exceeded", "Stroke radial segments exceed the scene performance budget.", f"{path}.metadata.stroke.radial_segments")

            try:
                mesh = obj.world_mesh()
            except Exception as exc:
                issue(errors, "mesh_generation_failed", f"Mesh generation failed: {exc}", path)
                continue
            if not mesh.vertices or not mesh.faces:
                issue(errors, "mesh_empty", "Object generated empty mesh data.", path)
                continue
            for vertex_index, vertex in enumerate(mesh.vertices[:2000]):
                if not _finite_vec(vertex):
                    issue(errors, "mesh_vertex_non_finite", "Mesh contains a non-finite vertex.", f"{path}.mesh.vertices[{vertex_index}]")
                    break
            for face_index, face in enumerate(mesh.faces):
                if len(face) < 3:
                    issue(errors, "mesh_face_invalid", "Mesh face must contain at least three indices.", f"{path}.mesh.faces[{face_index}]")
                    break
                if any(vertex_index < 0 or vertex_index >= len(mesh.vertices) for vertex_index in face):
                    issue(errors, "mesh_face_index_out_of_range", "Mesh face references a missing vertex.", f"{path}.mesh.faces[{face_index}]")
                    break

        connection_ids: set[str] = set()
        for index, connection in enumerate(self.connections):
            path = f"connections[{index}]"
            connection_id = str(connection.get("id", ""))
            if not connection_id:
                issue(errors, "connection_id_empty", "Connection id is required.", path)
            if connection_id in connection_ids:
                issue(errors, "connection_id_duplicate", f"Duplicate connection id {connection_id!r}.", path)
            connection_ids.add(connection_id)
            for side in ("from", "to"):
                endpoint = connection.get(side) or {}
                object_id = str(endpoint.get("object", ""))
                socket_id = str(endpoint.get("socket", ""))
                if object_id not in object_ids:
                    issue(errors, "connection_object_missing", f"Connection endpoint references missing object {object_id!r}.", f"{path}.{side}")
                elif socket_id not in socket_ids.get(object_id, set()):
                    issue(errors, "connection_socket_missing", f"Connection endpoint references missing socket {socket_id!r} on {object_id!r}.", f"{path}.{side}")

        path_ids = {str(node.get("id", "")) for node in self.path_nodes}
        if "" in path_ids:
            issue(errors, "path_node_id_empty", "Path node id is required.", "path_nodes")
        if len(path_ids) != len(self.path_nodes):
            issue(errors, "path_node_id_duplicate", "Path node ids must be unique.", "path_nodes")
        for index, node in enumerate(self.path_nodes):
            path = f"path_nodes[{index}]"
            if not _finite_vec(_as_vec3(node.get("position", (0, 0, 0)))):
                issue(errors, "path_node_position_non_finite", "Path node position contains non-finite values.", path)
            for link in node.get("links", []):
                if str(link) not in path_ids:
                    issue(errors, "path_node_link_missing", f"Path node link references missing node {link!r}.", path)

        behavior_ids: set[str] = set()
        for index, behavior in enumerate(self.behaviors):
            path = f"behaviors[{index}]"
            behavior_id = str(behavior.get("id", ""))
            behavior_type = str(behavior.get("type", ""))
            target = str(behavior.get("target", ""))
            if not behavior_id:
                issue(errors, "behavior_id_empty", "Behavior id is required.", path)
            if behavior_id in behavior_ids:
                issue(errors, "behavior_id_duplicate", f"Duplicate behavior id {behavior_id!r}.", path)
            behavior_ids.add(behavior_id)
            if target not in object_ids:
                issue(errors, "behavior_target_missing", f"Behavior targets missing object {target!r}.", path)
            if behavior_type not in ALLOWED_BEHAVIOR_TYPES:
                issue(errors, "behavior_type_unknown", f"Unsupported behavior type {behavior_type!r}.", path)
            if behavior_type == "follow_path":
                for node_id in (behavior.get("params") or {}).get("path", []):
                    if str(node_id) not in path_ids:
                        issue(errors, "behavior_path_node_missing", f"Follow-path behavior references missing node {node_id!r}.", path)

        panel_ids: set[str] = set()
        for index, panel in enumerate(self.editor_panels):
            path = f"editor_panels[{index}]"
            if not panel.id:
                issue(errors, "panel_id_empty", "Editor panel id is required.", path)
            if panel.id in panel_ids:
                issue(errors, "panel_id_duplicate", f"Duplicate editor panel id {panel.id!r}.", path)
            panel_ids.add(panel.id)
            if panel.size[0] <= 0 or panel.size[1] <= 0:
                issue(errors, "panel_size_invalid", "Editor panel size must stay positive.", path)
            if not (_finite_vec(panel.transform.position) and _finite_vec(panel.transform.rotation)):
                issue(errors, "panel_transform_non_finite", "Editor panel transform contains non-finite values.", path)
            if not 0.0 <= panel.opacity <= 1.0:
                issue(errors, "panel_opacity_range", "Editor panel opacity must be in 0..1.", path)

        if self.grid.enabled:
            if self.grid.cell_size <= 0:
                issue(errors, "grid_cell_size_invalid", "3D grid cell size must be positive.", "grid.cell_size")
            if any(value <= 0 for value in self.grid.dimensions):
                issue(errors, "grid_dimensions_invalid", "3D grid dimensions must be positive.", "grid.dimensions")
            if not _finite_vec(self.grid.origin):
                issue(errors, "grid_origin_non_finite", "3D grid origin contains non-finite values.", "grid.origin")
            if self.grid.line_count() > int(self.performance_budget.get("max_grid_visible_lines", 2400)):
                issue(warnings, "grid_line_budget_high", "3D grid visible line count is high; shrink proximity or dimensions.", "grid")
            occupancy = self.grid_occupancy_summary()
            if occupancy["occupied_cell_count"] > occupancy["max_occupied_cell_budget"]:
                issue(warnings, "grid_occupied_cell_budget_high", "Grid occupied-cell count is high for live VR editing.", "grid")
            if occupancy["overlap_count"]:
                issue(warnings, "grid_cell_overlap", "Multiple snapped objects occupy the same 3D grid cells.", "grid")

        for obj in self.objects:
            grid = obj.metadata.get("grid") or {}
            if not grid.get("snapped"):
                continue
            cell = tuple(int(value) for value in grid.get("cell", (0, 0, 0)))
            fill = _as_int3(grid.get("fill_cells", (1, 1, 1)))
            expected = self.grid.cell_center(cell, fill)
            if _distance(obj.transform.position, expected) > max(0.0001, self.grid.cell_size * 0.01):
                issue(errors, "grid_snap_position_mismatch", f"Snapped object {obj.id!r} is not at the persisted grid cell center.", f"objects.{obj.id}.metadata.grid")

        expected_indices = list(range(len(self.operation_history)))
        observed_indices = [item.get("index") for item in self.operation_history]
        if observed_indices != expected_indices:
            issue(warnings, "operation_history_indices_non_sequential", "Operation history indices are not sequential.", "operation_history")

        performance = self.performance_summary()
        if performance["triangle_estimate"] > 50000:
            issue(warnings, "triangle_budget_high", "Triangle estimate is high for standalone VR editing.", "performance.triangle_estimate")

        return {
            "ok": not errors,
            "schema": SCHEMA_VERSION,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "metrics": performance,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "units": self.units,
            "objects": [obj.to_dict() for obj in self.objects],
            "connections": self.connections,
            "path_nodes": self.path_nodes,
            "animations": self.animations,
            "behaviors": self.behaviors,
            "operation_history": self.operation_history,
            "performance_budget": self.performance_budget,
            "editor_panels": [panel.to_dict() for panel in self.editor_panels],
            "grid": self.grid.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuilderScene":
        if data.get("schema") not in SUPPORTED_SCHEMAS:
            raise ValueError(f"Unsupported Panda XR scene schema: {data.get('schema')!r}")
        return cls(
            name=str(data.get("name", "Panda XR VR Builder Scene")),
            units=str(data.get("units", "meters")),
            objects=[BuilderObject.from_dict(item) for item in data.get("objects", [])],
            connections=list(data.get("connections", [])),
            path_nodes=list(data.get("path_nodes", [])),
            animations=list(data.get("animations", [])),
            behaviors=list(data.get("behaviors", [])),
            operation_history=list(data.get("operation_history", [])),
            performance_budget=dict(data.get("performance_budget", {})) or {
                "max_stroke_points_per_object": 128,
                "max_stroke_radial_segments": 8,
                "target_frame_rate": 90,
                "recommended_draw_call_groups": 48,
                "max_grid_visible_lines": 2400,
                "max_grid_occupied_cells": 4096,
            },
            editor_panels=[EditorPanel.from_dict(item) for item in data.get("editor_panels", [])],
            grid=Grid3DSettings.from_dict(data.get("grid", {})),
            metadata=dict(data.get("metadata", {})),
        )

    def save_manifest(self, path: Path) -> Path:
        _write_text_atomic(path, json.dumps(self.to_dict(), indent=2, sort_keys=True))
        return path

    @classmethod
    def load_manifest(cls, path: Path) -> "BuilderScene":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def mesh_summaries(self) -> list[dict[str, Any]]:
        summaries = []
        for obj in self.objects:
            mesh = obj.world_mesh()
            summaries.append({
                "id": obj.id,
                "kind": obj.kind,
                "vertex_count": len(mesh.vertices),
                "face_count": len(mesh.faces),
                "bounds": mesh.bounds(),
                "checksum": mesh.checksum(),
                "control_point_count": len(obj.control_points),
                "collision": obj.collision,
                "sockets": obj.sockets,
                "material": _object_material(obj),
                "grid": obj.metadata.get("grid"),
                "smoothing": obj.metadata.get("smoothing"),
            })
        return summaries

    def export_obj(self, path: Path) -> Path:
        lines = ["# GPTOOL Panda XR VR Builder export", f"# scene: {self.name}", f"# units: {self.units}"]
        offset = 1
        for obj in self.objects:
            mesh = obj.world_mesh()
            lines.append(f"o {obj.id}")
            for vertex in mesh.vertices:
                lines.append(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}")
            for face in mesh.faces:
                lines.append("f " + " ".join(str(index + offset) for index in face))
            offset += len(mesh.vertices)
        _write_text_atomic(path, "\n".join(lines) + "\n")
        return path

    def export_metadata(self, path: Path, geometry: str | None = None) -> Path:
        payload = {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "units": self.units,
            "object_count": len(self.objects),
            "connection_count": len(self.connections),
            "path_node_count": len(self.path_nodes),
            "animation_count": len(self.animations),
            "behavior_count": len(self.behaviors),
            "operation_count": len(self.operation_history),
            "objects": self.mesh_summaries(),
            "connections": self.connections,
            "path_nodes": self.path_nodes,
            "animations": self.animations,
            "behaviors": self.behaviors,
            "operation_history": self.operation_history,
            "behavior_preview_t1": self.evaluate_behaviors(1.0),
            "editor_panels": [panel.to_dict() for panel in self.editor_panels],
            "grid": self.grid.to_dict(),
            "grid_occupancy": self.grid_occupancy_summary(),
            "performance": self.performance_summary(),
            "scene_metadata": self.metadata,
        }
        if geometry:
            payload["geometry"] = geometry
        _write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True))
        return path

    def _build_gltf(self, bin_uri: str | None) -> tuple[dict[str, Any], bytes]:
        binary = bytearray()
        buffer_views: list[dict[str, Any]] = []
        accessors: list[dict[str, Any]] = []
        meshes: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        materials: list[dict[str, Any]] = []

        def add_view(data: bytes, target: int) -> int:
            while len(binary) % 4:
                binary.append(0)
            offset = len(binary)
            binary.extend(data)
            while len(binary) % 4:
                binary.append(0)
            buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
            return len(buffer_views) - 1

        for obj in self.objects:
            mesh = obj.world_mesh()
            triangles = _triangulate_faces(mesh.faces)
            pos_view = add_view(b"".join(struct.pack("<fff", *vertex) for vertex in mesh.vertices), 34962)
            idx_view = add_view(b"".join(struct.pack("<I", index) for tri in triangles for index in tri), 34963)
            bounds = mesh.bounds()
            pos_accessor = len(accessors)
            accessors.append({"bufferView": pos_view, "componentType": 5126, "count": len(mesh.vertices), "type": "VEC3", "min": list(bounds["min"]), "max": list(bounds["max"])})
            idx_accessor = len(accessors)
            accessors.append({"bufferView": idx_view, "componentType": 5125, "count": len(triangles) * 3, "type": "SCALAR"})
            mesh_index = len(meshes)
            material = _object_material(obj)
            material_index = len(materials)
            gltf_material: dict[str, Any] = {
                "name": f"{obj.id}_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(material["base_color"]),
                    "metallicFactor": material["metallic"],
                    "roughnessFactor": material["roughness"],
                },
                "extras": material,
            }
            if material["emission_strength"] > 0:
                color = material["base_color"]
                gltf_material["emissiveFactor"] = [_r(color[0] * material["emission_strength"]), _r(color[1] * material["emission_strength"]), _r(color[2] * material["emission_strength"])]
            materials.append(gltf_material)
            meshes.append({
                "name": obj.id,
                "primitives": [{"attributes": {"POSITION": pos_accessor}, "indices": idx_accessor, "material": material_index, "mode": 4}],
                "extras": {
                    "builder_object": obj.to_dict(),
                    "deformed_checksum": mesh.checksum(),
                    "triangle_count": len(triangles),
                    "material": material,
                },
            })
            nodes.append({"name": obj.id, "mesh": mesh_index})

        gltf = {
            "asset": {"version": "2.0", "generator": "GPTOOL Panda XR VR Builder extension"},
            "scene": 0,
            "scenes": [{
                "name": self.name,
                "nodes": list(range(len(nodes))),
                "extras": {
                    "schema": SCHEMA_VERSION,
                    "units": self.units,
                    "connections": self.connections,
                    "path_nodes": self.path_nodes,
                    "animations": self.animations,
                    "behaviors": self.behaviors,
                    "operation_history": self.operation_history,
                    "behavior_preview_t1": self.evaluate_behaviors(1.0),
                    "editor_panels": [panel.to_dict() for panel in self.editor_panels],
                    "grid": self.grid.to_dict(),
                    "grid_occupancy": self.grid_occupancy_summary(),
                    "performance": self.performance_summary(),
                    "scene_metadata": self.metadata,
                },
            }],
            "nodes": nodes,
            "meshes": meshes,
            "materials": materials,
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": buffer_views,
            "accessors": accessors,
        }
        if bin_uri:
            gltf["buffers"][0]["uri"] = bin_uri
        return gltf, bytes(binary)

    def export_gltf(self, directory: Path) -> dict[str, Path]:
        gltf, binary = self._build_gltf("scene.bin")
        gltf_path = directory / "scene.gltf"
        bin_path = directory / "scene.bin"
        _write_bytes_atomic(bin_path, binary)
        _write_text_atomic(gltf_path, json.dumps(gltf, indent=2, sort_keys=True))
        return {"gltf": gltf_path, "bin": bin_path}

    def export_glb(self, path: Path) -> Path:
        gltf, binary = self._build_gltf(None)
        json_chunk = _pad4(json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode("utf-8"), b" ")
        bin_chunk = _pad4(binary, b"\x00")
        total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
        data = bytearray()
        data.extend(struct.pack("<4sII", b"glTF", 2, total))
        data.extend(struct.pack("<I4s", len(json_chunk), b"JSON"))
        data.extend(json_chunk)
        data.extend(struct.pack("<I4s", len(bin_chunk), b"BIN\x00"))
        data.extend(bin_chunk)
        _write_bytes_atomic(path, bytes(data))
        return path

    def export_game_ready(self, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        manifest = self.save_manifest(directory / "scene.manifest.json")
        obj = self.export_obj(directory / "scene.obj")
        metadata = self.export_metadata(directory / "scene.metadata.json", "scene.obj")
        gltf = self.export_gltf(directory)
        glb = self.export_glb(directory / "scene.glb")
        return {"manifest": manifest, "obj": obj, "metadata": metadata, "gltf": gltf["gltf"], "bin": gltf["bin"], "glb": glb}


def make_box_mesh(width: float, depth: float, height: float, subdivisions: int = 1) -> MeshData:
    subdivisions = max(1, int(subdivisions))
    hx, hy, hz = width / 2, depth / 2, height / 2
    vertices: list[Vec3] = []
    faces: list[Face] = []

    def add_face(axis: str, sign: float) -> None:
        start = len(vertices)
        for row in range(subdivisions + 1):
            for col in range(subdivisions + 1):
                if axis == "x":
                    vertex = (sign * hx, -hy + col * depth / subdivisions, -hz + row * height / subdivisions)
                elif axis == "y":
                    vertex = (-hx + col * width / subdivisions, sign * hy, -hz + row * height / subdivisions)
                else:
                    vertex = (-hx + col * width / subdivisions, -hy + row * depth / subdivisions, sign * hz)
                vertices.append(tuple(_r(v) for v in vertex))  # type: ignore[arg-type]
        for row in range(subdivisions):
            for col in range(subdivisions):
                i = start + row * (subdivisions + 1) + col
                faces.append((i, i + 1, i + subdivisions + 2, i + subdivisions + 1) if sign > 0 else (i, i + subdivisions + 1, i + subdivisions + 2, i + 1))

    for axis, sign in (("z", 1), ("z", -1), ("x", 1), ("x", -1), ("y", 1), ("y", -1)):
        add_face(axis, sign)
    return MeshData(vertices, faces)


def _resample_points(points: list[Vec3], max_points: int) -> list[Vec3]:
    if len(points) <= max_points or max_points <= 1:
        return points[:max_points]
    result = [points[0]]
    step = (len(points) - 1) / (max_points - 1)
    for index in range(1, max_points - 1):
        result.append(points[int(round(index * step))])
    result.append(points[-1])
    return result


def _smooth_polyline(points: list[Vec3]) -> list[Vec3]:
    if len(points) < 3:
        return points
    smoothed = [points[0]]
    for index in range(len(points) - 1):
        a = points[index]
        b = points[index + 1]
        smoothed.append(_vlerp(a, b, 0.25))
        smoothed.append(_vlerp(a, b, 0.75))
    smoothed.append(points[-1])
    return smoothed


def make_stroke_mesh(points: list[Vec3], radius: float = 0.04, radial_segments: int = 6, max_points: int = 128) -> MeshData:
    points = _resample_points([_as_vec3(point) for point in points], max(2, max_points))
    radial_segments = max(3, min(12, radial_segments))
    radius = max(0.002, radius)
    if len(points) < 2:
        return MeshData([], [])

    vertices: list[Vec3] = []
    faces: list[Face] = []
    up = (0.0, 0.0, 1.0)
    side_fallback = (1.0, 0.0, 0.0)
    for index, point in enumerate(points):
        if index == 0:
            tangent = _vsub(points[1], point)
        elif index == len(points) - 1:
            tangent = _vsub(point, points[index - 1])
        else:
            tangent = _vsub(points[index + 1], points[index - 1])
        tangent = _vnorm(tangent, (0.0, 1.0, 0.0))
        normal = _vcross(tangent, up)
        if _vlen(normal) < 1e-5:
            normal = _vcross(tangent, side_fallback)
        normal = _vnorm(normal, side_fallback)
        binormal = _vnorm(_vcross(tangent, normal), up)
        for segment in range(radial_segments):
            angle = math.tau * segment / radial_segments
            offset = _vadd(_vmul(normal, math.cos(angle) * radius), _vmul(binormal, math.sin(angle) * radius))
            vertices.append(_vadd(point, offset))

    for index in range(len(points) - 1):
        base = index * radial_segments
        next_base = (index + 1) * radial_segments
        for segment in range(radial_segments):
            faces.append((
                base + segment,
                base + ((segment + 1) % radial_segments),
                next_base + ((segment + 1) % radial_segments),
                next_base + segment,
            ))
    faces.append(tuple(reversed(range(radial_segments))))
    last_base = (len(points) - 1) * radial_segments
    faces.append(tuple(last_base + segment for segment in range(radial_segments)))
    return MeshData(vertices, faces)


def make_sphere_mesh(radius: float, rings: int = 12, segments: int = 16) -> MeshData:
    rings, segments = max(3, rings), max(6, segments)
    vertices: list[Vec3] = [(0.0, 0.0, _r(radius))]
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        z, rr = radius * math.cos(theta), radius * math.sin(theta)
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_r(rr * math.cos(phi)), _r(rr * math.sin(phi)), _r(z)))
    vertices.append((0.0, 0.0, _r(-radius)))
    return _ring_faces(vertices, rings, segments)


def _ring_faces(vertices: list[Vec3], rings: int, segments: int) -> MeshData:
    faces: list[Face] = []
    bottom = len(vertices) - 1
    first = 1
    last = 1 + (rings - 2) * segments
    for segment in range(segments):
        faces.append((0, first + segment, first + ((segment + 1) % segments)))
    for ring in range(rings - 2):
        row = 1 + ring * segments
        next_row = row + segments
        for segment in range(segments):
            faces.append((row + segment, next_row + segment, next_row + ((segment + 1) % segments), row + ((segment + 1) % segments)))
    for segment in range(segments):
        faces.append((last + ((segment + 1) % segments), last + segment, bottom))
    return MeshData(vertices, faces)


def make_cylinder_mesh(radius: float, height: float, segments: int = 16, height_segments: int = 1) -> MeshData:
    segments, height_segments = max(6, segments), max(1, height_segments)
    half = height / 2
    vertices: list[Vec3] = []
    for row in range(height_segments + 1):
        z = -half + height * row / height_segments
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_r(radius * math.cos(phi)), _r(radius * math.sin(phi)), _r(z)))
    bottom_center, top_center = len(vertices), len(vertices) + 1
    vertices.extend([(0.0, 0.0, _r(-half)), (0.0, 0.0, _r(half))])
    faces: list[Face] = []
    for row in range(height_segments):
        base, next_base = row * segments, (row + 1) * segments
        for segment in range(segments):
            faces.append((base + segment, base + ((segment + 1) % segments), next_base + ((segment + 1) % segments), next_base + segment))
    for segment in range(segments):
        faces.append((bottom_center, (segment + 1) % segments, segment))
        top_base = height_segments * segments
        faces.append((top_center, top_base + segment, top_base + ((segment + 1) % segments)))
    return MeshData(vertices, faces)


def make_capsule_mesh(radius: float, cylinder_height: float, segments: int = 16, hemisphere_rings: int = 6) -> MeshData:
    segments, hemisphere_rings = max(6, segments), max(2, hemisphere_rings)
    total_rings = hemisphere_rings * 2
    vertices: list[Vec3] = [(0.0, 0.0, _r(cylinder_height / 2 + radius))]
    for ring in range(1, total_rings):
        theta = math.pi * ring / total_rings
        rr = radius * math.sin(theta)
        local_z = radius * math.cos(theta)
        z = local_z + (cylinder_height / 2 if theta <= math.pi / 2 else -cylinder_height / 2)
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_r(rr * math.cos(phi)), _r(rr * math.sin(phi)), _r(z)))
    vertices.append((0.0, 0.0, _r(-cylinder_height / 2 - radius)))
    return _ring_faces(vertices, total_rings, segments)


def _default_socket(socket_id: str, position: Vec3, normal: Vec3) -> dict[str, Any]:
    return {"id": socket_id, "position": list(position), "normal": list(normal)}


def create_vr_editing_proof_scene() -> BuilderScene:
    scene = BuilderScene(name="GPTOOL Panda XR VR Builder Proof", metadata={"plugin": "panda_xr_vr_builder", "proof": True})
    scene.configure_grid_3d(origin=(-2.75, -1.85, 0.0), cell_size=0.25, dimensions=(24, 14, 10), proximity_radius=3.75, major_every=4, opacity=0.18, snap_enabled=True)
    scene.add_editor_panel(
        "panel_tools",
        "Create Tools",
        (-1.55, -1.72, 2.25),
        rotation=(68.0, 0.0, 0.0),
        content={"mode": "create", "active_tool": "grid_block", "brush": "smooth_cube"},
        controls=[{"type": "button", "id": "cube"}, {"type": "button", "id": "sphere"}, {"type": "button", "id": "stroke"}],
    )
    scene.add_editor_panel(
        "panel_grid",
        "3D Grid",
        (0.15, -1.82, 2.38),
        rotation=(62.0, 0.0, 0.0),
        content={"cell_size": 0.25, "snap": True, "fill_mode": "cell_volume", "proximity_radius": 3.75},
        controls=[{"type": "slider", "id": "cell_size", "min": 0.1, "max": 1.0}, {"type": "toggle", "id": "snap"}],
    )
    scene.add_editor_panel(
        "panel_materials",
        "Materials",
        (1.85, -1.72, 2.18),
        rotation=(58.0, 0.0, -8.0),
        content={"shade": "satin", "palette": ["skin", "hair", "clothes", "grid_glass"]},
        controls=[{"type": "swatch", "id": "base_color"}, {"type": "slider", "id": "roughness"}],
    )
    scene.move_editor_panel("panel_grid", (0.12, -1.78, 2.34), rotation=(64.0, 0.0, 0.0), smoothing=0.5)
    scene.create_object(BuilderObject("floor_01", "floor", {"width": 7.0, "depth": 5.0, "thickness": 0.12, "subdivisions": 2}, Transform(position=(0.0, 0.0, -0.06)), collision={"type": "box", "deformed": False}, sockets=[_default_socket("north_wall", (0, 2.5, 0.06), (0, 1, 0))]))
    scene.create_object(BuilderObject("wall_01", "wall", {"width": 4.0, "height": 2.4, "thickness": 0.16, "subdivisions": 2}, Transform(position=(0.0, 2.5, 1.2)), collision={"type": "box", "deformed": False}, sockets=[_default_socket("floor_mount", (0, -0.08, -1.2), (0, -1, 0))]))
    scene.create_object(BuilderObject("cube_01", "cube", {"size": 1.2, "subdivisions": 4}, Transform(position=(-1.25, -0.2, 0.65)), collision={"type": "box", "deformed": True}, sockets=[_default_socket("top", (0, 0, 0.8), (0, 0, 1))]))
    scene.create_object(BuilderObject("sphere_01", "sphere", {"radius": 0.62, "rings": 12, "segments": 18}, Transform(position=(1.05, -0.25, 0.85)), collision={"type": "sphere", "deformed": True}, sockets=[_default_socket("left", (-0.62, 0, 0), (-1, 0, 0))]))
    scene.create_object(BuilderObject("cylinder_01", "cylinder", {"radius": 0.34, "height": 1.5, "segments": 18, "height_segments": 3}, Transform(position=(2.35, 0.55, 0.85)), collision={"type": "cylinder", "deformed": True}, sockets=[_default_socket("top", (0, 0, 0.75), (0, 0, 1))]))
    scene.create_object(BuilderObject("capsule_01", "capsule", {"radius": 0.28, "cylinder_height": 0.9, "segments": 18, "hemisphere_rings": 5}, Transform(position=(2.35, 1.55, 0.95)), collision={"type": "capsule", "deformed": True}, sockets=[_default_socket("bottom", (0, 0, -0.73), (0, 0, -1))]))
    scene.begin_stroke("hand_light_ribbon_01", color=(0.1, 0.72, 1.0, 1.0), radius=0.045, shade="emissive", radial_segments=6, max_points=96)
    ribbon_points = []
    for index in range(48):
        t = index / 47.0
        angle = -1.35 + t * 2.7
        ribbon_points.append((_r(math.cos(angle) * 1.6), _r(-1.15 + math.sin(angle) * 0.55), _r(1.15 + math.sin(t * math.tau * 2.0) * 0.22)))
    scene.draw_stroke_points("hand_light_ribbon_01", ribbon_points, min_distance=0.02)
    scene.smooth_stroke("hand_light_ribbon_01", passes=1)
    scene.grab_move("hand_light_ribbon_01", (0.0, -1.15, 1.15), (0.15, -1.0, 1.25), smoothing=0.85)
    scene.smooth_grab_resize("hand_light_ribbon_01", (1.15, 1.15, 1.15), smoothing=0.5)
    scene.set_material("floor_01", (0.42, 0.43, 0.45, 1.0), shade="matte", roughness=0.82)
    scene.set_material("wall_01", (0.34, 0.37, 0.40, 1.0), shade="matte", roughness=0.78)
    scene.set_material("cube_01", (0.95, 0.52, 0.22, 1.0), shade="satin", roughness=0.44)
    scene.set_material("sphere_01", (0.32, 0.82, 0.96, 1.0), shade="gloss", roughness=0.28)
    scene.set_object_smoothing("cube_01", 0.45, edge_preserve=True)
    scene.set_object_smoothing("sphere_01", 0.82, edge_preserve=False)
    scene.set_object_smoothing("cylinder_01", 0.62, edge_preserve=True)
    scene.set_object_smoothing("capsule_01", 0.72, edge_preserve=False)
    scene.two_hand_resize("cube_01", (-0.6, 0, 0), (0.6, 0, 0), (-0.85, 0, 0), (0.85, 0, 0))
    scene.squeeze_morph("sphere_01", (0.9, -0.4, 1.15), (1.35, -0.1, 0.85), amount=0.35, radius=0.75)
    scene.two_hand_twist("cylinder_01", (2.0, 0.2, 0.9), (2.7, 0.2, 0.9), (2.05, 0.05, 0.9), (2.68, 0.55, 0.9))
    scene.squeeze_morph("capsule_01", (2.2, 1.45, 1.3), (2.5, 1.65, 1.1), amount=0.25, radius=0.55)
    scene.connect_sockets("floor_to_wall", "floor_01", "north_wall", "wall_01", "floor_mount")
    scene.connect_sockets("cube_to_sphere", "cube_01", "top", "sphere_01", "left")
    scene.connect_sockets("cylinder_to_capsule", "cylinder_01", "top", "capsule_01", "bottom")
    scene.add_path_node("path_start", (-2.5, -1.7, 0.02), ["path_mid"])
    scene.add_path_node("path_mid", (0.0, -1.6, 0.02), ["path_start", "path_end"])
    scene.add_path_node("path_end", (2.4, 0.95, 0.02), ["path_mid"])
    scene.animations.append({"id": "sphere_hover_test", "target": "sphere_01", "property": "transform.position.z", "keyframes": [{"time": 0.0, "value": 0.85}, {"time": 1.0, "value": 1.1}]})
    scene.program_behavior("stroke_color_pulse", "hand_light_ribbon_01", "pulse_color", {"color_a": [0.1, 0.72, 1.0, 1.0], "color_b": [1.0, 0.28, 0.85, 1.0], "frequency": 0.5})
    scene.program_behavior("sphere_live_bob", "sphere_01", "bob", {"amplitude": 0.16, "frequency": 0.65})
    scene.program_behavior("cylinder_spin", "cylinder_01", "spin", {"axis": "z", "degrees_per_second": 36.0})
    scene.program_behavior("capsule_path_follow", "capsule_01", "follow_path", {"path": ["path_start", "path_mid", "path_end"], "nodes_per_second": 0.5})
    scene.create_grid_block("grid_art_core", (9, 2, 2), (2, 2, 2), (0.96, 0.22, 0.36, 1.0), snap_group="pixel_room")
    scene.create_grid_block("grid_art_left", (7, 3, 3), (2, 1, 1), (0.22, 0.86, 1.0, 1.0), snap_group="pixel_room")
    scene.create_grid_block("grid_art_right", (11, 3, 3), (2, 1, 1), (0.22, 0.86, 1.0, 1.0), snap_group="pixel_room")
    scene.create_grid_block("grid_art_top", (10, 3, 4), (1, 1, 2), (1.0, 0.9, 0.26, 1.0), snap_group="pixel_room")
    scene.metadata["editor_mode"] = {
        "style": "augmented_reality_world_editor",
        "grid_editing": "persistent_resizable_3d_grid_with_snap_fill",
        "panel_placement": "world_locked_moveable_panels",
        "connected_object_performance": "batch snapped fills by grid batch_key",
    }
    return scene


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_export_bundle(exports: dict[str, Path]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def issue(target: list[dict[str, Any]], code: str, message: str, path: str) -> None:
        target.append({"code": code, "message": message, "path": path})

    required = ("manifest", "obj", "metadata", "gltf", "bin", "glb")
    for key in required:
        path = Path(exports[key]) if key in exports else None
        if path is None or not path.exists():
            issue(errors, "export_missing", f"Missing export file for {key}.", key)
        elif path.stat().st_size <= 0:
            issue(errors, "export_empty", f"Export file is empty for {key}.", key)
    if errors:
        return {"ok": False, "error_count": len(errors), "warning_count": len(warnings), "errors": errors, "warnings": warnings}

    manifest = json.loads(Path(exports["manifest"]).read_text(encoding="utf-8"))
    metadata = json.loads(Path(exports["metadata"]).read_text(encoding="utf-8"))
    gltf = json.loads(Path(exports["gltf"]).read_text(encoding="utf-8"))
    bin_bytes = Path(exports["bin"]).read_bytes()
    glb_bytes = Path(exports["glb"]).read_bytes()

    if manifest.get("schema") not in SUPPORTED_SCHEMAS:
        issue(errors, "manifest_schema_invalid", "Manifest schema is not supported.", "manifest.schema")
    if metadata.get("schema") not in SUPPORTED_SCHEMAS:
        issue(errors, "metadata_schema_invalid", "Metadata schema is not supported.", "metadata.schema")
    if gltf.get("asset", {}).get("version") != "2.0":
        issue(errors, "gltf_version_invalid", "glTF asset version must be 2.0.", "gltf.asset.version")

    object_count = len(manifest.get("objects", []))
    if len(gltf.get("meshes", [])) != object_count:
        issue(errors, "gltf_mesh_count_mismatch", "glTF mesh count must match manifest object count.", "gltf.meshes")
    if len(gltf.get("materials", [])) != object_count:
        issue(errors, "gltf_material_count_mismatch", "glTF material count must match manifest object count.", "gltf.materials")
    if gltf.get("buffers", [{}])[0].get("byteLength") != len(bin_bytes):
        issue(errors, "gltf_bin_length_mismatch", "glTF buffer byteLength does not match scene.bin.", "gltf.buffers[0]")

    if len(glb_bytes) < 20:
        issue(errors, "glb_too_short", "GLB file is too short.", "glb")
    else:
        magic, version, length = struct.unpack("<4sII", glb_bytes[:12])
        if magic != b"glTF":
            issue(errors, "glb_magic_invalid", "GLB magic header is invalid.", "glb.header")
        if version != 2:
            issue(errors, "glb_version_invalid", "GLB version must be 2.", "glb.header")
        if length != len(glb_bytes):
            issue(errors, "glb_length_mismatch", "GLB header length does not match file length.", "glb.header")

    obj_text = Path(exports["obj"]).read_text(encoding="utf-8", errors="ignore")
    for obj in manifest.get("objects", []):
        obj_id = obj.get("id")
        if obj_id and f"o {obj_id}" not in obj_text:
            issue(warnings, "obj_object_name_missing", f"OBJ output does not contain object name {obj_id!r}.", "obj")

    return {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "object_count": object_count,
            "gltf_mesh_count": len(gltf.get("meshes", [])),
            "gltf_material_count": len(gltf.get("materials", [])),
            "bin_bytes": len(bin_bytes),
            "glb_bytes": len(glb_bytes),
        },
    }


def run_vr_editing_proof(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = create_vr_editing_proof_scene()
    manifest = scene.save_manifest(output_dir / "scene.manifest.json")
    loaded = BuilderScene.load_manifest(manifest)
    exports = loaded.export_game_ready(output_dir / "exported")
    scene_quality = loaded.validate_scene()
    export_quality = validate_export_bundle(exports)
    proof_ok = scene_quality["ok"] and export_quality["ok"]
    proof = {
        "ok": proof_ok,
        "schema": SCHEMA_VERSION,
        "plugin": "panda_xr_vr_builder",
        "desktop_safe": True,
        "requires_openxr": False,
        "object_count": len(loaded.objects),
        "connection_count": len(loaded.connections),
        "path_node_count": len(loaded.path_nodes),
        "animation_count": len(loaded.animations),
        "behavior_count": len(loaded.behaviors),
        "editor_panel_count": len(loaded.editor_panels),
        "operation_count": len(loaded.operation_history),
        "objects": loaded.mesh_summaries(),
        "behavior_preview_t1": loaded.evaluate_behaviors(1.0),
        "grid": loaded.grid.to_dict(),
        "grid_occupancy": loaded.grid_occupancy_summary(),
        "performance": loaded.performance_summary(),
        "scene_quality": scene_quality,
        "export_quality": export_quality,
        "outputs": {"manifest": str(manifest), **{key: str(value) for key, value in exports.items()}, "proof_result": str(output_dir / "proof_result.json")},
        "checksums": {"manifest": _sha256(manifest), **{key: _sha256(value) for key, value in exports.items()}},
    }
    _write_text_atomic(output_dir / "proof_result.json", json.dumps(proof, indent=2, sort_keys=True))
    return proof
