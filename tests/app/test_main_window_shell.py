import os
import unittest
from unittest.mock import patch

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
        self.assertIsNotNone(window.tutorial_button)
        self.assertIsNotNone(window.gesture_debug_widget)

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
        self.assertIsNotNone(window.tutorial_button)
        self.assertIsNone(window.gesture_debug_widget)
        window.close()

    def test_tutorial_button_opens_modal_dialog(self):
        with patch("frontend.main_window.TutorialDialog") as tutorial_dialog_cls:
            dialog_instance = tutorial_dialog_cls.return_value
            window = MainWindow(ui_mode="dev")

            window.open_tutorial()

            tutorial_dialog_cls.assert_called_once()
            dialog_instance.exec.assert_called_once()
            window.close()


if __name__ == "__main__":
    unittest.main()
