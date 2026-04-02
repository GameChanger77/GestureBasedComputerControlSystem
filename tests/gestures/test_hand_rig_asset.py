import os
import unittest

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from backend.gesture_remap.hand_rig import (
    HandEditorAssetManifest,
    HandMeshDeformer,
    HandPoseDisplayMapper,
    HandRigSolver,
    build_hand_assets,
    load_hand_mesh_assets,
)
from backend.gesture_remap.pose_templates import build_preview_templates
from frontend.widgets.editors.hand_rig_scene import HandRigScene

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class HandRigAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_manifest_loads_expected_asset_and_nodes(self):
        manifest = HandEditorAssetManifest.load()
        self.assertTrue(manifest.asset_path.exists())
        self.assertEqual(len(manifest.bone_nodes), 20)
        self.assertEqual(len(manifest.anchor_nodes), 21)
        self.assertIn("display_hand", manifest.mesh_asset_keys)
        self.assertIn("interaction_hand", manifest.mesh_asset_keys)
        self.assertIn("display_hand", manifest.mesh_nodes)
        self.assertIn("interaction_hand", manifest.mesh_nodes)
        self.assertEqual(manifest.neutral_anchor_positions.shape, (21, 3))

    def test_solver_preserves_segment_lengths(self):
        manifest = HandEditorAssetManifest.load()
        solver = HandRigSolver(manifest)
        updated = manifest.neutral_landmarks.copy()
        updated[8, 0] += 0.12
        updated[8, 1] += 0.08
        updated[12, 2] -= 0.06

        solved = solver.solve_landmarks(updated)
        for bone in manifest.bone_nodes:
            expected = solver.segment_lengths[(bone.start, bone.end)]
            actual = float(np.linalg.norm(solved[bone.end] - solved[bone.start]))
            self.assertAlmostEqual(actual, expected, places=4)

    def test_solver_reaches_stable_solution(self):
        manifest = HandEditorAssetManifest.load()
        solver = HandRigSolver(manifest)
        updated = manifest.neutral_landmarks.copy()
        updated[4, 0] -= 0.08
        updated[16, 1] -= 0.10

        once = solver.solve_landmarks(updated)
        twice = solver.solve_landmarks(once)
        self.assertTrue(np.allclose(once, twice, atol=1e-4))

    def test_solver_bends_entire_finger_when_tip_moves(self):
        manifest = HandEditorAssetManifest.load()
        solver = HandRigSolver(manifest)
        updated = manifest.neutral_landmarks.copy()
        updated[8, 1] -= 0.35
        updated[8, 2] += 0.12

        solved = solver.solve_landmarks(updated, edited_index=8)
        self.assertGreater(float(np.linalg.norm(solved[6] - manifest.neutral_landmarks[6])), 0.03)
        self.assertGreater(float(np.linalg.norm(solved[7] - manifest.neutral_landmarks[7])), 0.08)
        self.assertLessEqual(float(np.linalg.norm(solved[8] - updated[8])), 0.35)

    def test_solver_bends_upstream_and_downstream_for_intermediate_joint(self):
        manifest = HandEditorAssetManifest.load()
        solver = HandRigSolver(manifest)
        updated = manifest.neutral_landmarks.copy()
        updated[6, 1] -= 0.18
        updated[6, 2] += 0.10

        solved = solver.solve_landmarks(updated, edited_index=6)
        self.assertGreater(float(np.linalg.norm(solved[5] - manifest.neutral_landmarks[5])), 0.02)
        self.assertGreater(float(np.linalg.norm(solved[7] - manifest.neutral_landmarks[7])), 0.02)
        self.assertGreater(float(np.linalg.norm(solved[8] - manifest.neutral_landmarks[8])), 0.02)

    def test_display_mapper_aligns_reference_open_hand_to_asset(self):
        manifest = HandEditorAssetManifest.load()
        mapper = HandPoseDisplayMapper(manifest)
        reference = build_preview_templates()["switch_to_keyboard"].as_array()
        mapped = mapper.to_display(reference)
        self.assertTrue(np.allclose(mapped, manifest.neutral_landmarks, atol=1e-4))

    def test_display_mapper_produces_finite_display_points_for_preview_pose(self):
        manifest = HandEditorAssetManifest.load()
        mapper = HandPoseDisplayMapper(manifest)
        template = build_preview_templates()["mouse_move"].as_array()
        mapped = mapper.to_display(template)
        self.assertTrue(np.isfinite(mapped).all())
        self.assertEqual(mapped.shape, (21, 3))

    def test_visual_hand_deformer_moves_mesh_vertices(self):
        manifest = HandEditorAssetManifest.load()
        meshes = load_hand_mesh_assets(manifest)
        display_asset, interaction_asset = build_hand_assets(manifest, meshes)
        deformer = HandMeshDeformer(manifest, display_asset, interaction_asset)
        updated = manifest.neutral_landmarks.copy()
        updated[8, 0] += 0.18
        updated[12, 1] += 0.12
        vertices, normals, anchors = deformer.deform(updated)
        self.assertEqual(vertices.shape, display_asset.mesh.vertices.shape)
        self.assertEqual(normals.shape, display_asset.mesh.normals.shape)
        self.assertEqual(anchors.shape, manifest.neutral_anchor_positions.shape)
        self.assertGreater(float(np.max(np.abs(vertices - display_asset.mesh.vertices))), 0.0)

    def test_deformer_excludes_root_segments_from_finger_chain_weights(self):
        manifest = HandEditorAssetManifest.load()
        meshes = load_hand_mesh_assets(manifest)
        display_asset, interaction_asset = build_hand_assets(manifest, meshes)
        deformer = HandMeshDeformer(manifest, display_asset, interaction_asset)
        for bone_indices in deformer._chain_bone_indices:
            self.assertEqual(len(bone_indices), 3)
            self.assertTrue(np.all(deformer._bone_indices[bone_indices][:, 0] != 0))

    def test_display_mesh_is_not_lower_quality_than_interaction_mesh(self):
        manifest = HandEditorAssetManifest.load()
        meshes = load_hand_mesh_assets(manifest)
        self.assertGreaterEqual(len(meshes[manifest.display_mesh_key].vertices), len(meshes[manifest.interaction_mesh_key].vertices))
        self.assertGreaterEqual(len(meshes[manifest.display_mesh_key].indices), len(meshes[manifest.interaction_mesh_key].indices))

    def test_neutral_anchor_positions_track_landmarks_reasonably(self):
        manifest = HandEditorAssetManifest.load()
        distances = np.linalg.norm(manifest.neutral_anchor_positions - manifest.neutral_landmarks, axis=1)
        self.assertLessEqual(float(np.max(distances)), 1e-6)
        self.assertLessEqual(float(np.mean(distances)), 1e-6)

    def test_scene_constructs_with_fitted_camera(self):
        scene = HandRigScene()
        scene.set_landmarks(scene._manifest.neutral_landmarks.copy())
        self._app.processEvents()
        self.assertIsNone(scene.asset_error)
        self.assertTrue(scene._camera_fitted)
        self.assertIsNotNone(scene._visual_mesh)
        self.assertGreater(scene._visual_mesh.renderer.vertexCount(), 0)
        scene.close()

    def test_scene_updates_mesh_and_display_anchors_when_landmarks_change(self):
        scene = HandRigScene()
        neutral = scene._manifest.neutral_landmarks.copy()
        scene.set_landmarks(neutral)
        self._app.processEvents()
        baseline_vertices = scene._latest_visual_vertices.copy()

        updated = neutral.copy()
        updated[8, 0] += 0.18
        updated[12, 1] += 0.12
        scene.set_landmarks(updated)
        self._app.processEvents()

        self.assertGreater(float(np.max(np.abs(scene._latest_visual_vertices - baseline_vertices))), 0.0)
        self.assertTrue(np.allclose(scene._display_anchor_positions, scene._landmarks, atol=1e-5))
        scene.close()

    def test_scene_event_forwarding_updates_camera_controls(self):
        scene = HandRigScene()
        scene.resize(740, 694)
        scene._container.resize(740, 694)
        scene.set_landmarks(scene._manifest.neutral_landmarks.copy())
        self._app.processEvents()

        yaw_before = scene._camera_yaw
        distance_before = scene._camera_distance

        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(320.0, 280.0),
            QPointF(320.0, 280.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(360.0, 300.0),
            QPointF(360.0, 300.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(360.0, 300.0),
            QPointF(360.0, 300.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        wheel = QWheelEvent(
            QPointF(360.0, 300.0),
            QPointF(360.0, 300.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

        self.assertTrue(scene.eventFilter(scene._container, press))
        self.assertTrue(scene.eventFilter(scene._container, move))
        self.assertTrue(scene.eventFilter(scene._container, release))
        self.assertTrue(scene.eventFilter(scene._container, wheel))

        self.assertNotEqual(scene._camera_yaw, yaw_before)
        self.assertNotEqual(scene._camera_distance, distance_before)
        scene.close()


if __name__ == "__main__":
    unittest.main()
