import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.ProdWindowKeyboardSurface import ProdWindowKeyboardSurface


class ProdWindowKeyboardSurfaceTests(unittest.TestCase):
    def setUp(self):
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

    def test_open_hand_unlocks_and_follows_anchor(self):
        self.surface._right_open_for_drag = lambda hands_data: True
        self.surface._right_anchor_screen_px = lambda hands_data: (300.0, 220.0)

        for _ in range(5):
            state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
            self.assertTrue(state.extra_overlay["prod_window_locked"])

        state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertFalse(state.extra_overlay["prod_window_locked"])

        rect = state.extra_overlay["prod_window_rect_px"]
        self.assertGreaterEqual(rect["x"], 0)
        self.assertGreaterEqual(rect["y"], 0)

    def test_clamps_window_with_out_of_bounds_anchor(self):
        self.surface._right_open_for_drag = lambda hands_data: True
        self.surface._right_anchor_screen_px = lambda hands_data: (5000.0, 5000.0)

        state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        rect = state.extra_overlay["prod_window_rect_px"]
        self.assertLessEqual(rect["x"] + rect["w"], 1920)
        self.assertLessEqual(rect["y"] + rect["h"], 1080)

    def test_closing_hand_locks_window(self):
        self.surface._right_open_for_drag = lambda hands_data: True
        self.surface._right_anchor_screen_px = lambda hands_data: (480.0, 380.0)

        for _ in range(6):
            state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertFalse(state.extra_overlay["prod_window_locked"])

        self.surface._right_open_for_drag = lambda hands_data: False
        state = self.surface.update_layout(self.empty, paused=False, rows=self.rows)
        self.assertTrue(state.extra_overlay["prod_window_locked"])

    def test_drag_requires_fully_open_palm_facing_camera(self):
        hands = HandsData({"Right": np.zeros((21, 3), dtype=np.float32)}, {"Right": np.zeros((21, 3), dtype=np.float32)})

        with patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.is_hand_fully_open",
            return_value=True,
        ) as open_mock:
            self.assertTrue(self.surface._right_open_for_drag(hands))

        open_mock.assert_called_once_with(
            hands.wrist.right,
            extension_threshold=self.surface.open_extension_threshold,
            min_extended_fingers=5,
            openness_threshold=0.08,
            require_palm_facing_camera=True,
            min_palm_normal_z=self.surface.open_min_palm_normal_z,
        )

    def test_uses_anchor_screen_when_anchor_is_on_non_primary_display(self):
        secondary_geom = SimpleNamespace(x=lambda: 1920, y=lambda: 0, width=lambda: 1280, height=lambda: 720)
        secondary_screen = SimpleNamespace(availableGeometry=lambda: secondary_geom)
        primary_geom = SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 1920, height=lambda: 1080)
        primary_screen = SimpleNamespace(availableGeometry=lambda: primary_geom)

        with patch("backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.screenAt", return_value=secondary_screen), patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=primary_screen,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))

        self.assertEqual(self.surface._screen_origin_x_px, 1920.0)
        self.assertEqual(self.surface._screen_width_px, 1280.0)

    def test_falls_back_to_primary_screen_when_anchor_screen_missing(self):
        primary_geom = SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 1920, height=lambda: 1080)
        primary_screen = SimpleNamespace(availableGeometry=lambda: primary_geom)

        with patch("backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.screenAt", return_value=None), patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=primary_screen,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))

        self.assertEqual(self.surface._screen_origin_x_px, 0.0)
        self.assertEqual(self.surface._screen_width_px, 1920.0)

    def test_clamping_uses_resolved_screen_geometry(self):
        secondary_geom = SimpleNamespace(x=lambda: 1920, y=lambda: 0, width=lambda: 1280, height=lambda: 720)
        secondary_screen = SimpleNamespace(availableGeometry=lambda: secondary_geom)
        primary_geom = SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 1920, height=lambda: 1080)
        primary_screen = SimpleNamespace(availableGeometry=lambda: primary_geom)

        with patch("backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.screenAt", return_value=secondary_screen), patch(
            "backend.gestures.keyboard_mode.ProdWindowKeyboardSurface.QGuiApplication.primaryScreen",
            return_value=primary_screen,
        ):
            self.surface._refresh_active_screen_geometry((2300.0, 300.0))
            x, y = self.surface._clamp_window_position(4000.0, 4000.0)

        self.assertLessEqual(x + self.surface.window_width_px, 1920.0 + 1280.0)
        self.assertLessEqual(y + self.surface.window_height_px, 720.0)


if __name__ == "__main__":
    unittest.main()
