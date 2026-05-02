from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 'panda-xr-builder-scene-v2'
SUPPORTED_SCHEMAS = {'panda-xr-builder-scene-v1', SCHEMA_VERSION}
Vec3 = Tuple[float, float, float]
Face = Tuple[int, ...]


def _round(value: float) -> float:
    return round(float(value), 6)


def _vadd(a: Vec3, b: Vec3) -> Vec3:
    return (_round(a[0] + b[0]), _round(a[1] + b[1]), _round(a[2] + b[2]))


def _vsub(a: Vec3, b: Vec3) -> Vec3:
    return (_round(a[0] - b[0]), _round(a[1] - b[1]), _round(a[2] - b[2]))


def _vmul(a: Vec3, scalar: float) -> Vec3:
    return (_round(a[0] * scalar), _round(a[1] * scalar), _round(a[2] * scalar))


def _vlen(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


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
    return (_round(x), _round(y), _round(z))


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp_path.write_text(text, encoding='utf-8')
    temp_path.replace(path)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp_path.write_bytes(data)
    temp_path.replace(path)


def _pad4(data: bytes, pad_byte: bytes = b'\x00') -> bytes:
    missing = (-len(data)) % 4
    if not missing:
        return data
    return data + pad_byte * missing


def _triangulate_faces(faces: Iterable[Face]) -> List[Tuple[int, int, int]]:
    triangles: List[Tuple[int, int, int]] = []
    for face in faces:
        if len(face) < 3:
            continue
        for i in range(1, len(face) - 1):
            triangles.append((face[0], face[i], face[i + 1]))
    return triangles


@dataclass
class MeshData:
    vertices: List[Vec3]
    faces: List[Face]

    def bounds(self) -> Dict[str, Vec3]:
        if not self.vertices:
            zero = (0.0, 0.0, 0.0)
            return {'min': zero, 'max': zero}
        xs, ys, zs = zip(*self.vertices)
        return {
            'min': (_round(min(xs)), _round(min(ys)), _round(min(zs))),
            'max': (_round(max(xs)), _round(max(ys)), _round(max(zs))),
        }

    def checksum(self) -> str:
        payload = json.dumps({'vertices': self.vertices, 'faces': self.faces}, sort_keys=True)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass
class ControlPoint:
    id: str
    position: Vec3
    delta: Vec3
    radius: float
    mode: str = 'smooth_pull'

    @classmethod
    def from_dict(cls, data: Dict) -> 'ControlPoint':
        return cls(
            id=str(data['id']),
            position=tuple(data['position']),
            delta=tuple(data['delta']),
            radius=float(data['radius']),
            mode=str(data.get('mode', 'smooth_pull')),
        )


@dataclass
class Transform:
    position: Vec3 = (0.0, 0.0, 0.0)
    rotation: Vec3 = (0.0, 0.0, 0.0)
    scale: Vec3 = (1.0, 1.0, 1.0)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Transform':
        return cls(
            position=tuple(data.get('position', (0.0, 0.0, 0.0))),
            rotation=tuple(data.get('rotation', (0.0, 0.0, 0.0))),
            scale=tuple(data.get('scale', (1.0, 1.0, 1.0))),
        )


@dataclass
class BuilderObject:
    id: str
    kind: str
    params: Dict[str, float] = field(default_factory=dict)
    transform: Transform = field(default_factory=Transform)
    control_points: List[ControlPoint] = field(default_factory=list)
    collision: Dict = field(default_factory=dict)
    sockets: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def base_mesh(self) -> MeshData:
        if self.kind == 'cube':
            size = self.params.get('size', 1.0)
            subdivisions = int(self.params.get('subdivisions', 2))
            return make_cube_mesh(float(size), max(1, subdivisions))
        if self.kind == 'floor':
            width = self.params.get('width', 4.0)
            depth = self.params.get('depth', 4.0)
            thickness = self.params.get('thickness', 0.12)
            subdivisions = int(self.params.get('subdivisions', 1))
            return make_box_mesh(float(width), float(depth), float(thickness), max(1, subdivisions))
        if self.kind == 'wall':
            width = self.params.get('width', 4.0)
            height = self.params.get('height', 2.5)
            thickness = self.params.get('thickness', 0.16)
            subdivisions = int(self.params.get('subdivisions', 1))
            return make_box_mesh(float(width), float(thickness), float(height), max(1, subdivisions))
        if self.kind == 'sphere':
            radius = self.params.get('radius', 0.5)
            rings = int(self.params.get('rings', 12))
            segments = int(self.params.get('segments', 16))
            return make_sphere_mesh(float(radius), max(3, rings), max(6, segments))
        if self.kind == 'cylinder':
            radius = self.params.get('radius', 0.5)
            height = self.params.get('height', 1.0)
            segments = int(self.params.get('segments', 16))
            height_segments = int(self.params.get('height_segments', 1))
            return make_cylinder_mesh(float(radius), float(height), max(6, segments), max(1, height_segments))
        if self.kind == 'capsule':
            radius = self.params.get('radius', 0.5)
            cylinder_height = self.params.get('cylinder_height', 1.0)
            segments = int(self.params.get('segments', 16))
            hemisphere_rings = int(self.params.get('hemisphere_rings', 6))
            return make_capsule_mesh(float(radius), float(cylinder_height), max(6, segments), max(2, hemisphere_rings))
        raise ValueError(f'Unsupported builder object kind: {self.kind}')

    def deformed_mesh(self) -> MeshData:
        mesh = self.base_mesh()
        if not self.control_points:
            return mesh
        deformed = []
        for vertex in mesh.vertices:
            next_vertex = vertex
            for control in self.control_points:
                distance = _vlen(_vsub(vertex, control.position))
                weight = _smooth_weight(distance, float(control.radius))
                if weight:
                    next_vertex = _vadd(next_vertex, _vmul(control.delta, weight))
            deformed.append(next_vertex)
        return MeshData(deformed, mesh.faces)

    def world_mesh(self) -> MeshData:
        mesh = self.deformed_mesh()
        vertices = []
        for vertex in mesh.vertices:
            scaled = (
                _round(vertex[0] * self.transform.scale[0]),
                _round(vertex[1] * self.transform.scale[1]),
                _round(vertex[2] * self.transform.scale[2]),
            )
            rotated = _rotate_xyz(scaled, self.transform.rotation)
            vertices.append(_vadd(rotated, self.transform.position))
        return MeshData(vertices, mesh.faces)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'kind': self.kind,
            'params': self.params,
            'transform': asdict(self.transform),
            'control_points': [asdict(control) for control in self.control_points],
            'collision': self.collision,
            'sockets': self.sockets,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'BuilderObject':
        return cls(
            id=str(data['id']),
            kind=str(data['kind']),
            params=dict(data.get('params', {})),
            transform=Transform.from_dict(data.get('transform', {})),
            control_points=[ControlPoint.from_dict(item) for item in data.get('control_points', [])],
            collision=dict(data.get('collision', {})),
            sockets=list(data.get('sockets', [])),
            metadata=dict(data.get('metadata', {})),
        )


@dataclass
class BuilderScene:
    name: str
    objects: List[BuilderObject] = field(default_factory=list)
    connections: List[Dict] = field(default_factory=list)
    path_nodes: List[Dict] = field(default_factory=list)
    animations: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    units: str = 'meters'

    def to_dict(self) -> Dict:
        return {
            'schema': SCHEMA_VERSION,
            'name': self.name,
            'units': self.units,
            'objects': [obj.to_dict() for obj in self.objects],
            'connections': self.connections,
            'path_nodes': self.path_nodes,
            'animations': self.animations,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'BuilderScene':
        schema = data.get('schema')
        if schema not in SUPPORTED_SCHEMAS:
            raise ValueError(f'Unsupported manifest schema: {schema!r}')
        return cls(
            name=str(data.get('name', 'Panda XR Scene')),
            units=str(data.get('units', 'meters')),
            objects=[BuilderObject.from_dict(item) for item in data.get('objects', [])],
            connections=list(data.get('connections', [])),
            path_nodes=list(data.get('path_nodes', [])),
            animations=list(data.get('animations', [])),
            metadata=dict(data.get('metadata', {})),
        )

    def save_manifest(self, path: Path) -> Path:
        _write_text_atomic(path, json.dumps(self.to_dict(), indent=2, sort_keys=True))
        return path

    @classmethod
    def load_manifest(cls, path: Path) -> 'BuilderScene':
        return cls.from_dict(json.loads(path.read_text(encoding='utf-8')))

    def mesh_summaries(self) -> List[Dict]:
        summaries = []
        for obj in self.objects:
            mesh = obj.world_mesh()
            summaries.append({
                'id': obj.id,
                'kind': obj.kind,
                'vertex_count': len(mesh.vertices),
                'face_count': len(mesh.faces),
                'bounds': mesh.bounds(),
                'checksum': mesh.checksum(),
                'control_point_count': len(obj.control_points),
            })
        return summaries

    def export_obj(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            '# Panda XR deformed scene export',
            f'# scene: {self.name}',
            f'# units: {self.units}',
        ]
        vertex_offset = 1
        for obj in self.objects:
            mesh = obj.world_mesh()
            lines.append(f'o {obj.id}')
            for vertex in mesh.vertices:
                lines.append(f'v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}')
            for face in mesh.faces:
                indices = ' '.join(str(index + vertex_offset) for index in face)
                lines.append(f'f {indices}')
            vertex_offset += len(mesh.vertices)
        _write_text_atomic(path, '\n'.join(lines) + '\n')
        return path

    def export_metadata(self, path: Path, obj_path: Optional[Path] = None) -> Path:
        payload = {
            'schema': SCHEMA_VERSION,
            'name': self.name,
            'units': self.units,
            'object_count': len(self.objects),
            'connection_count': len(self.connections),
            'path_node_count': len(self.path_nodes),
            'animation_count': len(self.animations),
            'objects': self.mesh_summaries(),
            'connections': self.connections,
            'path_nodes': self.path_nodes,
            'animations': self.animations,
            'scene_metadata': self.metadata,
        }
        if obj_path is not None:
            payload['geometry'] = str(obj_path.name)
        _write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True))
        return path

    def _build_gltf(self, bin_uri: Optional[str]) -> Tuple[Dict, bytes]:
        buffer = bytearray()
        buffer_views: List[Dict] = []
        accessors: List[Dict] = []
        meshes: List[Dict] = []
        nodes: List[Dict] = []

        def add_buffer_view(data: bytes, target: int) -> int:
            nonlocal buffer
            while len(buffer) % 4:
                buffer.append(0)
            offset = len(buffer)
            buffer.extend(data)
            while len(buffer) % 4:
                buffer.append(0)
            buffer_views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
            return len(buffer_views) - 1

        for obj in self.objects:
            mesh = obj.world_mesh()
            triangles = _triangulate_faces(mesh.faces)
            position_bytes = b''.join(struct.pack('<fff', *vertex) for vertex in mesh.vertices)
            index_bytes = b''.join(struct.pack('<I', index) for tri in triangles for index in tri)
            position_view = add_buffer_view(position_bytes, 34962)
            index_view = add_buffer_view(index_bytes, 34963)
            bounds = mesh.bounds()
            position_accessor = {
                'bufferView': position_view,
                'componentType': 5126,
                'count': len(mesh.vertices),
                'type': 'VEC3',
                'min': list(bounds['min']),
                'max': list(bounds['max']),
            }
            index_accessor = {
                'bufferView': index_view,
                'componentType': 5125,
                'count': len(triangles) * 3,
                'type': 'SCALAR',
            }
            position_accessor_index = len(accessors)
            accessors.append(position_accessor)
            index_accessor_index = len(accessors)
            accessors.append(index_accessor)
            mesh_index = len(meshes)
            meshes.append({
                'name': obj.id,
                'primitives': [{
                    'attributes': {'POSITION': position_accessor_index},
                    'indices': index_accessor_index,
                    'mode': 4,
                }],
                'extras': {
                    'builder_object': obj.to_dict(),
                    'source_vertex_count': len(mesh.vertices),
                    'source_face_count': len(mesh.faces),
                    'triangle_count': len(triangles),
                    'deformed_checksum': mesh.checksum(),
                },
            })
            nodes.append({'name': obj.id, 'mesh': mesh_index})

        gltf = {
            'asset': {'version': '2.0', 'generator': 'Panda XR builder_core'},
            'scene': 0,
            'scenes': [{
                'name': self.name,
                'nodes': list(range(len(nodes))),
                'extras': {
                    'schema': SCHEMA_VERSION,
                    'units': self.units,
                    'connections': self.connections,
                    'path_nodes': self.path_nodes,
                    'animations': self.animations,
                    'scene_metadata': self.metadata,
                },
            }],
            'nodes': nodes,
            'meshes': meshes,
            'buffers': [{'byteLength': len(buffer)}],
            'bufferViews': buffer_views,
            'accessors': accessors,
        }
        if bin_uri is not None:
            gltf['buffers'][0]['uri'] = bin_uri
        return gltf, bytes(buffer)

    def export_gltf(self, directory: Path) -> Dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        gltf, binary = self._build_gltf('scene.bin')
        gltf_path = directory / 'scene.gltf'
        bin_path = directory / 'scene.bin'
        _write_bytes_atomic(bin_path, binary)
        _write_text_atomic(gltf_path, json.dumps(gltf, indent=2, sort_keys=True))
        return {'gltf': gltf_path, 'bin': bin_path}

    def export_glb(self, path: Path) -> Path:
        gltf, binary = self._build_gltf(None)
        json_chunk = _pad4(json.dumps(gltf, separators=(',', ':'), sort_keys=True).encode('utf-8'), b' ')
        bin_chunk = _pad4(binary, b'\x00')
        total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
        payload = bytearray()
        payload.extend(struct.pack('<4sII', b'glTF', 2, total_length))
        payload.extend(struct.pack('<I4s', len(json_chunk), b'JSON'))
        payload.extend(json_chunk)
        payload.extend(struct.pack('<I4s', len(bin_chunk), b'BIN\x00'))
        payload.extend(bin_chunk)
        _write_bytes_atomic(path, bytes(payload))
        return path

    def export_game_ready(self, directory: Path) -> Dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        manifest = self.save_manifest(directory / 'scene.manifest.json')
        obj = self.export_obj(directory / 'scene.obj')
        metadata = self.export_metadata(directory / 'scene.metadata.json', obj)
        gltf_paths = self.export_gltf(directory)
        glb = self.export_glb(directory / 'scene.glb')
        return {'manifest': manifest, 'obj': obj, 'metadata': metadata, 'gltf': gltf_paths['gltf'], 'bin': gltf_paths['bin'], 'glb': glb}


