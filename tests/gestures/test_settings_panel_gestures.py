import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig
from backend.gesture_remap.rule_overrides import GestureRuleOverride
from frontend.widgets.settings.settings_panel import SettingsPanel


class _ConfigStub:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = {
            "keyboard_layout": "qwerty",
            "keyboard_theme": "dark",
            "camera_index": 0,
            "camera_backend": 0,
            "camera_device_path": "",
            "camera_device_name": "",
            "finger_extension_angle": 155.0,
            "scroll_sensitivity": 100,
            "pinch_threshold": 0.30,
            "mouse_tracking_pending_frames": 1,
            "click_pending_frames": 3,
            "scroll_pending_frames": 2,
            "ending_frames": 2,
            "keyboard_mode_entry_pending_frames": 6,
            "keyboard_mode_exit_pending_frames": 5,
            "keyboard_mode_exit_max_openness": 0.16,
            "keyboard_mode_exit_max_extension_ratio": 0.90,
            "keyboard_mode_exit_max_avg_finger_angle": 145.0,
        }


class SettingsPanelGesturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_gestures_page_exists_in_dev_and_prod(self):
        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            page_names = [panel._submenu_list.item(i).text() for i in range(panel._submenu_list.count())]
            self.assertIn("Gestures", page_names)
            self.assertEqual(panel._submenu_list.objectName(), "settingsNavList")

    def test_gesture_page_reflects_point_override_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            store = GestureOverrideStore(config_path.with_name("gesture_overrides.json"))
            panel = SettingsPanel(ui_mode="prod")
            store.set_override(
                "mouse_move",
                BuiltInGestureRegistry.get("mouse_move").default_pose_template,
                matcher_config=PoseMatcherConfig(),
            )

            panel.load_from_config(_ConfigStub(config_path))

            snapshot = panel._gesture_settings_page.snapshot_for("Mouse Move")
            self.assertEqual(snapshot["state"], "Custom (3D Hand Model)")

    def test_gesture_page_reflects_rule_override_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            store = GestureOverrideStore(config_path.with_name("gesture_overrides.json"))
            panel = SettingsPanel(ui_mode="prod")
            store.set_rule_override(
                "left_click",
                GestureRuleOverride(
                    conditions=[{"op": "hand_exists", "hand": "dominant"}],
                    pending_frames=3,
                    ending_frames=2,
                ),
            )

            panel.load_from_config(_ConfigStub(config_path))

            snapshot = panel._gesture_settings_page.snapshot_for("Left Click")
            self.assertEqual(snapshot["state"], "Custom (Rule-Based)")

    def test_edit_action_launches_unified_editor(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            panel = SettingsPanel(ui_mode="dev")
            panel.load_from_config(_ConfigStub(config_path))
            captured = {}

            class _DialogStub:
                def __init__(self, gesture_definition, config_source, override_record=None, validate_callback=None, parent=None):
                    captured["gesture_id"] = gesture_definition.id
                    captured["config_source"] = config_source
                    captured["override_record"] = override_record

                def exec(self):
                    return QDialog.DialogCode.Rejected

            with patch("frontend.widgets.settings.gesture_settings_page.GestureCustomEditorDialog", _DialogStub):
                panel._gesture_settings_page._on_edit_clicked("mouse_move")

            self.assertEqual(captured["gesture_id"], "mouse_move")
            self.assertIsInstance(captured["config_source"], dict)
            self.assertIsNone(captured["override_record"])

    def test_editor_uses_preview_pose_when_no_point_override_exists(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        panel = SettingsPanel(ui_mode="dev")
        self.assertFalse((definition.preview_pose_template.as_array() == definition.saved_pose_template.as_array()).all())
        self.assertEqual(definition.preview_pose_template.name, "Mouse Move Preview (Neutral)")
        panel.close()

    def test_sidebar_selection_tracks_page_stack(self):
        panel = SettingsPanel(ui_mode="prod")
        page_names = [panel._submenu_list.item(i).text() for i in range(panel._submenu_list.count())]
        gestures_index = page_names.index("Gestures")
        panel._submenu_list.setCurrentRow(gestures_index)
        self.assertEqual(panel._page_stack.currentIndex(), gestures_index)


if __name__ == "__main__":
    unittest.main()
