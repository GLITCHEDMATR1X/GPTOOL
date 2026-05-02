import json
import tempfile
import unittest
from pathlib import Path

from p3dopenxr.builder_core import (
    BuilderObject,
    BuilderScene,
    create_proof_scene,
    run_deformable_object_proof,
)


class BuilderCoreTests(unittest.TestCase):
    def test_manifest_roundtrip_preserves_builder_metadata(self):
        scene = create_proof_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'scene.manifest.json'
            scene.save_manifest(path)
            loaded = BuilderScene.load_manifest(path)

        self.assertEqual(loaded.name, scene.name)
        self.assertEqual(len(loaded.objects), 6)
        self.assertEqual(len(loaded.connections), 3)
        self.assertEqual(len(loaded.path_nodes), 3)
        self.assertEqual(len(loaded.animations), 1)
        self.assertTrue(any(obj.control_points for obj in loaded.objects))

    def test_supported_builder_primitives_generate_geometry(self):
        cases = [
            BuilderObject('cube', 'cube', {'size': 1.0, 'subdivisions': 1}),
            BuilderObject('sphere', 'sphere', {'radius': 0.5, 'rings': 6, 'segments': 8}),
            BuilderObject('cylinder', 'cylinder', {'radius': 0.4, 'height': 1.2, 'segments': 8}),
            BuilderObject('capsule', 'capsule', {'radius': 0.3, 'cylinder_height': 0.8, 'segments': 8, 'hemisphere_rings': 3}),
            BuilderObject('floor', 'floor', {'width': 2.0, 'depth': 3.0, 'thickness': 0.1}),
            BuilderObject('wall', 'wall', {'width': 2.0, 'height': 2.5, 'thickness': 0.1}),
        ]

        for obj in cases:
            with self.subTest(kind=obj.kind):
                mesh = obj.world_mesh()
                self.assertGreater(len(mesh.vertices), 0)
                self.assertGreater(len(mesh.faces), 0)
                self.assertNotEqual(mesh.bounds()['min'], mesh.bounds()['max'])

    def test_proof_writes_exported_deformed_geometry_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof = run_deformable_object_proof(Path(tmp))
            obj_path = Path(proof['outputs']['export_obj'])
            metadata_path = Path(proof['outputs']['export_metadata'])
            gltf_path = Path(proof['outputs']['export_gltf'])
            bin_path = Path(proof['outputs']['export_bin'])
            glb_path = Path(proof['outputs']['export_glb'])

            self.assertTrue(proof['ok'])
            self.assertTrue(obj_path.exists())
            self.assertTrue(metadata_path.exists())
            self.assertTrue(gltf_path.exists())
            self.assertTrue(bin_path.exists())
            self.assertTrue(glb_path.exists())
            self.assertIn('v -1.250000', obj_path.read_text(encoding='utf-8'))
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            self.assertEqual(metadata['object_count'], 6)
            self.assertEqual(metadata['connection_count'], 3)
            self.assertEqual(metadata['path_node_count'], 3)
            self.assertTrue(any(item['control_point_count'] for item in metadata['objects']))
            self.assertIn('proof_cylinder', obj_path.read_text(encoding='utf-8'))
            self.assertIn('proof_capsule', obj_path.read_text(encoding='utf-8'))

            gltf = json.loads(gltf_path.read_text(encoding='utf-8'))
            self.assertEqual(gltf['asset']['version'], '2.0')
            self.assertEqual(len(gltf['meshes']), 6)
            self.assertEqual(gltf['scenes'][0]['extras']['path_nodes'][0]['id'], 'path_start')
            self.assertGreater(bin_path.stat().st_size, 0)
            self.assertEqual(glb_path.read_bytes()[:4], b'glTF')


if __name__ == '__main__':
    unittest.main()
