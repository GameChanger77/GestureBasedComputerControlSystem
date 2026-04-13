import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.GestureConfig import GestureConfig
from frontend.widgets.settings.settings_panel import SettingsPanel


class SettingsPanelKeyboardOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_keyboard_page_exists_in_dev_and_prod(self):
        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            page_names = [panel._submenu_list.item(i).text() for i in range(panel._submenu_list.count())]

            self.assertIn("Keyboard", page_names)
            self.assertIn("keyboard_layout", panel._field_controls)
            self.assertIn("keyboard_theme", panel._field_controls)
            self.assertIn("dominant_hand", panel._field_controls)

    def test_keyboard_choices_are_populated_and_round_trip(self):
        panel = SettingsPanel(ui_mode="prod")
        panel.load_values(
            {
                "keyboard_layout": "colemak",
                "keyboard_theme": "light",
                "camera_index": 0,
                "camera_backend": 0,
                "camera_device_path": "",
                "camera_device_name": "",
            }
        )

        layout_combo = panel._field_controls["keyboard_layout"]["combo"]
        theme_combo = panel._field_controls["keyboard_theme"]["combo"]
        layout_values = {layout_combo.itemData(i) for i in range(layout_combo.count())}
        theme_values = {theme_combo.itemData(i) for i in range(theme_combo.count())}

        self.assertIn("qwerty", layout_values)
        self.assertIn("azerty", layout_values)
        self.assertIn("qwertz", layout_values)
        self.assertIn("dvorak", layout_values)
        self.assertIn("colemak", layout_values)
        self.assertEqual(theme_values, {"dark", "light"})
        self.assertEqual(layout_combo.currentData(), "colemak")
        self.assertEqual(theme_combo.currentData(), "light")

        values = panel.get_values()
        self.assertEqual(values["keyboard_layout"], "colemak")
        self.assertEqual(values["keyboard_theme"], "light")

    def test_camera_deadzone_settings_are_visible_on_camera_page_and_round_trip(self):
        expected_keys = {
            "camera_side_deadzone",
            "camera_top_deadzone",
            "camera_bottom_deadzone",
        }

        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            for key in expected_keys:
                self.assertIn(key, panel._field_controls)

            panel.load_values(
                {
                    "camera_index": 0,
                    "camera_backend": 0,
                    "camera_device_path": "",
                    "camera_device_name": "",
                    "camera_side_deadzone": 0.12,
                    "camera_top_deadzone": 0.03,
                    "camera_bottom_deadzone": 0.24,
                }
            )
            values = panel.get_values()
            self.assertAlmostEqual(values["camera_side_deadzone"], 0.12, places=2)
            self.assertAlmostEqual(values["camera_top_deadzone"], 0.03, places=2)
            self.assertAlmostEqual(values["camera_bottom_deadzone"], 0.24, places=2)

            page_definitions = GestureConfig.get_page_definitions(ui_mode=ui_mode)
            camera_keys = {
                key
                for keys in page_definitions.get("Camera", {}).values()
                for key in keys
            }
            self.assertTrue(expected_keys.issubset(camera_keys))

    def test_screen_interaction_sensitivity_slider_is_visible_on_controls_page(self):
        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            self.assertIn("screen_interaction_sensitivity", panel._field_controls)

            control = panel._field_controls["screen_interaction_sensitivity"]
            self.assertEqual(control["type"], "slider")
            self.assertEqual(control["slider"].minimum(), 100)
            self.assertEqual(control["slider"].maximum(), 200)
            self.assertEqual(control["slider"].singleStep(), 5)
            self.assertEqual(control["value_label"].text(), "1.00x")

            page_definitions = GestureConfig.get_page_definitions(ui_mode=ui_mode)
            controls_keys = {
                key
                for keys in page_definitions.get("Controls", {}).values()
                for key in keys
            }
            self.assertIn("screen_interaction_sensitivity", controls_keys)

    def test_screen_interaction_sensitivity_slider_round_trips_float_values(self):
        panel = SettingsPanel(ui_mode="prod")
        panel.load_values({"screen_interaction_sensitivity": 1.85})

        control = panel._field_controls["screen_interaction_sensitivity"]
        self.assertEqual(control["slider"].value(), 185)
        self.assertEqual(control["value_label"].text(), "1.85x")

        values = panel.get_values()
        self.assertAlmostEqual(values["screen_interaction_sensitivity"], 1.85, places=2)

    def test_cursor_move_smoothing_slider_is_visible_and_round_trips(self):
        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            self.assertIn("cursor_move_smoothing", panel._field_controls)

            control = panel._field_controls["cursor_move_smoothing"]
            self.assertEqual(control["type"], "slider")
            self.assertEqual(control["slider"].minimum(), 0)
            self.assertEqual(control["slider"].maximum(), 85)
            self.assertEqual(control["slider"].singleStep(), 5)
            self.assertEqual(control["value_label"].text(), "0.00")

            panel.load_values({"cursor_move_smoothing": 0.55})
            self.assertEqual(control["slider"].value(), 55)
            self.assertEqual(control["value_label"].text(), "0.55")

            values = panel.get_values()
            self.assertAlmostEqual(values["cursor_move_smoothing"], 0.55, places=2)

    def test_removed_screen_safe_margin_setting_is_not_exposed(self):
        self.assertNotIn("screen_safe_margin", GestureConfig.DEFAULT_CONFIG)
        self.assertNotIn("max_tracked_hands", GestureConfig.DEFAULT_CONFIG)
        self.assertNotIn("right_hand_only_processing", GestureConfig.DEFAULT_CONFIG)

        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            self.assertNotIn("screen_safe_margin", panel._field_controls)
            self.assertNotIn("max_tracked_hands", panel._field_controls)
            self.assertNotIn("right_hand_only_processing", panel._field_controls)

            page_definitions = GestureConfig.get_page_definitions(ui_mode=ui_mode)
            for groups in page_definitions.values():
                for keys in groups.values():
                    self.assertNotIn("screen_safe_margin", keys)
                    self.assertNotIn("max_tracked_hands", keys)
                    self.assertNotIn("right_hand_only_processing", keys)


if __name__ == "__main__":
    unittest.main()
