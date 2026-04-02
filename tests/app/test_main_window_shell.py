import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from frontend.main_window import MainWindow


class MainWindowShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dev_shell_switches_between_dashboard_and_settings(self):
        window = MainWindow(ui_mode="dev")

        self.assertIs(window.page_stack.currentWidget(), window.main_page)
        self.assertEqual(window.start_button.text(), "Start Tracking")
        self.assertEqual(window.status_label.text(), "Status: Not started")

        window.show_settings_page()
        self.assertIs(window.page_stack.currentWidget(), window.settings_page)

        window.show_main_page()
        self.assertIs(window.page_stack.currentWidget(), window.main_page)
        window.close()

    def test_prod_shell_keeps_runtime_badges_available(self):
        window = MainWindow(ui_mode="prod")

        self.assertEqual(window.start_button.text(), "Start Tracking")
        self.assertEqual(window.status_label.text(), "Status: Not started")
        self.assertTrue(window.mode_label.text().startswith("Mode:"))
        self.assertIsNotNone(window.settings_panel)
        window.close()

    def test_prod_shell_shows_hotkey_mode_badge(self):
        window = MainWindow(ui_mode="prod")
        window.strategizer = SimpleNamespace(get_mode_name=lambda: "HOTKEY")

        window._update_mode_label()

        self.assertEqual(window.mode_label.text(), "Mode: HOTKEY")
        self.assertEqual(window.mode_label.property("badgeTone"), "accent")
        window.close()


if __name__ == "__main__":
    unittest.main()
