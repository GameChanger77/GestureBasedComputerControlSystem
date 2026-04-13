import unittest
from unittest.mock import patch

from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture


class _ActionStub:
    def __init__(self):
        self.left_clicks = []
        self.double_clicks = []
        self.moves = []
        self.left_button_down = 0
        self.left_button_up = 0
        self.pending_latency = []

    def left_click(self, x, y):
        self.left_clicks.append((x, y))

    def double_click(self, x, y):
        self.double_clicks.append((x, y))

    def move_cursor(self, x, y):
        self.moves.append((x, y))

    def hold_left_click(self):
        self.left_button_down += 1

    def release_left_click(self):
        self.left_button_up += 1

    def set_pending_latency_origin_ts_ns(self, ts):
        self.pending_latency.append(ts)


class _CursorSmoothingActionStub(_ActionStub):
    def left_click(self, x=None, y=None):
        self.left_clicks.append((x, y))

    def double_click(self, x=None, y=None):
        self.double_clicks.append((x, y))

    def cursor_move_smoothing_enabled(self):
        return True


class _ScriptedLeftClickGesture(LeftClickGesture):
    def __init__(self, action, responses, **kwargs):
        super().__init__(action, **kwargs)
        self._responses = list(responses)

    def detect_gesture(self, _hands_data):
        if self._responses:
            return self._responses.pop(0)
        return False, None


class LeftClickRuntimeTests(unittest.TestCase):
    def test_left_click_triggers_once_on_release(self):
        action = _ActionStub()
        gesture = _ScriptedLeftClickGesture(
            action,
            responses=[
                (True, (100, 200)),
                (True, (100, 200)),
                (False, None),
                (False, None),
            ],
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            double_click_hold_time=0.5,
            drag_deadzone_px=24,
        )

        with patch("backend.gestures.mouse_mode.LeftClickGesture.time.time", side_effect=[100.0, 100.1]):
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=1))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=2))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=3))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=4))

        self.assertEqual(action.left_clicks, [(100, 200)])
        self.assertEqual(action.double_clicks, [])
        self.assertEqual(action.left_button_down, 0)
        self.assertEqual(action.left_button_up, 0)

    def test_left_click_hold_triggers_double_click_without_release_click(self):
        action = _ActionStub()
        gesture = _ScriptedLeftClickGesture(
            action,
            responses=[
                (True, (100, 200)),
                (True, (100, 200)),
                (True, (100, 200)),
                (False, None),
                (False, None),
            ],
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            double_click_hold_time=0.5,
            drag_deadzone_px=24,
        )

        with patch("backend.gestures.mouse_mode.LeftClickGesture.time.time", side_effect=[100.0, 100.7]):
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=1))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=2))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=3))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=4))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=5))

        self.assertEqual(action.left_clicks, [])
        self.assertEqual(action.double_clicks, [(100, 200)])
        self.assertEqual(action.left_button_down, 0)
        self.assertEqual(action.left_button_up, 0)

    def test_left_click_drag_holds_moves_and_releases(self):
        action = _ActionStub()
        gesture = _ScriptedLeftClickGesture(
            action,
            responses=[
                (True, (100, 200)),
                (True, (100, 200)),
                (True, (150, 240)),
                (True, (180, 260)),
                (False, None),
                (False, None),
            ],
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            double_click_hold_time=0.5,
            drag_deadzone_px=24,
        )

        with patch("backend.gestures.mouse_mode.LeftClickGesture.time.time", side_effect=[100.0, 100.1, 100.2]):
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=1))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=2))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=3))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=4))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=5))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=6))

        self.assertEqual(action.left_clicks, [])
        self.assertEqual(action.double_clicks, [])
        self.assertEqual(action.left_button_down, 1)
        self.assertEqual(action.left_button_up, 1)
        self.assertEqual(action.moves, [(100, 200), (150, 240), (180, 260)])

    def test_click_and_double_click_follow_current_cursor_when_pointer_smoothing_is_enabled(self):
        action = _CursorSmoothingActionStub()
        gesture = _ScriptedLeftClickGesture(
            action,
            responses=[
                (True, (100, 200)),
                (True, (100, 200)),
                (False, None),
                (False, None),
                (True, (300, 400)),
                (True, (300, 400)),
                (True, (300, 400)),
                (False, None),
                (False, None),
            ],
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.3,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=1,
            double_click_hold_time=0.5,
            drag_deadzone_px=24,
        )

        with patch("backend.gestures.mouse_mode.LeftClickGesture.time.time", side_effect=[100.0, 100.1, 200.0, 200.7]):
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=1))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=2))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=3))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=4))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=5))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=6))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=7))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=8))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=9))

        self.assertEqual(action.left_clicks, [(None, None)])
        self.assertEqual(action.double_clicks, [(None, None)])


if __name__ == "__main__":
    unittest.main()
