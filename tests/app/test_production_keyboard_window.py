import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from frontend.production_keyboard_window import ProductionKeyboardWindow


class ProductionKeyboardWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ProductionKeyboardWindow()

    def tearDown(self):
        self.window.close()

    def test_window_is_configured_as_pass_through_overlay(self):
        flags = self.window.windowFlags()
        self.assertTrue(bool(flags & Qt.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowStaysOnTopHint))
        self.assertTrue(bool(flags & Qt.WindowTransparentForInput))
        self.assertTrue(bool(flags & Qt.WindowDoesNotAcceptFocus))

    def test_valid_prod_overlay_shows_without_raising_window(self):
        overlay = {
            "enabled": True,
            "surface": "prod",
            "prod_window_rect_px": {"x": 100, "y": 200, "w": 900, "h": 300},
            "prod_window_rect_norm": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.3},
        }

        with patch.object(self.window, "show") as show_mock, patch.object(self.window, "raise_") as raise_mock, patch.object(
            self.window, "update"
        ) as update_mock, patch.object(self.window, "_fade_to") as fade_mock:
            self.window.set_overlay_data(overlay)

        show_mock.assert_called_once()
        raise_mock.assert_not_called()
        update_mock.assert_called_once()
        fade_mock.assert_called_once()

    def test_invalid_overlay_hides_window(self):
        with patch.object(self.window, "hide") as hide_mock:
            self.window.set_overlay_data(None)

        hide_mock.assert_called_once()

    def test_visible_window_updates_without_re_raising(self):
        overlay = {
            "enabled": True,
            "surface": "prod",
            "prod_window_rect_px": {"x": 100, "y": 200, "w": 900, "h": 300},
            "prod_window_rect_norm": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.3},
        }

        with patch.object(self.window, "isVisible", return_value=True), patch.object(
            self.window, "raise_"
        ) as raise_mock, patch.object(self.window, "update") as update_mock, patch.object(
            self.window, "_fade_to"
        ) as fade_mock, patch.object(self.window, "show") as show_mock:
            self.window.set_overlay_data(overlay)

        raise_mock.assert_not_called()
        update_mock.assert_called_once()
        fade_mock.assert_not_called()
        show_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