def make_box_mesh(width: float = 1.0, depth: float = 1.0, height: float = 1.0, subdivisions: int = 1) -> MeshData:
    hx = width / 2.0
    hy = depth / 2.0
    hz = height / 2.0
    vertices: List[Vec3] = []
    faces: List[Face] = []

    def add_face(axis: str, sign: float) -> None:
        start = len(vertices)
        for row in range(subdivisions + 1):
            for col in range(subdivisions + 1):
                if axis == 'x':
                    a = -hy + col * (depth / subdivisions)
                    b = -hz + row * (height / subdivisions)
                    vertex = (sign * hx, a, b)
                elif axis == 'y':
                    a = -hx + col * (width / subdivisions)
                    b = -hz + row * (height / subdivisions)
                    vertex = (a, sign * hy, b)
                else:
                    a = -hx + col * (width / subdivisions)
                    b = -hy + row * (depth / subdivisions)
                    vertex = (a, b, sign * hz)
                vertices.append(tuple(_round(v) for v in vertex))
        for row in range(subdivisions):
            for col in range(subdivisions):
                i = start + row * (subdivisions + 1) + col
                if sign > 0:
                    faces.append((i, i + 1, i + subdivisions + 2, i + subdivisions + 1))
                else:
                    faces.append((i, i + subdivisions + 1, i + subdivisions + 2, i + 1))

    for axis, sign in (('z', 1.0), ('z', -1.0), ('x', 1.0), ('x', -1.0), ('y', 1.0), ('y', -1.0)):
        add_face(axis, sign)
    return MeshData(vertices, faces)


