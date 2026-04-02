import unittest

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


if __name__ == "__main__":
    unittest.main()
