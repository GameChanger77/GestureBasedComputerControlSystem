import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig
from backend.gesture_remap.rule_overrides import GestureRuleOverride, RULE_OVERRIDE_KIND
from frontend.widgets.editors.gesture_custom_editor_dialog import GestureCustomEditorDialog


class GestureCustomEditorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_new_editor_defaults_to_rule_based(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        dialog = GestureCustomEditorDialog(definition, config_source={"finger_extension_angle": 155.0, "mouse_tracking_pending_frames": 1, "ending_frames": 2})
        self.assertEqual(dialog.selected_kind(), RULE_OVERRIDE_KIND)
        dialog.close()

    def test_existing_point_override_reopens_point_screen(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")
            store.set_override("mouse_move", definition.default_pose_template, matcher_config=PoseMatcherConfig())
            dialog = GestureCustomEditorDialog(definition, config_source={"finger_extension_angle": 155.0, "mouse_tracking_pending_frames": 1, "ending_frames": 2}, override_record=store.get("mouse_move"))
            self.assertEqual(dialog.selected_kind(), "point")
            dialog.close()

    def test_existing_rule_override_reopens_rule_screen(self):
        definition = BuiltInGestureRegistry.get("left_click")
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")
            store.set_rule_override(
                "left_click",
                GestureRuleOverride(
                    conditions=[{"op": "hand_exists", "hand": "dominant"}],
                    pending_frames=3,
                    ending_frames=2,
                ),
            )
            dialog = GestureCustomEditorDialog(
                definition,
                config_source={"pinch_threshold": 0.30, "click_pending_frames": 3, "ending_frames": 2},
                override_record=store.get("left_click"),
            )
            self.assertEqual(dialog.selected_kind(), RULE_OVERRIDE_KIND)
            dialog.close()

    def test_rule_based_save_returns_rule_payload(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        dialog = GestureCustomEditorDialog(definition, config_source={"finger_extension_angle": 155.0, "mouse_tracking_pending_frames": 1, "ending_frames": 2})
        self.assertTrue(dialog.rule_button.isCheckable())
        self.assertTrue(dialog.point_button.isCheckable())
        self.assertTrue(dialog.save_button.isEnabled())
        dialog._on_save_clicked()
        self.assertEqual(dialog.result_kind, RULE_OVERRIDE_KIND)
        self.assertIsNotNone(dialog.result_rule_override)
        dialog.close()

    def test_dialog_uses_standard_window_controls_and_bounded_geometry(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        dialog = GestureCustomEditorDialog(
            definition,
            config_source={"finger_extension_angle": 155.0, "mouse_tracking_pending_frames": 1, "ending_frames": 2},
        )
        flags = dialog.windowFlags()
        self.assertTrue(bool(flags & Qt.Window))
        self.assertTrue(bool(flags & Qt.WindowMinimizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowMaximizeButtonHint))
        self.assertTrue(dialog.isSizeGripEnabled())

        screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
        self.assertLess(dialog.width(), 1280)
        self.assertLessEqual(dialog.width(), screen_geometry.width())
        self.assertLessEqual(dialog.height(), screen_geometry.height())
        self.assertLessEqual(dialog.x(), screen_geometry.right())
        self.assertLessEqual(dialog.y(), screen_geometry.bottom())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
