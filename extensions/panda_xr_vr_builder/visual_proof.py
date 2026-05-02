from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .core import BuilderObject, BuilderScene, Transform, _as_color, _triangulate_faces, create_vr_editing_proof_scene


Vec3 = tuple[float, float, float]
GRAY_BG = (126, 128, 130)
DRAWN_OBJECT_ID = "vr_hand_drawn_spiral_01"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _visual_points() -> list[Vec3]:
    points: list[Vec3] = []
    for index in range(90):
        t = index / 89.0
        angle = math.tau * 2.7 * t
        radius = 0.38 + 0.34 * math.sin(math.pi * t)
        points.append((
            round(-0.1 + math.cos(angle) * radius, 6),
            round(-1.05 + math.sin(angle) * radius * 0.42, 6),
            round(1.22 + t * 0.86 + math.sin(angle * 0.5) * 0.08, 6),
        ))
    return points


def create_vr_visual_simulation_scene() -> BuilderScene:
    scene = create_vr_editing_proof_scene()
    draw_points = _visual_points()
    scene.begin_stroke(
        DRAWN_OBJECT_ID,
        color=(0.98, 0.24, 0.78, 1.0),
        radius=0.055,
        shade="emissive",
        radial_segments=8,
        max_points=128,
    )
    scene.draw_stroke_points(DRAWN_OBJECT_ID, draw_points, min_distance=0.01)
    scene.smooth_stroke(DRAWN_OBJECT_ID, passes=1)
    scene.smooth_grab_resize(DRAWN_OBJECT_ID, (1.08, 1.08, 1.08), smoothing=0.65)
    scene.program_behavior(
        "visual_drawn_object_pulse",
        DRAWN_OBJECT_ID,
        "pulse_color",
        {"color_a": [0.98, 0.24, 0.78, 1.0], "color_b": [0.22, 1.0, 0.88, 1.0], "frequency": 0.35},
    )
    scene.create_object(
        BuilderObject(
            "sim_left_hand",
            "sphere",
            {"radius": 0.09, "rings": 8, "segments": 12},
            Transform(position=(-0.78, -1.25, 1.32)),
            collision={"type": "controller_marker", "deformed": False},
            metadata={"material": {"base_color": [0.22, 1.0, 0.68, 1.0], "shade": "emissive", "emission_strength": 0.8}},
        )
    )
    scene.create_object(
        BuilderObject(
            "sim_right_hand",
            "sphere",
            {"radius": 0.09, "rings": 8, "segments": 12},
            Transform(position=(0.76, -1.18, 1.76)),
            collision={"type": "controller_marker", "deformed": False},
            metadata={"material": {"base_color": [1.0, 0.86, 0.25, 1.0], "shade": "emissive", "emission_strength": 0.8}},
        )
    )
    scene.metadata["visual_proof"] = {
        "mode": "vr_simulation",
        "drawn_object": DRAWN_OBJECT_ID,
        "simulated_hand_points": len(draw_points),
        "requires_openxr": False,
    }
    return scene


def _object_color(obj: BuilderObject) -> tuple[int, int, int, int]:
    material = obj.metadata.get("material") or {}
    color = _as_color(material.get("base_color"), (0.75, 0.78, 0.82, 1.0))
    return tuple(int(max(0, min(255, round(value * 255)))) for value in color)  # type: ignore[return-value]


def _image_metrics(path: Path, background: tuple[int, int, int] = GRAY_BG) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    pixels = image.load()
    width, height = image.size
    samples = 0
    non_background = 0
    min_x, min_y, max_x, max_y = width, height, 0, 0
    unique: set[tuple[int, int, int]] = set()
    step = max(1, min(width, height) // 180)
    for y in range(0, height, step):
        for x in range(0, width, step):
            value = pixels[x, y]
            unique.add(value)
            samples += 1
            if sum(abs(value[i] - background[i]) for i in range(3)) > 24:
                non_background += 1
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    ratio = non_background / max(1, samples)
    bbox = None if non_background == 0 else [min_x, min_y, max_x, max_y]
    return {
        "width": width,
        "height": height,
        "sample_count": samples,
        "unique_sampled_colors": len(unique),
        "non_background_ratio": round(ratio, 6),
        "content_bbox": bbox,
        "ok": ratio > 0.015 and len(unique) > 6,
    }


def _shade(color: tuple[int, int, int, int], normal: Vec3) -> tuple[int, int, int, int]:
    light = (0.45, -0.35, 0.82)
    length = math.sqrt(sum(component * component for component in normal)) or 1.0
    n = tuple(component / length for component in normal)
    dot = max(0.0, n[0] * light[0] + n[1] * light[1] + n[2] * light[2])
    amount = 0.45 + 0.55 * dot
    return (int(color[0] * amount), int(color[1] * amount), int(color[2] * amount), color[3])


def _normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )


