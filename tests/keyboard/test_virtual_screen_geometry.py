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


class VirtualScreenGeometryTests(unittest.TestCase):
    def test_get_screen_geometry_uses_virtual_desktop_bounds(self):
        fake_screen = _FakeScreen(_FakeGeometry(-1920, 0, 3840, 1080))

        with patch("main.QGuiApplication.primaryScreen", return_value=fake_screen):
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
            action._set_mouse_position(3839, 0)
            self.assertEqual(mouse.position, (1919, 120))
        finally:
            action.close()


if __name__ == "__main__":
    unittest.main()