def make_cube_mesh(size: float = 1.0, subdivisions: int = 2) -> MeshData:
    return make_box_mesh(size, size, size, subdivisions)


def make_sphere_mesh(radius: float = 0.5, rings: int = 12, segments: int = 16) -> MeshData:
    vertices: List[Vec3] = [(0.0, 0.0, _round(radius))]
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        z = radius * math.cos(theta)
        r = radius * math.sin(theta)
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_round(r * math.cos(phi)), _round(r * math.sin(phi)), _round(z)))
    vertices.append((0.0, 0.0, _round(-radius)))

    faces: List[Face] = []
    bottom_index = len(vertices) - 1
    first_ring = 1
    last_ring = 1 + (rings - 2) * segments
    for segment in range(segments):
        faces.append((0, first_ring + segment, first_ring + ((segment + 1) % segments)))
    for ring in range(rings - 2):
        row = 1 + ring * segments
        next_row = row + segments
        for segment in range(segments):
            faces.append((
                row + segment,
                next_row + segment,
                next_row + ((segment + 1) % segments),
                row + ((segment + 1) % segments),
            ))
    for segment in range(segments):
        faces.append((last_ring + ((segment + 1) % segments), last_ring + segment, bottom_index))
    return MeshData(vertices, faces)


def make_cylinder_mesh(radius: float = 0.5, height: float = 1.0, segments: int = 16, height_segments: int = 1) -> MeshData:
    vertices: List[Vec3] = []
    half = height / 2.0
    for row in range(height_segments + 1):
        z = -half + height * row / height_segments
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_round(radius * math.cos(phi)), _round(radius * math.sin(phi)), _round(z)))

    bottom_center = len(vertices)
    vertices.append((0.0, 0.0, _round(-half)))
    top_center = len(vertices)
    vertices.append((0.0, 0.0, _round(half)))

    faces: List[Face] = []
    for row in range(height_segments):
        base = row * segments
        next_base = base + segments
        for segment in range(segments):
            faces.append((
                base + segment,
                base + ((segment + 1) % segments),
                next_base + ((segment + 1) % segments),
                next_base + segment,
            ))
    for segment in range(segments):
        faces.append((bottom_center, (segment + 1) % segments, segment))
    top_base = height_segments * segments
    for segment in range(segments):
        faces.append((top_center, top_base + segment, top_base + ((segment + 1) % segments)))
    return MeshData(vertices, faces)


