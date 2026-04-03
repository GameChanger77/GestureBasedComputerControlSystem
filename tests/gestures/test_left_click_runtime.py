import unittest
from unittest.mock import patch

from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture


class _ActionStub:
    def __init__(self):
        self.left_clicks = []
        self.pending_latency = []

    def left_click(self, x, y):
        self.left_clicks.append((x, y))

    def set_pending_latency_origin_ts_ns(self, ts):
        self.pending_latency.append(ts)


class _ScriptedLeftClickGesture(LeftClickGesture):
    def __init__(self, action, responses, **kwargs):
        super().__init__(action, **kwargs)
        self._responses = list(responses)

    def detect_gesture(self, _hands_data):
        if self._responses:
            return self._responses.pop(0)
        return False, None


class LeftClickRuntimeTests(unittest.TestCase):
    def test_left_click_triggers_on_confirm_and_once_more_on_hold(self):
        action = _ActionStub()
        gesture = _ScriptedLeftClickGesture(
            action,
            responses=[
                (True, (100, 200)),
                (True, (100, 200)),
                (True, (100, 200)),
                (True, (100, 200)),
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
        )

        with patch("backend.gestures.mouse_mode.LeftClickGesture.time.time", side_effect=[100.0, 100.1, 100.7]):
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=1))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=2))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=3))
            self.assertTrue(gesture.update(object(), frame_capture_ts_ns=4))
            self.assertFalse(gesture.update(object(), frame_capture_ts_ns=5))

        self.assertEqual(action.left_clicks, [(100, 200), (100, 200)])


if __name__ == "__main__":
    unittest.main()
