import os
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.ProdWindowKeyboardSurface import ProdWindowKeyboardSurface

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
    def __init__(self, *, available_geometry, virtual_geometry=None):
        self._available_geometry = available_geometry
        self._virtual_geometry = virtual_geometry or available_geometry

    def availableGeometry(self):
        return self._available_geometry

    def virtualGeometry(self):
        return self._virtual_geometry


class ProdWindowKeyboardSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.primary_screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1920, 1080),
            virtual_geometry=_FakeGeometry(0, 0, 1920, 1080),
        )
        self.primary_screen_patch = patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=self.primary_screen,
        )
        self.primary_screen_patch.start()

        self.load_position_patch = patch.object(
            ProdWindowKeyboardSurface,
            "_load_or_center_position",
            autospec=True,
        )
        self.save_position_patch = patch.object(
            ProdWindowKeyboardSurface,
            "_save_position",
            autospec=True,
        )
        load_mock = self.load_position_patch.start()
        self.save_position_patch.start()
        load_mock.side_effect = lambda surface: surface._center_position()

        self.surface = ProdWindowKeyboardSurface(
            config={"finger_extension_angle": 155.0},
            flip_x_for_mapping=False,
            screen_width=1920,
            screen_height=1080,
        )
        self.empty = HandsData({}, {})
        self.rows = [
            [{"id": "q", "label": "Q", "w": 1.0}],
        ]

    def tearDown(self):
        self.load_position_patch.stop()
        self.save_position_patch.stop()
        self.primary_screen_patch.stop()

    def test_open_hand_unlocks_and_follows_anchor(self):
        self.surface._dominant_open_for_drag = lambda hands_data: True
        self.surface._dominant_anchor_screen_px = lambda hands_data: (300.0, 220.0)

        for _ in range(5):
            state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
            self.assertTrue(state.extra_overlay["prod_window_locked"])

        state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertFalse(state.extra_overlay["prod_window_locked"])

        rect = state.extra_overlay["prod_window_rect_px"]
        self.assertGreaterEqual(rect["x"], 0)
        self.assertGreaterEqual(rect["y"], 0)

    def test_drag_can_move_window_onto_secondary_monitor(self):
        multi_monitor_screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1920, 1080),
            virtual_geometry=_FakeGeometry(0, 0, 3200, 1080),
        )
        self.surface._dominant_open_for_drag = lambda hands_data: True
        self.surface._dominant_anchor_screen_px = lambda hands_data: (2600.0, 220.0)

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=multi_monitor_screen,
        ):
            for _ in range(6):
                state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)

        rect = state.extra_overlay["prod_window_rect_px"]
        self.assertGreater(rect["x"], 1920)
        self.assertLessEqual(rect["x"] + rect["w"], 3200)

    def test_clamps_window_with_out_of_bounds_anchor_to_virtual_desktop(self):
        multi_monitor_screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1920, 1080),
            virtual_geometry=_FakeGeometry(-1920, 0, 3840, 1080),
        )
        self.surface._dominant_open_for_drag = lambda hands_data: True
        self.surface._dominant_anchor_screen_px = lambda hands_data: (5000.0, 5000.0)

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=multi_monitor_screen,
        ):
            for _ in range(6):
                state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)

        rect = state.extra_overlay["prod_window_rect_px"]
        self.assertLessEqual(rect["x"] + rect["w"], 1920)
        self.assertLessEqual(rect["y"] + rect["h"], 1080)

    def test_closing_hand_locks_window(self):
        self.surface._dominant_open_for_drag = lambda hands_data: True
        self.surface._dominant_anchor_screen_px = lambda hands_data: (480.0, 380.0)

        for _ in range(6):
            state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertFalse(state.extra_overlay["prod_window_locked"])

        self.surface._dominant_open_for_drag = lambda hands_data: False
        state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertTrue(state.extra_overlay["prod_window_locked"])

    def test_drag_requires_fully_open_palm_facing_camera(self):
        hands = HandsData(
            {"Left": np.zeros((21, 3), dtype=np.float32)},
            {"Left": np.zeros((21, 3), dtype=np.float32)},
            dominant_hand="left",
        )

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.is_hand_fully_open",
            return_value=True,
        ) as open_mock:
            self.assertTrue(self.surface._dominant_open_for_drag(hands))

        open_mock.assert_called_once_with(
            hands.wrist.dominant,
            extension_threshold=self.surface.open_extension_threshold,
            min_extended_fingers=5,
            openness_threshold=0.08,
            require_palm_facing_camera=True,
            min_palm_normal_z=self.surface.open_min_palm_normal_z,
        )

    def test_anchor_mapping_applies_camera_deadzones(self):
        screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1000, 500),
            virtual_geometry=_FakeGeometry(0, 0, 1000, 500),
        )

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=screen,
        ):
            surface = ProdWindowKeyboardSurface(
                config={
                    "finger_extension_angle": 155.0,
                    "camera_side_deadzone": 0.10,
                    "camera_top_deadzone": 0.0,
                    "camera_bottom_deadzone": 0.20,
                },
                flip_x_for_mapping=False,
                screen_width=1000,
                screen_height=500,
            )

        camera = np.zeros((21, 3), dtype=np.float32)
        camera[8] = np.array([0.05, 0.95, 0.0], dtype=np.float32)
        hands = HandsData({}, {"Right": camera})

        anchor_x, anchor_y = surface._dominant_anchor_screen_px(hands)
        self.assertAlmostEqual(anchor_x, 0.0, places=3)
        self.assertAlmostEqual(anchor_y, 500.0, places=3)

    def test_uses_virtual_desktop_geometry_from_primary_screen(self):
        multi_monitor_screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1920, 1080),
            virtual_geometry=_FakeGeometry(-1920, 0, 3840, 1080),
        )

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=multi_monitor_screen,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))

        self.assertEqual(self.surface._screen_origin_x_px, -1920.0)
        self.assertEqual(self.surface._screen_width_px, 3840.0)

    def test_falls_back_to_constructor_screen_size_when_primary_screen_missing(self):
        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=None,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))

        self.assertEqual(self.surface._screen_origin_x_px, 0.0)
        self.assertEqual(self.surface._screen_width_px, 1920.0)

    def test_clamping_uses_virtual_desktop_geometry(self):
        multi_monitor_screen = _FakeScreen(
            available_geometry=_FakeGeometry(0, 0, 1920, 1080),
            virtual_geometry=_FakeGeometry(-1920, 0, 3840, 1080),
        )

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=multi_monitor_screen,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))
            x, y = self.surface._clamp_window_position(4000.0, 4000.0)

        self.assertLessEqual(x + self.surface.window_width_px, 1920.0)
        self.assertLessEqual(y + self.surface.window_height_px, 1080.0)


if __name__ == "__main__":
    unittest.main()