def _project(point: Vec3, width: int, height: int) -> tuple[int, int, float]:
    camera = (0.0, -7.4, 2.65)
    target = (0.25, -0.15, 0.95)
    forward = _unit((target[0] - camera[0], target[1] - camera[1], target[2] - camera[2]))
    right = _unit((forward[1], -forward[0], 0.0))
    up = _unit(_cross(right, forward))
    rel = (point[0] - camera[0], point[1] - camera[1], point[2] - camera[2])
    x = _dot(rel, right)
    y = _dot(rel, up)
    z = max(0.1, _dot(rel, forward))
    focal = width * 0.92
    return (int(width * 0.5 + x / z * focal), int(height * 0.53 - y / z * focal), z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec3) -> Vec3:
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def _software_render(scene: BuilderScene, screenshot_path: Path, width: int, height: int) -> dict[str, Any]:
    image = Image.new("RGB", (width, height), GRAY_BG)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle([0, int(height * 0.68), width, height], fill=(108, 110, 112, 255))
    draw.line([(0, int(height * 0.68)), (width, int(height * 0.68))], fill=(165, 168, 170, 255), width=2)

    triangles: list[tuple[float, list[tuple[int, int]], tuple[int, int, int, int]]] = []
    for obj in scene.objects:
        mesh = obj.world_mesh()
        color = _object_color(obj)
        for tri in _triangulate_faces(mesh.faces):
            verts = [mesh.vertices[index] for index in tri]
            projected = [_project(vertex, width, height) for vertex in verts]
            if any(p[2] <= 0.11 for p in projected):
                continue
            avg_depth = sum(p[2] for p in projected) / 3.0
            normal = _normal(verts[0], verts[1], verts[2])
            shaded = _shade(color, normal)
            if obj.kind == "stroke":
                shaded = color
            triangles.append((avg_depth, [(p[0], p[1]) for p in projected], shaded))
    for _depth, points, color in sorted(triangles, key=lambda item: item[0], reverse=True):
        draw.polygon(points, fill=color, outline=(30, 32, 34, 90))

    for obj in scene.objects:
        if obj.kind != "stroke":
            continue
        stroke = obj.metadata.get("stroke") or {}
        points = [tuple(float(v) for v in point[:3]) for point in stroke.get("points", [])]
        projected = [_project(point, width, height) for point in points]
        line = [(x, y) for x, y, depth in projected if depth > 0.11]
        if len(line) >= 2:
            draw.line(line, fill=_object_color(obj), width=max(4, int(width / 260)))

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(screenshot_path)
    return {"backend": "software_projection", "image_metrics": _image_metrics(screenshot_path)}


def _build_panda_geom(obj: BuilderObject):
    from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter

    mesh = obj.world_mesh()
    fmt = GeomVertexFormat.getV3n3c4()
    vertex_data = GeomVertexData(obj.id, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vertex_data, "vertex")
    normal_writer = GeomVertexWriter(vertex_data, "normal")
    color_writer = GeomVertexWriter(vertex_data, "color")
    triangles = GeomTriangles(Geom.UHStatic)
    color = tuple(channel / 255.0 for channel in _object_color(obj))
    row = 0
    for tri in _triangulate_faces(mesh.faces):
        verts = [mesh.vertices[index] for index in tri]
        normal = _unit(_normal(verts[0], verts[1], verts[2]))
        for value in verts:
            vertex.addData3(*value)
            normal_writer.addData3(*normal)
            color_writer.addData4(*color)
        triangles.addVertices(row, row + 1, row + 2)
        row += 3
    geom = Geom(vertex_data)
    geom.addPrimitive(triangles)
    node = GeomNode(obj.id)
    node.addGeom(geom)
    return node


