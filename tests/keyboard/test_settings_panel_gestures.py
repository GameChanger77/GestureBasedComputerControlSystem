import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig
from frontend.widgets.settings_panel import SettingsPanel


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

    def test_gesture_page_reflects_custom_override_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            overrides_path = config_path.with_name("gesture_overrides.json")
            store = GestureOverrideStore(overrides_path)
            panel = SettingsPanel(ui_mode="prod")
            store.set_override(
                "mouse_move",
                BuiltInGestureRegistry.get("mouse_move").default_pose_template,
                matcher_config=PoseMatcherConfig(),
            )

            panel.load_from_config(_ConfigStub(config_path))

            state_items = [
                panel._gesture_settings_page.table.item(row, 2).text()
                for row in range(panel._gesture_settings_page.table.rowCount())
                if panel._gesture_settings_page.table.item(row, 0).text() == "Mouse Move"
            ]
            self.assertEqual(state_items, ["Custom"])

    def test_editor_uses_preview_pose_when_no_override_exists(self):
        definition = BuiltInGestureRegistry.get("mouse_move")
        panel = SettingsPanel(ui_mode="dev")
        self.assertFalse((definition.preview_pose_template.as_array() == definition.saved_pose_template.as_array()).all())
        self.assertEqual(definition.preview_pose_template.name, "Mouse Move Preview (Neutral)")
        panel.close()


if __name__ == "__main__":
    unittest.main()
