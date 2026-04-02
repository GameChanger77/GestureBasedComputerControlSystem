import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.HandsData import HandsData
from backend.Strategizer import Strategizer
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
from backend.gestures.mouse_mode.ScrollGesture import ScrollGesture


class _ActionStub:
    def __init__(self):
        self.moves = []
        self.left_clicks = []
        self.right_clicks = []
        self.scrolls = []

    def move_cursor(self, x, y):
        self.moves.append((x, y))

    def left_click(self, x, y):
        self.left_clicks.append((x, y))

    def right_click(self, x, y):
        self.right_clicks.append((x, y))

    def scroll(self, delta_x=0, delta_y=0):
        self.scrolls.append((delta_x, delta_y))

    def press_key(self, *_args, **_kwargs):
        pass

    def release_key(self, *_args, **_kwargs):
        pass

    def type_text(self, *_args, **_kwargs):
        pass

    def set_pending_latency_origin_ts_ns(self, _ts):
        pass

    def get_runtime_debug_snapshot(self):
        return {
            "cursor": {"local_x": 0, "local_y": 0, "global_x": 0, "global_y": 0},
            "latest_action_event": None,
        }


class _ConfigStub(dict):
    def __init__(self, config_path: Path):
        super().__init__(
            keyboard_layout="qwerty",
            keyboard_theme="dark",
            finger_extension_angle=155.0,
            scroll_sensitivity=100,
            pinch_threshold=0.30,
            left_click_hold_time_sec=1.0,
            mouse_tracking_pending_frames=1,
            click_pending_frames=1,
            scroll_pending_frames=1,
            ending_frames=1,
            keyboard_mode_entry_pending_frames=1,
            keyboard_mode_exit_pending_frames=1,
            keyboard_mode_exit_extension_angle=150.0,
            keyboard_mode_exit_max_openness=0.16,
            keyboard_mode_exit_max_extension_ratio=0.90,
            keyboard_mode_exit_max_avg_finger_angle=145.0,
            keyboard_mode_switch_cooldown_sec=0.0,
            screen_safe_margin=50,
            debug_mode=False,
        )
        self.config_path = config_path
        self.config = self


def _hands_with_y(index_y: float = 0.0, middle_y: float = 0.0):
    wrist = np.zeros((21, 3), dtype=np.float32)
    camera = np.zeros((21, 3), dtype=np.float32)
    camera[8] = np.array([0.5, index_y, 0.0], dtype=np.float32)
    camera[12] = np.array([0.5, middle_y, 0.0], dtype=np.float32)
    return HandsData({"Right": wrist}, {"Right": camera})


class MouseRuntimeArbitrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.config = _ConfigStub(Path(self._tmp_dir.name) / "gesture_config.json")
        self.action = _ActionStub()
        self.strategizer = Strategizer(self.action, self.config, 1920, 1080)

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_left_click_active_suppresses_mouse_move_while_held(self):
        left_click = next(
            gesture for gesture in self.strategizer.mouse_mode_gestures if getattr(gesture, "debug_name", "") == "Left Click"
        )
        move = next(
            gesture for gesture in self.strategizer.mouse_mode_gestures if getattr(gesture, "debug_name", "") == "Mouse Move"
        )

        hands = _hands_with_y()

        with patch.object(left_click, "detect_gesture", side_effect=[(False, None), (True, (100, 200)), (True, (100, 200)), (True, (100, 200))]), patch.object(
            move, "detect_gesture", side_effect=[(True, (10, 10)), (True, (20, 20)), (True, (30, 30)), (True, (40, 40))]
        ):
            self.strategizer.strategize(hands)
            self.strategizer.strategize(hands)
            self.strategizer.strategize(hands)
            self.strategizer.strategize(hands)

        snapshot = self.strategizer.get_debug_snapshot()
        mode_entries = {entry["name"]: entry for entry in snapshot["mode_candidates"]}
        self.assertEqual(self.action.left_clicks, [(100, 200)])
        self.assertTrue(mode_entries["Left Click"]["active"])
        self.assertTrue(mode_entries["Mouse Move"]["suppressed"])