def make_capsule_mesh(radius: float = 0.5, cylinder_height: float = 1.0, segments: int = 16, hemisphere_rings: int = 6) -> MeshData:
    total_rings = hemisphere_rings * 2
    vertices: List[Vec3] = [(0.0, 0.0, _round(cylinder_height / 2.0 + radius))]
    for ring in range(1, total_rings):
        theta = math.pi * ring / total_rings
        ring_radius = radius * math.sin(theta)
        local_z = radius * math.cos(theta)
        z = local_z + (cylinder_height / 2.0 if theta <= math.pi / 2.0 else -cylinder_height / 2.0)
        for segment in range(segments):
            phi = math.tau * segment / segments
            vertices.append((_round(ring_radius * math.cos(phi)), _round(ring_radius * math.sin(phi)), _round(z)))
    vertices.append((0.0, 0.0, _round(-cylinder_height / 2.0 - radius)))

    faces: List[Face] = []
    bottom_index = len(vertices) - 1
    first_ring = 1
    last_ring = 1 + (total_rings - 2) * segments
    for segment in range(segments):
        faces.append((0, first_ring + segment, first_ring + ((segment + 1) % segments)))
    for ring in range(total_rings - 2):
        row = 1 + ring * segments
        next_row = row + segments
        for segment in range(segments):
            faces.append((
                row + segment,
                next_row + segment,
                next_row + ((segment + 1) % segments),
                row + ((segment + 1) % segments),
            ))
    for segment in range(segments):
        faces.append((last_ring + ((segment + 1) % segments), last_ring + segment, bottom_index))
    return MeshData(vertices, faces)