def _panda3d_render(scene: BuilderScene, screenshot_path: Path, width: int, height: int, seconds: float) -> dict[str, Any]:
    from direct.showbase.ShowBase import ShowBase
    from panda3d.core import AmbientLight, AntialiasAttrib, DirectionalLight, Filename, PerspectiveLens, Vec3, Vec4, load_prc_file_data

    load_prc_file_data(
        "panda-xr-visual-proof",
        "\n".join([
            "window-type offscreen",
            f"win-size {width} {height}",
            "framebuffer-srgb false",
            "framebuffer-multisample 0",
            "audio-library-name null",
            "notify-level-display error",
            "notify-level-glgsg error",
        ]),
    )
    base = ShowBase(windowType="offscreen")
    try:
        base.disableMouse()
        base.win.set_clear_color(Vec4(GRAY_BG[0] / 255.0, GRAY_BG[1] / 255.0, GRAY_BG[2] / 255.0, 1.0))
        lens = PerspectiveLens()
        lens.set_fov(52.0)
        lens.set_near_far(0.05, 80.0)
        base.cam.node().set_lens(lens)
        base.camera.set_pos(0.0, -7.4, 2.65)
        base.camera.look_at(0.25, -0.15, 0.95)

        ambient = AmbientLight("visual-proof-ambient")
        ambient.set_color(Vec4(0.42, 0.42, 0.42, 1.0))
        ambient_np = base.render.attach_new_node(ambient)
        base.render.set_light(ambient_np)
        sun = DirectionalLight("visual-proof-key")
        sun.set_color(Vec4(0.95, 0.94, 0.88, 1.0))
        sun_np = base.render.attach_new_node(sun)
        sun_np.set_hpr(-42.0, -36.0, 0.0)
        base.render.set_light(sun_np)
        base.render.set_antialias(AntialiasAttrib.MAuto)

        root = base.render.attach_new_node("panda-xr-vr-simulation-scene")
        for obj in scene.objects:
            np = root.attach_new_node(_build_panda_geom(obj))
            np.set_two_sided(True)
            if obj.kind == "stroke":
                np.set_light_off(1)

        frames = max(1, int(round(seconds * 60.0)))
        start = time.monotonic()
        for frame in range(frames):
            t = frame / max(1, frames - 1)
            root.set_h(5.0 * math.sin(t * math.tau * 0.35))
            base.graphicsEngine.renderFrame()
            if seconds >= 1.0:
                target_elapsed = (frame + 1) / 60.0
                remaining = target_elapsed - (time.monotonic() - start)
                if remaining > 0:
                    time.sleep(min(remaining, 0.02))
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        saved = base.win.save_screenshot(Filename.from_os_specific(str(screenshot_path)))
        base.graphicsEngine.renderFrame()
        metrics = _image_metrics(screenshot_path) if saved and screenshot_path.exists() else {"ok": False, "error": "save_screenshot failed"}
        return {"backend": "panda3d_offscreen", "image_metrics": metrics, "frames_rendered": frames}
    finally:
        base.destroy()


def run_vr_visual_proof(
    output_dir: Path,
    *,
    width: int = 1600,
    height: int = 900,
    seconds: float = 3.0,
    backend: str = "auto",
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    width = max(640, int(width))
    height = max(360, int(height))
    seconds = max(0.1, float(seconds))
    scene = create_vr_visual_simulation_scene()
    manifest_path = scene.save_manifest(output_dir / "visual_scene.manifest.json")
    exports = scene.export_game_ready(output_dir / "exported")
    screenshot_path = output_dir / "panda_xr_vr_visual_proof.png"
    errors: list[dict[str, str]] = []

    render: dict[str, Any]
    if backend not in {"auto", "panda3d", "software"}:
        raise ValueError("backend must be one of: auto, panda3d, software")
    if backend in {"auto", "panda3d"}:
        try:
            render = _panda3d_render(scene, screenshot_path, width, height, seconds)
            if not render.get("image_metrics", {}).get("ok"):
                raise RuntimeError(f"visual output failed image metrics: {render.get('image_metrics')}")
        except Exception as exc:
            errors.append({"backend": "panda3d_offscreen", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-1600:]})
            if backend == "panda3d":
                render = {"backend": "panda3d_offscreen", "image_metrics": {"ok": False}, "errors": errors}
            else:
                render = _software_render(scene, screenshot_path, width, height)
    else:
        render = _software_render(scene, screenshot_path, width, height)

    image_metrics = render.get("image_metrics") or {}
    proof = {
        "ok": bool(screenshot_path.exists() and image_metrics.get("ok")),
        "mode": "vr_simulation_desktop_safe",
        "requires_openxr": False,
        "backend": render.get("backend"),
        "backend_errors": errors,
        "width": width,
        "height": height,
        "aspect_ratio": "16:9" if abs(width / height - 16 / 9) < 0.01 else f"{width}:{height}",
        "duration_seconds": seconds,
        "frame_count": max(1, int(round(seconds * 60.0))),
        "drawn_object": DRAWN_OBJECT_ID,
        "drawn_point_count": len(_visual_points()),
        "object_count": len(scene.objects),
        "operation_count": len(scene.operation_history),
        "scene_quality": scene.validate_scene(),
        "image_metrics": image_metrics,
        "outputs": {
            "manifest": str(manifest_path),
            "screenshot": str(screenshot_path),
            **{key: str(value) for key, value in exports.items()},
            "visual_report": str(output_dir / "visual_proof_report.json"),
        },
    }
    _write_json(output_dir / "visual_proof_report.json", proof)
    return proof