class MousePoseRuleTests(unittest.TestCase):
    def test_left_click_rejects_when_ring_is_extended(self):
        gesture = LeftClickGesture(
            _ActionStub(),
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
        )
        hands = _hands_with_y()

        with patch("backend.gestures.mouse_mode.LeftClickGesture.are_fingers_pinched", return_value=True), patch(
            "backend.gestures.mouse_mode.LeftClickGesture.is_finger_extended",
            side_effect=[True, True, False],
        ):
            detected, _data = gesture.detect_gesture(hands)

        self.assertFalse(detected)

    def test_right_click_rejects_when_middle_is_extended(self):
        gesture = RightClickGesture(
            _ActionStub(),
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
        )
        hands = _hands_with_y()

        with patch("backend.gestures.mouse_mode.RightClickGesture.are_fingers_pinched", return_value=True), patch(
            "backend.gestures.mouse_mode.RightClickGesture.is_finger_extended",
            side_effect=[True, True, False],
        ):
            detected, _data = gesture.detect_gesture(hands)

        self.assertFalse(detected)

    def test_left_click_rejects_when_thumb_is_not_extended(self):
        gesture = LeftClickGesture(
            _ActionStub(),
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
        )
        hands = _hands_with_y()

        with patch("backend.gestures.mouse_mode.LeftClickGesture.are_fingers_pinched", return_value=True), patch(
            "backend.gestures.mouse_mode.LeftClickGesture.is_finger_extended",
            return_value=False,
        ):
            detected, _data = gesture.detect_gesture(hands)

        self.assertFalse(detected)

    def test_scroll_rejects_click_pinch_overlap(self):
        gesture = ScrollGesture(
            _ActionStub(),
            priority=5,
            scroll_sensitivity=100,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            pinch_threshold=0.3,
        )
        hands = _hands_with_y()

        with patch(
            "backend.gestures.mouse_mode.ScrollGesture.is_finger_extended",
            side_effect=[True, True, False, False],
        ), patch(
            "backend.gestures.mouse_mode.ScrollGesture.are_fingers_pinched",
            side_effect=[True, False],
        ):
            detected, _data = gesture.detect_gesture(hands)

        self.assertFalse(detected)

    def test_scroll_accumulates_small_movements_until_step_emits(self):
        action = _ActionStub()
        gesture = ScrollGesture(
            action,
            priority=5,
            scroll_sensitivity=100,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            pinch_threshold=0.3,
        )

        with patch(
            "backend.gestures.mouse_mode.ScrollGesture.is_finger_extended",
            side_effect=[True, True, False, False] * 4,
        ), patch(
            "backend.gestures.mouse_mode.ScrollGesture.are_fingers_pinched",
            return_value=False,
        ):
            self.assertFalse(gesture.update(_hands_with_y(0.0, 0.0)))
            self.assertFalse(gesture.update(_hands_with_y(0.004, 0.004)))
            self.assertFalse(gesture.update(_hands_with_y(0.008, 0.008)))
            self.assertTrue(gesture.update(_hands_with_y(0.012, 0.012)))

        self.assertEqual(action.scrolls, [(0, 1)])
        self.assertAlmostEqual(gesture._scroll_residual_y, 0.2, places=4)

    def test_scroll_rejects_when_ring_is_clearly_extended(self):
        gesture = ScrollGesture(
            _ActionStub(),
            priority=5,
            scroll_sensitivity=100,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            pinch_threshold=0.3,
        )
        hands = _hands_with_y()

        with patch(
            "backend.gestures.mouse_mode.ScrollGesture.is_finger_extended",
            side_effect=[True, True, True],
        ):
            detected, _data = gesture.detect_gesture(hands)

        self.assertFalse(detected)


if __name__ == "__main__":
    unittest.main()
