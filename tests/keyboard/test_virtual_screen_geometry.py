import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.Action import Action
from main import get_screen_geometry


class _FakeGeometry:
    def __init__(self, x, y, width, height):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._width

    def height(self):
        return self._height


class _FakeScreen:
    def __init__(self, geometry):
        self._geometry = geometry

    def virtualGeometry(self):
        return self._geometry


class _FakeMouse:
    def __init__(self):
        self.position = None

    def click(self, _button, _count):
        return None

    def scroll(self, _dx, _dy):
        return None

    def press(self, _button):
        return None

    def release(self, _button):
        return None


class _FakeKeyboard:
    pass


class _FakeQtPoint:
    def __init__(self, x, y):
        self._x = int(x)
        self._y = int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class _FakeQtCursor:
    position = (0, 0)

    @classmethod
    def pos(cls):
        return _FakeQtPoint(*cls.position)

    @classmethod
    def setPos(cls, x, y):
        cls.position = (int(x), int(y))


class VirtualScreenGeometryTests(unittest.TestCase):
    def test_get_screen_geometry_uses_virtual_desktop_bounds(self):
        fake_screen = _FakeScreen(_FakeGeometry(-1920, 0, 3840, 1080))

        with patch("PySide6.QtGui.QGuiApplication.primaryScreen", return_value=fake_screen):
            self.assertEqual(get_screen_geometry(), (-1920, 0, 3840, 1080))

    def test_action_offsets_mouse_position_by_virtual_origin(self):
        mouse = _FakeMouse()
        action = Action(
            mouse=mouse,
            keyboard_test=_FakeKeyboard(),
            screen_origin_x=-1920,
            screen_origin_y=120,
        )
        try:
            _FakeQtCursor.position = (0, 0)
            with patch.object(Action, "_qt_cursor_api", return_value=_FakeQtCursor):
                action._set_mouse_position(3839, 0)
            self.assertIsNone(mouse.position)
            self.assertEqual(_FakeQtCursor.position, (1919, 120))
        finally:
            action.close()

    def test_live_cursor_snapshot_prefers_qt_global_coordinates(self):
        mouse = _FakeMouse()
        action = Action(
            mouse=mouse,
            keyboard_test=_FakeKeyboard(),
            screen_origin_x=10,
            screen_origin_y=20,
        )
        try:
            mouse.position = (900, 1200)
            _FakeQtCursor.position = (150, 260)
            with patch.object(Action, "_qt_cursor_api", return_value=_FakeQtCursor):
                snapshot = action._live_cursor_snapshot()

            self.assertEqual(snapshot["global_x"], 150)
            self.assertEqual(snapshot["global_y"], 260)
            self.assertEqual(snapshot["local_x"], 140)
            self.assertEqual(snapshot["local_y"], 240)
        finally:
            action.close()

    def test_cursor_position_falls_back_to_mouse_when_qt_cursor_unavailable(self):
        mouse = _FakeMouse()
        action = Action(
            mouse=mouse,
            keyboard_test=_FakeKeyboard(),
            screen_origin_x=-100,
            screen_origin_y=75,
        )
        try:
            mouse.position = (300, 400)
            with patch.object(Action, "_qt_cursor_api", return_value=None):
                snapshot = action._live_cursor_snapshot()
                action._set_mouse_position(450, 250)

            self.assertEqual(snapshot["global_x"], 300)
            self.assertEqual(snapshot["global_y"], 400)
            self.assertEqual(snapshot["local_x"], 400)
            self.assertEqual(snapshot["local_y"], 325)
            self.assertEqual(mouse.position, (350, 325))
        finally:
            action.close()


if __name__ == "__main__":
    unittest.main()