def create_proof_scene() -> BuilderScene:
    cube = BuilderObject(
        id='proof_cube',
        kind='cube',
        params={'size': 2.0, 'subdivisions': 4},
        transform=Transform(position=(-1.25, 0.0, 1.0)),
        control_points=[
            ControlPoint('cube_top_pull', (0.0, 0.0, 1.0), (0.0, 0.0, 0.45), 1.35),
            ControlPoint('cube_front_smooth', (0.0, -1.0, 0.0), (0.0, -0.32, 0.08), 1.10),
        ],
        collision={'type': 'box', 'size': [2.0, 2.0, 2.0], 'deformed': True},
        sockets=[
            {'id': 'cube_socket_top', 'position': [0.0, 0.0, 1.45], 'normal': [0.0, 0.0, 1.0]},
        ],
        metadata={'role': 'editable_deformed_cube'},
    )
    sphere = BuilderObject(
        id='proof_sphere',
        kind='sphere',
        params={'radius': 0.85, 'rings': 12, 'segments': 18},
        transform=Transform(position=(1.25, 0.0, 1.1), rotation=(0.0, 0.0, 18.0)),
        control_points=[
            ControlPoint('sphere_right_pull', (0.85, 0.0, 0.0), (0.42, 0.0, 0.0), 0.80),
            ControlPoint('sphere_upper_squeeze', (0.0, 0.0, 0.85), (0.0, 0.0, -0.20), 0.65),
        ],
        collision={'type': 'sphere', 'radius': 0.85, 'deformed': True},
        sockets=[
            {'id': 'sphere_socket_left', 'position': [-0.85, 0.0, 0.0], 'normal': [-1.0, 0.0, 0.0]},
        ],
        metadata={'role': 'editable_deformed_sphere'},
    )
    cylinder = BuilderObject(
        id='proof_cylinder',
        kind='cylinder',
        params={'radius': 0.38, 'height': 1.8, 'segments': 18, 'height_segments': 3},
        transform=Transform(position=(3.0, -0.65, 0.9), rotation=(0.0, 0.0, -12.0)),
        control_points=[
            ControlPoint('cylinder_mid_pull', (0.38, 0.0, 0.0), (0.22, 0.0, 0.0), 0.62),
        ],
        collision={'type': 'cylinder', 'radius': 0.38, 'height': 1.8, 'deformed': True},
        sockets=[
            {'id': 'cylinder_socket_top', 'position': [0.0, 0.0, 0.9], 'normal': [0.0, 0.0, 1.0]},
            {'id': 'cylinder_socket_bottom', 'position': [0.0, 0.0, -0.9], 'normal': [0.0, 0.0, -1.0]},
        ],
        metadata={'role': 'editable_deformed_cylinder'},
    )
    capsule = BuilderObject(
        id='proof_capsule',
        kind='capsule',
        params={'radius': 0.34, 'cylinder_height': 1.15, 'segments': 18, 'hemisphere_rings': 5},
        transform=Transform(position=(3.0, 0.85, 1.05), rotation=(0.0, 18.0, 0.0)),
        control_points=[
            ControlPoint('capsule_top_smooth', (0.0, 0.0, 0.91), (0.0, 0.0, 0.18), 0.45),
        ],
        collision={'type': 'capsule', 'radius': 0.34, 'cylinder_height': 1.15, 'deformed': True},
        sockets=[
            {'id': 'capsule_socket_lower', 'position': [0.0, 0.0, -0.9], 'normal': [0.0, 0.0, -1.0]},
        ],
        metadata={'role': 'editable_deformed_capsule'},
    )
    floor = BuilderObject(
        id='proof_floor',
        kind='floor',
        params={'width': 6.5, 'depth': 4.5, 'thickness': 0.12, 'subdivisions': 2},
        transform=Transform(position=(0.5, 0.0, -0.06)),
        collision={'type': 'box', 'size': [6.5, 4.5, 0.12], 'deformed': False},
        sockets=[
            {'id': 'floor_socket_wall_north', 'position': [0.0, 2.25, 0.06], 'normal': [0.0, 1.0, 0.0]},
        ],
        metadata={'role': 'builder_floor'},
    )
    wall = BuilderObject(
        id='proof_wall',
        kind='wall',
        params={'width': 3.2, 'height': 2.2, 'thickness': 0.16, 'subdivisions': 2},
        transform=Transform(position=(0.5, 2.25, 1.1)),
        collision={'type': 'box', 'size': [3.2, 0.16, 2.2], 'deformed': False},
        sockets=[
            {'id': 'wall_socket_floor', 'position': [0.0, -0.08, -1.1], 'normal': [0.0, -1.0, 0.0]},
        ],
        metadata={'role': 'builder_wall'},
    )
    return BuilderScene(
        name='Panda XR Pass 2 Builder Primitive Proof Scene',
        objects=[floor, wall, cube, sphere, cylinder, capsule],
        connections=[
            {
                'id': 'cube_to_sphere_socket_link',
                'from': {'object': 'proof_cube', 'socket': 'cube_socket_top'},
                'to': {'object': 'proof_sphere', 'socket': 'sphere_socket_left'},
                'type': 'builder_connection',
            },
            {
                'id': 'floor_to_wall_socket_link',
                'from': {'object': 'proof_floor', 'socket': 'floor_socket_wall_north'},
                'to': {'object': 'proof_wall', 'socket': 'wall_socket_floor'},
                'type': 'builder_connection',
            },
            {
                'id': 'cylinder_to_capsule_link',
                'from': {'object': 'proof_cylinder', 'socket': 'cylinder_socket_top'},
                'to': {'object': 'proof_capsule', 'socket': 'capsule_socket_lower'},
                'type': 'builder_connection',
            }
        ],
        path_nodes=[
            {'id': 'path_start', 'position': [-2.5, -1.5, 0.02], 'links': ['path_mid'], 'radius': 0.35},
            {'id': 'path_mid', 'position': [0.5, -1.35, 0.02], 'links': ['path_start', 'path_end'], 'radius': 0.35},
            {'id': 'path_end', 'position': [2.8, 0.6, 0.02], 'links': ['path_mid'], 'radius': 0.35},
        ],
        animations=[
            {
                'id': 'sphere_bob_preview',
                'target': 'proof_sphere',
                'property': 'transform.position.z',
                'keyframes': [{'time': 0.0, 'value': 1.1}, {'time': 1.0, 'value': 1.35}],
            }
        ],
        metadata={'proof': True, 'pass': 'panda_xr_builder_primitives_2'},
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_deformable_object_proof(output_dir: Path) -> Dict:
    scene = create_proof_scene()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = scene.save_manifest(output_dir / 'proof_scene.manifest.json')
    reloaded = BuilderScene.load_manifest(manifest_path)
    export_paths = reloaded.export_game_ready(output_dir / 'exported')

    proof = {
        'ok': True,
        'schema': SCHEMA_VERSION,
        'object_count': len(reloaded.objects),
        'connection_count': len(reloaded.connections),
        'path_node_count': len(reloaded.path_nodes),
        'animation_count': len(reloaded.animations),
        'objects': reloaded.mesh_summaries(),
        'outputs': {
            'proof_manifest': str(manifest_path),
            'export_manifest': str(export_paths['manifest']),
            'export_obj': str(export_paths['obj']),
            'export_metadata': str(export_paths['metadata']),
            'export_gltf': str(export_paths['gltf']),
            'export_bin': str(export_paths['bin']),
            'export_glb': str(export_paths['glb']),
            'proof_result': str(output_dir / 'proof_result.json'),
        },
        'checksums': {
            'proof_manifest': _file_sha256(manifest_path),
            'export_manifest': _file_sha256(export_paths['manifest']),
            'export_obj': _file_sha256(export_paths['obj']),
            'export_metadata': _file_sha256(export_paths['metadata']),
            'export_gltf': _file_sha256(export_paths['gltf']),
            'export_bin': _file_sha256(export_paths['bin']),
            'export_glb': _file_sha256(export_paths['glb']),
        },
    }
    proof_path = output_dir / 'proof_result.json'
    _write_text_atomic(proof_path, json.dumps(proof, indent=2, sort_keys=True))
    return proof


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Panda XR deformable object proof/export tools')
    parser.add_argument('--proof', action='store_true', help='create, deform, save, reload, and export a proof scene')
    parser.add_argument('--output', default='assets/generated/panda_xr_builder_proof', help='proof output directory')
    args = parser.parse_args(argv)
    if not args.proof:
        parser.error('No action selected. Use --proof.')
    proof = run_deformable_object_proof(Path(args.output))
    print(json.dumps({'ok': proof['ok'], 'outputs': proof['outputs']}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
