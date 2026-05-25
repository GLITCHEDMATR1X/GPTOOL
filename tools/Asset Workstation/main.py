from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import shutil
import traceback
import importlib.util
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageChops, ImageTk

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Panda Asset Workstation"
APP_VERSION = "0.3.0"
VIRTUAL_WIDTH = 1600
VIRTUAL_HEIGHT = 900
SUPPORTED_IMPORTS = [
    ("3D Assets", "*.glb *.gltf *.obj *.stl *.ply *.off *.dae *.fbx"),
    ("All Files", "*.*"),
]
SUPPORTED_TEXTURES = [
    ("Images", "*.png *.jpg *.jpeg *.bmp *.tga *.webp"),
    ("All Files", "*.*"),
]
EXPORT_FORMATS = ["glb", "obj", "stl", "ply"]


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
TEXTURES_DIR = ASSETS_DIR / "textures"
EXPORTS_DIR = BASE_DIR / "exports"
EXPORT_STATES_DIR = EXPORTS_DIR / "states"
EXPORT_CANDIDATES_DIR = EXPORT_STATES_DIR / "candidate"
EXPORT_PASSED_DIR = EXPORT_STATES_DIR / "passed_test"
PACKAGE_CANDIDATES_DIR = EXPORT_CANDIDATES_DIR / "packages"
PACKAGE_PASSED_DIR = EXPORT_PASSED_DIR / "packages"
MODEL_CANDIDATES_DIR = EXPORT_CANDIDATES_DIR / "models"
MODEL_PASSED_DIR = EXPORT_PASSED_DIR / "models"
SCREENSHOTS_DIR = EXPORTS_DIR / "screenshots"
PROJECTS_DIR = BASE_DIR / "projects"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = LOGS_DIR / "reports"
TOOLS_DIR = BASE_DIR / "tools"
CACHE_DIR = BASE_DIR / "cache"
CONVERTED_DIR = CACHE_DIR / "converted"
EXTRACTED_TEXTURES_DIR = CACHE_DIR / "extracted_textures"
LATEST_LOG = LOGS_DIR / "latest.log"
CRASH_LOG = LOGS_DIR / "crash.log"
PATCH_NOTES = BASE_DIR / "patch_notes.txt"


