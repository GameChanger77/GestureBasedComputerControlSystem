import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from frontend.widgets.gesture_pose_editor_dialog import GesturePoseEditorDialog


class GesturePoseEditorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_constructs_and_updates_landmarks(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        dialog = GesturePoseEditorDialog(definition, definition.preview_pose_template)
        self._app.processEvents()
        updated = definition.preview_pose_template.as_array().copy()
        updated[8, 0] += 0.05
        dialog._apply_landmarks(updated)
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertIsNone(dialog.hand_view.asset_error)
        dialog.close()

    def test_wrist_edit_bends_hand_without_global_translation(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        dialog = GesturePoseEditorDialog(definition, definition.preview_pose_template)
        self._app.processEvents()
        baseline = dialog._landmarks.copy()
        target = baseline[0].copy()
        target[1] += 0.12
        dialog._apply_single_landmark_edit(0, target)
        updated = dialog._landmarks
        wrist_delta = updated[0] - baseline[0]
        fingertip_delta = updated[8] - baseline[8]
        self.assertGreater(float(np.linalg.norm(wrist_delta)), 0.0)
        self.assertGreater(float(np.linalg.norm(fingertip_delta)), 0.0)
        self.assertFalse(np.allclose(wrist_delta, fingertip_delta, atol=1e-3))
        dialog.close()


if __name__ == "__main__":
    unittest.main()
