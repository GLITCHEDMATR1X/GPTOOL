from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extensions.panda_xr_vr_builder.core import BuilderObject, BuilderScene, create_vr_editing_proof_scene, run_vr_editing_proof
from extensions.panda_xr_vr_builder.visual_proof import run_vr_visual_proof


class PandaXrVrBuilderExtensionTests(unittest.TestCase):
    def test_vr_editing_operation_model_round_trips(self) -> None:
        scene = create_vr_editing_proof_scene()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "scene.manifest.json"
            scene.save_manifest(manifest)
            loaded = BuilderScene.load_manifest(manifest)

        self.assertGreaterEqual(len(loaded.objects), 11)
        self.assertEqual(len(loaded.connections), 3)
        self.assertEqual(len(loaded.path_nodes), 3)
        self.assertEqual(len(loaded.animations), 1)
        self.assertEqual(len(loaded.behaviors), 4)
        self.assertEqual(len(loaded.editor_panels), 3)
        self.assertTrue(loaded.grid.enabled)
        self.assertEqual(loaded.grid.cell_size, 0.25)
        self.assertGreaterEqual(len(loaded.operation_history), 40)
        self.assertTrue(any(obj.control_points for obj in loaded.objects))
        self.assertEqual(loaded.object_by_id("hand_light_ribbon_01").kind, "stroke")
        self.assertGreater(loaded.object_by_id("cube_01").metadata["last_resize_factor"], 1.0)
        self.assertNotEqual(loaded.object_by_id("cylinder_01").metadata["last_twist_degrees"], 0.0)
        self.assertTrue(loaded.object_by_id("grid_art_core").metadata["grid"]["snapped"])
        self.assertTrue(loaded.object_by_id("sphere_01").metadata["smoothing"]["enabled"])
        preview = loaded.evaluate_behaviors(1.0)
        self.assertIn("hand_light_ribbon_01", preview)
        self.assertIn("material", preview["hand_light_ribbon_01"])
        self.assertTrue(loaded.validate_scene()["ok"])

    def test_vr_builder_proof_exports_engine_ready_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proof = run_vr_editing_proof(Path(tmp))
            outputs = {key: Path(value) for key, value in proof["outputs"].items()}

            self.assertTrue(proof["ok"])
            self.assertTrue(proof["scene_quality"]["ok"])
            self.assertTrue(proof["export_quality"]["ok"])
            self.assertFalse(proof["requires_openxr"])
            self.assertTrue(outputs["obj"].exists())
            self.assertTrue(outputs["gltf"].exists())
            self.assertTrue(outputs["glb"].exists())
            self.assertTrue(outputs["metadata"].exists())

            gltf = json.loads(outputs["gltf"].read_text(encoding="utf-8"))
            self.assertEqual(gltf["asset"]["version"], "2.0")
            self.assertGreaterEqual(len(gltf["meshes"]), 11)
            self.assertGreaterEqual(len(gltf["materials"]), 11)
            self.assertEqual(len(gltf["scenes"][0]["extras"]["operation_history"]), proof["operation_count"])
            self.assertEqual(len(gltf["scenes"][0]["extras"]["behaviors"]), 4)
            self.assertEqual(len(gltf["scenes"][0]["extras"]["editor_panels"]), 3)
            self.assertEqual(gltf["scenes"][0]["extras"]["grid"]["cell_size"], 0.25)
            self.assertGreater(proof["performance"]["stroke_point_count"], 0)
            self.assertGreater(proof["performance"]["grid_occupied_cell_count"], 0)

            glb = outputs["glb"].read_bytes()
            magic, version, length = struct.unpack("<4sII", glb[:12])
            self.assertEqual(magic, b"glTF")
            self.assertEqual(version, 2)
            self.assertEqual(length, len(glb))

    def test_bridge_panda_xr_proof_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "bridge.py"), "panda-xr-proof", "--output", tmp, "--json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["object_count"], 11)
        self.assertEqual(data["behavior_count"], 4)
        self.assertEqual(data["editor_panel_count"], 3)
        self.assertGreaterEqual(data["operation_count"], 40)
        self.assertIn("glb", data["outputs"])
        self.assertTrue(data["scene_quality"]["ok"])

    def test_quality_gate_rejects_broken_references(self) -> None:
        scene = BuilderScene("broken")
        scene.create_object(BuilderObject("cube", "cube", {"size": 1.0}, sockets=[{"id": "top", "position": [0, 0, 0.5], "normal": [0, 0, 1]}]))
        scene.connections.append({"id": "bad_link", "from": {"object": "cube", "socket": "top"}, "to": {"object": "missing", "socket": "none"}})
        report = scene.validate_scene()
        self.assertFalse(report["ok"])
        self.assertTrue(any(item["code"] == "connection_object_missing" for item in report["errors"]))

    def test_bridge_panda_xr_quality_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proof = run_vr_editing_proof(Path(tmp))
            result = subprocess.run(
                [sys.executable, str(ROOT / "bridge.py"), "panda-xr-quality", proof["outputs"]["manifest"], "--json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["error_count"], 0)
        self.assertIn("triangle_estimate", data["metrics"])

    def test_visual_proof_software_backend_writes_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_vr_visual_proof(Path(tmp), width=960, height=540, seconds=0.1, backend="software")
            screenshot = Path(report["outputs"]["screenshot"])

            self.assertTrue(report["ok"])
            self.assertFalse(report["requires_openxr"])
            self.assertEqual(report["backend"], "software_projection")
            self.assertEqual(report["aspect_ratio"], "16:9")
            self.assertEqual(report["editor_panel_count"], 3)
            self.assertTrue(report["grid"]["snap_enabled"])
            self.assertTrue(screenshot.exists())
            self.assertGreater(screenshot.stat().st_size, 1000)
            self.assertGreater(report["image_metrics"]["non_background_ratio"], 0.015)


if __name__ == "__main__":
    unittest.main()
