import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