def ensure_workspace() -> None:
    for path in [
        ASSETS_DIR,
        TEXTURES_DIR,
        EXPORTS_DIR,
        EXPORT_STATES_DIR,
        EXPORT_CANDIDATES_DIR,
        EXPORT_PASSED_DIR,
        PACKAGE_CANDIDATES_DIR,
        PACKAGE_PASSED_DIR,
        MODEL_CANDIDATES_DIR,
        MODEL_PASSED_DIR,
        SCREENSHOTS_DIR,
        PROJECTS_DIR,
        LOGS_DIR,
        REPORTS_DIR,
        TOOLS_DIR,
        CACHE_DIR,
        CONVERTED_DIR,
        EXTRACTED_TEXTURES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    PATCH_NOTES.write_text(
        f"{APP_NAME} {APP_VERSION}\n"
        "- Added formal import/export validation reports and JSON report output\n"
        "- Added CLI commands for validate, convert, and package workflows\n"
        "- Added explicit rig-safe versus static-only export labeling\n"
        "- Added candidate versus passed-test export state folders\n"
        "- Added preview screenshot output for validated runs\n"
        "- Packages latest logs and validation reports with Panda-ready exports\n",
        encoding="utf-8",
    )
    LATEST_LOG.write_text("", encoding="utf-8")


class Logger:
    def __init__(self, path: Path):
        self.path = path

    def write(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {message}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        print(line, end="")


LOGGER = Logger(LATEST_LOG)


def write_crash(exc: BaseException) -> None:
    text = "\n".join(
        [
            f"{APP_NAME} {APP_VERSION}",
            datetime.now().isoformat(timespec="seconds"),
            "",
            traceback.format_exc(),
        ]
    )
    CRASH_LOG.write_text(text, encoding="utf-8")


@dataclass
class TextureSettings:
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0
    blur: float = 0.0
    seamless_offset_x: float = 0.0
    seamless_offset_y: float = 0.0
    invert: bool = False
    grayscale: bool = False


@dataclass
class ProjectState:
    model_path: Optional[Path] = None
    model_scene: Optional[trimesh.Scene] = None
    texture_path: Optional[Path] = None
    texture_image: Optional[Image.Image] = None
    texture_preview: Optional[Image.Image] = None
    texture_settings: TextureSettings = field(default_factory=TextureSettings)
    status: str = "Ready"
    project_file: Optional[Path] = None
    converted_model_path: Optional[Path] = None
    import_backend: str = "unknown"
    import_note: str = ""
    texture_note: str = ""
    scene_dirty: bool = False
    validation_state: str = "candidate"
    last_report_path: Optional[Path] = None


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    created_at: str
    operation: str
    validation_state: str
    source_path: Optional[str]
    source_exists: bool
    source_format: Optional[str]
    import_backend: str
    output_path: Optional[str]
    output_exists: bool
    requested_export_format: Optional[str]
    export_backend: Optional[str]
    rig_status: str
    rig_reason: str
    axis_note: str
    texture_status: str
    scene_dirty: bool
    mesh_stats: dict
    screenshot_path: Optional[str]
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        severities = {issue.severity for issue in self.issues}
        if "error" in severities:
            return "failed"
        if "warning" in severities:
            return "passed_with_warnings"
        return "passed"

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "operation": self.operation,
            "validation_state": self.validation_state,
            "status": self.status,
            "source_path": self.source_path,
            "source_exists": self.source_exists,
            "source_format": self.source_format,
            "import_backend": self.import_backend,
            "output_path": self.output_path,
            "output_exists": self.output_exists,
            "requested_export_format": self.requested_export_format,
            "export_backend": self.export_backend,
            "rig_status": self.rig_status,
            "rig_reason": self.rig_reason,
            "axis_note": self.axis_note,
            "texture_status": self.texture_status,
            "scene_dirty": self.scene_dirty,
            "mesh_stats": self.mesh_stats,
            "screenshot_path": self.screenshot_path,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def summary_lines(self) -> list[str]:
        lines = [
            f"Validation status: {self.status}",
            f"Operation: {self.operation}",
            f"State label: {self.validation_state}",
            f"Source exists: {self.source_exists}",
            f"Output exists: {self.output_exists}",
            f"Source format: {self.source_format or 'unknown'}",
            f"Import backend: {self.import_backend}",
            f"Export backend: {self.export_backend or 'n/a'}",
            f"Rig handling: {self.rig_status}",
            f"Rig note: {self.rig_reason}",
            f"Axis/orientation: {self.axis_note}",
            f"Texture status: {self.texture_status}",
        ]
        if self.screenshot_path:
            lines.append(f"Preview screenshot: {self.screenshot_path}")
        if self.issues:
            lines.append("")
            lines.append("Warnings and errors:")
            for issue in self.issues:
                lines.append(f"- [{issue.severity}] {issue.message}")
        return lines


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_stem(path: Optional[Path], fallback: str = "asset") -> str:
    if not path:
        return fallback
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in path.stem).strip("_") or fallback


def prepare_output_path(path: Path, overwrite: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")
    return path


def detect_axis_note(source_format: Optional[str], import_backend: str) -> str:
    if source_format in {".fbx", ".dae"} or import_backend == "assimp-py":
        return "Coordinate system may vary. If the model looks Y-up in Panda3D, test a +90 degree X rotation."
    if source_format in {".obj"}:
        return "OBJ is treated as static geometry. Verify forward axis and scale once in Panda3D."
    return "GLB/GLTF is the preferred Panda3D runtime path. Verify forward axis once with the target loader."


def determine_rig_status(project: ProjectState, export_format: Optional[str]) -> tuple[str, str]:
    fmt = (export_format or "").lower()
    if fmt != "glb":
        return "static-only", "Only GLB export can be claimed rig-safe in this workstation."
    if project.scene_dirty:
        return "static-only", "Mesh-edit operations were applied, so rig and animation safety can no longer be guaranteed."
    if project.converted_model_path and project.converted_model_path.exists():
        return "rig-safe", "Export can reuse the untouched cached GLB generated from FBX2glTF."
    if project.model_path and project.model_path.suffix.lower() == ".glb" and project.model_path.exists():
        return "rig-safe", "Export can reuse the untouched source GLB."
    return "static-only", "This path requires scene re-export, so rig and animation preservation are not guaranteed."


def describe_texture_status(project: ProjectState) -> str:
    if project.texture_path and project.texture_path.exists():
        return f"Texture ready: {project.texture_path.name}"
    if project.texture_note:
        return project.texture_note
    return "No texture was detected or loaded."


def write_validation_report(report: ValidationReport, stem: str) -> Path:
    out = REPORTS_DIR / f"{stem}_{timestamp_slug()}_{report.operation}.json"
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return out


class BackendManager:
    @staticmethod
    def has_assimp_py() -> bool:
        return importlib.util.find_spec("assimp_py") is not None

    @staticmethod
    def find_fbx2gltf() -> Optional[Path]:
        candidates = [
            TOOLS_DIR / "FBX2glTF.exe",
            TOOLS_DIR / "FBX2glTF-windows-x86_64.exe",
            TOOLS_DIR / "FBX2glTF" / "FBX2glTF.exe",
            TOOLS_DIR / "fbx2gltf" / "FBX2glTF.exe",
            TOOLS_DIR / "FBX2glTF-windows-x86_64" / "FBX2glTF.exe",
            TOOLS_DIR / "FBX2glTF-windows-x86_64" / "FBX2glTF-windows-x86_64" / "FBX2glTF-windows-x86_64.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        for pattern in ("FBX2glTF.exe", "FBX2glTF*.exe"):
            for candidate in TOOLS_DIR.rglob(pattern):
                return candidate
        return None

    @staticmethod
    def status_lines() -> list[str]:
        lines = []
        lines.append(f"assimp-py: {'ready' if BackendManager.has_assimp_py() else 'missing'}")
        exe = BackendManager.find_fbx2gltf()
        lines.append(f"FBX2glTF: {exe if exe else 'missing'}")
        return lines

    @staticmethod
    def install_assimp_py() -> tuple[bool, str]:
        cmd = [sys.executable, "-m", "pip", "install", "-U", "assimp-py"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        ok = proc.returncode == 0
        text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return ok, text.strip()

    @staticmethod
    def install_fbx2gltf_from_script() -> tuple[bool, str]:
        script = BASE_DIR / "install_fbx_tools.bat"
        if not script.exists():
            return False, f"Missing installer script: {script}"
        try:
            proc = subprocess.run(["cmd", "/c", str(script)], capture_output=True, text=True)
            ok = proc.returncode == 0
            text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
            return ok, text.strip()
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def convert_fbx_to_glb(src: Path) -> Path:
        exe = BackendManager.find_fbx2gltf()
        if not exe:
            raise RuntimeError(
                "FBX2glTF is not installed. Run install_fbx_tools.bat or use the Repair Backends button."
            )
        out = CONVERTED_DIR / f"{src.stem}_converted.glb"
        cmd = [str(exe), "--binary", "--input", str(src), "--output", str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out.exists():
            details = ((proc.stdout or "") + ("\n" + (proc.stderr or ""))).strip()
            raise RuntimeError(f"FBX2glTF conversion failed.\n\n{details}")
        return out


class MeshPipeline:
    @staticmethod
    def _pil_from_any_image(obj) -> Optional[Image.Image]:
        if obj is None:
            return None
        if isinstance(obj, Image.Image):
            return obj.convert("RGBA")
        if hasattr(obj, "read"):
            try:
                obj.seek(0)
            except Exception:
                pass
            try:
                return Image.open(obj).convert("RGBA")
            except Exception:
                return None
        if isinstance(obj, np.ndarray):
            arr = obj
            if arr.ndim == 2:
                return Image.fromarray(arr.astype(np.uint8), mode="L").convert("RGBA")
            if arr.ndim == 3 and arr.shape[2] in (3, 4):
                mode = "RGB" if arr.shape[2] == 3 else "RGBA"
                return Image.fromarray(arr.astype(np.uint8), mode=mode).convert("RGBA")
        try:
            return Image.open(obj).convert("RGBA")
        except Exception:
            return None

    @staticmethod
    def _material_image_candidates(material) -> list[tuple[Image.Image, Optional[str]]]:
        images: list[tuple[Image.Image, Optional[str]]] = []
        if material is None:
            return images
        materials = [material]
        if hasattr(material, "to_simple"):
            try:
                materials.append(material.to_simple())
            except Exception:
                pass
        for mat in materials:
            for attr in ("image", "baseColorTexture", "emissiveTexture"):
                source = getattr(mat, attr, None)
                img = MeshPipeline._pil_from_any_image(source)
                if img is not None:
                    filename = getattr(source, "filename", None) or getattr(mat, "name", None)
                    images.append((img, filename))
        return images

    @staticmethod
    def _find_nearby_texture(path: Path) -> Optional[Path]:
        if not path.exists():
            return None
        candidates = [p for p in path.parent.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}]
        if not candidates:
            return None
        stem = path.stem.lower()
        keywords = [stem, "diffuse", "albedo", "basecolor", "base_color", "color", "skin", "body"]
        ranked = []
        for candidate in candidates:
            name = candidate.stem.lower()
            score = 0
            if name == stem:
                score += 100
            for word in keywords:
                if word and word in name:
                    score += 10
            ranked.append((score, candidate))
        ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))
        if ranked and ranked[0][0] > 0:
            return ranked[0][1]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def detect_texture(scene: trimesh.Scene, model_path: Path) -> tuple[Optional[Image.Image], Optional[Path], str]:
        for geom in scene.geometry.values():
            visual = getattr(geom, "visual", None)
            if visual is None:
                continue
            candidates = MeshPipeline._material_image_candidates(getattr(visual, "material", None))
            if not candidates and getattr(visual, "kind", None) == "texture":
                to_color = getattr(visual, "to_color", None)
                if callable(to_color):
                    try:
                        color_vis = to_color()
                        if getattr(color_vis, "main_color", None) is not None:
                            pass
                    except Exception:
                        pass
            for idx, (img, filename) in enumerate(candidates):
                img = img.convert("RGBA")
                if filename:
                    candidate_path = Path(str(filename))
                    if not candidate_path.is_absolute():
                        candidate_path = model_path.parent / candidate_path
                    if candidate_path.exists():
                        return img, candidate_path, "Texture detected from model material."
                out_path = EXTRACTED_TEXTURES_DIR / f"{model_path.stem}_auto_{idx}.png"
                img.save(out_path)
                return img, out_path, "Embedded texture extracted from the loaded model."
        nearby = MeshPipeline._find_nearby_texture(model_path)
        if nearby and nearby.exists():
            return TexturePipeline.load_image(nearby), nearby, "Texture auto-linked from a nearby image file."
        return None, None, ""

    @staticmethod
    def load_asset(path: Path) -> tuple[trimesh.Scene, Optional[Path], str, str]:
        suffix = path.suffix.lower()
        if suffix == ".fbx":
            try:
                converted = BackendManager.convert_fbx_to_glb(path)
                scene = trimesh.load(converted, force="scene")
                note = (
                    "FBX was converted to GLB with FBX2glTF. The cached GLB preserves the runtime asset path for Panda3D. "
                    "If you only convert/package, rigging and animations stay in the cached GLB. If you use mesh-edit tools, the export becomes static geometry."
                )
                return MeshPipeline._ensure_scene(scene), converted, note, "FBX2glTF"
            except Exception as convert_exc:
                if BackendManager.has_assimp_py():
                    try:
                        scene = MeshPipeline.load_scene_via_assimp(path)
                        note = (
                            "FBX loaded through assimp-py fallback. This is suitable for inspection and static mesh export, "
                            "but rigging and animation are not preserved by the workstation mesh-edit path."
                        )
                        return scene, None, note, "assimp-py"
                    except Exception as assimp_exc:
                        raise RuntimeError(
                            "FBX import is not ready in this environment. Install the bundled FBX2glTF tool for the preferred rig-safe path, "
                            "or repair the assimp-py backend for static fallback import."
                        ) from assimp_exc
                raise RuntimeError(
                    "FBX support is not ready in this workstation yet. Install the bundled FBX2glTF tool for rig-preserving conversion, "
                    "or install assimp-py for static fallback import."
                ) from convert_exc
        if suffix == ".dae":
            if BackendManager.has_assimp_py():
                scene = MeshPipeline.load_scene_via_assimp(path)
                note = "DAE loaded through assimp-py fallback."
                return scene, None, note, "assimp-py"
            try:
                scene = trimesh.load(path, force="scene")
                return MeshPipeline._ensure_scene(scene), None, "DAE loaded through trimesh backend.", "trimesh"
            except Exception as exc:
                raise RuntimeError(
                    "DAE import needs assimp-py or a working trimesh backend in this build."
                ) from exc
        scene = trimesh.load(path, force="scene")
        return MeshPipeline._ensure_scene(scene), None, "Loaded directly.", "trimesh"

    @staticmethod
    def load_scene(path: Path) -> trimesh.Scene:
        scene, _converted, _note, _backend = MeshPipeline.load_asset(path)
        return scene

    @staticmethod
    def _coerce_vector_array(data, label: str) -> np.ndarray:
        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            return np.empty((0, 3), dtype=np.float64)
        if arr.ndim == 1:
            if arr.size % 3 != 0:
                raise RuntimeError(f"{label} data could not be reshaped into XYZ triplets.")
            arr = arr.reshape((-1, 3))
        elif arr.ndim == 2:
            if arr.shape[1] < 3:
                raise RuntimeError(f"{label} data did not contain at least 3 components per entry.")
            arr = arr[:, :3]
        else:
            arr = arr.reshape((-1, arr.shape[-1]))
            if arr.shape[1] < 3:
                raise RuntimeError(f"{label} data did not contain at least 3 components per entry.")
            arr = arr[:, :3]
        return arr

    @staticmethod
    def _coerce_face_array(data) -> np.ndarray:
        arr = np.asarray(data, dtype=np.int64)
        if arr.size == 0:
            return np.empty((0, 3), dtype=np.int64)
        if arr.ndim == 1:
            if arr.size % 3 != 0:
                raise RuntimeError("Face index data was not triangulated and could not be reshaped.")
            return arr.reshape((-1, 3))
        if arr.ndim > 2:
            arr = arr.reshape((-1, arr.shape[-1]))
        if arr.shape[1] < 3:
            raise RuntimeError("Face index data did not contain at least 3 vertices per polygon.")
        if arr.shape[1] == 3:
            return arr
        tris = []
        for poly in arr:
            base = int(poly[0])
            for j in range(1, len(poly) - 1):
                tris.append([base, int(poly[j]), int(poly[j + 1])])
        return np.asarray(tris, dtype=np.int64)

    @staticmethod
    def load_scene_via_assimp(path: Path) -> trimesh.Scene:
        import assimp_py

        flags = int(
            assimp_py.Process_Triangulate
            | assimp_py.Process_JoinIdenticalVertices
            | assimp_py.Process_SortByPType
        )
        scene_ai = assimp_py.import_file(str(path), flags)
        scene = trimesh.Scene()
        added = 0
        for i, mesh in enumerate(scene_ai.meshes or []):
            verts = MeshPipeline._coerce_vector_array(getattr(mesh, "vertices", []), "Vertex")
            face_source = getattr(mesh, "indices", None)
            faces = MeshPipeline._coerce_face_array(face_source) if face_source is not None else None
            if verts.size == 0 or faces is None or faces.size == 0:
                continue
            normals = None
            normal_source = getattr(mesh, "normals", None)
            if normal_source is not None and len(normal_source):
                normals = MeshPipeline._coerce_vector_array(normal_source, "Normal")
            tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
            if normals is not None and len(normals) == len(tm.vertices):
                tm.vertex_normals = normals
            scene.add_geometry(tm, geom_name=f"mesh_{i}")
            added += 1
        if added == 0:
            raise RuntimeError("assimp-py loaded the file, but no triangulated mesh geometry was found.")
        return scene

    @staticmethod
    def _ensure_scene(obj: trimesh.Scene | trimesh.Trimesh) -> trimesh.Scene:
        if isinstance(obj, trimesh.Scene):
            return obj
        scene = trimesh.Scene()
        scene.add_geometry(obj)
        return scene

    @staticmethod
    def combined_mesh(scene: trimesh.Scene) -> trimesh.Trimesh:
        try:
            geom = scene.to_geometry()
        except Exception:
            geom = None
        if isinstance(geom, trimesh.Trimesh):
            return geom.copy()
        if isinstance(geom, list):
            meshes = [m for m in geom if isinstance(m, trimesh.Trimesh)]
            if meshes:
                return trimesh.util.concatenate(meshes)
        geometry = list(scene.geometry.values())
        meshes = [m.copy() for m in geometry if isinstance(m, trimesh.Trimesh)]
        if not meshes:
            raise RuntimeError("No mesh geometry was found in the scene.")
        return trimesh.util.concatenate(meshes)

    @staticmethod
    def scene_stats(scene: trimesh.Scene) -> dict:
        try:
            mesh = MeshPipeline.combined_mesh(scene)
        except Exception:
            return {
                "geometry_present": False,
                "vertices": 0,
                "faces": 0,
                "bounds_min": None,
                "bounds_max": None,
                "extents": None,
                "watertight": False,
            }
        extents = mesh.extents.tolist() if mesh.extents is not None else None
        bounds_min = mesh.bounds[0].tolist() if mesh.bounds is not None else None
        bounds_max = mesh.bounds[1].tolist() if mesh.bounds is not None else None
        return {
            "geometry_present": True,
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "bounds_min": [round(v, 4) for v in bounds_min] if bounds_min else None,
            "bounds_max": [round(v, 4) for v in bounds_max] if bounds_max else None,
            "extents": [round(v, 4) for v in extents] if extents else None,
            "watertight": bool(mesh.is_watertight),
        }

    @staticmethod
    def recenter(scene: trimesh.Scene) -> trimesh.Scene:
        mesh = MeshPipeline.combined_mesh(scene)
        mesh.apply_translation(-mesh.centroid)
        new_scene = trimesh.Scene()
        new_scene.add_geometry(mesh)
        return new_scene

    @staticmethod
    def apply_scale(scene: trimesh.Scene, factor: float) -> trimesh.Scene:
        mesh = MeshPipeline.combined_mesh(scene)
        mesh.apply_scale(factor)
        new_scene = trimesh.Scene()
        new_scene.add_geometry(mesh)
        return new_scene

    @staticmethod
    def apply_rotation(scene: trimesh.Scene, rx_deg: float, ry_deg: float, rz_deg: float) -> trimesh.Scene:
        mesh = MeshPipeline.combined_mesh(scene)
        rx = trimesh.transformations.rotation_matrix(math.radians(rx_deg), [1, 0, 0])
        ry = trimesh.transformations.rotation_matrix(math.radians(ry_deg), [0, 1, 0])
        rz = trimesh.transformations.rotation_matrix(math.radians(rz_deg), [0, 0, 1])
        transform = trimesh.transformations.concatenate_matrices(rz, ry, rx)
        mesh.apply_transform(transform)
        new_scene = trimesh.Scene()
        new_scene.add_geometry(mesh)
        return new_scene

    @staticmethod
    def fix_normals(scene: trimesh.Scene) -> trimesh.Scene:
        mesh = MeshPipeline.combined_mesh(scene)
        mesh.remove_unreferenced_vertices()
        mesh.remove_duplicate_faces()
        mesh.fix_normals(multibody=True)
        new_scene = trimesh.Scene()
        new_scene.add_geometry(mesh)
        return new_scene

    @staticmethod
    def export_scene(scene: trimesh.Scene, out_path: Path) -> Path:
        suffix = out_path.suffix.lower()
        if suffix == ".glb":
            try:
                data = scene.export(file_type="glb")
                if isinstance(data, (bytes, bytearray)):
                    out_path.write_bytes(data)
                    return out_path
            except Exception:
                pass
        mesh = MeshPipeline.combined_mesh(scene)
        if suffix == ".glb":
            data = mesh.export(file_type="glb")
            out_path.write_bytes(data)
        elif suffix == ".obj":
            out_path.write_text(mesh.export(file_type="obj"), encoding="utf-8")
        elif suffix == ".stl":
            out_path.write_bytes(mesh.export(file_type="stl"))
        elif suffix == ".ply":
            out_path.write_bytes(mesh.export(file_type="ply"))
        else:
            raise RuntimeError(f"Unsupported export format: {suffix}")
        return out_path

    @staticmethod
    def preview_image(scene: trimesh.Scene, size: tuple[int, int] = (512, 512)) -> Image.Image:
        try:
            png = scene.save_image(resolution=size, visible=True)
            return Image.open(io.BytesIO(png)).convert("RGBA")
        except Exception:
            try:
                mesh = MeshPipeline.combined_mesh(scene)
                png = mesh.scene().save_image(resolution=size, visible=True)
                return Image.open(io.BytesIO(png)).convert("RGBA")
            except Exception:
                return MeshPipeline.fallback_preview(MeshPipeline.combined_mesh(scene), size=size)

    @staticmethod
    def fallback_preview(mesh: trimesh.Trimesh, size: tuple[int, int] = (512, 512)) -> Image.Image:
        width, height = size
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        if verts.size == 0:
            return Image.new("RGBA", size, (12, 16, 22, 255))
        if verts.ndim == 1:
            if verts.size % 3 != 0:
                return Image.new("RGBA", size, (12, 16, 22, 255))
            verts = verts.reshape((-1, 3))
        x = verts[:, 0]
        y = verts[:, 1]
        z = verts[:, 2]
        min_x, max_x = float(x.min()), float(x.max())
        min_y, max_y = float(y.min()), float(y.max())
        min_z, max_z = float(z.min()), float(z.max())
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        span_z = max(max_z - min_z, 1e-6)
        margin = max(24, min(width, height) // 14)
        draw_w = max(1, width - margin * 2)
        draw_h = max(1, height - margin * 2)
        img = Image.new("RGBA", size, (12, 16, 22, 255))
        px = img.load()
        stride = max(1, len(verts) // 4000)
        for vx, vy, vz in verts[::stride]:
            sx = int(((vx - min_x) / span_x) * draw_w + margin)
            sy = int(((vy - min_y) / span_y) * draw_h + margin)
            bright = int(((vz - min_z) / span_z) * 180 + 75)
            for ox in range(-1, 2):
                for oy in range(-1, 2):
                    tx = max(0, min(width - 1, sx + ox))
                    ty = max(0, min(height - 1, (height - 1) - sy + oy))
                    px[tx, ty] = (bright, min(255, bright + 25), 255, 255)
        return img


class TexturePipeline:
    @staticmethod
    def load_image(path: Path) -> Image.Image:
        return Image.open(path).convert("RGBA")

    @staticmethod
    def make_seamless_offset(img: Image.Image, offset_x: float, offset_y: float) -> Image.Image:
        width, height = img.size
        dx = int(width * offset_x)
        dy = int(height * offset_y)
        shifted = ImageChops.offset(img, dx, dy)
        return shifted

    @staticmethod
    def apply_settings(img: Image.Image, settings: TextureSettings) -> Image.Image:
        out = img.copy().convert("RGBA")
        out = TexturePipeline.make_seamless_offset(out, settings.seamless_offset_x, settings.seamless_offset_y)
        if settings.grayscale:
            gray = ImageOps.grayscale(out)
            out = Image.merge("RGBA", (gray, gray, gray, out.getchannel("A")))
        if settings.invert:
            rgb = ImageOps.invert(out.convert("RGB"))
            out = Image.merge("RGBA", (*rgb.split(), out.getchannel("A")))
        if settings.blur > 0:
            out = out.filter(ImageFilter.GaussianBlur(radius=settings.blur))
        out = ImageEnhance.Brightness(out).enhance(settings.brightness)
        out = ImageEnhance.Contrast(out).enhance(settings.contrast)
        out = ImageEnhance.Color(out).enhance(settings.saturation)
        out = ImageEnhance.Sharpness(out).enhance(settings.sharpness)
        return out

    @staticmethod
    def to_height(img: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(img)
        return gray

    @staticmethod
    def to_normal_map(img: Image.Image, strength: float = 2.0) -> Image.Image:
        gray = np.asarray(ImageOps.grayscale(img).convert("L"), dtype=np.float32) / 255.0
        dx = np.gradient(gray, axis=1)
        dy = np.gradient(gray, axis=0)
        nx = -dx * strength
        ny = -dy * strength
        nz = np.ones_like(gray)
        length = np.sqrt(nx * nx + ny * ny + nz * nz)
        nx /= np.maximum(length, 1e-6)
        ny /= np.maximum(length, 1e-6)
        nz /= np.maximum(length, 1e-6)
        rgb = np.dstack(((nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)))
        rgb = (rgb * 255.0).clip(0, 255).astype(np.uint8)
        alpha = np.full((rgb.shape[0], rgb.shape[1], 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgb, alpha], axis=2)
        return Image.fromarray(rgba, "RGBA")

    @staticmethod
    def tile_preview(img: Image.Image, cols: int = 3, rows: int = 3, tile_size: int = 256) -> Image.Image:
        tile = img.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (tile_size * cols, tile_size * rows), (15, 18, 24, 255))
        for y in range(rows):
            for x in range(cols):
                canvas.paste(tile, (x * tile_size, y * tile_size))
        return canvas


def save_scene_screenshot(scene: trimesh.Scene, stem: str) -> Path:
    out = SCREENSHOTS_DIR / f"{stem}_{timestamp_slug()}.png"
    MeshPipeline.preview_image(scene, size=(768, 768)).save(out)
    return out


def build_validation_report(
    project: ProjectState,
    operation: str,
    output_path: Optional[Path] = None,
    requested_export_format: Optional[str] = None,
    export_backend: Optional[str] = None,
    validation_state: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> ValidationReport:
    source_path = project.model_path
    source_exists = bool(source_path and source_path.exists())
    source_format = source_path.suffix.lower() if source_path else None
    output_exists = bool(output_path and output_path.exists())
    rig_status, rig_reason = determine_rig_status(project, requested_export_format)
    texture_status = describe_texture_status(project)
    mesh_stats: dict = {}
    issues: list[ValidationIssue] = []
    if project.model_scene is not None:
        try:
            mesh_stats = MeshPipeline.scene_stats(project.model_scene)
            if (not mesh_stats.get("geometry_present", True)) or (mesh_stats.get("vertices", 0) == 0 and mesh_stats.get("faces", 0) == 0):
                issues.append(ValidationIssue("warning", "geometry_missing", "The loaded asset has no mesh geometry. This can be valid for animation-only content, but preview and static export are limited."))
        except Exception as exc:
            issues.append(ValidationIssue("error", "mesh_stats_failed", f"Mesh inspection failed: {exc}"))
    else:
        issues.append(ValidationIssue("error", "scene_missing", "No model scene is currently loaded."))
    if not source_exists:
        issues.append(ValidationIssue("error", "source_missing", "Source model file is missing."))
    if output_path is not None and not output_exists:
        issues.append(ValidationIssue("error", "output_missing", "Expected output file was not created."))
    if source_format == ".obj":
        issues.append(ValidationIssue("warning", "obj_static", "OBJ is handled as static geometry only."))
    if project.import_backend == "assimp-py":
        issues.append(ValidationIssue("warning", "assimp_partial", "assimp-py import is useful for inspection, but rig and animation preservation are not guaranteed."))
    if source_format == ".fbx" and not project.converted_model_path:
        issues.append(ValidationIssue("warning", "fbx_fallback", "FBX was not converted through FBX2glTF, so only static export is considered safe."))
    if project.scene_dirty:
        issues.append(ValidationIssue("warning", "scene_dirty", "Mesh edits were applied. Export is now labeled static-only unless the untouched GLB path is reused."))
    if "No texture" in texture_status:
        issues.append(ValidationIssue("warning", "texture_missing", "No texture was auto-detected or loaded for this asset."))
    axis_note = detect_axis_note(source_format, project.import_backend)
    report = ValidationReport(
        created_at=datetime.now().isoformat(timespec="seconds"),
        operation=operation,
        validation_state=validation_state or project.validation_state,
        source_path=str(source_path) if source_path else None,
        source_exists=source_exists,
        source_format=source_format,
        import_backend=project.import_backend,
        output_path=str(output_path) if output_path else None,
        output_exists=output_exists,
        requested_export_format=requested_export_format,
        export_backend=export_backend,
        rig_status=rig_status,
        rig_reason=rig_reason,
        axis_note=axis_note,
        texture_status=texture_status,
        scene_dirty=project.scene_dirty,
        mesh_stats=mesh_stats,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        issues=issues,
    )
    return report


def export_project_model(project: ProjectState, out_path: Path, overwrite: bool = False) -> tuple[Path, str, str, str]:
    if project.model_scene is None or project.model_path is None:
        raise RuntimeError("Load a model first.")
    out_path = prepare_output_path(out_path, overwrite=overwrite)
    fmt = out_path.suffix.lower().lstrip(".")
    rig_status, rig_reason = determine_rig_status(project, fmt)
    if fmt == "glb" and rig_status == "rig-safe":
        if project.converted_model_path and project.converted_model_path.exists():
            shutil.copy2(project.converted_model_path, out_path)
            return out_path, "copy-converted-glb", rig_status, rig_reason
        if project.model_path.suffix.lower() == ".glb" and project.model_path.exists():
            shutil.copy2(project.model_path, out_path)
            return out_path, "copy-source-glb", rig_status, rig_reason
    MeshPipeline.export_scene(project.model_scene, out_path)
    return out_path, "trimesh-export", rig_status, rig_reason


class PandaPackager:
    @staticmethod
    def create_package(
        project: ProjectState,
        export_mesh: Path,
        export_texture: Optional[Path],
        target_dir: Path,
        report: Optional[ValidationReport] = None,
        validation_state: str = "candidate",
    ) -> Path:
        package_dir = target_dir / f"package_{timestamp_slug()}"
        models_dir = package_dir / "models"
        textures_dir = package_dir / "textures"
        logs_dir = package_dir / "logs"
        models_dir.mkdir(parents=True, exist_ok=True)
        textures_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(export_mesh, models_dir / export_mesh.name)
        copied_texture = None
        if export_texture and export_texture.exists():
            copied_texture = textures_dir / export_texture.name
            shutil.copy2(export_texture, copied_texture)
        if LATEST_LOG.exists():
            shutil.copy2(LATEST_LOG, logs_dir / LATEST_LOG.name)
        if CRASH_LOG.exists():
            shutil.copy2(CRASH_LOG, logs_dir / CRASH_LOG.name)
        loader_script = package_dir / "panda_loader_example.py"
        model_name = export_mesh.name.replace("\\", "/")
        texture_line = ""
        if copied_texture:
            texture_line = (
                f"    tex = loader.loadTexture('textures/{copied_texture.name}')\n"
                f"    model.setTexture(tex, 1)\n"
            )
        loader_script.write_text(
            "from direct.showbase.ShowBase import ShowBase\n"
            "\n"
            "class App(ShowBase):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
            f"        model = self.loader.loadModel('models/{model_name}')\n"
            "        model.reparentTo(self.render)\n"
            "        model.setPos(0, 10, 0)\n"
            "        model.setScale(1)\n"
            + texture_line +
            "        self.disableMouse()\n"
            "\n"
            "app = App()\n"
            "app.run()\n",
            encoding="utf-8",
        )
        metadata = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "validation_state": validation_state,
            "source_model": str(project.model_path) if project.model_path else None,
            "source_texture": str(project.texture_path) if project.texture_path else None,
            "export_mesh": str(export_mesh.name),
            "export_texture": str(copied_texture.name) if copied_texture else None,
            "notes": [
                "Use panda3d-gltf for .glb/.gltf runtime loading.",
                "Panda3D uses forward slashes in asset paths.",
                "BAM is an efficient shipping format, but glTF is the preferred interchange format.",
                "When the exported mesh is GLB, materials are expected to travel inside that file. The copied texture is kept editable for later swaps.",
            ],
        }
        (package_dir / "package.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if report is not None:
            (package_dir / "validation_report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return package_dir


class WorkstationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.state = ProjectState()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry(f"{VIRTUAL_WIDTH}x{VIRTUAL_HEIGHT}")
        self.minsize(1280, 720)
        self.configure(bg="#10131a")
        self.option_add("*tearOff", False)
        self.model_preview_photo: Optional[ImageTk.PhotoImage] = None
        self.texture_preview_photo: Optional[ImageTk.PhotoImage] = None

        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self.set_status("Workspace ready")
        LOGGER.write("Application started")

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Root.TFrame", background="#10131a")
        style.configure("Panel.TFrame", background="#171c24")
        style.configure("Sidebar.TFrame", background="#0c0f15")
        style.configure("Hero.TLabel", background="#171c24", foreground="#ecf2ff", font=("Segoe UI", 16, "bold"))
        style.configure("Body.TLabel", background="#171c24", foreground="#b7c4d6", font=("Segoe UI", 10))
        style.configure("Sidebar.TLabel", background="#0c0f15", foreground="#d8e3f0", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background="#10131a", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 10), background="#182030", foreground="#dce6f5")
        style.map("TNotebook.Tab", background=[("selected", "#243149")])
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 8))
        style.configure("Tool.TButton", font=("Segoe UI", 9), padding=(8, 6))
        style.configure("Dark.Horizontal.TScale", background="#171c24")
        style.configure("TLabelframe", background="#171c24", foreground="#e6edf7")
        style.configure("TLabelframe.Label", background="#171c24", foreground="#e6edf7", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#111722", foreground="#dce6f5", fieldbackground="#111722", rowheight=24)
        style.map("Treeview", background=[("selected", "#30435f")])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=12)
        root.pack(fill="both", expand=True)

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", width=260)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        main = ttk.Frame(root, style="Panel.TFrame")
        main.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._build_sidebar(sidebar)
        self._build_main(main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Sidebar.TFrame", padding=14)
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, style="Sidebar.TLabel").pack(anchor="w")
        ttk.Label(top, text="Import • Edit • Package • Validate", style="Body.TLabel").pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(parent, style="Sidebar.TFrame", padding=(12, 8))
        actions.pack(fill="x")
        ttk.Button(actions, text="Open Model", style="Action.TButton", command=self.open_model).pack(fill="x", pady=4)
        ttk.Button(actions, text="Open Texture", style="Action.TButton", command=self.open_texture).pack(fill="x", pady=4)
        ttk.Button(actions, text="Save Project", style="Action.TButton", command=self.save_project).pack(fill="x", pady=4)
        ttk.Button(actions, text="Load Project", style="Action.TButton", command=self.load_project).pack(fill="x", pady=4)
        ttk.Button(actions, text="Package for Panda3D", style="Action.TButton", command=self.package_for_panda).pack(fill="x", pady=4)
        ttk.Button(actions, text="Save Validation Report", style="Action.TButton", command=self.save_validation_report).pack(fill="x", pady=4)
        ttk.Button(actions, text="Backend Status", style="Action.TButton", command=self.show_backend_status).pack(fill="x", pady=4)
        ttk.Button(actions, text="Repair Backends", style="Action.TButton", command=self.repair_backends).pack(fill="x", pady=4)

        sys_box = ttk.LabelFrame(parent, text="Workstation", padding=12)
        sys_box.pack(fill="x", padx=12, pady=12)
        self.summary_vars = {
            "model": tk.StringVar(value="No model"),
            "texture": tk.StringVar(value="No texture"),
            "project": tk.StringVar(value="Unsaved project"),
            "rig": tk.StringVar(value="Rig handling: no model"),
            "state": tk.StringVar(value="Validation state: candidate"),
        }
        ttk.Label(sys_box, textvariable=self.summary_vars["model"], style="Body.TLabel", wraplength=220).pack(anchor="w", pady=2)
        ttk.Label(sys_box, textvariable=self.summary_vars["texture"], style="Body.TLabel", wraplength=220).pack(anchor="w", pady=2)
        ttk.Label(sys_box, textvariable=self.summary_vars["project"], style="Body.TLabel", wraplength=220).pack(anchor="w", pady=2)
        ttk.Label(sys_box, textvariable=self.summary_vars["rig"], style="Body.TLabel", wraplength=220).pack(anchor="w", pady=2)
        ttk.Label(sys_box, textvariable=self.summary_vars["state"], style="Body.TLabel", wraplength=220).pack(anchor="w", pady=2)

        tips = ttk.LabelFrame(parent, text="Pipeline Notes", padding=12)
        tips.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tip_text = (
            "Preferred Panda3D path:\n"
            "FBX/OBJ source -> GLB export -> Panda3D loadModel()\n\n"
            "GLB/GLTF is the clean interchange target. BAM remains the fast shipping format once your Panda3D build pipeline is in place."
        )
        ttk.Label(tips, text=tip_text, style="Body.TLabel", wraplength=220, justify="left").pack(anchor="nw")

    def _build_main(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.pack(fill="x")
        ttk.Label(header, text="Panda3D Asset Workstation", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Unified importer, texture lab, mesh prep, and Panda-ready export packaging.",
            style="Body.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        content = ttk.Frame(parent, style="Panel.TFrame", padding=(16, 0, 16, 16))
        content.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)

        self.tab_import = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_mesh = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_texture = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_export = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)

        self.notebook.add(self.tab_import, text="Inspect")
        self.notebook.add(self.tab_mesh, text="Mesh")
        self.notebook.add(self.tab_texture, text="Texture Lab")
        self.notebook.add(self.tab_export, text="Export")

        self._build_import_tab()
        self._build_mesh_tab()
        self._build_texture_tab()
        self._build_export_tab()

        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(16, 0, 16, 12))
        footer.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status_var, style="Body.TLabel").pack(anchor="w")

    def _build_import_tab(self) -> None:
        left = ttk.Frame(self.tab_import, style="Panel.TFrame")
        left.pack(side="left", fill="both", expand=True)
        right = ttk.LabelFrame(self.tab_import, text="Preview", padding=10)
        right.pack(side="left", fill="both", expand=False, padx=(12, 0))

        toolbar = ttk.Frame(left, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Open Model", style="Tool.TButton", command=self.open_model).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Refresh Stats", style="Tool.TButton", command=self.refresh_model_info).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Open Texture", style="Tool.TButton", command=self.open_texture).pack(side="left")
        ttk.Button(toolbar, text="Write Report", style="Tool.TButton", command=self.save_validation_report).pack(side="left", padx=(6, 0))

        self.info_text = tk.Text(left, height=16, bg="#111722", fg="#e5edf8", insertbackground="#e5edf8", relief="flat")
        self.info_text.pack(fill="both", expand=True)

        self.preview_label = tk.Label(right, bg="#0d1117", width=512, height=512)
        self.preview_label.pack()

    def _build_mesh_tab(self) -> None:
        controls = ttk.LabelFrame(self.tab_mesh, text="Transform Tools", padding=12)
        controls.pack(fill="x")
        row1 = ttk.Frame(controls, style="Panel.TFrame")
        row1.pack(fill="x")
        ttk.Button(row1, text="Recenter to Origin", style="Tool.TButton", command=self.recenter_model).pack(side="left", padx=(0, 8))
        ttk.Button(row1, text="Fix Normals", style="Tool.TButton", command=self.fix_normals).pack(side="left", padx=(0, 8))
        ttk.Button(row1, text="Refresh", style="Tool.TButton", command=self.refresh_model_info).pack(side="left")

        row2 = ttk.Frame(controls, style="Panel.TFrame")
        row2.pack(fill="x", pady=(12, 0))
        self.scale_var = tk.StringVar(value="1.0")
        ttk.Label(row2, text="Scale", style="Body.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.scale_var, width=10).pack(side="left", padx=(6, 8))
        ttk.Button(row2, text="Apply Scale", style="Tool.TButton", command=self.apply_scale).pack(side="left", padx=(0, 12))

        self.rot_x = tk.StringVar(value="0")
        self.rot_y = tk.StringVar(value="0")
        self.rot_z = tk.StringVar(value="0")
        for label, variable in [("Rot X", self.rot_x), ("Rot Y", self.rot_y), ("Rot Z", self.rot_z)]:
            ttk.Label(row2, text=label, style="Body.TLabel").pack(side="left", padx=(0, 4))
            ttk.Entry(row2, textvariable=variable, width=8).pack(side="left", padx=(0, 8))
        ttk.Button(row2, text="Apply Rotation", style="Tool.TButton", command=self.apply_rotation).pack(side="left")

        notes = ttk.LabelFrame(self.tab_mesh, text="Panda Alignment Notes", padding=12)
        notes.pack(fill="both", expand=True, pady=(12, 0))
        text = (
            "For Panda3D, GLB is the preferred interchange export.\n\n"
            "If a source comes in with Y-up assumptions, test a +90 X rotation. Assimp-based imports can arrive rotated depending on source format and importer path."
        )
        ttk.Label(notes, text=text, style="Body.TLabel", justify="left", wraplength=900).pack(anchor="nw")

    def _build_texture_tab(self) -> None:
        left = ttk.LabelFrame(self.tab_texture, text="Texture Controls", padding=12)
        left.pack(side="left", fill="y")
        center = ttk.LabelFrame(self.tab_texture, text="Texture Preview", padding=12)
        center.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.texture_controls = {}
        sliders = [
            ("brightness", "Brightness", 0.0, 3.0, 1.0),
            ("contrast", "Contrast", 0.0, 3.0, 1.0),
            ("saturation", "Saturation", 0.0, 3.0, 1.0),
            ("sharpness", "Sharpness", 0.0, 4.0, 1.0),
            ("blur", "Blur", 0.0, 6.0, 0.0),
            ("seamless_offset_x", "Seamless X", -1.0, 1.0, 0.0),
            ("seamless_offset_y", "Seamless Y", -1.0, 1.0, 0.0),
        ]
        for key, label, min_v, max_v, default in sliders:
            row = ttk.Frame(left, style="Panel.TFrame")
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, style="Body.TLabel").pack(anchor="w")
            var = tk.DoubleVar(value=default)
            scale = ttk.Scale(row, variable=var, from_=min_v, to=max_v, orient="horizontal", command=lambda *_: self.update_texture_preview())
            scale.pack(fill="x")
            self.texture_controls[key] = var

        self.tex_invert = tk.BooleanVar(value=False)
        self.tex_gray = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="Invert", variable=self.tex_invert, command=self.update_texture_preview).pack(anchor="w", pady=(8, 2))
        ttk.Checkbutton(left, text="Grayscale", variable=self.tex_gray, command=self.update_texture_preview).pack(anchor="w", pady=2)
        ttk.Button(left, text="Save Texture", style="Tool.TButton", command=self.save_texture).pack(fill="x", pady=(12, 4))
        ttk.Button(left, text="Save Height Map", style="Tool.TButton", command=self.save_height_map).pack(fill="x", pady=4)
        ttk.Button(left, text="Save Normal Map", style="Tool.TButton", command=self.save_normal_map).pack(fill="x", pady=4)

        self.texture_preview_label = tk.Label(center, bg="#0d1117", width=768, height=768)
        self.texture_preview_label.pack(fill="both", expand=True)

    def _build_export_tab(self) -> None:
        box = ttk.LabelFrame(self.tab_export, text="Export Settings", padding=12)
        box.pack(fill="x")
        row = ttk.Frame(box, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Format", style="Body.TLabel").pack(side="left")
        self.export_format = tk.StringVar(value="glb")
        combo = ttk.Combobox(row, textvariable=self.export_format, values=EXPORT_FORMATS, state="readonly", width=10)
        combo.pack(side="left", padx=(8, 12))
        ttk.Button(row, text="Export Model", style="Tool.TButton", command=self.export_model).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Package for Panda3D", style="Tool.TButton", command=self.package_for_panda).pack(side="left")
        self.export_status_var = tk.StringVar(value="Current export profile: static-only")
        ttk.Label(box, textvariable=self.export_status_var, style="Body.TLabel", wraplength=900).pack(anchor="w", pady=(10, 0))

        notes = ttk.LabelFrame(self.tab_export, text="Runtime Notes", padding=12)
        notes.pack(fill="both", expand=True, pady=(12, 0))
        text = (
            "Target runtime:\n"
            "- Prefer GLB/GLTF for interchange.\n"
            "- Panda3D can cache models to BAM for fast shipping builds.\n"
            "- Use relative paths with forward slashes.\n"
            "- Panda3D's panda3d-gltf plug-in is the preferred loader path for glTF assets.\n"
            "- GLB can be labeled rig-safe only when the untouched native/cached GLB path is reused."
        )
        ttk.Label(notes, text=text, style="Body.TLabel", wraplength=900, justify="left").pack(anchor="nw")

    def _bind_shortcuts(self) -> None:
        self.bind("<Escape>", lambda _e: self.show_settings())
        self.bind("h", lambda _e: self.toggle_sidebar())
        self.bind("H", lambda _e: self.toggle_sidebar())

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.state.status = text
        LOGGER.write(text)

    def update_summary(self) -> None:
        self.summary_vars["model"].set(f"Model: {self.state.model_path.name if self.state.model_path else 'None'}")
        self.summary_vars["texture"].set(f"Texture: {self.state.texture_path.name if self.state.texture_path else 'None'}")
        if self.state.project_file:
            self.summary_vars["project"].set(f"Project: {self.state.project_file.name}")
        else:
            self.summary_vars["project"].set("Project: Unsaved")
        rig_status, rig_reason = determine_rig_status(self.state, self.export_format.get().lower() if hasattr(self, "export_format") else "glb")
        self.summary_vars["rig"].set(f"Rig handling: {rig_status}")
        self.summary_vars["state"].set(f"Validation state: {self.state.validation_state}")
        if hasattr(self, "export_status_var"):
            self.export_status_var.set(f"Current export profile: {rig_status} | {rig_reason}")

    def reset_texture_controls(self) -> None:
        defaults = TextureSettings()
        for key, value in defaults.__dict__.items():
            if key in self.texture_controls:
                self.texture_controls[key].set(value)
        self.tex_invert.set(False)
        self.tex_gray.set(False)
        self.state.texture_settings = defaults

    def autoload_texture_from_model(self) -> None:
        if not self.state.model_scene or not self.state.model_path:
            return
        texture_probe_path = self.state.converted_model_path or self.state.model_path
        image, texture_path, texture_note = MeshPipeline.detect_texture(self.state.model_scene, texture_probe_path)
        self.state.texture_note = texture_note
        if image is None:
            return
        self.state.texture_path = texture_path
        self.state.texture_image = image
        self.reset_texture_controls()
        self.update_texture_preview()

    def _capture_validation_evidence(self, operation: str, output_path: Optional[Path] = None, requested_export_format: Optional[str] = None, export_backend: Optional[str] = None) -> ValidationReport:
        if self.state.model_scene is None:
            raise RuntimeError("Load a model first.")
        requested_export_format = requested_export_format or (self.export_format.get().lower() if hasattr(self, "export_format") else "glb")
        screenshot = save_scene_screenshot(self.state.model_scene, f"{safe_stem(self.state.model_path)}_{operation}")
        report = build_validation_report(
            self.state,
            operation=operation,
            output_path=output_path,
            requested_export_format=requested_export_format,
            export_backend=export_backend,
            screenshot_path=screenshot,
        )
        self.state.last_report_path = write_validation_report(report, safe_stem(self.state.model_path))
        return report

    def _render_report(self, report: ValidationReport) -> None:
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0", "\n".join(report.summary_lines()))
        if report.mesh_stats:
            self.info_text.insert(tk.END, "\n\nMesh stats:\n")
            for key, value in report.mesh_stats.items():
                self.info_text.insert(tk.END, f"{key}: {value}\n")
        if self.state.import_note:
            self.info_text.insert(tk.END, f"\nImport note:\n{self.state.import_note}\n")
        if self.state.texture_note:
            self.info_text.insert(tk.END, f"\nTexture note:\n{self.state.texture_note}\n")
        self.update_summary()

    def open_model(self) -> None:
        path = filedialog.askopenfilename(title="Open model", filetypes=SUPPORTED_IMPORTS, initialdir=str(PROJECTS_DIR))
        if not path:
            return
        try:
            model_path = Path(path)
            scene, converted_model_path, import_note, import_backend = MeshPipeline.load_asset(model_path)
            self.state.model_path = model_path
            self.state.model_scene = scene
            self.state.converted_model_path = converted_model_path
            self.state.import_backend = import_backend
            self.state.import_note = import_note
            self.state.texture_note = ""
            self.state.scene_dirty = False
            self.state.validation_state = "candidate"
            self.state.texture_path = None
            self.state.texture_image = None
            self.state.texture_preview = None
            self.autoload_texture_from_model()
            report = self._capture_validation_evidence("import")
            self._render_report(report)
            self.render_model_preview()
            self.update_summary()
            status = f"Loaded model: {model_path.name}"
            if self.state.texture_path:
                status += f" | texture ready: {self.state.texture_path.name}"
            self.set_status(status)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.set_status("Model load failed")

    def open_texture(self) -> None:
        path = filedialog.askopenfilename(title="Open texture", filetypes=SUPPORTED_TEXTURES, initialdir=str(TEXTURES_DIR))
        if not path:
            return
        try:
            tex_path = Path(path)
            img = TexturePipeline.load_image(tex_path)
            self.state.texture_path = tex_path
            self.state.texture_image = img
            self.state.texture_note = "Texture loaded manually."
            self.reset_texture_controls()
            self.update_texture_preview()
            self.update_summary()
            self.set_status(f"Loaded texture: {tex_path.name}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.set_status("Texture load failed")

    def refresh_model_info(self) -> None:
        if not self.state.model_scene or not self.state.model_path:
            self.info_text.delete("1.0", tk.END)
            self.info_text.insert("1.0", "No model loaded.")
            return
        report = self._capture_validation_evidence("inspect")
        self._render_report(report)

    def render_model_preview(self) -> None:
        if not self.state.model_scene:
            return
        img = MeshPipeline.preview_image(self.state.model_scene, size=(512, 512))
        preview = img.resize((512, 512), Image.Resampling.LANCZOS)
        self.model_preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.model_preview_photo)

    def _read_texture_settings(self) -> TextureSettings:
        return TextureSettings(
            brightness=self.texture_controls["brightness"].get(),
            contrast=self.texture_controls["contrast"].get(),
            saturation=self.texture_controls["saturation"].get(),
            sharpness=self.texture_controls["sharpness"].get(),
            blur=self.texture_controls["blur"].get(),
            seamless_offset_x=self.texture_controls["seamless_offset_x"].get(),
            seamless_offset_y=self.texture_controls["seamless_offset_y"].get(),
            invert=self.tex_invert.get(),
            grayscale=self.tex_gray.get(),
        )

    def update_texture_preview(self) -> None:
        if not self.state.texture_image:
            return
        settings = self._read_texture_settings()
        self.state.texture_settings = settings
        processed = TexturePipeline.apply_settings(self.state.texture_image, settings)
        self.state.texture_preview = processed
        preview = TexturePipeline.tile_preview(processed, cols=2, rows=2, tile_size=320)
        preview = preview.resize((640, 640), Image.Resampling.LANCZOS)
        self.texture_preview_photo = ImageTk.PhotoImage(preview)
        self.texture_preview_label.configure(image=self.texture_preview_photo)

    def recenter_model(self) -> None:
        if not self.state.model_scene:
            return
        self.state.model_scene = MeshPipeline.recenter(self.state.model_scene)
        self.state.scene_dirty = True
        self.refresh_model_info()
        self.render_model_preview()
        self.set_status("Model recentered")

    def fix_normals(self) -> None:
        if not self.state.model_scene:
            return
        self.state.model_scene = MeshPipeline.fix_normals(self.state.model_scene)
        self.state.scene_dirty = True
        self.refresh_model_info()
        self.render_model_preview()
        self.set_status("Normals repaired")

    def apply_scale(self) -> None:
        if not self.state.model_scene:
            return
        try:
            factor = float(self.scale_var.get())
            self.state.model_scene = MeshPipeline.apply_scale(self.state.model_scene, factor)
            self.state.scene_dirty = True
            self.refresh_model_info()
            self.render_model_preview()
            self.set_status(f"Scale applied: {factor}")
        except ValueError:
            messagebox.showerror(APP_NAME, "Scale must be a number.")

    def apply_rotation(self) -> None:
        if not self.state.model_scene:
            return
        try:
            rx = float(self.rot_x.get())
            ry = float(self.rot_y.get())
            rz = float(self.rot_z.get())
            self.state.model_scene = MeshPipeline.apply_rotation(self.state.model_scene, rx, ry, rz)
            self.state.scene_dirty = True
            self.refresh_model_info()
            self.render_model_preview()
            self.set_status(f"Rotation applied: ({rx}, {ry}, {rz})")
        except ValueError:
            messagebox.showerror(APP_NAME, "Rotation values must be numbers.")

    def _save_processed_texture(self, img: Image.Image, title: str, suffix: str) -> Optional[Path]:
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialdir=str(TEXTURES_DIR),
        )
        if not path:
            return None
        out = Path(path)
        img.save(out)
        self.set_status(f"Saved {suffix}: {out.name}")
        return out

    def save_texture(self) -> None:
        if not self.state.texture_preview:
            return
        self._save_processed_texture(self.state.texture_preview, "Save texture", "texture")

    def save_height_map(self) -> None:
        if not self.state.texture_preview:
            return
        height = TexturePipeline.to_height(self.state.texture_preview)
        self._save_processed_texture(height, "Save height map", "height map")

    def save_normal_map(self) -> None:
        if not self.state.texture_preview:
            return
        normal = TexturePipeline.to_normal_map(self.state.texture_preview)
        self._save_processed_texture(normal, "Save normal map", "normal map")

    def export_model(self) -> Optional[Path]:
        if not self.state.model_scene or not self.state.model_path:
            messagebox.showinfo(APP_NAME, "Load a model first.")
            return None
        ext = self.export_format.get().lower()
        out_path = filedialog.asksaveasfilename(
            title="Export model",
            defaultextension=f".{ext}",
            filetypes=[(ext.upper(), f"*.{ext}")],
            initialdir=str(MODEL_CANDIDATES_DIR),
            initialfile=f"{self.state.model_path.stem}_candidate_{timestamp_slug()}.{ext}",
        )
        if not out_path:
            return None
        try:
            out_path_obj = Path(out_path)
            result, export_backend, rig_status, _rig_reason = export_project_model(self.state, out_path_obj, overwrite=False)
            report = self._capture_validation_evidence("export", output_path=result, requested_export_format=ext, export_backend=export_backend)
            self._render_report(report)
            self.set_status(f"Exported model: {result.name} | {rig_status}")
            return result
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.set_status("Export failed")
            return None

    def _export_preview_texture_to_temp(self) -> Optional[Path]:
        img = self.state.texture_preview or self.state.texture_image
        if not img:
            return None
        temp = EXPORTS_DIR / "_latest_preview_texture.png"
        img.save(temp)
        return temp

    def package_for_panda(self) -> None:
        if not self.state.model_scene or not self.state.model_path:
            return
        try:
            package_root = PACKAGE_CANDIDATES_DIR
            package_root.mkdir(parents=True, exist_ok=True)
            mesh_path = package_root / f"{safe_stem(self.state.model_path)}_panda_ready.glb"
            mesh_path, export_backend, _rig_status, _rig_reason = export_project_model(self.state, mesh_path, overwrite=True)
            tex_path = self._export_preview_texture_to_temp()
            report = self._capture_validation_evidence("package", output_path=mesh_path, requested_export_format="glb", export_backend=export_backend)
            self._render_report(report)
            package_dir = PandaPackager.create_package(
                self.state,
                mesh_path,
                tex_path,
                PACKAGE_CANDIDATES_DIR,
                report=report,
                validation_state=self.state.validation_state,
            )
            self.set_status(f"Created Panda package: {package_dir.name}")
            messagebox.showinfo(APP_NAME, f"Package created:\n{package_dir}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.set_status("Packaging failed")

    def save_validation_report(self) -> None:
        if not self.state.model_scene or not self.state.model_path:
            messagebox.showinfo(APP_NAME, "Load a model first.")
            return
        try:
            report = self._capture_validation_evidence("validate")
            self._render_report(report)
            messagebox.showinfo(APP_NAME, f"Validation report written:\n{self.state.last_report_path}")
            self.set_status(f"Validation report saved: {Path(self.state.last_report_path).name if self.state.last_report_path else 'report'}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.set_status("Validation report failed")

    def show_backend_status(self) -> None:
        messagebox.showinfo(APP_NAME, "\n".join(BackendManager.status_lines()))

    def repair_backends(self) -> None:
        self.set_status("Repairing backends")
        notes: list[str] = []
        ok_assimp, out_assimp = BackendManager.install_assimp_py()
        notes.append(f"assimp-py: {'ok' if ok_assimp else 'failed'}")
        if out_assimp:
            LOGGER.write(out_assimp[-8000:])
        ok_fbx, out_fbx = BackendManager.install_fbx2gltf_from_script()
        notes.append(f"FBX2glTF installer: {'ok' if ok_fbx else 'failed'}")
        if out_fbx:
            LOGGER.write(out_fbx[-8000:])
        self.refresh_model_info()
        self.set_status("Backend repair complete")
        messagebox.showinfo(APP_NAME, "\n".join(notes + ["", *BackendManager.status_lines()]))

    def save_project(self) -> None:
        project_path = filedialog.asksaveasfilename(
            title="Save project",
            defaultextension=".paw.json",
            filetypes=[("Panda Asset Workstation", "*.paw.json")],
            initialdir=str(PROJECTS_DIR),
        )
        if not project_path:
            return
        payload = {
            "model_path": str(self.state.model_path) if self.state.model_path else None,
            "converted_model_path": str(self.state.converted_model_path) if self.state.converted_model_path else None,
            "import_note": self.state.import_note,
            "texture_note": self.state.texture_note,
            "scene_dirty": self.state.scene_dirty,
            "texture_path": str(self.state.texture_path) if self.state.texture_path else None,
            "texture_settings": self.state.texture_settings.__dict__,
        }
        Path(project_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.state.project_file = Path(project_path)
        self.update_summary()
        self.set_status(f"Project saved: {self.state.project_file.name}")

    def load_project(self) -> None:
        project_path = filedialog.askopenfilename(
            title="Load project",
            filetypes=[("Panda Asset Workstation", "*.paw.json")],
            initialdir=str(PROJECTS_DIR),
        )
        if not project_path:
            return
        payload = json.loads(Path(project_path).read_text(encoding="utf-8"))
        self.state.project_file = Path(project_path)
        model_path = payload.get("model_path")
        texture_path = payload.get("texture_path")
        if model_path and Path(model_path).exists():
            self.state.model_path = Path(model_path)
            self.state.model_scene, self.state.converted_model_path, self.state.import_note, self.state.import_backend = MeshPipeline.load_asset(self.state.model_path)
            if payload.get("converted_model_path") and Path(payload["converted_model_path"]).exists():
                self.state.converted_model_path = Path(payload["converted_model_path"])
            self.state.scene_dirty = bool(payload.get("scene_dirty", False))
            if payload.get("import_note"):
                self.state.import_note = payload.get("import_note")
            if payload.get("texture_note"):
                self.state.texture_note = payload.get("texture_note")
            self.refresh_model_info()
            self.render_model_preview()
        if texture_path and Path(texture_path).exists():
            self.state.texture_path = Path(texture_path)
            self.state.texture_image = TexturePipeline.load_image(self.state.texture_path)
        elif self.state.model_scene and self.state.model_path:
            self.autoload_texture_from_model()
        if payload.get("texture_settings"):
            self.state.texture_settings = TextureSettings(**payload["texture_settings"])
            for key, value in self.state.texture_settings.__dict__.items():
                if key in self.texture_controls:
                    self.texture_controls[key].set(value)
            self.tex_invert.set(self.state.texture_settings.invert)
            self.tex_gray.set(self.state.texture_settings.grayscale)
            if self.state.texture_image:
                self.update_texture_preview()
        self.update_summary()
        if self.state.model_scene:
            report = self._capture_validation_evidence("load_project")
            self._render_report(report)
        self.set_status(f"Project loaded: {self.state.project_file.name}")

    def toggle_sidebar(self) -> None:
        # Minimal placeholder: cycles notebook visibility to emulate HUD toggle behavior.
        current = self.notebook.winfo_viewable()
        if current:
            self.notebook.pack_forget()
            self.set_status("Workbench panels hidden")
        else:
            self.notebook.pack(fill="both", expand=True)
            self.set_status("Workbench panels shown")

    def show_settings(self) -> None:
        top = tk.Toplevel(self)
        top.title("Settings")
        top.configure(bg="#171c24")
        top.geometry("420x220")
        ttk.Label(top, text="Workstation Settings", style="Hero.TLabel").pack(anchor="w", padx=16, pady=(16, 8))
        ttk.Label(
            top,
            text="This shell reserves Esc for settings and H for panel toggle. Add controller bindings and Panda preview integration in the next iteration.",
            style="Body.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", padx=16)
        ttk.Button(top, text="Close", style="Tool.TButton", command=top.destroy).pack(anchor="e", padx=16, pady=16)


def create_demo_assets() -> dict[str, Path]:
    cube = trimesh.creation.box(extents=(1.2, 1.0, 1.6))
    cube.visual.vertex_colors = [160, 210, 255, 255]
    demo_mesh = PROJECTS_DIR / "demo_cube.glb"
    demo_mesh.write_bytes(cube.export(file_type="glb"))

    size = 256
    img = Image.new("RGBA", (size, size), (34, 39, 56, 255))
    px = img.load()
    for y in range(size):
        for x in range(size):
            c = 30 + int(20 * math.sin(x * 0.09) + 20 * math.cos(y * 0.12))
            g = min(255, max(0, c + ((x // 16 + y // 16) % 2) * 18))
            px[x, y] = (g, min(255, g + 24), min(255, g + 48), 255)
    demo_tex = TEXTURES_DIR / "demo_panel.png"
    img.save(demo_tex)
    return {"mesh": demo_mesh, "texture": demo_tex}


def load_project_state_from_model(model_path: Path, texture_path: Optional[Path] = None) -> ProjectState:
    scene, converted_model_path, import_note, import_backend = MeshPipeline.load_asset(model_path)
    project = ProjectState(
        model_path=model_path,
        model_scene=scene,
        converted_model_path=converted_model_path,
        import_backend=import_backend,
        import_note=import_note,
        validation_state="candidate",
    )
    image, detected_texture_path, texture_note = MeshPipeline.detect_texture(scene, converted_model_path or model_path)
    if texture_path and texture_path.exists():
        project.texture_path = texture_path
        project.texture_image = TexturePipeline.load_image(texture_path)
        project.texture_note = "Texture loaded from CLI argument."
    else:
        project.texture_path = detected_texture_path
        project.texture_image = image
        project.texture_note = texture_note
    if project.texture_image is not None:
        project.texture_preview = project.texture_image
    return project


def parse_cli(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate", help="Validate a source asset and write a JSON report.")
    validate_parser.add_argument("input", help="Path to the source asset.")
    validate_parser.add_argument("--texture", help="Optional texture override.", default=None)

    convert_parser = subparsers.add_parser("convert", help="Convert a source asset into GLB or OBJ.")
    convert_parser.add_argument("input", help="Path to the source asset.")
    convert_parser.add_argument("--out", required=True, help="Path to the output model file.")
    convert_parser.add_argument("--format", choices=["glb", "obj"], required=True, help="Requested output format.")
    convert_parser.add_argument("--texture", help="Optional texture override.", default=None)
    convert_parser.add_argument("--scale", type=float, default=1.0, help="Uniform scale factor.")
    convert_parser.add_argument("--rotate-x", type=float, default=0.0, help="Rotation around X in degrees.")
    convert_parser.add_argument("--rotate-y", type=float, default=0.0, help="Rotation around Y in degrees.")
    convert_parser.add_argument("--rotate-z", type=float, default=0.0, help="Rotation around Z in degrees.")
    convert_parser.add_argument("--overwrite", action="store_true", help="Allow overwriting an existing output path.")

    package_parser = subparsers.add_parser("package", help="Create a Panda3D-ready package for an asset.")
    package_parser.add_argument("input", help="Path to the source asset.")
    package_parser.add_argument("--out", required=True, help="Directory that will receive the package folder.")
    package_parser.add_argument("--texture", help="Optional texture override.", default=None)
    package_parser.add_argument("--overwrite", action="store_true", help="Allow overwriting the intermediate GLB if it already exists.")

    subparsers.add_parser("selftest", help="Run the built-in self-test.")
    return parser.parse_args(argv)


def print_cli_error(operation: str, input_path: Optional[str], exc: BaseException) -> int:
    message = str(exc).strip() or exc.__class__.__name__
    LOGGER.write(f"{operation} failed: {message}")
    print(
        json.dumps(
            {
                "operation": operation,
                "status": "failed",
                "input": input_path,
                "error": message,
            },
            indent=2,
        )
    )
    return 1


def run_cli_validate(args: argparse.Namespace) -> int:
    try:
        project = load_project_state_from_model(Path(args.input), Path(args.texture) if args.texture else None)
        screenshot = save_scene_screenshot(project.model_scene, f"{safe_stem(project.model_path)}_validate")
        report = build_validation_report(project, "validate", requested_export_format="glb", screenshot_path=screenshot)
        report_path = write_validation_report(report, safe_stem(project.model_path))
        LOGGER.write(f"Validation report written: {report_path}")
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.status != "failed" else 1
    except Exception as exc:
        return print_cli_error("validate", args.input, exc)


def run_cli_convert(args: argparse.Namespace) -> int:
    try:
        project = load_project_state_from_model(Path(args.input), Path(args.texture) if args.texture else None)
        if args.scale != 1.0:
            project.model_scene = MeshPipeline.apply_scale(project.model_scene, args.scale)
            project.scene_dirty = True
        if any(abs(v) > 1e-6 for v in (args.rotate_x, args.rotate_y, args.rotate_z)):
            project.model_scene = MeshPipeline.apply_rotation(project.model_scene, args.rotate_x, args.rotate_y, args.rotate_z)
            project.scene_dirty = True
        out_path = Path(args.out)
        if out_path.suffix.lower().lstrip(".") != args.format:
            out_path = out_path.with_suffix(f".{args.format}")
        result, export_backend, rig_status, rig_reason = export_project_model(project, out_path, overwrite=args.overwrite)
        screenshot = save_scene_screenshot(project.model_scene, f"{safe_stem(project.model_path)}_convert")
        report = build_validation_report(
            project,
            "convert",
            output_path=result,
            requested_export_format=args.format,
            export_backend=export_backend,
            screenshot_path=screenshot,
        )
        report_path = write_validation_report(report, safe_stem(project.model_path))
        LOGGER.write(f"Converted asset: {result}")
        LOGGER.write(f"Rig handling: {rig_status} | {rig_reason}")
        LOGGER.write(f"Validation report written: {report_path}")
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.status != "failed" else 1
    except Exception as exc:
        return print_cli_error("convert", args.input, exc)


def run_cli_package(args: argparse.Namespace) -> int:
    try:
        project = load_project_state_from_model(Path(args.input), Path(args.texture) if args.texture else None)
        package_root = Path(args.out)
        package_root.mkdir(parents=True, exist_ok=True)
        export_mesh = package_root / f"{safe_stem(project.model_path)}_panda_ready.glb"
        export_mesh, export_backend, rig_status, rig_reason = export_project_model(project, export_mesh, overwrite=args.overwrite)
        export_texture = None
        if project.texture_preview is not None:
            export_texture = package_root / f"{safe_stem(project.texture_path, 'texture')}_preview.png"
            project.texture_preview.save(export_texture)
        screenshot = save_scene_screenshot(project.model_scene, f"{safe_stem(project.model_path)}_package")
        report = build_validation_report(
            project,
            "package",
            output_path=export_mesh,
            requested_export_format="glb",
            export_backend=export_backend,
            screenshot_path=screenshot,
        )
        report_path = write_validation_report(report, safe_stem(project.model_path))
        package_dir = PandaPackager.create_package(
            project,
            export_mesh,
            export_texture,
            package_root,
            report=report,
            validation_state=project.validation_state,
        )
        LOGGER.write(f"Created package: {package_dir}")
        LOGGER.write(f"Rig handling: {rig_status} | {rig_reason}")
        LOGGER.write(f"Validation report written: {report_path}")
        print(json.dumps({"package_dir": str(package_dir), "report_path": str(report_path), "status": report.status}, indent=2))
        return 0 if report.status != "failed" else 1
    except Exception as exc:
        return print_cli_error("package", args.input, exc)


def run_selftest() -> int:
    ensure_workspace()
    LOGGER.write("Running self-test")
    demo = create_demo_assets()
    project = load_project_state_from_model(demo["mesh"], demo["texture"])
    scene = project.model_scene
    stats = MeshPipeline.scene_stats(scene)
    LOGGER.write(f"Scene stats: {stats}")
    scene = MeshPipeline.recenter(scene)
    scene = MeshPipeline.apply_rotation(scene, 90, 0, 0)
    scene = MeshPipeline.apply_scale(scene, 1.25)
    project.model_scene = scene
    project.scene_dirty = True
    export_mesh, export_backend, rig_status, rig_reason = export_project_model(project, EXPORTS_DIR / "selftest_output.glb", overwrite=True)
    LOGGER.write(f"Exported self-test mesh: {export_mesh}")

    img = TexturePipeline.load_image(demo["texture"])
    settings = TextureSettings(brightness=1.1, contrast=1.2, saturation=1.15, sharpness=1.5, seamless_offset_x=0.25)
    processed = TexturePipeline.apply_settings(img, settings)
    processed_path = EXPORTS_DIR / "selftest_texture.png"
    processed.save(processed_path)
    TexturePipeline.to_normal_map(processed).save(EXPORTS_DIR / "selftest_normal.png")
    LOGGER.write(f"Exported self-test textures: {processed_path}")

    project.texture_path = demo["texture"]
    project.texture_image = img
    project.texture_preview = processed
    screenshot = save_scene_screenshot(scene, "selftest")
    report = build_validation_report(
        project,
        "selftest",
        output_path=export_mesh,
        requested_export_format="glb",
        export_backend=export_backend,
        screenshot_path=screenshot,
    )
    report_path = write_validation_report(report, "selftest")
    package_dir = PandaPackager.create_package(project, export_mesh, processed_path, EXPORTS_DIR, report=report, validation_state=project.validation_state)
    LOGGER.write(f"Created self-test package: {package_dir}")
    LOGGER.write(f"Rig handling: {rig_status} | {rig_reason}")
    LOGGER.write(f"Self-test validation report: {report_path}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ensure_workspace()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return run_selftest()
    if argv:
        args = parse_cli(argv)
        if args.command == "validate":
            return run_cli_validate(args)
        if args.command == "convert":
            return run_cli_convert(args)
        if args.command == "package":
            return run_cli_package(args)
        if args.command == "selftest":
            return run_selftest()
    app = WorkstationApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        write_crash(exc)
        raise
